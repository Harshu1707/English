"""Add Cloudinary metadata columns to lesson_media.
Revision ID: 0002_lesson_media_cloudinary_fields
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_lesson_media_cloudinary_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # Fresh databases are built by 0001 via create_all() from the *current* models, so these
    # columns already exist there; only databases created before this revision need them added.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("lesson_media")}
    if "provider" in existing:
        return
    op.add_column("lesson_media", sa.Column("provider", sa.String(30), nullable=False, server_default="cloudinary"))
    op.add_column("lesson_media", sa.Column("public_id", sa.String(255), nullable=True))
    op.add_column("lesson_media", sa.Column("resource_type", sa.String(20), nullable=True))
    op.add_column("lesson_media", sa.Column("format", sa.String(20), nullable=True))
    op.add_column("lesson_media", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("lesson_media", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("lesson_media", sa.Column("original_filename", sa.String(255), nullable=True))
    op.create_index("ix_lesson_media_public_id", "lesson_media", ["public_id"])
    op.alter_column("lesson_media", "provider", server_default=None)


def downgrade():
    op.drop_index("ix_lesson_media_public_id", table_name="lesson_media")
    op.drop_column("lesson_media", "original_filename")
    op.drop_column("lesson_media", "height")
    op.drop_column("lesson_media", "width")
    op.drop_column("lesson_media", "format")
    op.drop_column("lesson_media", "resource_type")
    op.drop_column("lesson_media", "public_id")
    op.drop_column("lesson_media", "provider")
