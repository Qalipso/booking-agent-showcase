"""Воркер уведомлений: отдельный процесс, та же база.

Запуск: ``python -m backend.app.worker``. В docker-compose это отдельный сервис —
API перезапускается при деплое, а очередь напоминаний не должна зависеть от того,
жив ли конкретный веб-процесс, и не должна конкурировать с ним за поток.

Задачи захватываются по одной сменой статуса ``scheduled → sending``, поэтому
несколько воркеров можно поднимать без координации.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

from . import migrate
from .db import DatabaseNotConfigured, build_store
from .notify import NotificationService
from .policies import install_pii_filter
from .secretstore import SecretStore
from .tenants import bind_secret_store, registry

TICK_SECONDS = int(os.getenv("NOTIFY_TICK_SECONDS", "30"))
BATCH = int(os.getenv("NOTIFY_BATCH", "50"))
STUCK_MINUTES = int(os.getenv("NOTIFY_STUCK_MINUTES", "5"))

# Отметка живости для healthcheck: обновляется каждый проход. Проверять живой
# процесс мало — воркер, залипший на одной задаче, тоже «жив», но бесполезен.
HEARTBEAT = Path(os.getenv("NOTIFY_HEARTBEAT", "/tmp/notify-worker.alive"))  # noqa: S108

log = logging.getLogger("worker")
_stop = False


def _handle_signal(signum, _frame) -> None:
    """SIGTERM от docker — доигрываем текущую задачу и выходим без потерь."""
    global _stop  # noqa: PLW0603
    _stop = True
    log.info("Получен сигнал %s — останавливаемся", signum)


def _plan_digests(service) -> None:
    """Утренняя сводка владельцу — по одной на бизнес в день.

    Ставится здесь, а не с вечера: сводка, собранная заранее, врёт про
    отменённые за ночь записи. Имя задачи содержит дату, поэтому проход каждые
    тридцать секунд ничего не дублирует.
    """
    for slug in registry.slugs():
        try:
            tenant = registry.get(slug)
        except Exception:  # noqa: BLE001 — бизнес могли удалить между проходами
            continue
        try:
            service.schedule_owner_digest(tenant)
        except Exception:  # noqa: BLE001 — сводка не имеет права ронять очередь
            log.exception("Сводка для %s не поставлена", slug)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    install_pii_filter(True)  # телефоны не должны утекать в логи

    try:
        store = build_store()
    except DatabaseNotConfigured as exc:
        log.error("%s", exc)
        return 2

    # Воркер пишет в те же таблицы — на устаревшей схеме он не запустится.
    if not store.url.startswith("sqlite") and not migrate.is_up_to_date(store.engine):
        log.error("Схема базы не соответствует коду (применена %s, ожидается %s). "
                  "Выполните: python -m backend.app.migrate",
                  migrate.current_revision(store.engine) or "нет", migrate.head_revision())
        return 3

    bind_secret_store(SecretStore(store))
    service = NotificationService(store)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    recovered = store.recover_stuck_notifications(STUCK_MINUTES)
    if recovered:
        log.warning("Возвращено в очередь после рестарта: %s", recovered)
    log.info("Воркер уведомлений запущен: тик %s с, бизнесов %s",
             TICK_SECONDS, len(registry.slugs()))

    last_recovery = time.monotonic()
    while not _stop:
        try:
            sent = service.tick(limit=BATCH)
            if sent:
                log.info("Обработано задач: %s", sent)
            _plan_digests(service)
            HEARTBEAT.write_text(str(int(time.time())), encoding="utf-8")
            # Раз в 5 минут подбираем задачи, брошенные упавшим процессом.
            if time.monotonic() - last_recovery > 300:
                store.recover_stuck_notifications(STUCK_MINUTES)
                last_recovery = time.monotonic()
        except Exception:  # noqa: BLE001 — воркер не имеет права умереть от одной ошибки
            log.exception("Проход очереди упал")

        for _ in range(TICK_SECONDS):
            if _stop:
                break
            time.sleep(1)

    log.info("Воркер остановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
