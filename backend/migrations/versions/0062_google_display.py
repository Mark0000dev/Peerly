"""Optional verified-provider display metadata, never account authority."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_google_display"
down_revision: str | Sequence[str] | None = "0061_native_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_identities", sa.Column("provider_display_name", sa.String(200), nullable=True)
    )
    op.add_column(
        "external_identities", sa.Column("provider_verified_email", sa.String(254), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("external_identities", "provider_verified_email")
    op.drop_column("external_identities", "provider_display_name")
