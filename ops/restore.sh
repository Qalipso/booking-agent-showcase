#!/bin/sh
# Восстановление из копии. Бэкап, который ни разу не разворачивали, — не бэкап.
#
#   docker compose exec backup sh /usr/local/bin/restore.sh /backups/booking-20260805-030000.sql.gz
#
# Конфигурации бизнесов разворачиваются отдельно:
#   tar -xzf /backups/tenants-<stamp>.tar.gz -C /tenants

set -eu

DUMP="${1:-}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "Укажите файл дампа: restore.sh /backups/booking-YYYYmmdd-HHMMSS.sql.gz" >&2
  exit 2
fi

if ! gzip -t "$DUMP"; then
  echo "Архив повреждён — восстанавливать нечего" >&2
  exit 1
fi

echo "Дамп будет развёрнут в базу ${PGDATABASE} на ${PGHOST}."
echo "Существующие таблицы будут удалены (dump сделан с --clean --if-exists)."
printf 'Продолжить? [y/N] '
read -r answer
case "$answer" in
  y|Y|yes|YES) ;;
  *) echo "Отменено."; exit 0 ;;
esac

# ON_ERROR_STOP: молча развёрнутый наполовину дамп хуже явного отказа.
gunzip -c "$DUMP" | psql --set ON_ERROR_STOP=on
echo "Готово. Перезапустите api и worker: docker compose restart api worker"
