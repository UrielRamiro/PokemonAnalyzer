from __future__ import annotations

from pathlib import Path

from pokebrain.replays.catalog import ReplayCatalog
from pokebrain.replays.collector import ReplayCollector
from pokebrain.replays.extraction import PolicyExampleExtractionJob
from pokebrain.replays.http import ReplayDownloadClient, ReplayHttpConfig, ReplaySearchClient
from pokebrain.replays.models import ReplayCollectionReport, ReplayCollectionRequest
from pokebrain.replays.quality import ReplayQualityConfig
from pokebrain.replays.storage import RawReplayStorage


def collect_replays_command(
    *,
    format_id: str,
    limit: int,
    before: int | None = None,
    minimum_rating: int | None = None,
    maximum_rating: int | None = None,
    database_path: Path = Path("data/database/replays.db"),
    raw_root: Path = Path("data/replays/raw"),
    minimum_turns: int = 5,
    require_finished_battle: bool = True,
    requests_per_second: float = 2.0,
) -> None:
    config = ReplayHttpConfig(requests_per_second=requests_per_second)
    collector = ReplayCollector(
        search_client=ReplaySearchClient(config=config),
        download_client=ReplayDownloadClient(config=config),
        catalog=ReplayCatalog(database_path),
        storage=RawReplayStorage(raw_root),
        quality_config=ReplayQualityConfig(
            minimum_turns=minimum_turns,
            require_finished_battle=require_finished_battle,
            require_rating=False,
        ),
    )
    report = collector.collect(
        ReplayCollectionRequest(
            format_id=format_id,
            maximum_replays=limit,
            before=before,
            minimum_rating=minimum_rating,
            maximum_rating=maximum_rating,
        )
    )
    print(render_collection_report(report))


def parse_replays_command(
    *,
    format_id: str,
    status: str = "pending",
    parser_version: str = "public-replay-parser-v1",
    limit: int | None = None,
    database_path: Path = Path("data/database/replays.db"),
    raw_root: Path = Path("data/replays/raw"),
    output_dir: Path = Path("data/policy/examples"),
) -> None:
    report = PolicyExampleExtractionJob(
        catalog=ReplayCatalog(database_path),
        storage=RawReplayStorage(raw_root),
    ).run_pending(
        format_id=format_id,
        parser_version=parser_version,
        status=status,
        limit=limit,
        output_dir=output_dir,
    )
    print(f"Solicitados: {report.requested}")
    print(f"Parseados: {report.parsed}")
    print(f"Exemplos: {report.examples}")
    print(f"Falhas: {report.failed}")


def render_collection_report(report: ReplayCollectionReport) -> str:
    return "\n".join(
        (
            f"Formato: {report.format_id}",
            f"Descobertos: {report.discovered}",
            f"Baixados: {report.downloaded}",
            f"Ja existentes: {report.already_present}",
            f"Filtrados: {report.filtered}",
            f"Nao encontrados: {report.not_found}",
            f"Falhas: {report.failed}",
            f"Paginas consultadas: {report.pages_requested}",
        )
    )
