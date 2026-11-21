import importlib

from sqlalchemy import create_engine

from alembic import context
from marcus.core.db import Base, sync_db_url
from marcus.core.settings import get_settings

importlib.import_module("marcus.core.models")  # registers the tables on Base.metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=sync_db_url(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(sync_db_url(get_settings().database_url))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
