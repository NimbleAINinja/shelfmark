"""Tests for the AudiobookBay-only Decypharr client wiring (local patch)."""

from unittest.mock import MagicMock, patch

from shelfmark.core.models import DownloadTask
from shelfmark.download.clients.decypharr import DecypharrClient
from shelfmark.release_sources.audiobookbay.handler import AudiobookBayHandler


def _decypharr_instance(category: str = "shelfmark") -> DecypharrClient:
    client = DecypharrClient.__new__(DecypharrClient)
    client._category = category
    client.remove = MagicMock(return_value=True)
    return client


def _task(source: str = "audiobookbay") -> DownloadTask:
    return DownloadTask(
        task_id="abb-task",
        source=source,
        title="Book",
        author="Author",
        format="mp3",
        content_type="audiobook",
    )


class TestDecypharrClientConfig:
    def test_is_configured_requires_enabled_and_url(self, monkeypatch):
        values = {"ABB_DECYPHARR_ENABLED": True, "ABB_DECYPHARR_URL": "http://decypharr:8282"}
        monkeypatch.setattr(
            "shelfmark.download.clients.decypharr.config.get",
            lambda key, default="": values.get(key, default),
        )
        assert DecypharrClient.is_configured() is True

        values["ABB_DECYPHARR_ENABLED"] = False
        assert DecypharrClient.is_configured() is False

        values["ABB_DECYPHARR_ENABLED"] = True
        values["ABB_DECYPHARR_URL"] = ""
        assert DecypharrClient.is_configured() is False

    def test_reads_its_own_namespace_not_the_global_qbittorrent_keys(self, monkeypatch):
        values = {
            "QBITTORRENT_URL": "http://qbit:8080",
            "QBITTORRENT_CATEGORY": "eBook",
            "ABB_DECYPHARR_URL": "http://decypharr:8282",
            "ABB_DECYPHARR_USERNAME": "graham",
            "ABB_DECYPHARR_PASSWORD": "secret",
            "ABB_DECYPHARR_CATEGORY": "shelfmark",
        }
        monkeypatch.setattr(
            "shelfmark.download.clients.qbittorrent.config.get",
            lambda key, default="": values.get(key, default),
        )
        fake_client_cls = MagicMock()
        with patch.dict("sys.modules", {"qbittorrentapi": MagicMock(Client=fake_client_cls)}):
            client = DecypharrClient()

        assert client.name == "decypharr"
        assert client.category == "shelfmark"
        assert client._base_url.startswith("http://decypharr:8282")
        kwargs = fake_client_cls.call_args.kwargs
        assert kwargs["host"].startswith("http://decypharr:8282")
        assert kwargs["username"] == "graham"
        assert kwargs["password"] == "secret"

    def test_global_qbittorrent_client_still_reads_global_keys(self, monkeypatch):
        from shelfmark.download.clients.qbittorrent import QBittorrentClient

        values = {"QBITTORRENT_URL": "http://qbit:8080", "QBITTORRENT_CATEGORY": "eBook"}
        monkeypatch.setattr(
            "shelfmark.download.clients.qbittorrent.config.get",
            lambda key, default="": values.get(key, default),
        )
        fake_client_cls = MagicMock()
        with patch.dict("sys.modules", {"qbittorrentapi": MagicMock(Client=fake_client_cls)}):
            client = QBittorrentClient()
        assert client._category == "eBook"
        assert fake_client_cls.call_args.kwargs["host"].startswith("http://qbit:8080")


class TestHandlerClientSelection:
    @patch("shelfmark.release_sources.audiobookbay.handler.get_client")
    @patch("shelfmark.release_sources.audiobookbay.handler.DecypharrClient")
    def test_prefers_decypharr_when_configured(self, mock_decypharr, mock_get_client):
        mock_decypharr.is_configured.return_value = True
        handler = AudiobookBayHandler()
        assert handler._get_client("torrent") is mock_decypharr.return_value
        mock_get_client.assert_not_called()

    @patch("shelfmark.release_sources.audiobookbay.handler.get_client")
    @patch("shelfmark.release_sources.audiobookbay.handler.DecypharrClient")
    def test_falls_back_to_shared_client(self, mock_decypharr, mock_get_client):
        mock_decypharr.is_configured.return_value = False
        handler = AudiobookBayHandler()
        assert handler._get_client("torrent") is mock_get_client.return_value
        mock_get_client.assert_called_once_with("torrent")

    @patch(
        "shelfmark.release_sources.audiobookbay.handler.list_configured_clients", return_value=[]
    )
    @patch("shelfmark.release_sources.audiobookbay.handler.DecypharrClient")
    def test_lists_torrent_when_only_decypharr_is_configured(self, mock_decypharr, _mock_list):
        mock_decypharr.is_configured.return_value = True
        assert AudiobookBayHandler()._list_configured_clients() == ["torrent"]

    def test_category_comes_from_decypharr_config(self):
        handler = AudiobookBayHandler()
        assert handler._get_category_for_task(_decypharr_instance("stage"), _task()) == "stage"

    def test_category_for_other_clients_uses_base_rules(self, monkeypatch):
        monkeypatch.setattr(
            "shelfmark.download.clients.base_handler.config.get",
            lambda key, default="": {"QBITTORRENT_CATEGORY_AUDIOBOOK": "Audiobook"}.get(
                key, default
            ),
        )
        client = MagicMock()
        client.name = "qbittorrent"
        assert AudiobookBayHandler()._get_category_for_task(client, _task()) == "Audiobook"


class TestHandlerCleanup:
    def test_remove_action_removes_entry_but_keeps_files(self, monkeypatch):
        monkeypatch.setattr(
            "shelfmark.release_sources.audiobookbay.handler.config.get",
            lambda key, default="": {"ABB_TORRENT_ACTION": "remove"}.get(key, default),
        )
        handler = AudiobookBayHandler()
        client = _decypharr_instance()
        task = _task()
        handler._cleanup_refs[task.task_id] = (client, "hash123", "torrent")

        handler.post_process_cleanup(task, success=True)

        client.remove.assert_called_once_with("hash123", delete_files=False)
        assert task.task_id not in handler._cleanup_refs

    def test_keep_action_leaves_entry(self, monkeypatch):
        monkeypatch.setattr(
            "shelfmark.release_sources.audiobookbay.handler.config.get",
            lambda key, default="": {"ABB_TORRENT_ACTION": "keep"}.get(key, default),
        )
        handler = AudiobookBayHandler()
        client = _decypharr_instance()
        task = _task()
        handler._cleanup_refs[task.task_id] = (client, "hash123", "torrent")

        handler.post_process_cleanup(task, success=True)

        client.remove.assert_not_called()
        assert task.task_id not in handler._cleanup_refs

    def test_failure_never_removes(self, monkeypatch):
        monkeypatch.setattr(
            "shelfmark.release_sources.audiobookbay.handler.config.get",
            lambda key, default="": {"ABB_TORRENT_ACTION": "remove"}.get(key, default),
        )
        handler = AudiobookBayHandler()
        client = _decypharr_instance()
        task = _task()
        handler._cleanup_refs[task.task_id] = (client, "hash123", "torrent")

        handler.post_process_cleanup(task, success=False)

        client.remove.assert_not_called()
        assert task.task_id not in handler._cleanup_refs

    def test_shared_client_follows_global_torrent_action(self, monkeypatch):
        monkeypatch.setattr(
            "shelfmark.download.clients.base_handler.config.get",
            lambda key, default="": {"PROWLARR_TORRENT_ACTION": "keep"}.get(key, default),
        )
        handler = AudiobookBayHandler()
        client = MagicMock()
        client.name = "qbittorrent"
        task = _task()
        handler._cleanup_refs[task.task_id] = (client, "hash123", "torrent")

        handler.post_process_cleanup(task, success=True)

        client.remove.assert_not_called()
        assert task.task_id not in handler._cleanup_refs
