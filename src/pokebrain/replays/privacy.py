from __future__ import annotations

import hashlib


def anonymize_player(player_name: str, dataset_salt: bytes) -> str:
    digest = hashlib.sha256(dataset_salt + player_name.strip().lower().encode("utf-8")).hexdigest()
    return f"player_{digest[:12]}"
