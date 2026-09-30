"""Initial relational learning schema.
Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from app.database.session import Base
import app.models.models
revision='0001_initial'; down_revision=None; branch_labels=None; depends_on=None
def upgrade(): Base.metadata.create_all(bind=op.get_bind())
def downgrade(): Base.metadata.drop_all(bind=op.get_bind())
