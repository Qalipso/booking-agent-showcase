# Один образ на два процесса: API и воркер уведомлений (команду задаёт compose).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# curl нужен HEALTHCHECK, postgresql-client — pg_dump в сервисе бэкапов.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl postgresql-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Зависимости отдельным слоем: код меняется часто, requirements — редко.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY config/ config/
COPY public/ public/
COPY ops/ ops/
# Конфигурация Alembic: миграции применяет сервис migrate из этого же образа.
COPY alembic.ini ./

# Каталог конфигураций бизнесов — том, а не слой образа: его правит админ-форма.
RUN mkdir -p tenants data

# От root не работаем: пробитый контейнер не должен становиться пробитым хостом.
RUN useradd --system --uid 10001 --home-dir /app app \
 && chown -R app:app /app

# /backups создаём заранее и отдаём приложению: пустой том наследует права точки
# монтирования из образа, иначе он достаётся root — и сервис бэкапов, работающий
# от app, не смог бы туда писать.
RUN mkdir -p /backups && chown app:app /backups
USER app

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null || exit 1

# --proxy-headers: за реверс-прокси Coolify иначе теряется https в redirect_uri OAuth.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
