"""Benzinga's answers kept without the key or the licensed identifiers,
each dividend naming the answer it was first read from, and months moved
past their window through the SDK."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from benzinga.api import HOST, Fetched
from benzinga.raw import RawStore, name_of, without_licensed

from conftest import AT

URL = f"{HOST}/api/v2.2/calendar/dividends?parameters%5Btickers%5D=NWND"
BODY = json.dumps(
    {"dividends": [{"id": "a", "ticker": "NWND", "isin": "US9990000017", "cusip": "999000001"}]}
).encode()


def test_an_answer_is_kept_without_the_licensed_identifiers(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    key = store.keep(Fetched(URL, 200, BODY, AT))
    assert key == "responses/2026-11/20261124T150000000000Z-dividends.json.gz"
    kept = store.read(key)
    assert kept is not None and kept["url"] == URL and kept["status"] == 200
    assert json.loads(kept["body"]) == {"dividends": [{"id": "a", "ticker": "NWND"}]}
    assert store.read("../outside.json.gz") is None
    assert name_of("/api/v2.2/calendar/dividends?x=1") == "dividends"
    # An answer that lists no row is kept as received.
    assert without_licensed(b'{"ok": false}') == '{"ok": false}'
    assert without_licensed(b"<html>") == "<html>"


def test_a_dividend_names_the_answer_it_was_first_read_from(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    first = store.keep(Fetched(URL, 200, b"{}", AT))
    later = store.keep(Fetched(URL, 200, b"{}", AT + timedelta(hours=1)))
    assert store.first("a@1", "2026-11", first) == (first, True)
    assert store.first("a@1", "2026-11", later) == (first, False)
    # Updated by Benzinga, it is a new version, first read from its own answer.
    assert store.first("a@2", "2026-11", later) == (later, True)
    store.save_firsts()
    again = RawStore(tmp_path)
    assert again.first("a@1", "2026-11", later) == (first, False)


class Plugin:
    def __init__(self) -> None:
        self.moved: list[tuple[str, str]] = []
        self.stored: list[Any] = []

    async def archive_unit(self, kind: str, unit: str, **_: Any) -> None:
        self.moved.append(("archived", unit))

    async def delete_unit(self, kind: str, unit: str, **_: Any) -> None:
        self.moved.append(("deleted", unit))


async def test_months_past_the_window_are_moved(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store._given, store._root, store._granted = tmp_path, tmp_path, True
    old = datetime(2025, 1, 5, tzinfo=UTC)
    store.keep(Fetched(URL, 200, b"{}", old))
    store.keep(Fetched(URL, 200, b"{}", AT))
    plugin = Plugin()
    done = await store.tend(plugin, 30, "archived", AT)  # type: ignore[arg-type]
    assert done["archived"] == 1 and plugin.moved == [("archived", "responses/2025-01")]
    assert plugin.stored[0].record_count == 2
    kept = await store.tend(Plugin(), 30, "kept", AT)  # type: ignore[arg-type]
    assert kept["kept"] == 1
