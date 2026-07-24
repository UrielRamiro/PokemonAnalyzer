from __future__ import annotations

from collections import defaultdict

from pokebrain.replay.models import BattleReview, DecisionErrorType, ErrorAggregate


def aggregate_reviews(reviews: tuple[BattleReview, ...]) -> tuple[ErrorAggregate, ...]:
    by_error: dict[DecisionErrorType, list] = defaultdict(list)
    for review in reviews:
        for decision in review.critical_decisions:
            for error in decision.error_types:
                if error is not DecisionErrorType.UNKNOWN:
                    by_error[error].append((review, decision))

    aggregates: list[ErrorAggregate] = []
    for error, entries in by_error.items():
        losses = sum(1 for review, _decision in entries if review.winner and review.winner != "PokeBrain")
        wins = sum(1 for review, _decision in entries if review.winner == "PokeBrain")
        value_losses = [entry[1].regret.regret / 100 for entry in entries]
        matchups = sorted({entry[1].record.battle_state.opponent.active.set_data.species_id for entry in entries})
        aggregates.append(
            ErrorAggregate(
                error_type=error,
                occurrence_count=len(entries),
                losses_with_error=losses,
                wins_with_error=wins,
                average_value_loss=sum(value_losses) / len(value_losses) if value_losses else 0.0,
                affected_matchups=tuple(matchups),
            )
        )
    return tuple(sorted(aggregates, key=lambda item: item.occurrence_count, reverse=True))
