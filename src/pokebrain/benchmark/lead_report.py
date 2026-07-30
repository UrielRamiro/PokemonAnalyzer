from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pokebrain.benchmark.models import BattleBenchmarkResult
from pokebrain.benchmark.report import calculate_win_rate


@dataclass(frozen=True, slots=True)
class LeadBattleSummary:
    battle_id: str
    run_dir: str
    turns: int
    won: bool
    lost: bool
    own_lead_pair: str
    opponent_lead_pair: str
    own_full_lead_pair: str
    opponent_full_lead_pair: str
    own_bring_order: str
    opponent_bring_order: str
    own_turn_one_action: str
    opponent_turn_one_action: str
    own_turn_one_tags: tuple[str, ...]
    opponent_turn_one_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TurnOneSideContext:
    active_species: tuple[str, ...]
    move_targets: dict[tuple[int, str], str]


@dataclass(frozen=True, slots=True)
class LeadGroupRow:
    label: str
    battles: int
    wins: int
    losses: int
    ties: int
    adjusted_win_rate: float


@dataclass(frozen=True, slots=True)
class LeadCountRow:
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class LeadEarlyLossReport:
    run_id: str
    primary_agent: str
    battles: int
    analyzable_battles: int
    early_losses: int
    early_losses_with_full_pairs: int
    maximum_turns: int
    worst_own_lead_pairs: tuple[LeadGroupRow, ...]
    worst_opponent_lead_pairs: tuple[LeadGroupRow, ...]
    worst_lead_matchups: tuple[LeadGroupRow, ...]
    early_loss_own_lead_pairs: tuple[LeadCountRow, ...]
    early_loss_opponent_lead_pairs: tuple[LeadCountRow, ...]
    early_loss_lead_matchups: tuple[LeadCountRow, ...]
    early_loss_tags: tuple[tuple[str, int], ...]
    examples: tuple[LeadBattleSummary, ...]


def build_lead_early_loss_report(
    *,
    run_id: str,
    battles: tuple[BattleBenchmarkResult, ...],
    primary_agent: str,
    maximum_turns: int,
    top: int,
    minimum_battles: int,
) -> LeadEarlyLossReport:
    summaries = tuple(
        summary
        for battle in battles
        for summary in (_summarize_battle(battle, primary_agent, maximum_turns=maximum_turns),)
        if summary is not None
    )
    early_losses = tuple(summary for summary in summaries if summary.lost and summary.turns <= maximum_turns)
    early_losses_with_full_pairs = tuple(
        summary
        for summary in early_losses
        if _is_full_pair(summary.own_full_lead_pair) and _is_full_pair(summary.opponent_full_lead_pair)
    )
    return LeadEarlyLossReport(
        run_id=run_id,
        primary_agent=primary_agent,
        battles=len(battles),
        analyzable_battles=len(summaries),
        early_losses=len(early_losses),
        early_losses_with_full_pairs=len(early_losses_with_full_pairs),
        maximum_turns=maximum_turns,
        worst_own_lead_pairs=_worst_rows(
            summaries,
            key=lambda summary: summary.own_lead_pair,
            top=top,
            minimum_battles=minimum_battles,
        ),
        worst_opponent_lead_pairs=_worst_rows(
            summaries,
            key=lambda summary: summary.opponent_lead_pair,
            top=top,
            minimum_battles=minimum_battles,
        ),
        worst_lead_matchups=_worst_rows(
            summaries,
            key=lambda summary: f"{summary.own_lead_pair} vs {summary.opponent_lead_pair}",
            top=top,
            minimum_battles=minimum_battles,
        ),
        early_loss_own_lead_pairs=_count_rows(
            early_losses_with_full_pairs,
            key=lambda summary: summary.own_full_lead_pair,
            top=top,
        ),
        early_loss_opponent_lead_pairs=_count_rows(
            early_losses_with_full_pairs,
            key=lambda summary: summary.opponent_full_lead_pair,
            top=top,
        ),
        early_loss_lead_matchups=_count_rows(
            early_losses_with_full_pairs,
            key=lambda summary: f"{summary.own_full_lead_pair} vs {summary.opponent_full_lead_pair}",
            top=top,
        ),
        early_loss_tags=_tag_counts(early_losses),
        examples=tuple(sorted(early_losses, key=lambda item: (item.turns, item.battle_id))[:top]),
    )


class TextLeadEarlyLossRenderer:
    def render(self, report: LeadEarlyLossReport) -> str:
        return "\n".join(
            [
                "Lead / Early Loss Analyzer",
                "",
                f"Run ID: {report.run_id}",
                f"Agente analisado: {report.primary_agent}",
                f"Partidas: {report.battles}",
                f"Partidas analisaveis: {report.analyzable_battles}",
                f"Derrotas ate {report.maximum_turns} turnos: {report.early_losses}",
                f"Derrotas curtas com lead pair completo: {report.early_losses_with_full_pairs}",
                "",
                "Piores leads/lead pairs gerais - nossos:",
                *_row_lines(report.worst_own_lead_pairs),
                "",
                "Piores leads/lead pairs gerais - adversarios:",
                *_row_lines(report.worst_opponent_lead_pairs),
                "",
                "Piores confrontos gerais de leads/lead pairs:",
                *_row_lines(report.worst_lead_matchups),
                "",
                "Lead pairs nas derrotas curtas - nossos:",
                *_count_lines(report.early_loss_own_lead_pairs),
                "",
                "Lead pairs nas derrotas curtas - adversarios:",
                *_count_lines(report.early_loss_opponent_lead_pairs),
                "",
                "Confrontos de lead pair nas derrotas curtas:",
                *_count_lines(report.early_loss_lead_matchups),
                "",
                "Tags nas derrotas curtas:",
                *_tag_lines(report.early_loss_tags),
                "",
                "Exemplos de derrotas curtas:",
                *_example_lines(report.examples),
            ]
        )


def _summarize_battle(
    battle: BattleBenchmarkResult,
    primary_agent: str,
    maximum_turns: int,
) -> LeadBattleSummary | None:
    side = _side_for_agent(battle, primary_agent)
    opponent_side = _opponent_side(side)
    if side is None or opponent_side is None:
        return None
    lead_pairs = {
        "p1": battle.lead_a_pair_id or battle.lead_a_id,
        "p2": battle.lead_b_pair_id or battle.lead_b_id,
    }
    own_lead_pair = lead_pairs.get(side)
    opponent_lead_pair = lead_pairs.get(opponent_side)
    own_full_lead_pair = own_lead_pair
    opponent_full_lead_pair = opponent_lead_pair
    bring_orders: dict[str, str] = {}
    won = _primary_won(battle, primary_agent)
    lost = battle.winner is not None and not won
    is_early_loss = lost and battle.turns <= maximum_turns
    if is_early_loss and battle.run_dir:
        run_dir = Path(battle.run_dir)
        if run_dir.exists():
            parsed_preview = _load_preview_selections(run_dir)
            own_full_lead_pair = parsed_preview.get(side, {}).get("lead_pair") or own_lead_pair
            opponent_full_lead_pair = parsed_preview.get(opponent_side, {}).get("lead_pair") or opponent_lead_pair
            bring_orders = {
                player_id: str(selection.get("bring_order") or "")
                for player_id, selection in parsed_preview.items()
            }
    if not own_lead_pair or not opponent_lead_pair:
        return None
    own_full_lead_pair = own_full_lead_pair or own_lead_pair
    opponent_full_lead_pair = opponent_full_lead_pair or opponent_lead_pair
    decisions: dict[str, str] = {}
    if is_early_loss and battle.run_dir:
        run_dir = Path(battle.run_dir)
        if run_dir.exists():
            contexts = _load_turn_one_contexts(run_dir)
            decisions = _load_turn_one_decisions(run_dir, contexts)
    own_action = decisions.get(side)
    opponent_action = decisions.get(opponent_side)
    return LeadBattleSummary(
        battle_id=battle.battle_id,
        run_dir=battle.run_dir,
        turns=battle.turns,
        won=won,
        lost=lost,
        own_lead_pair=own_lead_pair,
        opponent_lead_pair=opponent_lead_pair,
        own_full_lead_pair=own_full_lead_pair,
        opponent_full_lead_pair=opponent_full_lead_pair,
        own_bring_order=bring_orders.get(side, ""),
        opponent_bring_order=bring_orders.get(opponent_side, ""),
        own_turn_one_action=own_action or "n/a",
        opponent_turn_one_action=opponent_action or "n/a",
        own_turn_one_tags=_action_tags(own_action or ""),
        opponent_turn_one_tags=_action_tags(opponent_action or ""),
    )


def _load_preview_selections(run_dir: Path) -> dict[str, dict[str, str]]:
    species_by_side = _load_preview_species(run_dir)
    orders_by_side = _load_preview_orders(run_dir)
    selections: dict[str, dict[str, str]] = {}
    for side, order in orders_by_side.items():
        species = species_by_side.get(side, ())
        lead_pair = _lead_pair_from_order(species, order)
        bring_order = _bring_order_from_order(species, order)
        if lead_pair:
            selections[side] = {
                "lead_pair": lead_pair,
                "bring_order": bring_order or order,
            }
    return selections


def _load_preview_species(run_dir: Path) -> dict[str, tuple[str, ...]]:
    path = run_dir / "states.jsonl"
    if not path.exists():
        return {}
    species_by_side: dict[str, tuple[str, ...]] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("turn") != 0:
                if species_by_side:
                    break
                continue
            request = entry.get("request") or {}
            if request.get("requestType") != "team-preview":
                continue
            player_id = entry.get("player_id")
            if player_id not in {"p1", "p2"} or player_id in species_by_side:
                continue
            species_by_side[player_id] = tuple(
                str(pokemon.get("speciesId") or "unknown")
                for pokemon in request.get("team", ())
            )
            if len(species_by_side) == 2:
                break
    return species_by_side


def _load_preview_orders(run_dir: Path) -> dict[str, str]:
    path = run_dir / "decisions.jsonl"
    if not path.exists():
        return {}
    orders: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("turn") != 0 or "selected_action" not in entry:
                continue
            action = entry.get("selected_action") or {}
            if action.get("type") != "team":
                continue
            player_id = entry.get("player_id")
            order = action.get("order")
            if player_id in {"p1", "p2"} and order:
                orders[player_id] = str(order)
            if len(orders) == 2:
                break
    return orders


def _load_turn_one_contexts(run_dir: Path) -> dict[str, TurnOneSideContext]:
    path = run_dir / "states.jsonl"
    if not path.exists():
        return {}
    contexts: dict[str, TurnOneSideContext] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("turn") != 1:
                continue
            request = entry.get("request") or {}
            if request.get("requestType") != "move":
                continue
            player_id = entry.get("player_id")
            if player_id not in {"p1", "p2"} or player_id in contexts:
                continue
            active_species = tuple(
                str(pokemon.get("speciesId") or "unknown")
                for pokemon in request.get("team", ())
                if pokemon.get("active")
            )
            move_targets: dict[tuple[int, str], str] = {}
            for active_index, active in enumerate(request.get("active", ())):
                active_slot = active_index + 1
                for move in active.get("moves", ()):
                    move_id = str(move.get("id") or "")
                    if move_id:
                        move_targets[(active_slot, move_id)] = str(move.get("target") or "")
            contexts[player_id] = TurnOneSideContext(
                active_species=active_species,
                move_targets=move_targets,
            )
            if len(contexts) == 2:
                break
    return contexts


def _load_turn_one_decisions(
    run_dir: Path,
    contexts: dict[str, TurnOneSideContext],
) -> dict[str, str]:
    path = run_dir / "decisions.jsonl"
    if not path.exists():
        return {}
    decisions: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("turn") != 1 or "selected_action" not in entry:
                continue
            player_id = entry.get("player_id")
            if player_id not in {"p1", "p2"} or player_id in decisions:
                continue
            decisions[player_id] = _action_label(
                entry.get("selected_action") or {},
                player_id=player_id,
                contexts=contexts,
            )
            if len(decisions) == 2:
                break
    return decisions


def _action_label(
    action: dict[str, Any],
    *,
    player_id: str | None = None,
    contexts: dict[str, TurnOneSideContext] | None = None,
) -> str:
    if action.get("type") == "compound":
        return " + ".join(
            _action_label(choice, player_id=player_id, contexts=contexts)
            for choice in action.get("choices", ())
        )
    actor = _actor_label(action, player_id=player_id, contexts=contexts)
    if action.get("type") == "move":
        move = str(action.get("moveId") or f"move{action.get('slot')}")
        target = _target_label(action, player_id=player_id, contexts=contexts)
        if action.get("terastallize"):
            move = f"{move}+tera"
        if target:
            return f"{actor}: {move} -> {target}" if actor else f"{move} -> {target}"
        return f"{actor}: {move}" if actor else move
    if action.get("type") == "switch":
        target = action.get("switchSpeciesId") or action.get("slot")
        return f"{actor}: switch -> {target}" if actor else f"switch:{target}"
    if action.get("type") == "team":
        return f"team:{action.get('order') or action.get('slot')}"
    if action.get("type") == "pass":
        return f"{actor}: pass" if actor else "pass"
    return str(action.get("type") or "unknown")


def _actor_label(
    action: dict[str, Any],
    *,
    player_id: str | None,
    contexts: dict[str, TurnOneSideContext] | None,
) -> str:
    if not player_id or not contexts:
        return ""
    active_slot = int(action.get("activeSlot") or 0)
    if active_slot <= 0:
        return ""
    own_context = contexts.get(player_id)
    if own_context is None:
        return ""
    return _species_at_slot(own_context.active_species, active_slot)


def _target_label(
    action: dict[str, Any],
    *,
    player_id: str | None,
    contexts: dict[str, TurnOneSideContext] | None,
) -> str:
    if action.get("type") != "move" or not player_id or not contexts:
        return ""
    active_slot = int(action.get("activeSlot") or 0)
    move_id = str(action.get("moveId") or "")
    own_context = contexts.get(player_id)
    opponent_context = contexts.get(_opponent_side(player_id) or "")
    target_type = ""
    if own_context is not None:
        target_type = own_context.move_targets.get((active_slot, move_id), "")

    if action.get("target") is not None:
        target = int(action.get("target") or 0)
        if target > 0 and opponent_context is not None:
            return _species_at_slot(opponent_context.active_species, target)
        if target < 0 and own_context is not None:
            return _species_at_slot(own_context.active_species, abs(target))

    if target_type in {"self", "adjacentAllyOrSelf"}:
        return "self"
    if target_type == "allAdjacentFoes":
        return "all foes"
    if target_type == "allAdjacent":
        return "all adjacent"
    if target_type == "all":
        return "field"
    if target_type == "allies":
        return "all allies"
    if target_type == "allySide":
        return "ally side"
    if target_type == "foeSide":
        return "foe side"
    return ""


def _species_at_slot(species: tuple[str, ...], slot: int) -> str:
    index = slot - 1
    if 0 <= index < len(species):
        return species[index]
    return f"slot{slot}"


def _action_tags(action: str) -> tuple[str, ...]:
    lowered = action.lower()
    tags = []
    if any(move in lowered for move in ("fakeout",)):
        tags.append("fake_out")
    if any(move in lowered for move in ("protect", "detect")):
        tags.append("protect")
    if "tailwind" in lowered:
        tags.append("tailwind")
    if "trickroom" in lowered:
        tags.append("trick_room")
    if any(move in lowered for move in ("ragepowder", "followme")):
        tags.append("redirection")
    if "switch:" in lowered:
        tags.append("switch")
    return tuple(tags)


def _worst_rows(
    summaries: tuple[LeadBattleSummary, ...],
    *,
    key: Callable[[LeadBattleSummary], str],
    top: int,
    minimum_battles: int,
) -> tuple[LeadGroupRow, ...]:
    labels = sorted({key(summary) for summary in summaries if key(summary)})
    rows: list[LeadGroupRow] = []
    for label in labels:
        grouped = tuple(summary for summary in summaries if key(summary) == label)
        if len(grouped) < minimum_battles:
            continue
        wins = sum(1 for summary in grouped if summary.won)
        losses = sum(1 for summary in grouped if summary.lost)
        ties = len(grouped) - wins - losses
        rows.append(
            LeadGroupRow(
                label=label,
                battles=len(grouped),
                wins=wins,
                losses=losses,
                ties=ties,
                adjusted_win_rate=calculate_win_rate(wins, losses, ties),
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.adjusted_win_rate, -row.battles, row.label))[:top])


def _tag_counts(summaries: tuple[LeadBattleSummary, ...]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for summary in summaries:
        for tag in summary.own_turn_one_tags:
            counts[f"own:{tag}"] = counts.get(f"own:{tag}", 0) + 1
        for tag in summary.opponent_turn_one_tags:
            counts[f"opponent:{tag}"] = counts.get(f"opponent:{tag}", 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _row_lines(rows: tuple[LeadGroupRow, ...]) -> list[str]:
    if not rows:
        return ["- sem dados suficientes"]
    return [
        (
            f"- {row.label}: {row.battles} partidas, {_percent(row.adjusted_win_rate)} ajustado "
            f"({row.wins}V/{row.losses}D/{row.ties}E)"
        )
        for row in rows
    ]


def _tag_lines(rows: tuple[tuple[str, int], ...]) -> list[str]:
    if not rows:
        return ["- nenhuma tag encontrada"]
    return [f"- {tag}: {count}" for tag, count in rows]


def _count_rows(
    summaries: tuple[LeadBattleSummary, ...],
    *,
    key: Callable[[LeadBattleSummary], str],
    top: int,
) -> tuple[LeadCountRow, ...]:
    counts: dict[str, int] = {}
    for summary in summaries:
        label = key(summary)
        if label:
            counts[label] = counts.get(label, 0) + 1
    return tuple(
        LeadCountRow(label=label, count=count)
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top]
    )


def _count_lines(rows: tuple[LeadCountRow, ...]) -> list[str]:
    if not rows:
        return ["- nenhum dado encontrado"]
    return [f"- {row.label}: {row.count}" for row in rows]


def _example_lines(examples: tuple[LeadBattleSummary, ...]) -> list[str]:
    if not examples:
        return ["- nenhuma derrota curta analisavel"]
    return [
        (
            f"- {summary.battle_id}: {summary.turns} turnos, "
            f"{summary.own_full_lead_pair} vs {summary.opponent_full_lead_pair}, "
            f"bring nosso [{summary.own_bring_order or 'n/a'}], "
            f"bring deles [{summary.opponent_bring_order or 'n/a'}], "
            f"T1 nosso [{summary.own_turn_one_action}], "
            f"T1 deles [{summary.opponent_turn_one_action}], "
            f"replay {summary.run_dir}"
        )
        for summary in examples
    ]


def _primary_won(battle: BattleBenchmarkResult, primary_agent: str) -> bool:
    if battle.agent_a == primary_agent:
        return battle.winner == "PokeBrain"
    if battle.agent_b == primary_agent:
        return battle.winner == "Opponent"
    return battle.winner == primary_agent


def _side_for_agent(battle: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if battle.agent_a == primary_agent:
        return "p1"
    if battle.agent_b == primary_agent:
        return "p2"
    return None


def _opponent_side(side: str | None) -> str | None:
    if side == "p1":
        return "p2"
    if side == "p2":
        return "p1"
    return None


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _is_full_pair(value: str) -> bool:
    return "+" in value


def _lead_pair_from_order(species: tuple[str, ...], order: str) -> str | None:
    selected = _species_from_order(species, order[:2])
    if not selected:
        return None
    return "+".join(selected)


def _bring_order_from_order(species: tuple[str, ...], order: str) -> str | None:
    selected = _species_from_order(species, order)
    if not selected:
        return None
    return " / ".join(selected)


def _species_from_order(species: tuple[str, ...], order: str) -> tuple[str, ...]:
    selected: list[str] = []
    for character in order:
        if not character.isdigit():
            continue
        index = int(character) - 1
        if 0 <= index < len(species):
            selected.append(species[index])
    return tuple(selected)
