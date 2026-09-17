"""Indexing: chunk, embed, and write a repository's source into pgvector."""

from repository_service.indexing.runner import run_indexing

__all__ = ["run_indexing"]
