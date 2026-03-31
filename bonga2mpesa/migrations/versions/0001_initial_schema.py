"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_number", sa.String(15), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_phone_number", "users", ["phone_number"])

    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("phone_number", sa.String(15), nullable=False),
        sa.Column("bonga_points", sa.Integer, nullable=False),
        sa.Column("expected_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("safaricom_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("payout_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "VALIDATED", "PROCESSING", "SUCCESS", "FAILED", name="transactionstatus"),
            nullable=False,
            default="PENDING",
        ),
        sa.Column("mpesa_receipt", sa.String(50), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False, unique=True),
        sa.Column("b2c_conversation_id", sa.String(100), nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transactions_phone_number", "transactions", ["phone_number"])
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index("ix_transactions_mpesa_receipt", "transactions", ["mpesa_receipt"])
    op.create_index("ix_transactions_correlation_id", "transactions", ["correlation_id"])
    op.create_index("ix_transactions_b2c_conversation_id", "transactions", ["b2c_conversation_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column(
            "entry_type",
            sa.Enum("CREDIT", "DEBIT", name="ledgerentrytype"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(10, 2), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "webhook_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_type",
            sa.Enum("C2B", "B2C_RESULT", "B2C_TIMEOUT", name="webhookeventtype"),
            nullable=False,
        ),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("processed", sa.Boolean, default=False),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("webhook_logs")
    op.drop_table("ledger_entries")
    op.drop_table("transactions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS transactionstatus")
    op.execute("DROP TYPE IF EXISTS ledgerentrytype")
    op.execute("DROP TYPE IF EXISTS webhookeventtype")
