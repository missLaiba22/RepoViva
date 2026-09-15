"""CocoIndex context keys for the indexing flow."""

import asyncpg
import cocoindex as coco

# Resolved by postgres.mount_table_target() at flow time.
# The asyncpg pool is provided in build_app()'s lifespan
# (indexing/app.py).
PG_DB = coco.ContextKey[asyncpg.Pool]("repoviva_db")