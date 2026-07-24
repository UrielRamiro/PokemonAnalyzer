from __future__ import annotations

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
