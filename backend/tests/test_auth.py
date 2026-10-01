"""Вход в админку: пароли, сессии, второй фактор, защита от перебора."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app import auth
from backend.app.db import Store


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(f"sqlite:///{tmp_path/'auth.db'}")


@pytest.fixture
def secured(tenants_dir, tmp_path, monkeypatch):
    """Клиент с закрытой админкой: без входа сюда не попасть."""
    from fastapi.testclient import TestClient

    from backend.app import deps
    from backend.tests.conftest import write_tenant

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.delenv("ADMIN_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", "machine-token-for-scripts")
    # Тестовый клиент ходит по http, а Secure-cookie по http не сохраняется —
    # тот же флаг нужен и для локальной разработки на localhost.
    monkeypatch.setenv("ADMIN_COOKIE_INSECURE", "1")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'api.db'}"))

    # Счётчик попыток входа живёт в памяти модуля и фикстуру переживает: у всех
    # тестов один клиент «testclient», и на десятке входов подряд защита от
    # перебора срабатывала на самих тестах, роняя их по порядку запуска.
    from backend.app.routers import auth as auth_router
    auth_router._attempts._hits.clear()

    from backend.app.main import app

    return TestClient(app)


# --- пароли ------------------------------------------------------------------

def test_password_hash_is_not_reversible(store):
    user = auth.create_user(store, "a@b.dev", "correct horse 7")
    assert "correct horse 7" not in user.password_hash
    assert auth.verify_password("correct horse 7", user.password_hash)
    assert not auth.verify_password("Correct horse 7", user.password_hash)


def test_weak_password_rejected(store):
    with pytest.raises(auth.AuthError):
        auth.create_user(store, "a@b.dev", "short1")
    with pytest.raises(auth.AuthError):
        auth.create_user(store, "a@b.dev", "onlylettershere")


def test_unknown_user_and_wrong_password_look_the_same(store):
    """Иначе форма входа превращается в справочник существующих адресов."""
    auth.create_user(store, "a@b.dev", "correct horse 7")
    with pytest.raises(auth.AuthError) as wrong:
        auth.authenticate(store, "a@b.dev", "wrong password 9")
    with pytest.raises(auth.AuthError) as missing:
        auth.authenticate(store, "nobody@b.dev", "wrong password 9")
    assert str(wrong.value) == str(missing.value)


def test_lockout_after_repeated_failures(store):
    auth.create_user(store, "a@b.dev", "correct horse 7")
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth.AuthError):
            auth.authenticate(store, "a@b.dev", "nope nope 11")
    # Даже верный пароль теперь не пускает — перебор остановлен.
    with pytest.raises(auth.AuthError, match="попыток"):
        auth.authenticate(store, "a@b.dev", "correct horse 7")


def test_password_change_closes_sessions(store):
    user = auth.create_user(store, "a@b.dev", "correct horse 7")
    token = auth.open_session(store, user.id)
    assert auth.session_user(store, token)
    auth.set_password(store, user.id, "another good 42")
    assert auth.session_user(store, token) is None


# --- сессии ------------------------------------------------------------------

def test_session_expires(store, monkeypatch):
    user = auth.create_user(store, "a@b.dev", "correct horse 7")
    monkeypatch.setattr(auth, "SESSION_TTL", timedelta(seconds=-1))
    assert auth.session_user(store, auth.open_session(store, user.id)) is None


def test_session_token_stored_hashed(store):
    """Дамп базы не должен давать возможность войти чужой сессией."""
    user = auth.create_user(store, "a@b.dev", "correct horse 7")
    token = auth.open_session(store, user.id)
    with store.session_factory() as s:
        from backend.app.db import AdminSession
        rows = s.query(AdminSession).all()
    assert rows and all(r.token_hash != token for r in rows)


def test_logout_kills_session(store):
    user = auth.create_user(store, "a@b.dev", "correct horse 7")
    token = auth.open_session(store, user.id)
    auth.close_session(store, token)
    assert auth.session_user(store, token) is None


# --- второй фактор -----------------------------------------------------------

def test_totp_required_once_enabled(store):
    user = auth.create_user(store, "a@b.dev", "correct horse 7")
    secret = auth.new_totp_secret()
    auth.set_totp(store, user.id, secret)
    with pytest.raises(auth.AuthError, match="код"):
        auth.authenticate(store, "a@b.dev", "correct horse 7")
    assert auth.authenticate(store, "a@b.dev", "correct horse 7", auth.totp_code(secret))


def test_totp_rejects_wrong_code(store):
    secret = auth.new_totp_secret()
    assert not auth.verify_totp(secret, "000000")
    assert not auth.verify_totp(secret, "")
    assert not auth.verify_totp(secret, "abcdef")


def test_totp_tolerates_clock_drift(store):
    """Часы телефона и сервера расходятся — соседнее окно должно приниматься."""
    from backend.app.auth import _now
    secret = auth.new_totp_secret()
    past = auth.totp_code(secret, _now() - timedelta(seconds=30))
    assert auth.verify_totp(secret, past)


# --- HTTP --------------------------------------------------------------------

def test_admin_api_closed_without_login(secured):
    assert secured.get("/api/admin/config?tenant=demo-salon").status_code == 401


def test_machine_token_still_works(secured):
    """Скрипты и интеграции продолжают ходить по X-Admin-Token."""
    r = secured.get("/api/admin/config?tenant=demo-salon",
                    headers={"X-Admin-Token": "machine-token-for-scripts"})
    assert r.status_code == 200


def test_first_admin_can_register_then_path_closes(secured):
    assert secured.get("/api/admin/auth/state").json()["needsSetup"] is True

    r = secured.post("/api/admin/auth/register",
                     json={"email": "boss@salon.dev", "password": "first admin 55"})
    assert r.status_code == 200
    # Сессия выдана сразу — панель открывается без второго входа.
    assert secured.get("/api/admin/config?tenant=demo-salon").status_code == 200
    assert secured.get("/api/admin/auth/state").json()["authenticated"] is True

    again = secured.post("/api/admin/auth/register",
                         json={"email": "intruder@evil.dev", "password": "second admin 55"})
    assert again.status_code == 403


def test_login_logout_cycle(secured):
    secured.post("/api/admin/auth/register",
                 json={"email": "boss@salon.dev", "password": "first admin 55"})
    secured.post("/api/admin/auth/logout")
    assert secured.get("/api/admin/config?tenant=demo-salon").status_code == 401

    bad = secured.post("/api/admin/auth/login",
                       json={"email": "boss@salon.dev", "password": "wrong pass 77"})
    assert bad.status_code == 401

    ok = secured.post("/api/admin/auth/login",
                      json={"email": "boss@salon.dev", "password": "first admin 55"})
    assert ok.status_code == 200
    assert secured.get("/api/admin/config?tenant=demo-salon").status_code == 200


def test_session_cookie_is_httponly(secured):
    r = secured.post("/api/admin/auth/register",
                     json={"email": "boss@salon.dev", "password": "first admin 55"})
    cookie = r.headers.get("set-cookie", "")
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


# --- роли --------------------------------------------------------------------

def register_owner(client, email="boss@salon.dev", password="first admin 55"):
    return client.post("/api/admin/auth/register", json={"email": email, "password": password})


def test_first_registered_user_is_the_owner(secured):
    """Иначе подключить интеграции и завести людей было бы некому."""
    register_owner(secured)
    assert secured.get("/api/admin/auth/state").json()["role"] == "owner"


def test_owner_creates_an_admin_who_cannot_touch_integrations(secured):
    register_owner(secured)
    made = secured.post("/api/admin/auth/users",
                        json={"email": "admin@salon.dev", "password": "second admin 55",
                              "name": "Администратор", "role": "admin"})
    assert made.status_code == 200, made.text

    secured.post("/api/admin/auth/logout")
    secured.post("/api/admin/auth/login",
                 json={"email": "admin@salon.dev", "password": "second admin 55"})
    assert secured.get("/api/admin/auth/state").json()["role"] == "admin"

    # Записи и расписание — работа администратора.
    assert secured.get("/api/admin/bookings?tenant=demo-salon").status_code == 200
    # Ключи и подключения — нет. Спрятанного раздела в панели мало: проверяет сервер.
    for path in ("/api/admin/google/status", "/api/admin/telegram/status",
                 "/api/admin/ai/status", "/api/admin/database/status"):
        assert secured.get(f"{path}?tenant=demo-salon").status_code == 403, path


def test_admin_cannot_manage_users(secured):
    """Администратор не заводит себе равных и не разжалует владельца."""
    register_owner(secured)
    secured.post("/api/admin/auth/users",
                 json={"email": "admin@salon.dev", "password": "second admin 55", "role": "admin"})
    secured.post("/api/admin/auth/logout")
    secured.post("/api/admin/auth/login",
                 json={"email": "admin@salon.dev", "password": "second admin 55"})

    assert secured.get("/api/admin/auth/users").status_code == 403
    assert secured.post("/api/admin/auth/users",
                        json={"email": "x@salon.dev", "password": "third admin 55"}).status_code == 403


def test_last_owner_cannot_be_demoted_or_deleted(secured):
    """Панель не должна остаться без человека, который может её настраивать."""
    register_owner(secured)
    me = secured.get("/api/admin/auth/users").json()["users"][0]

    demote = secured.patch(f"/api/admin/auth/users/{me['id']}", json={"role": "admin"})
    assert demote.status_code == 422
    assert "единственный владелец" in demote.json()["detail"]

    off = secured.patch(f"/api/admin/auth/users/{me['id']}", json={"isActive": False})
    assert off.status_code == 422


def test_owner_cannot_delete_himself(secured):
    register_owner(secured)
    me = secured.get("/api/admin/auth/users").json()["users"][0]
    assert secured.delete(f"/api/admin/auth/users/{me['id']}").status_code == 422


def test_machine_token_keeps_owner_level_access(secured):
    """Скрипты ходят по X-Admin-Token: это доступ уровня сервера, а не роль."""
    register_owner(secured)
    secured.post("/api/admin/auth/logout")
    r = secured.get("/api/admin/google/status?tenant=demo-salon",
                    headers={"X-Admin-Token": "machine-token-for-scripts"})
    assert r.status_code == 200


def test_open_local_panel_reaches_the_users_screen(client):
    """Локальная панель (ADMIN_ALLOW_NO_TOKEN=1) не должна требовать вход.

    Раздел «Внутренние уведомления» читает список пользователей. Пока эта
    проверка признавала только сессию, панель, открытая для разработки,
    выбрасывала на форму входа посреди работы — 401 приходил там, где всё
    остальное открыто.
    """
    got = client.get("/api/admin/auth/users?tenant=demo-salon")
    assert got.status_code == 200, got.text
    assert "users" in got.json()


def test_machine_token_reaches_the_users_screen(secured):
    """Токен — доступ уровня сервера: он открывает записи, откроет и список людей."""
    with_token = secured.get("/api/admin/auth/users",
                             headers={"X-Admin-Token": "machine-token-for-scripts"})
    assert with_token.status_code == 200, with_token.text

    without = secured.get("/api/admin/auth/users")
    assert without.status_code == 401
