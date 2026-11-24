"""Benzinga's one request, the key's checks, and the stand-in's filtering."""

from __future__ import annotations

from datetime import date

import pytest

from benzinga.api import HOST, MOST_TICKERS, Fetched, SyntheticApi, check_key, dividends_url

from conftest import AT, CONTOSO, FABRIKAM, NORTHWIND


def test_the_dividends_address() -> None:
    url = dividends_url([NORTHWIND, CONTOSO], date(2026, 1, 1), date(2026, 12, 31), page=2)
    assert url == (
        f"{HOST}/api/v2.2/calendar/dividends?parameters%5Btickers%5D=NWND%2CCTSO"
        "&parameters%5Bdate_from%5D=2026-01-01&parameters%5Bdate_to%5D=2026-12-31"
        "&page=2&pagesize=1000"
    )
    with pytest.raises(ValueError):
        dividends_url(["T"] * (MOST_TICKERS + 1), date(2026, 1, 1), date(2026, 1, 2))


def test_the_keys_checks() -> None:
    assert check_key("") == "is not set"
    assert check_key("  ") == "is not set"
    assert check_key("has a space") == "holds spaces or characters other than plain ASCII"
    assert check_key("x" * 201) == "is longer than 200 characters"
    assert check_key("abcDEF123") == ""


def test_what_an_error_says() -> None:
    assert "benzinga_api_key" in Fetched("u", 401, b"", AT).error
    assert "paused" in Fetched("u", 429, b"", AT).error
    assert Fetched("u", 200, b"not json", AT).rows() == []


async def test_the_stand_in_filters_as_asked() -> None:
    api = SyntheticApi(lambda: AT)
    got = await api.get(dividends_url([FABRIKAM], date(2026, 11, 1), date(2026, 11, 30)))
    assert [r["id"][-3:] for r in got.rows()] == ["302"]
    none = await api.get(dividends_url(["ZZZZ"], date(2026, 1, 1), date(2026, 12, 31)))
    assert none.status == 200 and none.rows() == []
    assert (await api.get(f"{HOST}/api/v2/news")).status == 404
