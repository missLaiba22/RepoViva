"""CocoIndex flow: walk source_dir → chunk → embed → pgvector."""

from typing import Final

import cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.connectorkits.target import ManagedBy
from cocoindex.ops.text import RecursiveSplitter, detect_code_language
from cocoindex.resources.file import PatternFilePathMatcher
from cocoindex.resources.id import generate_id

from repository_service.indexing.config import PG_DB
from repository_service.indexing.embedder import EMBEDDER, build_embed_input
from repository_service.indexing.schema import CodeChunk

INCLUDED_PATTERNS: Final = [
    "**/*.py", "**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx",
    "**/*.go", "**/*.rs", "**/*.java", "**/*.rb",
    "**/*.md", "**/README*",
]

EXCLUDED_PATTERNS: Final = [
    "**/.git/**", "**/node_modules/**", "**/.venv/**",
    "**/dist/**", "**/build/**", "**/vendor/**",
    "**/*.lock", "**/package-lock.json", "**/yarn.lock",
]

MAX_FILE_BYTES: Final = 500 * 1024

CHUNK_SIZE: Final = 1000
CHUNK_OVERLAP: Final = 200

# Reusable across files — RecursiveSplitter takes language per .split() call.
SPLITTER: Final = RecursiveSplitter()


@coco.fn(memo=True)
async def index_file(
    file,
    table,
    sourcedir: str,
    repository_id: str,
    commit_sha: str,
) -> None:
    """Split one file into chunks, embed each, declare one row per chunk."""
    source = await file.read_text()
    if len(source.encode("utf-8")) > MAX_FILE_BYTES:
        return

    # Repo-relative path — absolute paths would leak the host FS.
    filename = str(file.file_path.resolve().relative_to(sourcedir))
    language = detect_code_language(filename=filename) or "text"

    chunks = SPLITTER.split(
        source, CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, language=language
    )
    for chunk in chunks:
        embed_input = build_embed_input(filename, chunk.text)
        embedding = await EMBEDDER.embed(embed_input)

        table.declare_row(
            row=CodeChunk(
                id=await generate_id(embed_input),
                repository_id=repository_id,
                commit_sha=commit_sha,
                filename=filename,
                start_line=chunk.start.line,
                end_line=chunk.end.line,
                language=language,
                content=chunk.text,
                embedding=embedding,
            )
        )


@coco.fn
async def app_main(
    sourcedir: str,
    repository_id: str,
    commit_sha: str,
) -> None:
    """Wire source → per-file indexer → pgvector target."""
    # generate_id() below is a per-App sequential counter (starts at 1), not
    # globally unique — with one App per repository_id, two repositories'
    # first chunk both land on id=1. The primary key must include
    # repository_id or the second repository's row silently overwrites the
    # first's via ON CONFLICT DO UPDATE.
    schema = await postgres.TableSchema.from_class(
        CodeChunk,
        primary_key=["repository_id", "id"],
        column_overrides={"embedding": EMBEDDER},
    )
    # code_chunks is shared by every repository's App — its DDL is owned by
    # sql/schema.sql (applied once at service startup), not by CocoIndex.
    # A fresh App has no record of a table a *different* App already
    # created and would otherwise issue a plain CREATE TABLE that fails
    # with DuplicateTableError. USER tells CocoIndex to only reconcile rows.
    table = await postgres.mount_table_target(
        PG_DB, "code_chunks", schema, managed_by=ManagedBy.USER
    )
    table.declare_vector_index(column="embedding")

    files = localfs.walk_dir(
        sourcedir,
        recursive=True,
        path_matcher=PatternFilePathMatcher(
            included_patterns=INCLUDED_PATTERNS,
            excluded_patterns=EXCLUDED_PATTERNS,
        ),
    ).items()

    await coco.mount_each(
        index_file,
        files,
        table,
        sourcedir=sourcedir,
        repository_id=repository_id,
        commit_sha=commit_sha,
    )