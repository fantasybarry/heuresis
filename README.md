# Heuresis

A home for independent, inventive software projects. Each project lives under `projects/` with its own application, documentation, and tests.

## Nomisma

[Nomisma](projects/nomisma/README.md) is the first project: a local workspace focused on intraday penny-stock momentum, with real-time Alpaca monitoring for up to 20 symbols, volume/float reports, and configurable Buy / Strong buy technical setup alerts. A separate daily US-equity screener supports broader research, saved filters, and scheduled scans.

Start it from this directory:

```sh
python3 projects/nomisma/run.py
```

Open **http://127.0.0.1:8765**. Requires Python 3.9 or newer, with no packages to install. Click **Start** on the live monitor to try the explicitly synthetic simulation, or [configure Alpaca](projects/nomisma/README.md#connect-real-time-market-data) and replace the demo tickers for real market data. Historical CSV import belongs to the separate daily screener. Setup scores are heuristics, not forecasts; Nomisma never submits orders.

```text
heuresis/
└── projects/
    └── nomisma/
        ├── nomisma/       Application, indicators, providers, and dashboard
        ├── tests/         Indicator, provider, persistence, and HTTP tests
        ├── examples/      CSV format example
        └── run.py         Local app / one-shot scanner entry point
```
