"""Folder output: AudiobookBay releases may be moved out of the client path (local patch)."""

from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from shelfmark.core.models import DownloadTask, SearchMode
from shelfmark.download.postprocess.router import post_process_download


def _config_mock(library_path: str, *, move: bool):
    return MagicMock(
        side_effect=lambda key, default=None, **_kwargs: {
            "DESTINATION": library_path,
            "DESTINATION_AUDIOBOOK": library_path,
            "TEMPLATE_ORGANIZE": "{Author}/{Title}",
            "TEMPLATE_AUDIOBOOK_ORGANIZE": "{Author}/{Title}{ - PartNumber}",
            "TEMPLATE_AUDIOBOOK_RENAME": "{Author} - {Title}",
            "FILE_ORGANIZATION": "organize",
            "FILE_ORGANIZATION_AUDIOBOOK": "organize",
            "HARDLINK_TORRENTS": False,
            "HARDLINK_TORRENTS_AUDIOBOOK": False,
            "SUPPORTED_FORMATS": ["epub", "mobi"],
            "SUPPORTED_AUDIOBOOK_FORMATS": ["mp3", "m4b"],
            "ABB_MOVE_ON_IMPORT": move,
        }.get(key, default)
    )


def _make_torrent_dir(tmp_path):
    torrent_dir = tmp_path / "client" / "shelfmark" / "Some Audiobook"
    (torrent_dir / "disc 2").mkdir(parents=True)
    files = [torrent_dir / "Part 01.mp3", torrent_dir / "disc 2" / "Part 02.mp3"]
    for f in files:
        f.write_bytes(b"ID3" + b"audio" * 100)
    return torrent_dir, files


def _task(source: str, torrent_dir) -> DownloadTask:
    return DownloadTask(
        task_id=f"{source}-001",
        source=source,
        title="Some Audiobook",
        author="Some Author",
        format="mp3",
        content_type="audiobook",
        search_mode=SearchMode.UNIVERSAL,
        original_download_path=str(torrent_dir),
    )


def _run(torrent_dir, task, library, *, move: bool):
    with patch("shelfmark.core.config.config") as cfg:
        cfg.get = _config_mock(str(library), move=move)
        cfg.CUSTOM_SCRIPT = None
        return post_process_download(
            torrent_dir, task, Event(), MagicMock(), preserve_source_on_failure=True
        )


class TestAudiobookBayMoveOnImport:
    def test_audiobookbay_moves_and_prunes_client_dir(self, tmp_path):
        torrent_dir, files = _make_torrent_dir(tmp_path)
        library = tmp_path / "library"
        library.mkdir()

        result = _run(torrent_dir, _task("audiobookbay", torrent_dir), library, move=True)

        assert result is not None
        assert len(list((library / "Some Author").glob("*.mp3"))) == 2
        for f in files:
            assert not f.exists(), f"{f.name} was copied instead of moved"
        assert not torrent_dir.exists(), "emptied client directory should be pruned"
        # The parent (Decypharr's category folder) is never touched.
        assert torrent_dir.parent.exists()

    def test_audiobookbay_copies_when_switch_off(self, tmp_path):
        torrent_dir, files = _make_torrent_dir(tmp_path)
        library = tmp_path / "library"
        library.mkdir()

        result = _run(torrent_dir, _task("audiobookbay", torrent_dir), library, move=False)

        assert result is not None
        assert len(list((library / "Some Author").glob("*.mp3"))) == 2
        for f in files:
            assert f.exists()

    @pytest.mark.parametrize("source", ["prowlarr", "direct_download"])
    def test_other_sources_ignore_the_switch(self, tmp_path, source):
        torrent_dir, files = _make_torrent_dir(tmp_path)
        library = tmp_path / "library"
        library.mkdir()

        result = _run(torrent_dir, _task(source, torrent_dir), library, move=True)

        assert result is not None
        assert len(list((library / "Some Author").glob("*.mp3"))) == 2
        for f in files:
            assert f.exists(), f"{source} torrent source {f.name} must be preserved for seeding"
        assert torrent_dir.exists()

    def test_leftover_files_keep_the_client_dir(self, tmp_path):
        torrent_dir, files = _make_torrent_dir(tmp_path)
        (torrent_dir / "cover.jpg").write_bytes(b"jpg")
        library = tmp_path / "library"
        library.mkdir()

        result = _run(torrent_dir, _task("audiobookbay", torrent_dir), library, move=True)

        assert result is not None
        for f in files:
            assert not f.exists()
        assert (torrent_dir / "cover.jpg").exists()
        assert torrent_dir.exists()
        assert not (torrent_dir / "disc 2").exists()
