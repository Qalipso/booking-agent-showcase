"""Хранилище диалогов, записей, уведомлений и секретов.

Postgres — единственное хранилище в проде; SQLite остаётся только для тестов и
локального запуска и включается явным ``DB_ALLOW_SQLITE=1``.
Двойное бронирование ловится базой, а не проверкой в коде: гонка двух
одновременных запросов иначе неизбежна. Уникальный индекс (master_id, start_at)
закрывает совпадение начала, EXCLUDE-ограничение на Postgres — пересечение
интервалов (услуга на три часа перекрывает всё, что попадает внутрь неё).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (
    func,
    Index, JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
    create_engine, delete, or_, select, text, update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .schema import ROOT

log = logging.getLogger("db")


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True, default="default")
    channel: Mapped[str] = mapped_column(String(16), default="web")
    external_id: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Client(Base):
    """Единая карточка клиента внутри бизнеса."""

    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("tenant_id", "phone", name="uq_client_phone"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    phone: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    lang: Mapped[str] = mapped_column(String(8), default="ru")
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    consent: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    visits_count: Mapped[int] = mapped_column(Integer, default=0)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_value: Mapped[int] = mapped_column(Integer, default=0)
    loyalty_balance: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        # Двойное бронирование ловится в пределах бизнеса — у разных салонов
        # мастера с одинаковым кодом друг другу не мешают.
        #
        # Индекс частичный: отменённая запись не должна держать слот вечно.
        # Пока условия не было, любое отменённое время становилось непригодным
        # навсегда — сетка показывала его свободным, а «Подтвердить» отвечало
        # «это время только что заняли». Лист ожидания по той же причине не мог
        # отдать освободившееся место никому.
        Index("uq_master_slot", "tenant_id", "master_id", "start_at", unique=True,
              sqlite_where=text("status IN ('confirmed', 'completed') AND shared = 0"),
              postgresql_where=text("status IN ('confirmed', 'completed') AND NOT shared")),
        UniqueConstraint("idempotency_key", name="uq_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True, default="default")
    conversation_id: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True, default=None)
    master_id: Mapped[str] = mapped_column(String(32), index=True)
    service_id: Mapped[str] = mapped_column(String(32))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(40), index=True)
    lang: Mapped[str] = mapped_column(String(8), default="ru")
    source: Mapped[str] = mapped_column(String(32), default="direct", index=True)
    promo_code: Mapped[str] = mapped_column(String(40), default="", index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    event_id: Mapped[str | None] = mapped_column(String(256), default=None)
    html_link: Mapped[str | None] = mapped_column(Text, default=None)
    # confirmed → completed | no_show | cancelled. Неявки нужны, чтобы бот просил
    # подтверждение у тех, кто уже трижды не пришёл.
    status: Mapped[str] = mapped_column(String(16), default="confirmed", index=True)
    # Клиент с историей неявок: запись создана, но требует подтверждения накануне.
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by_client: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), default=None)
    notify_consent: Mapped[bool] = mapped_column(Boolean, default=True)
    price_amount: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="UYU")
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str] = mapped_column(String(16), default="")
    # Абонемент или сертификат, которым закрыт визит. Хранится не ради отчёта, а
    # ради идемпотентности: без него повторный запрос на оплату списывал бы
    # посещение второй раз, а «оплачено абонементом» и остаток самого абонемента
    # разъезжались бы молча.
    asset_id: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)
    location_id: Mapped[str] = mapped_column(String(32), default="main", index=True)
    group_size: Mapped[int] = mapped_column(Integer, default=1)
    # Место в общей сессии (курс, мастер-класс): такие записи делят одно время
    # у одного мастера, и обычные «одна запись — один слот» правила к ним не
    # применяются. Флаг ставится по вместимости услуги в момент записи —
    # база вместимости не знает, а решать это ей приходится в индексах.
    shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Жизненный цикл уведомления: scheduled → sending → sent → delivered,
# либо → failed / cancelled. Всё, кроме scheduled, воркер повторно не берёт.
NOTIFICATION_STATUSES = ("scheduled", "sending", "sent", "delivered", "failed", "cancelled")


class Notification(Base):
    """Очередь уведомлений: подтверждения, напоминания, сообщения владельцу.

    ``notification_id`` — детерминированное имя задачи (`booking-reminder-…-{id}`).
    Уникальный индекс по нему и есть идемпотентность: повторная постановка той же
    задачи не создаёт дубль, а не проверяется кодом.
    """

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("notification_id", name="uq_notification_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[str] = mapped_column(String(160), index=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True, default="default")
    booking_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(40))
    audience: Mapped[str] = mapped_column(String(16))  # client | owner
    provider: Mapped[str] = mapped_column(String(16))  # twilio | telegram | email | console
    channel: Mapped[str] = mapped_column(String(16))   # whatsapp | sms | telegram | email
    recipient: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Снимок времени записи: перенос делает задачу неактуальной ещё до отправки.
    booking_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), index=True, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    fallback_of: Mapped[str | None] = mapped_column(String(160), default=None)
    # Язык сообщения и переменные утверждённого шаблона. Нужны там, где записи
    # под рукой уже нет: просьба об оценке живёт после визита, предложение места
    # — вместо чужой отменённой записи. Собрать из них шаблон в момент отправки
    # неоткуда, поэтому задача несёт их с собой.
    lang: Mapped[str] = mapped_column(String(8), default="")
    variables: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "tenant_id": self.tenant_id,
            "booking_id": self.booking_id,
            "type": self.type,
            "audience": self.audience,
            "provider": self.provider,
            "channel": self.channel,
            "recipient": self.recipient,
            "body": self.body,
            "status": self.status,
            "attempts": self.attempts,
            "scheduled_at": _iso(self.scheduled_at),
            "booking_start_at": _iso(self.booking_start_at),
            "provider_message_id": self.provider_message_id,
            "sent_at": _iso(self.sent_at),
            "delivered_at": _iso(self.delivered_at),
            "error": self.error,
            "fallback_of": self.fallback_of,
        }


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_location_code"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(64), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_resource_code"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), default=None)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32), default="chair")
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TimeBlock(Base):
    """Технический перерыв мастера: обед, уборка, доставка, личное дело.

    Отдельная таблица, а не запись со служебным статусом: у записи есть клиент,
    услуга, деньги, уведомления и место в конверсии — перерыв внутри `bookings`
    испортил бы и выручку, и статистику неявок, и отчёт по источникам.

    Перерыв обязан попадать в календарь мастера: иначе снаружи время выглядит
    свободным, и мастеру прилетает чужая встреча ровно в обед. Идентификатор
    события храним здесь же — чтобы при удалении перерыва снять и его.
    """

    __tablename__ = "time_blocks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    master_id: Mapped[str] = mapped_column(String(32), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(120), default="Перерыв")
    calendar_event_id: Mapped[str | None] = mapped_column(String(256), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))


class BookingResource(Base):
    __tablename__ = "booking_resources"
    __table_args__ = (UniqueConstraint("booking_id", "resource_id", name="uq_booking_resource"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(String(32), index=True)
    master_id: Mapped[str] = mapped_column(String(32), default="")
    date_from: Mapped[str] = mapped_column(String(10))
    date_to: Mapped[str] = mapped_column(String(10))
    time_from: Mapped[str] = mapped_column(String(5), default="")
    time_to: Mapped[str] = mapped_column(String(5), default="")
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)
    offered_booking_id: Mapped[str | None] = mapped_column(String(32), default=None)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_review_booking"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), default=None)
    score: Mapped[int | None] = mapped_column(Integer, default=None)
    feedback: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="requested", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    segment: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ClientAsset(Base):
    """Абонемент или сертификат клиента."""

    __tablename__ = "client_assets"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_client_asset_code"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # membership | certificate
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    balance_amount: Mapped[int] = mapped_column(Integer, default=0)
    remaining_uses: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), default=None)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TenantSecret(Base):
    """Секреты бизнеса, введённые в админке или полученные из OAuth.

    В JSON-конфигурации их больше нет — она лежит в git. Приоритет всё равно у
    переменных окружения, база нужна там, где секрет появляется в рантайме.
    """

    __tablename__ = "tenant_secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_secret"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def _iso(dt: datetime | None) -> str | None:
    return _aware(dt).isoformat() if dt else None


def _aware_booking(booking):
    """Время записи наружу — только с таймзоной.

    Postgres отдаёт `DateTime(timezone=True)` уже в UTC, а SQLite таймзону не
    хранит, и `astimezone()` в шаблонах уведомлений принимает naive-время за
    локальное время машины. Клиенту тогда уходит время, сдвинутое на смещение
    сервера: запись на 15:00 превращалась в «18:00» на машине в UTC-3 и в
    «13:00» в Мадриде. Нормализуем здесь, а не в вызывающем коде: тексты
    уведомлений не должны зависеть от того, чем поднят стенд.
    """
    if booking is not None:
        booking.start_at = _aware(booking.start_at)
        booking.end_at = _aware(booking.end_at)
    return booking


def _phone_keys(phone: str, aliases: tuple[str, ...] | list[str] = ()) -> list[str]:
    """Номер и его прежние написания — по ним ищется один и тот же человек."""
    keys = [phone, *aliases]
    return [k for i, k in enumerate(keys) if k and k not in keys[:i]]


def _to_utc(dt: datetime) -> datetime:
    """SQLite не хранит таймзону — приводим всё к UTC на границе БД."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


BOOKING_STATUSES = ("confirmed", "completed", "no_show", "cancelled")


class UsageCounter(Base):
    """Потребление по тарифу за календарный месяц.

    Счётчик отдельной строкой на (бизнес, месяц, метрика): так лимит считается
    одним запросом и не зависит от того, чистили ли историю записей.
    """

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("tenant_id", "period", "metric", name="uq_usage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)   # YYYY-MM
    metric: Mapped[str] = mapped_column(String(24))              # bookings | ai_messages | handoffs
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))


class AdminUser(Base):
    """Администратор панели: вход по почте и паролю.

    Пароль хранится только хешем bcrypt — из базы его не восстановить, даже имея
    дамп. Счётчик неудачных попыток и ``locked_until`` живут здесь, а не в памяти
    процесса: перезапуск контейнера не должен обнулять защиту от перебора, а
    реплик API может быть несколько.
    """

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(120), default="")
    # owner | admin. Владелец распоряжается деньгами и доступами: подключения,
    # ключи и список пользователей — только его. Администратор ведёт салон.
    role: Mapped[str] = mapped_column(String(16), default="admin", index=True)
    # Тот же человек получает уведомления о записях — отдельного списка контактов
    # не заводим: два списка людей неизбежно разъезжаются.
    telegram_chat_id: Mapped[str] = mapped_column(String(40), default="")
    notify_new_booking: Mapped[bool] = mapped_column(Boolean, default=True)
    # Секрет TOTP. Пока пусто — второй фактор у пользователя не настроен.
    totp_secret: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))


class AdminSession(Base):
    """Сессия входа. В cookie уходит случайный ключ, в базе лежит его хеш.

    Хеш, а не сам ключ: украденный дамп базы тогда не даёт войти под чужой
    сессией. Хранение в базе (а не подписанный токен) позволяет отзывать доступ —
    выход и смена пароля закрывают уже выданные сессии немедленно.
    """

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_users.id", ondelete="CASCADE"),
                                         index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MasterKey(Base):
    """Личная ссылка мастера в свой кабинет.

    Мастер — не пользователь панели: почты у него может не быть, пароль он
    забудет, а второй фактор в салоне превращается в звонок владельцу. Поэтому
    вход — по ссылке, которую владелец выдаёт из панели и в любой момент
    отзывает.

    В базе лежит хеш ключа, а не сам ключ: дамп базы не даёт войти. Ссылка одна
    на мастера — новая выдача гасит старую вместе со всеми открытыми по ней
    сессиями (`ondelete CASCADE` ниже).
    """

    __tablename__ = "master_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "master_id", name="uq_master_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    master_id: Mapped[str] = mapped_column(String(32), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Второй фактор: четыре цифры, которые владелец диктует мастеру отдельно от
    # ссылки. Ссылку пересылают в мессенджере, и она переживает пересылку —
    # ПИН этого не делает. Хранится хешем bcrypt, как пароль в панели.
    pin_hash: Mapped[str] = mapped_column(String(120), default="")
    # Четыре цифры перебираются за вечер, поэтому счётчик попыток живёт в базе,
    # а не в памяти процесса: перезапуск контейнера не должен обнулять защиту.
    pin_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class MasterSession(Base):
    """Открытый кабинет мастера. Живёт дольше админской: телефон мастера — его
    личный, а вход раз в неделю по ссылке из переписки никто терпеть не станет."""

    __tablename__ = "master_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_id: Mapped[int] = mapped_column(Integer, ForeignKey("master_keys.id", ondelete="CASCADE"),
                                        index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AssetProblem(RuntimeError):
    """Абонементом или сертификатом заплатить нельзя — и текст объясняет почему.

    Отдельный тип, а не HTTPException: база не знает про HTTP, а причина отказа
    («истёк», «чужой», «посещения кончились») нужна владельцу дословно.
    """


class SlotTaken(RuntimeError):
    """Слот занят: пересечение с чужой записью или уникальный индекс на начало."""


class Store:
    """Подключение к базе. Схему создают миграции, а не приложение.

    Исключение — SQLite: он живёт только в тестах и локальном запуске, где
    гонять Alembic на каждую временную базу дороже, чем создать таблицы из
    моделей. На Postgres ``create_all`` опасен: он молча создаст таблицы в
    обход истории миграций, и следующий `alembic upgrade` упадёт.
    """

    def __init__(self, url: str, *, create_schema: bool | None = None) -> None:
        self.url = url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, future=True, connect_args=connect_args)
        if create_schema is None:
            create_schema = url.startswith("sqlite")
        if create_schema:
            Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    # --- диалоги ----------------------------------------------------------
    def conversation(self, conversation_id: str | None, *, tenant_id: str, channel: str = "web",
                     external_id: str | None = None) -> Conversation:
        with self.session_factory() as s:
            conv = None
            if conversation_id:
                conv = s.get(Conversation, conversation_id)
                if conv and conv.tenant_id != tenant_id:
                    conv = None  # чужой диалог не подхватываем
            if conv is None and external_id:
                conv = s.scalar(select(Conversation).where(
                    Conversation.external_id == external_id, Conversation.tenant_id == tenant_id))
            if conv is None:
                conv = Conversation(tenant_id=tenant_id, channel=channel, external_id=external_id, state={})
                s.add(conv)
                s.commit()
            return conv

    def history(self, conversation_id: str, limit: int = 30) -> list[dict]:
        with self.session_factory() as s:
            rows = s.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc()).limit(limit)
            ).all()
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        with self.session_factory() as s:
            s.add(Message(conversation_id=conversation_id, role=role, content=content))
            conv = s.get(Conversation, conversation_id)
            if conv:
                conv.updated_at = datetime.now(timezone.utc)
            s.commit()

    def set_state(self, conversation_id: str, state: dict) -> None:
        with self.session_factory() as s:
            conv = s.get(Conversation, conversation_id)
            if conv:
                conv.state = state
                conv.updated_at = datetime.now(timezone.utc)
                s.commit()

    def get_state(self, conversation_id: str) -> dict:
        with self.session_factory() as s:
            conv = s.get(Conversation, conversation_id)
            return dict(conv.state or {}) if conv else {}

    # --- клиенты ----------------------------------------------------------
    def upsert_client(self, *, tenant_id: str, phone: str, name: str = "", lang: str = "ru",
                      consent: bool = True, aliases: tuple[str, ...] | list[str] = ()) -> Client:
        """Карточка по телефону. ``aliases`` — прежние написания того же номера.

        Карточку, заведённую до канонизации ключа (голые цифры «099000101»),
        находим по алиасу и переписываем на канонический номер: миграции для
        этого не нужно, а две карточки на одного человека — нужны ещё меньше.

        Если к этому моменту существуют обе — старая и уже канонизированная, —
        они сливаются в одну. Раньше на такой базе запись падала в 500:
        переименование упиралось в ``uq_client_phone``, а именно так и выглядит
        база салона, работавшего до канонизации.
        """
        now_ts = datetime.now(timezone.utc)
        with self.session_factory() as s:
            keys = _phone_keys(phone, aliases)
            found = list(s.scalars(select(Client)
                                   .where(Client.tenant_id == tenant_id, Client.phone.in_(keys))
                                   .order_by(Client.first_seen_at)).all())
            # Оставляем самую раннюю карточку: у неё длиннее история, и ссылки
            # «мои записи» из прежних сообщений ведут именно на неё.
            client = found[0] if found else None
            for dup in found[1:]:
                self._merge_client(s, keep=client, dup=dup)
            if client is not None and client.phone != phone:
                # Дубли уже удалены — канонический номер свободен.
                s.flush()
                client.phone = phone
            if client is None:
                client = Client(tenant_id=tenant_id, phone=phone, name=name.strip(), lang=lang or "ru",
                                consent=bool(consent), first_seen_at=now_ts, last_seen_at=now_ts)
                s.add(client)
            else:
                if name.strip():
                    client.name = name.strip()
                if lang:
                    client.lang = lang
                client.consent = bool(consent)
                client.last_seen_at = now_ts
                client.updated_at = now_ts
            s.commit()
            return client

    def _merge_client(self, session, *, keep: Client, dup: Client) -> None:
        """Сливает карточку-дубль в основную и удаляет дубль.

        Разъехавшаяся история — это не только неудобство отчётов: по ней
        считаются неявки и чёрный список. Поэтому блокировка при слиянии
        сохраняется (достаточно одной из карточек), а согласие на сообщения —
        наоборот, требуется от обеих: отказ важнее удобства рассылки.
        """
        for model in (Booking, WaitlistEntry, Review, ClientAsset, LoyaltyTransaction):
            session.execute(update(model).where(model.client_id == dup.id)
                            .values(client_id=keep.id))
        keep.name = keep.name or dup.name
        keep.notes = "\n".join(x for x in (keep.notes, dup.notes) if x)
        keep.tags = list(dict.fromkeys([*(keep.tags or []), *(dup.tags or [])]))
        keep.loyalty_balance += dup.loyalty_balance
        keep.blocked = keep.blocked or dup.blocked
        keep.consent = keep.consent and dup.consent
        keep.first_seen_at = min(_to_utc(keep.first_seen_at), _to_utc(dup.first_seen_at))
        keep.last_seen_at = max(_to_utc(keep.last_seen_at), _to_utc(dup.last_seen_at))
        session.delete(dup)
        session.flush()
        # Визиты, неявки и LTV считаются по записям — после переноса пересчёт
        # даёт верные числа сам, складывать счётчики руками незачем.
        self._refresh_client_metrics(session, keep.id)
        log.info("Слиты карточки клиента: %s ← %s (%s)", keep.phone, dup.phone, keep.id)

    def get_client(self, client_id: str, *, tenant_id: str) -> Client | None:
        with self.session_factory() as s:
            client = s.get(Client, client_id)
            return client if client and client.tenant_id == tenant_id else None

    def client_by_phone(self, phone: str, *, tenant_id: str,
                        aliases: tuple[str, ...] | list[str] = ()) -> Client | None:
        keys = _phone_keys(phone, aliases)
        with self.session_factory() as s:
            # Пока дубли не слиты, номер может отвечать двумя карточками. Первой
            # отдаём заблокированную: чёрный список не должен зависеть от того,
            # какая из них нашлась раньше, — иначе он обходится сменой формата.
            return s.scalar(select(Client)
                            .where(Client.tenant_id == tenant_id, Client.phone.in_(keys))
                            .order_by(Client.blocked.desc(), Client.first_seen_at))

    def list_clients(self, *, tenant_id: str, segment: str = "", query: str = "",
                     limit: int = 500) -> list[Client]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=60)
        with self.session_factory() as s:
            stmt = select(Client).where(Client.tenant_id == tenant_id)
            if query:
                needle = f"%{query.strip().lower()}%"
                stmt = stmt.where(or_(func.lower(Client.name).like(needle), Client.phone.like(f"%{query.strip()}%")))
            if segment == "inactive":
                stmt = stmt.where(or_(Client.last_visit_at.is_(None), Client.last_visit_at < cutoff))
            elif segment == "first_time":
                stmt = stmt.where(Client.visits_count <= 1)
            elif segment == "frequent":
                stmt = stmt.where(Client.visits_count >= 3)
            elif segment == "no_show":
                stmt = stmt.where(Client.no_show_count > 0)
            elif segment == "blocked":
                stmt = stmt.where(Client.blocked)
            return list(s.scalars(stmt.order_by(Client.last_seen_at.desc()).limit(limit)).all())

    def patch_client(self, client_id: str, *, tenant_id: str, fields: dict) -> Client | None:
        allowed = {"name", "lang", "notes", "tags", "consent", "blocked"}
        with self.session_factory() as s:
            client = s.get(Client, client_id)
            if not client or client.tenant_id != tenant_id:
                return None
            for key, value in fields.items():
                if key in allowed:
                    setattr(client, key, value)
            client.updated_at = datetime.now(timezone.utc)
            s.commit()
            return client

    def client_bookings(self, client_id: str, *, tenant_id: str) -> list[Booking]:
        with self.session_factory() as s:
            return [_aware_booking(b) for b in s.scalars(select(Booking).where(
                Booking.tenant_id == tenant_id, Booking.client_id == client_id
            ).order_by(Booking.start_at.desc())).all()]

    def _refresh_client_metrics(self, session, client_id: str | None) -> None:
        if not client_id:
            return
        client = session.get(Client, client_id)
        if not client:
            return
        rows = list(session.scalars(select(Booking).where(Booking.client_id == client_id)).all())
        completed = [b for b in rows if b.status == "completed"]
        client.visits_count = len(completed)
        client.no_show_count = sum(1 for b in rows if b.status == "no_show")
        client.last_visit_at = max((b.start_at for b in completed), default=None)
        client.lifetime_value = sum(max(0, int(b.paid_amount or 0)) for b in completed)
        client.updated_at = datetime.now(timezone.utc)

    # --- записи -----------------------------------------------------------
    def busy_intervals(self, master_id: str, start: datetime, end: datetime, *,
                       tenant_id: str, exclude_booking_id: str = "") -> list[tuple[datetime, datetime]]:
        """Занятость мастера. ``exclude_booking_id`` — запись, которую переносим.

        Своё же время при переносе занятым не считается: иначе окно, где запись
        стоит сейчас, исчезало бы из списка, и «оставить время, сменить мастера»
        становилось невозможным.
        """
        start, end = _to_utc(start), _to_utc(end)
        with self.session_factory() as s:
            query = (
                select(Booking).where(
                    Booking.tenant_id == tenant_id,
                    Booking.master_id == master_id,
                    # «Пришёл» мастер отмечает в начале визита, а не в конце:
                    # считать completed свободным временем — значит отдать
                    # клиенту стул, на котором ещё три часа красят волосы.
                    Booking.status.in_(("confirmed", "completed")),
                    Booking.end_at > start,
                    Booking.start_at < end,
                )
            )
            if exclude_booking_id:
                query = query.where(Booking.id != exclude_booking_id)
            rows = s.scalars(query).all()
            # Перерывы — та же занятость: их вычитает `free_slots`, поэтому
            # виджет, агент и панель получают одну и ту же сетку окон.
            blocks = s.scalars(
                select(TimeBlock).where(
                    TimeBlock.tenant_id == tenant_id,
                    TimeBlock.master_id == master_id,
                    TimeBlock.end_at > start,
                    TimeBlock.start_at < end,
                )
            ).all()
        return ([(_aware(b.start_at), _aware(b.end_at)) for b in rows]
                + [(_aware(b.start_at), _aware(b.end_at)) for b in blocks])

    # --- технические перерывы ---------------------------------------------
    def add_time_block(self, *, tenant_id: str, master_id: str, start_at: datetime,
                       end_at: datetime, title: str = "Перерыв") -> TimeBlock:
        with self.session_factory() as s:
            row = TimeBlock(tenant_id=tenant_id, master_id=master_id,
                            start_at=_to_utc(start_at), end_at=_to_utc(end_at),
                            title=title.strip() or "Перерыв")
            s.add(row)
            s.commit()
            row.start_at, row.end_at = _aware(row.start_at), _aware(row.end_at)
            return row

    def time_blocks(self, *, tenant_id: str, start: datetime, end: datetime,
                    master_id: str | None = None) -> list[TimeBlock]:
        """Перерывы в интервале. Границы приводятся к UTC: SQLite сравнивает
        параметр запроса без учёта пояса, и перерыв на вечер терялся."""
        start, end = _to_utc(start), _to_utc(end)
        with self.session_factory() as s:
            query = select(TimeBlock).where(
                TimeBlock.tenant_id == tenant_id,
                TimeBlock.end_at > start, TimeBlock.start_at < end)
            if master_id:
                query = query.where(TimeBlock.master_id == master_id)
            rows = list(s.scalars(query.order_by(TimeBlock.start_at)).all())
        for row in rows:
            row.start_at, row.end_at = _aware(row.start_at), _aware(row.end_at)
        return rows

    def get_time_block(self, block_id: str, *, tenant_id: str) -> TimeBlock | None:
        with self.session_factory() as s:
            row = s.get(TimeBlock, block_id)
            if not row or row.tenant_id != tenant_id:
                return None
            row.start_at, row.end_at = _aware(row.start_at), _aware(row.end_at)
            return row

    def attach_block_event(self, block_id: str, event_id: str | None) -> None:
        with self.session_factory() as s:
            row = s.get(TimeBlock, block_id)
            if row:
                row.calendar_event_id = event_id
                s.commit()

    def drop_time_block(self, block_id: str, *, tenant_id: str) -> TimeBlock | None:
        with self.session_factory() as s:
            row = s.get(TimeBlock, block_id)
            if not row or row.tenant_id != tenant_id:
                return None
            s.delete(row)
            s.commit()
            return row

    def session_seats(self, master_id: str, service_id: str, start: datetime, *,
                      tenant_id: str) -> int:
        """Сколько мест общей сессии уже занято. Для обычной услуги всегда 0."""
        start = _to_utc(start)
        with self.session_factory() as s:
            taken = s.scalar(
                select(func.coalesce(func.sum(Booking.group_size), 0)).where(
                    Booking.tenant_id == tenant_id, Booking.master_id == master_id,
                    Booking.service_id == service_id, Booking.start_at == start,
                    Booking.shared.is_(True),
                    Booking.status.in_(("confirmed", "completed")),
                ))
            return int(taken or 0)

    def find_by_idempotency(self, key: str, *, tenant_id: str | None = None) -> Booking | None:
        if not key:
            return None
        with self.session_factory() as s:
            query = select(Booking).where(Booking.idempotency_key == key)
            if tenant_id:
                query = query.where(Booking.tenant_id == tenant_id)
            return _aware_booking(s.scalar(query))

    def overlapping(self, master_id: str, start: datetime, end: datetime, *,
                    tenant_id: str, exclude_id: str | None = None) -> list[Booking]:
        """Активные записи мастера, пересекающиеся с интервалом [start, end).

        Пересечение, а не совпадение начала: окрашивание на три часа занимает
        три часа, и стрижка через полчаса после его начала — то же двойное
        бронирование, только уникальный индекс по началу его не видит.
        """
        start, end = _to_utc(start), _to_utc(end)
        with self.session_factory() as s:
            query = select(Booking).where(
                Booking.tenant_id == tenant_id,
                Booking.master_id == master_id,
                Booking.status.in_(("confirmed", "completed")),
                Booking.end_at > start,
                Booking.start_at < end,
            )
            if exclude_id:
                query = query.where(Booking.id != exclude_id)
            return [_aware_booking(b) for b in s.scalars(query.order_by(Booking.start_at)).all()]

    def create_booking(self, **fields) -> Booking:
        for key in ("start_at", "end_at"):
            if fields.get(key):
                fields[key] = _to_utc(fields[key])
        with self.session_factory() as s:
            # Проверка пересечения в той же транзакции, что и вставка. От гонки
            # двух одновременных запросов защищает уже база: на Postgres —
            # EXCLUDE-ограничение, на любом движке — уникальный индекс по началу.
            clash = list(s.scalars(
                select(Booking).where(
                    Booking.tenant_id == fields.get("tenant_id"),
                    Booking.master_id == fields.get("master_id"),
                    Booking.status.in_(("confirmed", "completed")),
                    Booking.end_at > fields["start_at"],
                    Booking.start_at < fields["end_at"],
                )
            ).all())
            # Место в общей сессии не конфликтует с такими же местами в ней же:
            # курс на десять человек — это десять записей на одно время, и
            # запрещать их значит продать один билет вместо десяти.
            if clash and fields.get("shared"):
                # `_aware`: SQLite отдаёт время без пояса, и наивное значение
                # никогда не равно приведённому к UTC — сессия выглядела бы
                # чужой записью, а места так и не продавались.
                same = all(b.shared and b.service_id == fields.get("service_id")
                           and _aware(b.start_at) == fields["start_at"] for b in clash)
                if same:
                    clash = []
            if clash:
                raise SlotTaken(f"пересечение с записью {clash[0].id}")
            booking = Booking(**fields)
            s.add(booking)
            try:
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise SlotTaken(str(exc)) from exc
            return _aware_booking(booking)

    def attach_event(self, booking_id: str, event_id: str | None, html_link: str | None) -> None:
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if booking:
                booking.event_id, booking.html_link = event_id, html_link
                s.commit()

    def drop_booking(self, booking_id: str) -> None:
        """Откат: календарь отказал — запись не должна остаться висеть."""
        with self.session_factory() as s:
            s.execute(delete(Booking).where(Booking.id == booking_id))
            s.commit()

    def cancel_booking(self, booking_id: str) -> Booking | None:
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if booking:
                booking.status = "cancelled"
                s.commit()
            return booking

    def get_booking(self, booking_id: str, *, tenant_id: str | None = None) -> Booking | None:
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if booking and tenant_id and booking.tenant_id != tenant_id:
                return None  # чужую запись не отдаём и не трогаем
            return _aware_booking(booking)

    def bookings_by_phone(self, phone: str, since: datetime, *, tenant_id: str,
                          aliases: tuple[str, ...] | list[str] = ()) -> list[Booking]:
        since = _to_utc(since)
        keys = _phone_keys(phone, aliases)
        with self.session_factory() as s:
            client = s.scalar(select(Client.id).where(Client.tenant_id == tenant_id,
                                                      Client.phone.in_(keys)))
            return list(s.scalars(
                select(Booking).where(
                    Booking.tenant_id == tenant_id,
                    or_(Booking.client_id == client, Booking.phone.in_(keys)) if client
                    else Booking.phone.in_(keys),
                    Booking.status == "confirmed",
                    Booking.created_at >= since,
                )
            ).all())

    def upcoming_by_phone(self, phone: str, now: datetime, *, tenant_id: str,
                          aliases: tuple[str, ...] | list[str] = ()) -> list[Booking]:
        now = _to_utc(now)
        keys = _phone_keys(phone, aliases)
        with self.session_factory() as s:
            client = s.scalar(select(Client.id).where(Client.tenant_id == tenant_id,
                                                      Client.phone.in_(keys)))
            return list(s.scalars(
                select(Booking).where(
                    Booking.tenant_id == tenant_id,
                    or_(Booking.client_id == client, Booking.phone.in_(keys)) if client
                    else Booking.phone.in_(keys),
                    Booking.status == "confirmed",
                    Booking.start_at >= now,
                ).order_by(Booking.start_at)
            ).all())

    # --- уведомления ------------------------------------------------------
    def set_booking_status(self, booking_id: str, status: str, *, tenant_id: str) -> Booking | None:
        """Отметка «пришёл / не пришёл / отменено» — основа учёта неявок."""
        if status not in BOOKING_STATUSES:
            raise ValueError(f"Неизвестный статус визита: {status}")
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if not booking or booking.tenant_id != tenant_id:
                return None
            booking.status = status
            self._refresh_client_metrics(s, booking.client_id)
            s.commit()
            return _aware_booking(booking)

    def mark_client_confirmed(self, booking_id: str, *, tenant_id: str | None = None) -> Booking | None:
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if booking and (not tenant_id or booking.tenant_id == tenant_id):
                booking.confirmed_by_client = True
                s.commit()
                return _aware_booking(booking)
            return None

    def reschedule_booking(self, booking_id: str, *, tenant_id: str, master_id: str,
                           start_at: datetime, end_at: datetime) -> Booking | None:
        start_at, end_at = _to_utc(start_at), _to_utc(end_at)
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if not booking or booking.tenant_id != tenant_id:
                return None
            clash = s.scalar(select(Booking.id).where(
                Booking.tenant_id == tenant_id, Booking.master_id == master_id,
                Booking.id != booking_id, Booking.status.in_(("confirmed", "completed")),
                Booking.end_at > start_at, Booking.start_at < end_at))
            if clash:
                raise SlotTaken(f"пересечение с записью {clash}")
            booking.master_id, booking.start_at, booking.end_at = master_id, start_at, end_at
            booking.confirmed_by_client = False
            try:
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise SlotTaken(str(exc)) from exc
            return _aware_booking(booking)

    def set_payment(self, booking_id: str, *, tenant_id: str, paid_amount: int,
                    payment_method: str, discount_amount: int = 0) -> Booking | None:
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if not booking or booking.tenant_id != tenant_id:
                return None
            booking.paid_amount = max(0, int(paid_amount))
            booking.payment_method = payment_method
            booking.discount_amount = max(0, int(discount_amount))
            self._refresh_client_metrics(s, booking.client_id)
            s.commit()
            return _aware_booking(booking)

    def pay_with_asset(self, booking_id: str, *, tenant_id: str, asset_id: str,
                       discount_amount: int = 0) -> Booking:
        """Оплата визита абонементом или сертификатом. Списание — в той же транзакции.

        Деньги признаются в момент продажи абонемента, а не в момент, когда его
        тратят: иначе одна и та же сумма попадает в выручку дважды. Поэтому
        `paid_amount` у такого визита ноль, а сколько услуг оказано по
        абонементам, видно по `price_amount` и способу оплаты.

        Частичная оплата сертификатом не поддерживается намеренно: у записи один
        способ оплаты, и «половина сертификатом, половина наличными» потребует
        отдельной таблицы платежей, а не ещё одного поля.
        """
        with self.session_factory() as s:
            booking = s.get(Booking, booking_id)
            if not booking or booking.tenant_id != tenant_id:
                raise AssetProblem("Запись не найдена")
            asset = s.get(ClientAsset, asset_id)
            if not asset or asset.tenant_id != tenant_id:
                raise AssetProblem("Абонемент не найден")

            # Повторный запрос тем же активом ничего не списывает: панель могла
            # отправить его дважды, а посещение у клиента одно.
            if booking.asset_id == asset.id:
                return _aware_booking(booking)
            if booking.asset_id:
                raise AssetProblem("Визит уже оплачен другим абонементом")
            if asset.status != "active":
                raise AssetProblem(f"Абонемент {asset.code} уже не действует")
            if asset.expires_at and _aware(asset.expires_at) < datetime.now(timezone.utc):
                raise AssetProblem(f"Срок действия {asset.code} истёк")
            # Сертификат без владельца — на предъявителя, его принимаем у любого.
            if asset.client_id and booking.client_id and asset.client_id != booking.client_id:
                raise AssetProblem("Абонемент принадлежит другому клиенту")

            price = max(0, int(booking.price_amount or 0) - max(0, int(discount_amount)))
            if asset.kind == "membership":
                if asset.remaining_uses <= 0:
                    raise AssetProblem(f"В абонементе {asset.code} не осталось посещений")
                asset.remaining_uses -= 1
            else:
                if asset.balance_amount < price:
                    raise AssetProblem(f"На сертификате {asset.code} осталось "
                                       f"{asset.balance_amount}, а визит стоит {price}")
                asset.balance_amount -= price
            if asset.remaining_uses <= 0 and asset.balance_amount <= 0:
                asset.status = "spent"

            booking.asset_id = asset.id
            booking.payment_method = "membership" if asset.kind == "membership" else "certificate"
            booking.paid_amount = 0
            booking.discount_amount = max(0, int(discount_amount))
            self._refresh_client_metrics(s, booking.client_id)
            s.commit()
            return _aware_booking(booking)

    def no_show_count(self, phone: str, *, tenant_id: str, since: datetime,
                      aliases: tuple[str, ...] | list[str] = ()) -> int:
        keys = _phone_keys(phone, aliases)
        with self.session_factory() as s:
            client = s.scalar(select(Client.id).where(Client.tenant_id == tenant_id,
                                                      Client.phone.in_(keys)))
            return int(s.scalar(
                select(func.count()).select_from(Booking).where(
                    Booking.tenant_id == tenant_id,
                    or_(Booking.client_id == client, Booking.phone.in_(keys)) if client
                    else Booking.phone.in_(keys),
                    Booking.status == "no_show",
                    Booking.start_at >= _to_utc(since),
                )
            ) or 0)

    # --- лист ожидания, отзывы и кампании --------------------------------
    def add_waitlist(self, **fields) -> WaitlistEntry:
        with self.session_factory() as s:
            row = WaitlistEntry(**fields)
            s.add(row); s.commit(); return row

    def list_waitlist(self, *, tenant_id: str, status: str = "waiting") -> list[WaitlistEntry]:
        with self.session_factory() as s:
            stmt = select(WaitlistEntry).where(WaitlistEntry.tenant_id == tenant_id)
            if status:
                stmt = stmt.where(WaitlistEntry.status == status)
            return list(s.scalars(stmt.order_by(WaitlistEntry.created_at)).all())

    def create_review(self, *, tenant_id: str, booking_id: str, client_id: str | None) -> Review | None:
        with self.session_factory() as s:
            row = Review(tenant_id=tenant_id, booking_id=booking_id, client_id=client_id)
            s.add(row)
            try: s.commit()
            except IntegrityError: s.rollback(); return None
            return row

    def available_resource(self, *, tenant_id: str, kind: str, start: datetime,
                           end: datetime, location_id: str | None = None) -> Resource | None:
        """Первый свободный ресурс нужного типа на всём интервале записи."""
        start, end = _to_utc(start), _to_utc(end)
        with self.session_factory() as session:
            query = select(Resource).where(
                Resource.tenant_id == tenant_id, Resource.kind == kind, Resource.active.is_(True))
            if location_id:
                query = query.where(Resource.location_id == location_id)
            resources = list(session.scalars(query.order_by(Resource.name)).all())
            for resource in resources:
                occupied = session.scalar(select(func.count()).select_from(BookingResource).join(
                    Booking, Booking.id == BookingResource.booking_id).where(
                        BookingResource.resource_id == resource.id,
                        Booking.status == "confirmed", Booking.start_at < end, Booking.end_at > start))
                if int(occupied or 0) < max(1, int(resource.capacity or 1)):
                    session.expunge(resource)
                    return resource
        return None

    def resource_kind_exists(self, *, tenant_id: str, kind: str,
                             location_id: str | None = None) -> bool:
        with self.session_factory() as session:
            query = select(func.count()).select_from(Resource).where(
                Resource.tenant_id == tenant_id, Resource.kind == kind, Resource.active.is_(True))
            if location_id:
                query = query.where(Resource.location_id == location_id)
            return bool(session.scalar(query))

    def assign_resource(self, booking_id: str, resource_id: str) -> None:
        with self.session_factory() as session:
            session.add(BookingResource(booking_id=booking_id, resource_id=resource_id))
            session.commit()

    def change_loyalty(self, *, tenant_id: str, client_id: str, points: int,
                       reason: str, booking_id: str | None = None,
                       idempotent: bool = False) -> int:
        with self.session_factory() as session:
            client = session.get(Client, client_id)
            if not client or client.tenant_id != tenant_id:
                raise ValueError("Клиент не найден")
            if idempotent and booking_id and session.scalar(select(LoyaltyTransaction.id).where(
                    LoyaltyTransaction.tenant_id == tenant_id,
                    LoyaltyTransaction.booking_id == booking_id,
                    LoyaltyTransaction.reason == reason)):
                return client.loyalty_balance
            if client.loyalty_balance + points < 0:
                raise ValueError("Недостаточно баллов")
            client.loyalty_balance += points
            session.add(LoyaltyTransaction(tenant_id=tenant_id, client_id=client_id,
                                           booking_id=booking_id, points=points, reason=reason))
            session.commit()
            return client.loyalty_balance

    def submit_review(self, review_id: str, *, score: int, feedback: str) -> Review | None:
        with self.session_factory() as s:
            row = s.get(Review, review_id)
            if not row: return None
            row.score, row.feedback = score, feedback.strip()
            row.status = "public" if score == 5 else "private"
            s.commit(); return row

    def create_campaign(self, **fields) -> Campaign:
        with self.session_factory() as s:
            row = Campaign(**fields); s.add(row); s.commit(); return row

    def list_campaigns(self, *, tenant_id: str) -> list[Campaign]:
        with self.session_factory() as s:
            return list(s.scalars(select(Campaign).where(Campaign.tenant_id == tenant_id)
                                  .order_by(Campaign.created_at.desc())).all())

    # --- потребление по тарифу --------------------------------------------
    def bump_usage(self, tenant_id: str, metric: str, period: str, amount: int = 1) -> int:
        """Увеличивает счётчик и возвращает новое значение."""
        with self.session_factory() as s:
            row = s.scalar(select(UsageCounter).where(
                UsageCounter.tenant_id == tenant_id,
                UsageCounter.period == period,
                UsageCounter.metric == metric,
            ))
            if row is None:
                row = UsageCounter(tenant_id=tenant_id, period=period, metric=metric, count=0)
                s.add(row)
            row.count += amount
            row.updated_at = datetime.now(timezone.utc)
            try:
                s.commit()
            except IntegrityError:  # гонка двух запросов — читаем чужую строку
                s.rollback()
                return self.bump_usage(tenant_id, metric, period, amount)
            return row.count

    def usage(self, period: str, *, tenant_id: str | None = None) -> dict[str, int]:
        """Потребление за месяц: по одному бизнесу или суммарно по всем."""
        with self.session_factory() as s:
            query = select(UsageCounter.metric, func.sum(UsageCounter.count)).where(
                UsageCounter.period == period)
            if tenant_id:
                query = query.where(UsageCounter.tenant_id == tenant_id)
            rows = s.execute(query.group_by(UsageCounter.metric)).all()
        return {metric: int(total or 0) for metric, total in rows}

    def usage_by_tenant(self, period: str) -> dict[str, dict[str, int]]:
        with self.session_factory() as s:
            rows = s.execute(
                select(UsageCounter.tenant_id, UsageCounter.metric, func.sum(UsageCounter.count))
                .where(UsageCounter.period == period)
                .group_by(UsageCounter.tenant_id, UsageCounter.metric)
            ).all()
        out: dict[str, dict[str, int]] = {}
        for tenant_id, metric, total in rows:
            out.setdefault(tenant_id, {})[metric] = int(total or 0)
        return out

    # --- статистика ---------------------------------------------------------
    def booking_stats(self, *, tenant_id: str, since: datetime) -> dict:
        since = _to_utc(since)
        with self.session_factory() as s:
            by_status = dict(s.execute(
                select(Booking.status, func.count()).where(
                    Booking.tenant_id == tenant_id, Booking.created_at >= since)
                .group_by(Booking.status)
            ).all())
            from_chat = int(s.scalar(
                select(func.count()).select_from(Booking).where(
                    Booking.tenant_id == tenant_id, Booking.created_at >= since,
                    Booking.conversation_id.is_not(None))
            ) or 0)
            conversations = int(s.scalar(
                select(func.count()).select_from(Conversation).where(
                    Conversation.tenant_id == tenant_id, Conversation.created_at >= since)
            ) or 0)
            with_booking = int(s.scalar(
                select(func.count(func.distinct(Booking.conversation_id))).where(
                    Booking.tenant_id == tenant_id, Booking.created_at >= since,
                    Booking.conversation_id.is_not(None))
            ) or 0)
            top_services = s.execute(
                select(Booking.service_id, func.count()).where(
                    Booking.tenant_id == tenant_id, Booking.created_at >= since,
                    Booking.status != "cancelled")
                .group_by(Booking.service_id).order_by(func.count().desc()).limit(10)
            ).all()
            top_masters = s.execute(
                select(Booking.master_id, func.count()).where(
                    Booking.tenant_id == tenant_id, Booking.created_at >= since,
                    Booking.status != "cancelled")
                .group_by(Booking.master_id).order_by(func.count().desc()).limit(10)
            ).all()
        total = sum(int(v) for v in by_status.values())
        return {
            "conversations": conversations,
            "conversationsWithBooking": with_booking,
            "bookings": total,
            "fromChat": from_chat,
            "confirmed": int(by_status.get("confirmed", 0)),
            "completed": int(by_status.get("completed", 0)),
            "cancelled": int(by_status.get("cancelled", 0)),
            "noShow": int(by_status.get("no_show", 0)),
            "byService": [{"id": sid, "count": int(c)} for sid, c in top_services],
            "byMaster": [{"id": mid, "count": int(c)} for mid, c in top_masters],
        }

    def daily_bookings(self, *, tenant_id: str, since: datetime) -> list[dict]:
        """Записи по дням — для простого графика в панели."""
        since = _to_utc(since)
        with self.session_factory() as s:
            rows = s.execute(
                select(func.date(Booking.created_at), func.count()).where(
                    Booking.tenant_id == tenant_id, Booking.created_at >= since)
                .group_by(func.date(Booking.created_at))
                .order_by(func.date(Booking.created_at))
            ).all()
        return [{"date": str(day), "count": int(count)} for day, count in rows]

    # --- диалоги для админки -----------------------------------------------
    def list_conversations(self, *, tenant_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """Прошедшие диалоги: когда, сколько сообщений, чем закончились."""
        with self.session_factory() as s:
            convs = list(s.scalars(
                select(Conversation).where(Conversation.tenant_id == tenant_id)
                .order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
            ).all())
            if not convs:
                return []
            ids = [c.id for c in convs]
            counts = dict(s.execute(
                select(Message.conversation_id, func.count())
                .where(Message.conversation_id.in_(ids)).group_by(Message.conversation_id)
            ).all())
            firsts = dict(s.execute(
                select(Message.conversation_id, func.min(Message.id))
                .where(Message.conversation_id.in_(ids), Message.role == "user")
                .group_by(Message.conversation_id)
            ).all())
            first_texts = dict(s.execute(
                select(Message.conversation_id, Message.content)
                .where(Message.id.in_([v for v in firsts.values() if v]))
            ).all())
            booked = dict(s.execute(
                select(Booking.conversation_id, func.count())
                .where(Booking.conversation_id.in_(ids), Booking.tenant_id == tenant_id)
                .group_by(Booking.conversation_id)
            ).all())
        return [
            {
                "id": c.id,
                "channel": c.channel,
                "startedAt": _aware(c.created_at).isoformat(),
                "updatedAt": _aware(c.updated_at).isoformat(),
                "messages": int(counts.get(c.id, 0)),
                "firstMessage": (first_texts.get(c.id) or "")[:120],
                "bookings": int(booked.get(c.id, 0)),
            }
            for c in convs
        ]

    def conversation_detail(self, conversation_id: str, *, tenant_id: str) -> dict | None:
        with self.session_factory() as s:
            conv = s.get(Conversation, conversation_id)
            if not conv or conv.tenant_id != tenant_id:
                return None
            messages = list(s.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.id)
            ).all())
            bookings = list(s.scalars(
                select(Booking).where(Booking.conversation_id == conversation_id)
            ).all())
        return {
            "id": conv.id,
            "channel": conv.channel,
            "startedAt": _aware(conv.created_at).isoformat(),
            "messages": [
                {"role": m.role, "content": m.content, "at": _aware(m.created_at).isoformat()}
                for m in messages
            ],
            # Запись отдаём целиком: карточка в «Диалогах» показывает то же,
            # что и раздел «Записи», — иначе владельцу приходится искать
            # телефон и комментарий клиента в другом экране.
            "bookings": [
                {
                    "id": b.id,
                    "channel": conv.channel,
                    "start": _aware(b.start_at).isoformat(),
                    "end": _aware(b.end_at).isoformat(),
                    "status": b.status,
                    "service": b.service_id,
                    "master": b.master_id,
                    "client": b.client_name,
                    "phone": b.phone,
                    "comment": b.comment or "",
                    "eventId": b.event_id,
                    "htmlLink": b.html_link,
                    "createdAt": _aware(b.created_at).isoformat(),
                    "requiresConfirmation": bool(b.requires_confirmation),
                    "confirmedByClient": bool(b.confirmed_by_client),
                    "notifyConsent": bool(b.notify_consent),
                }
                for b in bookings
            ],
        }

    def day_bookings(self, *, tenant_id: str, start: datetime, end: datetime) -> list[Booking]:
        """Все записи бизнеса в интервале — для экрана расписания."""
        start, end = _to_utc(start), _to_utc(end)
        with self.session_factory() as s:
            # Через `_aware_booking`, как и остальные выборки: без этого SQLite
            # отдаёт naive-время, `astimezone()` в расписании принимает его за
            # локальное время машины, и запись на 11:00 показывалась как 14:00
            # на стенде в UTC-3.
            return [_aware_booking(b) for b in s.scalars(
                select(Booking).where(
                    Booking.tenant_id == tenant_id,
                    Booking.status != "cancelled",
                    Booking.end_at > start,
                    Booking.start_at < end,
                ).order_by(Booking.start_at)
            ).all()]

    def enqueue_notification(self, **fields) -> Notification | None:
        """Повторная постановка задачи с тем же именем ничего не создаёт.

        Идемпотентность обеспечивает уникальный индекс, а не проверка перед
        вставкой: два воркера могут планировать одну запись одновременно.
        """
        for key in ("scheduled_at", "booking_start_at"):
            if fields.get(key):
                fields[key] = _to_utc(fields[key])
        with self.session_factory() as s:
            task = Notification(**fields)
            s.add(task)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return None
            return task

    def claim_due_notifications(self, now_ts: datetime, limit: int = 50) -> list[Notification]:
        """Забирает готовые к отправке задачи, помечая их 'sending'.

        Захват идёт по одной строке с проверкой прежнего статуса, поэтому
        параллельный воркер ту же задачу уже не возьмёт — без блокировок таблицы.
        """
        now_ts = _to_utc(now_ts)
        claimed: list[Notification] = []
        with self.session_factory() as s:
            due = s.scalars(
                select(Notification)
                .where(Notification.status == "scheduled", Notification.scheduled_at <= now_ts)
                .order_by(Notification.scheduled_at).limit(limit)
            ).all()
            for task in due:
                result = s.execute(
                    update(Notification)
                    .where(Notification.id == task.id, Notification.status == "scheduled")
                    .values(status="sending", updated_at=datetime.now(timezone.utc))
                )
                if result.rowcount:
                    s.refresh(task)
                    claimed.append(task)
            s.commit()
        return claimed

    def patch_notification(self, notification_id: str, patch: dict) -> Notification | None:
        with self.session_factory() as s:
            task = s.scalar(select(Notification).where(Notification.notification_id == notification_id))
            if not task:
                return None
            for key, value in patch.items():
                setattr(task, key, _to_utc(value) if isinstance(value, datetime) else value)
            if "updated_at" not in patch:
                task.updated_at = datetime.now(timezone.utc)
            s.commit()
            return task

    def cancel_notifications(self, booking_id: str, reason: str) -> int:
        """Отмена или перенос записи — все ещё не отправленные задачи снимаются."""
        with self.session_factory() as s:
            result = s.execute(
                update(Notification)
                .where(Notification.booking_id == booking_id, Notification.status == "scheduled")
                .values(status="cancelled", error=reason, updated_at=datetime.now(timezone.utc))
            )
            s.commit()
            return result.rowcount or 0

    def notification_by_message_id(self, provider_message_id: str) -> Notification | None:
        if not provider_message_id:
            return None
        with self.session_factory() as s:
            return s.scalar(select(Notification)
                            .where(Notification.provider_message_id == provider_message_id))

    def list_notifications(self, *, tenant_id: str | None = None, booking_id: str | None = None,
                           limit: int = 100) -> list[Notification]:
        with self.session_factory() as s:
            query = select(Notification).order_by(Notification.scheduled_at.desc()).limit(limit)
            if tenant_id:
                query = query.where(Notification.tenant_id == tenant_id)
            if booking_id:
                query = query.where(Notification.booking_id == booking_id)
            return list(s.scalars(query).all())

    def recover_stuck_notifications(self, older_than_minutes: int = 5) -> int:
        """Задача, захваченная упавшим процессом, иначе осталась бы в 'sending' навсегда.

        Возвращаем такие в очередь: перед отправкой всё равно будет перепроверка,
        так что повторная попытка безопаснее потерянного напоминания.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        with self.session_factory() as s:
            result = s.execute(
                update(Notification)
                .where(Notification.status == "sending", Notification.updated_at < cutoff)
                .values(status="scheduled", updated_at=datetime.now(timezone.utc))
            )
            s.commit()
            return result.rowcount or 0

    def staff_recipients(self) -> list[dict]:
        """Свои, кому идут уведомления о записях: активные, с привязанным чатом.

        Список людей один — тот же, что и вход в панель. Отдельный справочник
        контактов неизбежно разъехался бы с ним: отключённый администратор
        продолжал бы получать записи салона.
        """
        with self.session_factory() as s:
            rows = s.scalars(
                select(AdminUser).where(
                    AdminUser.is_active,
                    AdminUser.notify_new_booking,
                    AdminUser.telegram_chat_id != "",
                ).order_by(AdminUser.id)
            ).all()
            return [{"id": u.id, "name": u.name or u.email, "role": u.role,
                     "chatId": u.telegram_chat_id} for u in rows]

    # --- секреты ----------------------------------------------------------
    def get_secret(self, tenant_id: str, key: str) -> str:
        with self.session_factory() as s:
            row = s.scalar(select(TenantSecret)
                           .where(TenantSecret.tenant_id == tenant_id, TenantSecret.key == key))
            return row.value if row else ""

    def set_secret(self, tenant_id: str, key: str, value: str) -> None:
        with self.session_factory() as s:
            row = s.scalar(select(TenantSecret)
                           .where(TenantSecret.tenant_id == tenant_id, TenantSecret.key == key))
            if not value:
                if row:
                    s.delete(row)
                    s.commit()
                return
            if row:
                row.value, row.updated_at = value, datetime.now(timezone.utc)
            else:
                s.add(TenantSecret(tenant_id=tenant_id, key=key, value=value))
            s.commit()

    def drop_secrets(self, tenant_id: str) -> None:
        with self.session_factory() as s:
            s.execute(delete(TenantSecret).where(TenantSecret.tenant_id == tenant_id))
            s.commit()

    # --- паспорт хранилища ------------------------------------------------
    def describe(self, *, tenant_id: str | None = None) -> dict:
        """Что за база под сервисом — для экрана «База данных» в админке.

        Наружу отдаём адрес и объём, но никогда пароль: строка подключения —
        секрет уровня сервера, а владельцу салона от неё всё равно нет пользы.
        Провайдер узнаётся по хосту: подключённый Supabase должен выглядеть
        подключённым, а не «какой-то внешней базой».
        """
        url = make_url(self.url)
        sqlite = url.get_backend_name() == "sqlite"
        info: dict = {
            "kind": "sqlite" if sqlite else "postgres",
            "host": url.host or ("файл" if sqlite else ""),
            "port": url.port or 0,
            "name": (url.database or "").split("/")[-1],
            "provider": _provider(url.host or "", sqlite=sqlite),
            "version": "",
            "sizeBytes": 0,
            "counts": {},
            "ok": False,
            "error": "",
        }
        try:
            with self.session_factory() as s:
                if sqlite:
                    info["version"] = "SQLite " + (s.scalar(text("select sqlite_version()")) or "")
                    path = Path(url.database or "")
                    info["sizeBytes"] = path.stat().st_size if path.exists() else 0
                else:
                    raw = s.scalar(text("select version()")) or ""
                    info["version"] = " ".join(raw.split()[:2])  # «PostgreSQL 16.3», без сборки и ОС
                    info["sizeBytes"] = int(s.scalar(text("select pg_database_size(current_database())")) or 0)
                info["counts"] = {
                    "bookings": self._count(s, Booking, tenant_id),
                    "conversations": self._count(s, Conversation, tenant_id),
                    "notifications": self._count(s, Notification, tenant_id),
                }
                info["ok"] = True
        except Exception as exc:  # noqa: BLE001 — экран статуса не должен падать вместе с базой
            info["error"] = str(exc).splitlines()[0][:200]
        return info

    @staticmethod
    def _count(session, model, tenant_id: str | None) -> int:
        query = select(func.count()).select_from(model)
        if tenant_id:
            query = query.where(model.tenant_id == tenant_id)
        return int(session.scalar(query) or 0)

    def selftest(self) -> dict:
        """Круговая проверка: соединиться, записать, прочитать, откатить.

        «База отвечает на SELECT 1» — ещё не «база работает»: том может быть
        смонтирован только на чтение, а место на диске — кончиться. Пишем во
        временную таблицу и откатываем: настоящая запись без следа в данных.
        """
        started = time.perf_counter()
        try:
            with self.session_factory() as s:
                s.execute(text("create temporary table _demo_salon_selftest (n integer)"))
                s.execute(text("insert into _demo_salon_selftest (n) values (1)"))
                value = s.scalar(text("select n from _demo_salon_selftest"))
                s.rollback()
            if value != 1:
                return {"ok": False, "error": "База вернула не то, что записали", "latencyMs": 0}
        except Exception as exc:  # noqa: BLE001 — причину показываем в админке
            return {"ok": False, "error": str(exc).splitlines()[0][:200], "latencyMs": 0}
        return {"ok": True, "error": "", "latencyMs": round((time.perf_counter() - started) * 1000)}

    def purge_old_conversations(self, retention_days: int, *, tenant_id: str | None = None) -> int:
        """Срок хранения диалогов из настроек — данные не живут вечно."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with self.session_factory() as s:
            query = select(Conversation.id).where(Conversation.updated_at < cutoff)
            if tenant_id:
                query = query.where(Conversation.tenant_id == tenant_id)
            ids = list(s.scalars(query).all())
            if ids:
                s.execute(delete(Message).where(Message.conversation_id.in_(ids)))
                s.execute(delete(Conversation).where(Conversation.id.in_(ids)))
                s.commit()
            return len(ids)


def _aware(dt: datetime) -> datetime:
    """SQLite отдаёт naive datetime — возвращаем в UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Хост базы → провайдер. Внутренний `db` — это сервис из docker-compose рядом с
# API: для владельца салона это «база сервиса», настраивать её не нужно.
_PROVIDERS = [
    ("supabase.co", "Supabase"), ("supabase.com", "Supabase"), ("neon.tech", "Neon"),
    ("render.com", "Render"), ("railway.app", "Railway"), ("rds.amazonaws.com", "Amazon RDS"),
    ("cockroachlabs.cloud", "CockroachDB"), ("aivencloud.com", "Aiven"),
]


def _provider(host: str, *, sqlite: bool = False) -> str:
    if sqlite:
        return "file"
    low = host.lower()
    for needle, name in _PROVIDERS:
        if needle in low:
            return name
    # Только короткое имя сервиса из compose. `db.example.com` — чужая машина:
    # объявив её «базой сервиса», админка пообещала бы бэкапы, которых нет.
    if low in ("db", "postgres", "localhost", "127.0.0.1", ""):
        return "service"
    return "external"


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL не задан, а падать на SQLite в проде нельзя."""


def _normalize_url(url: str) -> str:
    """`postgres://` из панелей хостинга SQLAlchemy не понимает — приводим к psycopg."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def build_store(database: dict | None = None) -> Store:
    """Единственное хранилище — Postgres из ``DATABASE_URL``.

    Записи и диалоги в JSON-файлах не живут: их нельзя ни забэкапить целиком, ни
    открыть двумя процессами (API и воркер). SQLite остаётся для тестов и включается
    только явным ``DB_ALLOW_SQLITE=1`` — молча уехать на файл в проде хуже отказа.
    """
    url = (os.getenv("DATABASE_URL") or (database or {}).get("url") or "").strip()
    if url:
        return Store(_normalize_url(url))

    if os.getenv("DB_ALLOW_SQLITE") == "1":
        data_dir = ROOT / "data"
        data_dir.mkdir(exist_ok=True)
        log.warning("DATABASE_URL не задан — работаем на локальном SQLite (только разработка)")
        return Store(f"sqlite:///{data_dir / 'booking-v2.db'}")

    raise DatabaseNotConfigured(
        "DATABASE_URL не задан. Укажите строку подключения к Postgres в окружении "
        "сервера или выставьте DB_ALLOW_SQLITE=1 для локального запуска."
    )
