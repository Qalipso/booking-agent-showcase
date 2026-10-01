"""Живые сервисы по бизнесам.

База одна на всех (изоляция по tenant_id), а календарь, инструменты и агент —
свои у каждого бизнеса, потому что у них разные ключи и настройки.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .agent import Agent
from .calendar_service import CalendarService
from .db import Store, build_store
from .notify import NotificationService
from .policies import RateLimiter, install_pii_filter
from .secretstore import SecretStore
from .tenants import Tenant, bind_secret_store, registry
from .tools import BookingTools

log = logging.getLogger("app")


@dataclass
class TenantRuntime:
    tenant: Tenant
    calendar: CalendarService
    tools: BookingTools
    agent: Agent


class Runtime:
    """Общие сервисы процесса. База подключается лениво — при первом обращении.

    Ленивость здесь не оптимизация: импорт модуля не должен падать из-за
    незаданного DATABASE_URL, иначе не поднимется даже /health с понятной ошибкой.
    """

    def __init__(self) -> None:
        self.limiter = RateLimiter()
        self._store: Store | None = None
        self._secrets: SecretStore | None = None
        self._notifications: NotificationService | None = None
        self._by_tenant: dict[str, TenantRuntime] = {}
        self._apply_log_policy(True)

    @property
    def store(self) -> Store:
        if self._store is None:
            # База одна на всех: и API, и воркер уведомлений смотрят в неё же.
            self.bind(build_store())
        return self._store

    @property
    def secrets(self) -> SecretStore:
        self.store  # noqa: B018 — гарантирует, что хранилище поднято
        return self._secrets

    @property
    def notifications(self) -> NotificationService:
        self.store  # noqa: B018
        return self._notifications

    def bind(self, store: Store) -> None:
        """Подключает хранилище. Тесты подставляют сюда свой SQLite."""
        self._store = store
        self._secrets = SecretStore(store)
        bind_secret_store(self._secrets)
        self._notifications = NotificationService(store)
        self._by_tenant.clear()

    def for_tenant(self, slug: str) -> TenantRuntime:
        if slug not in self._by_tenant:
            self._by_tenant[slug] = self._build(registry.get(slug))
        return self._by_tenant[slug]

    def _build(self, tenant: Tenant) -> TenantRuntime:
        store = self.store  # инициализирует secrets и notifications при первом вызове
        calendar = CalendarService(tenant, store)
        tools = BookingTools(tenant, store, calendar, self.limiter, self.notifications)
        agent = Agent(tenant, tools)
        self._apply_log_policy(bool(tenant.policy("maskPiiInLogs", True)))
        log.info("Бизнес %s: календарь=%s, AI=%s, уведомления=%s", tenant.slug, calendar.mode,
                 "on" if agent.available() else "off",
                 tenant.notifications.get("provider", "console"))
        return TenantRuntime(tenant=tenant, calendar=calendar, tools=tools, agent=agent)

    def reload(self, slug: str) -> TenantRuntime:
        """Настройки бизнеса изменились — пересобираем его сервисы."""
        registry.invalidate(slug)
        self._by_tenant.pop(slug, None)
        return self.for_tenant(slug)

    def forget(self, slug: str) -> None:
        self._by_tenant.pop(slug, None)

    def _apply_log_policy(self, enabled: bool) -> None:
        """Маскирование PII включается, если его требует хотя бы один бизнес."""
        install_pii_filter(enabled)


runtime = Runtime()
