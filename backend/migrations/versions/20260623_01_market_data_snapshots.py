"""add market data snapshot registry"""

from alembic import op
import sqlalchemy as sa

revision = "20260623_01"
down_revision = "20260621_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "market_data_snapshots" not in tables:
        op.create_table(
            "market_data_snapshots",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("market", sa.String(length=20), nullable=False),
            sa.Column("symbol", sa.String(length=40), nullable=False),
            sa.Column("vendor_symbol", sa.String(length=80), nullable=True),
            sa.Column("frequency", sa.String(length=20), nullable=False, server_default="1day"),
            sa.Column("start_date", sa.String(length=10), nullable=False),
            sa.Column("end_date", sa.String(length=10), nullable=False),
            sa.Column("rows", sa.Integer(), nullable=False),
            sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_market_data_snapshots_provider", "market_data_snapshots", ["provider"])
        op.create_index("ix_market_data_snapshots_market", "market_data_snapshots", ["market"])
        op.create_index("ix_market_data_snapshots_symbol", "market_data_snapshots", ["symbol"])
        op.create_index("ix_market_data_snapshots_start_date", "market_data_snapshots", ["start_date"])
        op.create_index("ix_market_data_snapshots_end_date", "market_data_snapshots", ["end_date"])
        op.create_index("ix_market_data_snapshots_snapshot_hash", "market_data_snapshots", ["snapshot_hash"])
    backtest_columns = {column["name"] for column in inspector.get_columns("backtests")} if "backtests" in tables else set()
    if "data_snapshot_id" not in backtest_columns:
        op.add_column("backtests", sa.Column("data_snapshot_id", sa.String(length=64), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("backtests")} if "backtests" in tables else set()
    if "ix_backtests_data_snapshot_id" not in indexes:
        op.create_index("ix_backtests_data_snapshot_id", "backtests", ["data_snapshot_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "backtests" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("backtests")}
        if "ix_backtests_data_snapshot_id" in indexes:
            op.drop_index("ix_backtests_data_snapshot_id", table_name="backtests")
        columns = {column["name"] for column in inspector.get_columns("backtests")}
        if "data_snapshot_id" in columns:
            op.drop_column("backtests", "data_snapshot_id")
    if "market_data_snapshots" in tables:
        op.drop_table("market_data_snapshots")
