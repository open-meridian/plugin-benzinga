"""The data suite (meridian.suites), each case Benzinga's dividends calendar
presents mapped to the plugin's own conversion of the responses committed
with it: a dividend declared, a ticker that meets two records reported
missing, a subject declined, a standing want withdrawn, its dataset's
licence read, and its feed delay.

A dividend is not a price, a rate, a trade, a quote or an outcome: every
case about one is the SDK's list for a plugin that records none
(`RATES_NOT_PRESENTED`, but for those this version presents), or the rates
cases, each with why. The cases every suite holds that the SDK answers are
the SDK's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import (
    RATES_CASES,
    RATES_NOT_PRESENTED,
    Instruments,
    feed_delay,
)
from meridian.suites import ANSWERED_BY_SDK, Recorder, run

from conftest import CONTOSO, DIVIDENDS, INSTRUMENTS, NORTHWIND, feed, symbol, want

PRESENTED = (
    "a-dividend-declared",
    "an-asset-that-does-not-resolve",
    "a-subject-declined",
    "a-standing-want-withdrawn",
    "reads-its-datasets-licences",
    "reports-its-feed-delay",
)
NOT_A_FILING = "Benzinga's calendar is no filing, and this plugin reads none"
NOT_PRESENTED = {
    **{c: why for c, why in RATES_NOT_PRESENTED.items() if c not in PRESENTED},
    **{c: "it records dividends, never rates" for c in RATES_CASES},
    "a-filing-recorded": NOT_A_FILING,
    "resolves-a-filer": NOT_A_FILING,
    "a-fact-restated": NOT_A_FILING,
    "a-fact-confirmed": NOT_A_FILING,
    "a-complete-holdings-report": NOT_A_FILING,
    "a-stake-crossed": NOT_A_FILING,
    "a-cusip-used-as-key": "it holds no holdings report, and never sends a CUSIP",
    "a-rating-action": "this plugin records no rating, ever",
    "records-a-datasets-liveness": "it checks Benzinga hourly and streams nothing",
    "reads-a-calendar": "its dataset declares no calendar: dividends arrive as announced",
    "asks-for-a-settlement-date": "a dividend announced settles nothing here",
    "records-a-derived-series": "Benzinga's dividends calendar publishes no figure of its own",
}


def hold(recorder: Recorder) -> Instruments:
    """The deployment's instruments, held by ticker, answering the recorder."""
    store = Instruments().answering(recorder)
    for ticker, instrument in INSTRUMENTS.items():
        store.hold(instrument, symbol(ticker))
    return store


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    async def declared(recorder: Recorder) -> None:
        # Northwind, kept current, declares its quarterly cash dividend.
        hold(recorder)
        await feed(tmp, recorder, watchlist=[NORTHWIND]).check()

    async def two_records(recorder: Recorder) -> None:
        # Contoso's ticker on its exchange meets two of the deployment's records.
        store = Instruments().answering(recorder)
        store.hold("INS-A", symbol(CONTOSO))
        store.hold("INS-B", symbol(CONTOSO))
        await feed(tmp, recorder, watchlist=[CONTOSO]).check()

    async def delayed(recorder: Recorder, latency: object) -> None:
        # Each dividend recorded unasked has its age at the edge recorded, by
        # Benzinga's update time, then reported.
        hold(recorder)
        work = feed(tmp, recorder, watchlist=[NORTHWIND])
        work.wants.latency = latency
        await work.check()

    async def declined(recorder: Recorder) -> None:
        hold(recorder)
        work = feed(tmp, recorder)
        asked = want("w-2", ["INS-NOT-HELD"], day="2026-11-12").message
        recorder.answer("ObservationsWanted", lambda _: asked)
        await recorder.hear(work, "ObservationsWanted")

    async def withdrawn(recorder: Recorder) -> None:
        hold(recorder)
        work = feed(tmp, recorder)
        recorder.answer(
            "WantWithdrawn",
            lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=DIVIDENDS),
        )
        await recorder.hear(work, "WantWithdrawn")

    async def licences(recorder: Recorder) -> None:
        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=DIVIDENDS)]),
        )
        work = feed(tmp, recorder)
        await work.wants.read_licences()
        assert work.wants.licensed == {DIVIDENDS}

    return {
        "a-dividend-declared": declared,
        "an-asset-that-does-not-resolve": two_records,
        "reports-its-feed-delay": feed_delay(delayed),
        "a-subject-declined": declined,
        "a-standing-want-withdrawn": withdrawn,
        "reads-its-datasets-licences": licences,
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id="benzinga")
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    assert sorted(report.passed_cases) == sorted([*PRESENTED, *ANSWERED_BY_SDK])
