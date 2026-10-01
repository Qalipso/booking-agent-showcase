"""Google Calendar. Без кредов работает локальный календарь на той же БД."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .tenants import Tenant

log = logging.getLogger("calendar")
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarError(RuntimeError):
    """Календарь недоступен или отказал — повод для эскалации, а не для «вы записаны»."""


def calendar_id(master: dict) -> str:
    """Календарь мастера. Пустое значение — тот же «primary», а не KeyError на записи."""
    return (master.get("calendarId") or "primary").strip() or "primary"


class CalendarService:
    """Единственный компонент, которому разрешено менять календарь."""

    def __init__(self, tenant: Tenant, store) -> None:
        self.settings = tenant   # совместимость: тот же интерфейс, что у прежних настроек
        self.tenant = tenant
        self.store = store
        self._client: Any = None
        self.mode = "local"
        # Google настроен, но подключиться не удалось. Отличать это от честного
        # локального режима обязательно: иначе сломанная интеграция выглядит
        # как «владелец не подключал календарь», и её никто не чинит.
        self.degraded = False
        self.error = ""
        self._connect()

    def _connect(self) -> None:
        integration = self.tenant.google
        mode = integration.get("mode", "local")
        self.degraded, self.error = False, ""
        if mode == "local":
            self.mode = "local"
            return
        try:
            from googleapiclient.discovery import build  # локальный импорт: без Google не нужен

            if mode == "service_account":
                from google.oauth2 import service_account

                path = integration.get("serviceAccountFile")
                if not path:
                    raise RuntimeError("не указан путь к JSON-ключу сервисного аккаунта")
                creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
                if integration.get("impersonateUser"):
                    creds = creds.with_subject(integration["impersonateUser"])
            else:
                from google.oauth2.credentials import Credentials

                missing = [name for name, key in
                           (("refresh token", "refreshToken"), ("Client ID", "clientId"),
                            ("Client Secret", "clientSecret"))
                           if not integration.get(key)]
                if missing:
                    raise RuntimeError("не хватает: " + ", ".join(missing))
                creds = Credentials(
                    token=None,
                    refresh_token=integration["refreshToken"],
                    client_id=integration["clientId"],
                    client_secret=integration["clientSecret"],
                    token_uri="https://oauth2.googleapis.com/token",
                    scopes=SCOPES,
                )
            self._client = build("calendar", "v3", credentials=creds, cache_discovery=False)
            self.mode = "google"
        except Exception as exc:  # noqa: BLE001 — падать на старте нельзя, но и молчать тоже
            log.error("Google Calendar настроен (%s), но недоступен: %s", mode, exc)
            self._client = None
            self.mode = "local"
            self.degraded = True
            self.error = str(exc)[:300]

    def reload(self) -> None:
        """Вызывается после сохранения формы."""
        self._client = None
        self._connect()

    def busy(self, master: dict, start: datetime, end: datetime,
             exclude_booking_id: str = "") -> list[tuple[datetime, datetime]]:
        """Занятое время мастера: свои записи плюс всё, что стоит у него в Google.

        ``exclude_booking_id`` — переносимая запись: её собственное время
        занятым не считается ни в базе, ни в Google, иначе перенос «в те же
        часы, но к другому мастеру» упирался бы в самого себя.

        Свои записи учитываются всегда, а не только в локальном режиме. Иначе
        сетка окон и проверка перед вставкой считают занятость по разным
        источникам: клиенту показывалось время, на которое уже есть запись в
        базе, — и подтверждение падало с «это время пересекается с другой
        записью мастера». Google-событие могло не создаться, попасть в чужой
        календарь или просто не отдаться freebusy без прав — база знает точно.
        """
        own = self.store.busy_intervals(master["id"], start, end, tenant_id=self.tenant.slug,
                                        exclude_booking_id=exclude_booking_id)
        skip = self._own_span(exclude_booking_id)
        if self.mode != "google":
            return own
        try:
            res = (
                self._client.freebusy()
                .query(
                    body={
                        "timeMin": start.isoformat(),
                        "timeMax": end.isoformat(),
                        "items": [{"id": calendar_id(master)}],
                    }
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(str(exc)) from exc
        busy = res.get("calendars", {}).get(calendar_id(master), {}).get("busy", [])
        spans = [
            (datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
             datetime.fromisoformat(b["end"].replace("Z", "+00:00")))
            for b in busy
        ]
        # Своя запись и её же событие в Google — один интервал, а не два:
        # дубль ломал групповые сессии, где «занято своей же сессией» означает
        # ровно один совпадающий по границам интервал.
        for span in own:
            if span not in spans:
                spans.append(span)
        # Событие переносимой записи в Google — это она сама. Убираем и его:
        # без этого freebusy возвращал бы окно занятым, хотя в базе мы его уже
        # исключили.
        return [span for span in spans if span != skip] if skip else spans

    def _own_span(self, booking_id: str) -> tuple[datetime, datetime] | None:
        """Интервал записи, которую переносим, — чтобы вычесть её из freebusy."""
        if not booking_id:
            return None
        booking = self.store.get_booking(booking_id, tenant_id=self.tenant.slug)
        if not booking:
            return None
        start = booking.start_at if booking.start_at.tzinfo else booking.start_at.replace(tzinfo=timezone.utc)
        end = booking.end_at if booking.end_at.tzinfo else booking.end_at.replace(tzinfo=timezone.utc)
        return (start, end)

    def create_event(
        self, *, master: dict, service: dict, start: datetime, end: datetime,
        client_name: str, phone: str, comment: str = "",
    ) -> dict:
        """Создаёт событие. Возвращает {'id', 'htmlLink'} либо бросает CalendarError."""
        summary = f"{service['title']} — {client_name}"
        description = "\n".join(
            filter(None, [
                f"Услуга: {service['title']} ({service['duration']} мин)",
                f"Мастер: {master['name']}",
                f"Клиент: {client_name}",
                f"Телефон: {phone}",
                f"Комментарий: {comment}" if comment else None,
                "Источник: бот записи Demo Salon",
            ])
        )
        if self.mode != "google":
            return {"id": f"local-{self.tenant.slug}-{int(start.timestamp())}-{master['id']}", "htmlLink": None,
                    "summary": summary, "description": description}
        try:
            event = (
                self._client.events()
                .insert(
                    calendarId=calendar_id(master),
                    body={
                        "summary": summary,
                        "description": description,
                        "start": {"dateTime": start.isoformat(), "timeZone": self.tenant.timezone},
                        "end": {"dateTime": end.isoformat(), "timeZone": self.tenant.timezone},
                        "extendedProperties": {
                            "private": {"tenantId": self.tenant.slug, "masterId": master["id"],
                                        "serviceId": service["id"]}
                        },
                    },
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(str(exc)) from exc
        return {"id": event["id"], "htmlLink": event.get("htmlLink"),
                "summary": summary, "description": description}

    def create_block(self, *, master: dict, title: str, start: datetime, end: datetime) -> dict:
        """Технический перерыв в календаре мастера.

        Отдельно от `create_event`: у перерыва нет ни клиента, ни услуги, а в
        описании важно ровно обратное — что это не запись и звонить некому.
        Без события в календаре время выглядит снаружи свободным, и мастеру
        назначают встречу ровно в обед.
        """
        summary = title.strip() or "Перерыв"
        description = "Технический перерыв. Не запись клиента.\nИсточник: панель Demo Salon"
        if self.mode != "google":
            return {"id": f"local-block-{self.tenant.slug}-{int(start.timestamp())}-{master['id']}",
                    "htmlLink": None, "summary": summary}
        try:
            event = (
                self._client.events()
                .insert(
                    calendarId=calendar_id(master),
                    body={
                        "summary": summary,
                        "description": description,
                        "start": {"dateTime": start.isoformat(), "timeZone": self.tenant.timezone},
                        "end": {"dateTime": end.isoformat(), "timeZone": self.tenant.timezone},
                        "transparency": "opaque",
                        "extendedProperties": {
                            "private": {"tenantId": self.tenant.slug, "masterId": master["id"],
                                        "kind": "break"}
                        },
                    },
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(str(exc)) from exc
        return {"id": event["id"], "htmlLink": event.get("htmlLink"), "summary": summary}

    def delete_event(self, master: dict, event_id: str) -> None:
        if self.mode != "google":
            return
        try:
            self._client.events().delete(calendarId=calendar_id(master), eventId=event_id).execute()
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(str(exc)) from exc

    def update_event(self, *, master: dict, event_id: str, service: dict,
                     start: datetime, end: datetime, client_name: str,
                     phone: str, comment: str = "") -> dict:
        """Перенести событие внутри календаря того же мастера."""
        if self.mode != "google":
            return {"id": f"local-{self.tenant.slug}-{int(start.timestamp())}-{master['id']}",
                    "htmlLink": None}
        body = {
            "summary": f"{service['title']} — {client_name}",
            "description": "\n".join(filter(None, [
                f"Услуга: {service['title']} ({service['duration']} мин)", f"Мастер: {master['name']}",
                f"Клиент: {client_name}", f"Телефон: {phone}",
                f"Комментарий: {comment}" if comment else None, "Источник: бот записи Demo Salon",
            ])),
            "start": {"dateTime": start.isoformat(), "timeZone": self.tenant.timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": self.tenant.timezone},
        }
        try:
            event = self._client.events().patch(
                calendarId=calendar_id(master), eventId=event_id, body=body).execute()
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(str(exc)) from exc
        return {"id": event["id"], "htmlLink": event.get("htmlLink")}
