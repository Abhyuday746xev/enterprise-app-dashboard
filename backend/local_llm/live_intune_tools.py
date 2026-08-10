from __future__ import annotations

# ==========================================
# Live Microsoft Graph / Intune Tools
# ==========================================
#
# This module reads current users, applications
# and managed devices through graph_batch.py.
#
# It is read-only. It does not update, delete,
# wipe, retire, restart or remediate anything.
#
# ==========================================

import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from graph_batch import fetch_batch_data


# ==========================================
# Environment Configuration
# ==========================================

BACKEND_DIRECTORY = Path(
    __file__
).resolve().parents[1]

ENV_FILE = (
    BACKEND_DIRECTORY / ".env"
)

load_dotenv(
    dotenv_path=ENV_FILE
)


# ==========================================
# Cache Configuration
# ==========================================

def read_non_negative_float(
    name: str,
    default: float,
) -> float:
    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = float(
            raw_value
        )

    except ValueError as error:
        raise RuntimeError(
            f"{name} must be a number."
        ) from error

    if value < 0:
        raise RuntimeError(
            f"{name} cannot be negative."
        )

    return value


LIVE_CACHE_TTL_SECONDS = (
    read_non_negative_float(
        "LIVE_INTUNE_CACHE_TTL_SECONDS",
        60,
    )
)


# ==========================================
# Internal Cache
# ==========================================

_cache_lock = threading.RLock()

_inventory_cache: dict[
    str,
    Any,
] | None = None

_inventory_cache_time = 0.0


# ==========================================
# General Helpers
# ==========================================

MISSING_VALUES = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "nil",
    "unknown",
    "not available",
    "[]",
    "{}",
}


def normalize_text(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def normalize_key(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").lower(),
    )


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        return len(value) == 0

    return (
        str(value)
        .strip()
        .lower()
        in MISSING_VALUES
    )


def parse_boolean(
    value: Any,
) -> bool | None:
    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return None

    normalized = normalize_text(
        value
    )

    if normalized in {
        "true",
        "1",
        "yes",
        "enabled",
        "active",
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
        "disabled",
        "inactive",
    }:
        return False

    return None


def parse_graph_datetime(
    value: Any,
) -> datetime | None:
    if is_missing(
        value
    ):
        return None

    if isinstance(
        value,
        datetime,
    ):
        parsed = value

    else:
        text = str(
            value
        ).strip()

        if text.endswith("Z"):
            text = (
                text[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                text
            )

        except ValueError:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def format_graph_date(
    value: Any,
) -> str | None:
    parsed = parse_graph_datetime(
        value
    )

    if parsed is None:
        return None

    return parsed.strftime(
        "%d %B %Y"
    )


def first_present(
    record: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = record.get(
            key
        )

        if not is_missing(
            value
        ):
            return value

    return None


def clone_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        dict(record)
        for record in records
    ]


def deduplicate_by_id(
    records: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        records,
        list,
    ):
        return []

    unique: dict[
        str,
        dict[str, Any],
    ] = {}

    anonymous_index = 0

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            continue

        record_id = normalize_key(
            record.get("id")
        )

        if not record_id:
            anonymous_index += 1
            record_id = (
                f"anonymous{anonymous_index}"
            )

        unique[record_id] = dict(
            record
        )

    return list(
        unique.values()
    )


# ==========================================
# Access Token
# ==========================================

def get_graph_access_token() -> str:
    token = os.getenv(
        "GRAPH_ACCESS_TOKEN",
        "",
    ).strip()

    if token.lower().startswith(
        "bearer "
    ):
        token = token[7:].strip()

    if not token:
        raise RuntimeError(
            "GRAPH_ACCESS_TOKEN was not found. "
            f"Expected environment file: {ENV_FILE}"
        )

    return token


# ==========================================
# Live Inventory Loading
# ==========================================

def clear_live_inventory_cache() -> None:
    global _inventory_cache
    global _inventory_cache_time

    with _cache_lock:
        _inventory_cache = None
        _inventory_cache_time = 0.0


def cache_is_valid() -> bool:
    if _inventory_cache is None:
        return False

    if LIVE_CACHE_TTL_SECONDS == 0:
        return False

    age = (
        time.monotonic()
        - _inventory_cache_time
    )

    return (
        age
        < LIVE_CACHE_TTL_SECONDS
    )


def get_live_inventory(
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Return current Microsoft Graph inventory.

    A short cache avoids sending a complete paginated
    batch request for every single chat message.

    Set LIVE_INTUNE_CACHE_TTL_SECONDS=0 to disable
    caching and query Graph on every request.
    """

    global _inventory_cache
    global _inventory_cache_time

    with _cache_lock:
        if (
            not force_refresh
            and cache_is_valid()
        ):
            assert _inventory_cache is not None

            return {
                "applications":
                    clone_records(
                        _inventory_cache[
                            "applications"
                        ]
                    ),

                "users":
                    clone_records(
                        _inventory_cache[
                            "users"
                        ]
                    ),

                "devices":
                    clone_records(
                        _inventory_cache[
                            "devices"
                        ]
                    ),

                "fetched_at":
                    _inventory_cache[
                        "fetched_at"
                    ],

                "cached":
                    True,
            }

        token = get_graph_access_token()

        applications, users, devices = (
            fetch_batch_data(
                token
            )
        )

        inventory = {
            "applications":
                deduplicate_by_id(
                    applications
                ),

            "users":
                deduplicate_by_id(
                    users
                ),

            "devices":
                deduplicate_by_id(
                    devices
                ),

            "fetched_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "cached":
                False,
        }

        _inventory_cache = {
            "applications":
                clone_records(
                    inventory[
                        "applications"
                    ]
                ),

            "users":
                clone_records(
                    inventory[
                        "users"
                    ]
                ),

            "devices":
                clone_records(
                    inventory[
                        "devices"
                    ]
                ),

            "fetched_at":
                inventory[
                    "fetched_at"
                ],
        }

        _inventory_cache_time = (
            time.monotonic()
        )

        return inventory


def get_live_users(
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    return get_live_inventory(
        force_refresh=force_refresh
    )["users"]


def get_live_applications(
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    return get_live_inventory(
        force_refresh=force_refresh
    )["applications"]


def get_live_devices(
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    return get_live_inventory(
        force_refresh=force_refresh
    )["devices"]


# ==========================================
# Application Platform Detection
# ==========================================

def normalize_graph_type(
    value: Any,
) -> str:
    text = normalize_text(
        value
    )

    for prefix in (
        "#microsoft.graph.",
        "microsoft.graph.",
    ):
        if text.startswith(
            prefix
        ):
            return text[
                len(prefix):
            ]

    return text


def detect_application_platform(
    application: dict[str, Any],
) -> str:
    value = first_present(
        application,
        "platform",
        "operatingSystem",
        "operating_system",
        "@odata.type",
        "appType",
        "app_type",
    )

    normalized = normalize_graph_type(
        value
    )

    if (
        "ios" in normalized
        or "ipad" in normalized
    ):
        return "iOS/iPadOS"

    if (
        "macos" in normalized
        or "mac os" in normalized
        or normalized.startswith("mac")
    ):
        return "macOS"

    if "android" in normalized:
        return "Android"

    if (
        "windows" in normalized
        or "win32" in normalized
        or "winget" in normalized
        or "microsoftstore" in normalized
        or "officesuite" in normalized
    ):
        return "Windows"

    if (
        normalized in {
            "web",
            "webapp",
        }
        or "browser" in normalized
    ):
        return "Web"

    return "Other"


# ==========================================
# Record Alias Helpers
# ==========================================

def user_aliases(
    record: dict[str, Any],
) -> list[str]:
    aliases = [
        first_present(
            record,
            "displayName",
            "display_name",
        ),
        first_present(
            record,
            "userPrincipalName",
            "user_principal_name",
        ),
        record.get("mail"),
        record.get("id"),
    ]

    for value in list(
        aliases
    ):
        if (
            isinstance(
                value,
                str,
            )
            and "@" in value
        ):
            aliases.append(
                value.split(
                    "@",
                    1,
                )[0]
            )

    return [
        str(value)
        for value in aliases
        if not is_missing(
            value
        )
    ]


def application_aliases(
    record: dict[str, Any],
) -> list[str]:
    values = (
        first_present(
            record,
            "displayName",
            "display_name",
            "name",
        ),
        record.get("fileName"),
        record.get("id"),
    )

    return [
        str(value)
        for value in values
        if not is_missing(
            value
        )
    ]


def device_aliases(
    record: dict[str, Any],
) -> list[str]:
    values = (
        first_present(
            record,
            "deviceName",
            "device_name",
            "managedDeviceName",
        ),
        record.get("azureADDeviceId"),
        record.get(
            "azureActiveDirectoryDeviceId"
        ),
        record.get("id"),
    )

    return [
        str(value)
        for value in values
        if not is_missing(
            value
        )
    ]


def record_aliases(
    entity_type: str,
    record: dict[str, Any],
) -> list[str]:
    if entity_type == "user":
        return user_aliases(
            record
        )

    if entity_type == "application":
        return application_aliases(
            record
        )

    if entity_type == "device":
        return device_aliases(
            record
        )

    return []


# ==========================================
# Record Search
# ==========================================

def score_alias_match(
    question_key: str,
    alias: str,
) -> int:
    alias_key = normalize_key(
        alias
    )

    if len(alias_key) < 3:
        return 0

    if question_key == alias_key:
        return (
            10_000
            + len(alias_key)
        )

    if alias_key in question_key:
        return (
            8_000
            + len(alias_key)
        )

    if (
        len(question_key) >= 3
        and question_key in alias_key
    ):
        return (
            5_000
            + len(question_key)
        )

    return 0


def find_live_records(
    question: Any,
    entity_type: str | None = None,
    inventory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    question_key = normalize_key(
        question
    )

    if len(question_key) < 3:
        return []

    if inventory is None:
        inventory = get_live_inventory()

    collections = {
        "user":
            inventory["users"],

        "application":
            inventory[
                "applications"
            ],

        "device":
            inventory["devices"],
    }

    if entity_type is not None:
        if entity_type not in collections:
            raise ValueError(
                "entity_type must be user, "
                "application or device."
            )

        entity_types = [
            entity_type
        ]

    else:
        entity_types = [
            "user",
            "application",
            "device",
        ]

    matches: list[
        dict[str, Any]
    ] = []

    for current_type in entity_types:
        for record in collections[
            current_type
        ]:
            best_score = 0
            best_alias = None

            for alias in record_aliases(
                current_type,
                record,
            ):
                score = score_alias_match(
                    question_key,
                    alias,
                )

                if score > best_score:
                    best_score = score
                    best_alias = alias

            if best_score:
                matches.append({
                    "entity_type":
                        current_type,

                    "record":
                        record,

                    "score":
                        best_score,

                    "matched_alias":
                        best_alias,
                })

    matches.sort(
        key=lambda match: (
            match["score"],
            len(
                normalize_key(
                    match[
                        "matched_alias"
                    ]
                )
            ),
        ),
        reverse=True,
    )

    if not matches:
        return []

    highest_score = matches[0][
        "score"
    ]

    return [
        match
        for match in matches
        if match["score"] == highest_score
    ]


def find_live_record(
    question: Any,
    entity_type: str | None = None,
    inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matches = find_live_records(
        question=question,
        entity_type=entity_type,
        inventory=inventory,
    )

    unique_matches: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    for match in matches:
        record = match[
            "record"
        ]

        identity = (
            match["entity_type"],
            str(
                record.get("id")
                or match[
                    "matched_alias"
                ]
            ),
        )

        unique_matches[
            identity
        ] = match

    reduced_matches = list(
        unique_matches.values()
    )

    if not reduced_matches:
        return {
            "status": "not_found",
            "matches": [],
        }

    if len(reduced_matches) > 1:
        return {
            "status": "ambiguous",
            "matches": reduced_matches,
        }

    return {
        "status": "found",
        "match": reduced_matches[0],
        "matches": reduced_matches,
    }


# ==========================================
# Standalone Test
# ==========================================

if __name__ == "__main__":
    inventory = get_live_inventory(
        force_refresh=True
    )

    print(
        "\n========== LIVE GRAPH SUMMARY ==========\n"
    )

    print(
        f"Applications : "
        f"{len(inventory['applications'])}"
    )

    print(
        f"Users        : "
        f"{len(inventory['users'])}"
    )

    print(
        f"Devices      : "
        f"{len(inventory['devices'])}"
    )

    print(
        f"Fetched at   : "
        f"{inventory['fetched_at']}"
    )