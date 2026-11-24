"""Benzinga's dividends calendar into the lake: the watchlist's tickers'
dividends recorded as they are announced, and any security's recorded when
the lake wants them, as `CorporateActionAnnounced` rows (contract v28).

**Push.** At start and every hour, the tickers kept current -- the
`benzinga_watchlist` setting's, and a standing want's -- have their
dividends read, from 90 days back to a year ahead, and each dividend not yet
sent in this process, or updated by Benzinga since, is recorded. The lake
answers a row it holds unchanged, so nothing is kept between starts but the
answers in storage: a restart sends the dividends again, each naming the
answer it was first read from, and the lake changes nothing.

**A dividend.** One row, keyed by Benzinga's ID, kind cash dividend: the
amount per share in the currency Benzinga states, and the declared, ex,
record and payment dates as Benzinga states them. Its valid time is the
declared day's start in New York, its published time Benzinga's last update.
Each row names the rule that read it (`RULE`): this plugin's reading of
Benzinga's calendar row, never a date or an amount worked out here. A row
is recorded only where Benzinga states all of it; otherwise it is counted,
with why (`Skipped`):

- a dividend that is not cash (`dividend_type` stock, say): the contract
  records cash dividends only;
- a date Benzinga leaves empty, or an amount or currency that does not read.

**The security.** A row names its security by ticker and exchange, and the
deployment's instrument is resolved by those alone (`symbol`, Benzinga's,
and the exchange's MIC), once per process. Benzinga also tags a row with
ISIN and CUSIP under its licence: the plugin uses them only as a key to the
resolution it already made, while it runs -- never sent to the deployment,
never logged, never kept (raw.py takes them out of the answers it keeps). A
security the deployment does not resolve is reported missing, as any miss
is, and its dividends are not recorded.

**Wants.** The lake asks `benzinga_dividends` for instruments: dividends
declared on a business date, over a range of time, or the latest. Each
instrument whose ticker is known -- one this process resolved, or its
record's `symbol` -- is answered from Benzinga; declined `not_covered`
where no ticker, `source_silent` where Benzinga lists none then, and every
instrument `not_entitled` while the key is missing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import meridian
from meridian.errors import CallFailed
from meridian.operations import CorporateActionAnnounced, MeasureRef, Money
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import Latency, data
from meridian.roles.data import filings

from . import api as benzinga
from .declared import CORPORATE_ACTION, DAY_TIME_ZONE, DIVIDENDS, KEYS
from .raw import RawStore

log = logging.getLogger("benzinga")

NEW_YORK = ZoneInfo(DAY_TIME_ZONE)
#: The source this plugin names on what it reports missing, and on the
#: ticker it resolves by.
SOURCE = "benzinga"
#: The rule each row names: this plugin's reading of a calendar row.
RULE = ("benzinga-dividend-calendar", 1)
#: How far back and ahead a check reads.
LOOKBACK_DAYS = 90
AHEAD_DAYS = 366
#: The most pages one request is read to.
MOST_PAGES = 20
#: The most dividends one want is answered with.
MOST_DIVIDENDS = 5000

#: Benzinga's exchange names, to the venue's MIC; any other is resolved by
#: ticker alone.
MICS = {
    "NASDAQ": "XNAS",
    "NYSE": "XNYS",
    "AMEX": "XASE",
    "NYSEAMERICAN": "XASE",
    "NYSE AMERICAN": "XASE",
    "ARCA": "ARCX",
    "NYSEARCA": "ARCX",
    "BATS": "BATS",
}


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


def _day(text: object) -> date | None:
    try:
        return date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def day_start_ns(day: date) -> int:
    """A day's start in New York, in nanoseconds."""
    return _ns(datetime.combine(day, time(), NEW_YORK))


class Skipped:
    """Why a calendar row is not recorded, as the Datasets page counts it."""

    NOT_CASH = "not a cash dividend"
    DATES = "a date not stated"
    AMOUNT = "no amount that reads"
    CURRENCY = "no currency that reads"
    NOT_RESOLVED = "its security not resolved"


@dataclass(frozen=True)
class Stated:
    """One dividend as Benzinga states it. `licensed` is its ISIN or CUSIP,
    held only as a key to its resolution while the plugin runs."""

    dividend_id: str
    updated: int
    ticker: str
    exchange: str
    name: str
    currency: str
    amount: str
    dividend_type: str
    declared: date | None
    ex: date | None
    record: date | None
    payment: date | None
    licensed: str = field(default="", repr=False, compare=False)

    @property
    def version(self) -> str:
        """Its ID and its update: one version of one row."""
        return f"{self.dividend_id}@{self.updated}"

    @property
    def mic(self) -> str:
        return MICS.get(self.exchange.strip().upper(), "")


def stated_in(rows: Sequence[Mapping[str, Any]]) -> list[Stated]:
    """The dividends of one answer, a row with no ID or ticker left out."""
    held = []
    for row in rows:
        dividend_id = str(row.get("id") or "").strip()
        ticker = str(row.get("ticker") or "").strip().upper()
        if not dividend_id or not ticker:
            continue
        updated = row.get("updated")
        held.append(
            Stated(
                dividend_id=dividend_id[:96],
                updated=updated if isinstance(updated, int) and updated > 0 else 0,
                ticker=ticker,
                exchange=str(row.get("exchange") or ""),
                name=str(row.get("name") or ""),
                currency=str(row.get("currency") or "").strip().upper(),
                amount=str(row.get("dividend") or "").strip(),
                dividend_type=str(row.get("dividend_type") or "").strip(),
                declared=_day(row.get("date")),
                ex=_day(row.get("ex_dividend_date")),
                record=_day(row.get("record_date")),
                payment=_day(row.get("payable_date")),
                licensed=str(row.get("isin") or row.get("cusip") or ""),
            )
        )
    return held


def why_skipped(each: Stated) -> str:
    """Why a dividend cannot be recorded as the contract has it; empty where
    it can."""
    if "cash" not in each.dividend_type.lower():
        return Skipped.NOT_CASH
    if None in (each.declared, each.ex, each.record, each.payment):
        return Skipped.DATES
    try:
        amount = Decimal(each.amount)
    except InvalidOperation:
        return Skipped.AMOUNT
    if not amount.is_finite() or amount <= 0:
        return Skipped.AMOUNT
    if len(each.currency) != 3 or not each.currency.isalpha():
        return Skipped.CURRENCY
    return ""


@dataclass
class TickerState:
    """One ticker as the plugin last saw it, for the Tickers tab."""

    ticker: str
    exchange: str = ""
    name: str = ""
    entry: str = ""
    instrument_id: str = ""
    miss: str = ""
    latest_ex: date | None = None
    sent: int = 0


@dataclass(frozen=True)
class Outcome:
    recorded: int = 0
    restated: int = 0
    unchanged: int = 0


@dataclass
class Status:
    """What the plugin last did, for its pages; held in memory, lost on a
    restart and read again by the first check."""

    mode: str = "live"
    #: Why the key will not do, while it will not; empty once it will.
    waiting: str = ""
    started_at: datetime | None = None
    checked_at: datetime | None = None
    read_at: datetime | None = None
    error: str = ""
    fetches: int = 0
    #: Each ticker seen.
    tickers: dict[str, TickerState] = field(default_factory=dict)
    #: Each watchlist entry that is no ticker.
    unread: tuple[str, ...] = ()
    #: Rows not recorded since start, by why.
    skipped: dict[str, int] = field(default_factory=dict)


class Failed(Exception):  # noqa: N818 - what an answer was
    """Benzinga refused or did not answer; its words."""


class Feed(data.Role):
    """The plugin's data role class, its acts made on itself -- registered
    with `meridian.run`, or bound to the suite's `Recorder` in its tests --
    reading Benzinga, resolving securities, recording dividends, answering
    wants."""

    def __init__(
        self,
        api: benzinga.Api,
        raw: RawStore,
        now: Callable[[], datetime] = benzinga.utc_now,
        watchlist: Sequence[str] = (),
        waiting: str = "",
    ) -> None:
        self.api = api
        self.raw = raw
        self.now = now
        self.watchlist = tuple(watchlist)
        clock = lambda: _ns(self.now())  # noqa: E731 - one clock for all
        self.wants = data.Wants(self, KEYS, clock_ns=clock)
        # Each dividend recorded unasked or for a standing want has its age at
        # the edge recorded, by Benzinga's update, and reported (`__main__`).
        self.latency = Latency(self, clock_ns=clock)
        self.wants.latency = self.latency
        self.status = Status(mode=api.mode, waiting=waiting, started_at=now())
        #: Each version sent in this process: a dividend's ID and update.
        self.sent: set[str] = set()
        #: A standing want's instruments, with their tickers.
        self.standing: dict[str, str] = {}
        #: Each resolution made, by the row's local key; and each instrument's
        #: ticker, for wants.
        self._resolved: dict[str, str] = {}
        self._tickers: dict[str, str] = {}

    def use(
        self, api: benzinga.Api, watchlist: Sequence[str], waiting: str, unread: Sequence[str] = ()
    ) -> None:
        """Read from `api` from now on, keeping `watchlist` current: the
        settings changed."""
        if api.mode != self.api.mode:
            self.sent.clear()
        self.api = api
        self.watchlist = tuple(watchlist)
        self.status.mode = api.mode
        self.status.waiting = waiting
        self.status.unread = tuple(unread)

    @property
    def waiting(self) -> str:
        """Why Benzinga is not asked: the key's problem, live; empty where it
        may be asked."""
        return "" if self.api.mode == "synthetic" else self.status.waiting

    def ticker(self, symbol: str) -> TickerState:
        return self.status.tickers.setdefault(symbol, TickerState(symbol))

    # ── Asking Benzinga ─────────────────────────────────────────────────

    async def ask(self, url: str) -> tuple[list[dict[str, Any]], str]:
        """One answer's rows and its key in storage; Failed where Benzinga
        refused or did not answer."""
        try:
            fetched = await self.api.get(url)
        except benzinga.Unreachable as failed:
            raise Failed(str(failed)) from None
        self.status.fetches += 1
        key = self.raw.keep(fetched)
        if fetched.status == 404:
            return [], key  # Benzinga's answer for "no data found"
        if fetched.status != 200:
            raise Failed(fetched.error)
        return fetched.rows(), key

    async def read(
        self, tickers: Sequence[str], start: date, end: date
    ) -> list[tuple[Stated, str]]:
        """The dividends of `tickers` between two days, each with the key of
        the answer it was read from, a page at a time."""
        held: list[tuple[Stated, str]] = []
        for i in range(0, len(tickers), benzinga.MOST_TICKERS):
            batch = tickers[i : i + benzinga.MOST_TICKERS]
            for page in range(MOST_PAGES):
                rows, key = await self.ask(benzinga.dividends_url(batch, start, end, page))
                held.extend((each, key) for each in stated_in(rows))
                if len(rows) < benzinga.PAGE_SIZE:
                    break
        for each, _ in held:
            seen = self.ticker(each.ticker)
            seen.exchange, seen.name = each.exchange, each.name
            ex = each.ex
            if ex and not why_skipped(each) and (seen.latest_ex is None or ex > seen.latest_ex):
                seen.latest_ex = ex
        return held

    # ── Resolving and converting ────────────────────────────────────────

    async def instrument(self, each: Stated) -> str:
        """The deployment's instrument for a row's security, by its ticker and
        exchange alone, asked once per process; empty where none resolves,
        reported missing as any miss is. The row's ISIN or CUSIP is only the
        key the resolution is kept under here."""
        local = each.licensed or f"{each.ticker}@{each.exchange}"
        if local in self._resolved:
            return self._resolved[local]
        symbol = meridian.Identifier(scheme="symbol", value=each.ticker, source=SOURCE)
        now = _ns(self.now())
        found = await self.resolve_identifier(
            identifiers=[symbol], as_of_ns=now, exchange_mic=each.mic
        )
        seen = self.ticker(each.ticker)
        if found.found and found.instrument_id:
            resolved = str(found.instrument_id)
            seen.instrument_id, seen.miss = resolved, ""
            self._tickers[resolved] = each.ticker
        else:
            resolved = ""
            reason = found.miss_reason or ops.MISS_REASON_NOT_FOUND
            seen.miss = ops.MissReason.Name(reason).removeprefix("MISS_REASON_").lower()
            await self.report_missing_instrument(
                source=SOURCE, identifiers=[symbol], as_of_ns=now, reason=reason,
                observed_at_ns=now,
            )  # fmt: skip
            log.info("ticker %s is not resolved: %s", each.ticker, seen.miss)
        self._resolved[local] = resolved
        return resolved

    def skip(self, why: str) -> None:
        self.status.skipped[why] = self.status.skipped.get(why, 0) + 1

    async def convert(self, read: Sequence[tuple[Stated, str]]) -> list[CorporateActionAnnounced]:
        """`read` as rows of `benzinga_dividends`, each naming the answer it
        was first read from; a row the contract cannot carry counted."""
        rows = []
        for each, key in read:
            why = why_skipped(each)
            security = "" if why else await self.instrument(each)
            if not why and not security:
                why = Skipped.NOT_RESOLVED
            if why:
                self.skip(why)
                continue
            assert each.declared and each.ex and each.record and each.payment
            first, _ = self.raw.first(each.version, f"{each.declared:%Y-%m}", key)
            rows.append(
                CorporateActionAnnounced(
                    meta=filings.meta(
                        f"benzinga-dividend-{each.dividend_id}",
                        [(security, "subject")],
                        dataset=self.wants.dataset(DIVIDENDS),
                        valid_from_ns=day_start_ns(each.declared),
                        published_ns=each.updated * 10**9,
                        raw=self.plugin.raw_record(first) if first else None,
                    ),
                    kind="cash_dividend",
                    amount_per_share=Money(Decimal(each.amount), each.currency),
                    declared_date=each.declared,
                    ex_date=each.ex,
                    record_date=each.record,
                    payment_date=each.payment,
                    rule=MeasureRef(definition=RULE[0], version=RULE[1]),
                )
            )
        self.raw.save_firsts()
        return rows

    async def record(self, rows: Sequence[CorporateActionAnnounced], want_id: str = "") -> Outcome:
        counts = self.wants.counts
        before = (counts.recorded, counts.restated, counts.unchanged)
        if rows:
            await self.wants.record("corporate_actions", rows, DIVIDENDS, want_id)
        for row in rows:
            ticker = self._tickers.get(row.meta.subjects[0].entity_id) if row.meta else None
            if ticker:
                self.ticker(ticker).sent += 1
        return Outcome(
            counts.recorded - before[0], counts.restated - before[1], counts.unchanged - before[2]
        )

    # ── Keeping the watchlist current ───────────────────────────────────

    def current(self) -> list[str]:
        """The tickers kept current: the watchlist's, then each standing want's."""
        held: list[str] = []
        for entry in self.watchlist:
            if entry not in held:
                held.append(entry)
                self.ticker(entry).entry = entry
        for symbol in self.standing.values():
            if symbol not in held:
                held.append(symbol)
        return held

    async def check(self) -> Outcome:
        """Read every ticker kept current, recording each dividend not yet
        sent in this process, or updated since."""
        self.status.checked_at = self.now()
        if self.waiting:
            self.status.error = ""
            return Outcome()
        kept = self.current()
        if not kept:
            self.status.error = ""
            return Outcome()
        today = self.now().astimezone(NEW_YORK).date()
        start, end = today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=AHEAD_DAYS)
        try:
            read = await self.read(kept, start, end)
        except Failed as failed:
            self.status.error = str(failed)
            return Outcome()
        fresh = [(each, key) for each, key in read if each.version not in self.sent]
        rows = await self.convert(fresh)
        try:
            done = await self.record(rows)
        except meridian.MeridianError as refused:
            self.status.error = f"the deployment refused a recording: {refused}"
            return Outcome()
        self.sent.update(each.version for each, _ in fresh)
        self.status.error = ""
        self.status.read_at = self.now()
        if done.recorded or done.restated:
            log.info("%d dividends recorded, %d restated", done.recorded, done.restated)
        return done

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_observations_wanted(
        self, heard: meridian.Heard[ops.ObservationsWantedEvent]
    ) -> None:
        """Record what the lake wants of `benzinga_dividends`, or decline it
        (the SDK's `Wants.hear`, answered by `answer`)."""
        await self.wants.hear(heard, self.answer)

    async def on_want_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        """A standing want withdrawn: its instruments no longer kept current for it."""
        held = self.wants.withdraw(heard.message.want_id)
        if held is not None:
            still = {s for w in self.wants.standing.values() for s in w.subjects}
            for subject in held.subjects:
                if subject not in still:
                    self.standing.pop(subject, None)
        log.info("standing want %s withdrawn", heard.message.want_id)

    async def ticker_of(self, instrument_id: str) -> str:
        """The ticker of one of the deployment's instruments: one this process
        resolved, or its record's `symbol`; empty where neither."""
        if instrument_id in self._tickers:
            return self._tickers[instrument_id]
        found = ""
        try:
            answer = await self.resolve_instrument(
                instrument_id=instrument_id, as_of_ns=_ns(self.now())
            )
        except (CallFailed, meridian.NotGranted):
            answer = None
        if answer is not None and answer.found:
            for identifier in answer.instrument.identifiers:
                if identifier.scheme == "symbol" and identifier.value:
                    found = identifier.value.strip().upper()
                    break
        if found:
            self._tickers[instrument_id] = found
        return found

    async def answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """One want answered from Benzinga: its dividends recorded against it,
        and each instrument declined, with why."""
        if key not in KEYS or want.data_type not in ("", CORPORATE_ACTION):
            return {s: "not_covered" for s in subjects}
        if self.waiting:
            return {s: "not_entitled" for s in subjects}
        declined: dict[str, str] = {}
        for subject in subjects:
            symbol = await self.ticker_of(subject)
            if not symbol:
                declined[subject] = "not_covered"
                continue
            reason = await self._record_ticker(want, subject, symbol)
            if reason:
                declined[subject] = reason
            elif want.standing:
                self.wants.stand(want, [subject], kinds)
                self.standing[subject] = symbol
        return declined

    def _window(self, want: ops.ObservationsWantedEvent) -> tuple[date, date]:
        """The days a want asks for, New York's; the lookback for the latest."""
        if want.business_date:
            day = date.fromisoformat(want.business_date)
            return day, day
        today = self.now().astimezone(NEW_YORK).date()
        if want.valid_from_ns or want.valid_until_ns:
            start = datetime.fromtimestamp(want.valid_from_ns / 1e9, NEW_YORK).date()
            until = want.valid_until_ns - 1 if want.valid_until_ns else _ns(self.now())
            return start, datetime.fromtimestamp(until / 1e9, NEW_YORK).date()
        return today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=AHEAD_DAYS)

    @staticmethod
    def _asked(want: ops.ObservationsWantedEvent, each: Stated) -> bool:
        """Whether a want asks for a dividend, by the day it was declared."""
        if each.declared is None:
            return False
        if want.business_date:
            return each.declared.isoformat() == want.business_date
        at = day_start_ns(each.declared)
        if want.valid_from_ns and at < want.valid_from_ns:
            return False
        return not (want.valid_until_ns and at >= want.valid_until_ns)

    async def _record_ticker(
        self, want: ops.ObservationsWantedEvent, subject: str, symbol: str
    ) -> str:
        """Record a ticker's dividends that a want asks for, against the
        instrument it wants; the reason it is declined, or empty where a
        dividend was recorded."""
        start, end = self._window(want)
        try:
            read = await self.read([symbol], start, end)
        except Failed as failed:
            log.warning("want %s: %s not read: %s", want.want_id, symbol, failed)
            return "source_silent"
        chosen = [(each, key) for each, key in read if each.ticker == symbol]
        latest = not (want.business_date or want.valid_from_ns or want.valid_until_ns)
        if latest:
            chosen = sorted(chosen, key=lambda pair: pair[0].declared or date.min)[-1:]
        else:
            chosen = [(each, key) for each, key in chosen if self._asked(want, each)]
        rows = await self.convert(chosen[:MOST_DIVIDENDS])
        rows = [r for r in rows if r.meta and r.meta.subjects[0].entity_id == subject]
        if not rows:
            return "source_silent"
        await self.record(rows, want.want_id)
        return ""
