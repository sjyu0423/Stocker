import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter

from marketmind.domain.entities import RawRecordInput


class FixtureCollector:
    """Offline collector used for development and deterministic tests only."""

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def collect(self, _identifiers: Sequence[str]) -> Sequence[RawRecordInput]:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return TypeAdapter(list[RawRecordInput]).validate_python(payload)
