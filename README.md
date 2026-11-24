# Benzinga plugin

An [Open Meridian](https://github.com/open-meridian) data plugin that records
the cash dividends companies announce into a deployment's lake, read from
Benzinga's dividends calendar with the deployment's own key.

- **One dataset, `benzinga_dividends`:** each cash dividend's amount per
  share, currency, and declared, ex, record and payment dates, against the
  security the deployment holds for its ticker and exchange.
- **A watchlist** of tickers kept current; any other security's dividends
  are fetched when a reader asks.
- **Careful with what is licensed:** the key is never shown or kept, and the
  ISINs and CUSIPs Benzinga's rows carry are neither kept nor sent.
- **Traceable:** every row names the Benzinga answer it was read from, kept
  in the plugin's storage.

It shows no dividend on its own pages, which show its connection and its
dataset. What it may publish and read comes from the role `pyproject.toml`
declares, `data`, once a deployment admin approves it.

## Use it

    meridian plugin upload
    meridian plugin launch benzinga 0.1.0 --instance benzinga

Then, in the dashboard: set **Benzinga API key**, optionally the rate and the
watchlist; license `benzinga:benzinga_dividends` on **Data sources**; and
entitle the plugins that read it. [docs/setup.md](docs/setup.md) walks
through each step.

## Develop it

    pip install -e '.[dev]'
    python -m pytest
    meridian plugin check --verified --run-tests

The tests run offline against fictitious responses committed under
`src/benzinga/responses/`; nothing in the tests or CI calls Benzinga. With
the **Sample data** setting on, a development deployment runs on the same
responses. `make ci-local` runs lint, the tests, the plugin check and the
image in containers.

| Module | What it does |
|---|---|
| `api.py` | Benzinga's dividends request, and the committed stand-in |
| `limits.py` | the request pace and the pause after a refusal |
| `feed.py` | turns calendar rows into dividends, the watchlist, readers' wants |
| `raw.py` | Benzinga's answers as received, without what is licensed |
| `settings.py`, `declared.py` | the settings and the dataset's declaration |
| `page.py`, `records.py`, `templates/` | the Connection and Datasets pages, and their tools |

`AGENTS.md` is for coding agents working on the plugin.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Not affiliated with
or endorsed by Benzinga.
