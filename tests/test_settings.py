"""The settings as declared, in the data role's order, and read back."""

from __future__ import annotations

from meridian._settings import declared_by

from benzinga.settings import DECLARED, config_from

from conftest import KEY


def test_declared_in_the_roles_order() -> None:
    declared = declared_by(DECLARED)
    assert [s.name for s in declared] == [
        "benzinga_api_key",
        "benzinga_requests_per_second",
        "benzinga_watchlist",
        "sample_data",
    ]
    key, rate, watchlist, sample = declared
    assert key.required and key.secret and key.kind is str
    assert rate.kind is int and rate.default == 2
    assert watchlist.kind is list and [c.name for c in watchlist.columns] == ["ticker"]
    assert watchlist.columns[0].required and watchlist.columns[0].kind == "text"
    assert sample.developer


def test_read_back() -> None:
    config = config_from(
        {
            "benzinga_api_key": f"  {KEY} ",
            "benzinga_requests_per_second": 5,
            "benzinga_watchlist": [{"ticker": " nwnd "}, {"ticker": "BRK.B"}, {"ticker": "NWND"},
                                   {"ticker": "not a ticker"}, {"other": "x"}],
            "responses_window_days": 30,
            "responses_past_window": "archived",
        }
    )  # fmt: skip
    assert config.key == KEY and config.key_problem == ""
    assert config.per_second == 5 and config.watchlist == ("NWND", "BRK.B")
    assert config.unread == ("NOT A TICKER",)
    assert config.window_days == 30 and config.past_window == "archived"
    assert not config.sample_data
    # The key is a secret: never in the configuration's own text.
    assert KEY not in repr(config) and KEY not in str(config)


def test_a_missing_key_is_said() -> None:
    assert config_from({}).key_problem == "is not set"
    assert config_from({"benzinga_requests_per_second": 40}).per_second == 10
    assert config_from({"benzinga_requests_per_second": 0}).per_second == 1
    assert config_from({}).per_second == 2
