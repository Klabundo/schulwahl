"""Pytest-Setup: frische Test-DB (vor dem Import von app setzen!)."""
import os
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp(prefix="schulwahl-test-")
os.environ["SCHULWAHL_DB"] = os.path.join(_tmpdir, "test.db")


@pytest.fixture()
def client():
    import app as appmod

    appmod.app.config["TESTING"] = True
    with appmod.app.test_client() as c:
        yield c


@pytest.fixture()
def admin_client(client):
    r = client.post("/login", data={"password": "admin123"})
    assert r.status_code == 302, "Login mit Standard-Passwort muss klappen"
    return client
