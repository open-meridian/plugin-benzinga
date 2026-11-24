"""The plugin's settings, declared to the SDK, and what it makes of them.

In the data role's order: no `environment` (Benzinga has one API); the
credentials; the plugin's own; then the role's sample data.

- `benzinga_api_key` -- the firm's own Benzinga key, a secret: required,
  never logged, shown or kept. While it is missing the sidecar names it, and
  while it is missing or malformed (`check_key`) the plugin asks Benzinga
  nothing and its status names the setting.
- `benzinga_requests_per_second` -- the pace, within the firm's plan: 1 to
  10, 2 by default.
- `benzinga_watchlist` -- the tickers whose dividends are pushed as they are
  announced, a typed table of one column; any other security's dividends are
  fetched when a reader wants them. The plugin never reads positions to
  choose.
- `sample_data` -- a developer's setting: the responses committed under
  responses/ in place of Benzinga, for trying the plugin offline.

The SDK declares the storage's two settings from the declaration's kind:
`responses_window_days` and `responses_past_window`. Their names are the
SDK's, and read here only. How long the lake keeps the rows, or whether it
serves them and keeps none, is the dataset's licence, set on Data sources.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import meridian

from .api import check_key
from .limits import DEFAULT_PER_SECOND, MOST_PER_SECOND, per_second
from .raw import DEFAULT_WINDOW_DAYS, RESPONSES

API_KEY = "benzinga_api_key"
PER_SECOND = "benzinga_requests_per_second"
WATCHLIST = "benzinga_watchlist"
#: The table's one column: a ticker.
TICKER = "ticker"
SAMPLE_DATA = "sample_data"
WINDOW = f"{RESPONSES}_window_days"
PAST_WINDOW = f"{RESPONSES}_past_window"
#: The most tickers the watchlist holds.
MOST_WATCHED = 500
#: A ticker as Benzinga writes one: letters, digits, a dot or a slash.
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9./-]{0,14}")


@meridian.settings
class Declared:
    """The settings as declared, in the data role's order."""

    benzinga_api_key: str = meridian.setting(
        "Benzinga API key",
        required=True,
        secret=True,
        description=(
            "Your firm's own Benzinga API key, under your firm's licence with Benzinga. "
            "Without it the plugin asks Benzinga nothing."
        ),
    )
    benzinga_requests_per_second: int = meridian.setting(
        "Requests a second",
        default=DEFAULT_PER_SECOND,
        at_least=1,
        at_most=MOST_PER_SECOND,
        unit="requests a second",
        description="How fast the plugin asks Benzinga, 1 to 10. Keep it within your plan's limit.",
    )
    benzinga_watchlist: list = meridian.setting(  # type: ignore[type-arg]
        "Watchlist",
        description=(
            "The tickers whose dividends are recorded as they are announced. Any other "
            "security's dividends are fetched when a reader wants them."
        ),
        columns=[
            meridian.Column(
                TICKER,
                kind="text",
                label="Ticker",
                required=True,
                description="The security's ticker, as Benzinga lists it",
            )
        ],
        most_rows=MOST_WATCHED,
    )
    sample_data: bool = meridian.sample_data(
        description=(
            "Serve the responses committed with the plugin instead of asking Benzinga: three "
            "fictitious companies' dividends in Benzinga's layout. Runs without a key. "
            "Development deployments only."
        )
    )


DECLARED = Declared


@dataclass(frozen=True)
class Config:
    key: str = ""
    #: Why the key will not do; empty where it will.
    key_problem: str = "is not set"
    per_second: int = DEFAULT_PER_SECOND
    watchlist: tuple[str, ...] = ()
    #: Each watchlist entry that is no ticker.
    unread: tuple[str, ...] = ()
    sample_data: bool = False
    window_days: int = DEFAULT_WINDOW_DAYS
    past_window: str = "kept"

    def __repr__(self) -> str:
        # The key is a secret: never in a log line or an error.
        return f"Config(key=<{'set' if self.key else 'unset'}>, watchlist={self.watchlist!r})"


def _watchlist(rows: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The table's tickers, trimmed, once each, in the table's order; and
    the entries that are no ticker."""
    held: list[str] = []
    unread: list[str] = []
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return (), ()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        entry = str(row.get(TICKER, "")).strip().upper()
        if not entry:
            continue
        if not _TICKER.fullmatch(entry):
            unread.append(entry[:20])
        elif entry not in held:
            held.append(entry)
    return tuple(held[:MOST_WATCHED]), tuple(unread)


def config_from(values: Mapping[str, object]) -> Config:
    """The configuration a delivery of the settings says."""
    key = values.get(API_KEY)
    rate = values.get(PER_SECOND)
    window = values.get(WINDOW)
    past = values.get(PAST_WINDOW)
    said = key.strip() if isinstance(key, str) else ""
    watchlist, unread = _watchlist(values.get(WATCHLIST))
    return Config(
        key=said,
        key_problem=check_key(said),
        per_second=per_second(rate) if isinstance(rate, int) else DEFAULT_PER_SECOND,
        watchlist=watchlist,
        unread=unread,
        sample_data=values.get(SAMPLE_DATA) is True,
        window_days=window if isinstance(window, int) and window > 0 else DEFAULT_WINDOW_DAYS,
        past_window=past if isinstance(past, str) and past else "kept",
    )
