from __future__ import annotations

import argparse
from pathlib import Path

from pokebrain.replays.cli import collect_replays_command, parse_replays_command


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pokebrain.replays")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect public Pokemon Showdown replay JSON.")
    collect.add_argument("--format", required=True)
    collect.add_argument("--limit", type=int, required=True)
    collect.add_argument("--before", type=int)
    collect.add_argument("--minimum-rating", type=int)
    collect.add_argument("--maximum-rating", type=int)
    collect.add_argument("--database", default="data/database/replays.db")
    collect.add_argument("--raw-root", default="data/replays/raw")
    collect.add_argument("--minimum-turns", type=int, default=5)
    collect.add_argument("--allow-unfinished", action="store_true")
    collect.add_argument("--requests-per-second", type=float, default=2.0)

    parse = subparsers.add_parser("parse", help="Parse collected raw replays into policy examples.")
    parse.add_argument("--format", required=True)
    parse.add_argument("--status", default="pending")
    parse.add_argument("--parser-version", default="public-replay-parser-v1")
    parse.add_argument("--limit", type=int)
    parse.add_argument("--database", default="data/database/replays.db")
    parse.add_argument("--raw-root", default="data/replays/raw")
    parse.add_argument("--output", default="data/policy/examples")

    args = parser.parse_args()
    if args.command == "collect":
        collect_replays_command(
            format_id=args.format,
            limit=args.limit,
            before=args.before,
            minimum_rating=args.minimum_rating,
            maximum_rating=args.maximum_rating,
            database_path=Path(args.database),
            raw_root=Path(args.raw_root),
            minimum_turns=args.minimum_turns,
            require_finished_battle=not args.allow_unfinished,
            requests_per_second=args.requests_per_second,
        )
    elif args.command == "parse":
        parse_replays_command(
            format_id=args.format,
            status=args.status,
            parser_version=args.parser_version,
            limit=args.limit,
            database_path=Path(args.database),
            raw_root=Path(args.raw_root),
            output_dir=Path(args.output),
        )


if __name__ == "__main__":
    main()
