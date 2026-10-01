"""AI-диалог: модель ведёт разговор, инструменты выполняет backend.

Модель видит только четыре функции и результат их выполнения. Ни календарь,
ни база, ни секреты ей недоступны.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from .policies import mask_pii
from .timeutil import norm_lang
from .tenants import Tenant
from .tools import BookingTools, ToolContext, ToolError

log = logging.getLogger("agent")

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_free_slots",
        "description": "Реальные свободные окна. Вызывай перед любым предложением времени — выдумывать время нельзя.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string", "description": "Код услуги из каталога"},
                "master_id": {"type": "string", "description": "Код мастера; опусти, если клиенту всё равно"},
                "date_from": {"type": "string", "description": "С какой даты искать, YYYY-MM-DD"},
                # Строку разрешаем намеренно: открытые модели пишут «"days": "7"»,
                # а провайдер сверяет аргументы с этой же схемой и отклоняет весь
                # запрос. Приводить строку к числу нам ничего не стоит — терять
                # из-за неё разговор с клиентом стоит дорого.
                "days": {"type": ["integer", "string"], "description": "Сколько дней просмотреть, 1–7"},
                "time": {"type": "string", "description": (
                    "Время, которое назвал клиент, HH:MM. Вместе с date_from проверяет именно его: "
                    "ответ requested.free и token, а если занято — requested.nearest")},
            },
            "required": ["service_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "create_booking",
        "description": (
            "Создать запись. Вызывай ТОЛЬКО после того, как показал сводку и клиент явно подтвердил. "
            "confirmation_token бери из ответа get_free_slots для выбранного слота."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "master_id": {"type": "string"},
                "start": {"type": "string", "description": "Начало в ISO, как в ответе get_free_slots"},
                "customer_name": {"type": "string"},
                "phone": {"type": "string"},
                "confirmation_token": {"type": "string", "description": "token выбранного слота"},
                "comment": {"type": "string"},
            },
            "required": ["service_id", "master_id", "start", "customer_name", "phone", "confirmation_token"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "cancel_booking",
        "description": "Отменить запись по её id или по телефону клиента. Нужно явное подтверждение клиента.",
        "parameters": {
            "type": "object",
            "properties": {"booking_id": {"type": "string"}, "phone": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "reschedule_booking",
        "description": "Перенести существующую запись в показанный свободный слот после явного подтверждения клиента.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string"}, "master_id": {"type": "string"},
                "start": {"type": "string"}, "confirmation_token": {"type": "string"},
            },
            "required": ["booking_id", "master_id", "start", "confirmation_token"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "handoff_to_human",
        "description": (
            "Передать разговор администратору: жалоба, нестандартная просьба, ошибка календаря, "
            "вопрос о цене которого нет в каталоге, любая ситуация вне записи."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "summary": {"type": "string", "description": "Кратко, что хочет клиент"},
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]

BASE_RULES = """Ты администратор салона {salon}. Твоя задача — записать клиента.

Жёсткие правила:
- Никогда не называй свободное время по памяти. Сначала get_free_slots, предлагай 2–3 варианта из ответа.
- Клиент назвал конкретное время — даже если его нет среди окон — не отказывай и не говори «занято»
  наугад: вызови get_free_slots с date_from и time. requested.free = true — записывай на это время
  с requested.token. Занято — скажи об этом и предложи 2–3 варианта из requested.nearest.
- Перед созданием записи покажи сводку: услуга, мастер, дата, время, длительность, имя, телефон — и дождись явного «да».
- Говори «вы записаны» только после того, как create_booking вернул booking_id.
- Не выдумывай услуги, цены и мастеров: только то, что в каталоге.
- Не спрашивай и не записывай лишние данные — нужны имя и телефон.
{escalation_rules}
- Отвечай коротко, 1–3 предложения, без списков-простыней.
{chips_rule}
{sales_rules}

Каталог и рабочие часы:
{catalog}

Сегодня {today}, часовой пояс {tz}."""

# Бот работает сам: администратора не зовём и его звонок не обещаем.
AUTONOMOUS_RULES = """- Ты доводишь дело до конца сам. Не предлагай написать администратору, не обещай,
  что «с вами свяжутся», и не перекладывай вопрос на человека — даже если клиент просит.
- Если инструмент вернул ошибку — коротко скажи, что не вышло, и сразу предложи выход:
  другое время, другой день, другого мастера.
- Вопросы про цены, услуги, адрес и часы работы отвечай сам по каталогу. Чего в каталоге нет —
  честно скажи, что уточните при визите, и веди дальше к записи."""

MANAGED_RULES = """- Если инструмент вернул ошибку — честно скажи об этом и предложи другое время или администратора.
- Всё, что выходит за рамки записи (жалобы, особые условия, оплата) — handoff_to_human."""

# Кнопки под ответом: клиенту не обязательно печатать.
CHIPS_RULE = """- Последней строкой добавляй 2–4 варианта ответа в двойных квадратных скобках через |,
  например: [[Да, подтверждаю | Другое время]]. Пиши их от лица клиента и коротко — клиент увидит
  кнопки, самих скобок он не видит. Не добавляй строку, если ответить кнопкой нечем."""

CHIPS_RE = re.compile(r"\[\[([^\[\]]{1,240})\]\]\s*$")

BOOK_PHRASE = {
    "ru": "Запишите меня к {master} на {date} в {time}",
    "es": "Resérveme con {master} el {date} a las {time}",
    "en": "Book me with {master} on {date} at {time}",
}

LANGUAGE_HINT = {
    "ru": "Отвечай по-русски.",
    "es": "Responde en español.",
    "en": "Answer in English.",
    "auto": "Отвечай на языке последнего сообщения клиента.",
}


class AgentUnavailable(RuntimeError):
    """AI выключен или не настроен."""


# Подсказка после отклонённого вызова: модели хватает одного напоминания.
TOOL_CALL_REPAIR = (
    "Предыдущий вызов инструмента был отклонён из-за формата. Вызови инструмент заново: "
    "имя функции — только её имя, аргументы — строго по схеме, days числом без кавычек."
)

# Признаки того, что провайдер отверг именно вызов инструмента, а не запрос целиком.
_TOOL_CALL_ERRORS = ("tool_use_failed", "tool call validation failed", "did not match schema")


def _is_tool_call_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TOOL_CALL_ERRORS)


def _sales_rules(settings: Tenant) -> str:
    """Мягкая продажа: одно предложение, без повторов, отказ закрывает тему."""
    sales = settings.sales
    rules = []
    if sales.get("upsellEnabled", True):
        limit = int(sales.get("upsellMaxPerDialog", 1) or 1)
        moment = ("после того как запись подтверждена" if sales.get("upsellMoment") == "after_booking"
                  else "когда клиент выбрал услугу")
        pairs = [
            f"к «{s['title']}» — " + ", ".join(
                f"«{(settings.service(x) or {}).get('title', x)}»" for x in s.get("suggestWith", []))
            for s in settings.services if s.get("suggestWith")
        ]
        rules.append(
            f"- Можешь {moment} ОДИН раз (максимум {limit} за разговор) мягко упомянуть дополнение: "
            "одной короткой фразой, как предложение, а не как давление. "
            "Если клиент отказался или промолчал — тему больше не поднимай."
        )
        if pairs:
            rules.append("- Что с чем сочетается: " + "; ".join(pairs) + ".")
        if sales.get("upsellNote"):
            rules.append("- Пожелание салона по предложениям: " + sales["upsellNote"])
    else:
        rules.append("- Ничего не предлагай сверх того, о чём спросил клиент.")
    if sales.get("fillGaps", True):
        rules.append("- Если названное клиентом время занято, сразу предложи два ближайших свободных "
                     "варианта, а не проси выбрать заново.")
    return "\n".join(rules)


def build_system_prompt(settings: Tenant, tools: BookingTools, lang: str | None = None) -> str:
    """lang приходит из виджета (язык страницы или первого сообщения) и важнее настройки салона."""
    ai = settings.ai
    code = (lang or "").strip().lower()[:2] or ai.get("language", "ru")
    catalog = tools.catalog(code)
    prompt = BASE_RULES.format(
        salon=settings.salon.get("name", "салона"),
        catalog=json.dumps(catalog, ensure_ascii=False, indent=1),
        today=catalog["today"],
        tz=catalog["timezone"],
        escalation_rules=AUTONOMOUS_RULES if settings.autonomous else MANAGED_RULES,
        chips_rule=CHIPS_RULE,
        sales_rules=_sales_rules(settings),
    )
    hint = LANGUAGE_HINT.get(code) or LANGUAGE_HINT.get(ai.get("language", "ru"), LANGUAGE_HINT["ru"])
    prompt += "\n" + hint
    if ai.get("systemPrompt"):
        prompt += "\n\nДополнительно от салона:\n" + ai["systemPrompt"]
    return prompt


class Agent:
    """Оркестрация вызовов модели. Провайдер подменяем — в тестах это заглушка."""

    def __init__(self, settings: Tenant, tools: BookingTools, client_factory: Callable[[dict], Any] | None = None):
        self.settings = settings
        self.tools = tools
        self._client_factory = client_factory or _openai_client

    def available(self) -> bool:
        ai = self.settings.ai
        return bool(ai.get("enabled") and ai.get("apiKey") and ai.get("model"))

    def reply(self, user_text: str, ctx: ToolContext, lang: str | None = None) -> dict:
        """Один ход диалога. Возвращает {'text', 'actions', 'handoff', 'suggestions'}."""
        if not self.available():
            raise AgentUnavailable("AI-диалог выключен или не настроен")

        ai = self.settings.ai
        client = self._client_factory(ai)
        max_steps = int(ai.get("maxSteps", 8))
        # Автономный бот не видит инструмента «позвать человека» — значит и не позовёт.
        tool_schemas = ([t for t in TOOL_SCHEMAS if t["name"] != "handoff_to_human"]
                        if self.settings.autonomous else TOOL_SCHEMAS)

        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt(self.settings, self.tools, lang or ctx.lang)},
        ]
        for item in ctx.history[-20:]:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": user_text})

        actions: list[dict] = []
        handoff = False

        retried_tool_call = False
        for step in range(max_steps):
            try:
                response = client.complete(messages=messages, tools=tool_schemas,
                                           timeout=int(ai.get("timeoutSeconds", 30)))
            except Exception as exc:  # noqa: BLE001 — разбираем по тексту ниже
                # Открытые модели регулярно ломают вызов инструмента: пишут число
                # строкой или коверкают имя функции. Провайдер валидирует это у
                # себя и отвечает 400 — весь диалог падал целиком, хотя клиенту
                # достаточно было бы одной повторной попытки.
                if retried_tool_call or not _is_tool_call_error(exc):
                    raise
                retried_tool_call = True
                log.warning("Провайдер отклонил вызов инструмента, повторяю: %s", str(exc)[:200])
                messages.append({"role": "system", "content": TOOL_CALL_REPAIR})
                continue
            calls = response.get("tool_calls") or []
            if not calls:
                text, chips = split_chips(response.get("text") or "")
                text = _guard_false_confirmation(text, actions, ctx)
                # Свободные окна важнее «да/нет»: пока клиент не выбрал время,
                # кнопками должно быть само время — из ответа инструмента, а не
                # из фантазии модели.
                slots = slot_suggestions(actions, ctx.lang)
                booked = any(a["tool"] == "create_booking" and a["ok"] for a in actions)
                return {"text": text, "actions": actions, "handoff": handoff,
                        "suggestions": chips if booked else (slots or chips)}

            messages.append({"role": "assistant", "content": response.get("text") or "", "tool_calls": calls})
            for call in calls:
                name = call["name"]
                args = call.get("arguments") or {}
                result, ok = self._run_tool(name, args, ctx)
                if name == "handoff_to_human" and ok:
                    handoff = True
                actions.append({"tool": name, "ok": ok, "result": result})
                log.info("tool %s ok=%s %s", name, ok, mask_pii(json.dumps(result, ensure_ascii=False))[:400])
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

        # Шаги кончились — не оставляем клиента без ответа.
        reason = "Агент не уложился в лимит шагов"
        if self.settings.autonomous:
            fallback = self.tools.recover(reason, ctx=ctx)
            return {"text": fallback["message"], "actions": actions, "handoff": False,
                    "suggestions": slot_suggestions(actions, ctx.lang), "fallback": True}
        fallback = self.tools.handoff_to_human(reason=reason, ctx=ctx)
        return {"text": fallback["message"], "actions": actions, "handoff": True, "suggestions": []}

    def _run_tool(self, name: str, args: dict, ctx: ToolContext) -> tuple[dict, bool]:
        try:
            if name == "get_free_slots":
                allowed = {"service_id", "master_id", "date_from", "days", "time"}
                return self.tools.get_free_slots(**_clean(args, allowed), lang=ctx.lang), True
            if name == "create_booking":
                allowed = {"service_id", "master_id", "start", "customer_name", "phone",
                           "confirmation_token", "comment"}
                return self.tools.create_booking(**_clean(args, allowed), ctx=ctx), True
            if name == "cancel_booking":
                return self.tools.cancel_booking(**_clean(args, {"booking_id", "phone"}), ctx=ctx), True
            if name == "reschedule_booking":
                allowed = {"booking_id", "master_id", "start", "confirmation_token"}
                return self.tools.reschedule_booking(**_clean(args, allowed), ctx=ctx), True
            if name == "handoff_to_human":
                return self.tools.handoff_to_human(**_clean(args, {"reason", "summary"}), ctx=ctx), True
        except ToolError as exc:
            if exc.escalate:
                self.tools.handoff_to_human(reason=exc.message, ctx=ctx)
            return {"error": exc.message}, False
        except Exception as exc:  # noqa: BLE001 — модель не должна видеть трейс
            log.exception("Инструмент %s упал", name)
            return {"error": "Внутренняя ошибка сервиса, попробуйте позже"}, False
        return {"error": f"Неизвестный инструмент {name}"}, False


def _clean(args: dict, allowed: set[str]) -> dict:
    return {k: v for k, v in (args or {}).items() if k in allowed and v not in (None, "")}


# --- кнопки под ответом -------------------------------------------------------

def split_chips(text: str) -> tuple[str, list[dict]]:
    """Отрезает от ответа строку `[[вариант | вариант]]` и превращает её в кнопки.

    Клиенту скобки показывать нельзя: если модель ошиблась с форматом, текст
    остаётся как есть, а кнопок просто не будет.
    """
    match = CHIPS_RE.search(text.strip())
    if not match:
        return text.strip(), []
    chips: list[dict] = []
    for raw in match.group(1).split("|"):
        label = " ".join(raw.split())[:48]
        if label and all(label != c["label"] for c in chips):
            chips.append({"label": label, "text": label})
    return text[:match.start()].strip(), chips[:4]


# Фразы, которыми модель объявляет запись созданной. Ловим их на трёх языках
# виджета: цена ошибки — клиент, который придёт в салон, где его не ждут.
_CONFIRMED_RE = re.compile(
    r"вы\s+записан|записал[аи]?\s+вас|запись\s+(создан|подтвержд|оформл)"
    r"|te\s+(he\s+)?(reserv|anot)|reserva\s+(confirmad|creada)"
    r"|you(?:'re| are)\s+booked|booking\s+(is\s+)?(confirmed|created)",
    re.IGNORECASE,
)

_NOT_BOOKED_YET = {
    "ru": "Пока не записал: выберите время из списка, и я оформлю запись.",
    "es": "Todavía no está reservado: elija una hora de la lista y la registro.",
    "en": "Not booked yet — pick a time from the list and I'll register it.",
}


def _guard_false_confirmation(text: str, actions: list[dict], ctx: ToolContext) -> str:
    """Не выпускаем «вы записаны», если записи не было.

    Модель, у которой сорвался вызов инструмента, охотно рапортует об успехе —
    и клиент приходит в салон, где его никто не ждёт. Проверить нечем, кроме
    факта: вернул ли create_booking booking_id. Сервер это знает точно.
    """
    if not _CONFIRMED_RE.search(text or ""):
        return text
    if any(a["tool"] == "create_booking" and a["ok"] for a in actions):
        return text
    log.warning("Модель объявила запись без create_booking (%s): %s",
                ctx.conversation_id, (text or "")[:160])
    return _NOT_BOOKED_YET.get(norm_lang(ctx.lang), _NOT_BOOKED_YET["ru"])


def slot_suggestions(actions: list[dict], lang: str = "ru", limit: int = 6) -> list[dict]:
    """Свободные окна из последнего get_free_slots — кнопками, по кругу между мастерами."""
    result = next((a["result"] for a in reversed(actions)
                   if a["tool"] == "get_free_slots" and a["ok"]), None)
    if not result:
        return []
    phrase = BOOK_PHRASE.get(lang, BOOK_PHRASE["ru"])
    queues = []
    for master in result.get("availability", []):
        items = [
            {"label": f"{day['date_label']} · {slot['time']}", "kind": "slot",
             "text": phrase.format(master=master["master_name"], date=day["date_label"],
                                   time=slot["time"])}
            for day in master.get("days", [])[:2] for slot in day.get("slots", [])[:3]
        ]
        if items:
            queues.append(items)
    chips: list[dict] = []
    for row in range(max((len(q) for q in queues), default=0)):
        for queue in queues:
            if row < len(queue) and len(chips) < limit:
                chips.append(queue[row])
    return chips


# --- провайдеры ---------------------------------------------------------------

class _OpenAIClient:
    """Тонкая обёртка над Responses API: наружу — единый формат tool_calls."""

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model

    def complete(self, *, messages: list[dict], tools: list[dict], timeout: int) -> dict:
        payload = _to_responses_input(messages)
        response = self._client.responses.create(
            model=self.model, input=payload, tools=tools, timeout=timeout,
        )
        text_parts: list[str] = []
        calls: list[dict] = []
        for item in response.output:
            if item.type == "function_call":
                try:
                    arguments = json.loads(item.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                calls.append({"id": item.call_id, "name": item.name, "arguments": arguments})
            elif item.type == "message":
                for chunk in item.content:
                    if getattr(chunk, "text", None):
                        text_parts.append(chunk.text)
        return {"text": "\n".join(text_parts).strip(), "tool_calls": calls}


def _to_responses_input(messages: list[dict]) -> list[dict]:
    """История в формат Responses API."""
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            out.append({"type": "function_call_output", "call_id": msg.get("tool_call_id"),
                        "output": msg["content"]})
        elif role == "assistant" and msg.get("tool_calls"):
            if msg.get("content"):
                out.append({"role": "assistant", "content": msg["content"]})
            for call in msg["tool_calls"]:
                out.append({"type": "function_call", "call_id": call["id"], "name": call["name"],
                            "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False)})
        else:
            out.append({"role": role, "content": msg["content"]})
    return out


class _ChatClient:
    """Chat Completions — общий диалект бесплатных провайдеров.

    Google AI Studio и Groq принимают запросы в формате OpenAI, но только по
    ``/chat/completions``: Responses API есть лишь у самой OpenAI. Разница в
    двух местах — инструменты обёрнуты в ``function``, а аргументы вызова
    приходят строкой JSON, а не объектом.
    """

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def complete(self, *, messages: list[dict], tools: list[dict], timeout: int) -> dict:
        converted = [
            {"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["parameters"]}}
            for t in tools
        ]
        response = self._client.chat.completions.create(
            model=self.model, messages=_to_chat_messages(messages), tools=converted, timeout=timeout,
        )
        message = response.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            parsed = {"id": call.id, "name": call.function.name, "arguments": arguments}
            # Gemini 3 отдаёт вместе с вызовом «подпись рассуждения» и требует
            # вернуть её на следующем шаге — иначе отвечает 400 и разговор
            # обрывается на первом же обращении к инструменту. Провайдеров, где
            # её нет, это поле не касается: оно просто не появится.
            extra = getattr(call, "extra_content", None) or {}
            if isinstance(extra, dict) and extra.get("google"):
                parsed["extra_content"] = {"google": extra["google"]}
            calls.append(parsed)
        return {"text": (message.content or "").strip(), "tool_calls": calls}


def _to_chat_messages(messages: list[dict]) -> list[dict]:
    """История во внутреннем формате → формат Chat Completions."""
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            out.append({"role": "tool", "tool_call_id": msg.get("tool_call_id"),
                        "content": msg["content"]})
        elif role == "assistant" and msg.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": msg.get("content") or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"],
                                  "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False)},
                     # Подпись рассуждения возвращается провайдеру как получена:
                     # без неё Gemini 3 не принимает историю с вызовами.
                     **({"extra_content": c["extra_content"]} if c.get("extra_content") else {})}
                    for c in msg["tool_calls"]
                ],
            })
        else:
            out.append({"role": role, "content": msg["content"]})
    return out


class _AnthropicClient:
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, *, messages: list[dict], tools: list[dict], timeout: int) -> dict:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        converted = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]
        response = self._client.messages.create(
            model=self.model, max_tokens=1024, system=system, tools=converted,
            messages=[m for m in messages if m["role"] in ("user", "assistant")], timeout=timeout,
        )
        text_parts, calls = [], []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append({"id": block.id, "name": block.name, "arguments": block.input})
        return {"text": "\n".join(text_parts).strip(), "tool_calls": calls}


def _openai_client(ai: dict):
    """Клиент по провайдеру из настроек. Список провайдеров — один на сервис."""
    from .ai_providers import PROVIDERS

    provider = ai.get("provider") or "openai"
    cfg = PROVIDERS.get(provider) or PROVIDERS["openai"]
    if cfg["kind"] == "anthropic":
        return _AnthropicClient(ai["apiKey"], ai["model"])
    if cfg["kind"] == "chat":
        return _ChatClient(ai["apiKey"], ai["model"], cfg["baseUrl"])
    return _OpenAIClient(ai["apiKey"], ai["model"])
