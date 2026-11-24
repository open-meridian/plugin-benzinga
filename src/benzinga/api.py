"""Benzinga's calendar API, and its stand-in.

One kind of request is made, and nothing else: the dividends calendar,

    GET https://api.benzinga.com/api/v2.2/calendar/dividends
        ?parameters[tickers]=AAA,BBB&parameters[date_from]=...&parameters[date_to]=...
        &page=0&pagesize=1000

answered as JSON, `{"dividends": [...]}`, each row a dividend as Benzinga
states it. At most 50 tickers a request and 1000 rows a page, as Benzinga's
documentation says.

**The key.** Each deployment's admin enters their own Benzinga key in
Settings (`benzinga_api_key`). Benzinga takes it as the `token` query
parameter, so it is added to the address only as the request is sent
(`LiveApi._get`): every address the rest of the plugin sees, logs or keeps
is the one without it (`Fetched.url`). It is never logged, shown, or kept in
a raw record, and nothing is asked of Benzinga while it is missing.

**How fast.** Every request waits for its slot (limits.py): at most the
setting's rate, and paused after a 429.

`SyntheticApi` answers from the responses committed under responses/
(responses/index.json): three fictitious companies' dividends, in Benzinga's
documented layout, filtered by tickers and dates as Benzinga filters them, so
the tests and sample data run offline and the same on any day.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from importlib import resources
from typing import Any, Protocol

from .limits import Limiter, retry_after

HOST = "https://api.benzinga.com"
DIVIDENDS = "/api/v2.2/calendar/dividends"
TIMEOUT = 60.0
#: The most of an answer read.
MOST_BYTES = 32 * 1024 * 1024
#: Benzinga's limits for one request: tickers, and rows a page.
MOST_TICKERS = 50
PAGE_SIZE = 1000
#: The longest key accepted.
MOST_KEY = 200


def dividends_url(tickers: Sequence[str], date_from: date, date_to: date, page: int = 0) -> str:
    """The dividends calendar's address for `tickers` between two days, the
    announcement's or the ex-date's, one page of it; never with the key."""
    if not 0 < len(tickers) <= MOST_TICKERS:
        raise ValueError(f"1 to {MOST_TICKERS} tickers a request")
    query = urllib.parse.urlencode(
        [
            ("parameters[tickers]", ",".join(tickers)),
            ("parameters[date_from]", date_from.isoformat()),
            ("parameters[date_to]", date_to.isoformat()),
            ("page", str(page)),
            ("pagesize", str(PAGE_SIZE)),
        ]
    )
    return f"{HOST}{DIVIDENDS}?{query}"


def check_key(text: str) -> str:
    """Why a key will not do, or empty where it will: present, one plain
    word of printable ASCII."""
    said = text.strip()
    if not said:
        return "is not set"
    if len(said) > MOST_KEY:
        return f"is longer than {MOST_KEY} characters"
    if any(not ("!" <= c <= "~") for c in said):
        return "holds spaces or characters other than plain ASCII"
    return ""


class Unreachable(Exception):  # noqa: N818 - what Benzinga was
    """Benzinga could not be asked: no answer, or not in time."""


@dataclass(frozen=True)
class Fetched:
    """One answer of Benzinga's, as received; `url` never holds the key."""

    url: str
    status: int
    body: bytes
    fetched_at: datetime
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return self.url.removeprefix(HOST)

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            return None

    def rows(self) -> list[dict[str, Any]]:
        """The dividends the answer lists; none where it lists none."""
        read = self.json()
        held = read.get("dividends") if isinstance(read, dict) else None
        return [row for row in held if isinstance(row, dict)] if isinstance(held, list) else []

    @property
    def error(self) -> str:
        if self.status == 401:
            return "Benzinga answered 401: the key was refused; check benzinga_api_key"
        if self.status == 403:
            return "Benzinga answered 403: the key's plan does not cover the dividends calendar"
        if self.status == 429:
            return "Benzinga answered 429: too many requests; paused"
        return f"Benzinga answered {self.status}"


class Api(Protocol):
    mode: str
    limiter: Limiter

    async def get(self, url: str) -> Fetched: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class LiveApi:
    """Benzinga itself, asked with `key`, paced by `limiter`."""

    mode = "live"

    def __init__(self, key: str, limiter: Limiter, now: Callable[[], datetime] = utc_now) -> None:
        self._key = key.strip()
        self.limiter = limiter
        self._now = now

    async def get(self, url: str) -> Fetched:
        await self.limiter.wait()
        got = await asyncio.to_thread(self._get, url)
        self.limiter.answered(got.status, retry_after(got.headers.get("retry-after")))
        return got

    def _get(self, url: str) -> Fetched:
        if not url.startswith(HOST + "/"):
            raise ValueError("only Benzinga's API is asked")
        signed = f"{url}&{urllib.parse.urlencode({'token': self._key})}"
        request = urllib.request.Request(
            signed, headers={"Accept": "application/json", "Accept-Encoding": "gzip"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310 - Benzinga's https address
                body = answer.read(MOST_BYTES + 1)
                status = answer.status
                headers = {k.lower(): v for k, v in answer.headers.items()}
        except urllib.error.HTTPError as refused:
            body = refused.read(MOST_BYTES + 1) if refused.fp else b""
            status = refused.code
            headers = {k.lower(): v for k, v in (refused.headers or {}).items()}
        except (urllib.error.URLError, TimeoutError, OSError) as failed:
            # The address in an error is the one without the key.
            reason = getattr(failed, "reason", failed)
            raise Unreachable(f"{url}: {type(reason).__name__}") from None
        if len(body) > MOST_BYTES:
            raise Unreachable(f"{url}: answered more than {MOST_BYTES} bytes")
        if headers.get("content-encoding") == "gzip":
            body = gzip.decompress(body)
        return Fetched(url, status, body, self._now(), headers)


def _day(text: object) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


class SyntheticApi:
    """The responses committed under responses/: each ticker's dividends, as
    Benzinga lists them, answered for a request as Benzinga filters it --
    the tickers asked, a row's announcement or ex-date between the two days
    -- a page at a time."""

    mode = "synthetic"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self.limiter = Limiter()
        held = resources.files(__package__).joinpath("responses")
        index = json.loads(held.joinpath("index.json").read_text(encoding="utf-8"))
        self.rows: dict[str, list[dict[str, Any]]] = {
            ticker: json.loads(held.joinpath(name).read_text(encoding="utf-8"))["dividends"]
            for ticker, name in index["tickers"].items()
        }
        self.asked: list[str] = []

    @property
    def answers(self) -> dict[str, list[dict[str, Any]]]:
        return self.rows

    async def get(self, url: str) -> Fetched:
        self.asked.append(url)
        at = self._now()
        parts = urllib.parse.urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" != HOST or parts.path != DIVIDENDS:
            return Fetched(url, 404, b'{"ok": false}', at)
        query = dict(urllib.parse.parse_qsl(parts.query))
        tickers = [t for t in query.get("parameters[tickers]", "").split(",") if t]
        start = _day(query.get("parameters[date_from]")) or date.min
        end = _day(query.get("parameters[date_to]")) or date.max
        page, size = int(query.get("page", "0")), int(query.get("pagesize", str(PAGE_SIZE)))
        chosen = [
            row
            for ticker in tickers
            for row in self.rows.get(ticker.upper(), [])
            if any(
                d is not None and start <= d <= end
                for d in (_day(row.get("date")), _day(row.get("ex_dividend_date")))
            )
        ]
        shown = chosen[page * size : (page + 1) * size]
        return Fetched(url, 200, json.dumps({"dividends": shown}).encode(), at)


def api(synthetic: bool, key: str, limiter: Limiter, now: Callable[[], datetime] = utc_now) -> Api:
    return SyntheticApi(now) if synthetic else LiveApi(key, limiter, now)
