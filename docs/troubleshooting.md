# Troubleshooting

## Waiting for benzinga_api_key

The API key is missing or malformed, so the plugin asks Benzinga nothing.
The status says what is wrong: not set, too long, or holding spaces or
characters other than plain ASCII. Set it in the Settings form.

## Not answering

Benzinga could not be reached, or answered with an error. A 401 or 403
means Benzinga refused the key, or your plan does not cover the dividends
calendar: check the key with Benzinga. A 429 means too many requests: the
plugin pauses on its own, longer each time, and carries on when Benzinga
lets it. Lower **Requests a second** if it happens often.

## N tickers not resolved

Your deployment holds no security for those tickers on their exchanges, or
holds two. Their dividends are not recorded until it holds exactly one. The
Datasets page's **Tickers** tab names each one and why.

## N watchlist entries are no ticker

A watchlist row is not written as a ticker. Correct the row as Benzinga
writes the ticker, such as `BRK.B`.

## A dividend is missing

The Datasets page's **Not recorded** tab counts the calendar rows the plugin
did not record, and why: a stock dividend, a row missing a date, an amount
or a currency, or a ticker not resolved. A row Benzinga completes later is
recorded at the next check.

## A dividend appears later than expected

The plugin checks the watchlist hourly, so a dividend can take up to an hour,
plus Benzinga's own delay, to appear. A reader asking for a security's
dividends is answered at once.
