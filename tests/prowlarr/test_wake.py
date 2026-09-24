"""Tests for waking an on-demand Prowlarr when the UI connects."""

from unittest.mock import patch

import pytest
import requests

from shelfmark.release_sources.prowlarr import wake


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(wake, "_last_wake", None)
    monkeypatch.setenv("PROWLARR_WAKE_ON_CONNECT", "true")
    settings = {"PROWLARR_ENABLED": True, "PROWLARR_URL": "http://prowlarr:9696/"}
    monkeypatch.setattr(wake.config, "get", lambda key, default=None: settings.get(key, default))
    return settings


class _SyncThread:
    """Runs the target inline so tests can assert on the ping."""

    def __init__(self, target, args=(), **_kwargs):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


@pytest.fixture
def pings(monkeypatch):
    calls = []
    monkeypatch.setattr(wake.threading, "Thread", _SyncThread)
    monkeypatch.setattr(
        wake.requests,
        "get",
        lambda url, timeout: calls.append((url, timeout)) or type("R", (), {"status_code": 200}),
    )
    return calls


def test_pings_prowlarr_ping_endpoint(pings):
    assert wake.wake_async(now=100.0) is True
    assert pings == [("http://prowlarr:9696/ping", wake._PING_TIMEOUT_SECONDS)]


def test_off_by_default(monkeypatch, pings):
    monkeypatch.delenv("PROWLARR_WAKE_ON_CONNECT")
    assert wake.wake_async(now=100.0) is False
    assert pings == []


def test_skipped_when_prowlarr_disabled(_reset, pings):
    _reset["PROWLARR_ENABLED"] = False
    assert wake.wake_async(now=100.0) is False
    assert pings == []


def test_skipped_without_url(_reset, pings):
    _reset["PROWLARR_URL"] = ""
    assert wake.wake_async(now=100.0) is False
    assert pings == []


def test_throttled_within_interval(pings):
    assert wake.wake_async(now=100.0) is True
    assert wake.wake_async(now=100.0 + wake._MIN_INTERVAL_SECONDS - 1) is False
    assert wake.wake_async(now=100.0 + wake._MIN_INTERVAL_SECONDS) is True
    assert len(pings) == 2


def test_ping_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(wake.threading, "Thread", _SyncThread)

    def boom(url, timeout):
        raise requests.ConnectionError("down")

    with patch.object(wake.requests, "get", boom):
        assert wake.wake_async(now=100.0) is True
