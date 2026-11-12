from pathlib import Path

from marketmind.infrastructure.collectors.fixture import FixtureCollector


def test_fixture_collector_loads_typed_records() -> None:
    records = FixtureCollector(Path("fixtures/source_records.json")).collect([])

    assert len(records) == 2
    assert records[0].external_id == "fixture-news-aapl-q4-2025"
    assert records[0].published_at is not None
