#!/bin/sh
# Резервные копии: дамп Postgres плюс конфигурации бизнесов.
#
# Дампа базы недостаточно: в tenants/ лежат услуги, мастера и расписание, без
# которых восстановленная база ничего не значит. Секретов в бэкапе нет — они
# живут в окружении сервера и в таблице tenant_secrets (её дамп содержит).
#
# Цикл вместо cron: в контейнере нет ни демона cron, ни причины его туда ставить.

set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
TENANTS_DIR="${TENANTS_DIR:-/tenants}"

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%SZ') backup: $*"; }

run_backup() {
  stamp="$(date -u '+%Y%m%d-%H%M%S')"
  target="${BACKUP_DIR}/booking-${stamp}.sql.gz"
  tmp="${target}.part"

  # Пишем во временный файл: оборванный дамп не должен выглядеть как готовый.
  if pg_dump --no-owner --no-privileges --clean --if-exists | gzip -9 > "$tmp"; then
    mv "$tmp" "$target"
    log "дамп базы готов: $(basename "$target") ($(du -h "$target" | cut -f1))"
  else
    rm -f "$tmp"
    log "ОШИБКА: pg_dump не отработал"
    return 1
  fi

  if [ -d "$TENANTS_DIR" ]; then
    tenants_target="${BACKUP_DIR}/tenants-${stamp}.tar.gz"
    if tar -czf "${tenants_target}.part" -C "$TENANTS_DIR" . ; then
      mv "${tenants_target}.part" "$tenants_target"
      log "конфигурации бизнесов сохранены: $(basename "$tenants_target")"
    else
      rm -f "${tenants_target}.part"
      log "ОШИБКА: не удалось упаковать tenants/"
    fi
  fi

  # Проверяем, что архив читается: бэкап, который нельзя открыть, — не бэкап.
  if ! gzip -t "$target"; then
    log "ОШИБКА: архив ${target} повреждён"
    return 1
  fi

  removed="$(find "$BACKUP_DIR" -name '*.gz' -type f -mtime "+${KEEP_DAYS}" -print -delete | wc -l)"
  [ "$removed" -gt 0 ] && log "удалено старых копий: ${removed}"
  return 0
}

mkdir -p "$BACKUP_DIR"
log "сервис запущен: интервал ${INTERVAL_HOURS} ч, хранение ${KEEP_DAYS} дней"

while true; do
  run_backup || log "проход завершился с ошибкой — повторим в следующий раз"
  sleep "$(( INTERVAL_HOURS * 3600 ))"
done
