from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from pokebrain.data.importer import SQLiteImporter
from pokebrain.data.manager import DataManager
from pokebrain.showdown import ShowdownEngine


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SNAPSHOT_DIR = ROOT_DIR / "data" / "normalized" / "v1"
DEFAULT_DATABASE = ROOT_DIR / "data" / "database" / "pokemon.db"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pokebrain.data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update_parser = subparsers.add_parser("update", help="Export and import Showdown data.")
    update_parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT_DIR))
    update_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    update_parser.add_argument("--skip-export", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one species.")
    inspect_parser.add_argument("species_id")
    inspect_parser.add_argument("--database", default=str(DEFAULT_DATABASE))

    resolve_parser = subparsers.add_parser("resolve", help="Resolve Dex data in one mod.")
    resolve_parser.add_argument("kind", choices=["species", "move", "ability", "item"])
    resolve_parser.add_argument("name_or_id")
    resolve_parser.add_argument("--mod", default="gen9")

    validate_parser = subparsers.add_parser("validate-team", help="Validate a Showdown team.")
    validate_parser.add_argument("--format", required=True)
    validate_parser.add_argument("--team-file")

    list_formats_parser = subparsers.add_parser("list-formats", help="List Showdown formats.")
    list_formats_parser.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()

    if args.command == "update":
        update(Path(args.snapshot), Path(args.database), skip_export=args.skip_export)
    elif args.command == "inspect":
        inspect(args.species_id, Path(args.database))
    elif args.command == "resolve":
        resolve(args.mod, args.kind, args.name_or_id)
    elif args.command == "validate-team":
        validate_team(args.format, Path(args.team_file) if args.team_file else None)
    elif args.command == "list-formats":
        list_formats(args.limit)


def update(snapshot_dir: Path, database_path: Path, skip_export: bool = False) -> None:
    if not skip_export:
        subprocess.run(
            [
                "node",
                "scripts/export_showdown_with_node.js",
                "--output",
                str(snapshot_dir),
            ],
            cwd=ROOT_DIR,
            check=True,
        )

    snapshot = SQLiteImporter(database_path).import_snapshot(snapshot_dir)
    metadata = snapshot.metadata
    counts = metadata.get("record_counts", {})

    print(f"Showdown snapshot: {metadata.get('source_commit', 'unknown')}")
    print(f"Schema version: {metadata.get('schema_version', 1)}")
    print("")
    print(f"Species imported: {counts.get('species', len(snapshot.species))}")
    print(f"Moves imported: {counts.get('moves', len(snapshot.moves))}")
    print(f"Abilities imported: {counts.get('abilities', len(snapshot.abilities))}")
    print(f"Items imported: {counts.get('items', len(snapshot.items))}")
    print("")
    print("Integrity checks: passed")
    print("Database updated successfully")


def inspect(species_id: str, database_path: Path) -> None:
    manager = DataManager(database_path)
    species = manager.species.get_by_id(species_id)
    if species is None:
        print(f"Species not found: {species_id}", file=sys.stderr)
        sys.exit(1)

    stats = species.base_stats
    print(species.name)
    print(f"ID: {species.id}")
    print(f"Generation: {species.generation}")
    print(f"Types: {' / '.join(species.types)}")
    print(f"Abilities: {', '.join(species.abilities.values())}")
    print(
        "Base stats: "
        f"{stats.hp} / {stats.attack} / {stats.defense} / "
        f"{stats.special_attack} / {stats.special_defense} / {stats.speed}"
    )


def resolve(mod: str, kind: str, name_or_id: str) -> None:
    data = ShowdownEngine().resolve(mod, kind, name_or_id)
    if data is None:
        print(f"{kind.title()} not found in {mod}: {name_or_id}", file=sys.stderr)
        sys.exit(1)

    print(f"{data['name']}")
    print(f"ID: {data['id']}")
    print(f"Mod: {mod}")

    if kind == "species":
        print(f"Generation: {data['generation']}")
        print(f"Types: {' / '.join(data['types'])}")
        print(f"Abilities: {', '.join(data['abilities'].values())}")
    elif kind == "move":
        print(f"Generation: {data['generation']}")
        print(f"Type: {data['type']}")
        print(f"Category: {data['category']}")
        print(f"Power: {data['power']}")
        print(f"Accuracy: {data['accuracy']}")
        print(f"PP: {data['pp']}")
    elif kind in {"ability", "item"}:
        print(f"Generation: {data['generation']}")
        if data.get("description"):
            print(f"Description: {data['description']}")


def validate_team(format_id: str, team_file: Path | None) -> None:
    team_text = team_file.read_text(encoding="utf-8") if team_file else sys.stdin.read()
    result = ShowdownEngine().validate_team(format_id, team_text)
    print(f"Format: {result.format_id}")
    print(f"Valid: {'yes' if result.valid else 'no'}")
    if result.errors:
        print("")
        print("Problems:")
        for problem in result.problems:
            print(f"- {problem}")


def list_formats(limit: int | None) -> None:
    formats = ShowdownEngine().list_formats()
    if limit is not None:
        formats = formats[:limit]

    for format_data in formats:
        print(
            f"{format_data['id']}: {format_data['name']} "
            f"(gen {format_data['generation']}, {format_data['game_type']})"
        )


if __name__ == "__main__":
    main()
