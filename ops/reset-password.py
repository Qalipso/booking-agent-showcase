"""Сброс пароля пользователя панели.

Штатного «забыли пароль» в панели нет: рассылка писем потребовала бы SMTP, а
владелец у салона один и сидит рядом с сервером. Поэтому сброс — операция на
сервере, доступная тому, у кого есть SSH.

    docker exec -it -w /app -e PYTHONPATH=/app <api> python ops/reset-password.py

Пароль спрашивается интерактивно и не остаётся ни в истории команд, ни в логах.
Смена пароля закрывает все прежние сессии этого пользователя.
"""

from __future__ import annotations

import getpass
import sys

from backend.app import auth
from backend.app.deps import runtime


def main() -> int:
    store = runtime.store
    users = auth.list_users(store)
    if not users:
        print("Пользователей нет — откройте панель, она предложит создать первого.")
        return 1

    print("Кому меняем пароль:")
    for i, u in enumerate(users, 1):
        print(f"  {i}. {u.email} ({u.role})")

    choice = input("Номер: ").strip()
    try:
        user = users[int(choice) - 1]
    except (ValueError, IndexError):
        print("Нет такого номера.")
        return 1

    password = getpass.getpass(f"Новый пароль для {user.email}: ")
    again = getpass.getpass("Ещё раз: ")
    if password != again:
        print("Пароли не совпали.")
        return 1

    try:
        auth.set_password(store, user.id, password)
    except auth.AuthError as exc:
        print(f"Не подошёл: {exc}")
        return 1

    print(f"Пароль изменён: {user.email}. Прежние сессии закрыты.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
