from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text
from app.core.config import settings
from app.database.session import Base
import app.models.models
config=context.config
# The URL comes from the same settings/.env the app uses (alembic.ini leaves it blank). '%' is escaped for configparser.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata=Base.metadata
def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
def _prepare_version_table(connection):
    # MySQL: alembic_version.version_num defaults to VARCHAR(32) but the existing revision id
    # '0002_lesson_media_cloudinary_fields' is 35 chars, so recording it fails ("Data too long").
    if connection.dialect.name != "mysql": return
    if "alembic_version" in inspect(connection).get_table_names():
        connection.execute(text("ALTER TABLE alembic_version MODIFY version_num VARCHAR(255) NOT NULL"))
    else:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"))
    connection.commit()
def run_migrations_online():
    connectable=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _prepare_version_table(connection)
        context.configure(connection=connection,target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
