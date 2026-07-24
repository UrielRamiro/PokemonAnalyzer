from __future__ import annotations

from pokebrain.benchmark.models import BenchmarkComparison
from pokebrain.benchmark.report import build_benchmark_report
from pokebrain.benchmark.repository import BenchmarkResultRepository


def compare_benchmark_runs(
    repository: BenchmarkResultRepository,
    run_a_id: str,
    run_b_id: str,
) -> BenchmarkComparison:
    agent_a, _ = repository.get_run_agents(run_a_id)
    agent_b, _ = repository.get_run_agents(run_b_id)
    report_a = build_benchmark_report(run_a_id, repository.load_battles(run_a_id), primary_agent=agent_a)
    report_b = build_benchmark_report(run_b_id, repository.load_battles(run_b_id), primary_agent=agent_b)
    a_lower, a_upper = report_a.confidence_interval_95
    b_lower, b_upper = report_b.confidence_interval_95
    return BenchmarkComparison(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        run_a_adjusted_win_rate=report_a.adjusted_win_rate,
        run_b_adjusted_win_rate=report_b.adjusted_win_rate,
        difference=report_a.adjusted_win_rate - report_b.adjusted_win_rate,
        run_a_confidence_interval_95=report_a.confidence_interval_95,
        run_b_confidence_interval_95=report_b.confidence_interval_95,
        likely_meaningful=a_lower > b_upper or b_lower > a_upper,
    )


class TextBenchmarkComparisonRenderer:
    def render(self, comparison: BenchmarkComparison) -> str:
        a_lower, a_upper = comparison.run_a_confidence_interval_95
        b_lower, b_upper = comparison.run_b_confidence_interval_95
        meaning = "sim" if comparison.likely_meaningful else "nao"
        return "\n".join(
            [
                "Comparacao de benchmarks",
                "",
                f"Run A: {comparison.run_a_id}",
                f"Run B: {comparison.run_b_id}",
                "",
                f"Run A ajustado: {_percent(comparison.run_a_adjusted_win_rate)}",
                f"Run B ajustado: {_percent(comparison.run_b_adjusted_win_rate)}",
                f"Diferenca: {_percent(comparison.difference)}",
                "",
                f"IC 95% A: {_percent(a_lower)}-{_percent(a_upper)}",
                f"IC 95% B: {_percent(b_lower)}-{_percent(b_upper)}",
                f"Diferenca provavelmente significativa: {meaning}",
            ]
        )


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"
