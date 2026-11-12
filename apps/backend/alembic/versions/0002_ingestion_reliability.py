"""Add immutable source revisions and collector recovery.

Revision ID: 0002_ingestion_reliability
Revises: 0001_product_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_ingestion_reliability"
down_revision: str | None = "0001_product_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("record_type", sa.String(64), nullable=False),
        sa.Column("original_published_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "external_id"),
    )
    op.create_index("ix_source_records_data_source_id", "source_records", ["data_source_id"])
    op.create_index("ix_source_records_first_seen", "source_records", ["first_seen_at"])

    op.add_column("raw_source_records", sa.Column("source_record_id", sa.Uuid()))
    op.add_column("raw_source_records", sa.Column("revision_number", sa.Integer()))
    op.execute(
        sa.text(
            """
            INSERT INTO source_records (
                id, data_source_id, external_id, record_type,
                original_published_at, first_seen_at, ingested_at
            )
            SELECT
                id, data_source_id, external_id, record_type,
                published_at, first_seen_at, ingested_at
            FROM raw_source_records
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE raw_source_records
            SET source_record_id = id, revision_number = 1
            """
        )
    )
    with op.batch_alter_table("raw_source_records") as batch:
        batch.alter_column("source_record_id", existing_type=sa.Uuid(), nullable=False)
        batch.alter_column("revision_number", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_raw_source_records_data_source_id", type_="unique")
        batch.create_foreign_key(
            "fk_raw_source_records_source_record_id_source_records",
            "source_records",
            ["source_record_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint(
            "uq_raw_source_records_source_record_id_revision_number",
            ["source_record_id", "revision_number"],
        )
        batch.create_unique_constraint(
            "uq_raw_source_records_source_record_id_content_hash",
            ["source_record_id", "content_hash"],
        )
        batch.create_index(
            "ix_raw_source_records_source_record_id", ["source_record_id"], unique=False
        )
        batch.create_index(
            "ix_raw_source_records_availability",
            ["source_record_id", "first_seen_at"],
            unique=False,
        )

    with op.batch_alter_table("collection_runs") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(512)))
        batch.add_column(sa.Column("checkpoint_start", sa.JSON()))
        batch.add_column(sa.Column("checkpoint_end", sa.JSON()))
        batch.add_column(
            sa.Column("dry_run", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("failure_kind", sa.String(32)))
        batch.create_unique_constraint("uq_collection_runs_idempotency_key", ["idempotency_key"])

    op.create_table(
        "collection_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("collector_name", sa.String(255), nullable=False),
        sa.Column("cursor", sa.JSON()),
        sa.Column("last_successful_run_id", sa.Uuid()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_successful_run_id"], ["collection_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "collector_name"),
    )
    op.create_index(
        "ix_collection_checkpoints_data_source_id",
        "collection_checkpoints",
        ["data_source_id"],
    )


def downgrade() -> None:
    op.drop_table("collection_checkpoints")
    with op.batch_alter_table("collection_runs") as batch:
        batch.drop_constraint("uq_collection_runs_idempotency_key", type_="unique")
        batch.drop_column("failure_kind")
        batch.drop_column("heartbeat_at")
        batch.drop_column("dry_run")
        batch.drop_column("checkpoint_end")
        batch.drop_column("checkpoint_start")
        batch.drop_column("idempotency_key")

    # M0A cannot represent multiple revisions. Retain revision 1 when downgrading.
    op.execute(
        sa.text(
            """
            DELETE FROM event_sources
            WHERE source_record_id IN (
                SELECT id FROM raw_source_records WHERE revision_number > 1
            )
            """
        )
    )
    op.execute(sa.text("DELETE FROM raw_source_records WHERE revision_number > 1"))
    with op.batch_alter_table("raw_source_records") as batch:
        batch.drop_index("ix_raw_source_records_availability")
        batch.drop_index("ix_raw_source_records_source_record_id")
        batch.drop_constraint("uq_raw_source_records_source_record_id_content_hash", type_="unique")
        batch.drop_constraint(
            "uq_raw_source_records_source_record_id_revision_number", type_="unique"
        )
        batch.drop_constraint(
            "fk_raw_source_records_source_record_id_source_records", type_="foreignkey"
        )
        batch.drop_column("revision_number")
        batch.drop_column("source_record_id")
        batch.create_unique_constraint(
            "uq_raw_source_records_data_source_id", ["data_source_id", "external_id"]
        )
    op.drop_table("source_records")
