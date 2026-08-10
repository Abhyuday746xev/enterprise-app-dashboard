from __future__ import annotations

# ==========================================
# Local Enterprise Chat Model
# ==========================================

import os
from typing import Any

import requests

from .config import (
    OLLAMA_CHAT_URL,
    REQUEST_TIMEOUT,
    TEMPERATURE,
)
from .models import get_chat_model
from .prompts import SYSTEM_PROMPT


# ==========================================
# Configuration
# ==========================================

def read_positive_integer_environment(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = int(
            raw_value
        )

    except ValueError as error:
        raise RuntimeError(
            f"{name} must be an integer."
        ) from error

    if value <= 0:
        raise RuntimeError(
            f"{name} must be greater than zero."
        )

    return value


MAX_PROMPT_CHARACTERS = (
    read_positive_integer_environment(
        "OLLAMA_MAX_PROMPT_CHARACTERS",
        120000,
    )
)

KEEP_ALIVE = os.getenv(
    "OLLAMA_KEEP_ALIVE",
    "10m",
).strip()

NUM_PREDICT_VALUE = os.getenv(
    "OLLAMA_NUM_PREDICT",
    "",
).strip()


# ==========================================
# Exceptions
# ==========================================

class OllamaError(RuntimeError):
    """Raised when the local Ollama request fails."""


# ==========================================
# Configuration Helpers
# ==========================================

def get_ollama_url() -> str:
    url = str(
        OLLAMA_CHAT_URL or ""
    ).strip()

    if not url:
        raise OllamaError(
            "OLLAMA_CHAT_URL is not configured."
        )

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        raise OllamaError(
            "OLLAMA_CHAT_URL must start with "
            "http:// or https://."
        )

    return url


def get_temperature() -> float:
    try:
        temperature = float(
            TEMPERATURE
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise OllamaError(
            "TEMPERATURE must be a number."
        ) from error

    # Keep enterprise answers predictable.
    return max(
        0.0,
        min(
            temperature,
            2.0,
        ),
    )


def get_num_predict() -> int | None:
    if not NUM_PREDICT_VALUE:
        return None

    try:
        value = int(
            NUM_PREDICT_VALUE
        )

    except ValueError as error:
        raise OllamaError(
            "OLLAMA_NUM_PREDICT must be an integer."
        ) from error

    if value <= 0:
        raise OllamaError(
            "OLLAMA_NUM_PREDICT must be greater than zero."
        )

    return value


def get_timeout() -> Any:
    """
    Preserve either an integer timeout or a
    (connect_timeout, read_timeout) tuple from config.
    """

    timeout = REQUEST_TIMEOUT

    if isinstance(
        timeout,
        (
            int,
            float,
        ),
    ):
        if timeout <= 0:
            raise OllamaError(
                "REQUEST_TIMEOUT must be greater than zero."
            )

        return timeout

    if (
        isinstance(
            timeout,
            tuple,
        )
        and len(timeout) == 2
    ):
        try:
            connect_timeout = float(
                timeout[0]
            )
            read_timeout = float(
                timeout[1]
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise OllamaError(
                "REQUEST_TIMEOUT tuple values "
                "must be numbers."
            ) from error

        if (
            connect_timeout <= 0
            or read_timeout <= 0
        ):
            raise OllamaError(
                "REQUEST_TIMEOUT values must "
                "be greater than zero."
            )

        return (
            connect_timeout,
            read_timeout,
        )

    raise OllamaError(
        "REQUEST_TIMEOUT must be a positive number "
        "or a two-value tuple."
    )


# ==========================================
# Prompt Validation
# ==========================================

def clean_prompt(prompt: Any) -> str:
    cleaned = str(
        prompt or ""
    ).strip()

    if not cleaned:
        raise ValueError(
            "The LLM prompt cannot be empty."
        )

    if len(cleaned) > MAX_PROMPT_CHARACTERS:
        raise ValueError(
            "The LLM prompt is too large. "
            f"Maximum size: {MAX_PROMPT_CHARACTERS} characters."
        )

    return cleaned


# ==========================================
# Payload Construction
# ==========================================

def build_chat_payload(
    prompt: str,
) -> dict[str, Any]:
    model = str(
        get_chat_model() or ""
    ).strip()

    if not model:
        raise OllamaError(
            "No Ollama chat model is configured."
        )

    system_prompt = str(
        SYSTEM_PROMPT or ""
    ).strip()

    options: dict[str, Any] = {
        "temperature": get_temperature(),
    }

    num_predict = get_num_predict()

    if num_predict is not None:
        options["num_predict"] = (
            num_predict
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [],
        "stream": False,
        "options": options,
    }

    if system_prompt:
        payload["messages"].append({
            "role": "system",
            "content": system_prompt,
        })

    payload["messages"].append({
        "role": "user",
        "content": prompt,
    })

    if KEEP_ALIVE:
        payload["keep_alive"] = (
            KEEP_ALIVE
        )

    return payload


# ==========================================
# Error Parsing
# ==========================================

def response_error_text(
    response: requests.Response,
) -> str:
    try:
        body = response.json()

    except ValueError:
        body = response.text

    if isinstance(
        body,
        dict,
    ):
        message = (
            body.get("error")
            or body.get("message")
        )

        if message:
            return str(
                message
            )

    text = str(
        body or ""
    ).strip()

    return (
        text
        if text
        else "Unknown Ollama error"
    )


# ==========================================
# Chat Response Parsing
# ==========================================

def parse_chat_response(
    result: Any,
) -> str:
    if not isinstance(
        result,
        dict,
    ):
        raise OllamaError(
            "Ollama returned an invalid JSON response."
        )

    if result.get("error"):
        raise OllamaError(
            f"Ollama error: {result['error']}"
        )

    message = result.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        raise OllamaError(
            "Ollama response does not contain "
            "a message object."
        )

    content = str(
        message.get(
            "content",
            "",
        )
        or ""
    ).strip()

    if not content:
        raise OllamaError(
            "Ollama returned an empty response."
        )

    return content


# ==========================================
# Generate Local LLM Answer
# ==========================================

def ask_llm(prompt: Any) -> str:
    """
    Send one non-streaming chat request to Ollama.

    This function only generates text. It does not
    read Microsoft Graph, execute remediation actions,
    or decide whether an action is authorized.
    """

    cleaned_prompt = clean_prompt(
        prompt
    )

    payload = build_chat_payload(
        cleaned_prompt
    )

    try:
        response = requests.post(
            get_ollama_url(),
            json=payload,
            timeout=get_timeout(),
        )

    except requests.ConnectionError as error:
        raise OllamaError(
            "Could not connect to Ollama. "
            "Make sure the Ollama service is running."
        ) from error

    except requests.Timeout as error:
        raise OllamaError(
            "The Ollama request timed out. "
            "The model may still be loading or the "
            "prompt may be too large."
        ) from error

    except requests.RequestException as error:
        raise OllamaError(
            f"Ollama request failed: {error}"
        ) from error

    if not response.ok:
        error_text = response_error_text(
            response
        )

        if response.status_code == 404:
            raise OllamaError(
                "Ollama returned HTTP 404. Check "
                "OLLAMA_CHAT_URL and confirm that the "
                f"model '{payload['model']}' is installed. "
                f"Details: {error_text}"
            )

        raise OllamaError(
            "Ollama returned "
            f"HTTP {response.status_code}: "
            f"{error_text}"
        )

    try:
        result = response.json()

    except ValueError as error:
        raise OllamaError(
            "Ollama returned a non-JSON response."
        ) from error

    return parse_chat_response(
        result
    )


# ==========================================
# Health Check
# ==========================================

def safe_model_name() -> str | None:
    try:
        model = str(
            get_chat_model() or ""
        ).strip()

        return model or None

    except Exception:
        return None


def test_connection() -> dict[str, Any]:
    """
    Verify that Ollama and the configured model
    can produce a chat response.
    """

    model = safe_model_name()

    try:
        reply = ask_llm(
            "Reply with exactly: OK"
        )

        return {
            "success": True,
            "model": model,
            "response": reply,
            "exact_ok": (
                reply.strip().upper()
                == "OK"
            ),
        }

    except Exception as error:
        return {
            "success": False,
            "model": model,
            "error": str(error),
        }


# ==========================================
# Standalone Testing
# ==========================================

if __name__ == "__main__":
    result = test_connection()

    if result["success"]:
        print(
            "Ollama connection successful."
        )
        print(
            f"Model: {result['model']}"
        )
        print(
            f"Response: {result['response']}"
        )

    else:
        print(
            "Ollama connection failed."
        )
        print(
            f"Error: {result.get('error')}"
        )