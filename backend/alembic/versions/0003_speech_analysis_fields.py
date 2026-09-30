"""Add speaking-analysis fields to speaking_attempts / speech_scores / speech_feedback.

Revision ID: 0003_speech_analysis_fields
Revises: 0002_lesson_media_cloudinary_fields

Additive and non-destructive: every new column is nullable, no table or row is touched.
Idempotent on purpose: revision 0001 builds fresh databases with create_all() from the
current models, so on a brand-new database these columns already exist.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_speech_analysis_fields"
down_revision = "0002_lesson_media_cloudinary_fields"
branch_labels = None
depends_on = None

# table -> [(column name, column factory)]
NEW_COLUMNS = {
    "speaking_attempts": [
        ("public_id", lambda: sa.Column("public_id", sa.String(255), nullable=True)),
        ("duration_seconds", lambda: sa.Column("duration_seconds", sa.Float(), nullable=True)),
        ("overall_score", lambda: sa.Column("overall_score", sa.Float(), nullable=True)),
        ("error_message", lambda: sa.Column("error_message", sa.String(500), nullable=True)),
    ],
    "speech_scores": [
        ("words_per_minute", lambda: sa.Column("words_per_minute", sa.Float(), nullable=True)),
        ("pace", lambda: sa.Column("pace", sa.Float(), nullable=True)),
    ],
    "speech_feedback": [
        ("sentence_structure_score", lambda: sa.Column("sentence_structure_score", sa.Float(), nullable=True)),
    ],
}


def _existing(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    for table, columns in NEW_COLUMNS.items():
        present = _existing(table)
        for name, factory in columns:
            if name not in present:
                op.add_column(table, factory())


def downgrade():
    for table, columns in NEW_COLUMNS.items():
        present = _existing(table)
        for name, _ in reversed(columns):
            if name in present:
                op.drop_column(table, name)
