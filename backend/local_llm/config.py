# =====================================
# Local LLM Configuration
# =====================================

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"

CHAT_MODEL = "qwen2.5:3b"

EMBEDDING_MODEL = "nomic-embed-text"

REQUEST_TIMEOUT = 120

TEMPERATURE = 0.2

TOP_K = 5

VECTOR_DB_PATH = "vector_db"

CHUNK_SIZE = 500

CHUNK_OVERLAP = 50