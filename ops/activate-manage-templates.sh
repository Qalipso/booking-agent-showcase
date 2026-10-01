#!/bin/bash
# Включает кнопку «Перенести или отменить», как только Meta одобрит шаблоны.
#
# Модерация занимает от минут до суток, и всё это время включать флаг нельзя:
# у неодобренного шаблона переменных пять, а очередь отправит шесть. Поэтому
# пробуем по расписанию и снимаем задание, когда получилось.
#
#   cp ops/activate-manage-templates.sh /root/
#   echo '*/10 * * * * root /root/activate-manage-templates.sh' > /etc/cron.d/activate-manage-templates
#
# Лог: /var/log/activate-manage-templates.log
set -u
TENANT="${1:-demo-salon}"
LOG=/var/log/activate-manage-templates.log

say() { echo "$(date '+%F %T') $*" >> "$LOG"; }

api=$(docker ps --format '{{.Names}}' | grep '^api-qkir' | head -1)
worker=$(docker ps --format '{{.Names}}' | grep '^worker-qkir' | head -1)
if [ -z "$api" ] || [ -z "$worker" ]; then
  say "контейнеры не найдены — возможно, идёт деплой"
  exit 0
fi

out=$(docker exec -w /app "$api" python3 ops/whatsapp_templates.py --tenant "$TENANT" --activate 2>&1)
rc=$?

# Шаблон без кнопки одобряют отдельно от остальных, и ждать ради него общего
# включения незачем: его Content SID вписывается сразу, но настройки читаются
# при старте — значит контейнеры надо поднять заново.
if echo "$out" | grep -q "нужен перезапуск"; then
  say "$out"
  docker restart "$api" "$worker" >/dev/null && say "api и worker перезапущены"
  exit 0
fi

if [ $rc -ne 0 ]; then
  say "пока нет: $(echo "$out" | tail -1)"
  exit 0
fi

say "$out"
rm -f /etc/cron.d/activate-manage-templates
say "задание снято — все шаблоны на месте"
