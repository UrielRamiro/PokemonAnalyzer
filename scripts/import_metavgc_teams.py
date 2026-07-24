from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


DEFAULT_SOURCE_URL = "https://metavgc.com/pt/times/naic-2026"
DEFAULT_OUTPUT_DIR = Path("teams/champions-vgc-pilot-1")

STAT_ORDER = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")
POKEMON_TYPES = {
    "Normal",
    "Fire",
    "Water",
    "Electric",
    "Grass",
    "Ice",
    "Fighting",
    "Poison",
    "Ground",
    "Flying",
    "Psychic",
    "Bug",
    "Rock",
    "Ghost",
    "Dragon",
    "Dark",
    "Steel",
    "Fairy",
}


@dataclass(frozen=True, slots=True)
class ImportedTeam:
    title: str
    source_url: str
    filename: str
    pokemon_count: int


@dataclass(frozen=True, slots=True)
class TeamImportCandidate:
    title: str
    source_url: str
    pokemon: tuple["PokemonExport", ...]


@dataclass(frozen=True, slots=True)
class PokemonExport:
    species: str
    item: str
    nature: str
    ability: str
    stat_points: tuple[tuple[str, int], ...]
    moves: tuple[str, ...]

    def to_showdown(self) -> str:
        lines = [
            f"{self.species} @ {self.item}",
            f"Ability: {self.ability}",
        ]
        if self.stat_points:
            lines.append("EVs: " + " / ".join(f"{value} {stat}" for stat, value in self.stat_points))
        lines.append(f"{self.nature} Nature")
        lines.extend(f"- {move}" for move in self.moves)
        return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import MetaVGC teams into a local Showdown team pool.")
    parser.add_argument("--source", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-pages", type=int, default=1, help="Maximum number of listing pages to scan.")
    parser.add_argument("--page-param", default="page", help="Query parameter used to build listing page URLs.")
    parser.add_argument(
        "--page-url-template",
        help="Optional listing URL template, for example 'https://site/times?page={page}'.",
    )
    parser.add_argument("--api", action="store_true", help="Use MetaVGC's team API instead of visible HTML links.")
    parser.add_argument("--tournament-id", help="MetaVGC tournament id, for example 436 for NAIC 2026.")
    parser.add_argument("--api-batch-size", type=int, default=50)
    parser.add_argument("--slug-contains", help="Only import team URLs containing this text. Defaults to the source page slug.")
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification for environments without local CA roots.")
    args = parser.parse_args()

    imported = import_metavgc_teams(
        source_url=args.source,
        output_dir=Path(args.output),
        limit=args.limit,
        max_pages=args.max_pages,
        page_param=args.page_param,
        page_url_template=args.page_url_template,
        use_api=args.api,
        tournament_id=args.tournament_id,
        api_batch_size=args.api_batch_size,
        sleep_seconds=args.sleep,
        overwrite=args.overwrite,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        verify_tls=not args.insecure,
        slug_contains=args.slug_contains,
    )
    print(f"Source: {args.source}")
    print(f"Teams imported: {len(imported)}")
    print(f"Output: {args.output}")
    for team in imported:
        print(f"- {team.filename}: {team.title} ({team.pokemon_count} Pokemon)")


def import_metavgc_teams(
    *,
    source_url: str,
    output_dir: Path,
    limit: int | None = None,
    max_pages: int = 1,
    page_param: str = "page",
    page_url_template: str | None = None,
    use_api: bool = False,
    tournament_id: str | None = None,
    api_batch_size: int = 50,
    sleep_seconds: float = 0.25,
    overwrite: bool = False,
    skip_existing: bool = False,
    dry_run: bool = False,
    verify_tls: bool = True,
    slug_contains: str | None = None,
) -> tuple[ImportedTeam, ...]:
    if use_api or tournament_id:
        candidates = collect_api_team_candidates(
            source_url=source_url,
            tournament_id=tournament_id,
            limit=limit,
            batch_size=api_batch_size,
            verify_tls=verify_tls,
        )
    else:
        team_urls = collect_team_urls(
            source_url=source_url,
            max_pages=max_pages,
            page_param=page_param,
            page_url_template=page_url_template,
            slug_contains=slug_contains,
            verify_tls=verify_tls,
        )
        if limit is not None:
            team_urls = team_urls[:limit]
        if not team_urls:
            raise SystemExit(f"No MetaVGC team links found at {source_url}")
        candidates = collect_html_team_candidates(team_urls, verify_tls=verify_tls)

    output_dir.mkdir(parents=True, exist_ok=True)
    imported: list[ImportedTeam] = []
    for index, candidate in enumerate(candidates, start=1):
        if len(candidate.pokemon) != 6:
            raise SystemExit(f"Expected 6 Pokemon in {candidate.source_url}, parsed {len(candidate.pokemon)}.")
        filename = f"{index:03d}-{slugify(candidate.title)}.txt"
        path = output_dir / filename
        if path.exists() and skip_existing:
            continue
        if path.exists() and not overwrite:
            raise SystemExit(f"Refusing to overwrite existing team file: {path}")
        showdown = "\n\n".join(member.to_showdown() for member in candidate.pokemon) + "\n"
        if not dry_run:
            path.write_text(showdown, encoding="utf-8")
        imported.append(
            ImportedTeam(
                title=candidate.title,
                source_url=candidate.source_url,
                filename=filename,
                pokemon_count=len(candidate.pokemon),
            )
        )
        if sleep_seconds:
            time.sleep(sleep_seconds)

    if not dry_run:
        write_manifest(output_dir / "metavgc_import_manifest.json", source_url, imported)
    return tuple(imported)


def collect_html_team_candidates(team_urls: tuple[str, ...], *, verify_tls: bool = True) -> tuple[TeamImportCandidate, ...]:
    candidates = []
    for team_url in team_urls:
        page_html = fetch_text(team_url, verify_tls=verify_tls)
        title, pokemon = parse_team_page(page_html)
        candidates.append(TeamImportCandidate(title=title, source_url=team_url, pokemon=pokemon))
    return tuple(candidates)


def collect_api_team_candidates(
    *,
    source_url: str,
    tournament_id: str | None = None,
    limit: int | None = None,
    batch_size: int = 50,
    verify_tls: bool = True,
) -> tuple[TeamImportCandidate, ...]:
    if batch_size < 1:
        raise ValueError("--api-batch-size must be at least 1.")
    resolved_tournament_id = tournament_id or extract_featured_tournament_id(fetch_text(source_url, verify_tls=verify_tls))
    if not resolved_tournament_id:
        raise SystemExit("Could not determine MetaVGC tournament id. Pass --tournament-id explicitly.")

    candidates: list[TeamImportCandidate] = []
    offset = 0
    while limit is None or len(candidates) < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - len(candidates))
        response = fetch_json(
            "https://metavgc.com/api/vgc/teams?locale=pt",
            {
                "isActiveFormat": True,
                "tournamentId": resolved_tournament_id,
                "noSlugsLimit": True,
                "limit": remaining,
                "offset": offset,
            },
            verify_tls=verify_tls,
        )
        data = response.get("data", [])
        if not isinstance(data, list) or not data:
            break
        for team in data:
            if isinstance(team, dict):
                candidates.append(api_team_to_candidate(team))
        offset += len(data)
        total = response.get("total")
        if isinstance(total, int) and offset >= total:
            break
    return tuple(candidates)


def fetch_json(url: str, payload: dict, *, verify_tls: bool = True) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": "pokebrain-metavgc-importer/1.0",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    context = None if verify_tls else ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        parsed = json.loads(response.read().decode(charset, errors="replace"))
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object from {url}.")
        return parsed


def api_team_to_candidate(team: dict) -> TeamImportCandidate:
    player = str(team.get("player") or "Unknown Player")
    tournament = str(team.get("tournament") or "MetaVGC Tournament")
    placement = str(team.get("placement") or "").strip()
    title = f"{player} - {tournament}" + (f" - #{placement}" if placement else "")
    public_id = str(team.get("publicId") or team.get("id") or slugify(title))
    pokemon = tuple(api_pokemon_to_export(member) for member in team.get("pokemon", []) if isinstance(member, dict))
    return TeamImportCandidate(
        title=title,
        source_url=f"https://metavgc.com/pt/times/{public_id}",
        pokemon=pokemon,
    )


def api_pokemon_to_export(member: dict) -> PokemonExport:
    evs = member.get("evs")
    stats: list[tuple[str, int]] = []
    if isinstance(evs, dict):
        for api_name, stat in (("hp", "HP"), ("atk", "Atk"), ("def", "Def"), ("spa", "SpA"), ("spd", "SpD"), ("spe", "Spe")):
            value = evs.get(api_name, 0)
            if isinstance(value, int) and value > 0:
                stats.append((stat, value))
    moves = tuple(str(move) for move in member.get("moves", []) if move)
    return PokemonExport(
        species=str(member.get("name") or "Unknown"),
        item=str(member.get("item") or ""),
        nature=str(member.get("nature") or "Serious"),
        ability=str(member.get("ability") or ""),
        stat_points=tuple(stats),
        moves=moves[:4],
    )


def extract_featured_tournament_id(index_html: str) -> str | None:
    normalized = html.unescape(index_html).replace("\\/", "/")
    match = re.search(r'teamSearchTournamentId\\?":\\?"?(\d+)', normalized)
    if match:
        return match.group(1)
    match = re.search(r'tournamentId\\?":\\?"?(\d+)', normalized)
    if match:
        return match.group(1)
    return None


def collect_team_urls(
    *,
    source_url: str,
    max_pages: int = 1,
    page_param: str = "page",
    page_url_template: str | None = None,
    slug_contains: str | None = None,
    verify_tls: bool = True,
) -> tuple[str, ...]:
    urls: list[str] = []
    seen: set[str] = set()
    for page_number, index_url in enumerate(
        index_page_urls(
            source_url,
            max_pages=max_pages,
            page_param=page_param,
            page_url_template=page_url_template,
        ),
        start=1,
    ):
        index_html = fetch_text(index_url, verify_tls=verify_tls)
        page_urls = extract_team_urls(index_html, source_url, slug_contains=slug_contains)
        new_urls = [url for url in page_urls if url not in seen]
        if page_number > 1 and not new_urls:
            break
        for url in new_urls:
            seen.add(url)
            urls.append(url)
    return tuple(urls)


def index_page_urls(
    source_url: str,
    *,
    max_pages: int = 1,
    page_param: str = "page",
    page_url_template: str | None = None,
) -> tuple[str, ...]:
    if max_pages < 1:
        raise ValueError("--max-pages must be at least 1.")
    urls = [source_url]
    for page in range(2, max_pages + 1):
        if page_url_template:
            urls.append(page_url_template.format(page=page, source=source_url))
            continue
        parsed = urllib.parse.urlparse(source_url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        query[page_param] = str(page)
        urls.append(urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query))))
    return tuple(urls)


def fetch_text(url: str, *, verify_tls: bool = True) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "pokebrain-metavgc-importer/1.0"})
    context = None if verify_tls else ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_team_urls(index_html: str, source_url: str, *, slug_contains: str | None = None) -> tuple[str, ...]:
    parser = LinkExtractor()
    parser.feed(index_html)
    candidate_urls = list(parser.hrefs)
    candidate_urls.extend(extract_embedded_team_url_candidates(index_html))
    urls = []
    seen = set()
    parsed_source = urllib.parse.urlparse(source_url)
    source_path = parsed_source.path.rstrip("/")
    source_slug = slug_contains or source_path.rsplit("/", 1)[-1]
    for href in candidate_urls:
        absolute = urllib.parse.urljoin(source_url, html.unescape(href))
        parsed = urllib.parse.urlparse(absolute)
        path = parsed.path.rstrip("/")
        if not path.startswith("/pt/times/"):
            continue
        if path == source_path:
            continue
        if source_slug and source_slug not in path:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        urls.append(absolute)
    return tuple(urls)


def extract_embedded_team_url_candidates(index_html: str) -> tuple[str, ...]:
    normalized = html.unescape(index_html).replace("\\/", "/")
    pattern = re.compile(r"(?:https://metavgc\.com)?/pt/times/[a-z0-9][a-z0-9/-]*")
    return tuple(match.group(0) for match in pattern.finditer(normalized))


def parse_team_page(page_html: str) -> tuple[str, tuple[PokemonExport, ...]]:
    parser = TextExtractor()
    parser.feed(page_html)
    lines = parser.lines
    title = next((line for line in parser.headings if " – " in line or " - " in line), parser.title or "metavgc-team")
    pokemon = []
    index = 0
    while index < len(lines):
        details = parse_details_at(lines, index)
        if details is None:
            index += 1
            continue
        nature, ability, next_index = details
        species, item = find_species_and_item(lines, index)
        stat_points, moves = parse_stats_and_moves(lines, next_index)
        pokemon.append(
            PokemonExport(
                species=species,
                item=item,
                nature=nature,
                ability=ability,
                stat_points=stat_points,
                moves=moves,
            )
        )
        index = next_index
    return title, tuple(pokemon[:6])


def parse_details_at(lines: list[str], index: int) -> tuple[str, str, int] | None:
    line = lines[index]
    if "·" not in line:
        return None
    parts = [part.strip() for part in line.split("·") if part.strip()]
    if len(parts) == 2:
        nature, ability = parts
        return nature, ability, index + 1
    if line == "·" and index + 3 < len(lines) and lines[index + 2] == "·":
        nature = lines[index + 1].strip()
        ability = lines[index + 3].strip()
        if nature and ability:
            return nature, ability, index + 4
    return None


def parse_details(line: str) -> tuple[str, str] | None:
    result = parse_details_at([line], 0)
    if result is None:
        return None
    return result[0], result[1]


def find_species_and_item(lines: list[str], detail_index: int) -> tuple[str, str]:
    if detail_index < 2:
        raise ValueError("Team member detail line has no preceding species/item context.")
    item = lines[detail_index - 1]
    species_index = detail_index - 2
    while species_index >= 0 and is_type_line(lines[species_index]):
        species_index -= 1
    if species_index < 0:
        raise ValueError("Could not find species before team member detail line.")
    species = lines[species_index]
    return species, item


def parse_stats_and_moves(lines: list[str], start_index: int) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...]]:
    stats: dict[str, int] = {}
    moves: list[str] = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        if parse_details_at(lines, index) is not None:
            break
        if line == "Movimentos":
            moves = [move for move in lines[index + 1 : index + 5] if move and parse_details(move) is None]
            break
        parsed_stat = parse_stat_line(line)
        if parsed_stat:
            stats[parsed_stat[0]] = parsed_stat[1]
            index += 1
            continue
        if line in STAT_ORDER and index + 1 < len(lines) and lines[index + 1].isdigit():
            stats[line] = int(lines[index + 1])
            index += 2
            continue
        index += 1
    ordered_stats = tuple((stat, stats[stat]) for stat in STAT_ORDER if stat in stats and stats[stat] > 0)
    return ordered_stats, tuple(moves[:4])


def parse_stat_line(line: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"(HP|Atk|Def|SpA|SpD|Spe)\s+(\d+)", line)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def is_type_line(line: str) -> bool:
    parts = line.split()
    return bool(parts) and all(part in POKEMON_TYPES for part in parts)


def write_manifest(path: Path, source_url: str, imported: list[ImportedTeam]) -> None:
    payload = {
        "source": "metavgc",
        "source_url": source_url,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "team_count": len(imported),
        "teams": [asdict(team) for team in imported],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:120] or "team"


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._tag_stack: list[str] = []
        self.headings: list[str] = []
        self.title: str | None = None

    @property
    def lines(self) -> list[str]:
        result = []
        seen_consecutive = set()
        for chunk in self._chunks:
            for line in re.split(r"[\r\n]+", chunk):
                cleaned = re.sub(r"\s+", " ", html.unescape(line)).strip()
                if not cleaned:
                    continue
                key = (len(result), cleaned)
                if key in seen_consecutive:
                    continue
                seen_consecutive.add(key)
                result.append(cleaned)
        return result

    def handle_starttag(self, tag: str, attrs) -> None:
        self._tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        current = self._tag_stack[-1] if self._tag_stack else ""
        if current == "title":
            self.title = cleaned
        if current in {"h1", "h2"}:
            self.headings.append(cleaned)
        self._chunks.append(cleaned)


if __name__ == "__main__":
    main()
