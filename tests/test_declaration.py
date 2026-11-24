"""The catalogue, from code, as the deployment approves it."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops

from benzinga.declaration import DECLARATION
from benzinga.declared import TERMS


def test_one_dataset_of_dividends() -> None:
    (dividends,) = DECLARATION.catalogue
    assert dividends.key == "benzinga_dividends"
    assert list(dividends.data_types) == ["meridian.v1.CorporateActionAnnounced"]
    assert dividends.vendor == "Benzinga"
    assert [ops.ObservationMode.Name(m) for m in dividends.modes] == [
        "OBSERVATION_MODE_PUSH", "OBSERVATION_MODE_PULL"
    ]  # fmt: skip
    # Event-driven: silence is no fault. New York's day, no calendar.
    assert dividends.cadence == 0
    assert dividends.day_time_zone == "America/New_York" and not dividends.calendar_id
    assert not dividends.venue_id and dividends.gap_recovery == "backfill"


def test_benzingas_terms_in_words_and_no_licence() -> None:
    (dividends,) = DECLARATION.catalogue
    assert dividends.terms_and_pricing == TERMS and len(TERMS) <= 2000
    assert "own licence" in TERMS and "ISIN" in TERMS and "Not affiliated" in TERMS


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
