"""The two pages under Manage, and their read tools: what each shows, to
whom, that a tool answers what its page shows, that a missing key is named,
and that no dividend, key, ISIN or CUSIP is shown."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from meridian.testing import PageClient

from benzinga import page as page_module
from benzinga.api import SyntheticApi
from benzinga.page import CONNECTION, DATASETS, figures, hold, pages

from conftest import AT, CONTOSO, DIVIDENDS, FABRIKAM, KEY, LICENSED, NORTHWIND, feed, lake, want

#: Amounts the committed responses hold, none of which a page may show.
AMOUNTS = ("0.2600", "1.1500", "0.4400")


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    work = feed(tmp_path, watchlist=[NORTHWIND, CONTOSO])

    async def run() -> None:
        await work.check()
        await work.on_observations_wanted(want("w-day", ["INS-FABRIKAM"], day="2026-11-12"))
        await work.on_observations_wanted(want("w-standing", ["INS-FABRIKAM"], standing=True))

    asyncio.run(run())
    hold(work)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        (CONNECTION, "admin"): 200,
        (CONNECTION, "write"): 403,
        (CONNECTION, "read"): 403,
        (DATASETS, "admin"): 200,
        (DATASETS, "write"): 403,
        (DATASETS, "read"): 403,
    }
    # No dividend on any page: dividends are the reading roles' to show.
    client.assert_no_account_data(*AMOUNTS)


def test_no_page_or_tool_shows_a_licensed_identifier(client: PageClient) -> None:
    for path in (CONNECTION, DATASETS):
        for view in ("", "served", "wants", "tickers", "not-recorded", "terms"):
            text = client.get(path, "admin", view=view).text
            assert all(identifier not in text for identifier in LICENSED)
    for tool in ("read_connection", "read_datasets"):
        held = str(client.call_tool(tool).json)
        assert all(identifier not in held for identifier in LICENSED)


def test_connection_says_how_benzinga_is_reached(client: PageClient) -> None:
    text = client.get(CONNECTION, "admin").text
    assert text.index("<h2>Key</h2>") < text.index("<tr data-source>") < text.index("<h2>Limits")
    assert "Benzinga API key: set" in text
    assert "Kept current: 3 tickers" in text  # two entries, one standing want
    assert "at most 2 a second" in text
    assert 'href="/.meridian/ui/0.13.0/meridian.css"' in text


def test_datasets_lists_the_dataset_and_its_tickers(client: PageClient) -> None:
    text = client.get(DATASETS, "admin").text
    tabs = ["Served <span", "Wants <span", "Tickers <span", "Not recorded <span", ">Terms</a>"]
    assert [text.index(t) for t in tabs] == sorted(text.index(t) for t in tabs)
    assert DIVIDENDS in text and "<h2>Subjects</h2>" in text
    tickers = client.get(DATASETS, "admin", view="tickers").text
    assert tickers.count("<tr data-ticker=") == 3
    assert "INS-NORTHWIND" in tickers and "Thu 12 Nov 2026" in tickers
    skipped = client.get(DATASETS, "admin", view="not-recorded").text
    assert "not a cash dividend" in skipped and "a date not stated" in skipped
    assert "Splits" in skipped
    terms = client.get(DATASETS, "admin", view="terms").text
    assert "own licence" in terms and "Not affiliated" in terms


def test_the_tickers_are_searched(client: PageClient) -> None:
    text = client.get(DATASETS, "admin", q="northwind").text
    assert f'data-ticker="{NORTHWIND}"' in text and f'data-ticker="{CONTOSO}"' not in text
    assert len(client.call_tool("read_datasets").data["tickers"]) == 3


def test_the_tools_answer_what_the_pages_show(client: PageClient) -> None:
    assert {t.name for t in pages.tools} == {"read_connection", "read_datasets"}
    data = client.call_tool("read_connection").data
    assert data["mode"] == "Sample data" and data["sessions"] is None
    assert data["kept_current"] == 3 and data["per_second"] == 2
    read = client.call_tool("read_datasets").data
    assert [s["dataset"] for s in read["served"]] == [DIVIDENDS]
    assert read["served"][0]["recorded"] == 4  # three pushed, one wanted
    tickers = {t["ticker"]: t for t in read["tickers"]}
    assert tickers[NORTHWIND]["entry"] == NORTHWIND and tickers[NORTHWIND]["kept_current"]
    assert tickers[FABRIKAM]["entry"] == "" and tickers[FABRIKAM]["kept_current"]
    assert tickers[FABRIKAM]["sent"] == 2  # once for each want, the second unchanged
    assert {s["reason"]: s["rows"] for s in read["not_recorded"]} == {
        "a date not stated": 1, "not a cash dividend": 1
    }  # fmt: skip
    assert read["wants"][0]["want_id"] == "w-standing"


def test_a_missing_key_is_named(tmp_path: Path) -> None:
    api = SyntheticApi(lambda: AT)
    api.mode = "live"
    work = feed(tmp_path, lake(), api=api, waiting="is not set")
    hold(work)
    client = PageClient(pages)
    text = client.get(CONNECTION, "admin").text
    assert "Waiting for benzinga_api_key" in text
    data = client.call_tool("read_connection").data
    assert data["mode"] == "No key" and data["waiting"] == "benzinga_api_key is not set"
    assert data["credentials"] == [{"label": "Benzinga API key", "set": False}]
    said = figures(work.status, work)
    assert said[0].value == "Waiting for benzinga_api_key" and said[0].state == "warn"
    assert said[1].value == "0 of 1 datasets: benzinga_api_key is not set"


def test_the_key_is_never_shown(tmp_path: Path) -> None:
    work = feed(tmp_path, watchlist=[CONTOSO])
    asyncio.run(work.check())
    hold(work)
    client = PageClient(pages)
    for path in (CONNECTION, DATASETS):
        assert KEY not in client.get(path, "admin").text
    assert KEY not in str(client.call_tool("read_connection").json)


def test_before_the_first_check() -> None:
    page_module._held.clear()
    client = PageClient(pages)
    assert "Waiting for benzinga_api_key" in client.get(CONNECTION, "admin").text
    assert client.get(DATASETS, "admin", view="tickers").status == 200


def test_the_figures_are_the_data_roles_in_its_order(client: PageClient) -> None:
    work = page_module._held["feed"]
    said = figures(work.status, work)
    assert [f.label for f in said] == [
        "Connection",
        "Entitled at the vendor",
        "Stream",
        "Last recorded",
        "Rate use",
    ]
    assert said[1].value == "1 of 1 datasets" and said[2].value == "Does not stream"
    assert said[4].value == "at most 2 of 10 a second"
