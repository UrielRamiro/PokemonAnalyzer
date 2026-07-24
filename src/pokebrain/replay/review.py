from __future__ import annotations

from collections import Counter

from pokebrain.policy_calibration.evaluation import probability_for_action
from pokebrain.policy_calibration.perspective import swap_perspective
from pokebrain.replay.detectors import detect_error_types
from pokebrain.replay.models import BattleReplay, BattleReview, DecisionErrorType, PolicyPredictionReview, ReviewedDecision, TurnEvaluation
from pokebrain.replay.scoring import calculate_regret
from pokebrain.search.policy import HeuristicOpponentPolicyModel


class ReplayAnalyzer:
    def __init__(self, policy_model: HeuristicOpponentPolicyModel | None = None) -> None:
        self.policy_model = policy_model or HeuristicOpponentPolicyModel()

    def review(self, replay: BattleReplay, regret_threshold: float = 20.0) -> BattleReview:
        reviewed: list[ReviewedDecision] = []
        turning_points: list[TurnEvaluation] = []
        for record in replay.decisions:
            regret = calculate_regret(record)
            errors = detect_error_types(record)
            turning_point = _turn_evaluation(record.turn, regret.regret)
            if turning_point and is_turning_point(turning_point):
                turning_points.append(turning_point)
            if regret.regret >= regret_threshold or errors != (DecisionErrorType.UNKNOWN,):
                reviewed.append(
                    ReviewedDecision(
                        record=record,
                        regret=regret,
                        error_types=errors,
                        turning_point=turning_point,
                        policy_prediction=self._policy_prediction(record),
                    )
                )

        recurring = tuple(
            error
            for error, _count in Counter(
                error for decision in reviewed for error in decision.error_types if error is not DecisionErrorType.UNKNOWN
            ).most_common()
        )
        return BattleReview(
            battle_id=replay.battle_id,
            winner=replay.winner,
            critical_decisions=tuple(sorted(reviewed, key=lambda item: item.regret.regret, reverse=True)),
            turning_points=tuple(turning_points),
            recurring_error_types=recurring,
            summary=_summary(replay, reviewed, recurring),
        )

    def _policy_prediction(self, record) -> PolicyPredictionReview | None:
        legal_actions = tuple(
            action
            for action in record.legal_actions
            if action.move_id not in {"team", "unknown"} and (action.move_id or action.switch_target_id)
        )
        if not legal_actions or record.selected_action not in legal_actions:
            return None
        observed_state = swap_perspective(record.battle_state)
        predicted = self.policy_model.predict(observed_state, None, legal_actions)
        return PolicyPredictionReview(
            actual_action=record.selected_action,
            predicted_actions=predicted,
            actual_probability=probability_for_action(predicted, record.selected_action),
            covered_top_k=record.selected_action in tuple(item.action for item in predicted[:4]),
        )


def is_turning_point(evaluation: TurnEvaluation) -> bool:
    return evaluation.value_change <= -0.20


class TextBattleReviewRenderer:
    def render(self, review: BattleReview, top: int = 10) -> str:
        lines = [
            f"Batalha {review.battle_id}",
            f"Resultado: {review.winner or 'sem vencedor'}",
            "",
            review.summary,
            "",
            "Decisoes criticas:",
        ]
        if not review.critical_decisions:
            lines.append("- nenhuma decisao critica encontrada")
        for decision in review.critical_decisions[:top]:
            record = decision.record
            lines.extend(
                [
                    (
                        f"- Turno {record.turn} {record.player_id}: "
                        f"{_format_action(record.selected_action)} | "
                        f"arrependimento {decision.regret.regret:.1f} "
                        f"({decision.regret.classification})"
                    ),
                    f"  tipos: {', '.join(error.value for error in decision.error_types)}",
                    f"  score escolhido: {decision.regret.selected_score:.1f}; melhor disponivel: {decision.regret.best_available_score:.1f}",
                ]
            )
            if decision.policy_prediction is not None:
                policy = decision.policy_prediction
                lines.append("  acao adversaria prevista:")
                for predicted in policy.predicted_actions[:4]:
                    lines.append(f"  - {_format_action(predicted.action)}: {predicted.probability:.0%}")
                lines.append(f"  acao real: {_format_action(policy.actual_action)}")
                lines.append(f"  coberta pelo Top-K: {'sim' if policy.covered_top_k else 'nao'}")
                lines.append(f"  probabilidade atribuida: {policy.actual_probability:.0%}")
        if review.turning_points:
            lines.append("")
            lines.append("Possiveis pontos de virada:")
            for point in review.turning_points[:top]:
                lines.append(
                    f"- Turno {point.turn}: {point.value_before_action:.0%} -> {point.value_after_action:.0%}"
                )
        return "\n".join(lines)


def _turn_evaluation(turn: int, regret: float) -> TurnEvaluation | None:
    if regret <= 0:
        return None
    before = 0.5
    after = max(0.0, before - regret / 100)
    return TurnEvaluation(
        turn=turn,
        value_before_action=before,
        value_after_action=after,
        value_change=after - before,
    )


def _summary(replay: BattleReplay, decisions: list[ReviewedDecision], recurring: tuple[DecisionErrorType, ...]) -> str:
    if not decisions:
        return "Nenhum erro objetivo ou arrependimento alto foi encontrado nos logs disponiveis."
    main = decisions[0]
    types = ", ".join(error.value for error in recurring[:3]) or "unknown"
    return (
        f"{len(decisions)} decisoes suspeitas encontradas. "
        f"Maior arrependimento no turno {main.record.turn}: {main.regret.regret:.1f}. "
        f"Categorias recorrentes: {types}."
    )


def _format_action(action) -> str:
    if action.move_id:
        return f"move {action.move_id}"
    return f"switch {action.switch_target_id}"
