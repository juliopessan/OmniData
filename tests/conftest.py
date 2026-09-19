import os
import pathlib

import pytest

from omnidata import db

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:54399/omnidata_test")
pathlib.Path("tests/__init__.py").touch(exist_ok=True)


@pytest.fixture
def conn():
    """Fresh schema per test; skipped when no Postgres is reachable (CI provides one)."""
    try:
        c = db.connect(TEST_DSN)
    except Exception:
        pytest.skip("no test Postgres available (set TEST_DATABASE_URL)")
    with c.cursor() as cur:
        cur.execute("drop schema if exists bronze, silver, gold, serving, app, airbyte cascade; "
                    "drop table if exists public._omnidata_migrations")
    c.commit()
    db.migrate(c)
    yield c
    c.close()
