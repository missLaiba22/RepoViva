"""CocoIndex flow: walk source_dir → chunk → embed → pgvector."""

from typing import Final

import cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.connectorkits.target import ManagedBy
from cocoindex.ops.text import RecursiveSplitter, detect_code_language
from cocoindex.resources.file import PatternFilePathMatcher
from cocoindex.resources.id import IdGenerator

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
    # .as_posix() (not str()) so the stored path always uses forward
    # slashes, regardless of the host OS indexing ran on — filename_prefix
    # matching in retrieval.search_chunks assumes this.
    filename = file.file_path.resolve().relative_to(sourcedir).as_posix()
    language = detect_code_language(filename=filename) or "text"

    chunks = SPLITTER.split(
        source, CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, language=language
    )
    # IdGenerator, not generate_id(): generate_id() returns the *same* id
    # for the same input, so a file containing two identical chunks (common
    # in docs — repeated code samples, admonitions) would declare the same
    # primary key twice and fail the whole file. next_id() is distinct per
    # call yet still stable across runs, so re-indexing an unchanged file
    # remains a no-op.
    id_gen = IdGenerator()
    for chunk in chunks:
        embed_input = build_embed_input(filename, chunk.text)
        embedding = await EMBEDDER.embed(embed_input)

        table.declare_row(
            row=CodeChunk(
                id=await id_gen.next_id(embed_input),
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
    # IdGenerator in index_file() is a per-App sequential counter (starts at 1), not
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
    # Deliberately no table.declare_vector_index(): retrieval is exact
    # search (decision 033). Declaring one here would make every App
    # DROP + CREATE an index on the shared table on its first run,
    # overriding sql/schema.sql. Apps that declared one in the past see it
    # as removed and issue a harmless DROP INDEX IF EXISTS.

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