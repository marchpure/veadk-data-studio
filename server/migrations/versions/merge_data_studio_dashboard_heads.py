"""merge data studio and dashboard migration heads

Revision ID: merge_ds_dash_20260816
Revises: backfill_legacy_dashboard_assets, add_blocked_source_resource_status
Create Date: 2026-08-16
"""

from __future__ import annotations

revision = "merge_ds_dash_20260816"
down_revision = ("backfill_legacy_dashboard_assets", "add_blocked_source_resource_status")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
