from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from scripts.import_metavgc_teams import (
    api_team_to_candidate,
    extract_featured_tournament_id,
    extract_team_urls,
    index_page_urls,
    parse_team_page,
)


class MetaVGCImporterTest(unittest.TestCase):
    def test_extracts_team_urls_from_index(self) -> None:
        html = """
        <a href="/pt/times/naic-2026">Times</a>
        <a href="/pt/times/team-one-naic-2026">One</a>
        <a href="https://metavgc.com/pt/times/team-two-naic-2026">Two</a>
        <a href="/pt/times/buscador">Search</a>
        <a href="/pt/guias/x">Guide</a>
        """

        urls = extract_team_urls(html, "https://metavgc.com/pt/times/naic-2026")

        self.assertEqual(
            urls,
            (
                "https://metavgc.com/pt/times/team-one-naic-2026",
                "https://metavgc.com/pt/times/team-two-naic-2026",
            ),
        )

    def test_extracts_embedded_team_urls_from_metadata(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@id":"https://metavgc.com/pt/times/team-eleven-naic-2026-place-11th"}
        </script>
        <script>self.__next_f.push(["/pt/times/team-twelve-naic-2026-place-12th"])</script>
        """

        urls = extract_team_urls(html, "https://metavgc.com/pt/times/naic-2026")

        self.assertEqual(
            urls,
            (
                "https://metavgc.com/pt/times/team-eleven-naic-2026-place-11th",
                "https://metavgc.com/pt/times/team-twelve-naic-2026-place-12th",
            ),
        )

    def test_builds_paginated_index_urls_with_query_param(self) -> None:
        urls = index_page_urls("https://metavgc.com/pt/times/naic-2026?lang=pt", max_pages=3)

        self.assertEqual(
            urls,
            (
                "https://metavgc.com/pt/times/naic-2026?lang=pt",
                "https://metavgc.com/pt/times/naic-2026?lang=pt&page=2",
                "https://metavgc.com/pt/times/naic-2026?lang=pt&page=3",
            ),
        )

    def test_builds_paginated_index_urls_with_template(self) -> None:
        urls = index_page_urls(
            "https://metavgc.com/pt/times/naic-2026",
            max_pages=3,
            page_url_template="https://metavgc.com/pt/times/naic-2026/{page}",
        )

        self.assertEqual(
            urls,
            (
                "https://metavgc.com/pt/times/naic-2026",
                "https://metavgc.com/pt/times/naic-2026/2",
                "https://metavgc.com/pt/times/naic-2026/3",
            ),
        )

    def test_extracts_featured_tournament_id_from_next_payload(self) -> None:
        html = 'self.__next_f.push(["teamSearchTournamentId\\":\\"436\\""])'

        self.assertEqual(extract_featured_tournament_id(html), "436")

    def test_converts_api_team_to_showdown_export(self) -> None:
        candidate = api_team_to_candidate(
            {
                "player": "Theotime Massaut",
                "tournament": "NAIC 2026, New Orleans",
                "placement": "26th",
                "publicId": "delphox-mega-by-theotime-massaut-place-26th",
                "pokemon": [
                    {
                        "name": "Delphox Mega",
                        "item": "Delphoxite",
                        "ability": "Levitate",
                        "nature": "Timid",
                        "evs": {"hp": 11, "atk": 0, "def": 4, "spa": 19, "spd": 0, "spe": 32},
                        "moves": ["Heat Wave", "Psyshock", "Nasty Plot", "Protect"],
                    }
                ],
            }
        )

        self.assertEqual(candidate.title, "Theotime Massaut - NAIC 2026, New Orleans - #26th")
        self.assertEqual(candidate.source_url, "https://metavgc.com/pt/times/delphox-mega-by-theotime-massaut-place-26th")
        self.assertIn("EVs: 11 HP / 4 Def / 19 SpA / 32 Spe", candidate.pokemon[0].to_showdown())
        self.assertIn("- Protect", candidate.pokemon[0].to_showdown())

    def test_parses_visible_team_page_into_showdown_export(self) -> None:
        title, pokemon = parse_team_page(TEAM_HTML)

        self.assertEqual(title, "Francesco Pio Pero – NAIC 2026, New Orleans – #1st")
        self.assertEqual(len(pokemon), 6)
        self.assertIn("Charizard Mega Y @ Charizardite Y", pokemon[0].to_showdown())
        self.assertIn("EVs: 20 HP / 32 Def / 1 SpA / 13 Spe", pokemon[0].to_showdown())
        self.assertIn("- Weather Ball", pokemon[0].to_showdown())
        self.assertIn("Aerodactyl Mega @ Aerodactylite", pokemon[-1].to_showdown())


TEAM_HTML = """
<html>
<head><title>Mega Charizard Y #1st</title></head>
<body>
<h1>Francesco Pio Pero – NAIC 2026, New Orleans – #1st</h1>
<a>Charizard Mega Y</a><p>Fire Flying</p><span>Charizardite Y</span><p>·Timid·Drought</p>
<p>HP 20</p><p>Def 32</p><p>SpA 1</p><p>Spe 13</p><h3>Movimentos</h3>
<p>Heat Wave</p><p>Solar Beam</p><p>Weather Ball</p><p>Protect</p>
<a>Sylveon</a><p>Fairy</p><span>Fairy Feather</span><p>·Modest·Pixilate</p>
<p>HP 9</p><p>Def 22</p><p>SpA 30</p><p>Spe 5</p><h3>Movimentos</h3>
<p>Detect</p><p>Hyper Voice</p><p>Yawn</p><p>Quick Attack</p>
<a>Kingambit</a><p>Dark Steel</p><span>Chople Berry</span><p>·Adamant·Defiant</p>
<p>HP 32</p><p>Atk 32</p><p>SpD 2</p><h3>Movimentos</h3>
<p>Sucker Punch</p><p>Kowtow Cleave</p><p>Low Kick</p><p>Iron Head</p>
<a>Basculegion-M</a><p>Water Ghost</p><span>Focus Sash</span><p>·Jolly·Adaptability</p>
<p>HP 2</p><p>Atk 32</p><p>Spe 32</p><h3>Movimentos</h3>
<p>Protect</p><p>Last Respects</p><p>Aqua Jet</p><p>Liquidation</p>
<a>Garchomp</a><p>Dragon Ground</p><span>Sitrus Berry</span><p>·Jolly·Rough Skin</p>
<p>HP 2</p><p>Atk 32</p><p>Spe 32</p><h3>Movimentos</h3>
<p>Rock Tomb</p><p>Earthquake</p><p>Dragon Claw</p><p>Protect</p>
<a>Aerodactyl Mega</a><p>Rock Flying</p><span>Aerodactylite</span><p>·Jolly·Tough Claws</p>
<p>HP 22</p><p>Atk 12</p><p>Spe 32</p><h3>Movimentos</h3>
<p>Tailwind</p><p>Dual Wingbeat</p><p>Rock Slide</p><p>Wide Guard</p>
</body>
</html>
"""


if __name__ == "__main__":
    unittest.main()
