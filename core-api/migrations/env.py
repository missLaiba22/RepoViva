from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from core_api.config import get_settings
from core_api.db import Base
from core_api.users.models import User  # noqa: F401
from core_api.repositories.models import Repository  # noqa: F401
from core_api.interviews.models import Interview  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use our SQLAlchemy models for Alembic autogenerate.
target_metadata = Base.metadata

# Override the URL from alembic.ini with our .env value.
config.set_main_option(
    "sqlalchemy.url",
    get_settings().database_url,
)


def include_object(object, name, type_, reflected, compare_to):
    """Limit autogenerate to tables Core API owns (decisions 021, 037).

    The database is shared across services. A table that exists in the
    database (`reflected=True`) but has no Core API model
    (`compare_to is None`) belongs to another service — e.g. Repository
    Service's `code_chunks` — and must be ignored, never dropped.

    Tradeoff: if Core API intentionally removes one of its own models,
    autogenerate will not emit the drop_table; write it by hand.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine.
    """
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    This creates an Engine and connects to the database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


# env.py is a script, not a library: this block runs the migration as
# soon as Alembic loads the file. Everything it uses must be defined above.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()