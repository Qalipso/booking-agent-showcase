"""Оркестрация агента на заглушке провайдера — без обращений к OpenAI."""

from __future__ import annotations

import pytest

from backend.app.agent import Agent
from backend.app.tools import ToolContext


class FakeClient:
    """Проигрывает заранее заданные ходы модели."""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.seen: list[list[dict]] = []
        self.tools_seen: list[list[dict]] = []

    def complete(self, *, messages, tools, timeout):
        self.seen.append(list(messages))
        self.tools_seen.append(list(tools))
        return self.script.pop(0) if self.script else {"text": "…", "tool_calls": []}


def make_agent(settings, tools, script) -> tuple[Agent, FakeClient]:
    settings.integration["ai"] = {"enabled": True, "model": "test", "apiKey": "test", "maxSteps": 6}
    client = FakeClient(script)
    return Agent(settings, tools, client_factory=lambda ai: client), client


def test_agent_books_through_tools(settings, tools, tomorrow):
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow, days=1)
    slot = slots["availability"][0]["days"][0]["slots"][0]

    agent, client = make_agent(settings, tools, [
        {"text": "", "tool_calls": [
            {"id": "1", "name": "get_free_slots", "arguments": {"service_id": "haircut", "master_id": "alex"}}
        ]},
        {"text": "", "tool_calls": [
            {"id": "2", "name": "create_booking", "arguments": {
                "service_id": "haircut", "master_id": "alex", "start": slot["start"],
                "customer_name": "Jordan", "phone": "+598 91234567",
                "confirmation_token": slot["token"],
            }}
        ]},
        {"text": "Вы записаны!", "tool_calls": []},
    ])

    ctx = ToolContext(conversation_id="c1", history=[{"role": "user", "content": "да, подтверждаю"}])
    result = agent.reply("да, подтверждаю", ctx)

    assert result["text"] == "Вы записаны!"
    booking = [a for a in result["actions"] if a["tool"] == "create_booking"][0]
    assert booking["ok"] is True
    assert booking["result"]["booking_id"]


def test_tool_error_goes_back_to_model_not_to_crash(settings, tools):
    """Отказ инструмента — обычный результат для модели, а не 500 клиенту."""
    agent, _ = make_agent(settings, tools, [
        {"text": "", "tool_calls": [
            {"id": "1", "name": "create_booking", "arguments": {
                "service_id": "haircut", "master_id": "alex", "start": "2026-08-07T13:00:00-03:00",
                "customer_name": "X", "phone": "+598 91234567", "confirmation_token": "fake",
            }}
        ]},
        {"text": "Извините, это время недоступно.", "tool_calls": []},
    ])
    ctx = ToolContext(conversation_id="c1", history=[{"role": "user", "content": "да"}])
    result = agent.reply("да", ctx)

    failed = [a for a in result["actions"] if not a["ok"]]
    assert failed and "error" in failed[0]["result"]
    assert result["text"].startswith("Извините")


def test_step_limit_stays_with_the_bot(settings, tools):
    """Модель зациклилась — бот сам предлагает пройти запись по шагам."""
    loop = {"text": "", "tool_calls": [
        {"id": "1", "name": "get_free_slots", "arguments": {"service_id": "haircut"}}
    ]}
    agent, _ = make_agent(settings, tools, [loop] * 6)
    ctx = ToolContext(conversation_id="c1", history=[])
    result = agent.reply("привет", ctx)

    assert result["handoff"] is False
    assert "администратор" not in result["text"].lower()
    assert result["suggestions"]          # клиенту есть что нажать


def test_step_limit_hands_off_when_manual_mode(settings, tools):
    """Салон выключил автономность — тогда прежнее поведение с администратором."""
    settings.integration["handoff"]["autonomous"] = False
    loop = {"text": "", "tool_calls": [
        {"id": "1", "name": "get_free_slots", "arguments": {"service_id": "haircut"}}
    ]}
    agent, _ = make_agent(settings, tools, [loop] * 6)
    result = agent.reply("привет", ToolContext(conversation_id="c1", history=[]))

    assert result["handoff"] is True
    assert "администратор" in result["text"].lower()


def test_autonomous_agent_has_no_handoff_tool(settings, tools):
    """Инструмента «позвать человека» модель просто не видит."""
    agent, client = make_agent(settings, tools, [{"text": "ок", "tool_calls": []}])
    agent.reply("привет", ToolContext(conversation_id="c1", history=[]))
    assert "handoff_to_human" not in {t["name"] for t in client.tools_seen[0]}


def test_reply_turns_model_options_into_buttons(settings, tools):
    """Строка со скобками уходит в кнопки, а клиенту её текст не показывается."""
    agent, _ = make_agent(settings, tools, [
        {"text": "Записать вас на 15:00?\n[[Да, подтверждаю | Другое время]]", "tool_calls": []},
    ])
    result = agent.reply("да", ToolContext(conversation_id="c1", history=[]))

    assert "[[" not in result["text"]
    assert [c["label"] for c in result["suggestions"]] == ["Да, подтверждаю", "Другое время"]


def test_free_slots_become_buttons(settings, tools, tomorrow):
    """После поиска окон клиент может просто нажать на время."""
    agent, _ = make_agent(settings, tools, [
        {"text": "", "tool_calls": [
            {"id": "1", "name": "get_free_slots",
             "arguments": {"service_id": "haircut", "master_id": "alex", "date_from": tomorrow}}
        ]},
        {"text": "Вот свободное время.", "tool_calls": []},
    ])
    result = agent.reply("когда можно?", ToolContext(conversation_id="c1", history=[]))

    assert result["suggestions"]
    first = result["suggestions"][0]
    assert first["kind"] == "slot" and "Alex" in first["text"]


def test_system_prompt_contains_catalog(settings, tools):
    agent, client = make_agent(settings, tools, [{"text": "ок", "tool_calls": []}])
    agent.reply("привет", ToolContext(conversation_id="c1", history=[]))
    system = client.seen[0][0]["content"]
    assert "haircut" in system and "Alex" in system
    assert "get_free_slots" in system or "свободное время" in system


def test_provider_rejecting_a_tool_call_gets_one_more_try(settings, tools):
    """Открытые модели ломают вызов инструмента — диалог из-за этого не падает.

    Groq сверяет аргументы со схемой у себя и отвечает 400: llama пишет
    «"days": "7"» строкой или коверкает имя функции. Раньше это роняло весь
    разговор, и клиент получал «что-то не сработало» вместо записи.
    """
    attempts = []

    class FlakyClient:
        def complete(self, *, messages, tools, timeout):
            attempts.append(messages[-1]["role"])
            if len(attempts) == 1:
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': 'tool call validation failed: "
                    "parameters for tool get_free_slots did not match schema', "
                    "'code': 'tool_use_failed'}}"
                )
            return {"text": "Свободно завтра в 11:00", "tool_calls": []}

    settings.integration["ai"] = {"enabled": True, "model": "test", "apiKey": "test", "maxSteps": 6}
    agent = Agent(settings, tools, client_factory=lambda ai: FlakyClient())
    result = agent.reply("хочу стрижку", ToolContext(conversation_id="c1", history=[]))

    assert result["text"] == "Свободно завтра в 11:00"
    assert attempts == ["user", "system"], attempts  # вторая попытка с подсказкой


def test_provider_error_that_is_not_about_tools_is_not_retried(settings, tools):
    """Ретрай только для отклонённого вызова: перебирать упавший провайдер незачем."""
    calls = []

    class DeadClient:
        def complete(self, *, messages, tools, timeout):
            calls.append(1)
            raise RuntimeError("Error code: 401 - invalid api key")

    settings.integration["ai"] = {"enabled": True, "model": "test", "apiKey": "test", "maxSteps": 6}
    agent = Agent(settings, tools, client_factory=lambda ai: DeadClient())
    with pytest.raises(RuntimeError, match="401"):
        agent.reply("привет", ToolContext(conversation_id="c1", history=[]))
    assert len(calls) == 1


def test_model_cannot_announce_a_booking_that_was_not_made(settings, tools):
    """«Вы записаны» без create_booking до клиента не доходит.

    Модель, у которой сорвался вызов инструмента, охотно рапортует об успехе —
    и клиент приходит в салон, где его никто не ждёт. Проверяем фактом: вернул
    ли create_booking booking_id.
    """
    agent, _ = make_agent(settings, tools, [
        {"text": "Готово! Вы записаны на завтра в 11:00.", "tool_calls": []},
    ])
    result = agent.reply("запиши меня", ToolContext(conversation_id="c1", history=[]))

    assert "записаны" not in result["text"].lower(), result["text"]
    assert "выберите время" in result["text"].lower(), result["text"]


def test_real_booking_is_still_announced(settings, tools, tomorrow):
    """Настоящая запись подтверждается как обычно — защита не мешает работе."""
    slot = tools.get_free_slots(service_id="haircut", master_id="alex",
                                date_from=tomorrow, days=1)["availability"][0]["days"][0]["slots"][0]
    agent, _ = make_agent(settings, tools, [
        {"text": "", "tool_calls": [{"id": "1", "name": "create_booking", "arguments": {
            "service_id": "haircut", "master_id": "alex", "start": slot["start"],
            "customer_name": "Мария", "phone": "+598 99123456",
            "confirmation_token": slot["token"]}}]},
        {"text": "Вы записаны, ждём вас!", "tool_calls": []},
    ])
    ctx = ToolContext(conversation_id="c2", history=[{"role": "user", "content": "да, подтверждаю"}])
    result = agent.reply("да", ctx)

    assert "записаны" in result["text"].lower(), result["text"]


def test_free_slots_become_buttons_before_the_client_picks_a_time(settings, tools, tomorrow):
    """Кнопками должны быть свободные окна, а не «да/нет» от модели."""
    agent, _ = make_agent(settings, tools, [
        {"text": "", "tool_calls": [{"id": "1", "name": "get_free_slots", "arguments": {
            "service_id": "haircut", "master_id": "alex", "date_from": tomorrow, "days": 1}}]},
        {"text": "Есть окна завтра.\n[[Да, подтверждаю | Другое время]]", "tool_calls": []},
    ])
    result = agent.reply("хочу стрижку", ToolContext(conversation_id="c3", history=[]))

    labels = [s["label"] for s in result["suggestions"]]
    assert labels and all(":" in label for label in labels), labels
    assert "Да, подтверждаю" not in labels, labels


def test_thought_signature_returns_to_the_provider(settings, tools):
    """Подпись рассуждения Gemini возвращается вместе с историей вызовов.

    Gemini 3 отдаёт её рядом с вызовом инструмента и требует обратно на
    следующем шаге: без неё отвечает 400, и разговор обрывается на первом же
    обращении к инструменту.
    """
    from backend.app.agent import _to_chat_messages

    history = [
        {"role": "user", "content": "хочу стрижку"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "1", "name": "get_free_slots", "arguments": {"service_id": "haircut"},
             "extra_content": {"google": {"thought_signature": "ABC123"}}},
        ]},
    ]
    sent = _to_chat_messages(history)
    call = sent[-1]["tool_calls"][0]
    assert call["extra_content"] == {"google": {"thought_signature": "ABC123"}}, call


def test_calls_without_a_signature_stay_clean(settings, tools):
    """Провайдерам без подписи лишнего поля не отправляем."""
    from backend.app.agent import _to_chat_messages

    sent = _to_chat_messages([
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "1", "name": "get_free_slots", "arguments": {}}]},
    ])
    assert "extra_content" not in sent[-1]["tool_calls"][0]
