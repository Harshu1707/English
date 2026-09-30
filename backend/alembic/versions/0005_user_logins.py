"""Add user_logins: one row per successful sign-in, behind the admin login-activity stats.

Revision ID: 0005_user_logins
Revises: 0004_learning_activities

Additive and non-destructive: one new table, no existing table or row is touched.
Idempotent on purpose, like revisions 0003/0004: revision 0001 builds fresh databases with
create_all() from the current models, so on a brand-new database the table already exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_user_logins"
down_revision = "0004_learning_activities"
branch_labels = None
depends_on = None

TABLE = "user_logins"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("login_at", sa.DateTime(), nullable=False),
        sa.Column("login_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_logins_user_id", TABLE, ["user_id"])
    op.create_index("ix_user_logins_login_at", TABLE, ["login_at"])
    op.create_index("ix_user_logins_login_date", TABLE, ["login_date"])
    op.create_index("ix_user_logins_user_id_login_at", TABLE, ["user_id", "login_at"])


def downgrade():
    if TABLE in _tables():
        op.drop_table(TABLE)
