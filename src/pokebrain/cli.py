from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pokebrain.analysis import TeamAnalyzer, TextTeamAnalysisRenderer
from pokebrain.analysis.matchup import MatchupAnalyzer, TextMatchupRenderer
from pokebrain.analysis.team_matchup import TeamMatchupAnalyzer, TextTeamMatchupRenderer
from pokebrain.battle import DecisionStyle, MoveDecisionEngine, TextMoveDecisionRenderer, load_battle_state
from pokebrain.benchmark.cli import compare_benchmark_command, run_benchmark_command, run_performance_benchmark_command
from pokebrain.damage import DamagePokemon, DamageRequest, ShowdownDamageEngine
from pokebrain.policy_calibration.cli import calibrate_policy_command, evaluate_policy_command
from pokebrain.policy_dataset.cli import (
    audit_policy_dataset_command,
    build_policy_dataset_command,
    coverage_policy_dataset_command,
    report_policy_dataset_command,
    report_policy_pilot_command,
)
from pokebrain.policy_evaluation.cli import compare_policy_baselines_command, evaluate_policy_baselines_command
from pokebrain.replay.cli import review_battle_command, review_benchmark_command, review_benchmark_leads_command
from pokebrain.replays.cli import collect_replays_command, parse_replays_command
from pokebrain.regressions import test_regressions_command
from pokebrain.team.models import EVSpread, IVSpread, PokemonSet
from pokebrain.utils import to_id


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pokebrain")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze-team", help="Analyze a Showdown team.")
    analyze_parser.add_argument("--format", required=True)
    analyze_parser.add_argument("--file", required=True)

    damage_parser = subparsers.add_parser("calculate-damage", help="Calculate one damage interaction.")
    damage_parser.add_argument("--generation", type=int, required=True)
    damage_parser.add_argument("--attacker", required=True)
    damage_parser.add_argument("--defender", required=True)
    damage_parser.add_argument("--move", required=True)

    matchup_parser = subparsers.add_parser("matchup", help="Compare two Pokemon sets.")
    matchup_parser.add_argument("--generation", type=int, required=True)
    matchup_parser.add_argument("--pokemon-a", required=True)
    matchup_parser.add_argument("--pokemon-b", required=True)

    team_matchup_parser = subparsers.add_parser("team-matchup", help="Compare two full teams.")
    team_matchup_parser.add_argument("--generation", type=int, required=True)
    team_matchup_parser.add_argument("--team-a", required=True)
    team_matchup_parser.add_argument("--team-b", required=True)
    team_matchup_parser.add_argument("--format", default="gen9ou")

    decide_parser = subparsers.add_parser("decide-action", help="Recommend a battle action from a JSON state.")
    decide_parser.add_argument("--state", required=True)
    decide_parser.add_argument(
        "--style",
        choices=[style.value for style in DecisionStyle],
        default=DecisionStyle.BALANCED.value,
    )

    benchmark_parser = subparsers.add_parser("benchmark", help="Run local Showdown benchmark battles.")
    benchmark_parser.add_argument("--format", required=True)
    benchmark_parser.add_argument("--agent-a", default="pokebrain-v1")
    benchmark_parser.add_argument("--agent-b", default="max-damage")
    benchmark_parser.add_argument("--battles", type=int, required=True)
    benchmark_parser.add_argument("--teams", required=True)
    benchmark_parser.add_argument("--seed", type=int, default=12345)
    benchmark_parser.add_argument("--maximum-turns", type=int, default=500)
    benchmark_parser.add_argument("--timeout-seconds", type=int, default=120)
    benchmark_parser.add_argument("--parallel-workers", type=int, default=1)
    benchmark_parser.add_argument("--database", default="data/database/benchmarks.db")

    compare_parser = subparsers.add_parser("compare-benchmarks", help="Compare two saved benchmark runs.")
    compare_parser.add_argument("--run-a", required=True)
    compare_parser.add_argument("--run-b", required=True)
    compare_parser.add_argument("--database", default="data/database/benchmarks.db")

    performance_parser = subparsers.add_parser("benchmark-performance", help="Run paired performance benchmarks across agents.")
    performance_parser.add_argument("--format", required=True)
    performance_parser.add_argument("--agents", nargs="+", default=["pokebrain-v1", "search-v1", "search-v1-cache"])
    performance_parser.add_argument("--pairs", type=int, default=50)
    performance_parser.add_argument("--teams", required=True)
    performance_parser.add_argument("--seed", type=int, default=12345)
    performance_parser.add_argument("--maximum-turns", type=int, default=500)
    performance_parser.add_argument("--timeout-seconds", type=int, default=120)
    performance_parser.add_argument("--parallel-workers", type=int, default=1)
    performance_parser.add_argument("--database", default="data/database/benchmarks.db")

    review_parser = subparsers.add_parser("review-battle", help="Review one local battle replay directory.")
    review_parser.add_argument("--battle", required=True)
    review_parser.add_argument("--write-regressions", action="store_true")
    review_parser.add_argument("--regressions-dir", default="regressions")

    review_benchmark_parser = subparsers.add_parser("review-benchmark", help="Aggregate replay reviews for a benchmark run.")
    review_benchmark_parser.add_argument("--run", required=True)
    review_benchmark_parser.add_argument("--database", default="data/database/benchmarks.db")
    review_benchmark_parser.add_argument("--only-losses", action="store_true")
    review_benchmark_parser.add_argument("--top", type=int, default=10)
    review_benchmark_parser.add_argument("--min-battles", type=int, default=3)

    review_benchmark_leads_parser = subparsers.add_parser(
        "review-benchmark-leads",
        help="Analyze lead pairs and early losses for a benchmark run.",
    )
    review_benchmark_leads_parser.add_argument("--run", required=True)
    review_benchmark_leads_parser.add_argument("--database", default="data/database/benchmarks.db")
    review_benchmark_leads_parser.add_argument("--max-turns", type=int, default=4)
    review_benchmark_leads_parser.add_argument("--top", type=int, default=20)
    review_benchmark_leads_parser.add_argument("--min-battles", type=int, default=5)

    evaluate_policy_parser = subparsers.add_parser("evaluate-policy", help="Evaluate the opponent policy model on replay directories.")
    evaluate_policy_parser.add_argument("--format", required=True)
    evaluate_policy_parser.add_argument("--replays", nargs="+", required=True)
    evaluate_policy_parser.add_argument("--rating-bucket")

    calibrate_policy_parser = subparsers.add_parser("calibrate-policy", help="Fit offline opponent policy calibration from replay directories.")
    calibrate_policy_parser.add_argument("--format", required=True)
    calibrate_policy_parser.add_argument("--replays", nargs="+", required=True)
    calibrate_policy_parser.add_argument("--output", default="data/policy_profiles/gen9ou.json")
    calibrate_policy_parser.add_argument("--rating-bucket")

    collect_replays_parser = subparsers.add_parser("collect-replays", help="Collect public Pokemon Showdown replay JSON.")
    collect_replays_parser.add_argument("--format", required=True)
    collect_replays_parser.add_argument("--limit", type=int, required=True)
    collect_replays_parser.add_argument("--before", type=int)
    collect_replays_parser.add_argument("--minimum-rating", type=int)
    collect_replays_parser.add_argument("--maximum-rating", type=int)
    collect_replays_parser.add_argument("--database", default="data/database/replays.db")
    collect_replays_parser.add_argument("--raw-root", default="data/replays/raw")
    collect_replays_parser.add_argument("--minimum-turns", type=int, default=5)
    collect_replays_parser.add_argument("--allow-unfinished", action="store_true")
    collect_replays_parser.add_argument("--requests-per-second", type=float, default=2.0)

    parse_replays_parser = subparsers.add_parser("parse-replays", help="Parse collected raw replays into policy examples.")
    parse_replays_parser.add_argument("--format", required=True)
    parse_replays_parser.add_argument("--status", default="pending")
    parse_replays_parser.add_argument("--parser-version", default="public-replay-parser-v1")
    parse_replays_parser.add_argument("--limit", type=int)
    parse_replays_parser.add_argument("--database", default="data/database/replays.db")
    parse_replays_parser.add_argument("--raw-root", default="data/replays/raw")
    parse_replays_parser.add_argument("--output", default="data/policy/examples")

    build_dataset_parser = subparsers.add_parser("build-policy-dataset", help="Build a reproducible policy dataset from complete replay examples.")
    build_dataset_parser.add_argument("--format", required=True)
    build_dataset_parser.add_argument("--replays", nargs="+", required=True)
    build_dataset_parser.add_argument("--output", default="data/policy/datasets/policy-dataset-v1")
    build_dataset_parser.add_argument("--dataset-version", default="policy-dataset-v1")
    build_dataset_parser.add_argument("--parser-version", default="local-replay-loader-v1")
    build_dataset_parser.add_argument("--belief-version", default="belief-v1")

    build_pilot_parser = subparsers.add_parser("build-policy-dataset-pilot", help="Build the first Gen 9 OU policy pilot dataset.")
    build_pilot_parser.add_argument("--format", default="gen9ou")
    build_pilot_parser.add_argument("--replays", nargs="+", required=True)
    build_pilot_parser.add_argument("--output", default="data/policy/datasets/policy-dataset-pilot-1")

    report_dataset_parser = subparsers.add_parser("report-policy-dataset", help="Report quality statistics for replay-derived policy examples.")
    report_dataset_parser.add_argument("--format", required=True)
    report_dataset_parser.add_argument("--replays", nargs="+", required=True)
    report_dataset_parser.add_argument("--output")

    report_pilot_parser = subparsers.add_parser("report-policy-pilot", help="Report pilot diversity, fingerprints and audit status.")
    report_pilot_parser.add_argument("--format", required=True)
    report_pilot_parser.add_argument("--replays", nargs="+", required=True)
    report_pilot_parser.add_argument("--output")

    coverage_dataset_parser = subparsers.add_parser("coverage-policy-dataset", help="Report replay catalog coverage for policy datasets.")
    coverage_dataset_parser.add_argument("--format", required=True)
    coverage_dataset_parser.add_argument("--database", default="data/database/replays.db")
    coverage_dataset_parser.add_argument("--output")

    audit_dataset_parser = subparsers.add_parser("audit-policy-dataset", help="Fail if a built policy dataset has severe audit violations.")
    audit_dataset_parser.add_argument("--dataset", required=True)

    evaluate_baselines_parser = subparsers.add_parser("evaluate-policy-baselines", help="Evaluate policy predictors on replay-derived examples.")
    evaluate_baselines_parser.add_argument("--format", required=True)
    evaluate_baselines_parser.add_argument("--replays", nargs="+", required=True)
    evaluate_baselines_parser.add_argument("--output")

    compare_baselines_parser = subparsers.add_parser("compare-policy-baselines", help="Compare frequency baseline against heuristic policy.")
    compare_baselines_parser.add_argument("--format", required=True)
    compare_baselines_parser.add_argument("--replays", nargs="+", required=True)
    compare_baselines_parser.add_argument("--output")

    regressions_parser = subparsers.add_parser("test-regressions", help="Run fixed decision/regression cases.")
    regressions_parser.add_argument("--agent", choices=["pokebrain-v1", "search-v1", "search-v1-cache"], default="pokebrain-v1")
    regressions_parser.add_argument("--cases", default="benchmarks/decision_cases")

    args = parser.parse_args()

    if args.command == "analyze-team":
        analyze_team(args.format, Path(args.file))
    elif args.command == "calculate-damage":
        calculate_damage(
            generation=args.generation,
            attacker_path=Path(args.attacker),
            defender_path=Path(args.defender),
            move=args.move,
        )
    elif args.command == "matchup":
        matchup(
            generation=args.generation,
            pokemon_a_path=Path(args.pokemon_a),
            pokemon_b_path=Path(args.pokemon_b),
        )
    elif args.command == "team-matchup":
        team_matchup(
            generation=args.generation,
            format_id=args.format,
            team_a_path=Path(args.team_a),
            team_b_path=Path(args.team_b),
        )
    elif args.command == "decide-action":
        decide_action(Path(args.state), DecisionStyle(args.style))
    elif args.command == "benchmark":
        run_benchmark_command(
            format_id=args.format,
            agent_a=args.agent_a,
            agent_b=args.agent_b,
            battles=args.battles,
            teams=Path(args.teams),
            seed=args.seed,
            maximum_turns=args.maximum_turns,
            timeout_seconds=args.timeout_seconds,
            parallel_workers=args.parallel_workers,
            database_path=Path(args.database),
        )
    elif args.command == "compare-benchmarks":
        compare_benchmark_command(
            run_a=args.run_a,
            run_b=args.run_b,
            database_path=Path(args.database),
        )
    elif args.command == "benchmark-performance":
        run_performance_benchmark_command(
            format_id=args.format,
            agents=tuple(args.agents),
            pairs=args.pairs,
            teams=Path(args.teams),
            seed=args.seed,
            maximum_turns=args.maximum_turns,
            timeout_seconds=args.timeout_seconds,
            parallel_workers=args.parallel_workers,
            database_path=Path(args.database),
        )
    elif args.command == "review-battle":
        review_battle_command(
            battle_path=Path(args.battle),
            write_regressions=args.write_regressions,
            regressions_dir=Path(args.regressions_dir),
        )
    elif args.command == "review-benchmark":
        review_benchmark_command(
            run_id=args.run,
            database_path=Path(args.database),
            only_losses=args.only_losses,
            top=args.top,
            minimum_battles=args.min_battles,
        )
    elif args.command == "review-benchmark-leads":
        review_benchmark_leads_command(
            run_id=args.run,
            database_path=Path(args.database),
            maximum_turns=args.max_turns,
            top=args.top,
            minimum_battles=args.min_battles,
        )
    elif args.command == "evaluate-policy":
        evaluate_policy_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            rating_bucket=args.rating_bucket,
        )
    elif args.command == "calibrate-policy":
        calibrate_policy_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_path=Path(args.output),
            rating_bucket=args.rating_bucket,
        )
    elif args.command == "collect-replays":
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
    elif args.command == "parse-replays":
        parse_replays_command(
            format_id=args.format,
            status=args.status,
            parser_version=args.parser_version,
            limit=args.limit,
            database_path=Path(args.database),
            raw_root=Path(args.raw_root),
            output_dir=Path(args.output),
        )
    elif args.command == "build-policy-dataset":
        build_policy_dataset_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_dir=Path(args.output),
            dataset_version=args.dataset_version,
            parser_version=args.parser_version,
            belief_version=args.belief_version,
        )
    elif args.command == "build-policy-dataset-pilot":
        build_policy_dataset_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_dir=Path(args.output),
            dataset_version="policy-dataset-pilot-1",
            parser_version="local-replay-loader-v1",
            belief_version="belief-v1",
        )
    elif args.command == "report-policy-dataset":
        report_policy_dataset_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_path=Path(args.output) if args.output else None,
        )
    elif args.command == "report-policy-pilot":
        report_policy_pilot_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_dir=Path(args.output) if args.output else None,
        )
    elif args.command == "coverage-policy-dataset":
        coverage_policy_dataset_command(
            format_id=args.format,
            database_path=Path(args.database),
            output_path=Path(args.output) if args.output else None,
        )
    elif args.command == "audit-policy-dataset":
        audit_policy_dataset_command(dataset_dir=Path(args.dataset))
    elif args.command == "evaluate-policy-baselines":
        evaluate_policy_baselines_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_dir=Path(args.output) if args.output else None,
        )
    elif args.command == "compare-policy-baselines":
        compare_policy_baselines_command(
            replay_paths=tuple(Path(path) for path in args.replays),
            format_id=args.format,
            output_dir=Path(args.output) if args.output else None,
        )
    elif args.command == "test-regressions":
        test_regressions_command(agent=args.agent, cases_dir=Path(args.cases))


def analyze_team(format_id: str, team_file: Path) -> None:
    team_text = team_file.read_text(encoding="utf-8")
    analysis = TeamAnalyzer().analyze(format_id=format_id, team_text=team_text)
    print(TextTeamAnalysisRenderer().render(analysis))


def calculate_damage(
    generation: int,
    attacker_path: Path,
    defender_path: Path,
    move: str,
) -> None:
    attacker = load_damage_pokemon(attacker_path)
    defender = load_damage_pokemon(defender_path)
    result = ShowdownDamageEngine().calculate(
        DamageRequest(
            generation=generation,
            attacker=attacker,
            defender=defender,
            move_id=move,
        )
    )

    print(f"{result.attacker_id} uses {result.move_id} against {result.defender_id}")
    print("")
    print(f"Damage: {result.minimum_damage}-{result.maximum_damage} HP")
    print(f"Percentage: {result.minimum_percent}%-{result.maximum_percent}%")
    print(f"Result: {result.classification.replace('_', ' ')}")
    print(f"Description: {result.description}")


def load_damage_pokemon(path: Path) -> DamagePokemon:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return DamagePokemon(
        species=data["species"],
        level=data.get("level", 100),
        ability=data.get("ability"),
        item=data.get("item"),
        nature=data.get("nature"),
        evs=data.get("evs", {}),
        ivs=data.get("ivs", {}),
        boosts=data.get("boosts", {}),
        status=data.get("status"),
        tera_type=data.get("teraType"),
        current_hp=data.get("currentHp"),
    )


def matchup(generation: int, pokemon_a_path: Path, pokemon_b_path: Path) -> None:
    pokemon_a = load_pokemon_set(pokemon_a_path)
    pokemon_b = load_pokemon_set(pokemon_b_path)
    analysis = MatchupAnalyzer().compare(
        generation=generation,
        pokemon_a=pokemon_a,
        pokemon_b=pokemon_b,
    )
    print(TextMatchupRenderer().render(analysis))


def team_matchup(
    generation: int,
    format_id: str,
    team_a_path: Path,
    team_b_path: Path,
) -> None:
    from pokebrain.team.parser import TeamParser

    parser = TeamParser()
    parsed_a = parser.parse(format_id, team_a_path.read_text(encoding="utf-8"))
    parsed_b = parser.parse(format_id, team_b_path.read_text(encoding="utf-8"))
    if parsed_a.team is None or parsed_b.team is None:
        raise SystemExit("Both team files must contain at least one parseable Pokemon.")
    analysis = TeamMatchupAnalyzer().compare(
        generation=generation,
        team_a=parsed_a.team,
        team_b=parsed_b.team,
    )
    print(TextTeamMatchupRenderer().render(analysis))


def decide_action(state_path: Path, style: DecisionStyle) -> None:
    state = load_battle_state(state_path)
    decision = MoveDecisionEngine().decide(state, style=style)
    print(TextMoveDecisionRenderer().render(decision))


def load_pokemon_set(path: Path) -> PokemonSet:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return PokemonSet(
        species_id=to_id(str(data["species"])),
        nickname=data.get("nickname"),
        item_id=_optional_id(data.get("item")),
        ability_id=_optional_id(data.get("ability")),
        level=data.get("level", 100),
        nature=data.get("nature"),
        tera_type=data.get("teraType"),
        moves=tuple(_optional_id(move) or "" for move in data.get("moves", ())),
        evs=EVSpread(
            hp=data.get("evs", {}).get("hp", 0),
            attack=data.get("evs", {}).get("atk", 0),
            defense=data.get("evs", {}).get("def", 0),
            special_attack=data.get("evs", {}).get("spa", 0),
            special_defense=data.get("evs", {}).get("spd", 0),
            speed=data.get("evs", {}).get("spe", 0),
        ),
        ivs=IVSpread(
            hp=data.get("ivs", {}).get("hp", 31),
            attack=data.get("ivs", {}).get("atk", 31),
            defense=data.get("ivs", {}).get("def", 31),
            special_attack=data.get("ivs", {}).get("spa", 31),
            special_defense=data.get("ivs", {}).get("spd", 31),
            speed=data.get("ivs", {}).get("spe", 31),
        ),
    )


def _optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    return to_id(value)


if __name__ == "__main__":
    main()
