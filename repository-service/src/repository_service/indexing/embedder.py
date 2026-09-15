"""
Voyage AI embedder and embed-input builder.

Uses Voyage 4-lite for 1024-dimensional embeddings.
"""

from typing import Final

from cocoindex.ops.litellm import LiteLLMEmbedder

# Shared CocoIndex embedding operation. Reads VOYAGE_API_KEY from the
# process env via litellm's provider lookup.
EMBEDDER: Final = LiteLLMEmbedder("voyage/voyage-4-lite")


def build_embed_input(filename: str, code: str) -> str:
    """Build the text sent to the embedding model."""
    return f"{filename}\n\n{code}"

