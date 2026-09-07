"""AudiobookBay download handler - resolves magnet links and uses shared client lifecycle."""

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from shelfmark.core.config import config
from shelfmark.core.logger import setup_logger
from shelfmark.download.clients import (
    DownloadClient,
    get_client,
    list_configured_clients,
)
from shelfmark.download.clients.base_handler import (
    _CLIENT_CLEANUP_ERRORS,
    DownloadRequest,
    ExternalClientHandler,
)
from shelfmark.download.clients.decypharr import DecypharrClient
from shelfmark.release_sources import register_handler
from shelfmark.release_sources.audiobookbay import scraper
from shelfmark.release_sources.audiobookbay.utils import normalize_hostname

if TYPE_CHECKING:
    from collections.abc import Callable

    from shelfmark.core.models import DownloadTask
    from shelfmark.download.postprocess.packs import PackFile

logger = setup_logger(__name__)
DEFAULT_ABB_HOSTNAME = "audiobookbay.lu"
ALLOWED_DETAIL_URL_SCHEMES = {"https"}


def _resolve_configured_hostname() -> str:
    """Return a normalized ABB hostname from config when available."""
    configured_hostname = config.get("ABB_HOSTNAME", "")
    return normalize_hostname(configured_hostname if isinstance(configured_hostname, str) else "")


def _resolve_allowed_detail_hostname() -> str:
    """Return the ABB hostname allowed for queued detail URLs."""
    return _resolve_configured_hostname() or DEFAULT_ABB_HOSTNAME


def _detail_url_matches_host(detail_url: str, hostname: str) -> bool:
    """Return True when a detail URL uses the allowed ABB scheme and host."""
    parsed = urlparse(detail_url)
    detail_hostname = normalize_hostname(parsed.hostname)
    allowed_hostname = normalize_hostname(hostname).lower().rstrip(".")
    return (
        parsed.scheme.lower() in ALLOWED_DETAIL_URL_SCHEMES
        and bool(detail_hostname)
        and detail_hostname.lower().rstrip(".") == allowed_hostname
    )


@register_handler("audiobookbay")
class AudiobookBayHandler(ExternalClientHandler):
    """Handler for AudiobookBay downloads via configured torrent client."""

    @staticmethod
    def _resolve_detail_url(task: DownloadTask) -> str | None:
        """Resolve ABB detail URL from queued task metadata."""
        source_url = (task.source_url or "").strip()
        if source_url:
            return source_url

        # Backward-compat: older tests and some legacy flows used task_id as URL.
        task_id = (task.task_id or "").strip()
        if task_id.startswith(("http://", "https://")):
            return task_id
        return None

    def list_files(self, release_data: dict[str, Any]) -> list[PackFile] | None:
        """Read the torrent's file list off the detail page, without downloading."""
        raw_url = release_data.get("download_url") or release_data.get("source_url")
        detail_url = raw_url.strip() if isinstance(raw_url, str) else ""
        hostname = _resolve_allowed_detail_hostname()
        if not detail_url or not _detail_url_matches_host(detail_url, hostname):
            logger.debug("Cannot list files for AudiobookBay release without a valid detail URL")
            return None
        detail_html = scraper.fetch_detail_html(detail_url, hostname)
        if not detail_html:
            return None
        return scraper.extract_file_list(detail_html)

    def _get_client(self, protocol: str) -> DownloadClient | None:
        """Prefer the dedicated Decypharr client for torrents, else the shared client.

        The module-level ``get_client`` call is kept as the fallback so tests can
        still patch it.
        """
        if protocol == "torrent" and DecypharrClient.is_configured():
            return DecypharrClient()
        return get_client(protocol)

    def _list_configured_clients(self) -> list[str]:
        """Shared clients plus the dedicated Decypharr torrent client when configured."""
        configured = list(list_configured_clients())
        if DecypharrClient.is_configured() and "torrent" not in configured:
            configured.append("torrent")
        return configured

    def _get_category_for_task(self, client: DownloadClient, task: DownloadTask) -> str | None:
        """Decypharr downloads always use their own category; others follow the base rules."""
        if isinstance(client, DecypharrClient):
            return client.category or None
        return super()._get_category_for_task(client, task)

    def post_process_cleanup(self, task: DownloadTask, *, success: bool) -> None:
        """Apply ABB_TORRENT_ACTION to Decypharr entries; defer to the base class otherwise."""
        client_ref = self._cleanup_refs.get(task.task_id)
        if client_ref is None or not isinstance(client_ref[0], DecypharrClient):
            super().post_process_cleanup(task, success=success)
            return

        self._cleanup_refs.pop(task.task_id, None)
        if not success:
            return

        client, download_id, _protocol = client_ref
        if config.get("ABB_TORRENT_ACTION", "remove") != "remove":
            return
        try:
            client.remove(download_id, delete_files=False)
        except _CLIENT_CLEANUP_ERRORS as e:
            logger.warning(
                "Failed to remove AudiobookBay download %s from %s: %s",
                download_id,
                getattr(client, "name", "client"),
                e,
            )

    def _resolve_download(
        self,
        task: DownloadTask,
        status_callback: Callable[[str, str | None], None],
    ) -> DownloadRequest | None:
        """Resolve ABB detail page into a magnet-link download request."""
        detail_url = self._resolve_detail_url(task)
        if not detail_url:
            status_callback("error", "Missing AudiobookBay details URL")
            logger.warning("Missing details URL for AudiobookBay task: %s", task.task_id)
            return None

        hostname = _resolve_allowed_detail_hostname()
        if not _detail_url_matches_host(detail_url, hostname):
            status_callback("error", "Invalid AudiobookBay details URL")
            logger.warning(
                "Rejected AudiobookBay details URL with invalid scheme or host: %s",
                detail_url,
            )
            return None

        status_callback("resolving", "Extracting magnet link")
        magnet_link = scraper.extract_magnet_link(detail_url, hostname)

        if not magnet_link:
            status_callback("error", "Failed to extract magnet link from detail page")
            return None

        logger.info("Extracted magnet link for task %s", task.task_id)

        return DownloadRequest(
            url=magnet_link,
            protocol="torrent",
            release_name=task.title or "Unknown",
            expected_hash=None,
        )

    def cancel(self, task_id: str) -> bool:
        """Cancel an in-progress download.

        Shelfmark can stop waiting via the queue cancel flag, but once a magnet has
        been sent to the torrent client we do not remove it client-side. Users must
        cancel/remove it in their torrent client UI.
        """
        logger.debug("Cancel requested for AudiobookBay task: %s", task_id)
        return False
