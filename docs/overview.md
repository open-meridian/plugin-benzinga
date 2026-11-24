# Overview

This plugin records Benzinga's dividends calendar into your deployment's
lake, so the deployment knows each cash dividend a company has announced:
its amount per share, its currency, and its declared, ex, record and
payment dates.

## Who it is for

Firms that hold a Benzinga data licence covering the dividends calendar,
and want those dividends available to the other plugins in their
deployment, such as those that reconcile cash or project income.

## What it does

- Keeps a watchlist of tickers current: each hour it reads their dividends
  from 90 days back to a year ahead, and records any new or updated one.
- Answers a reader that asks for a security's dividends, whether or not the
  security is on the watchlist.
- Records each dividend against the security your deployment holds for its
  ticker and exchange. A ticker your deployment does not hold, or holds
  twice, is reported and not recorded.
- Records a dividend once. Reading it again changes nothing; a dividend
  Benzinga updates is recorded again as its new version.
- Keeps Benzinga's answers in the plugin's storage, for as long as the
  deployment's settings say, so any row can be traced back to the answer it
  came from.

## What it does not do

- It records cash dividends only. Stock dividends, rows missing a date or
  an amount, and splits are counted on the Datasets page and not recorded.
- It does not record Benzinga's economic calendar, news, earnings dates,
  IPOs or consensus estimates in this version.
- It never records ratings, price targets or any other opinion.
- It shows no dividend on its own pages: other plugins show them.
- It does not keep or send ISINs or CUSIPs. Benzinga's rows carry them, but
  the plugin uses each only while it reads a row, and resolves securities by
  ticker and exchange alone.

Each deployment uses its own Benzinga key and its own lake.
