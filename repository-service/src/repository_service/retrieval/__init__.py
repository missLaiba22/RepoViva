"""Retrieval over code_chunks: similarity search for /retrieve, id lookup for /chunks."""

from repository_service.retrieval.lookup import get_chunks_by_ids
from repository_service.retrieval.search import search_chunks

__all__ = ["get_chunks_by_ids", "search_chunks"]
