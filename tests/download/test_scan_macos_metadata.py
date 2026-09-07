"""Directory scans ignore macOS AppleDouble sidecars and .DS_Store (local patch)."""

from unittest.mock import patch

from shelfmark.download.postprocess.scan import is_macos_metadata_file, scan_directory_tree


def test_is_macos_metadata_file():
    assert is_macos_metadata_file("._Book.epub")
    assert is_macos_metadata_file(".DS_Store")
    assert not is_macos_metadata_file("Book.epub")
    assert not is_macos_metadata_file(".hidden.epub")


def test_scan_skips_appledouble_sidecars(tmp_path):
    (tmp_path / "Book 1.epub").write_bytes(b"epub")
    (tmp_path / "._Book 1.epub").write_bytes(b"\x00\x05\x16\x07")
    (tmp_path / ".DS_Store").write_bytes(b"ds")
    sub = tmp_path / "disc 2"
    sub.mkdir()
    (sub / "Part 02.mp3").write_bytes(b"mp3")
    (sub / "._Part 02.mp3").write_bytes(b"\x00\x05\x16\x07")

    with patch("shelfmark.download.postprocess.scan.get_supported_formats", return_value=["epub"]):
        book_files, rejected, archives, error = scan_directory_tree(tmp_path, "book")

    assert error is None
    assert [p.name for p in book_files] == ["Book 1.epub"]
    assert all(not p.name.startswith("._") for p in rejected)
    assert archives == []
