# ==========================================
# Enterprise Embedding Generator
# ==========================================

import requests

from .config import (
    OLLAMA_EMBED_URL,
    EMBEDDING_MODEL
)


def create_embedding(text):

    text = text.strip()

    if not text:

        raise ValueError("Cannot create embedding from empty text.")

    response = requests.post(

        OLLAMA_EMBED_URL,

        json={
            "model": EMBEDDING_MODEL,
            "input": text
        }

    )

    response.raise_for_status()

    data = response.json()

    embeddings = data.get("embeddings", [])

    if not embeddings:

        raise RuntimeError("No embedding returned from Ollama.")

    return embeddings[0]