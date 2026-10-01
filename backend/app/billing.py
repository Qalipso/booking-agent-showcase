"""Тарифы, лимиты и учёт потребления.

Подписка живёт на уровне аккаунта (весь инстанс сервиса), а лимиты считаются
суммарно по всем его бизнесам: столько-то бизнесов, записей и AI-сообщений
в календарный месяц.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import CONFIG_DIR

log = logging.getLogger("billing")
ACCOUNT_FILE = CONFIG_DIR / "account.json"
_lock = threading.Lock()

UNLIMITED = -1

PLANS: dict[str, dict[str, Any]] = {
    "trial": {
        "title": "Пробный",
        "price": "0 USD / 14 дней",
        "limits": {"tenants": 1, "bookings": 50, "aiMessages": 300},
        "features": {"ai": True, "whatsapp": False, "notifications": True},
        "note": "Полный сценарий, чтобы проверить бота на живых клиентах.",
    },
    "solo": {
        "title": "Один салон",
        "price": "29 USD / мес",
        "limits": {"tenants": 1, "bookings": 400, "aiMessages": 3000},
        "features": {"ai": True, "whatsapp": True, "notifications": True},
        "note": "Один бизнес, запись и напоминания без ограничений по мастерам.",
    },
    "studio": {
        "title": "Сеть",
        "price": "79 USD / мес",
        "limits": {"tenants": 5, "bookings": 2000, "aiMessages": 15000},
        "features": {"ai": True, "whatsapp": True, "notifications": True},
        "note": "До пяти салонов в одной панели, общий биллинг.",
    },
    "agency": {
        "title": "Агентство",
        "price": "199 USD / мес",
        "limits": {"tenants": UNLIMITED, "bookings": UNLIMITED, "aiMessages": 60000},
        "features": {"ai": True, "whatsapp": True, "notifications": True},
        "note": "Без ограничения на число бизнесов — для студий и подрядчиков.",
    },
}

DEFAULT_ACCOUNT = {
    "plan": "trial",
    "status": "active",          # active | past_due | cancelled
    "customerEmail": "",
    "startedAt": "",
    "renewsAt": "",
    "provider": "manual",        # manual | stripe | mercadopago
    "externalId": "",
}

METRICS = ("bookings", "aiMessages")


class LimitExceeded(RuntimeError):
    """Лимит тарифа исчерпан. Сообщение уходит клиенту и владельцу."""

    def __init__(self, metric: str, message: str) -> None:
        super().__init__(message)
        self.metric = metric
        self.message = message


def period_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


class Account:
    """Подписка инстанса. Правится через админку или платёжный провайдер."""

    def __init__(self) -> None:
        self.data = self._read()

    @staticmethod
    def _read() -> dict:
        try:
            return {**DEFAULT_ACCOUNT, **json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_ACCOUNT)

    def reload(self) -> None:
        self.data = self._read()

    @property
    def plan_id(self) -> str:
        plan = self.data.get("plan", "trial")
        return plan if plan in PLANS else "trial"

    @property
    def plan(self) -> dict:
        return PLANS[self.plan_id]

    @property
    def active(self) -> bool:
        return self.data.get("status", "active") == "active"

    def limit(self, metric: str) -> int:
        return int(self.plan["limits"].get(metric, UNLIMITED))

    def feature(self, name: str) -> bool:
        return bool(self.plan["features"].get(name, False))

    def save(self, patch: dict) -> None:
        with _lock:
            self.data = {**self.data, **patch}
            ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = ACCOUNT_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(ACCOUNT_FILE)
        log.info("Тариф аккаунта: %s (%s)", self.plan_id, self.data.get("status"))


account = Account()


def _left(limit: int, used: int) -> int | None:
    return None if limit == UNLIMITED else max(0, limit - used)


def check_can_add_tenant(current_count: int) -> None:
    limit = account.limit("tenants")
    if limit != UNLIMITED and current_count >= limit:
        raise LimitExceeded(
            "tenants",
            f"Тариф «{account.plan['title']}» рассчитан на {limit} "
            f"{'бизнес' if limit == 1 else 'бизнесов'}. Перейдите на следующий тариф, чтобы добавить ещё.",
        )


def check_and_count(store, metric: str, *, tenant_id: str) -> int:
    """Проверяет лимит и увеличивает счётчик. Бросает LimitExceeded, если исчерпан.

    Проверка и учёт вместе: иначе между ними успевает пройти лишний запрос.
    """
    if not account.active:
        raise LimitExceeded("subscription",
                            "Подписка приостановлена — оплатите её, чтобы бот продолжил работу.")
    limit = account.limit(metric)
    period = period_key()
    if limit == UNLIMITED:
        return store.bump_usage(tenant_id, metric, period)

    used = store.usage(period).get(metric, 0)  # суммарно по всем бизнесам аккаунта
    if used >= limit:
        raise LimitExceeded(metric, _limit_message(metric, limit))
    return store.bump_usage(tenant_id, metric, period)


def _limit_message(metric: str, limit: int) -> str:
    if metric == "aiMessages":
        return (f"Исчерпан лимит AI-диалога на этот месяц ({limit} сообщений). "
                "Бот продолжит записывать кнопками — или повысьте тариф.")
    if metric == "bookings":
        return (f"Исчерпан лимит записей на этот месяц ({limit}). "
                "Повысьте тариф, чтобы бот продолжил принимать записи.")
    return "Лимит тарифа исчерпан."


def snapshot(store, *, tenants: list[str]) -> dict:
    """Состояние подписки для админки: план, потребление, остатки."""
    period = period_key()
    used = store.usage(period)
    by_tenant = store.usage_by_tenant(period)
    limits = account.plan["limits"]
    return {
        "plan": account.plan_id,
        "planTitle": account.plan["title"],
        "price": account.plan["price"],
        "note": account.plan["note"],
        "status": account.data.get("status", "active"),
        "renewsAt": account.data.get("renewsAt", ""),
        "customerEmail": account.data.get("customerEmail", ""),
        "provider": account.data.get("provider", "manual"),
        "period": period,
        "usage": {
            "tenants": {"used": len(tenants), "limit": limits.get("tenants", UNLIMITED),
                        "left": _left(int(limits.get("tenants", UNLIMITED)), len(tenants))},
            "bookings": {"used": used.get("bookings", 0), "limit": limits.get("bookings", UNLIMITED),
                         "left": _left(int(limits.get("bookings", UNLIMITED)), used.get("bookings", 0))},
            "aiMessages": {"used": used.get("aiMessages", 0), "limit": limits.get("aiMessages", UNLIMITED),
                           "left": _left(int(limits.get("aiMessages", UNLIMITED)), used.get("aiMessages", 0))},
        },
        "byTenant": by_tenant,
        "plans": [
            {"id": pid, "title": p["title"], "price": p["price"], "note": p["note"],
             "limits": p["limits"], "features": p["features"], "current": pid == account.plan_id}
            for pid, p in PLANS.items()
        ],
    }
