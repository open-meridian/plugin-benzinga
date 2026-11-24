"""The typed records the pages answer, for a person's page and an agent's
tool alike: the data role's common records (`meridian.roles.data`), each
extended with Benzinga's own fields -- Connection's pace and kept answers,
and Datasets' **Tickers** and what was **Not recorded**. The Connection tab
is `read_connection`, the Datasets tab `read_datasets`, each answering what
its page shows.

A data plugin's pages show its connection and its datasets, never the data:
dividends are the reading roles' to show. So neither record holds a
dividend, and neither holds the key, an ISIN or a CUSIP.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meridian.roles import data


@dataclass(frozen=True)
class ConnectionRead(data.ConnectionRead):
    """Connection's common fields, then Benzinga's: the head's status and
    what it means, where it reads, the last check, why it waits (the key's
    problem, naming the setting), the pace kept and Benzinga's refusals, how
    many tickers are kept current, and the answers kept."""

    state: str = ""
    said: str = ""
    source: str = ""
    checked_at: str = ""
    waiting: str = ""
    per_second: int = 0
    kept_current: int = 0
    responses_kept: int = 0
    kept_for: str = ""


@dataclass(frozen=True)
class TickerRead:
    """One ticker the plugin reads, as "Tickers" lists it: Benzinga's name
    and exchange, the watchlist entry naming it, whether it is kept current,
    the deployment's instrument or why there is none, its latest ex-date,
    and the dividends sent since start."""

    ticker: str
    name: str = ""
    exchange: str = ""
    entry: str = ""
    kept_current: bool = False
    instrument_id: str = ""
    miss: str = ""
    latest_ex: str = ""
    sent: int = 0


@dataclass(frozen=True)
class SkippedRead:
    """Calendar rows not recorded since start, for one reason."""

    reason: str
    rows: int


@dataclass(frozen=True)
class DatasetsRead(data.DatasetsRead):
    """Datasets' common fields, then Benzinga's: its terms in words, each
    ticker it reads ("Tickers"), the rows not recorded and why, each
    watchlist entry that is no ticker, and what waits for the contract."""

    served: list[data.Served] = field(default_factory=list)
    wants: list[data.WantHeard] = field(default_factory=list)  # type: ignore[assignment]
    terms: str = ""
    tickers: list[TickerRead] = field(default_factory=list)
    not_recorded: list[SkippedRead] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)
    not_yet: list[str] = field(default_factory=list)
