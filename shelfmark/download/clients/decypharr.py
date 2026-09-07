"""Decypharr client: a second qBittorrent-compatible endpoint used only by AudiobookBay.

Decypharr (https://github.com/sirrobot01/decypharr) fronts debrid services
(Real-Debrid etc.) with a qBittorrent-compatible Web API. Shelfmark supports a
single global torrent client (``PROWLARR_TORRENT_CLIENT``), which is typically a
real seeding client that must not be used for public-tracker releases. This
client lets the AudiobookBay release source send its magnets to Decypharr
instead, configured under its own ``ABB_DECYPHARR_*`` keys.

It is intentionally NOT registered with ``register_client``: the registry hands
the first configured client to every external release source, and this one must
only ever be picked by ``AudiobookBayHandler``.
"""

from __future__ import annotations

from shelfmark.core.config import config
from shelfmark.download.clients._coercion import normalize_http_config_url
from shelfmark.download.clients.qbittorrent import QBittorrentClient


class DecypharrClient(QBittorrentClient):
    """qBittorrent-API client bound to the ``ABB_DECYPHARR_*`` settings."""

    name = "decypharr"
    config_prefix = "ABB_DECYPHARR"

    @property
    def category(self) -> str:
        """Configured category (also Decypharr's per-torrent staging folder name)."""
        return self._category

    @staticmethod
    def is_configured() -> bool:
        """True when the AudiobookBay-specific Decypharr client is enabled and has a URL."""
        enabled = bool(config.get("ABB_DECYPHARR_ENABLED", False))
        url = normalize_http_config_url(config.get("ABB_DECYPHARR_URL", ""), require_string=True)
        return enabled and bool(url)
