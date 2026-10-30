from toolkit.config import Settings
from toolkit.db import models  # noqa: F401
from toolkit.db.base import Base


def test_settings_defaults_have_no_secrets() -> None:
    s = Settings(_env_file=None)
    assert s.hubspot_token is None
    assert s.google_service_account_file is None
    assert "5434" in s.database_url


def test_metadata_has_all_tables() -> None:
    assert set(Base.metadata.tables) == {
        "products",
        "price_snapshots",
        "change_events",
        "leads",
        "job_runs",
    }
