"""AudiobookBay settings registration."""

from __future__ import annotations

from typing import Any

from shelfmark.core.settings_registry import (
    ActionButton,
    CheckboxField,
    NumberField,
    PasswordField,
    SelectField,
    SettingsField,
    TagListField,
    TextField,
    register_settings,
)
from shelfmark.core.utils import normalize_http_url
from shelfmark.download.clients.settings import (
    _QBITTORRENT_SETTINGS_ERRORS,
    _QBittorrentLoginFailed,
    _resolve_string_setting,
)
from shelfmark.download.network import get_ssl_verify

_ABB_ON = {"field": "ABB_ENABLED", "value": True}
_DECYPHARR_ON = [_ABB_ON, {"field": "ABB_DECYPHARR_ENABLED", "value": True}]


def _test_decypharr_connection(current_values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Test the AudiobookBay Decypharr connection using current form values."""
    from shelfmark.core.config import config

    current_values = current_values or {}

    raw_url = _resolve_string_setting(current_values, config.get, "ABB_DECYPHARR_URL")
    username = _resolve_string_setting(current_values, config.get, "ABB_DECYPHARR_USERNAME")
    password = _resolve_string_setting(current_values, config.get, "ABB_DECYPHARR_PASSWORD")
    api_key = _resolve_string_setting(current_values, config.get, "ABB_DECYPHARR_API_KEY")

    if not raw_url:
        return {"success": False, "message": "Decypharr URL is required"}

    try:
        from qbittorrentapi import Client

        url = normalize_http_url(raw_url)
        if not url:
            return {"success": False, "message": "Decypharr URL is invalid"}

        client = Client(
            host=url,
            username=username,
            password=password,
            api_key=api_key or None,
            VERIFY_WEBUI_CERTIFICATE=get_ssl_verify(url),
        )
        client.auth_log_in()
        api_version = client.app.web_api_version
    except ImportError:
        return {"success": False, "message": "qbittorrent-api package not installed"}
    except _QBITTORRENT_SETTINGS_ERRORS as e:
        if isinstance(e, _QBittorrentLoginFailed):
            rejected = "API key" if api_key else "username or password"
            return {"success": False, "message": f"Decypharr rejected the {rejected}"}
        return {"success": False, "message": f"Connection failed: {e!s}"}
    else:
        return {
            "success": True,
            "message": f"Connected to Decypharr (qBittorrent API v{api_version})",
        }


# ==================== Register Settings ====================


@register_settings("audiobookbay_config", "AudiobookBay", icon="download", order=45)
def audiobookbay_config_settings() -> list[SettingsField]:
    """AudiobookBay configuration settings."""
    return [
        CheckboxField(
            key="ABB_ENABLED",
            label="Enable AudiobookBay",
            description="Enable AudiobookBay as a release source for audiobooks.",
            default=False,
        ),
        TextField(
            key="ABB_HOSTNAME",
            label="Hostname",
            description="AudiobookBay domain (e.g., audiobookbay.lu, audiobookbay.is). Required to enable searches.",
            default="",
            required=True,
            show_when=_ABB_ON,
        ),
        NumberField(
            key="ABB_PAGE_LIMIT",
            label="Max Pages to Search",
            description="Maximum number of search result pages to fetch (1-10).",
            default=1,
            min_value=1,
            max_value=10,
            show_when=_ABB_ON,
        ),
        CheckboxField(
            key="ABB_EXACT_PHRASE",
            label="Prefer Exact-Phrase Search",
            description="Wrap generated queries in quotes for stricter matching. If no results are found, Shelfmark retries without quotes.",
            show_when=_ABB_ON,
        ),
        NumberField(
            key="ABB_RATE_LIMIT_DELAY",
            label="Rate Limit Delay (seconds)",
            description="Delay between requests in seconds to avoid rate limiting (0-10).",
            default=1.0,
            min_value=0.0,
            max_value=10.0,
            show_when=_ABB_ON,
        ),
        # ---- Dedicated debrid client (local patch) ----
        CheckboxField(
            key="ABB_DECYPHARR_ENABLED",
            label="Use Decypharr for AudiobookBay",
            description=(
                "Send AudiobookBay magnets to a dedicated qBittorrent-compatible debrid client "
                "(Decypharr) instead of the global torrent client configured under Download Clients."
            ),
            default=False,
            show_when=_ABB_ON,
        ),
        TextField(
            key="ABB_DECYPHARR_URL",
            label="Decypharr URL",
            description="Web UI URL of your Decypharr instance (e.g. http://decypharr:8282).",
            default="",
            required=True,
            show_when=_DECYPHARR_ON,
        ),
        TextField(
            key="ABB_DECYPHARR_USERNAME",
            label="Username",
            description="Decypharr Web UI username.",
            default="",
            show_when=_DECYPHARR_ON,
        ),
        PasswordField(
            key="ABB_DECYPHARR_PASSWORD",
            label="Password",
            description="Decypharr Web UI password.",
            show_when=_DECYPHARR_ON,
        ),
        PasswordField(
            key="ABB_DECYPHARR_API_KEY",
            label="API Key",
            description="Optional bearer API key; used instead of username/password when set.",
            show_when=_DECYPHARR_ON,
        ),
        TextField(
            key="ABB_DECYPHARR_CATEGORY",
            label="Category",
            description=(
                "Category assigned to AudiobookBay downloads. Decypharr saves each torrent under "
                "<download folder>/<category>/, so this doubles as the staging folder name."
            ),
            default="shelfmark",
            show_when=_DECYPHARR_ON,
        ),
        TextField(
            key="ABB_DECYPHARR_DOWNLOAD_DIR",
            label="Download Directory",
            description="Optional server-side save path override (leave empty to use the Decypharr default).",
            default="",
            show_when=_DECYPHARR_ON,
        ),
        TagListField(
            key="ABB_DECYPHARR_TAG",
            label="Tags",
            description="Optional tags to assign to Decypharr downloads.",
            default=[],
            show_when=_DECYPHARR_ON,
            hidden_in_ui=True,
        ),
        SelectField(
            key="ABB_TORRENT_ACTION",
            label="Completion Action",
            description="What to do with the Decypharr entry after the files have been imported.",
            options=[
                {"value": "keep", "label": "Keep"},
                {"value": "remove", "label": "Remove"},
            ],
            default="remove",
            show_when=_DECYPHARR_ON,
        ),
        CheckboxField(
            key="ABB_MOVE_ON_IMPORT",
            label="Move Files on Import",
            description=(
                "Move AudiobookBay downloads out of the client path into the destination instead of "
                "copying them. Only sensible with a debrid client that does not seed."
            ),
            default=True,
            show_when=_DECYPHARR_ON,
        ),
        ActionButton(
            key="test_abb_decypharr",
            label="Test Connection",
            description="Verify your Decypharr configuration",
            style="primary",
            callback=_test_decypharr_connection,
            show_when=_DECYPHARR_ON,
        ),
    ]
