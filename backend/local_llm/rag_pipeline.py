from __future__ import annotations

# ==========================================
# Enterprise RAG Fallback Pipeline
# ==========================================
#
# Live users, applications and devices should
# be answered by local_llm.live_query_router.
#
# This file is intentionally responsible only
# for semantic RAG questions such as:
#
# - Explain a compliance issue.
# - Summarize the retrieved enterprise context.
# - Suggest troubleshooting guidance from the
#   indexed knowledge base.
#
# It must not guess live inventory counts,
# statuses, dates or named-record details.
#
# ==========================================

import re
from typing import Any

from local_llm.llm import ask_llm
from local_llm.memory import memory
from local_llm.prompts import build_prompt
from local_llm.retriever import retrieve_context


# ==========================================
# Configuration
# ==========================================

DEFAULT_TOP_K = 10
MAX_ANSWER_CHARACTERS = 8_000

LIVE_ENTITY_WORDS = (
    "user",
    "users",
    "account",
    "accounts",
    "application",
    "applications",
    "app",
    "apps",
    "software",
    "device",
    "devices",
    "computer",
    "computers",
    "laptop",
    "laptops",
    "tablet",
    "tablets",
)

LIVE_INVENTORY_TERMS = (
    "how many",
    "count",
    "total",
    "show all",
    "list all",
    "display all",
    "oldest",
    "newest",
    "latest",
    "earliest",
    "largest",
    "smallest",
    "enabled",
    "disabled",
    "compliant",
    "noncompliant",
    "non-compliant",
    "published",
    "unpublished",
    "created date",
    "last modified",
    "phone number",
    "mobile phone",
    "notes",
    "publisher",
    "platform",
    "version",
)


# ==========================================
# Text Helpers
# ==========================================

def normalize_text(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def contains_entity_word(question: str) -> bool:
    normalized = normalize_text(
        question
    )

    return any(
        re.search(
            rf"\b{re.escape(word)}\b",
            normalized,
        )
        for word in LIVE_ENTITY_WORDS
    )


def is_follow_up_question(question: str) -> bool:
    normalized = normalize_text(
        question
    )

    return bool(
        re.search(
            r"\b("
            r"it|its|"
            r"they|them|their|"
            r"those|these|"
            r"that one|"
            r"the previous one|"
            r"what about"
            r")\b",
            normalized,
        )
    )


def looks_like_named_record_lookup(
    question: str,
) -> bool:
    """
    Detect short record lookups such as:

    - what about test-1?
    - tell me about LAPTOP-04
    - Adobe Reader?
    """

    normalized = normalize_text(
        question
    )

    if re.search(
        r"\b("
        r"what about|"
        r"tell me about|"
        r"details (?:for|of|about)|"
        r"information (?:for|on|about)|"
        r"describe"
        r")\b",
        normalized,
    ):
        return True

    cleaned = re.sub(
        r"[^a-z0-9@._\-\s]",
        "",
        normalized,
    ).strip()

    return (
        bool(cleaned)
        and len(cleaned.split()) <= 3
        and not re.search(
            r"\b("
            r"why|how|explain|summarize|"
            r"recommend|advisory|troubleshoot"
            r")\b",
            cleaned,
        )
    )


def looks_like_live_inventory_question(
    question: str,
) -> bool:
    """
    Identify questions that should have been
    handled by the live Microsoft Graph router.

    Refusing these in the RAG fallback prevents
    Chroma retrieval or the LLM from inventing
    exact live values.
    """

    normalized = normalize_text(
        question
    )

    if looks_like_named_record_lookup(
        question
    ):
        return True

    has_inventory_term = any(
        term in normalized
        for term in LIVE_INVENTORY_TERMS
    )

    return (
        contains_entity_word(
            question
        )
        and has_inventory_term
    )


# ==========================================
# Conversation Memory
# ==========================================

def get_reference_context(
    question: str,
) -> str:
    """
    Conversation history is used only to resolve
    references in follow-up questions. It is never
    treated as an authoritative inventory source.
    """

    if not is_follow_up_question(
        question
    ):
        return ""

    context = memory.get_context()

    return str(
        context or ""
    ).strip()


def save_exchange(
    question: str,
    answer: str,
) -> None:
    try:
        memory.add_exchange(
            question,
            answer,
        )

    except Exception as error:
        # Memory failure should not prevent an
        # otherwise valid answer from returning.
        print(
            f"Conversation memory warning: {error}"
        )


# ==========================================
# Prompt Construction
# ==========================================

def build_accuracy_prompt(
    question: str,
    retrieved_context: list[dict[str, Any]],
) -> str:
    base_prompt = build_prompt(
        question=question,
        retrieved_documents=retrieved_context,
    )

    rules = """
You are the Enterprise AI RAG fallback.

Response rules:

1. Use only facts explicitly present in the current retrieved enterprise context.
2. Do not invent users, applications, devices, assignments, statuses, dates, versions, relationships, causes, actions or counts.
3. Treat false, 0, "false" and "0" as Disabled only when they come from an explicit account-enabled field.
4. Never say "enabled status of 0". Say "Disabled" when the explicit account-enabled value is false or 0.
5. Never infer account status from an email address, username, domain or naming convention.
6. Never calculate an enterprise-wide total from partial semantic retrieval.
7. If required evidence is absent, state the missing field or evidence directly.
8. Do not claim that a user has no applications unless the context explicitly contains complete assignment data.
9. Do not claim that a field is absent across the enterprise merely because it is absent from the retrieved records.
10. Start with the direct answer.
11. Use one to four concise sentences unless the user explicitly requests a list or detailed explanation.
12. Do not repeat the question.
13. Do not add generic background, warnings or recommendations unless requested.
14. Conversation history may resolve pronouns only. It is not an authoritative data source.
""".strip()

    reference_context = get_reference_context(
        question
    )

    if reference_context:
        return f"""
{rules}

Conversation history for reference resolution only:
{reference_context}

{base_prompt}
""".strip()

    return f"""
{rules}

{base_prompt}
""".strip()


# ==========================================
# Source Formatting
# ==========================================

def build_sources(
    context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in context:
        if not isinstance(
            item,
            dict,
        ):
            continue

        metadata = item.get(
            "metadata"
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        source_type = str(
            metadata.get("type")
            or metadata.get("entity_type")
            or metadata.get("record_type")
            or "enterprise_record"
        )

        source_label = str(
            metadata.get("name")
            or metadata.get("display_name")
            or metadata.get("email")
            or metadata.get("user_principal_name")
            or metadata.get("device_name")
            or metadata.get("id")
            or source_type
        )

        identity = (
            source_type,
            source_label,
        )

        if identity in seen:
            continue

        seen.add(
            identity
        )

        sources.append({
            "type": source_type,
            "metadata": metadata,
        })

    return sources


# ==========================================
# Response Helpers
# ==========================================

def live_router_required_response(
    question: str,
) -> dict[str, Any]:
    answer = (
        "This is a live inventory question and must be "
        "answered from Microsoft Graph. The live Intune "
        "query router did not handle it, so I will not "
        "guess from partial RAG context."
    )

    save_exchange(
        question,
        answer,
    )

    return {
        "question": question,
        "answer": answer,
        "sources": [],
        "route": "live_router_required",
    }


def no_context_response(
    question: str,
) -> dict[str, Any]:
    answer = (
        "I could not find enough relevant information "
        "in the enterprise knowledge base to answer that."
    )

    save_exchange(
        question,
        answer,
    )

    return {
        "question": question,
        "answer": answer,
        "sources": [],
        "route": "rag",
    }


# ==========================================
# Enterprise AI RAG Fallback
# ==========================================

def ask_enterprise_ai(
    question: str,
) -> dict[str, Any]:
    cleaned_question = str(
        question or ""
    ).strip()

    if not cleaned_question:
        return {
            "question": "",
            "answer": "Please enter a question.",
            "sources": [],
            "route": "validation",
        }

    print(
        "\n======================================"
    )
    print(
        "Enterprise RAG Fallback Request"
    )
    print(
        "======================================"
    )
    print(
        f"\nQuestion:\n{cleaned_question}"
    )

    # Exact live inventory questions must be
    # answered by live_query_router.py in app.py.
    if looks_like_live_inventory_question(
        cleaned_question
    ):
        return live_router_required_response(
            cleaned_question
        )

    try:
        context = retrieve_context(
            question=cleaned_question,
            top_k=DEFAULT_TOP_K,
        )

    except Exception as error:
        print(
            f"RAG retrieval error: {error}"
        )

        return {
            "question": cleaned_question,
            "answer": (
                "The enterprise knowledge base could "
                "not be searched successfully."
            ),
            "sources": [],
            "route": "rag_error",
        }

    if not context:
        return no_context_response(
            cleaned_question
        )

    prompt = build_accuracy_prompt(
        question=cleaned_question,
        retrieved_context=context,
    )

    try:
        answer = str(
            ask_llm(
                prompt
            )
            or ""
        ).strip()

    except Exception as error:
        print(
            f"Local LLM error: {error}"
        )

        return {
            "question": cleaned_question,
            "answer": (
                "The local language model could not "
                "generate an answer."
            ),
            "sources": build_sources(
                context
            ),
            "route": "rag_error",
        }

    if not answer:
        answer = (
            "The local language model did not "
            "return an answer."
        )

    if len(answer) > MAX_ANSWER_CHARACTERS:
        answer = (
            answer[:MAX_ANSWER_CHARACTERS]
            .rstrip()
            + "…"
        )

    save_exchange(
        cleaned_question,
        answer,
    )

    return {
        "question": cleaned_question,
        "answer": answer,
        "sources": build_sources(
            context
        ),
        "route": "rag",
    }


# ==========================================
# Interactive Console
# ==========================================

if __name__ == "__main__":
    print(
        "\n======================================"
    )
    print(
        "Enterprise RAG Fallback"
    )
    print(
        "======================================"
    )
    print(
        "Type 'exit' to quit."
    )
    print(
        "Type 'clear' to clear memory.\n"
    )

    while True:
        question = input(
            "Ask Enterprise AI > "
        ).strip()

        if question.lower() == "exit":
            print(
                "\nGoodbye.\n"
            )
            break

        if question.lower() == "clear":
            memory.clear()
            print(
                "\nConversation Memory Cleared.\n"
            )
            continue

        if not question:
            print(
                "Please enter a question.\n"
            )
            continue

        try:
            result = ask_enterprise_ai(
                question
            )

        except Exception as error:
            print(
                f"\nEnterprise AI Error:\n"
                f"{error}\n"
            )
            continue

        print(
            "\n======================================"
        )
        print(
            "Answer"
        )
        print(
            "======================================\n"
        )
        print(
            result["answer"]
        )

        print(
            "\nSources"
        )

        for source in result["sources"]:
            print(
                source
            )

        print()