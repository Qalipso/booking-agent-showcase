"""Тексты уведомлений.

Имена шаблонов совпадают с именами WhatsApp-шаблонов, которые нужно заранее
утвердить в Meta: вне 24-часового окна свободный текст не доставляется.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from ..timeutil import human_date, norm_lang
from ..policies import to_international

TEMPLATE_NAMES = (
    "owner_new_booking",
    "master_new_booking",
    "master_booking_cancelled",
    "master_booking_rescheduled",
    "owner_booking_rescheduled",
    "booking_confirmation",
    "booking_rescheduled",
    "booking_cancelled",
    "booking_reminder_day_before",
    "booking_reminder_today",
    "owner_delivery_failed",
    # Тексты этих двух живут в LINK_MESSAGES: у них ссылка внутри, а не набор
    # {{плейсхолдеров}}. Порядок переменных им всё равно нужен — оба уходят
    # утверждённым шаблоном WhatsApp.
    "review_request",
    "waitlist_offer",
)

DEFAULT_TEMPLATES = {
    "owner_new_booking":
        "Новая запись: {{name}}, {{service}}, {{date}} в {{time}}. Мастер: {{master}}. Телефон: {{phone}}.",
    "booking_confirmation":
        "Здравствуйте, {{name}}! Ваша запись на {{service}} подтверждена: {{date}} в {{time}}. "
        "Ждём вас: {{address}}. До скорой встречи!",
    # Приветствие и «ждём вас» не для красоты: Meta не пропускает шаблон, у
    # которого переменная стоит в самом начале или в самом конце, а прежний
    # текст начинался словом «Запись» и заканчивался адресом.
    "booking_rescheduled":
        "Здравствуйте, {{name}}! Ваша запись на {{service}} перенесена: {{date}} в {{time}}. "
        "Ждём вас: {{address}}. До скорой встречи!",
    # Отмену делает салон — клиент о ней не знает и придёт к закрытой двери.
    # Адреса в тексте нет намеренно: звать по адресу того, кого отменили,
    # незачем, а переменная в конце шаблона Meta не проходит модерацию.
    "booking_cancelled":
        "Здравствуйте, {{name}}! Ваша запись на {{service}} {{date}} в {{time}} отменена. "
        "Напишите нам, чтобы выбрать другое время.",
    # Переменные идут в том же порядке, что и в TEMPLATE_VARIABLES, — иначе
    # Meta отклоняет шаблон: нумерация {{1}}, {{2}}, {{3}} обязана совпадать с
    # порядком в тексте. Отсюда «запись на {{service}} в {{time}}», а не
    # привычное «в {{time}} запись на {{service}}».
    "booking_reminder_day_before":
        "Здравствуйте, {{name}}! Напоминаем: завтра у вас запись на {{service}} — {{date}} в {{time}}. "
        "Ждём вас: {{address}}. До скорой встречи!",
    "booking_reminder_today":
        "Здравствуйте, {{name}}! Напоминаем: сегодня у вас запись на {{service}} в {{time}}. "
        "Ждём вас: {{address}}. До скорой встречи!",
    "owner_delivery_failed":
        "Не доставлено напоминание клиенту {{name}} ({{phone}}) о записи {{date}} в {{time}}. Свяжитесь вручную.",
    # Мастеру — только его записи. Имя мастера в текст не ставим: он и так знает,
    # кто он, а вот телефон клиента нужен, чтобы перезвонить и не гадать.
    "master_new_booking":
        "Новая запись: {{date}} в {{time}} — {{service}}. Клиент: {{name}}, {{phone}}.",
    "master_booking_cancelled":
        "Отмена: {{date}} в {{time}} — {{service}}. Клиент: {{name}}. Окно освободилось.",
    # Перенос своим — такое же рабочее событие, как новая запись: без него
    # мастер приходит к прежнему времени, а клиент — к новому.
    "master_booking_rescheduled":
        "Перенос: теперь {{date}} в {{time}} — {{service}}. Клиент: {{name}}, {{phone}}.",
    "owner_booking_rescheduled":
        "Запись перенесена: {{name}}, {{service}} — теперь {{date}} в {{time}}. "
        "Мастер: {{master}}. Телефон: {{phone}}.",
}

# Тексты на языке клиента. Салону в Монтевидео русский текст по умолчанию не
# годится, а заставлять владельца переводить четыре шаблона руками — верный
# способ получить их незаполненными. Сообщения владельцу остаются на языке
# панели: их читает он сам, а не клиент.
LOCALIZED_TEMPLATES = {
    "es": {
        "booking_confirmation":
            "¡Hola, {{name}}! Su cita para {{service}} está confirmada: {{date}} a las {{time}}. "
            "Lo esperamos en {{address}}. ¡Hasta pronto!",
        "booking_rescheduled":
            "¡Hola, {{name}}! Su cita para {{service}} fue reprogramada: {{date}} a las {{time}}. "
            "Lo esperamos en {{address}}. ¡Hasta pronto!",
        "booking_cancelled":
            "¡Hola, {{name}}! Su cita de {{service}} del {{date}} a las {{time}} fue cancelada. "
            "Escríbanos para elegir otro horario.",
        # Приветствие с именем есть и здесь: текст должен совпадать с
        # утверждённым WhatsApp-шаблоном, иначе проверка на `console` показывает
        # владельцу не то сообщение, которое получит клиент.
        # «¡Hasta pronto!» в конце — не только прощание: Meta не пропускает
        # шаблон, у которого переменная стоит в самом конце («Variables can't be
        # at the start or end of the template»), а оба напоминания заканчивались
        # адресом и были отклонены. Перенос и отмену клиент открывает кнопкой
        # под сообщением, поэтому «responda a este mensaje» больше не нужно.
        "booking_reminder_day_before":
            "¡Hola, {{name}}! Le recordamos su cita de {{service}} mañana, {{date}}, a las {{time}}. "
            "Lo esperamos en {{address}}. ¡Hasta pronto!",
        "booking_reminder_today":
            "¡Hola, {{name}}! Le recordamos su cita de {{service}} hoy a las {{time}}. "
            "Lo esperamos en {{address}}. ¡Hasta pronto!",
    },
    "en": {
        "booking_confirmation":
            "Hello, {{name}}! Your {{service}} appointment is confirmed: {{date}} at {{time}}. "
            "See you at {{address}}. Looking forward to your visit!",
        "booking_rescheduled":
            "Hello, {{name}}! Your {{service}} appointment was rescheduled: {{date}} at {{time}}. "
            "See you at {{address}}. Looking forward to your visit!",
        "booking_cancelled":
            "Hello, {{name}}! Your {{service}} appointment on {{date}} at {{time}} was cancelled. "
            "Message us to pick another time.",
        "booking_reminder_day_before":
            "Hello, {{name}}! A reminder: your {{service}} appointment is tomorrow, {{date}}, "
            "at {{time}}. See you at {{address}}. Looking forward to your visit!",
        "booking_reminder_today":
            "Hello, {{name}}! A reminder: your {{service}} appointment is today at {{time}}. "
            "See you at {{address}}. Looking forward to your visit!",
    },
}

# Тексты со ссылкой: просьба об оценке и предложение освободившегося места.
# Уходят они утверждённым шаблоном — расчёт на 24-часовое окно не оправдался:
# клиент, записавшийся через виджет, салону не писал никогда, и Meta отбивала
# оба сообщения кодом 63016. Эти тексты остаются для тех каналов, где шаблона
# нет вовсе (`console`, SMS, Telegram) и для окна, когда клиент только что
# написал сам.
# Язык берётся у клиента, а не у салона: испанке из Монтевидео русская просьба
# оценить визит читается как чужая рассылка, и по ссылке она не пойдёт.
LINK_MESSAGES = {
    "review_request": {
        "ru": "Здравствуйте, {name}! Спасибо, что были у нас в {salon}. "
              "Как прошла процедура «{service}»? Оцените визит за минуту: {link}",
        "es": "¡Hola, {name}! Gracias por su visita a {salon}. ¿Cómo estuvo {service}? "
              "Puntúe su visita en un minuto: {link}",
        "en": "Hello, {name}! Thank you for visiting {salon}. How was your {service}? "
              "Rate your visit in a minute: {link}",
    },
    # Хвост подтверждения и напоминаний: ссылка на страницу «мои записи».
    # Отдельной строкой, а не внутри текста, — тело сообщения обязано совпадать
    # с утверждённым в Meta шаблоном, и вписать в него ссылку без повторной
    # модерации нельзя.
    "manage_hint": {
        "ru": "Перенести или отменить: {link}",
        "es": "Cambiar o cancelar: {link}",
        "en": "Reschedule or cancel: {link}",
    },
    # Пятнадцать минут — не фигура речи: `offer_expires_at` истекает ровно через
    # столько, и после этого ссылка отвечает «место уже занято».
    "waitlist_offer": {
        "ru": "Здравствуйте, {name}! Освободилось место на «{service}»: {date} в {time}. "
              "Оно ваше, если подтвердите в ближайшие 15 минут: {link}",
        "es": "¡Hola, {name}! Se liberó un lugar para {service}: {date} a las {time}. "
              "Es suyo si lo confirma en los próximos 15 minutos: {link}",
        "en": "Hello, {name}! A spot opened up for {service}: {date} at {time}. "
              "It is yours if you confirm within the next 15 minutes: {link}",
    },
}


def link_message(kind: str, lang: str, **values: str) -> str:
    """Текст со ссылкой на языке клиента."""
    texts = LINK_MESSAGES[kind]
    return texts.get(norm_lang(lang), texts["ru"]).format(**values)


_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# Порядок переменных для WhatsApp-шаблонов (Twilio Content API нумерует их с 1).
# Свой набор на каждый тип, а не общий словарь: Meta требует сплошной нумерации
# {{1}}, {{2}}, {{3}} без пропусков, поэтому шаблон подтверждения не может
# использовать «имя, услугу, дату», пропустив телефон и мастера. Пока сюда
# уезжали все восемь переменных подряд, утверждённый шаблон вида
# «Hola {{1}}, tu cita para {{2}}» подставлял в услугу телефон клиента.
# Порядок в этих кортежах — контракт с утверждённым шаблоном: менять его можно
# только вместе с повторной модерацией шаблона в Meta.
TEMPLATE_VARIABLES: dict[str, tuple[str, ...]] = {
    "booking_confirmation": ("name", "service", "date", "time", "address"),
    "booking_rescheduled": ("name", "service", "date", "time", "address"),
    "booking_cancelled": ("name", "service", "date", "time"),
    "booking_reminder_day_before": ("name", "service", "date", "time", "address"),
    "booking_reminder_today": ("name", "service", "time", "address"),
    "owner_new_booking": ("name", "service", "date", "time", "master", "phone"),
    "owner_delivery_failed": ("name", "phone", "date", "time"),
    # Последняя переменная этих двух — хвост ссылки для кнопки под сообщением
    # (`https://…/review/{{4}}`). Meta разрешает подставлять в адрес кнопки
    # только его окончание, поэтому идентификатор, подпись и язык уезжают одной
    # строкой, а не тремя параметрами.
    "review_request": ("name", "salon", "service", "link"),
    "waitlist_offer": ("name", "service", "date", "time", "link"),
    # Мастеру и владельцу уходит Telegram, а не утверждённый шаблон WhatsApp:
    # эти наборы нужны только для единообразия, в Content API они не поедут.
    "master_new_booking": ("date", "time", "service", "name", "phone"),
    "master_booking_cancelled": ("date", "time", "service", "name"),
    "master_booking_rescheduled": ("date", "time", "service", "name", "phone"),
    "owner_booking_rescheduled": ("name", "service", "date", "time", "master", "phone"),
}


def local_time(start_at: datetime, tz_name: str) -> str:
    """Час и минуты записи в часовом поясе бизнеса."""
    return start_at.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")


def local_date_key(start_at: datetime, tz_name: str) -> str:
    """Дата записи как 'YYYY-MM-DD' в часовом поясе бизнеса."""
    return start_at.astimezone(ZoneInfo(tz_name)).date().isoformat()


def short_address(salon: dict) -> str:
    """Адрес для сообщения: улица с домом, без индекса и департамента.

    Полный адрес нужен картам и странице записи, а в сообщении «Lo esperamos en
    100 Example Street, Example City» —
    половина строки на то, что клиент и так знает. Режем по первой запятой:
    в адресе она отделяет дом от города. Не подошло — владелец пишет свой
    короткий адрес в настройках салона.
    """
    explicit = str(salon.get("addressShort") or "").strip()
    if explicit:
        return explicit
    return str(salon.get("address") or "").split(",")[0].strip()


def variables_for(booking, tenant, lang: str = "ru") -> dict[str, str]:
    """Переменные шаблона для конкретной записи, на языке сообщения.

    Название услуги и дата берутся на языке клиента: испанский шаблон с
    подставленным «Тотал блонд» и датой «вт, 18 авг» выглядит поломкой, а не
    заботой. Имя мастера не переводится — это имя собственное.
    """
    tz_name = tenant.timezone
    date_key = local_date_key(booking.start_at, tz_name)
    service = tenant.service(booking.service_id) or {}
    master = tenant.master(booking.master_id) or {}
    return {
        "name": booking.client_name,
        # В базе телефон лежит так, как его ввёл клиент, — по-местному и без
        # кода страны. В сообщении он нужен в E.164: иначе мастер не может
        # позвонить нажатием, а «099000101» вообще не опознаётся как номер.
        "phone": to_international(booking.phone, tenant.salon.get("phoneCountry")),
        "service": tenant.localized(service, "title", lang) or booking.service_id,
        "master": master.get("name", booking.master_id),
        "date": human_date(date_key, lang),
        "time": local_time(booking.start_at, tz_name),
        "address": short_address(tenant.salon),
        "salon": tenant.salon.get("name") or "",
    }


# Шаблоны, где есть личная ссылка клиента, — у них на одну переменную больше.
# Набор выбирается флагом тенанта, а не жёстко: пока в Meta висит старая версия
# шаблона без ссылки, лишняя переменная ломает отправку (Twilio 63028).
#
# Ссылка живёт в кнопке «Перенести или отменить» под сообщением, а не в тексте:
# длинный адрес с токеном посреди напоминания владелец читать клиенту не хотел.
# Цена этого — внутри 24-часового окна Twilio отправляет содержимое обычным
# сообщением, и кнопки у него нет: клиент, который недавно писал салону сам,
# получит напоминание без ссылки. Поэтому значение переменной — только хвост
# адреса, а начало зашито в самом шаблоне Meta.
#
# Переноса здесь нет намеренно: его шаблон в Meta — обычный текст, поданный
# раньше этой правки, и лишняя переменная сломала бы отправку. Ссылку на свои
# записи клиент получит следующим напоминанием.
MANAGE_BUTTON_TEMPLATES = ("booking_confirmation",
                           "booking_reminder_day_before", "booking_reminder_today")


def variables_order(kind: str, manage_button: bool = False) -> tuple[str, ...]:
    """Порядок переменных шаблона; с кнопкой — плюс хвост ссылки последним."""
    order = TEMPLATE_VARIABLES.get(kind, ())
    if manage_button and kind in MANAGE_BUTTON_TEMPLATES:
        order += ("link",)
    return order


def ordered_variables(kind: str, values: dict[str, str],
                      manage_button: bool = False) -> dict[str, str]:
    """Значения в порядке нумерации шаблона.

    Неизвестный тип отдаёт пустой набор: лучше уйти обычным `Body`, чем
    подставить в чужой шаблон произвольные значения.
    """
    return {key: values.get(key, "") for key in variables_order(kind, manage_button)}


def content_variables(kind: str, booking, tenant, lang: str = "ru",
                      manage_button: bool = False) -> dict[str, str]:
    """Переменные утверждённого WhatsApp-шаблона для конкретной записи."""
    return ordered_variables(kind, variables_for(booking, tenant, lang), manage_button)


_LINK_PHRASE = re.compile(r"[^.!?¡¿]*\{\{\s*link\s*\}\}\s*")


def render(template: str, variables: dict[str, str]) -> str:
    """Подстановка {{ключ}}. Неизвестные плейсхолдеры удаляются, чтобы не уехать в сообщение."""
    text = str(template)
    if not (variables.get("link") or "").strip():
        # Без ссылки «Перенести или отменить:» повисает обещанием без адреса.
        # Такое бывает у записи без карточки клиента и на стенде без публичного
        # адреса: сообщение должно остаться осмысленным и там.
        text = _LINK_PHRASE.sub("", text)
    text = _PLACEHOLDER.sub(lambda m: str(variables.get(m.group(1), "")), text)
    return re.sub(r"\s+", " ", text).strip()


def has_link(kind: str, lang: str = "ru", overrides: dict | None = None) -> bool:
    """Стоит ли личная ссылка в самом тексте — тогда отдельной строкой не нужна."""
    override = ((overrides or {}).get(kind) or "").strip()
    text = (override or LOCALIZED_TEMPLATES.get(norm_lang(lang), {}).get(kind)
            or DEFAULT_TEMPLATES.get(kind) or "")
    return "{{link}}" in text.replace(" ", "")


def link_in_body(kind: str, lang: str = "ru") -> bool:
    """Ссылка стоит в тексте утверждённого шаблона, а не в кнопке под ним.

    От этого зависит значение переменной: в текст нужен полный адрес, в кнопку —
    только его хвост. Раньше это решал отдельный флаг тенанта, и он разъехался с
    шаблоном: панель не знает поля `manageLinkInText`, любое сохранение формы
    стирало его из `integration.json`, и клиенты получали «Перенести или
    отменить: e0333b26…?tenant=demo-salon» — хвост без домена.

    Теперь источник один — текст здесь, из которого шаблон и создавался
    (`ops/whatsapp_templates.py`). Правки владельца в панели не учитываем: в
    отправку с Content SID его текст не попадает вовсе.
    """
    text = (LOCALIZED_TEMPLATES.get(norm_lang(lang), {}).get(kind)
            or DEFAULT_TEMPLATES.get(kind) or "")
    return "{{link}}" in text.replace(" ", "")


def message_for(kind: str, booking, tenant, overrides: dict | None = None,
                lang: str = "ru", link: str = "") -> str:
    """Текст сообщения по типу уведомления.

    Приоритет: текст из формы → готовый перевод → русский текст. Заполненный
    владельцем шаблон не подменяется переводом: он писал его сам и для своего
    салона.
    """
    override = ((overrides or {}).get(kind) or "").strip()
    localized = LOCALIZED_TEMPLATES.get(norm_lang(lang), {}).get(kind)
    template = override or localized or DEFAULT_TEMPLATES.get(kind) or ""
    return render(template, {**variables_for(booking, tenant, lang), "link": link})
