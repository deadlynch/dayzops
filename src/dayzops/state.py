from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _file(self, name: str) -> Path:
        return self.state_dir / name

    def load(self, name: str, default: Any = None) -> Any:
        path = self._file(name)

        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, name: str, data: Any) -> None:
        path = self._file(name)

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                data,
                fh,
                indent=2,
                sort_keys=True,
            )

    def exists(self, name: str) -> bool:
        return self._file(name).exists()