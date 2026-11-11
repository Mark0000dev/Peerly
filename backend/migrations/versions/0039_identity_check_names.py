"""Align historical CHECK names with unchanged registered constraint expressions."""

from collections.abc import Sequence

from alembic import op

revision: str = "0039_identity_check_names"
down_revision: str | Sequence[str] | None = "0038_operator_timeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMES: tuple[tuple[str, str, str], ...] = (
    (
        "external_identities",
        "ck_external_identities_ck_external_identities_google_issuer",
        "ck_external_identities_google_issuer",
    ),
    (
        "external_identities",
        "ck_external_identities_ck_external_identities_nonempty_subject",
        "ck_external_identities_nonempty_subject",
    ),
    (
        "sessions",
        "ck_sessions_ck_sessions_expiry_after_issuance",
        "ck_sessions_expiry_after_issuance",
    ),
    (
        "sessions",
        "ck_sessions_ck_sessions_secret_digest_length",
        "ck_sessions_secret_digest_length",
    ),
    ("sessions", "ck_sessions_ck_sessions_valid_revocation", "ck_sessions_valid_revocation"),
    (
        "institutional_bindings",
        "ck_institutional_bindings_ck_institutional_bindings_can_03d0",
        "ck_institutional_bindings_canonical_student_email",
    ),
    (
        "institutional_bindings",
        "ck_institutional_bindings_ck_institutional_bindings_val_5234",
        "ck_institutional_bindings_valid_revocation",
    ),
    (
        "login_transactions",
        "ck_login_transactions_ck_login_transactions_completion__63cd",
        "ck_login_transactions_completion_after_consumption",
    ),
    (
        "login_transactions",
        "ck_login_transactions_ck_login_transactions_consumed_er_b83b",
        "ck_login_transactions_consumed_erases_material",
    ),
    (
        "login_transactions",
        "ck_login_transactions_ck_login_transactions_digest_lengths",
        "ck_login_transactions_digest_lengths",
    ),
    (
        "login_transactions",
        "ck_login_transactions_ck_login_transactions_local_return_route",
        "ck_login_transactions_local_return_route",
    ),
    (
        "login_transactions",
        "ck_login_transactions_ck_login_transactions_valid_expiry",
        "ck_login_transactions_valid_expiry",
    ),
)


def upgrade() -> None:
    for table, old, new in RENAMES:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')


def downgrade() -> None:
    for table, old, new in reversed(RENAMES):
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{new}" TO "{old}"')
