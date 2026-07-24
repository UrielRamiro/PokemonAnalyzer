from __future__ import annotations

import random

from pokebrain.benchmark.models import Seed


def create_battle_seed(base_seed: int, battle_number: int) -> Seed:
    random_source = random.Random((base_seed * 1_000_003) + battle_number)
    return tuple(random_source.randint(1, 2_147_483_647) for _ in range(4))  # type: ignore[return-value]


def seed_to_text(seed: Seed) -> str:
    return ",".join(str(value) for value in seed)
