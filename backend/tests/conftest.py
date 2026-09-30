"""Test setup. Runs against a throwaway SQLite file by default; set TEST_DATABASE_URL to run the same
suite against MySQL (e.g. mysql+pymysql://user:pw@127.0.0.1/verba_test). Cloudinary, Groq and the
AI analysis model are always faked: no test touches the network."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="verba-tests-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/verba_test.db"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-0123456789abcdef"
os.environ["ADMIN_INVITE_CODE"] = "let-me-in-123"
os.environ["SPEECH_PROVIDER"] = "groq"
os.environ["GROQ_API_KEY"] = "test-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.session import Base, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import models as _models  # noqa: E402,F401  (registers tables on Base)

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with TestClient(fastapi_app) as c:
        yield c


def register(client, email="teacher@example.com", *, role="teacher", name="Test Teacher", **extra):
    body = {"email": email, "full_name": name, "password": PASSWORD, "confirm_password": PASSWORD, "role": role, **extra}
    return client.post("/auth/register", json=body)


def auth_headers(client, email="teacher@example.com", **kw):
    res = register(client, email, **kw)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def teacher(client):
    return auth_headers(client, "teacher@example.com")


@pytest.fixture()
def other_teacher(client):
    return auth_headers(client, "other@example.com", name="Other Teacher")
