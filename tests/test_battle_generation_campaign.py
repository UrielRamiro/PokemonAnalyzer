from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battles.config import load_generation_plan
from pokebrain.battles.ledger import BattleCampaignLedger
from pokebrain.battles.models import BattleJobStatus
from pokebrain.battles.planner import BattleCampaignPlanner
from pokebrain.battles.report import BattleCampaignReporter
from pokebrain.battles.runner import BattleGenerationCampaign
from pokebrain.benchmark.battle_runner import LocalShowdownBattleRunner
from pokebrain.battles.seed import derive_battle_seed
from pokebrain.battles.team_pool import build_team_pool_manifest
from pokebrain.battles.validation import BattleArtifactValidator
from pokebrain.battles.vgc_audit import VGCHomologationReporter
from pokebrain.benchmark.models import BattleBenchmarkResult
from pokebrain.benchmark.team_sampler import SampledTeam


class BattleGenerationCampaignTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT_DIR / ".tmp_tests" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.teams = self.root / "teams"
        self.teams.mkdir()
        (self.teams / "alpha.txt").write_text("Garchomp\nAbility: Rough Skin\n- Earthquake\n", encoding="utf-8")
        (self.teams / "beta.txt").write_text("Kingambit\nAbility: Supreme Overlord\n- Kowtow Cleave\n", encoding="utf-8")
        self.config = self.root / "campaign.yaml"
        self.config.write_text(
            "\n".join(
                (
                    "campaign_id: test-campaign",
                    "format_id: gen9ou",
                    "simulator_version: test-showdown",
                    "engine_version: test-engine",
                    "target_battles: 4",
                    "master_seed: 123",
                    "team_pool_id: test-pool",
                    f"team_pool_path: {self.teams}",
                    "max_turns: 50",
                    "timeout_seconds: 5",
                    f"artifact_root: {self.root / 'battles'}",
                    f"database_path: {self.root / 'campaign.db'}",
                    "agent_matchups:",
                    "  - matchup_id: search-v3-vs-search-v3",
                    "    agent_1_id: search-v3-policy",
                    "    agent_2_id: search-v3-policy",
                    "    weight: 1",
                    "  - matchup_id: heuristic-vs-search-v3",
                    "    agent_1_id: pokebrain-v1",
                    "    agent_2_id: search-v3-policy",
                    "    weight: 1",
                    "coverage_targets:",
                    "  - bucket: switch",
                    "    minimum_examples: 10",
                )
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_plan_loads_yaml_and_derives_stable_seed(self) -> None:
        plan = load_generation_plan(self.config)

        self.assertEqual(plan.campaign_id, "test-campaign")
        self.assertEqual(plan.target_battles, 4)
        self.assertEqual(len(plan.agent_matchups), 2)
        self.assertEqual(derive_battle_seed(123, 1, "x"), derive_battle_seed(123, 1, "x"))
        self.assertNotEqual(derive_battle_seed(123, 1, "x"), derive_battle_seed(123, 2, "x"))

    def test_planner_balances_teams_sides_and_agents(self) -> None:
        plan = load_generation_plan(self.config)
        team_pool = build_team_pool_manifest(plan.team_pool_id, plan.format_id, plan.team_pool_path)

        jobs = BattleCampaignPlanner().plan_jobs(plan, team_pool)

        self.assertEqual(len(jobs), 4)
        self.assertEqual(jobs[0].team_1_id, "alpha")
        self.assertEqual(jobs[1].team_2_id, "beta")
        self.assertTrue(any(job.agent_1_id != job.agent_2_id for job in jobs))

    def test_campaign_create_writes_resumable_ledger(self) -> None:
        plan = load_generation_plan(self.config)

        jobs = BattleGenerationCampaign(battle_runner=FakeBattleRunner(self.root)).create(plan, config_path=self.config)
        records = BattleCampaignLedger(plan.database_path).list_jobs(plan.campaign_id)

        self.assertEqual(len(jobs), 4)
        self.assertEqual(len(records), 4)
        self.assertTrue(all(record.status is BattleJobStatus.PENDING for record in records))
        self.assertTrue((plan.artifact_root / plan.campaign_id / "campaign_manifest.json").exists())

    def test_campaign_run_preserves_artifacts_validates_and_reports(self) -> None:
        plan = load_generation_plan(self.config)

        BattleGenerationCampaign(battle_runner=FakeBattleRunner(self.root)).run(plan, config_path=self.config, workers=1, resume=True)
        records = BattleCampaignLedger(plan.database_path).list_jobs(plan.campaign_id)
        artifact = plan.artifact_root / plan.campaign_id / "000001"
        validation = BattleArtifactValidator().validate(artifact)
        report = BattleCampaignReporter().report(plan)

        self.assertTrue(all(record.status is BattleJobStatus.COMPLETED for record in records))
        self.assertTrue((artifact / "battle.json").exists())
        self.assertTrue((artifact / "team-p1.txt").exists())
        self.assertTrue((artifact / "team-p2.txt").exists())
        self.assertTrue(validation.complete)
        self.assertEqual(validation.decision_count, 1)
        self.assertEqual(report.completed, 4)
        self.assertEqual(report.total_jobs, 4)

    def test_campaign_recovers_completed_result_after_timeout(self) -> None:
        plan = load_generation_plan(self.config)
        battle_id = "test-campaign-000001"
        run_dir = self.root / "runs" / "2026-07-22" / battle_id
        run_dir.mkdir(parents=True)
        _write_json(
            run_dir / "result.json",
            {
                "battle_id": battle_id,
                "seed": [1, 2, 3, 4],
                "agent_a": "pokebrain-v1",
                "agent_b": "search-v3-policy",
                "winner": "p1",
                "turns": 7,
                "termination_reason": "win",
                "run_dir": str(run_dir),
            },
        )
        _write_json(run_dir / "metadata.json", {"battle_id": battle_id})
        (run_dir / "protocol.log").write_text("|turn|1\n", encoding="utf-8")
        (run_dir / "states.jsonl").write_text("", encoding="utf-8")
        (run_dir / "decisions.jsonl").write_text(
            json.dumps(
                {
                    "turn": 1,
                    "player_id": "p1",
                    "legal_actions": [{"type": "move", "moveId": "earthquake"}],
                    "selected_action": {"type": "move", "moveId": "earthquake"},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        runner = LocalShowdownBattleRunner(self.root)
        result = runner._recover_existing_completed_result(
            battle_id=battle_id,
            pair_id="pair-1",
            format_id="gen9ou",
            agent_a_name="pokebrain-v1",
            agent_b_name="search-v3-policy",
            team_a=SampledTeam("alpha", self.teams / "alpha.txt"),
            team_b=SampledTeam("beta", self.teams / "beta.txt"),
            seed=(1, 2, 3, 4),
            duration=180.0,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.termination_reason, "win")
        self.assertEqual(result.turns, 7)
        self.assertEqual(result.run_dir, str(run_dir))

    def test_vgc_audit_reports_competitive_mechanics_and_gametype_alert(self) -> None:
        plan = load_generation_plan(self.config)
        BattleGenerationCampaign(battle_runner=FakeBattleRunner(self.root)).create(plan, config_path=self.config)
        artifact = plan.artifact_root / plan.campaign_id / "000001"
        artifact.mkdir(parents=True)
        _write_json(
            artifact / "battle.json",
            {
                "battle_id": "test-campaign-000001",
                "seed": [1, 2, 3, 4],
                "turns": 3,
                "termination_reason": "win",
                "winner": "p1",
            },
        )
        (artifact / "team-p1.txt").write_text(
            "\n\n".join(
                (
                    "Garchomp @ Sitrus Berry\nAbility: Rough Skin\nTera Type: Dragon\nEVs: 4 HP\nJolly Nature\n- Protect\n- Rock Tomb\n- Earthquake\n- Dragon Claw",
                    "Incineroar @ Safety Goggles\nAbility: Intimidate\nTera Type: Fire\nEVs: 4 HP\nCareful Nature\n- Fake Out\n- Parting Shot\n- Flare Blitz\n- Knock Off",
                )
            ),
            encoding="utf-8",
        )
        (artifact / "team-p2.txt").write_text(
            "Amoonguss @ Rocky Helmet\nAbility: Regenerator\nTera Type: Water\nEVs: 4 HP\nCalm Nature\n- Rage Powder\n- Spore\n- Protect\n- Pollen Puff\n",
            encoding="utf-8",
        )
        (artifact / "protocol.log").write_text(
            "\n".join(
                (
                    "|gametype|singles",
                    "|move|p1a: Incineroar|Fake Out|p2a: Amoonguss",
                    "|move|p2a: Amoonguss|Rage Powder|p2a: Amoonguss",
                    "|-weather|SunnyDay|[from] ability: Drought",
                    "|-terastallize|p1a: Garchomp|Dragon",
                )
            ),
            encoding="utf-8",
        )
        (artifact / "decisions.jsonl").write_text(
            json.dumps({"selected_action": {"type": "move", "moveId": "protect"}}) + "\n",
            encoding="utf-8",
        )
        BattleCampaignLedger(plan.database_path).mark_finished(
            campaign_id=plan.campaign_id,
            battle_index=1,
            status=BattleJobStatus.COMPLETED,
            artifact_path=artifact,
            failure_reason=None,
        )

        report = VGCHomologationReporter().report(plan)

        self.assertEqual(report.battles, 1)
        self.assertEqual(report.gametypes, (("singles", 1),))
        self.assertEqual(report.fake_out_used, 1)
        self.assertEqual(report.redirection_used, 1)
        self.assertEqual(report.tera_used, 1)
        self.assertTrue(any("not doubles" in alert for alert in report.alerts))


class FakeBattleRunner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run(
        self,
        *,
        battle_id: str,
        pair_id: str,
        format_id: str,
        agent_a_name: str,
        agent_b_name: str,
        team_a: SampledTeam,
        team_b: SampledTeam,
        seed,
        maximum_turns: int,
        timeout_seconds: int,
    ) -> BattleBenchmarkResult:
        run_dir = self.root / "runs" / battle_id
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            run_dir / "result.json",
            {
                "battle_id": battle_id,
                "seed": seed,
                "agent_a": agent_a_name,
                "agent_b": agent_b_name,
                "winner": "p1",
                "turns": 1,
                "termination_reason": "win",
                "run_dir": str(run_dir),
                "duration_seconds": 0.1,
            },
        )
        _write_json(run_dir / "metadata.json", {"battle_id": battle_id})
        (run_dir / "protocol.log").write_text("", encoding="utf-8")
        (run_dir / "states.jsonl").write_text("", encoding="utf-8")
        with (run_dir / "decisions.jsonl").open("w", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "turn": 1,
                        "player_id": "p1",
                        "legal_actions": [{"type": "move", "moveId": "earthquake"}],
                        "selected_action": {"type": "move", "moveId": "earthquake"},
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        return BattleBenchmarkResult(
            battle_id=battle_id,
            pair_id=pair_id,
            seed=seed,
            agent_a=agent_a_name,
            agent_b=agent_b_name,
            team_a_id=team_a.team_id,
            team_b_id=team_b.team_id,
            winner="p1",
            turns=1,
            illegal_action_count_a=0,
            illegal_action_count_b=0,
            decision_error_count_a=0,
            decision_error_count_b=0,
            duration_seconds=0.1,
            termination_reason="win",
            run_dir=str(run_dir),
        )


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file)


if __name__ == "__main__":
    unittest.main()
