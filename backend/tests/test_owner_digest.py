"""Утренняя сводка владельцу.

Владелец узнаёт про дыру в расписании утром, а не вечером. Сводка собирается в
то же утро, а не с вечера: за ночь записи отменяют и переносят.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.notify.service import settings_for
from backend.app.timeutil import zoned

TZ = "America/Montevideo"


def _morning(date_key: str, at: str = "08:05") -> datetime:
    """Момент «сейчас» в поясе салона, приведённый к UTC."""
    return zoned(date_key, at, TZ).astimezone(timezone.utc)


def _book(store, tenant, *, date_key: str, at: str, name: str = "Мария",
          status: str = "confirmed", paid: int = 0, minutes: int = 60, **fields):
    start = zoned(date_key, at, TZ)
    return store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=start, end_at=start + timedelta(minutes=minutes),
        client_name=name, phone="59891234567", status=status,
        paid_amount=paid, currency="UYU", **fields)


@pytest.fixture
def today(tenant) -> str:
    from backend.app.timeutil import today_key

    return today_key(tenant.timezone)


def test_digest_is_scheduled_once_a_day(notifications, store, tenant, today):
    _book(store, tenant, date_key=today, at="11:00")

    first = notifications.schedule_owner_digest(tenant, moment=_morning(today))
    second = notifications.schedule_owner_digest(tenant, moment=_morning(today, "08:40"))

    assert first is not None
    assert second is None      # уникальное имя задачи, а не проверка в коде
    queue = store.list_notifications(tenant_id=tenant.slug)
    assert [t.type for t in queue] == ["owner_digest"]
    assert queue[0].recipient == settings_for(tenant).owner_recipient


def test_digest_is_not_sent_in_the_afternoon(notifications, store, tenant, today):
    """Воркер, поднявшийся к вечеру, «утреннюю сводку» уже не шлёт."""
    assert notifications.schedule_owner_digest(tenant, moment=_morning(today, "14:00")) is None
    assert store.list_notifications(tenant_id=tenant.slug) == []


def test_digest_tells_the_day_and_yesterday(notifications, store, tenant, today):
    yesterday = (zoned(today, "12:00", TZ) - timedelta(days=1)).date().isoformat()
    _book(store, tenant, date_key=today, at="11:00", name="Мария")
    _book(store, tenant, date_key=today, at="15:00", name="Хуан", requires_confirmation=True)
    _book(store, tenant, date_key=yesterday, at="12:00", name="Ана",
          status="completed", paid=1500)
    _book(store, tenant, date_key=yesterday, at="16:00", name="Луис", status="no_show")

    body = notifications.schedule_owner_digest(tenant, moment=_morning(today)).body

    assert "Записей сегодня: 2" in body
    assert "11:00 Мария" in body
    assert "Ждут подтверждения: 1 — Хуан" in body
    assert "Вчера: 1 визитов, 1500 UYU, неявок 1" in body
    # Загрузка считается из смен и записей, без обращения к Google.
    assert "рабочего времени" in body


def test_digest_needs_a_recipient(notifications, store, tenant, today):
    tenant.integration["notifications"] = {**tenant.integration["notifications"],
                                           "ownerPhone": "", "ownerProvider": "console"}
    tenant.integration["handoff"] = {**tenant.integration["handoff"],
                                     "adminWhatsapp": "", "telegramChatId": ""}

    assert notifications.schedule_owner_digest(tenant, moment=_morning(today)) is None


def test_digest_can_be_switched_off(notifications, store, tenant, today):
    tenant.integration["notifications"] = {**tenant.integration["notifications"],
                                           "dailyDigest": False}

    assert notifications.schedule_owner_digest(tenant, moment=_morning(today)) is None


def test_digest_survives_the_queue(notifications, store, tenant, today):
    """Задача без записи должна пройти guard и уйти, а не отмениться."""
    _book(store, tenant, date_key=today, at="11:00")
    notifications.schedule_owner_digest(tenant, moment=_morning(today))

    sent = notifications.tick(limit=10)

    assert sent == 1
    task = store.list_notifications(tenant_id=tenant.slug)[0]
    assert task.status == "sent"
    assert task.error is None
