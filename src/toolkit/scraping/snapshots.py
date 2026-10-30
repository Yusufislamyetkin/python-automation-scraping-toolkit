"""Save the raw HTML of a page that failed to parse, for later debugging."""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from toolkit.logging import get_logger

log = get_logger(__name__)


def save_snapshot(directory: Path, source: str, url: str, html: str, reason: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower())[-60:].strip("-")
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    path = directory / f"{source}_{stamp}_{slug}_{digest}.html"
    path.write_text(f"<!-- url: {url}\n reason: {reason} -->\n{html}", encoding="utf-8")
    log.warning("snapshot_saved", source=source, url=url, path=str(path), reason=reason)
    return path
