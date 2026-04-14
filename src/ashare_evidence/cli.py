from __future__ import annotations

import argparse
import json
from typing import Any

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.services import bootstrap_demo_data, get_latest_recommendation_summary, get_recommendation_trace


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-first data foundation CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create database tables.")
    init_db.add_argument("--database-url", default=None)

    load_demo = subparsers.add_parser("load-demo", help="Seed a demo watchlist stock and traceable recommendation.")
    load_demo.add_argument("--database-url", default=None)
    load_demo.add_argument("--symbol", default="600519.SH")

    latest = subparsers.add_parser("latest", help="Show the latest recommendation for a stock.")
    latest.add_argument("--database-url", default=None)
    latest.add_argument("--symbol", default="600519.SH")

    trace = subparsers.add_parser("trace", help="Show a full evidence trace for a recommendation ID.")
    trace.add_argument("--database-url", default=None)
    trace.add_argument("--recommendation-id", type=int, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        init_database(args.database_url)
        print("database initialized")
        return 0

    if args.command == "load-demo":
        init_database(args.database_url)
        with session_scope(args.database_url) as session:
            payload = bootstrap_demo_data(session, args.symbol)
        _print_json(payload)
        return 0

    if args.command == "latest":
        init_database(args.database_url)
        with session_scope(args.database_url) as session:
            payload = get_latest_recommendation_summary(session, args.symbol)
        if payload is None:
            print(f"no recommendation found for {args.symbol}")
            return 1
        _print_json(payload)
        return 0

    if args.command == "trace":
        init_database(args.database_url)
        with session_scope(args.database_url) as session:
            payload = get_recommendation_trace(session, args.recommendation_id)
        _print_json(payload)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
