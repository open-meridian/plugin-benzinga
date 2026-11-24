"""Benzinga's licensed identifiers and the key never leave the plugin: no
operation it sends holds an ISIN or a CUSIP, no answer it keeps holds
either, and no answer it keeps, no address and no page holds the key."""

from __future__ import annotations

import gzip
from pathlib import Path

from meridian.suites import Recorder

from benzinga.api import Fetched, LiveApi, dividends_url
from benzinga.limits import Limiter

from conftest import AT, CONTOSO, FABRIKAM, KEY, LICENSED, NORTHWIND, feed, lake, want


def _everything_sent(recorder: Recorder) -> str:
    """Every operation the plugin sent, each as its bytes and its text."""
    held = []
    for sent in recorder.sent:
        params = sent.params
        held.append(str(params))
        held.append(params.SerializeToString().decode("latin-1"))
    return "\n".join(held)


async def test_no_isin_or_cusip_is_sent_or_kept(tmp_path: Path) -> None:
    recorder = lake()
    work = feed(tmp_path, recorder, watchlist=[NORTHWIND, CONTOSO])
    await work.check()
    await work.on_observations_wanted(want("w-1", ["INS-FABRIKAM"], day="2026-11-12"))
    assert recorder.on("RecordCorporateActions"), "something was recorded"
    assert recorder.on("ResolveIdentifier"), "something was resolved"
    bus = _everything_sent(recorder)
    for identifier in LICENSED:
        assert identifier not in bus
    kept = [gzip.decompress(p.read_bytes()).decode() for p in tmp_path.rglob("*.json.gz")]
    assert kept and all(identifier not in k for k in kept for identifier in LICENSED)
    assert all('"isin"' not in k and '"cusip"' not in k for k in kept)
    firsts = "".join(p.read_text() for p in (tmp_path / "firsts").glob("*.json"))
    assert all(identifier not in firsts for identifier in LICENSED)
    assert FABRIKAM in work.status.tickers


def test_the_key_is_never_in_an_address_the_plugin_holds() -> None:
    url = dividends_url([NORTHWIND], AT.date(), AT.date())
    assert "token" not in url
    live = LiveApi(KEY, Limiter())
    assert KEY not in repr(live.__dict__.get("limiter"))
    fetched = Fetched(url, 401, b"{}", AT)
    assert KEY not in fetched.url and KEY not in fetched.error
