"""FastAPI-приложение: виджет, админ-форма, AI-диалог, WhatsApp, уведомления."""

from __future__ import annotations

import logging
import os
import json
from html import escape
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import migrate
from .db import DatabaseNotConfigured
from .deps import runtime
from .routers import (admin, auth as auth_router, crm, insights, notifications, public,
                      team, telegram_hook, whatsapp)
from .schema import ROOT
from .tenants import ensure_default_tenant, registry
from .timeutil import BadDate, norm_lang

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

# Домен виджета Demo Salon. Перекрывается ALLOWED_ORIGINS в окружении сервера.
DEFAULT_ORIGINS = ("https://demo-salon.com", "https://www.demo-salon.com")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        store = runtime.store  # падать при старте, а не на первом запросе клиента
    except DatabaseNotConfigured as exc:
        log.error("%s", exc)
        raise

    # Приложение миграции не накатывает: две реплики начали бы это одновременно.
    # Но и работать на схеме, которой не соответствует код, оно не должно.
    if not store.url.startswith("sqlite") and not migrate.is_up_to_date(store.engine):
        raise RuntimeError(
            f"Схема базы не соответствует коду: применена ревизия "
            f"{migrate.current_revision(store.engine) or 'нет'}, ожидается {migrate.head_revision()}. "
            "Выполните: python -m backend.app.migrate"
        )

    created = ensure_default_tenant()
    if created:
        log.info("Создан бизнес по умолчанию: %s", created)
    for slug in registry.slugs():
        tenant = registry.get(slug)
        retention = int(tenant.policy("dataRetentionDays", 180) or 0)
        if retention:
            purged = runtime.store.purge_old_conversations(retention, tenant_id=slug)
            if purged:
                log.info("[%s] удалено диалогов старше %s дней: %s", slug, retention, purged)
    recovered = runtime.store.recover_stuck_notifications()
    if recovered:
        log.warning("Уведомлений возвращено в очередь после рестарта: %s", recovered)
    log.info("Бизнесов настроено: %s | CORS: %s", len(registry.slugs()) or "нет",
             ", ".join(allowed_origins()))
    yield


app = FastAPI(title="Demo Salon booking agent", version="2.0", lifespan=lifespan)


def allowed_origins() -> list[str]:
    """Домены, которым разрешён виджет.

    Порядок: ALLOWED_ORIGINS из окружения → домены из настроек бизнесов →
    домен Demo Salon. Звёздочка допускается только явным ``CORS_ALLOW_ALL=1``
    для локальной разработки: открытый CORS на проде отдаёт API любому сайту.
    """
    env_value = (os.getenv("ALLOWED_ORIGINS") or "").strip()
    if env_value:
        return [o.strip().rstrip("/") for o in env_value.split(",") if o.strip()]

    origins: list[str] = []
    for slug in registry.slugs():
        try:
            raw = (registry.get(slug).channel.get("allowedOrigins") or "").strip()
        except Exception:  # noqa: BLE001 — сломанный конфиг не должен открывать CORS
            continue
        origins += [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    if not origins:
        if os.getenv("CORS_ALLOW_ALL") == "1":
            return ["*"]
        return list(DEFAULT_ORIGINS)
    return sorted(set(origins))


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Заголовки безопасности на каждый ответ.

    Виджет встраивается на чужие сайты тегом `<script>`, а не в iframe, поэтому
    запрет фреймов ничего не ломает — зато закрывает кликджекинг на админке,
    где одним кликом меняются настройки бизнеса. HSTS ставим только на HTTPS:
    на локальном `http://localhost` он загнал бы браузер в бесконечный редирект.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")
    return response

app.include_router(public.router)
app.include_router(auth_router.router)
app.include_router(admin.router)
app.include_router(insights.router)
app.include_router(crm.router)
app.include_router(whatsapp.router)
app.include_router(notifications.router)
app.include_router(telegram_hook.router)
app.include_router(team.router)


@app.exception_handler(DatabaseNotConfigured)
async def _db_not_configured(_request, exc: DatabaseNotConfigured) -> JSONResponse:
    log.error("%s", exc)
    return JSONResponse({"detail": "База данных не настроена"}, status_code=503)


# Типовые причины отказа схемы по-русски. Остальное берём из сообщения pydantic:
# лучше английский текст, чем пустота.
_VALIDATION_REASONS = {
    "string_pattern_mismatch": "неверный формат",
    "missing": "обязательное поле",
    "string_too_short": "слишком короткое значение",
    "string_too_long": "слишком длинное значение",
    "int_parsing": "нужно число",
    "bool_parsing": "нужно да/нет",
}


@app.exception_handler(RequestValidationError)
async def _validation_failed(_request, exc: RequestValidationError) -> JSONResponse:
    """Отказ схемы — одной строкой, а не массивом объектов.

    Виджет показывает клиенту `detail` как есть, и стандартный список pydantic
    превращался на экране в «[object Object]». Поле называем явно: «date:
    неверный формат» чинится за секунду, «Ошибка проверки» — нет.
    """
    problems = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
        reason = _VALIDATION_REASONS.get(err.get("type", ""), err.get("msg", "недопустимое значение"))
        problems.append(f"{field}: {reason}" if field else reason)
    return JSONResponse({"detail": "; ".join(problems)[:300] or "Запрос не прошёл проверку"},
                        status_code=422)


@app.exception_handler(BadDate)
async def _bad_date(_request, exc: BadDate) -> JSONResponse:
    """Кривая дата — ошибка запроса, а не сбой сервиса.

    Схемы запросов ловят такое раньше и точнее, но дата долетает до расчётов
    и из мест без схемы. Страховка нужна, чтобы промах в формате не выглядел в
    логах как настоящая поломка: 500 с трейсом мешает искать реальные сбои.
    """
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.get("/health")
def health():
    """Проба для Coolify: без живой базы контейнер считается нездоровым."""
    try:
        with runtime.store.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "error": str(exc)[:200]}, status_code=503)
    return {"status": "ok", "tenants": registry.list()}


BOOK_TITLE = {"ru": "онлайн-запись", "es": "reserva en línea", "en": "online booking"}


def _public_shell(title: str, body: str, script: str = "") -> HTMLResponse:
    """Небольшие самостоятельные страницы для ссылок из уведомлений."""
    return HTMLResponse(f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>body{{margin:0;background:#f6f3ee;color:#231f20;font:16px system-ui,sans-serif}}main{{max-width:620px;margin:8vh auto;padding:32px;background:white;border-radius:24px;box-shadow:0 16px 50px #0001}}h1{{font-size:30px}}button,a.button{{display:inline-block;border:0;border-radius:12px;padding:13px 20px;background:#231f20;color:white;text-decoration:none;font-weight:700;cursor:pointer}}button.secondary{{background:#eee;color:#231f20}}textarea{{box-sizing:border-box;width:100%;min-height:110px;padding:12px;border:1px solid #ccc;border-radius:12px}}.stars button{{font-size:28px;background:transparent;color:#b88b35;padding:8px}}.item{{padding:16px 0;border-top:1px solid #eee}}small{{color:#706a66}}#message{{margin-top:18px}}</style></head><body><main>{body}</main><script>{script}</script></body></html>""")


@app.get("/book/{slug}", response_class=HTMLResponse)
def public_booking_page(slug: str, lang: str = ""):
    """Страница записи на своём домене — ссылка для шапки Instagram и рекламы.

    Заголовок, описание и Open Graph собираются здесь, а не скриптом: превью
    ссылки в WhatsApp и Instagram строит краулер, который JavaScript не
    выполняет. Всё остальное — услуги, мастера, часы — страница забирает
    публичным `/api/config`, тем же, что и виджет: держать прайс в двух местах
    значит однажды показать клиенту старую цену.
    """
    try:
        tenant = registry.get(slug)
    except Exception:  # noqa: BLE001
        return HTMLResponse("Бизнес не найден", status_code=404)

    # Без `?lang=` страницу открывают из шапки Instagram и из рекламы — то есть
    # чаще всего клиент салона, а не мы. Русский по умолчанию встречал испанца
    # русским заголовком.
    code = norm_lang(lang) if lang.strip() else tenant.default_lang
    salon = tenant.salon
    name = escape(str(salon.get("name") or tenant.title))
    tagline = escape(str(salon.get("tagline") or ""))
    address = escape(str(salon.get("address") or ""))
    summary = escape(" · ".join(x for x in (salon.get("tagline"), salon.get("address")) if x)
                     or BOOK_TITLE[code].capitalize())
    initial = escape((str(salon.get("name") or tenant.title).strip() or "A")[0].upper())

    return HTMLResponse(f"""<!doctype html>
<html lang="{code}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{name} — {escape(BOOK_TITLE[code])}</title>
<meta name="description" content="{summary}">
<meta property="og:type" content="website">
<meta property="og:title" content="{name}">
<meta property="og:description" content="{summary}">
<link rel="stylesheet" href="/book.css">
</head>
<body data-tenant="{escape(slug)}">
<div class="wrap">
  <header class="hero">
    <div class="mark" aria-hidden="true">{initial}</div>
    <h1>{name}</h1>
    {f'<p class="tagline">{tagline}</p>' if tagline else ''}
    <div class="facts" id="facts"></div>
    <button class="cta" id="cta" type="button" data-demo-salon-open>{escape(BOOK_TITLE[code])}</button>
  </header>
  <main id="content"></main>
</div>
<script src="/widget.js" data-api="" data-tenant="{escape(slug)}" data-lang="{code}"></script>
<script src="/book.js"></script>
</body>
</html>""")


# Ссылки из уведомлений ведут на обычные страницы `public/client.html`: разметка,
# стили и переводы лежат файлами, а не экранированной строкой внутри Python.
# Идентификатор, подпись и код бизнеса страница читает из самого адреса.
CLIENT_PAGE = ROOT / "public" / "client.html"


def _client_page(entity_id: str = "", section: str = ""):
    """Страница клиента — или разворот адреса, приехавшего одним куском.

    Кнопка утверждённого в Meta шаблона подставляет только хвост адреса, и
    прийти он может закодированным: `/review/abc%3Ftenant%3Ddemo-salon…`. Тогда
    подпись и код бизнеса оказываются внутри путевого сегмента, а страница
    ищет их в `?query` и не находит — «ссылка недействительна» на ровном месте.
    Разворачиваем редиректом: дальше всё как обычно.
    """
    if "?" in entity_id:
        return RedirectResponse(f"/{section}/{entity_id}", status_code=302)
    return FileResponse(CLIENT_PAGE, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/review/{review_id}", response_class=HTMLResponse)
def public_review_page(review_id: str):
    return _client_page(review_id, "review")


@app.get("/waitlist/{entry_id}", response_class=HTMLResponse)
def public_waitlist_page(entry_id: str):
    return _client_page(entry_id, "waitlist")


@app.get("/manage/{client_id}", response_class=HTMLResponse)
def public_manage_page(client_id: str):
    return _client_page(client_id, "manage")


# Кабинет мастера живёт на своём поддомене — `team.demo-salon.com`. Отдельный
# адрес нужен не технике, а людям: мастеру дают ссылку, которую он кладёт на
# домашний экран телефона, и она не должна выглядеть как кусок админки. Сам
# сервис тот же самый: один контейнер, одна база, разные двери.
TEAM_PAGE = ROOT / "public" / "team.html"

# Поддомен можно назвать явно (`TEAM_HOST`), а можно положиться на привычные
# имена: перепутать «team» с рабочим доменом салона невозможно.
TEAM_LABELS = ("team", "staff", "master", "masters")


def is_team_host(host: str) -> bool:
    named = (os.getenv("TEAM_HOST") or "").strip().lower()
    host = (host or "").split(":")[0].lower()
    if named and host == named:
        return True
    return host.split(".")[0] in TEAM_LABELS


def _team_page() -> FileResponse:
    return FileResponse(TEAM_PAGE, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/team", response_class=HTMLResponse)
def team_page():
    """Кабинет мастера по прямому адресу — работает и без отдельного поддомена."""
    return _team_page()


@app.get("/", response_class=HTMLResponse)
def site_root(request: Request):
    """Корень поддомена мастеров. На остальных доменах в корне ничего нет —
    виджет, панель и страницы клиента живут по своим адресам."""
    if is_team_host(request.headers.get("host", "")):
        return _team_page()
    raise HTTPException(404, "Страница не найдена")


class Assets(StaticFiles):
    """Статика с предсказуемым кэшированием.

    Свой код (`admin.js`, стили, разметка) обязан перечитываться после деплоя:
    иначе браузер оставляет вчерашний CSS с новой разметкой, и панель выглядит
    сломанной у всех, кто не нажал Ctrl+Shift+R. Вендор в `/vendor/` наоборот
    кэшируется надолго — его содержимое меняется только вместе с именем версии
    в README, а весит он больше всего остального.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.startswith("vendor/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            # no-cache — это не «не кэшировать», а «спроси сервер, изменилось ли».
            # Ответ 304 по ETag остаётся дешёвым.
            response.headers["Cache-Control"] = "no-cache"
        return response


# Виджет и админ-форма отдаются тем же сервисом — один контейнер, один домен.
app.mount("/", Assets(directory=ROOT / "public", html=True), name="static")
