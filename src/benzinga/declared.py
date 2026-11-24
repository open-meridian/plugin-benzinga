"""What this version declares beside its role, `data`, built from code and
used twice: `__main__` registers with it, and `meridian plugin upload` reads
it from the built image (pyproject.toml's `[tool.meridian] declaration`).

**The catalogue: one dataset in this version, `benzinga_dividends`.** Each
cash dividend Benzinga's calendar lists for a security, recorded as a
`CorporateActionAnnounced` row against the instrument the deployment holds
for its ticker:

- `vendor` Benzinga; no aggregator;
- `modes`: pushed (the watchlist's tickers, read every hour) and pulled
  (any security's, when a reader wants it);
- `cadence` 0: a dividend arrives when it is announced, and silence is no
  fault;
- `history` 0: Benzinga states no depth;
- its day New York's; no calendar; no venue;
- its terms in plain words (`TERMS`), and no licence declared: a deployment
  admin sets the licence, and how long the lake keeps the rows, on the Data
  sources page;
- a gap asked again (`gap_recovery` `backfill`): Benzinga serves past dates.

Splits and the economic calendar's actual values wait for kinds the
contract does not have yet; news, earnings dates, IPOs and consensus are
not in this version. Ratings and price targets are never carried.

**Storage:** Benzinga's answers, without the key or the licensed
identifiers (raw.py), archivable, a year by default.
"""

from __future__ import annotations

from meridian import DatasetDeclaration
from meridian.declaration import RecordKind

from .raw import DEFAULT_WINDOW_DAYS, RESPONSES

DIVIDENDS = "benzinga_dividends"
KEYS = (DIVIDENDS,)

VENDOR = "Benzinga"
CORPORATE_ACTION = "meridian.v1.CorporateActionAnnounced"
#: Event-driven: a dividend arrives when it is announced.
CADENCE = 0
#: Benzinga states no depth of history.
HISTORY = 0
DAY_TIME_ZONE = "America/New_York"

#: Benzinga's terms, in plain words, as docs/terms.md summarises them.
TERMS = (
    "Benzinga's calendar data, under each firm's own licence and key with Benzinga: what a "
    "firm may display, keep or use internally, and for how long, is that licence's, as "
    "Benzinga states it in the firm's agreement. Each deployment enters its own key and "
    "records into its own lake; nothing is shared between deployments. Benzinga tags each "
    "row with ISIN and CUSIP under its licence: this plugin uses them only to tell rows "
    "apart while it runs, and keeps and sends neither. Not affiliated with or endorsed by "
    "Benzinga."
)

CATALOGUE = [
    DatasetDeclaration(
        key=DIVIDENDS,
        vendor=VENDOR,
        data_types=[CORPORATE_ACTION],
        modes=["push", "pull"],
        cadence=CADENCE,
        history=HISTORY,
        terms_and_pricing=TERMS,
        gap_recovery="backfill",
        day_time_zone=DAY_TIME_ZONE,
    )
]

RESPONSES_KIND = RecordKind(RESPONSES, "Raw responses", window_days=DEFAULT_WINDOW_DAYS)
