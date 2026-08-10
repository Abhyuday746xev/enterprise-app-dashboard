# ==========================================
# Enterprise Vector Store (ChromaDB)
# ==========================================

import chromadb

from chromadb.config import Settings

# ==========================================
# Create Persistent Client
# ==========================================

client = chromadb.PersistentClient(

    path="./chroma_db",

    settings=Settings(
        anonymized_telemetry=False
    )

)

# ==========================================
# Collection
# ==========================================

collection = client.get_or_create_collection(

    name="enterprise_dashboard"

)

# ==========================================
# Add One Document
# ==========================================

def add_document(

    document_id,
    document,
    embedding,
    metadata

):

    collection.add(

        ids=[document_id],

        documents=[document],

        embeddings=[embedding],

        metadatas=[metadata]

    )

# ==========================================
# Search Similar Documents
# ==========================================

def search(

    embedding,
    top_k=5

):

    return collection.query(

        query_embeddings=[embedding],

        n_results=top_k

    )

# ==========================================
# Delete Everything
# ==========================================

def clear_collection():

    global collection

    client.delete_collection(

        "enterprise_dashboard"

    )

    collection = client.get_or_create_collection(

        name="enterprise_dashboard"

    )

# ==========================================
# Count Documents
# ==========================================

def count():

    return collection.count()