"""The dividends: the watchlist's pushed as they are announced, recorded
once; an update restated; any security's pulled when wanted; what the
contract cannot carry counted, never guessed; and what is declined, and
why."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from meridian import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops

from benzinga.api import HOST, SyntheticApi
from benzinga.feed import RULE, Skipped, day_start_ns, stated_in, why_skipped

from conftest import (
    AT,
    CONTOSO,
    DIVIDENDS,
    FABRIKAM,
    NORTHWIND,
    Updated,
    feed,
    lake,
    sent,
    want,
)


async def test_the_watchlists_dividends_are_recorded_once(tmp_path: Path) -> None:
    recorder = lake()
    work = feed(tmp_path, recorder, watchlist=[NORTHWIND, CONTOSO])
    first = await work.check()
    # Northwind's Q4 (its Q3 is before the window), Contoso's two complete
    # cash dividends.
    assert (first.recorded, first.restated, first.unchanged) == (3, 0, 0)
    # Read again, nothing is sent: each version was sent in this process.
    before = len(sent(recorder))
    again = await work.check()
    assert (again.recorded, again.restated, again.unchanged) == (0, 0, 0)
    assert len(sent(recorder)) == before
    # One request for both tickers, the window from 90 days back to a year ahead.
    assert isinstance(work.api, SyntheticApi)
    (asked,) = set(work.api.asked)
    assert asked.startswith(f"{HOST}/api/v2.2/calendar/dividends?")
    assert "parameters%5Btickers%5D=NWND%2CCTSO" in asked
    assert "date_from%5D=2026-08-26" in asked and "date_to%5D=2027-11-25" in asked


async def test_a_dividend_as_the_contract_has_it(tmp_path: Path) -> None:
    recorder = lake()
    await feed(tmp_path, recorder, watchlist=[NORTHWIND]).check()
    q4 = next(a for a in sent(recorder) if a.meta.row_key.endswith("102"))
    assert q4.meta.row_key == "benzinga-dividend-syn0000000000000000000102"
    assert [(s.entity_id, ops.SubjectRole.Name(s.role)) for s in q4.meta.subjects] == [
        ("INS-NORTHWIND", "SUBJECT_ROLE_SUBJECT")
    ]
    assert q4.meta.source.dataset == DIVIDENDS
    assert ops.CorporateActionKind.Name(q4.kind) == "CORPORATE_ACTION_KIND_CASH_DIVIDEND"
    assert as_decimal(q4.amount_per_share.amount) == Decimal("0.2600")
    assert (q4.declared_date, q4.ex_date, q4.record_date, q4.payment_date) == (
        "2026-10-29", "2026-11-12", "2026-11-13", "2026-11-26"
    )  # fmt: skip
    assert (q4.rule.definition, q4.rule.version) == RULE
    # Valid from the declared day in New York; published at Benzinga's update.
    assert q4.meta.valid_from_ns == day_start_ns(date(2026, 10, 29))
    assert [t.at_ns for t in q4.meta.source_times] == [1793304000 * 10**9]
    assert q4.meta.raw.key.startswith("responses/2026-11/")
    assert not q4.HasField("filing")


async def test_an_update_is_restated_and_a_restart_changes_nothing(tmp_path: Path) -> None:
    recorder = lake()
    api = Updated()
    work = feed(tmp_path, recorder, watchlist=[NORTHWIND], api=api)
    await work.check()
    api.updated = True
    raised = await work.check()
    assert (raised.recorded, raised.restated, raised.unchanged) == (0, 1, 0)
    assert as_decimal(sent(recorder)[-1].amount_per_share.amount) == Decimal("0.2700")
    # A restart reads it all again: the lake changes nothing, each row naming
    # the answer it was first read from.
    restarted = feed(tmp_path, recorder, watchlist=[NORTHWIND], api=api)
    again = await restarted.check()
    assert (again.recorded, again.restated, again.unchanged) == (0, 0, 1)


async def test_what_the_contract_cannot_carry_is_counted(tmp_path: Path) -> None:
    work = feed(tmp_path, watchlist=[CONTOSO])
    await work.check()
    assert work.status.skipped == {Skipped.NOT_CASH: 1, Skipped.DATES: 1}
    rows = [
        {"id": "a", "ticker": "x", "dividend_type": "Cash", "dividend": "abc", "currency": "USD",
         "date": "2026-01-02", "ex_dividend_date": "2026-01-05", "record_date": "2026-01-05",
         "payable_date": "2026-01-09"},
        {"id": "b", "ticker": "x", "dividend_type": "Special Cash", "dividend": "0.5",
         "currency": "", "date": "2026-01-02", "ex_dividend_date": "2026-01-05",
         "record_date": "2026-01-05", "payable_date": "2026-01-09"},
        {"id": "", "ticker": "x"},
    ]  # fmt: skip
    read = stated_in(rows)
    assert [why_skipped(r) for r in read] == [Skipped.AMOUNT, Skipped.CURRENCY]


async def test_a_ticker_not_resolved_is_reported_and_not_recorded(tmp_path: Path) -> None:
    recorder = lake({CONTOSO: "INS-CONTOSO"})
    recorder.instruments.hold("INS-OTHER", ops.Identifier(scheme="symbol", value=NORTHWIND,
                                                          source="benzinga"))  # fmt: skip
    recorder.instruments.hold("INS-OTHER-2", ops.Identifier(scheme="symbol", value=NORTHWIND,
                                                            source="benzinga"))  # fmt: skip
    work = feed(tmp_path, recorder, watchlist=[NORTHWIND, CONTOSO])
    await work.check()
    assert {a.meta.subjects[0].entity_id for a in sent(recorder)} == {"INS-CONTOSO"}
    (missing,) = recorder.on("ReportMissingInstrument")
    assert [i.value for i in missing.identifiers] == [NORTHWIND]
    assert ops.MissReason.Name(missing.reason) == "MISS_REASON_AMBIGUOUS"
    assert work.status.tickers[NORTHWIND].miss == "ambiguous"
    assert work.status.skipped[Skipped.NOT_RESOLVED] == 1
    # Resolved once per process, whatever the checks.
    await work.check()
    assert len(recorder.on("ResolveIdentifier")) == 2


async def test_resolution_names_the_ticker_and_exchange_alone(tmp_path: Path) -> None:
    recorder = lake()
    await feed(tmp_path, recorder, watchlist=[NORTHWIND, CONTOSO]).check()
    asked = recorder.on("ResolveIdentifier")
    assert {(p.identifiers[0].value, p.exchange_mic) for p in asked} == {
        (NORTHWIND, "XNAS"), (CONTOSO, "XNYS")
    }  # fmt: skip
    assert all(len(p.identifiers) == 1 for p in asked)
    assert {i.scheme for p in asked for i in p.identifiers} == {"symbol"}


async def test_a_want_is_recorded_against(tmp_path: Path) -> None:
    recorder = lake()
    work = feed(tmp_path, recorder)
    await work.on_observations_wanted(want("w-day", ["INS-FABRIKAM"], day="2026-11-12"))
    (action,) = sent(recorder)
    assert action.meta.row_key.endswith("302") and action.declared_date == "2026-11-12"
    (recorded,) = recorder.on("RecordCorporateActions")
    assert recorded.want_id == "w-day"


async def test_the_latest_is_wanted(tmp_path: Path) -> None:
    recorder = lake()
    work = feed(tmp_path, recorder)
    await work.on_observations_wanted(want("w-latest", ["INS-FABRIKAM"]))
    (action,) = sent(recorder)
    assert action.declared_date == "2026-11-12"


async def test_what_is_declined_and_why(tmp_path: Path) -> None:
    recorder = lake()
    work = feed(tmp_path, recorder)
    await work.on_observations_wanted(
        want("w-1", ["INS-UNKNOWN", "INS-FABRIKAM"], day="2026-11-13")
    )
    declined = {
        s.entity_id: ops.UnansweredReason.Name(p.reason)
        for p in recorder.on("DeclineWant")
        for s in p.subjects
    }
    assert declined == {
        "INS-UNKNOWN": "UNANSWERED_REASON_NOT_COVERED",
        "INS-FABRIKAM": "UNANSWERED_REASON_SOURCE_SILENT",
    }


async def test_a_missing_key_waits_and_declines(tmp_path: Path) -> None:
    api = SyntheticApi(lambda: AT)
    api.mode = "live"
    recorder = lake()
    work = feed(tmp_path, recorder, watchlist=[NORTHWIND], api=api, waiting="is not set")
    done = await work.check()
    assert (done.recorded, done.restated, done.unchanged) == (0, 0, 0)
    assert api.asked == [] and not sent(recorder)
    await work.on_observations_wanted(want("w-2", ["INS-NORTHWIND"], day="2026-10-29"))
    (declined,) = recorder.on("DeclineWant")
    assert ops.UnansweredReason.Name(declined.reason) == "UNANSWERED_REASON_NOT_ENTITLED"


async def test_a_standing_want_is_kept_current_until_withdrawn(tmp_path: Path) -> None:
    recorder = lake()
    work = feed(tmp_path, recorder)
    await work.on_observations_wanted(want("w-standing", ["INS-FABRIKAM"], standing=True))
    assert work.standing == {"INS-FABRIKAM": FABRIKAM}
    assert work.current() == [FABRIKAM]
    recorder.answer(
        "WantWithdrawn",
        lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=DIVIDENDS),
    )
    await recorder.hear(work, "WantWithdrawn")
    assert work.standing == {} and work.current() == []
