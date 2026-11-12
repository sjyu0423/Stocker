from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    url = f"sqlite:///{database}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)

    command.upgrade(config, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {
        "companies",
        "tracked_symbols",
        "data_sources",
        "source_records",
        "raw_source_records",
        "financial_events",
        "event_sources",
        "collection_runs",
        "model_inference_usage",
        "collection_checkpoints",
    } <= tables
    command.check(config)

    command.downgrade(config, "base")
    remaining = set(inspect(create_engine(url)).get_table_names())
    assert remaining == {"alembic_version"}
