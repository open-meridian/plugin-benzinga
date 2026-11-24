"""The plugin's pages, under Manage alone: the data role's common pages,
Connection and Datasets, each also a read tool for agents on the
deployment's MCP under the role's names (`read_connection`,
`read_datasets`). Each record is the role's (`meridian.roles.data`),
extended with Benzinga's fields; each template is the role's, with
Benzinga's nuance at its blocks or, for the Datasets tabs, its sections in
its order.

A data plugin shows its connectivity, its datasets and how its subjects
resolve, and no data:

- **Connection** (`/`): "Key" -- the mode (Live, Sample data or No key while
  the key is missing or malformed), whether the key is set (the setting
  named, its value never shown); "Limits and use" -- the pace kept and
  Benzinga's refusals; "Stream": it does not stream.
- **Datasets** (`/datasets`): the role's sections and Benzinga's as tabs,
  one shown at a time (`?view=`): "Served" and "Subjects", "Wants",
  **Tickers** (each ticker read, with the deployment's instrument or why
  none, searched), **Not recorded** (calendar rows the contract cannot
  carry yet, by why) and **Terms**.

Neither shows a dividend, the key, an ISIN or a CUSIP. Settings change
through core's tools; the pages hold no actions.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import meridian
from meridian.roles import data

from . import records
from .api import DIVIDENDS, HOST
from .declared import CATALOGUE, TERMS
from .feed import Feed, Status
from .limits import MOST_PER_SECOND
from .settings import API_KEY

TITLE = "Benzinga"
#: The kit these pages are built on.
KIT = "0.13.0"

pages = meridian.Pages(TITLE, templates=Path(__file__).parent / "templates", kit=KIT)

CONNECTION = "/"
DATASETS = "/datasets"

#: The longest search the Tickers tab reads.
MOST_QUERY = 100
#: The Datasets page's tabs, one shown at a time (`?view=`), the first by default.
VIEWS = ("served", "wants", "tickers", "not-recorded", "terms")
#: How many wants the Datasets tab lists; read_datasets answers every one held.
SHOWN_WANTS = 3
#: What Benzinga's calendar carries that this version does not record, and why.
NOT_YET = [
    "Splits: the contract records no split yet",
    "The economic calendar's actual values: the contract has no economic series or "
    "country subject yet",
    "News, earnings dates, IPOs and consensus: not in this version",
]

_held: dict[str, Feed] = {}


def hold(feed: Feed) -> None:
    """The feed the pages read, once the plugin has registered."""
    _held["feed"] = feed


def _status() -> tuple[Status, Feed | None]:
    feed = _held.get("feed")
    return (feed.status if feed is not None else Status(waiting="is not set"), feed)


def _iso(moment: datetime | None) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds") if moment else ""


def _waiting(status: Status) -> str:
    return "" if status.mode == "synthetic" else status.waiting


def _mode(status: Status) -> str:
    if status.mode == "synthetic":
        return "Sample data"
    return "No key" if status.waiting else "Live"


def _state(status: Status, feed: Feed | None) -> tuple[str, str, str]:
    """The head's status: its state, what it means, and its detail."""
    waiting = _waiting(status)
    if waiting:
        return "warn", f"Waiting for {API_KEY}", f"{API_KEY} {waiting}"
    misses = sorted(t.ticker for t in status.tickers.values() if t.miss)
    if status.error and status.read_at is None:
        return "error", "Not answering", status.error
    if status.error:
        return "warn", "Answering", status.error
    if feed is not None and not feed.watchlist and not feed.standing:
        return "ok", "Nothing kept current", "Dividends are fetched when wanted"
    if status.read_at is None:
        return "busy", "Checking Benzinga", ""
    if misses:
        plural = "ticker" if len(misses) == 1 else "tickers"
        return "warn", f"{len(misses)} {plural} not resolved", ", ".join(misses)
    if status.unread:
        said = "entry is" if len(status.unread) == 1 else "entries are"
        return "warn", f"{len(status.unread)} watchlist {said} no ticker", ", ".join(status.unread)
    return "ok", "Sample data" if status.mode == "synthetic" else "Answering", ""


def connection_read(status: Status, feed: Feed | None) -> records.ConnectionRead:
    state, said, _ = _state(status, feed)
    kept = feed.raw.keys() if feed is not None else []
    window = ""
    if feed is not None and feed.raw.granted:
        window = "in the storage the deployment grants, as its responses settings say"
    elif feed is not None:
        window = "in a directory of the plugin's own: this deployment grants no storage"
    rate = feed.api.limiter.rate if feed is not None else 0
    return records.ConnectionRead(
        mode=_mode(status),
        credentials=[data.Credential("Benzinga API key", status.waiting != "is not set")],
        entitled_at_vendor="" if _waiting(status) else "Dividends, as your firm's plan allows",
        limit=(
            f"Your firm's plan's limit, which Benzinga does not publish; this plugin asks one "
            f"at a time, at most {rate} a second, and pauses after a refusal"
        ),
        calls=status.fetches,
        rate_limited=feed.api.limiter.refused if feed is not None else 0,
        last_call_at=_iso(status.checked_at),
        last_error=status.error,
        sessions=None,
        state=state,
        said=said,
        source=(
            "The responses committed with the plugin"
            if status.mode == "synthetic"
            else f"{HOST}{DIVIDENDS}"
        ),
        checked_at=_iso(status.checked_at),
        waiting=f"{API_KEY} {_waiting(status)}" if _waiting(status) else "",
        per_second=rate,
        kept_current=len(feed.watchlist) + len(feed.standing) if feed is not None else 0,
        responses_kept=len(kept),
        kept_for=window,
    )


def _ticker_read(feed: Feed | None, held: Any) -> records.TickerRead:
    kept = feed is not None and (bool(held.entry) or held.ticker in feed.standing.values())
    return records.TickerRead(
        ticker=held.ticker,
        name=held.name,
        exchange=held.exchange,
        entry=held.entry,
        kept_current=kept,
        instrument_id=held.instrument_id,
        miss=held.miss,
        latest_ex=held.latest_ex.isoformat() if held.latest_ex else "",
        sent=held.sent,
    )


def datasets_read(status: Status, feed: Feed | None) -> records.DatasetsRead:
    instance = feed.plugin.identity.instance_id if feed is not None else "benzinga"
    entitled = (
        f"No: {API_KEY} {_waiting(status)}"
        if _waiting(status)
        else "Yes: the dividends your firm's plan allows"
    )
    return records.DatasetsRead(
        served=data.served(CATALOGUE, instance, feed.wants if feed is not None else None, entitled),
        wants=list(data.want_rows(feed.wants)) if feed is not None else [],
        reads_instruments=True,
        terms=TERMS,
        tickers=[_ticker_read(feed, t) for _, t in sorted(status.tickers.items())],
        not_recorded=[
            records.SkippedRead(reason, rows) for reason, rows in sorted(status.skipped.items())
        ],
        unread=list(status.unread),
        not_yet=list(NOT_YET),
    )


def figures(status: Status, feed: Feed | None) -> list[meridian.Figure]:
    """The data role's figures, in its order (`meridian.roles.data`)."""
    state, said, why = _state(status, feed)
    if status.mode == "synthetic" and state == "ok":
        connection: Any = "Sample data"
    elif _waiting(status) or said == "Not answering":
        connection = meridian.Figure(
            "", said, state="error" if state == "error" else "warn", why=why[:200]
        )
    else:
        connection = meridian.Figure(
            "", "Answering", state="warn" if status.error else None, why=status.error[:200]
        )
    last = feed.wants.counts.last_ns if feed is not None else 0
    rate = feed.api.limiter.rate if feed is not None else 0
    return data.figures(
        connection=connection,
        entitled_at_vendor=(
            f"0 of 1 datasets: {API_KEY} {_waiting(status)}"
            if _waiting(status)
            else "1 of 1 datasets"
        ),
        stream="Does not stream",
        last_recorded=(datetime.fromtimestamp(last / 10**9, UTC) if last else None),
        rate_use=f"at most {rate} of {MOST_PER_SECOND} a second",
    )


def _moment(value: str) -> str:
    """An ISO moment as a person reads it, to the minute in UTC."""
    if not value:
        return ""
    if len(value) == 10:
        return value
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _weekday(value: str) -> str:
    return date.fromisoformat(value).strftime("%a %d %b %Y") if value else ""


def matching(query: str, *texts: str) -> bool:
    """Whether every word of a search is in one of `texts`, case aside."""
    words = query.lower().split()
    held = " ".join(texts).lower()
    return all(word in held for word in words)


pages.environment.filters["moment"] = _moment
pages.environment.filters["day"] = _weekday


@pages.page(
    CONNECTION,
    "Connection",
    levels="admin",
    answers=records.ConnectionRead,
    name="read_connection",
    description=(
        "How this plugin reaches Benzinga, as every data plugin's Connection answers it: the "
        "mode (Live, Sample data, or No key while benzinga_api_key is missing or malformed), "
        "whether the key is set (never its value), what Benzinga serves, the pace kept within "
        "the firm's plan, the requests made and Benzinga's refusals, the last call and why it "
        "failed if it did; it does not stream. Then how many tickers are kept current and how "
        "many answers are kept. No dividend."
    ),
)
async def connection(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = connection_read(status, feed)
    return pages.answer("connection.html", read, detail=_state(status, feed)[2])


@pages.page(
    DATASETS,
    "Datasets",
    levels="admin",
    answers=records.DatasetsRead,
    name="read_datasets",
    description=(
        "What this plugin serves the lake, as every data plugin's Datasets answers it: "
        "benzinga_dividends as the catalogue declares it (cash dividends from Benzinga's "
        "calendar, pushed for the watchlist and pulled when wanted; New York's day; no "
        "calendar), whether a deployment admin has licensed it, what it recorded and declined; "
        "the standing wants it keeps current and the wants it answered. Then Benzinga's own: "
        "its terms in words, each ticker read with the deployment's instrument or why there is "
        "none, calendar rows not recorded and why, each watchlist entry that is no ticker, and "
        "what Benzinga serves that waits for the contract. No dividend."
    ),
)
async def datasets(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = datasets_read(status, feed)
    # A browser's search narrows the tickers drawn, and it is drawn the latest
    # wants; a tool answers them all.
    query = request.query.get("q", "").strip()[:MOST_QUERY]
    asked = request.query.get("view", "")
    view = "tickers" if query else asked if asked in VIEWS else VIEWS[0]
    shown = [t for t in read.tickers if matching(query, t.ticker, t.name, t.exchange)]
    drawn = read if request.tool_name else replace(read, wants=read.wants[:SHOWN_WANTS])
    return pages.answer(
        "datasets.html",
        drawn,
        query=query,
        view=view,
        shown=shown,
        state=_state(status, feed),
        checked_at=_iso(status.checked_at),
        wants=len(read.wants),
    )
