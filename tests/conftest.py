"""Shared stand-ins: Benzinga's responses committed with the plugin, a fixed
clock, the deployment's instruments, and the lake as the sidecar answers
it."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Lake
from meridian.suites import Recorder

from benzinga.api import Fetched, SyntheticApi
from benzinga.feed import Feed
from benzinga.raw import RawStore

#: 15:00 UTC on Tuesday 24 November 2026, 10:00 in New York.
AT = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)
INSTANCE = "benzinga"
DIVIDENDS = f"{INSTANCE}:benzinga_dividends"
CORPORATE_ACTION = "meridian.v1.CorporateActionAnnounced"
#: The key the tests use: a placeholder, never a real one.
KEY = "test-placeholder-key"

#: The three fictitious companies the committed responses hold.
NORTHWIND = "NWND"
CONTOSO = "CTSO"
FABRIKAM = "FBRK"  # on no watchlist: fetched when wanted
#: The deployment's instrument for each, by ticker.
INSTRUMENTS = {NORTHWIND: "INS-NORTHWIND", CONTOSO: "INS-CONTOSO", FABRIKAM: "INS-FABRIKAM"}
#: The licensed identifiers the responses tag rows with, which nothing the
#: plugin sends or keeps may hold.
LICENSED = (
    "US9990000017", "999000001", "US9990000025", "999000002", "US9990000033", "999000003",
)  # fmt: skip


def symbol(ticker: str) -> ops.Identifier:
    return ops.Identifier(scheme="symbol", value=ticker, source="benzinga")


def lake(held: dict[str, str] | None = None) -> Lake:
    """The lake as a test stands it in, holding the instruments by ticker,
    and answering a batch of corporate actions as it answers any row: a row
    key new recorded, the same row again unchanged, a changed one restated."""
    recorder = Lake(INSTANCE)
    for ticker, instrument in (INSTRUMENTS if held is None else held).items():
        recorder.instruments.hold(instrument, symbol(ticker))
    versions: dict[str, bytes] = {}

    def recorded(params: ops.RecordCorporateActionsParams) -> ops.RecordCorporateActionsResult:
        done = ops.RecordCorporateActionsResult()
        for action in params.actions:
            stated = ops.CorporateActionAnnounced()
            stated.CopyFrom(action)
            stated.meta.ClearField("recorded_at_ns")
            value = stated.SerializeToString(deterministic=True)
            was = versions.get(action.meta.row_key)
            if was is None:
                done.recorded += 1
            elif was == value:
                done.unchanged += 1
            else:
                done.restated += 1
            versions[action.meta.row_key] = value
        return done

    recorder.answer("RecordCorporateActions", recorded)
    return recorder


def sent(recorder: Recorder) -> list[ops.CorporateActionAnnounced]:
    """Every corporate action sent, in the order sent."""
    return [a for params in recorder.on("RecordCorporateActions") for a in params.actions]


class Updated(SyntheticApi):
    """Benzinga, Northwind's Q4 dividend raised once `updated` is set, as an
    update to a row already read shows."""

    def __init__(self) -> None:
        super().__init__(lambda: AT)
        self.updated = False

    async def get(self, url: str) -> Fetched:
        got = await super().get(url)
        if not self.updated:
            return got
        answer = json.loads(got.body)
        for row in answer["dividends"]:
            if row["id"].endswith("102"):
                row["dividend"], row["updated"] = "0.2700", row["updated"] + 3600
        return Fetched(url, 200, json.dumps(answer).encode(), got.fetched_at)


def feed(
    tmp: Path,
    recorder: Recorder | None = None,
    *,
    watchlist: Sequence[str] = (),
    api: Any = None,
    at: datetime = AT,
    waiting: str = "",
) -> Feed:
    """The plugin's work on the lake and Benzinga's committed responses, at
    `at`: its data role class bound to the lake."""
    held = recorder if recorder is not None else lake()
    return held.bind(
        Feed(
            api or SyntheticApi(lambda: at),
            RawStore(tmp),
            now=lambda: at,
            watchlist=watchlist,
            waiting=waiting,
        )
    )


def want(
    want_id: str,
    subjects: list[str],
    *,
    day: str = "",
    standing: bool = False,
    dataset: str = DIVIDENDS,
    data_type: str = CORPORATE_ACTION,
    valid_from_ns: int = 0,
    valid_until_ns: int = 0,
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=dataset,
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            business_date=day,
            standing=standing,
            valid_from_ns=valid_from_ns,
            valid_until_ns=valid_until_ns,
        ),
    )
