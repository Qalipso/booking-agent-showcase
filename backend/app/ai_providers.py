"""Провайдеры AI-диалога: где взять ключ, чем проверить, каким протоколом ходить.

Единственный список на весь сервис: по нему админка рисует карточки подключения,
проверяет ключ и выбирает клиента в ``agent.py``. Раньше выбор провайдера жил в
трёх местах и расходился — в схеме формы были две опции, в коде три ветки.

Бесплатные тарифы (Groq и Google AI Studio) идут первыми: салону, который только
пробует бота, платить за диалог незачем, а оба говорят на диалекте OpenAI Chat
Completions — отдельного кода под них не нужно. По умолчанию предлагается Groq:
ключ выдаётся сразу по почте, а лимит там на запросы в минуту, а не в сутки —
дневной потолок Gemini салон с потоком клиентов упирает к вечеру.
"""

from __future__ import annotations

import httpx

TIMEOUT = 15.0

PROVIDERS: dict[str, dict] = {
    "groq": {
        "title": "Groq",
        "note": "Открытые модели на быстром железе. Регистрация по почте, карта не нужна.",
        "free": True,
        "recommended": True,
        "freeNote": "Бесплатный тариф с лимитом запросов в минуту",
        "keyUrl": "https://console.groq.com/keys",
        "baseUrl": "https://api.groq.com/openai/v1",
        "defaultModel": "llama-3.3-70b-versatile",
        "kind": "chat",
    },
    "google": {
        "title": "Google AI Studio",
        "note": "Gemini. Ключ выдаётся сразу, карта не нужна.",
        "free": True,
        "recommended": False,
        "freeNote": "Бесплатный тариф с дневным лимитом запросов",
        "keyUrl": "https://aistudio.google.com/apikey",
        "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai",
        # Конкретные версии Google закрывает для новых аккаунтов: 2.5-flash
        # перестала выдаваться прямо посреди подключения. Алиас не протухает.
        "defaultModel": "gemini-flash-latest",
        "kind": "chat",
    },
    "openai": {
        "title": "OpenAI",
        "note": "Самые предсказуемые вызовы инструментов. Нужен платный аккаунт.",
        "free": False,
        "freeNote": "Оплата по расходу, минимум пополнения — 5 $",
        "keyUrl": "https://platform.openai.com/api-keys",
        "baseUrl": "https://api.openai.com/v1",
        "defaultModel": "gpt-4.1-mini",
        "kind": "responses",
    },
    "anthropic": {
        "title": "Anthropic",
        "note": "Claude. Аккуратно ведёт длинный диалог. Нужен платный аккаунт.",
        "free": False,
        "freeNote": "Оплата по расходу",
        "keyUrl": "https://console.anthropic.com/settings/keys",
        "baseUrl": "https://api.anthropic.com/v1",
        "defaultModel": "claude-haiku-4-5-20251001",
        "kind": "anthropic",
    },
}


class ProviderError(RuntimeError):
    """Текст безопасно показывать в админке."""


def catalog() -> list[dict]:
    """Список для карточек подключения. Ключей и секретов здесь нет."""
    return [
        {"id": pid, "title": p["title"], "note": p["note"], "free": p["free"],
         "freeNote": p["freeNote"], "keyUrl": p["keyUrl"], "defaultModel": p["defaultModel"],
         "recommended": bool(p.get("recommended"))}
        for pid, p in PROVIDERS.items()
    ]


def get(provider: str) -> dict:
    try:
        return PROVIDERS[provider]
    except KeyError:
        raise ProviderError(f"Неизвестный провайдер: {provider}") from None


def _headers(provider: str, api_key: str) -> dict:
    if PROVIDERS[provider]["kind"] == "anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {api_key}"}


def verify(provider: str, api_key: str) -> list[str]:
    """Проверяет ключ и возвращает доступные модели.

    Список моделей нужен не для красоты: у бесплатных провайдеров имена моделей
    меняются чаще, чем выходят релизы бота, и «ключ верный, но модель не та» —
    самый частый способ получить молчащего бота вместо работающего.
    """
    cfg = get(provider)
    if not api_key:
        raise ProviderError("Пустой ключ")
    try:
        response = httpx.get(f"{cfg['baseUrl']}/models", headers=_headers(provider, api_key),
                             timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{cfg['title']} недоступен: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        # Отдельная ветка под неверный ключ: Google отвечает на него 400, а не
        # 401, и голое «ответил 400» владельцу салона ничего не объясняет.
        detail = _error_text(payload)
        if response.status_code in (401, 403) or "api key" in detail.lower() or "api_key" in detail.lower():
            raise ProviderError(f"{cfg['title']} не принял ключ — скопируйте его заново")
        raise ProviderError(f"{cfg['title']}: {detail or f'ответил {response.status_code}'}")

    rows = payload.get("data") or payload.get("models") or []
    return [str(r.get("id") or r.get("name") or "").split("/")[-1] for r in rows if isinstance(r, dict)]


def _error_text(payload: dict) -> str:
    """Сообщение об ошибке из ответа: у провайдеров три разных формы одного и того же."""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("status") or "")[:200]
    return str(error or payload.get("message") or "")[:200]


def probe(provider: str, api_key: str, model: str) -> str:
    """Настоящий короткий запрос к модели — по кнопке «Проверить».

    Валидный ключ ещё не значит работающий диалог: у модели может не быть
    доступа, а имя — устареть. Дешевле узнать это здесь, чем на первом клиенте.
    """
    cfg = get(provider)
    prompt = "Ответь одним словом: готово"
    headers = _headers(provider, api_key) | {"Content-Type": "application/json"}
    try:
        if cfg["kind"] == "anthropic":
            response = httpx.post(f"{cfg['baseUrl']}/messages", headers=headers, timeout=TIMEOUT,
                                  json={"model": model, "max_tokens": 256,
                                        "messages": [{"role": "user", "content": prompt}]})
        else:
            response = httpx.post(f"{cfg['baseUrl']}/chat/completions", headers=headers, timeout=TIMEOUT,
                                  json={"model": model, "max_tokens": 256,
                                        "messages": [{"role": "user", "content": prompt}]})
    except httpx.HTTPError as exc:
        raise ProviderError(f"{cfg['title']} недоступен: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        raise ProviderError(_error_text(payload) or f"{cfg['title']} ответил {response.status_code}")

    if cfg["kind"] == "anthropic":
        blocks = payload.get("content") or []
        return " ".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()
    choices = payload.get("choices") or [{}]
    return ((choices[0].get("message") or {}).get("content") or "").strip()
