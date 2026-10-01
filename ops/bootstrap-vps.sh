#!/usr/bin/env bash
# Подготовка свежего VPS под Coolify: пользователь, SSH, файрвол, Docker, Coolify.
#
#   ssh root@ВАШ_IP 'bash -s' < ops/bootstrap-vps.sh
#
# Скрипт идемпотентен: повторный запуск ничего не ломает и не дублирует.
# Всё, что нельзя сделать за владельца (DNS, пароль администратора Coolify,
# переменные окружения приложения), скрипт не трогает и печатает в конце.
#
# ВАЖНО: перед запуском убедитесь, что ваш публичный ключ уже лежит в
# /root/.ssh/authorized_keys — скрипт отключает вход по паролю, и без ключа
# вы потеряете доступ к серверу.

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
SKIP_SSH_HARDENING="${SKIP_SSH_HARDENING:-0}"

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!  %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Запускать от root."
command -v apt-get >/dev/null || die "Скрипт рассчитан на Debian/Ubuntu."

# --- 0. Ключ на месте? -------------------------------------------------------
# Проверяем до отключения паролей: иначе можно закрыть себе единственную дверь.
if [ "$SKIP_SSH_HARDENING" != "1" ]; then
  if ! grep -qE '^(ssh|ecdsa)-' /root/.ssh/authorized_keys 2>/dev/null; then
    die "В /root/.ssh/authorized_keys нет ключа. Добавьте его или запустите с SKIP_SSH_HARDENING=1."
  fi
fi

# --- 1. Обновление и базовые пакеты -----------------------------------------
log "Обновляю пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl ca-certificates ufw fail2ban rsync

# --- 2. Пользователь для эксплуатации ---------------------------------------
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  log "Пользователь $DEPLOY_USER уже есть"
else
  log "Создаю пользователя $DEPLOY_USER"
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG sudo "$DEPLOY_USER"
if [ -d /root/.ssh ]; then
  rsync --archive --chown="$DEPLOY_USER:$DEPLOY_USER" /root/.ssh "/home/$DEPLOY_USER/"
fi

# --- 3. SSH ------------------------------------------------------------------
if [ "$SKIP_SSH_HARDENING" = "1" ]; then
  warn "Ужесточение SSH пропущено (SKIP_SSH_HARDENING=1)"
else
  log "Отключаю вход по паролю и вход root"
  cat > /etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
  sshd -t || die "Конфигурация sshd не проходит проверку — ничего не меняю."
  systemctl restart ssh || systemctl restart sshd
fi

systemctl enable --now fail2ban >/dev/null 2>&1 || warn "fail2ban не запустился"

# --- 4. Файрвол --------------------------------------------------------------
# Порт Postgres не открываем никогда: база доступна только внутри сети Docker.
log "Настраиваю файрвол: SSH, HTTP, HTTPS и порт установки Coolify"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp   >/dev/null
ufw allow 443/tcp  >/dev/null
ufw allow 8000/tcp >/dev/null   # панель Coolify до переезда на свой домен
ufw --force enable >/dev/null
ufw status numbered

# --- 5. Своп -----------------------------------------------------------------
# Сборка образа на 4 ГБ без свопа иногда падает по памяти.
if [ ! -f /swapfile ] && [ "$(free -m | awk '/^Mem:/{print $2}')" -lt 8000 ]; then
  log "Создаю swap 2 ГБ"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- 6. Coolify --------------------------------------------------------------
if [ -d /data/coolify ]; then
  log "Coolify уже установлен — пропускаю"
else
  log "Устанавливаю Coolify (поднимет Docker сам)"
  curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
fi

IP="$(curl -fsS --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')"

cat <<EOF

────────────────────────────────────────────────────────────────
Сервер готов. Дальше — вручную, эти шаги за вас сделать нельзя:

1. Откройте http://${IP}:8000 и СРАЗУ создайте администратора.
   Регистрация открыта до первого аккаунта — не откладывайте.

2. DNS: A-запись booking.ваш-домен → ${IP}
   Проверка: dig +short booking.ваш-домен

3. Coolify → + New → Docker Compose → приватный репозиторий,
   ветка main, файл docker-compose.yml.

4. Environment Variables (без них деплой не стартует):
     POSTGRES_PASSWORD, ADMIN_TOKEN, SLOT_SIGNING_KEY
   Сгенерировать:  openssl rand -base64 32
     ALLOWED_ORIGINS=https://demo-salon.vercel.app

5. Домен привяжите к сервису api, health check: /health, порт 8080.

6. После деплоя закройте порт панели:  ufw delete allow 8000/tcp
   (предварительно выдав Coolify собственный домен в Settings).

Подробности: docs/DEPLOY.md
────────────────────────────────────────────────────────────────
EOF
