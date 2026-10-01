"""Голосовые сообщения в WhatsApp.

В Латинской Америке клиент диктует, а не печатает. Раньше такое сообщение
отбрасывалось молча, и клиент оставался в уверенности, что записался, — здесь
проверяется, что молчания больше нет ни в одном исходе.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from backend.app.billing import period_key
from backend.app.routers import whatsapp
from backend.app.routers.whatsapp import _download as real_download
from backend.app.transcribe import TranscribeError, transcribe
from backend.tests.conftest import INTEGRATION, SALON, write_tenant

PHONE = "59891234567"


def _payload(kind: str = "audio", *, text: str = "", media_id: str = "media-1") -> dict:
    message = {"from": PHONE, "type": kind}
    if kind == "text":
        message["text"] = {"body": text}
    else:
        message[kind] = {"id": media_id, "mime_type": "audio/ogg; codecs=opus"}
    return {"entry": [{"changes": [{"value": {"messages": [message]}}]}]}


class _Response:
    """Ответ httpx ровно в том объёме, в каком его читает загрузка файла."""

    def __init__(self, data: dict | None = None, content: bytes = b"") -> None:
        self._data, self.content = data or {}, content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


@pytest.fixture
def wa(client, tenants_dir, monkeypatch):
    """Салон с WhatsApp-каналом и включённым ботом. Наружу не ходит ничего."""
    from backend.app import deps

    integration = copy.deepcopy(INTEGRATION)
    integration["channel"] = {"kind": "whatsapp", "whatsappPhoneId": "111",
                              "whatsappToken": "tok", "whatsappVerifyToken": "verify"}
    integration["ai"] = {**integration["ai"], "enabled": True, "provider": "groq",
                         "model": "llama-3.3-70b-versatile", "apiKey": "key"}
    write_tenant(tenants_dir, "demo-salon", copy.deepcopy(SALON), integration)
    rt = deps.runtime.reload("demo-salon")

    sent: list[tuple[str, str]] = []
    escalations: list[str] = []
    monkeypatch.setattr(whatsapp, "_send", lambda tenant, to, text: sent.append((to, text)))
    monkeypatch.setattr(whatsapp, "notify_admin", lambda tenant, text: escalations.append(text))
    monkeypatch.setattr(rt.agent, "reply",
                        lambda text, ctx, lang=None: {"text": f"эхо: {text}", "suggestions": []})
    monkeypatch.setattr(whatsapp, "_download", lambda tenant, media_id: (b"ogg-bytes", "audio/ogg"))
    return SimpleNamespace(client=client, rt=rt, sent=sent, escalations=escalations,
                           store=deps.runtime.store)


def test_voice_reaches_the_agent(wa, monkeypatch):
    heard = []
    monkeypatch.setattr(whatsapp, "transcribe",
                        lambda audio, **kw: heard.append(audio) or "hola, quiero un corte")

    assert wa.client.post("/webhook/whatsapp/demo-salon", json=_payload()).status_code == 200

    assert heard == [b"ogg-bytes"]
    assert wa.sent == [(PHONE, "эхо: hola, quiero un corte")]
    # Расшифровка стоит денег провайдера — её считают отдельно от сообщений.
    assert wa.store.usage(period_key())["voiceMessages"] == 1


def test_voice_is_marked_in_the_dialog(wa, monkeypatch):
    monkeypatch.setattr(whatsapp, "transcribe", lambda audio, **kw: "quiero un turno")
    wa.client.post("/webhook/whatsapp/demo-salon", json=_payload())

    conversation = wa.client.get("/api/admin/conversations").json()["conversations"][0]
    detail = wa.client.get(f"/api/admin/conversations/{conversation['id']}").json()
    said = [m["content"] for m in detail["messages"] if m["role"] == "user"]
    assert said == ["🎙 quiero un turno"]


def test_unreadable_voice_answers_and_escalates(wa, monkeypatch):
    monkeypatch.setattr(whatsapp, "transcribe",
                        lambda audio, **kw: (_ for _ in ()).throw(TranscribeError("тишина")))

    assert wa.client.post("/webhook/whatsapp/demo-salon", json=_payload()).status_code == 200

    # Клиенту — просьба написать текстом, владельцу — сигнал. Молчания нет.
    assert wa.sent == [(PHONE, whatsapp.CANT_HEAR["ru"])]
    assert wa.escalations and "голосовое" in wa.escalations[0]
    # Диалога не завелось: агент нерасслышанного сообщения не видел.
    assert wa.client.get("/api/admin/conversations").json()["conversations"] == []


def test_answer_uses_the_client_language(wa, monkeypatch):
    wa.client.post("/api/admin/clients", json={"name": "Jordan", "phone": f"+{PHONE}",
                                               "lang": "es"})
    monkeypatch.setattr(whatsapp, "transcribe",
                        lambda audio, **kw: (_ for _ in ()).throw(TranscribeError("тишина")))

    wa.client.post("/webhook/whatsapp/demo-salon", json=_payload())

    assert wa.sent == [(PHONE, whatsapp.CANT_HEAR["es"])]


def test_long_audio_is_not_transcribed(wa, monkeypatch):
    """Размер известен до скачивания — на нём и отсекаем, до расходов."""
    calls = []
    monkeypatch.setattr(whatsapp, "_download", real_download)
    monkeypatch.setattr(whatsapp.httpx, "get", lambda url, **kw: _Response(
        {"file_size": whatsapp.MAX_BYTES + 1, "url": "https://cdn/voice.ogg",
         "mime_type": "audio/ogg"}))
    monkeypatch.setattr(whatsapp, "transcribe", lambda audio, **kw: calls.append(1) or "текст")

    wa.client.post("/webhook/whatsapp/demo-salon", json=_payload())

    assert calls == []
    assert wa.sent == [(PHONE, whatsapp.CANT_HEAR["ru"])]


def test_text_messages_still_work(wa):
    wa.client.post("/webhook/whatsapp/demo-salon", json=_payload("text", text="привет"))

    assert wa.sent == [(PHONE, "эхо: привет")]
    assert "voiceMessages" not in wa.store.usage(period_key())


def test_unknown_message_type_is_skipped(wa):
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": PHONE, "type": "image", "image": {"id": "img-1"}}]}}]}]}

    assert wa.client.post("/webhook/whatsapp/demo-salon", json=payload).status_code == 200
    assert wa.sent == []


def test_provider_without_audio_says_so(tenant):
    """Google говорит на диалекте OpenAI, но расшифровки у него нет."""
    tenant.integration["ai"] = {**tenant.integration["ai"], "provider": "google", "apiKey": "key"}

    with pytest.raises(TranscribeError) as exc:
        transcribe(b"ogg", tenant=tenant)

    assert exc.value.permanent
    assert "не умеет расшифровывать" in exc.value.message


def test_transcription_can_be_switched_off(wa, monkeypatch):
    """Выключено владельцем: клиенту отвечаем, владельца не дёргаем."""
    calls = []
    wa.rt.tenant.integration["ai"] = {**wa.rt.tenant.integration["ai"], "voiceTranscription": "off"}
    monkeypatch.setattr(whatsapp, "transcribe", lambda audio, **kw: calls.append(1) or "текст")

    wa.client.post("/webhook/whatsapp/demo-salon", json=_payload())

    assert calls == []
    assert wa.sent == [(PHONE, whatsapp.CANT_HEAR["ru"])]
    assert wa.escalations == []


def test_client_language_reaches_the_agent(wa, tenants_dir, monkeypatch):
    """Испанцу отвечаем по-испански целиком, а не только словами модели.

    `ai.language` у салона стоит в «auto» — это правило для модели, а не язык.
    Раньше он превращался в русский, и в одном сообщении оказывались испанский
    текст модели и русские даты с названиями услуг из каталога.
    """
    from backend.app import deps

    integration = copy.deepcopy(INTEGRATION)
    integration["channel"] = {"kind": "whatsapp", "whatsappPhoneId": "111",
                              "whatsappToken": "tok", "whatsappVerifyToken": "verify"}
    integration["ai"] = {**integration["ai"], "enabled": True, "provider": "groq",
                         "model": "llama-3.3-70b-versatile", "apiKey": "key", "language": "auto"}
    integration["notifications"] = {**integration["notifications"], "language": "es"}
    write_tenant(tenants_dir, "demo-salon", copy.deepcopy(SALON), integration)
    rt = deps.runtime.reload("demo-salon")

    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(rt.agent, "reply", lambda text, ctx, lang=None:
                        seen.append((ctx.lang, lang)) or {"text": "ok", "suggestions": []})

    assert wa.client.post("/webhook/whatsapp/demo-salon",
                          json=_payload("text", text="hola, quiero un corte")).status_code == 200

    assert seen == [("es", "es")]


def test_confirmation_reply_is_in_the_client_language(wa, tenants_dir, monkeypatch):
    """«Визит подтверждён» — единственная фраза, которую бот говорит сам."""
    from datetime import datetime, timedelta, timezone

    from backend.app import deps

    integration = copy.deepcopy(INTEGRATION)
    integration["channel"] = {"kind": "whatsapp", "whatsappPhoneId": "111",
                              "whatsappToken": "tok", "whatsappVerifyToken": "verify"}
    integration["ai"] = {**integration["ai"], "enabled": True, "provider": "groq",
                         "model": "llama-3.3-70b-versatile", "apiKey": "key", "language": "auto"}
    integration["notifications"] = {**integration["notifications"], "language": "es"}
    write_tenant(tenants_dir, "demo-salon", copy.deepcopy(SALON), integration)
    deps.runtime.reload("demo-salon")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    wa.store.create_booking(
        tenant_id="demo-salon", master_id="alex", service_id="haircut",
        start_at=start, end_at=start + timedelta(minutes=60),
        client_name="Ana", phone=PHONE, status="confirmed", requires_confirmation=True)

    assert wa.client.post("/webhook/whatsapp/demo-salon",
                          json=_payload("text", text="confirmo")).status_code == 200

    assert wa.sent == [(PHONE, "Su cita está confirmada. ¡Gracias!")]
