from __future__ import annotations

import json
from pathlib import Path

from pokebrain.benchmark.loss_report import TextBenchmarkLossRenderer, build_loss_report
from pokebrain.benchmark.repository import BenchmarkResultRepository
from pokebrain.replay.aggregate import aggregate_reviews
from pokebrain.replay.loader import ReplayLoader
from pokebrain.replay.regression import write_regression_cases
from pokebrain.replay.review import ReplayAnalyzer, TextBattleReviewRenderer


def review_battle_command(
    *,
    battle_path: Path,
    write_regressions: bool = False,
    regressions_dir: Path = Path("regressions"),
) -> None:
    replay = ReplayLoader().load(battle_path)
    review = ReplayAnalyzer().review(replay)
    print(TextBattleReviewRenderer().render(review))
    if write_regressions:
        paths = write_regression_cases(review, regressions_dir)
        print("")
        print(f"Regressoes escritas: {len(paths)}")
        for path in paths:
            print(f"- {path}")


def review_benchmark_command(
    *,
    run_id: str,
    database_path: Path,
    only_losses: bool,
    top: int,
    minimum_battles: int = 3,
) -> None:
    repository = BenchmarkResultRepository(database_path)
    battles = repository.load_battles(run_id)
    agent_a, _agent_b = repository.get_run_agents(run_id)
    reviews = []
    for battle in battles:
        if only_losses and battle.winner == "PokeBrain":
            continue
        if not battle.run_dir:
            continue
        path = Path(battle.run_dir)
        if not path.exists():
            continue
        reviews.append(ReplayAnalyzer().review(ReplayLoader().load(path)))

    aggregates = aggregate_reviews(tuple(reviews))
    print(f"{len(reviews)} batalhas analisadas")
    print("")
    print("Principais categorias:")
    if not aggregates:
        print("- nenhuma categoria objetiva encontrada")
    for aggregate in aggregates[:top]:
        print(
            f"- {aggregate.error_type.value}: {aggregate.occurrence_count} ocorrencias, "
            f"perda media {aggregate.average_value_loss:.0%}, "
            f"matchups: {', '.join(aggregate.affected_matchups[:8]) or 'n/a'}"
        )

    print("")
    print(
        TextBenchmarkLossRenderer().render(
            build_loss_report(
                run_id=run_id,
                battles=tuple(battles),
                primary_agent=agent_a,
                top=top,
                minimum_battles=minimum_battles,
            )
        )
    )
    print("")
    _print_agent_fallback_summary(battles=tuple(battles), primary_agent=agent_a)


def _print_agent_fallback_summary(*, battles, primary_agent: str) -> None:
    decision_count = 0
    fallback_count = 0
    reasons: dict[str, int] = {}
    for battle in battles:
        side = _side_for_agent(battle, primary_agent)
        if side is None or not battle.run_dir:
            continue
        path = Path(battle.run_dir) / "decisions.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("player_id") != side or "selected_action" not in entry:
                    continue
                if int(entry.get("turn") or 0) <= 0:
                    continue
                decision_count += 1
                metrics = entry.get("metrics") or {}
                if metrics.get("search_fallback_used"):
                    fallback_count += 1
                    reason = str(metrics.get("search_interruption_reason") or "unknown")
                    reasons[reason] = reasons.get(reason, 0) + 1

    print("Fallback do agente analisado:")
    if decision_count == 0:
        print("- sem decisoes analisaveis")
        return
    print(f"- decisoes: {decision_count}")
    print(f"- fallbacks: {fallback_count} ({fallback_count / decision_count:.1%})")
    for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
        print(f"- {reason}: {count}")


def _side_for_agent(battle, primary_agent: str) -> str | None:
    if battle.agent_a == primary_agent:
        return "p1"
    if battle.agent_b == primary_agent:
        return "p2"
    return None
