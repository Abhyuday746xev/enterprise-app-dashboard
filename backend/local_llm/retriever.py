from __future__ import annotations

# ==========================================
# Enterprise RAG Retriever
# ==========================================

import math
import os
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError

from local_llm.embeddings import create_embedding


# ==========================================
# Chroma Configuration
# ==========================================

BACKEND_DIRECTORY = Path(
    __file__
).resolve().parents[1]

configured_chroma_path = os.getenv(
    "CHROMA_DIRECTORY",
    "",
).strip()

if configured_chroma_path:
    candidate_path = Path(
        configured_chroma_path
    ).expanduser()

    CHROMA_DIRECTORY = (
        candidate_path
        if candidate_path.is_absolute()
        else BACKEND_DIRECTORY / candidate_path
    ).resolve()

else:
    CHROMA_DIRECTORY = (
        BACKEND_DIRECTORY / "chroma_db"
    ).resolve()


COLLECTION_NAME = os.getenv(
    "CHROMA_COLLECTION_NAME",
    "enterprise_dashboard",
).strip() or "enterprise_dashboard"


DEFAULT_TOP_K = 10
MAX_TOP_K = 50


# Optional relevance filter.
#
# Leave CHROMA_MAX_DISTANCE unset to keep all
# retrieved results. Set it only after checking
# the distance values produced by your collection.
#
# Lower distance means a closer match.
configured_max_distance = os.getenv(
    "CHROMA_MAX_DISTANCE",
    "",
).strip()

try:
    MAX_DISTANCE = (
        float(configured_max_distance)
        if configured_max_distance
        else None
    )

except ValueError as error:
    raise RuntimeError(
        "CHROMA_MAX_DISTANCE must be a number."
    ) from error


# ==========================================
# General Helpers
# ==========================================

def normalize_key(value: Any) -> str:
    return "".join(
        character
        for character in str(
            value or ""
        ).strip().lower()
        if character.isalnum()
    )


def normalize_entity_type(
    value: Any,
) -> str | None:
    aliases = {
        "user": "user",
        "users": "user",
        "enterpriseuser": "user",
        "account": "user",
        "accounts": "user",

        "application": "application",
        "applications": "application",
        "app": "application",
        "apps": "application",
        "mobileapp": "application",
        "software": "application",

        "device": "device",
        "devices": "device",
        "manageddevice": "device",
        "computer": "device",
        "computers": "device",
    }

    return aliases.get(
        normalize_key(
            value
        )
    )


def list_collection_names(
    client: Any,
) -> list[str]:
    try:
        collections = client.list_collections()

    except Exception:
        return []

    names: list[str] = []

    for collection in collections:
        name = (
            collection
            if isinstance(
                collection,
                str,
            )
            else getattr(
                collection,
                "name",
                None,
            )
        )

        if name:
            names.append(
                str(name)
            )

    return names


def get_chroma_client():
    CHROMA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    return chromadb.PersistentClient(
        path=str(
            CHROMA_DIRECTORY
        )
    )


# ==========================================
# Get Current Chroma Collection
# ==========================================

def get_enterprise_collection():
    """
    Return the current Chroma collection by name.

    A new client and collection reference are
    obtained for each request so a stale collection
    UUID is not reused after the collection is
    rebuilt.
    """

    client = get_chroma_client()

    try:
        return client.get_collection(
            name=COLLECTION_NAME
        )

    except NotFoundError as error:
        available_collections = (
            list_collection_names(
                client
            )
        )

        raise RuntimeError(
            "\nEnterprise AI collection was not found."
            f"\nExpected collection: {COLLECTION_NAME}"
            f"\nChroma directory: {CHROMA_DIRECTORY}"
            f"\nAvailable collections: {available_collections}"
            "\nRun the enterprise knowledge-base sync "
            "before asking RAG questions."
        ) from error


# ==========================================
# Embedding Validation
# ==========================================

def normalize_embedding(
    embedding: Any,
) -> list[float]:
    """
    Convert the embedding result into one flat,
    finite list of floats.

    This supports ordinary Python lists and
    array-like values such as NumPy arrays.
    """

    if embedding is None:
        raise RuntimeError(
            "The embedding model returned no embedding."
        )

    if hasattr(
        embedding,
        "tolist",
    ):
        embedding = embedding.tolist()

    # Some embedding helpers return [[...]]
    # instead of [...].
    if (
        isinstance(
            embedding,
            list,
        )
        and len(embedding) == 1
        and isinstance(
            embedding[0],
            (
                list,
                tuple,
            ),
        )
    ):
        embedding = embedding[0]

    if not isinstance(
        embedding,
        (
            list,
            tuple,
        ),
    ):
        raise RuntimeError(
            "The embedding model returned an "
            "unsupported embedding type."
        )

    normalized: list[float] = []

    for value in embedding:
        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                "The embedding contains a non-numeric value."
            ) from error

        if not math.isfinite(
            number
        ):
            raise RuntimeError(
                "The embedding contains a non-finite value."
            )

        normalized.append(
            number
        )

    if not normalized:
        raise RuntimeError(
            "The embedding model returned an "
            "empty query embedding."
        )

    return normalized


# ==========================================
# Query Result Helpers
# ==========================================

def first_result_list(
    results: dict[str, Any],
    key: str,
) -> list[Any]:
    value = results.get(
        key
    )

    if not isinstance(
        value,
        list,
    ):
        return []

    if (
        value
        and isinstance(
            value[0],
            list,
        )
    ):
        return value[0] or []

    return value


def normalize_distance(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        distance = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if not math.isfinite(
        distance
    ):
        return None

    return distance


def distance_is_acceptable(
    distance: float | None,
) -> bool:
    if MAX_DISTANCE is None:
        return True

    if distance is None:
        return False

    return distance <= MAX_DISTANCE


def build_context(
    results: dict[str, Any],
) -> list[dict[str, Any]]:
    ids = first_result_list(
        results,
        "ids",
    )

    documents = first_result_list(
        results,
        "documents",
    )

    metadatas = first_result_list(
        results,
        "metadatas",
    )

    distances = first_result_list(
        results,
        "distances",
    )

    result_count = max(
        len(ids),
        len(documents),
        len(metadatas),
        len(distances),
        0,
    )

    context: list[
        dict[str, Any]
    ] = []

    for index in range(
        result_count
    ):
        record_id = (
            ids[index]
            if index < len(ids)
            else None
        )

        document = (
            documents[index]
            if index < len(documents)
            else ""
        )

        metadata = (
            metadatas[index]
            if index < len(metadatas)
            else {}
        )

        raw_distance = (
            distances[index]
            if index < len(distances)
            else None
        )

        distance = normalize_distance(
            raw_distance
        )

        if not distance_is_acceptable(
            distance
        ):
            continue

        context.append({
            "id": record_id,
            "document": str(
                document or ""
            ),
            "metadata": (
                metadata
                if isinstance(
                    metadata,
                    dict,
                )
                else {}
            ),
            "distance": distance,
        })

    # Chroma normally returns nearest results first,
    # but sorting keeps the behavior deterministic.
    context.sort(
        key=lambda item: (
            item["distance"] is None,
            (
                item["distance"]
                if item["distance"] is not None
                else float("inf")
            ),
        )
    )

    return context


# ==========================================
# Query Chroma
# ==========================================

def query_collection(
    collection: Any,
    embedding: list[float],
    result_limit: int,
) -> dict[str, Any]:
    try:
        return collection.query(
            query_embeddings=[
                embedding
            ],
            n_results=result_limit,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

    except NotFoundError:
        # The collection may have been rebuilt
        # between count() and query(). Reopen the
        # collection and retry exactly once.
        refreshed_collection = (
            get_enterprise_collection()
        )

        refreshed_count = (
            refreshed_collection.count()
        )

        if refreshed_count == 0:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }

        return refreshed_collection.query(
            query_embeddings=[
                embedding
            ],
            n_results=min(
                result_limit,
                refreshed_count,
            ),
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

    except Exception as error:
        raise RuntimeError(
            "Chroma could not search the enterprise "
            "knowledge base."
        ) from error


# ==========================================
# Retrieve Relevant Documents
# ==========================================

def retrieve_context(
    question: Any,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    cleaned_question = str(
        question or ""
    ).strip()

    if not cleaned_question:
        return []

    try:
        requested_results = int(
            top_k
        )

    except (
        TypeError,
        ValueError,
    ):
        requested_results = (
            DEFAULT_TOP_K
        )

    requested_results = max(
        1,
        min(
            requested_results,
            MAX_TOP_K,
        ),
    )

    collection = (
        get_enterprise_collection()
    )

    try:
        record_count = int(
            collection.count()
        )

    except NotFoundError:
        collection = (
            get_enterprise_collection()
        )

        record_count = int(
            collection.count()
        )

    except Exception as error:
        raise RuntimeError(
            "Chroma could not count the enterprise "
            "knowledge-base records."
        ) from error

    print(
        "\nSearching Enterprise Knowledge Base..."
    )
    print(
        f"Collection: {COLLECTION_NAME}"
    )
    print(
        f"Chroma directory: {CHROMA_DIRECTORY}"
    )
    print(
        f"Knowledge-base records: {record_count}"
    )

    if record_count == 0:
        print(
            "Enterprise knowledge base is empty."
        )
        return []

    result_limit = min(
        requested_results,
        record_count,
    )

    embedding = normalize_embedding(
        create_embedding(
            cleaned_question
        )
    )

    results = query_collection(
        collection=collection,
        embedding=embedding,
        result_limit=result_limit,
    )

    context = build_context(
        results
    )

    print(
        f"Retrieved {len(context)} relevant documents"
    )

    if (
        MAX_DISTANCE is not None
        and not context
    ):
        print(
            "All retrieved documents were rejected "
            "by CHROMA_MAX_DISTANCE."
        )

    return context


# ==========================================
# Retrieve All Records
# ==========================================

def retrieve_all_records() -> list[
    dict[str, Any]
]:
    collection = (
        get_enterprise_collection()
    )

    try:
        results = collection.get(
            include=[
                "documents",
                "metadatas",
            ]
        )

    except NotFoundError:
        collection = (
            get_enterprise_collection()
        )

        results = collection.get(
            include=[
                "documents",
                "metadatas",
            ]
        )

    ids = results.get(
        "ids"
    ) or []

    documents = results.get(
        "documents"
    ) or []

    metadatas = results.get(
        "metadatas"
    ) or []

    record_count = max(
        len(ids),
        len(documents),
        len(metadatas),
        0,
    )

    records: list[
        dict[str, Any]
    ] = []

    for index in range(
        record_count
    ):
        records.append({
            "id": (
                ids[index]
                if index < len(ids)
                else None
            ),
            "document": (
                documents[index]
                if index < len(documents)
                else ""
            ) or "",
            "metadata": (
                metadatas[index]
                if index < len(metadatas)
                else {}
            ) or {},
        })

    return records


# ==========================================
# Retrieve Records by Entity Type
# ==========================================

def retrieve_all_entities(
    entity_type: Any,
) -> list[dict[str, Any]]:
    expected_type = normalize_entity_type(
        entity_type
    )

    if expected_type is None:
        raise ValueError(
            "entity_type must be user, "
            "application or device."
        )

    matching_records: list[
        dict[str, Any]
    ] = []

    for record in retrieve_all_records():
        metadata = record.get(
            "metadata"
        ) or {}

        stored_type = normalize_entity_type(
            metadata.get("entity_type")
            or metadata.get("type")
            or metadata.get("record_type")
            or metadata.get("source_type")
        )

        if stored_type == expected_type:
            matching_records.append(
                record
            )

    return matching_records


# ==========================================
# Count Enterprise Entities
# ==========================================

def count_enterprise_entities(
    entity_type: Any,
) -> int:
    return len(
        retrieve_all_entities(
            entity_type
        )
    )


# ==========================================
# Collection Diagnostics
# ==========================================

def get_collection_status() -> dict[str, Any]:
    collection = (
        get_enterprise_collection()
    )

    return {
        "collection_name":
            COLLECTION_NAME,

        "chroma_directory":
            str(
                CHROMA_DIRECTORY
            ),

        "record_count":
            int(
                collection.count()
            ),

        "max_distance":
            MAX_DISTANCE,
    }


# ==========================================
# Pretty Print
# ==========================================

def print_context(
    results: list[dict[str, Any]],
) -> None:
    print(
        "\nRetrieved Context\n"
    )

    if not results:
        print(
            "No relevant documents were found."
        )
        return

    for index, result in enumerate(
        results,
        start=1,
    ):
        print(
            "=" * 60
        )
        print(
            f"Document {index}"
        )
        print(
            "-" * 60
        )
        print(
            result.get(
                "document",
                "",
            )
        )
        print(
            "\nMetadata"
        )
        print(
            result.get(
                "metadata",
                {},
            )
        )
        print(
            "\nDistance"
        )
        print(
            result.get(
                "distance"
            )
        )
        print()


# ==========================================
# Standalone Testing
# ==========================================

if __name__ == "__main__":
    query = input(
        "Question: "
    ).strip()

    retrieved = retrieve_context(
        query
    )

    print_context(
        retrieved
    )