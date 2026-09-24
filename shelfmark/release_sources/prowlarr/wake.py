"""Wake Prowlarr when someone opens the Shelfmark UI.

Some deployments run Prowlarr on demand (e.g. stopped by Sablier after a quiet spell and
started again by the first request through a proxy). A cold Prowlarr takes several
seconds to boot, and without this the user pays for it at the search box.

Opening the page is a good early signal that a search is coming, so the Socket.IO
connect handler calls :func:`wake_async`, which pings Prowlarr's unauthenticated
``/ping`` on a daemon thread. The ping itself is what starts it; nothing waits on it.

Off unless ``PROWLARR_WAKE_ON_CONNECT`` is true. Throttled, because every tab, reload
and reconnect fires a connect event. Swallows every failure: this is an optimisation,
and an unreachable Prowlarr is the search path's error to report, not this one's.
"""

from __future__ import annotations

import os
import threading
import time

import requests

from shelfmark.core.config import config
from shelfmark.core.logger import setup_logger
from shelfmark.core.request_helpers import normalize_optional_text
from shelfmark.core.utils import normalize_http_url

logger = setup_logger(__name__)

# One wake per window is plenty: an on-demand proxy keeps Prowlarr up far longer than this.
_MIN_INTERVAL_SECONDS = 60.0

# Long enough for a proxy that holds the request until Prowlarr is healthy.
_PING_TIMEOUT_SECONDS = 120.0

_lock = threading.Lock()
_last_wake: float | None = None


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        from shelfmark.config.env import string_to_bool

        return string_to_bool(value)
    return bool(value)


def is_enabled() -> bool:
    """Whether connect-time wakes are switched on (env only; not a UI setting)."""
    return _as_bool(os.environ.get("PROWLARR_WAKE_ON_CONNECT", "false"))


def _ping_url() -> str | None:
    if not _as_bool(config.get("PROWLARR_ENABLED", False)):
        return None
    raw_url = config.get("PROWLARR_URL", "")
    url = normalize_optional_text(raw_url) if isinstance(raw_url, str) else None
    base = normalize_http_url(url) if url else None
    return f"{base.rstrip('/')}/ping" if base else None


def _ping(url: str) -> None:
    started = time.monotonic()
    try:
        response = requests.get(url, timeout=_PING_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        logger.info("Prowlarr wake did not complete: %s", exc)
        return
    logger.info("Prowlarr wake: HTTP %s in %.1fs", response.status_code, time.monotonic() - started)


def wake_async(*, now: float | None = None) -> bool:
    """Ping Prowlarr on a daemon thread. Returns True if a ping was started."""
    global _last_wake

    if not is_enabled():
        return False
    url = _ping_url()
    if url is None:
        return False

    current = time.monotonic() if now is None else now
    with _lock:
        if _last_wake is not None and current - _last_wake < _MIN_INTERVAL_SECONDS:
            return False
        _last_wake = current

    threading.Thread(target=_ping, args=(url,), name="ProwlarrWake", daemon=True).start()
    return True
