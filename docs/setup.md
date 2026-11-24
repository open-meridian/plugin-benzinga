# Setup

## Before launching

Your firm needs a Benzinga data licence that covers the dividends calendar,
and an API key for it. Benzinga issues the key; this plugin never shares it.

Launch the plugin and approve its one role, `data` (a data plugin).

## Settings

In the dashboard's Settings form:

- **Benzinga API key**, required and secret. While it is missing or
  malformed the plugin asks Benzinga nothing, Connection says **No key**,
  and the plugin's status names the setting and what is wrong with it.
- **Requests a second**: the most this plugin asks Benzinga, from 1 to 10,
  2 by default. Keep it within your plan's limit, and lower it where other
  tools at your firm use the same key.
- **Watchlist**: the tickers whose dividends are kept current, one per row,
  as Benzinga writes them (`BRK.B`). Up to 500. Empty by default: any
  security's dividends are still fetched when a reader asks.
- **Raw responses window** and **past the window**: how long Benzinga's
  answers are kept in the plugin's storage, a year by default, and whether
  they are then archived, kept or deleted.
- **Sample data**, on a deployment installed for development only: three
  fictitious companies' dividends, committed with the plugin, in place of
  Benzinga. Runs without a key.

## Its dataset

On the deployment's **Data sources** page (deployment admins):

1. **License** `<instance>:benzinga_dividends`. It describes Benzinga's terms
   in words (see Terms) and declares no licence of its own: set the one your
   firm's agreement gives, and choose whether the lake keeps its rows, and
   for how long, or serves them without keeping them.
2. **Entitle** each plugin that reads dividends.

## The securities

Each dividend is recorded against the security your deployment holds for
its ticker on its exchange. The Datasets page's **Tickers** tab shows each
ticker read and the record it resolved to, or why there is none. Add or
correct the security, and the next check records its dividends.
