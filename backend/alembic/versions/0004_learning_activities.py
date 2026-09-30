"""Add learning_activities: per-user activity log behind streaks and the activity calendar.

Revision ID: 0004_learning_activities
Revises: 0003_speech_analysis_fields

Additive and non-destructive: one new table, no existing table or row is touched.
Idempotent on purpose, like revision 0003: revision 0001 builds fresh databases with
create_all() from the current models, so on a brand-new database the table already exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_learning_activities"
down_revision = "0003_speech_analysis_fields"
branch_labels = None
depends_on = None

TABLE = "learning_activities"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(20), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("speaking_attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_learning_activities_user_id", TABLE, ["user_id"])
    op.create_index("ix_learning_activities_activity_type", TABLE, ["activity_type"])
    op.create_index("ix_learning_activities_activity_date", TABLE, ["activity_date"])
    op.create_index("ix_learning_activities_user_date", TABLE, ["user_id", "activity_date"])


def downgrade():
    if TABLE in _tables():
        op.drop_table(TABLE)
