from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pokebrain.replays.models import RawReplay, ReplaySummary
from pokebrain.replays.serialization import canonical_json


class RawReplayStorage:
    def __init__(self, root: Path | str = "data/replays/raw") -> None:
        self.root = Path(root)

    def path_for(self, summary: ReplaySummary) -> Path:
        uploaded_at = datetime.fromtimestamp(summary.upload_time, timezone.utc)
        return self.root / summary.format_id / f"{uploaded_at:%Y}" / f"{uploaded_at:%m}" / f"{summary.replay_id}.json"

    def save(self, summary: ReplaySummary, raw: RawReplay) -> Path:
        path = self.path_for(summary)
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw.raw_text:
            path.write_text(raw.raw_text, encoding="utf-8")
        else:
            with path.open("w", encoding="utf-8") as file:
                json.dump(raw.payload, file, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                file.write("\n")
        return path

    def load_payload(self, path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            raise ValueError(f"Raw replay payload is not an object: {path}")
        return payload

    def load_canonical_text(self, path: Path) -> str:
        return canonical_json(self.load_payload(path))
