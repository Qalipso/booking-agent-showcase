"""Расшифровка голосовых сообщений клиента.

В Латинской Америке голосовые — обычный способ переписки: клиент диктует
«hola, quiero un corte mañana», а не набирает текст. Ни DIKIDI, ни YCLIENTS их
не понимают — там переписку ведёт человек. Для нас это единственное место, где
разрыв делается в нашу сторону, а не догоняется.

Отдельный провайдер здесь не заводится: и Groq, и OpenAI отдают расшифровку по
адресу ``/audio/transcriptions`` в одном и том же диалекте, а их базовый адрес и
ключ у бизнеса уже настроены для диалога (``ai_providers.PROVIDERS``). Салон,
подключивший бесплатный Groq, получает голосовые тем же ключом и бесплатно.

Переменные окружения ``TRANSCRIBE_PROVIDER``, ``TRANSCRIBE_MODEL`` и
``TRANSCRIBE_API_KEY`` перекрывают выбор — на случай, когда диалог ведёт модель
одного поставщика, а слушает другой.
"""

from __future__ import annotations

import logging
import os

import httpx

from .ai_providers import PROVIDERS

log = logging.getLogger("transcribe")

# Модели расшифровки у провайдеров, которые говорят на диалекте OpenAI.
# Провайдера, которого здесь нет, мы не умеем слушать — и говорим об этом прямо,
# а не молчим в ответ на голосовое.
MODELS = {
    "groq": "whisper-large-v3-turbo",
    "openai": "whisper-1",
}

# Минута речи в opus — это около 250 КБ. Пять мегабайт с запасом покрывают
# длинное сообщение и отсекают присланный файл: платить за расшифровку
# получасовой записи салон не подписывался.
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 30.0


class TranscribeError(RuntimeError):
    """Не расшифровали. ``permanent`` — повтор не поможет."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.permanent = permanent


def settings_for(tenant) -> dict:
    """Откуда брать расшифровку для этого бизнеса."""
    ai = tenant.ai
    provider = str(os.getenv("TRANSCRIBE_PROVIDER") or ai.get("provider") or "").lower()
    return {
        "provider": provider,
        "key": os.getenv("TRANSCRIBE_API_KEY") or ai.get("apiKey") or "",
        "model": os.getenv("TRANSCRIBE_MODEL") or MODELS.get(provider, ""),
        "base": str(PROVIDERS.get(provider, {}).get("baseUrl") or ""),
    }


def enabled(tenant) -> bool:
    """Расшифровку можно выключить: это счёт салона у провайдера, а не наш."""
    return str(tenant.ai.get("voiceTranscription") or "auto").lower() != "off"


def available(tenant) -> bool:
    cfg = settings_for(tenant)
    return bool(enabled(tenant) and cfg["key"] and cfg["model"] and cfg["base"])


def transcribe(audio: bytes, *, tenant, mime: str = "audio/ogg") -> str:
    """Голос → текст. Бросает ``TranscribeError``, а не возвращает пустую строку.

    Пустой ответ выглядел бы как «клиент прислал ничего» и ушёл бы агенту,
    который вежливо переспросил бы, — а на самом деле мы не расслышали.
    """
    if not enabled(tenant):
        raise TranscribeError("Расшифровка голосовых выключена в настройках", permanent=True)
    cfg = settings_for(tenant)
    if not (cfg["key"] and cfg["base"]):
        raise TranscribeError("AI-провайдер не настроен — голосовые не расшифровать",
                              permanent=True)
    if not cfg["model"]:
        raise TranscribeError(f"Провайдер {cfg['provider'] or '—'} не умеет расшифровывать голос",
                              permanent=True)
    if not audio:
        raise TranscribeError("Пустая запись", permanent=True)
    if len(audio) > MAX_BYTES:
        raise TranscribeError("Голосовое слишком длинное", permanent=True)

    try:
        response = httpx.post(
            f"{cfg['base']}/audio/transcriptions",
            headers={"Authorization": f"Bearer {cfg['key']}"},
            data={"model": cfg["model"]},
            files={"file": ("voice.ogg", audio, mime or "audio/ogg")},
            timeout=TIMEOUT,
        )
        # 4xx — наша вина (ключ, модель, формат), повтор её не исправит;
        # 5xx и таймаут — чужая, и по ней имеет смысл попросить повторить.
        if response.status_code >= 400:
            detail = response.text[:200]
            log.error("Расшифровка не удалась: %s %s", response.status_code, detail)
            raise TranscribeError(f"Провайдер ответил {response.status_code}",
                                  permanent=response.status_code < 500)
        text = str((response.json() or {}).get("text") or "").strip()
    except TranscribeError:
        raise
    except httpx.HTTPError as exc:
        raise TranscribeError(f"Провайдер расшифровки недоступен: {exc}") from exc
    except ValueError as exc:  # ответ не JSON
        raise TranscribeError("Провайдер вернул не то, что мы умеем читать",
                              permanent=True) from exc

    if not text:
        raise TranscribeError("В записи не разобрать слов", permanent=True)
    return text
