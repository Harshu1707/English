from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import text

from app.core.config import settings
from app.database.session import engine
from tests.conftest import PASSWORD, auth_headers, register


def test_register_login_me_roundtrip(client):
    res = register(client, "Jo@Example.com")
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "jo@example.com"  # normalised
    assert body["user"]["role"] == "teacher"
    assert "password" not in res.text and "password_hash" not in res.text

    login = client.post("/auth/login", json={"email": "JO@example.com", "password": PASSWORD})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.status_code == 200
    assert set(me.json()) == {"id", "email", "full_name", "role"}


def test_password_is_hashed_in_db(client):
    register(client, "hash@example.com")
    with engine.connect() as c:
        stored = c.execute(text("SELECT password_hash FROM users WHERE email='hash@example.com'")).scalar()
    assert stored != PASSWORD and stored.startswith("$2")


def test_duplicate_email_rejected_case_insensitively(client):
    assert register(client, "dup@example.com").status_code == 200
    again = register(client, "DUP@example.com")
    assert again.status_code == 409 and "already registered" in again.json()["detail"]


def test_registration_validation(client):
    base = {"email": "v@example.com", "full_name": "Vee", "password": PASSWORD, "confirm_password": PASSWORD}
    cases = {
        "mismatch": {**base, "confirm_password": "something-else-entirely"},
        "bad email": {**base, "email": "not-an-email"},
        "short password": {**base, "password": "short", "confirm_password": "short"},
        "over 72 bytes": {**base, "password": "x" * 73, "confirm_password": "x" * 73},
        "bad role": {**base, "role": "superuser"},
        "short name": {**base, "full_name": " a "},
    }
    for label, body in cases.items():
        assert client.post("/auth/register", json=body).status_code == 422, label


def test_admin_registration_needs_invite_code(client, monkeypatch):
    assert register(client, "a1@example.com", role="admin").status_code == 403
    assert register(client, "a2@example.com", role="admin", admin_invite_code="wrong").status_code == 403
    ok = register(client, "a3@example.com", role="admin", admin_invite_code="let-me-in-123")
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "admin"
    monkeypatch.setattr(settings, "admin_invite_code", None)  # feature off => nobody can self-register as admin
    assert register(client, "a4@example.com", role="admin", admin_invite_code="let-me-in-123").status_code == 403


def test_login_failures_are_indistinguishable(client):
    register(client, "real@example.com")
    wrong_pw = client.post("/auth/login", json={"email": "real@example.com", "password": "not-the-password"})
    unknown = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


def test_protected_routes_reject_missing_bad_and_expired_tokens(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    good = auth_headers(client)
    forged = jwt.encode({"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "wrong-secret", algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = jwt.encode({"sub": "1", "role": "teacher", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, settings.jwt_secret, algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    no_sub = jwt.encode({"role": "teacher", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, settings.jwt_secret, algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {no_sub}"}).status_code == 401
    assert client.get("/auth/me", headers=good).status_code == 200


def test_deactivated_user_loses_access(client):
    headers = auth_headers(client)
    with engine.begin() as c:
        c.execute(text("UPDATE users SET is_active = 0"))
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/login", json={"email": "teacher@example.com", "password": PASSWORD}).status_code == 403


def test_role_based_access_on_admin_routes(client):
    teacher = auth_headers(client, "t@example.com")
    admin = auth_headers(client, "ad@example.com", role="admin", admin_invite_code="let-me-in-123")
    url = "/admin/media/lesson/999"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=teacher).status_code == 403
    assert client.get(url, headers=admin).status_code == 404  # authorised; lesson simply doesn't exist
