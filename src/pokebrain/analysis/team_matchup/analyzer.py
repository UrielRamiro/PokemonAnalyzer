from __future__ import annotations

from collections import defaultdict

from pokebrain.analysis.matchup import MatchupAnalyzer, MatchupVerdict
from pokebrain.analysis.team_matchup.models import (
    MatchupCell,
    PokemonMatchupSummary,
    TeamMatchupAnalysis,
    TeamMatchupMatrix,
    ThreatAssessment,
)
from pokebrain.analysis.team_matchup.scoring import (
    calculate_coverage_score,
    classify_threat,
    score_for_team_a,
)
from pokebrain.damage import FieldState
from pokebrain.team.models import Team


class TeamMatchupAnalyzer:
    def __init__(self, matchup_analyzer: MatchupAnalyzer | None = None) -> None:
        self.matchup_analyzer = matchup_analyzer or MatchupAnalyzer()

    def compare(
        self,
        generation: int,
        team_a: Team,
        team_b: Team,
        field: FieldState | None = None,
    ) -> TeamMatchupAnalysis:
        field = field or FieldState()
        cells: list[MatchupCell] = []
        for member_a in team_a.members:
            for member_b in team_b.members:
                analysis = self.matchup_analyzer.compare(
                    generation=generation,
                    pokemon_a=member_a,
                    pokemon_b=member_b,
                    field=field,
                )
                cells.append(
                    MatchupCell(
                        pokemon_a_id=member_a.species_id,
                        pokemon_b_id=member_b.species_id,
                        analysis=analysis,
                    )
                )

        matrix = TeamMatchupMatrix(
            team_a_ids=tuple(member.species_id for member in team_a.members),
            team_b_ids=tuple(member.species_id for member in team_b.members),
            cells=tuple(cells),
        )
        return self._summarize(generation, matrix)

    def _summarize(self, generation: int, matrix: TeamMatchupMatrix) -> TeamMatchupAnalysis:
        team_a_summaries = tuple(
            self._summary_for(matrix, pokemon_id, perspective="a")
            for pokemon_id in matrix.team_a_ids
        )
        team_b_summaries = tuple(
            self._summary_for(matrix, pokemon_id, perspective="b")
            for pokemon_id in matrix.team_b_ids
        )
        threats_to_team_a = tuple(
            self._threat_assessment(matrix, threat_id, target_team="a")
            for threat_id in matrix.team_b_ids
        )
        threats_to_team_b = tuple(
            self._threat_assessment(matrix, threat_id, target_team="b")
            for threat_id in matrix.team_a_ids
        )
        scores = [
            score_for_team_a(cell.analysis.verdict, cell.analysis.confidence).weighted_score
            for cell in matrix.cells
        ]
        overall_score = sum(scores) / len(scores) if scores else 0.0
        return TeamMatchupAnalysis(
            generation=generation,
            matrix=matrix,
            team_a_summaries=team_a_summaries,
            team_b_summaries=team_b_summaries,
            threats_to_team_a=threats_to_team_a,
            threats_to_team_b=threats_to_team_b,
            overall_score_for_team_a=overall_score,
            warnings=self._warnings(threats_to_team_a, threats_to_team_b),
            limitations=(
                "Direct matchups only; not a prediction of match win probability.",
                "Switching, hidden information, sacks, setup sequencing and Terastalization are not modeled.",
            ),
        )

    def _summary_for(
        self,
        matrix: TeamMatchupMatrix,
        pokemon_id: str,
        perspective: str,
    ) -> PokemonMatchupSummary:
        favorable: list[str] = []
        unfavorable: list[str] = []
        even: list[str] = []
        uncertain: list[str] = []

        for cell in matrix.cells:
            if perspective == "a":
                if cell.pokemon_a_id != pokemon_id:
                    continue
                opponent_id = cell.pokemon_b_id
                verdict = cell.analysis.verdict
                favored = MatchupVerdict.A_FAVORED
                unfavored = MatchupVerdict.B_FAVORED
            else:
                if cell.pokemon_b_id != pokemon_id:
                    continue
                opponent_id = cell.pokemon_a_id
                verdict = cell.analysis.verdict
                favored = MatchupVerdict.B_FAVORED
                unfavored = MatchupVerdict.A_FAVORED

            if verdict is favored:
                favorable.append(opponent_id)
            elif verdict is unfavored:
                unfavorable.append(opponent_id)
            elif verdict is MatchupVerdict.UNCERTAIN:
                uncertain.append(opponent_id)
            else:
                even.append(opponent_id)

        return PokemonMatchupSummary(
            pokemon_id=pokemon_id,
            favorable_against=tuple(favorable),
            unfavorable_against=tuple(unfavorable),
            even_against=tuple(even),
            uncertain_against=tuple(uncertain),
            coverage_score=calculate_coverage_score(
                len(favorable),
                len(unfavorable),
                len(even),
                len(uncertain),
            ),
        )

    def _threat_assessment(
        self,
        matrix: TeamMatchupMatrix,
        threat_id: str,
        target_team: str,
    ) -> ThreatAssessment:
        favorable_answers: list[str] = []
        neutral_answers: list[str] = []
        unfavorable_answers: list[str] = []

        for cell in matrix.cells:
            if target_team == "a":
                if cell.pokemon_b_id != threat_id:
                    continue
                answer_id = cell.pokemon_a_id
                if cell.analysis.verdict is MatchupVerdict.A_FAVORED:
                    favorable_answers.append(answer_id)
                elif cell.analysis.verdict is MatchupVerdict.EVEN:
                    neutral_answers.append(answer_id)
                else:
                    unfavorable_answers.append(answer_id)
            else:
                if cell.pokemon_a_id != threat_id:
                    continue
                answer_id = cell.pokemon_b_id
                if cell.analysis.verdict is MatchupVerdict.B_FAVORED:
                    favorable_answers.append(answer_id)
                elif cell.analysis.verdict is MatchupVerdict.EVEN:
                    neutral_answers.append(answer_id)
                else:
                    unfavorable_answers.append(answer_id)

        return ThreatAssessment(
            threat_id=threat_id,
            favorable_answers=tuple(favorable_answers),
            neutral_answers=tuple(neutral_answers),
            unfavorable_answers=tuple(unfavorable_answers),
            severity=classify_threat(len(favorable_answers), len(neutral_answers)),
        )

    def _warnings(
        self,
        threats_to_team_a: tuple[ThreatAssessment, ...],
        threats_to_team_b: tuple[ThreatAssessment, ...],
    ) -> tuple[str, ...]:
        warnings = []
        for threat in threats_to_team_a:
            if threat.severity in {"critical", "high"}:
                warnings.append(f"Team A has limited direct answers to {threat.threat_id}.")
        for threat in threats_to_team_b:
            if threat.severity in {"critical", "high"}:
                warnings.append(f"Team B has limited direct answers to {threat.threat_id}.")
        return tuple(warnings)

