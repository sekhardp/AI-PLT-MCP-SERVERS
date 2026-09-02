import asyncio
import logging
from typing import List, Optional
from google import genai
from rag_server.settings import settings

logger = logging.getLogger("rag-server")

_genai_client: Optional[genai.Client] = None


def get_genai_client() -> Optional[genai.Client]:
    """Lazily initialize and return the Google GenAI Client for Vertex AI."""
    global _genai_client
    if _genai_client is None:
        try:
            _genai_client = genai.Client(
                vertexai=True,
                project=settings.gcp_project,
                location=settings.gcp_location,
            )
        except Exception as e:
            logger.warning("Failed to initialize Google GenAI Client: %s", e)
    return _genai_client


async def get_embedding(text_content: str) -> Optional[List[float]]:
    """Generate 768-dim query embedding using Vertex AI text-embedding-005."""
    client = get_genai_client()
    if not client:
        return None
    try:
        response = await asyncio.wait_for(
            client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=[text_content],
            ),
            timeout=settings.embedding_timeout_seconds,
        )
        if hasattr(response, "embeddings") and response.embeddings:
            return response.embeddings[0].values
        elif hasattr(response, "embedding") and response.embedding:
            return response.embedding.values
    except Exception as e:
        logger.warning("Query embedding generation failed: %s", e)
    return None
