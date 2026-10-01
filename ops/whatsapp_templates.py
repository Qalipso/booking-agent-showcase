#!/usr/bin/env python3
"""Создание WhatsApp-шаблонов с кнопкой «Перенести или отменить».

Тело шаблона утверждённой версии менять нельзя, а ссылку на свои записи клиенту
дать надо — поэтому подтверждение и оба напоминания пересоздаются как
`twilio/call-to-action` с кнопкой, в адрес которой уезжает хвост личной ссылки.
Кнопка — на каждом из трёх языков: шаблон Meta одноязычен, и заголовок кнопки
тоже часть шаблона.

    python3 ops/whatsapp_templates.py --tenant demo-salon --dry-run
    python3 ops/whatsapp_templates.py --tenant demo-salon --create
    python3 ops/whatsapp_templates.py --tenant demo-salon --status

Запускать можно снаружи контейнера — креды берутся из хранилища секретов того же
тенанта. Созданный шаблон подаётся на модерацию сразу; ответ Meta приходит от
нескольких минут до суток, до этого Content SID в конфиг вписывать рано.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

CONTENT_API = "https://content.twilio.com/v1/Content"
# По этой строке задание по расписанию понимает, что настройки изменились и
# контейнеры пора перезапустить: их читают при старте.
RESTART_MARK = "нужен перезапуск: вписан новый Content SID"
# Заголовок кнопки на языке сообщения: испанская кнопка под русским текстом
# выглядит чужой вставкой, а не частью письма салона.
BUTTON_TITLES = {"es": "Cambiar o cancelar", "ru": "Перенести или отменить",
                 "en": "Reschedule or cancel"}

# Тексты берём из самого приложения: шаблон в Meta и текст на `console` обязаны
# совпадать слово в слово, а держать вторую копию здесь — верный способ увидеть
# расхождение уже после модерации.
KINDS = ("booking_confirmation", "booking_reminder_day_before", "booking_reminder_today")
BUTTON_LANGUAGES = ("es", "ru", "en")

SAMPLES = {
    "es": {"name": "Ana", "service": "Corte de dama", "date": "martes, 18 de agosto",
           "time": "15:00", "address": "100 Example Street"},
    "ru": {"name": "Анна", "service": "Женская стрижка", "date": "вт, 18 авг",
           "time": "15:00", "address": "100 Example Street"},
    "en": {"name": "Anna", "service": "Women's haircut", "date": "Tue, 18 Aug",
           "time": "15:00", "address": "100 Example Street"},
}


def template_name(kind: str, lang: str) -> str:
    """Имя шаблона в Meta.

    Поколений здесь два, и оба одобрены: `…_manage` — с кнопкой, `…_link` — с
    адресом внутри текста. Работает то, чьё имя вернёт эта функция: от него
    зависит, какие Content SID впишет `--activate`. Значение переменной под
    поколение подстраивается само — по тексту шаблона в `app.notify.templates`.

    Испанские названы без языкового суффикса: они появились раньше остальных и
    уже одобрены, переименование стоило бы новой модерации.
    """
    return f"{kind}_manage" if lang == "es" else f"{kind}_manage_{lang}"


def spec_for(kind: str, lang: str, link: bool = True) -> dict:
    """Текст шаблона с нумерованными переменными и образцы значений для Meta."""
    from app.notify import templates

    text = (templates.LOCALIZED_TEMPLATES.get(lang, {}).get(kind)
            or templates.DEFAULT_TEMPLATES[kind])
    order = templates.variables_order(kind, manage_button=link)
    body = text
    for number, key in enumerate(order, start=1):
        body = body.replace("{{" + key + "}}", "{{" + str(number) + "}}")
    values = dict(SAMPLES.get(lang, SAMPLES["es"]))
    # Хвост, а не полный адрес: в адрес кнопки Meta пускает только окончание.
    values["link"] = f"c_9f2a?tenant=demo-salon&token=abc123&lang={lang}"
    samples = {str(i): values[key] for i, key in enumerate(order, start=1)}
    tail = str(order.index("link") + 1) if link else ""
    return {"body": body, "link": "{{" + tail + "}}" if tail else "", "samples": samples}


def tenant_settings(slug: str):
    from app.deps import runtime
    from app.notify.service import settings_for, public_base_url
    from app.tenants import registry

    runtime.store  # поднимает хранилище секретов
    tenant = registry.get(slug)
    return settings_for(tenant), public_base_url(tenant)


def api(method: str, url: str, auth: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Basic {auth}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Twilio {exc.code}: {exc.read().decode(errors='replace')}") from exc


def payload_for(name: str, spec: dict, base_url: str, language: str) -> dict:
    """Тело запроса Content API: текст плюс кнопка со ссылкой на свои записи."""
    return {
        "friendly_name": template_name(name, language),
        "language": language,
        "variables": spec["samples"],
        "types": {
            "twilio/call-to-action": {
                "body": spec["body"],
                "actions": [{
                    "type": "URL",
                    "title": BUTTON_TITLES.get(language, BUTTON_TITLES["es"]),
                    "url": f"{base_url}/manage/{spec['link']}",
                }],
            },
        },
    }


# Обычный текст без кнопки. Живут отдельно от кнопочных потому, что не должны
# задерживать их включение: `--activate` ждёт одобрения всех шаблонов с кнопкой,
# а эти к кнопке отношения не имеют.
#
# Перенос был здесь пропущен, и подтверждение замены уходило свободным текстом —
# то есть только в течение суток после сообщения клиента. Клиент, записавшийся
# через виджет, салону не писал никогда, и о новом времени не узнавал вовсе.
# Кнопки у переноса нет намеренно: она стоила бы отдельной модерации, а ссылку
# на свои записи клиент получит следующим напоминанием.
TEXT_KINDS = ("booking_rescheduled", "booking_cancelled")


def plain_spec_for(kind: str, lang: str) -> dict:
    """То же, что `spec_for`, но без личной ссылки.

    Отмена и перенос уходят без неё, и лишняя переменная в конце такой шаблон
    же и сломает: Twilio отвечает 63028, «number of parameters does not match».
    """
    return spec_for(kind, lang, link=False)


# Поле настроек, куда ложится Content SID каждого типа.
SID_FIELDS = {
    "booking_confirmation": "contentSidConfirmation",
    "booking_reminder_day_before": "contentSidReminderDayBefore",
    "booking_reminder_today": "contentSidReminderToday",
}

TEXT_SID_FIELDS = {"booking_rescheduled": "contentSidRescheduled",
                   "booking_cancelled": "contentSidCancelled"}


def text_payload_for(name: str, spec: dict, language: str) -> dict:
    """Тело запроса для шаблона без кнопки."""
    return {
        "friendly_name": name,
        "language": language,
        "variables": spec["samples"],
        "types": {"twilio/text": {"body": spec["body"]}},
    }


def sid_field(kind: str, lang: str) -> str:
    """Поле настроек под Content SID: у испанского оно без языкового суффикса."""
    base = SID_FIELDS[kind]
    return base if lang == "es" else base + lang.capitalize()


def existing_names(auth: str) -> dict[str, str]:
    """Уже созданные шаблоны: имя → SID. Повторный `--create` не плодит дубли."""
    page = api("GET", f"{CONTENT_API}?PageSize=100", auth)
    return {item["friendly_name"]: item["sid"] for item in page.get("contents", [])}


def approved_sids(auth: str) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Одобренные Meta шаблоны: (тип, язык) → SID для кнопочных и тип → SID для
    бескнопочных."""
    buttons: dict[tuple[str, str], str] = {}
    plain: dict[str, str] = {}
    known = {template_name(kind, lang): (kind, lang)
             for kind in KINDS for lang in BUTTON_LANGUAGES}
    for name, sid in existing_names(auth).items():
        target = known.get(name)
        if target is None and name not in TEXT_SID_FIELDS:
            continue
        status = (api("GET", f"{CONTENT_API}/{sid}/ApprovalRequests", auth)
                  .get("whatsapp") or {}).get("status")
        if status != "approved":
            continue
        if target is None:
            plain[name] = sid
        else:
            buttons[target] = sid
    return buttons, plain


def activate(slug: str, auth: str) -> int:
    """Включение кнопки: только когда одобрены все три шаблона.

    Частичное включение хуже выключенного: у неодобренного шаблона переменных
    по-прежнему пять, а очередь отправит шесть — и это сообщение не уйдёт вовсе.
    """
    from app.tenants import registry

    sids, plain = approved_sids(auth)
    tenant = registry.get(slug)

    # Точечными ключами, а не целой секцией: рядом лежат номера и адреса, которые
    # владелец мог поменять в панели, пока шла модерация.
    #
    # Бескнопочные вписываем сразу и по одному: они друг от друга не зависят, и
    # ждать ради них одобрения кнопочных значит держать готовый шаблон
    # невостребованным.
    # Только то, чего в настройках ещё нет: задание крутится каждые десять
    # минут, и патч на каждом круге означал бы перезапуск контейнеров каждые
    # десять минут до самого одобрения кнопочных шаблонов.
    fresh = {kind: sid for kind, sid in plain.items()
             if (tenant.notifications.get(TEXT_SID_FIELDS[kind]) or "") != sid}
    if fresh:
        tenant.patch_integration({f"notifications.{TEXT_SID_FIELDS[kind]}": sid
                                  for kind, sid in fresh.items()})
        for kind, sid in fresh.items():
            print(f"{kind}: {sid}")
        print(RESTART_MARK)

    # Шаблоны на языке клиента вписываем по мере одобрения: пока русского нет,
    # `provider_cfg` берёт испанский, и человек получает сообщение, а не тишину.
    extra = {(kind, lang): sid for (kind, lang), sid in sids.items()
             if lang != "es" and (tenant.notifications.get(sid_field(kind, lang)) or "") != sid}
    if extra:
        tenant.patch_integration({f"notifications.{sid_field(kind, lang)}": sid
                                  for (kind, lang), sid in extra.items()})
        # Языковой шаблон того же поколения, что и испанский: если тот уже
        # включён, вписанный SID сразу пойдёт в дело.
        for (kind, lang), sid in extra.items():
            print(f"{kind} [{lang}]: {sid}")
        print(RESTART_MARK)

    missing = [kind for kind in SID_FIELDS if (kind, "es") not in sids]
    if missing:
        print("Ещё не одобрены: " + ", ".join(missing))
        print("Кнопка не включена — иначе эти сообщения перестанут уходить.")
        return 1

    base = {kind: sids[(kind, "es")] for kind in SID_FIELDS}
    # Полный адрес или хвост для кнопки — решает текст шаблона в приложении, а
    # не настройка тенанта: отдельный флаг `manageLinkInText` здесь уже
    # разъезжался с шаблоном, и клиенты получали хвост без домена.
    turned_on = (tenant.notifications.get("manageButtonTemplates") is True
                 and all((tenant.notifications.get(SID_FIELDS[kind]) or "") == sid
                         for kind, sid in base.items()))
    if not turned_on:
        patch = {f"notifications.{SID_FIELDS[kind]}": sid for kind, sid in base.items()}
        patch["notifications.manageButtonTemplates"] = True
        tenant.patch_integration(patch)
        for kind, sid in base.items():
            print(f"{kind}: {sid}")
        print("Кнопка «Перенести или отменить» включена.")
        print(RESTART_MARK)

    # Успех — это когда вписаны все языки, а не только испанский. Иначе задание
    # снимет себя на первом же одобренном наборе, и русские с английскими
    # шаблонами останутся лежать одобренными, но невостребованными.
    waiting = [f"{kind} [{lang}]" for kind in SID_FIELDS for lang in BUTTON_LANGUAGES
               if not (tenant.notifications.get(sid_field(kind, lang)) or "")]
    if waiting:
        print("Ждут одобрения: " + ", ".join(waiting))
        return 1
    print("Все языки на месте.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default="demo-salon")
    parser.add_argument("--languages", nargs="*", default=list(BUTTON_LANGUAGES),
                        help="языки шаблонов с кнопкой (по умолчанию es ru en)")
    parser.add_argument("--language", default="es",
                        help="язык шаблонов без кнопки — отмены и переноса")
    parser.add_argument("--base-url", default="",
                        help="домен кнопки, если он ещё не прописан в настройках бизнеса")
    parser.add_argument("--only", nargs="*", default=[],
                        help="имена шаблонов в Meta, которые создавать (по умолчанию — все)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="показать, что уйдёт в Twilio")
    group.add_argument("--create", action="store_true", help="создать и подать на модерацию")
    group.add_argument("--status", action="store_true", help="статус модерации созданных шаблонов")
    group.add_argument("--activate", action="store_true",
                       help="вписать одобренные Content SID в настройки бизнеса и включить кнопку")
    args = parser.parse_args()

    settings, base_url = tenant_settings(args.tenant)
    base_url = args.base_url.rstrip("/") or base_url
    if not base_url:
        raise SystemExit("У бизнеса не задан публичный адрес — ссылке некуда вести")
    sid = settings.twilio.get("accountSid") or ""
    token = settings.twilio.get("authToken") or ""
    if not (sid and token) and not args.dry_run:
        raise SystemExit("Нет ключей Twilio у бизнеса")
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()

    if args.activate:
        return activate(args.tenant, auth)

    if args.status:
        page = api("GET", f"{CONTENT_API}?PageSize=100", auth)
        for item in page.get("contents", []):
            name = item["friendly_name"]
            if not (name.endswith("_manage") or "_link" in name or name in TEXT_SID_FIELDS):
                continue
            approval = api("GET", f"{CONTENT_API}/{item['sid']}/ApprovalRequests", auth)
            whatsapp = (approval.get("whatsapp") or {})
            print(f"{item['friendly_name']:34} {item['sid']}  {whatsapp.get('status', '—')}")
        return 0

    plan = [(template_name(kind, lang), payload_for(kind, spec_for(kind, lang), base_url, lang))
            for kind in KINDS for lang in args.languages]
    plan += [(kind, text_payload_for(kind, plain_spec_for(kind, args.language), args.language))
             for kind in TEXT_KINDS]
    if args.only:
        plan = [(meta_name, body) for meta_name, body in plan if meta_name in args.only]
        if not plan:
            raise SystemExit("Под --only не подошёл ни один шаблон")

    # Созданный шаблон повторно не создаём: у Meta это дубль под тем же именем,
    # который придётся удалять руками.
    already = {} if args.dry_run else existing_names(auth)
    for meta_name, body in plan:
        if meta_name in already:
            print(f"{meta_name}: уже создан ({already[meta_name]}), пропущен")
            continue
        if args.dry_run:
            print(f"\n== {meta_name}")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            continue
        created = api("POST", CONTENT_API, auth, body)
        print(f"{meta_name}: создан {created['sid']}")
        # Категория Utility, не Marketing: это сервисное сообщение по записи,
        # которую клиент сделал сам.
        approval = api("POST", f"{CONTENT_API}/{created['sid']}/ApprovalRequests/whatsapp", auth,
                       {"name": meta_name, "category": "UTILITY"})
        print(f"{meta_name}: подан на модерацию — {approval.get('status', 'received')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
