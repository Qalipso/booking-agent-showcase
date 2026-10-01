"""Четыре инструмента агента.

Модель не имеет доступа к Calendar API — она запрашивает конкретное действие,
а здесь проверяются рабочее время, график мастера, длительность услуги,
таймзона, занятость, лимиты и наличие явного подтверждения клиента.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .billing import LimitExceeded, check_and_count
from .events import event as log_event
from .calendar_service import CalendarError, CalendarService
from .db import SlotTaken, Store
from .policies import (
    RateLimiter, check_slot_token, client_confirmed, client_key, client_keys,
    idempotency_key, normalize_phone, phone_problem,
    slot_token, within_daily_limit,
)
from .tenants import Tenant
from .slots import available_days, free_slots, lead_minutes, nearby_slots, slot_at
from .billing import period_key as _period
from .timeutil import human_date, norm_lang, now, today_key, zoned

log = logging.getLogger("tools")

# Сколько окон дня показывать модели. Когда спрашивают конкретный день — весь
# день целиком: двенадцати не хватало, при шаге 30 минут они кончались на 16:30,
# и вечер салона переставал существовать для бота. Когда идёт обзор «где вообще
# есть места» — по нескольку окон на день: полная сетка по всем мастерам за три
# дня весит одиннадцать килобайт и на каждом шаге едет в контекст заново, упирая
# диалог в лимит бесплатного тарифа провайдера.
SLOTS_PER_DAY = 24
SLOTS_PER_DAY_PREVIEW = 8

# Что бот говорит клиенту, когда сам споткнулся. Про администратора — ни слова:
# автономный бот доводит запись до конца, пусть и по шагам.
RECOVER_MESSAGE = {
    "ru": "Что-то не сработало на моей стороне. Давайте выберем услугу и время по шагам — это минута.",
    "es": "Algo falló de mi lado. Elijamos el servicio y el horario paso a paso — es un minuto.",
    "en": "Something went wrong on my side. Let us pick the service and time step by step — one minute.",
}

# Передача администратору. Текст видит клиент, поэтому он тоже на его языке:
# «Передаю ваш вопрос администратору» в испанской переписке читается как чужое
# сообщение, попавшее не в тот чат.
HANDOFF_MESSAGE = {
    "ru": "Передаю ваш вопрос администратору — с вами свяжутся в ближайшее время.",
    "es": "Le paso su consulta al administrador — se comunicarán con usted en breve.",
    "en": "I am passing your question to the manager — they will contact you shortly.",
}

ADMIN_WORD = {"ru": "администратор", "es": "el administrador", "en": "the manager"}


def _human_lead(minutes: int) -> str:
    """«120» → «2 часа»: клиенту нельзя отвечать в минутах от полутора суток."""
    if minutes % 60 or minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    tail = hours % 10
    if hours % 100 in (11, 12, 13, 14) or tail == 0 or tail >= 5:
        return f"{hours} часов"
    return f"{hours} час" + ("" if tail == 1 else "а")


class ToolError(Exception):
    """Ожидаемый отказ: модель получает текст и объясняет его клиенту.

    ``conflict`` означает «время занято» — HTTP-слой отвечает на такое 409, а не
    400. Раньше он опознавал конфликт по слову «заняли» в тексте: стоило
    переписать сообщение — и панель получала «неверный запрос» вместо «занято».
    """

    def __init__(self, message: str, *, escalate: bool = False, conflict: bool = False,
                 code: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.escalate = escalate
        self.conflict = conflict
        # Код отказа для кнопочного сценария. Текст сообщения читает модель и
        # пересказывает его клиенту на его языке, а виджет показывает отказ как
        # есть — испанка видела русскую плашку под испанской формой. По коду он
        # берёт свой перевод, а текст остаётся запасным вариантом.
        self.code = code


@dataclass
class ToolContext:
    conversation_id: str
    history: list[dict]
    channel: str = "web"
    lang: str = "ru"   # язык клиента: на нём подписываются даты в ответах инструментов


class BookingTools:
    def __init__(self, tenant: Tenant, store: Store, calendar: CalendarService,
                 limiter: RateLimiter | None = None, notifications=None) -> None:
        self.settings = tenant   # исторический алиас
        self.tenant = tenant
        self.store = store
        self.calendar = calendar
        self.limiter = limiter or RateLimiter()
        self.notifications = notifications

    # --- справочники ------------------------------------------------------
    def catalog(self, lang: str = "ru") -> dict:
        """Справочник для модели. Названия — на языке клиента, иначе модель
        пересказывает испанцу русские названия услуг."""
        return {
            "services": [
                {"id": s["id"], "title": self.settings.localized(s, "title", lang),
                 "duration": s["duration"], "price": self.settings.localized(s, "price", lang)}
                for s in self.settings.services
            ],
            "masters": [
                {"id": m["id"], "name": m["name"],
                 "role": self.settings.localized(m, "role", lang), "services": m.get("services", [])}
                for m in self.settings.masters
            ],
            "workHours": self.settings.salon.get("workHours"),
            "timezone": self.settings.timezone,
            "today": today_key(self.settings.timezone),
        }

    # --- инструмент 1 -----------------------------------------------------
    def get_free_slots(self, *, service_id: str, master_id: str | None = None,
                       date_from: str | None = None, days: int = 3, time: str | None = None,
                       lang: str = "ru") -> dict:
        service = self.settings.service(service_id)
        if not service:
            # Названия в подсказке — на языке клиента: модель пересказывает её
            # клиенту почти дословно, и русский список услуг попадал в испанский
            # ответ целиком.
            raise ToolError(f"Нет услуги с кодом «{service_id}». Доступны: "
                            + ", ".join(f"{s['id']} ({self.settings.localized(s, 'title', lang)})"
                                        for s in self.settings.services))

        masters = [self.settings.master(master_id)] if master_id else list(self.settings.masters)
        if master_id and not masters[0]:
            raise ToolError(f"Нет мастера с кодом «{master_id}»")
        masters = [m for m in masters if m and service_id in (m.get("services") or [])]
        if not masters:
            raise ToolError("Услугу «" + self.settings.localized(service, "title", lang)
                            + "» не делает ни один из выбранных мастеров")

        days = max(1, min(int(days or 3), 7))
        tz_name = self.settings.timezone
        start_date = date_from or today_key(tz_name)
        # Клиент назвал точное время: проверяем именно его, а не сетку меню.
        wanted = (time or "").strip()
        if wanted:
            if len(wanted) == 4 and wanted[1] == ":":
                wanted = "0" + wanted
            days = 1

        result = []
        for master in masters:
            day_list = [d for d in available_days(self.settings, master, limit=14, lang=lang)
                        if d["date"] >= start_date]
            per_master = []
            for day in day_list[:days]:
                try:
                    slots = free_slots(self.settings, self.calendar, master, service, day["date"])
                except CalendarError as exc:
                    log.error("Календарь недоступен: %s", exc)
                    raise ToolError("Не могу прочитать расписание — календарь недоступен", escalate=True) from exc
                requested = None
                if wanted and day["date"] == start_date:
                    requested = self._requested_time(master, service, day["date"], wanted)
                if not slots and not requested:
                    continue
                shown = slots[:SLOTS_PER_DAY if days == 1 else SLOTS_PER_DAY_PREVIEW]
                day_payload = {
                    "date": day["date"],
                    "date_label": day["label"],
                    # Токен подписывает слот: время, которого не показывали, забронировать нельзя.
                    "slots": [
                        {
                            "time": s["time"],
                            "start": s["start"].isoformat(),
                            "token": slot_token(master["id"], service_id, s["start"].isoformat(), self.tenant.slug),
                        }
                        for s in shown
                    ],
                }
                # Обрезанный список модель принимала за полный: на «хочу в 17:00»
                # она отвечала, что такого времени нет, хотя салон работает до 20:00
                # — просто вечерние окна не помещались в выдачу.
                if len(slots) > len(shown):
                    day_payload["truncated"] = True
                    day_payload["last_time"] = slots[-1]["time"]
                if requested:
                    day_payload["requested"] = requested
                per_master.append(day_payload)
            if per_master:
                result.append({"master_id": master["id"], "master_name": master["name"], "days": per_master})

        if not result:
            raise ToolError("Свободных окон в ближайшие дни нет — предложите клиенту другую дату "
                            "или передайте разговор администратору")
        return {"service": {"id": service["id"],
                            "title": self.settings.localized(service, "title", lang),
                            "duration": service["duration"]},
                "availability": result}

    def _requested_time(self, master: dict, service: dict, date_str: str, wanted: str) -> dict:
        """Ответ на «хочу в 16:00»: свободно ли, а если нет — два-три соседних окна.

        Время вне сетки меню — не отказ: мастер может быть свободен между
        окнами, которые показывают кнопками.
        """
        try:
            slot = slot_at(self.settings, self.calendar, master, service, date_str, wanted)
            nearby = [] if slot else nearby_slots(self.settings, self.calendar, master, service,
                                                  date_str, wanted)
        except CalendarError as exc:
            log.error("Календарь недоступен: %s", exc)
            raise ToolError("Не могу прочитать расписание — календарь недоступен", escalate=True) from exc
        sign = lambda s: {"time": s["time"], "start": s["start"].isoformat(),  # noqa: E731
                          "token": slot_token(master["id"], service["id"], s["start"].isoformat(),
                                              self.tenant.slug)}
        if slot:
            return {"time": wanted, "free": True, **sign(slot)}
        return {"time": wanted, "free": False, "nearest": [sign(s) for s in nearby]}

    # --- инструмент 2 -----------------------------------------------------
    def create_booking(self, *, service_id: str, master_id: str, start: str, customer_name: str,
                       phone: str, confirmation_token: str, comment: str = "",
                       notify_consent: bool = True, promo_code: str = "", source: str = "",
                       group_size: int = 1, ctx: ToolContext | None = None) -> dict:
        policies = self.settings.policies
        service = self.settings.service(service_id)
        master = self.settings.master(master_id)
        if not service or not master:
            raise ToolError("Неизвестная услуга или мастер")
        if service_id not in (master.get("services") or []):
            raise ToolError(f"{master['name']} не делает «{service['title']}»")

        if not customer_name or len(customer_name.strip()) < 2:
            raise ToolError("Нужно имя клиента", code="need_name")
        country = self.tenant.salon.get("phoneCountry", "")
        # Про код страны говорим только тому, у кого номер длиннее местного:
        # на «123» и «1111111111» такой совет сбивает с толку — там цифр не
        # хватает, а не кода.
        problem = phone_problem(phone, country)
        if problem == "need_country_code":
            raise ToolError("Номер другой страны — укажите его с кодом, например +1 305 555 0134",
                            code="need_country_code")
        if problem:
            raise ToolError("Нужен корректный телефон для связи", code="bad_phone")
        normalized_phone = normalize_phone(phone)
        # Один человек набирает номер по-разному: «092…» дома и «+598 92…» в
        # переписке. Карточку, чёрный список и историю ищем по обоим написаниям —
        # иначе заблокированный клиент записывался, сменив формат номера.
        keys = client_keys(phone, country)
        existing_client = self.store.client_by_phone(client_key(phone, country),
                                                     tenant_id=self.tenant.slug, aliases=keys)
        if existing_client and existing_client.blocked:
            raise ToolError("Онлайн-запись для этого клиента отключена — обратитесь в салон",
                            escalate=True, code="blocked")
        group_size = max(1, int(group_size or 1))
        capacity = max(1, int(service.get("groupCapacity") or 1))
        if group_size > capacity:
            raise ToolError(f"Для этой услуги доступно не больше {capacity} мест", code="group_over")
        # Услуга с несколькими местами — общая сессия: курс или мастер-класс.
        # Такие записи делят одно время у одного мастера, и обычное правило
        # «одна запись на слот» к ним не применяется.
        shared = capacity > 1

        # 1. Явное подтверждение — проверяем сообщения клиента, а не слова модели.
        if policies.get("requireExplicitConfirmation", True):
            if not ctx or not client_confirmed(ctx.history):
                raise ToolError("Клиент ещё не подтвердил запись. Покажите сводку и дождитесь явного «да».")

        # 2. Подпись слота: время должно быть из того, что показывал get_free_slots.
        start_dt = _parse_start(start, self.settings.timezone)
        if not check_slot_token(confirmation_token, master_id, service_id, start_dt.isoformat(),
                                self.tenant.slug):
            raise ToolError("Это время не предлагалось клиенту — сначала вызовите get_free_slots")

        # 2.1 Минимальный запас времени. Проверяется отдельно от сетки окон:
        # подпись слота не стареет, и показанное утром время «через час» иначе
        # можно было бы отправить в запись к самому его началу.
        end_dt = start_dt + timedelta(minutes=int(service["duration"]))
        location_id = str(master.get("locationId") or "main")
        resource_kind = str(service.get("resourceKind") or "").strip()
        resource = None
        if resource_kind:
            resource = self.store.available_resource(
                tenant_id=self.tenant.slug, kind=resource_kind,
                start=start_dt, end=end_dt,
                location_id=None if location_id == "main" else location_id)
            if not resource:
                raise ToolError(f"На это время нет свободного ресурса типа «{resource_kind}»",
                                conflict=True)
        lead = lead_minutes(self.settings)
        if lead and start_dt < now(self.settings.timezone) + timedelta(minutes=lead):
            raise ToolError(f"Записываем не раньше чем за {_human_lead(lead)} до визита — "
                            "предложите клиенту более позднее время")

        # 3. Лимит записей на телефон.
        limit = policies.get("maxBookingsPerPhonePerDay")
        if limit:
            since = datetime.now(timezone.utc) - timedelta(days=1)
            count = len(self.store.bookings_by_phone(normalized_phone, since,
                                                     tenant_id=self.tenant.slug, aliases=keys))
            if not within_daily_limit(count, limit):
                raise ToolError("По этому номеру уже максимум записей на сегодня — передайте администратору",
                                escalate=True, code="daily_limit")

        # 3.1 Клиент с историей неявок: записываем, но с обязательным подтверждением.
        risky = self._is_no_show_risk(phone)

        # Ключ карточки — международный формат: «092…» и «+598 92…» должны
        # попадать в одного человека, а не в двух.
        client = self.store.upsert_client(
            tenant_id=self.tenant.slug, phone=client_key(phone, country), name=customer_name,
            lang=ctx.lang if ctx else "ru", consent=notify_consent, aliases=keys,
        )
        promo = (promo_code or "").strip().upper()
        discount = 0
        if promo:
            offer = next((p for p in self.tenant.salon.get("promotions", [])
                          if str(p.get("code") or "").upper() == promo and p.get("active", True)), None)
            if not offer:
                raise ToolError("Промокод не найден или больше не действует", code="promo_unknown")
            if offer.get("firstVisitOnly") and client.visits_count > 0:
                raise ToolError("Этот промокод действует только на первый визит", code="promo_first")
            base = max(0, int(service.get("priceAmount") or 0))
            discount = (base * int(offer.get("value") or 0) // 100
                        if offer.get("kind") == "percent" else int(offer.get("value") or 0))
            discount = min(base, max(0, discount))

        # 3.2 Лимит тарифа. Проверяем до вставки, чтобы не создавать запись, за которую не заплачено.
        try:
            check_and_count(self.store, "bookings", tenant_id=self.tenant.slug)
        except LimitExceeded as exc:
            log.error("Лимит записей: %s", exc.message)
            raise ToolError(exc.message, escalate=True) from exc

        # 4. Идемпотентность: повторный вызов не создаёт вторую запись.
        #
        # Ключ считается от «мастер + время + телефон», а уникален он по всей
        # таблице и без оглядки на статус. Отменённая запись держала его вечно:
        # клиент, вернувшийся на то же время после отмены, доходил до вставки и
        # получал «это время только что заняли» — при том что окно свободно и
        # сетка честно его показывала. Поэтому ключ версионируем: занят —
        # берём следующий, пока не найдём свободный или свою же активную запись.
        base = (idempotency_key(master_id, start_dt.isoformat(), phone, self.tenant.slug)
                if policies.get("idempotencyEnabled", True) else None)
        key = base
        if key:
            for attempt in range(1, 50):
                existing = self.store.find_by_idempotency(key, tenant_id=self.tenant.slug)
                if not existing:
                    break
                # Своя же активная запись на это самое время — повторный клик по
                # «подтвердить». Отдаём её, а не заводим вторую.
                if existing.status == "confirmed" and existing.start_at == start_dt:
                    return _booking_payload(existing, service, master, self.settings, ctx.lang)
                key = f"{base}-{attempt}"   # колонка на 64 символа, хеш — 48

        # 5. Пересечение с чужой записью. Проверяется всегда, а не по политике:
        # услуга на три часа перекрывает всё, что попадает внутрь неё, и её
        # середину уникальный индекс по началу не защищает.
        clash = self.store.overlapping(master_id, start_dt, end_dt, tenant_id=self.tenant.slug)
        if clash and shared:
            # Соседи по той же сессии не мешают: считаем места, а не записи.
            others = [b for b in clash if not (b.shared and b.service_id == service_id
                                               and b.start_at == start_dt)]
            taken = self.store.session_seats(master_id, service_id, start_dt,
                                             tenant_id=self.tenant.slug)
            if not others:
                clash = []
                if taken + group_size > capacity:
                    left = max(0, capacity - taken)
                    raise ToolError(
                        f"В этой группе осталось мест: {left}" if left
                        else "В этой группе не осталось свободных мест",
                        conflict=True, code="group_full")
        if clash:
            busy = clash[0]
            log.info("Пересечение: %s занят %s–%s", master_id, busy.start_at, busy.end_at)
            raise ToolError("Это время пересекается с другой записью мастера — "
                            "предложите клиенту другое", conflict=True, code="slot_taken")

        # 5.1 Перепроверка слота непосредственно перед вставкой.
        if policies.get("recheckSlotBeforeInsert", True):
            date_str = start_dt.date().isoformat()
            try:
                fresh = slot_at(self.settings, self.calendar, master, service, date_str,
                                start_dt.strftime("%H:%M"))
            except CalendarError as exc:
                raise ToolError("Календарь недоступен — не могу подтвердить запись",
                                escalate=True, code="calendar_down") from exc
            # Время проверяем само по себе, а не по сетке меню: клиент мог
            # назвать свободные 16:00 между двумя окнами кнопок.
            if not fresh:
                raise ToolError("Это время только что заняли — предложите клиенту другое",
                                conflict=True, code="slot_taken")

        # 6. Вставка в БД. Уникальный индекс (мастер, время) — настоящая защита от гонки.
        try:
            booking = self.store.create_booking(
                tenant_id=self.tenant.slug,
                conversation_id=ctx.conversation_id if ctx else None,
                master_id=master_id, service_id=service_id,
                start_at=start_dt, end_at=end_dt,
                client_id=client.id, client_name=customer_name.strip(), phone=normalized_phone,
                lang=ctx.lang if ctx else "ru", source=(source or (ctx.channel if ctx else "direct")),
                promo_code=promo, price_amount=max(0, int(service.get("priceAmount") or 0)),
                currency=str(service.get("currency") or "UYU")[:3].upper(), discount_amount=discount,
                location_id=location_id, group_size=group_size, shared=shared,
                comment=(comment or "").strip(), idempotency_key=key,
                notify_consent=bool(notify_consent),
                requires_confirmation=risky,
            )
        except SlotTaken as exc:
            raise ToolError("Это время только что заняли — предложите клиенту другое",
                            conflict=True) from exc

        if resource:
            self.store.assign_resource(booking.id, resource.id)

        # 7. Календарь. Отказ — откатываем запись и не говорим «вы записаны».
        try:
            event = self.calendar.create_event(
                master=master, service=service, start=start_dt, end=end_dt,
                client_name=customer_name.strip(), phone=phone, comment=comment or "",
            )
        except CalendarError as exc:
            self.store.drop_booking(booking.id)
            log.error("Календарь отказал, запись откачена: %s", exc)
            raise ToolError("Календарь не принял запись — предложите повторить или передайте администратору",
                            escalate=True) from exc

        self.store.attach_event(booking.id, event["id"], event.get("htmlLink"))
        booking.event_id = event["id"]
        booking.html_link = event.get("htmlLink")

        if risky:
            # Клиента не отчитываем: просто предупреждаем, что накануне спросим подтверждение,
            # и сообщаем администратору, чтобы он мог перезвонить.
            notify_admin(self.settings,
                         f"Запись клиента с историей неявок: {customer_name}, "
                         f"{start_dt.strftime('%d.%m %H:%M')}, {service['title']}")

        # 8. Уведомления ставим только после ответа календаря: пока события нет,
        # «вы записаны» обещать нельзя. Сбой очереди саму запись не отменяет.
        if self.notifications:
            try:
                self.notifications.schedule_for_booking(booking, self.tenant)
            except Exception as exc:  # noqa: BLE001
                log.error("Не удалось запланировать уведомления по %s: %s", booking.id, exc)

        log_event("booking.created", tenant=self.tenant.slug, booking=booking.id,
                  master=master_id, service=service_id, start=start_dt.isoformat(),
                  source=booking.source, price=booking.price_amount,
                  group=booking.group_size, shared=booking.shared)
        return _booking_payload(booking, service, master, self.settings, ctx.lang)

    # --- инструмент 3 -----------------------------------------------------
    def cancel_booking(self, *, booking_id: str | None = None, phone: str | None = None,
                       ctx: ToolContext | None = None) -> dict:
        if not self.settings.policies.get("allowCancel", True):
            raise ToolError("Отмена через бота отключена — передайте разговор администратору", escalate=True)

        booking = None
        if booking_id:
            booking = self.store.get_booking(booking_id, tenant_id=self.tenant.slug)
        elif phone:
            upcoming = self.store.upcoming_by_phone(
                normalize_phone(phone), datetime.now(timezone.utc), tenant_id=self.tenant.slug,
                aliases=client_keys(phone, self.tenant.salon.get("phoneCountry", "")))
            if len(upcoming) > 1:
                return {
                    "needs_choice": True,
                    "bookings": [
                        {"booking_id": b.id, "start": b.start_at.isoformat(), "service_id": b.service_id,
                         "master_id": b.master_id}
                        for b in upcoming
                    ],
                }
            booking = upcoming[0] if upcoming else None

        if not booking or booking.status != "confirmed":
            raise ToolError("Активной записи не нашёл. Уточните телефон или дату.")

        if self.settings.policies.get("requireExplicitConfirmation", True):
            if not ctx or not client_confirmed(ctx.history):
                raise ToolError("Клиент не подтвердил отмену — переспросите явно")

        master = self.settings.master(booking.master_id)
        if booking.event_id and master:
            try:
                self.calendar.delete_event(master, booking.event_id)
            except CalendarError as exc:
                log.error("Не удалось удалить событие: %s", exc)
                raise ToolError("Календарь не отвечает — передайте отмену администратору", escalate=True) from exc

        self.store.cancel_booking(booking.id)
        if self.notifications:
            # Напоминание об отменённой записи — худшее, что можно прислать клиенту.
            self.notifications.cancel_for_booking(booking.id)
            # Клиенту пишем, только когда отменил не он сам: свою отмену он уже
            # видит ответом в том же диалоге, и второе сообщение об этом —
            # лишний расход утверждённого шаблона.
            if ctx and ctx.channel == "admin":
                self.notifications.notify_client_cancelled(booking, self.tenant)
            # Мастеру, наоборот, сообщаем: у него освободилось окно.
            self.notifications.notify_master_cancelled(booking, self.tenant)
            self.notifications.offer_waitlist(booking, self.tenant)
        log_event("booking.cancelled", tenant=self.tenant.slug, booking=booking.id,
                  master=booking.master_id, service=booking.service_id,
                  start=booking.start_at.isoformat(), by=(ctx.channel if ctx else "—"))
        return {"cancelled": True, "booking_id": booking.id,
                "start": booking.start_at.isoformat()}

    # --- инструмент 4 -----------------------------------------------------
    def reschedule_booking(self, *, booking_id: str, master_id: str, start: str,
                           confirmation_token: str, ctx: ToolContext | None = None) -> dict:
        if not self.settings.policies.get("allowReschedule", False) and (not ctx or ctx.channel != "admin"):
            raise ToolError("Перенос через бота отключён — обратитесь к администратору", escalate=True)
        booking = self.store.get_booking(booking_id, tenant_id=self.tenant.slug)
        if not booking or booking.status != "confirmed":
            raise ToolError("Активная запись не найдена")
        if self.settings.policies.get("requireExplicitConfirmation", True):
            if not ctx or not client_confirmed(ctx.history):
                raise ToolError("Клиент не подтвердил перенос — переспросите явно")

        service = self.settings.service(booking.service_id)
        new_master = self.settings.master(master_id)
        old_master = self.settings.master(booking.master_id)
        if not service or not new_master or booking.service_id not in (new_master.get("services") or []):
            raise ToolError("Неизвестный мастер или он не делает эту услугу")
        start_dt = _parse_start(start, self.settings.timezone)
        if not check_slot_token(confirmation_token, master_id, booking.service_id, start_dt.isoformat(),
                                self.tenant.slug):
            raise ToolError("Это время не предлагалось клиенту — сначала вызовите get_free_slots")
        end_dt = start_dt + timedelta(minutes=int(service["duration"]))
        clash = self.store.overlapping(master_id, start_dt, end_dt, tenant_id=self.tenant.slug,
                                       exclude_id=booking.id)
        if clash:
            raise ToolError("Это время пересекается с другой записью мастера", conflict=True)

        old_event_id, old_link = booking.event_id, booking.html_link
        was = {"master_id": booking.master_id, "start_at": booking.start_at}
        created_new = False
        try:
            if old_event_id and old_master and old_master["id"] == new_master["id"]:
                event = self.calendar.update_event(
                    master=new_master, event_id=old_event_id, service=service,
                    start=start_dt, end=end_dt, client_name=booking.client_name,
                    phone=booking.phone, comment=booking.comment or "")
            else:
                event = self.calendar.create_event(
                    master=new_master, service=service, start=start_dt, end=end_dt,
                    client_name=booking.client_name, phone=booking.phone, comment=booking.comment or "")
                created_new = True
            moved = self.store.reschedule_booking(
                booking.id, tenant_id=self.tenant.slug, master_id=master_id,
                start_at=start_dt, end_at=end_dt)
            if not moved:
                raise ToolError("Запись не найдена")
        except (CalendarError, SlotTaken) as exc:
            if created_new and event.get("id"):
                try: self.calendar.delete_event(new_master, event["id"])
                except CalendarError: pass
            raise ToolError("Не удалось перенести запись — выберите другое время", conflict=True) from exc

        self.store.attach_event(booking.id, event["id"], event.get("htmlLink"))
        moved.event_id, moved.html_link = event["id"], event.get("htmlLink")
        if created_new and old_event_id and old_master:
            try:
                self.calendar.delete_event(old_master, old_event_id)
            except CalendarError as exc:
                log.error("Новая запись перенесена, но старое событие %s не удалено: %s", old_event_id, exc)
        if self.notifications:
            self.notifications.reschedule_for_booking(moved, self.tenant, previous=was)
        log_event("booking.rescheduled", tenant=self.tenant.slug, booking=moved.id,
                  master=moved.master_id, service=moved.service_id,
                  start=moved.start_at.isoformat(), by=(ctx.channel if ctx else "—"))
        return {**_booking_payload(moved, service, new_master, self.settings, ctx.lang),
                "rescheduled": True, "previous_event": old_link}

    # --- инструмент 5 -----------------------------------------------------
    def handoff_to_human(self, *, reason: str, summary: str = "", ctx: ToolContext | None = None) -> dict:
        handoff = self.settings.handoff
        lang = ctx.lang if ctx else self.settings.default_lang
        # Текст владельца — только на его языке; для остальных берём перевод, а
        # не русскую фразу посреди испанского диалога. Заполненное поле
        # `handoffMessageEs`/`En` важнее нашего текста: салон пишет своё.
        own = self.settings.localized(handoff, "handoffMessage", lang)
        if norm_lang(lang) != "ru" and own == (handoff.get("handoffMessage") or ""):
            own = ""      # перевода нет — русский оригинал клиенту не показываем
        payload = {
            "handed_off": True,
            "reason": reason,
            "admin": handoff.get("managerName") or handoff.get("adminName")
            or ADMIN_WORD.get(norm_lang(lang), ADMIN_WORD["ru"]),
            "contact": handoff.get("managerWhatsapp") or handoff.get("adminWhatsapp")
            or self.settings.salon.get("whatsapp"),
            "message": own or HANDOFF_MESSAGE.get(norm_lang(lang), HANDOFF_MESSAGE["ru"]),
        }
        log.warning("HANDOFF (%s): %s | %s", ctx.conversation_id if ctx else "-", reason, summary)
        self.store.bump_usage(self.tenant.slug, "handoffs", _period())
        self._notify_manager(reason, summary, ctx)
        return payload

    def recover(self, reason: str, summary: str = "", ctx: ToolContext | None = None) -> dict:
        """Сбой на нашей стороне у автономного бота.

        Клиента не отправляем к человеку — предлагаем пройти запись по шагам,
        а владелец узнаёт о сбое из уведомления.
        """
        log.warning("RECOVER (%s): %s | %s", ctx.conversation_id if ctx else "-", reason, summary)
        self._notify_manager(reason, summary, ctx)
        lang = ctx.lang if ctx else "ru"
        return {"handed_off": False, "reason": reason,
                "message": RECOVER_MESSAGE.get(lang, RECOVER_MESSAGE["ru"])}

    # --- вспомогательное ---------------------------------------------------
    def _is_no_show_risk(self, phone: str) -> bool:
        """Три неявки за окно — и бот попросит подтвердить визит заранее."""
        policies = self.settings.policies
        limit = int(policies.get("noShowLimit", 3) or 0)
        if limit <= 0:
            return False
        window = int(policies.get("noShowWindowDays", 180) or 180)
        since = datetime.now(timezone.utc) - timedelta(days=window)
        count = self.store.no_show_count(
            normalize_phone(phone), tenant_id=self.tenant.slug, since=since,
            aliases=client_keys(phone, self.tenant.salon.get("phoneCountry", "")))
        return count >= limit

    def _notify_manager(self, reason: str, summary: str, ctx: ToolContext | None) -> None:
        """Эскалация уходит в WhatsApp главного менеджера — там её точно увидят."""
        handoff = self.settings.handoff
        text = "\n".join(filter(None, [
            f"⚠️ {self.settings.salon.get('name', self.tenant.slug)}: нужен человек",
            f"Причина: {reason}",
            f"Клиент: {summary}" if summary else None,
            f"Диалог: {ctx.conversation_id}" if ctx else None,
        ]))
        phone = handoff.get("managerWhatsapp") or handoff.get("adminWhatsapp")
        if phone and self.notifications:
            try:
                self.notifications.notify_manager(self.tenant, phone, text)
                return
            except Exception as exc:  # noqa: BLE001 — эскалация не должна ронять диалог
                log.error("Не удалось написать менеджеру в WhatsApp: %s", exc)
        notify_admin(self.settings, text)


def _parse_start(value: str, tz_name: str) -> datetime:
    """Принимает ISO-время или 'YYYY-MM-DD HH:MM' — модель пишет по-разному."""
    text = (value or "").strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            date_part, time_part = text.split()
            dt = datetime.fromisoformat(f"{date_part}T{time_part}")
        except ValueError as exc:
            raise ToolError("Не понял время записи — нужен формат 2026-08-10T15:00") from exc
    if dt.tzinfo is None:
        return zoned(dt.date().isoformat(), dt.strftime("%H:%M"), tz_name)
    return dt.astimezone(now(tz_name).tzinfo)


def _booking_payload(booking, service: dict, master: dict, settings: Tenant, lang: str = "ru") -> dict:
    local = booking.start_at.astimezone(now(settings.timezone).tzinfo)
    date_str = local.date().isoformat()
    return {
        "booking_id": booking.id,
        "event_id": booking.event_id,
        "html_link": booking.html_link,
        # Подтверждение уходит на языке клиента — вместе с названием услуги.
        "service": settings.localized(service, "title", lang),
        "master": master["name"],
        "date": date_str,
        "date_label": human_date(date_str, lang),
        "time": local.strftime("%H:%M"),
        "duration": service["duration"],
        "address": settings.salon.get("address", ""),
    }


def notify_admin(settings: Tenant, text: str) -> None:
    """Уведомление в Telegram. Молча не падаем — это не критичный путь."""
    handoff = settings.handoff
    token, chat_id = handoff.get("telegramBotToken"), handoff.get("telegramChatId")
    if not (token and chat_id):
        return
    try:
        import httpx

        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Не удалось уведомить администратора: %s", exc)
