#!/usr/bin/env python3
"""Discovery study acquisition steps (DISCOVERY_STUDY_SPEC.md); read-only, never places orders."""

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT / "data" / "discovery")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("universe", help="Step 1: grouped daily bars, ticker snapshots, discovery universe")
    check = commands.add_parser("delisted-check", help="Step 2: minute bars for delisted common stocks")
    check.add_argument("--count", type=int, default=10)
    minutes = commands.add_parser("minutes", help="Step 3/5: minute bars for one discovery month")
    minutes.add_argument("--month", required=True, help="YYYY-MM")
    pilot = commands.add_parser("pilot", help="Step 4: count opportunities in a downloaded month")
    pilot.add_argument("--month", required=True, help="YYYY-MM")
    replay = commands.add_parser("replay", help="Step 6: minute-bar replay and cost sweep for a month")
    replay.add_argument("--month", required=True, help="YYYY-MM")
    scan = commands.add_parser("conditions", help="Post-hoc decision-time feature scan of a replayed month")
    scan.add_argument("--month", required=True, help="YYYY-MM")
    spreads = commands.add_parser("spreads", help="Q26: net returns of in-play trades with measured spreads")
    spreads.add_argument("--months", required=True, help="Comma-separated YYYY-MM list")
    spreads.add_argument("--gap", type=float, default=20.0)
    spreads.add_argument("--arms", default="b3,b6,c,d")
    losers = commands.add_parser("losers", help="Export the candidate rule's losing account trades")
    losers.add_argument("--months", required=True, help="Comma-separated YYYY-MM list")
    commands.add_parser("tally", help="Month-by-month gross returns for the tracked rules")
    sample = commands.add_parser("quote-sample", help="Step 4: Alpaca quote/trade sizes for disk projection")
    sample.add_argument("--month", required=True, help="YYYY-MM")
    sample.add_argument("--count", type=int, default=30)
    seal = commands.add_parser("manifest", help="SHA-256 manifest of a period's raw files")
    seal.add_argument("period", choices=["discovery", "holdout"])
    args = parser.parse_args(argv)

    from run import load_environment
    from nomisma import discovery_data as data
    load_environment(PROJECT / ".env")
    if args.command == "manifest":
        digest, files = data.manifest(args.root, args.period)
        print("%s manifest: %d files, sha256 %s" % (args.period, files, digest))
        return
    if args.command == "pilot":
        from nomisma import discovery_signals
        print(json.dumps(discovery_signals.pilot(args.root, args.month), indent=2))
        return
    if args.command == "replay":
        from nomisma import discovery_replay
        result = discovery_replay.replay(args.root, args.month)
        print("%d groups written; no-stop by arm: %s" % (len(result["groups"]), result["no_stop_by_arm"]))
        return
    if args.command == "conditions":
        from nomisma import discovery_replay
        cells = discovery_replay.conditions(args.root, args.month)
        for c in cells[:15]:
            print(json.dumps(c))
        print("%d cells; %d with gross > 1%%" % (len(cells), sum(c["gross_pct"] > 1 for c in cells)))
        return
    if args.command == "spreads":
        from nomisma import discovery_replay
        print(json.dumps(discovery_replay.real_spreads(args.root, tuple(args.months.split(",")), args.gap,
                                                       arms=tuple(args.arms.split(","))), indent=2))
        return
    if args.command == "losers":
        from nomisma import discovery_replay
        path, rows = discovery_replay.export_losers(args.root, tuple(args.months.split(",")))
        print("%s: %d losing trades, %+.2f USD" % (path, len(rows), sum(r["pnl_usd"] for r in rows)))
        return
    if args.command == "tally":
        from nomisma import discovery_replay
        print("\n".join(discovery_replay.tally(args.root)))
        return
    if args.command == "quote-sample":
        print(json.dumps(data.quote_sample(args.root, args.month, args.count), indent=2))
        return
    get = data.Massive()
    if args.command == "universe":
        start, end = data.HOLDOUT[0], data.DISCOVERY[1]
        data.fetch_tickers(get, args.root, start, end)
        data.fetch_grouped(get, args.root, start, end)
        print(json.dumps(data.build_universe(args.root), indent=2))
    elif args.command == "minutes":
        from datetime import date, timedelta
        start = date.fromisoformat(args.month + "-01")
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        data.fetch_minutes(get, args.root, start, end, data.period(start))
    else:
        print(json.dumps(data.delisted_check(get, args.root, args.count), indent=2))


if __name__ == "__main__":
    main()
