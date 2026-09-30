"""Add user_lesson_progress.completed_at: when a teacher first completed a lesson.

Revision ID: 0006_progress_completed_at
Revises: 0005_user_logins

Additive and non-destructive: one new NULLABLE column on an existing table. No row is deleted
or rewritten except to fill the new column, and no other column is touched.

Idempotent on purpose, like revisions 0003-0005: revision 0001 builds fresh databases with
create_all() from the current models, so on a brand-new database the column already exists.

Backfill (never fabricated): a lesson completed BEFORE this revision has no timestamp of its
own. Where the teacher's earliest recorded video/podcast learning activity for that same lesson
exists (written in the same request that marked the lesson complete), that real timestamp is
used. Otherwise completed_at stays NULL and the admin UI shows "date not recorded".
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_progress_completed_at"
down_revision = "0005_user_logins"
branch_labels = None
depends_on = None

TABLE = "user_lesson_progress"
COLUMN = "completed_at"

# Plain SQL on purpose: identical on MySQL and SQLite, and no dependency on model classes.
BACKFILL_SQL = """
UPDATE user_lesson_progress
SET completed_at = (
    SELECT MIN(la.created_at)
    FROM learning_activities la
    WHERE la.user_id = user_lesson_progress.user_id
      AND la.lesson_id = user_lesson_progress.lesson_id
      AND la.activity_type IN ('video', 'podcast')
)
WHERE completed = :done AND completed_at IS NULL
"""


def _inspector():
    return sa.inspect(op.get_bind())


def _columns() -> set[str]:
    insp = _inspector()
    if TABLE not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    columns = _columns()
    if not columns:  # table missing: nothing to extend (0001 creates it on every real path)
        return
    if COLUMN not in columns:
        op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(), nullable=True))
    if "learning_activities" in _inspector().get_table_names():
        op.get_bind().execute(sa.text(BACKFILL_SQL), {"done": True})


def downgrade():
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
