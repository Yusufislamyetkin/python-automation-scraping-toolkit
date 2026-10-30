from pathlib import Path

import pytest

from toolkit.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        request_delay_seconds=0,
        max_pages=3,
        snapshot_dir=tmp_path / "snapshots",
        demo_output_dir=tmp_path / "demo",
    )
