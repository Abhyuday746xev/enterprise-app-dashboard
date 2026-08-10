from __future__ import annotations

# ==========================================
# Live Microsoft Graph Query Router
# ==========================================
#
# This module converts common enterprise
# inventory questions into deterministic,
# read-only operations over live Graph data.
#
# Exact values are calculated in Python. The
# local LLM is not allowed to guess them.
#
# ==========================================

import re
from collections import Counter
from datetime import datetime
from typing import Any, Callable

from local_llm.live_intune_tools import (
    detect_application_platform,
    find_live_record,
    first_present,
    format_graph_date,
    get_live_inventory,
    is_missing,
    normalize_key,
    normalize_text,
    parse_boolean,
    parse_graph_datetime,
)


# ==========================================
# Entity Configuration
# ==========================================

ENTITY_LABELS = {
    "user": (
        "user",
        "users",
    ),

    "application": (
        "application",
        "applications",
    ),

    "device": (
        "device",
        "devices",
    ),
}


ENTITY_PATTERNS = {
    "user":
        r"\b("
        r"users?|accounts?|employees?|people"
        r")\b",

    "application":
        r"\b("
        r"applications?|apps?|software|packages?"
        r")\b",

    "device":
        r"\b("
        r"devices?|machines?|computers?|laptops?|"
        r"tablets?"
        r")\b",
}


# ==========================================
# General Question Detection
# ==========================================

def detect_entity_type(
    question: Any,
) -> str | None:
    normalized = normalize_text(
        question
    )

    for entity_type, pattern in (
        ENTITY_PATTERNS.items()
    ):
        if re.search(
            pattern,
            normalized,
        ):
            return entity_type

    return None


def is_count_question(
    question: Any,
) -> bool:
    return bool(
        re.search(
            r"\b("
            r"how many|number of|count of|"
            r"total number of|total|count"
            r")\b",
            normalize_text(
                question
            ),
        )
    )


def is_list_question(
    question: Any,
) -> bool:
    normalized = normalize_text(
        question
    )

    return bool(
        re.search(
            r"\b(show|list|display|give|get|fetch)\b"
            r".*\b(all|every)\b",
            normalized,
        )
        or re.search(
            r"\b("
            r"what users do we have|"
            r"who are the users|"
            r"what applications do we have|"
            r"what apps do we have|"
            r"which applications are available|"
            r"what devices do we have"
            r")\b",
            normalized,
        )
        or (
            re.search(
                r"\bwhich\b",
                normalized,
            )
            and detect_entity_type(
                question
            ) is not None
            and not is_superlative_question(
                question
            )
        )
    )


def is_superlative_question(
    question: Any,
) -> bool:
    return bool(
        re.search(
            r"\b("
            r"oldest|earliest|"
            r"newest|latest|most recent|"
            r"largest|biggest|smallest"
            r")\b",
            normalize_text(
                question
            ),
        )
    )


def is_named_record_question(
    question: Any,
) -> bool:
    normalized = normalize_text(
        question
    )

    if re.search(
        r"\b("
        r"what about|"
        r"tell me about|"
        r"details (?:for|of|about)|"
        r"information (?:for|on|about)|"
        r"who is|"
        r"describe"
        r")\b",
        normalized,
    ):
        return True

    # A short token such as test-1? or LAPTOP-07?
    cleaned = re.sub(
        r"[^a-z0-9@._\-\s]",
        "",
        normalized,
    ).strip()

    return (
        bool(cleaned)
        and len(cleaned.split()) <= 3
        and not is_count_question(
            question
        )
        and not is_list_question(
            question
        )
        and not is_superlative_question(
            question
        )
        and not re.search(
            r"\b("
            r"all|every|"
            r"why|how|explain|summarize|"
            r"recommend|advisory|troubleshoot"
            r")\b",
            cleaned,
        )
    )


def is_platform_span_question(
    question: Any,
) -> bool:
    normalized = normalize_text(
        question
    )

    return bool(
        is_count_question(
            question
        )
        and re.search(
            ENTITY_PATTERNS[
                "application"
            ],
            normalized,
        )
        and re.search(
            r"\b("
            r"platforms?|operating systems?|oses"
            r")\b",
            normalized,
        )
    )


# ==========================================
# Source Formatting
# ==========================================

def live_source(
    entity_type: str | None,
    inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata: dict[
        str,
        Any,
    ] = {
        "name":
            "Live Microsoft Graph",

        "fetched_at":
            inventory.get(
                "fetched_at"
            ),

        "cached":
            inventory.get(
                "cached",
                False,
            ),
    }

    if entity_type:
        metadata[
            "entity_type"
        ] = entity_type

    return [
        {
            "type":
                "microsoft_graph",

            "metadata":
                metadata,
        }
    ]


def result(
    question: str,
    answer: str,
    inventory: dict[str, Any],
    entity_type: str | None = None,
) -> dict[str, Any]:
    return {
        "question": question,
        "answer": answer,
        "sources": live_source(
            entity_type,
            inventory,
        ),
        "route": "live_intune",
    }


# ==========================================
# Record Collections
# ==========================================

def entity_records(
    inventory: dict[str, Any],
    entity_type: str,
) -> list[dict[str, Any]]:
    key = {
        "user":
            "users",

        "application":
            "applications",

        "device":
            "devices",
    }[
        entity_type
    ]

    return inventory[
        key
    ]


# ==========================================
# Status and Field Helpers
# ==========================================

def user_status(
    user: dict[str, Any],
) -> str:
    enabled = parse_boolean(
        first_present(
            user,
            "accountEnabled",
            "account_enabled",
        )
    )

    if enabled is True:
        return "Enabled"

    if enabled is False:
        return "Disabled"

    return "Unknown"


def normalize_compliance(
    value: Any,
) -> str:
    normalized = normalize_key(
        value
    )

    aliases = {
        "compliant":
            "compliant",

        "noncompliant":
            "noncompliant",

        "notcompliant":
            "noncompliant",

        "unknown":
            "unknown",

        "error":
            "error",

        "conflict":
            "conflict",

        "ingraceperiod":
            "inGracePeriod",
    }

    return aliases.get(
        normalized,
        str(value or "unknown"),
    )


def application_notes(
    application: dict[str, Any],
) -> Any:
    return first_present(
        application,
        "notes",
        "note",
        "remarks",
        "comments",
    )


def user_phone(
    user: dict[str, Any],
) -> Any:
    mobile = first_present(
        user,
        "mobilePhone",
        "mobile_phone",
        "phone",
    )

    if not is_missing(
        mobile
    ):
        return mobile

    business_phones = first_present(
        user,
        "businessPhones",
        "business_phones",
    )

    if isinstance(
        business_phones,
        list,
    ):
        return ", ".join(
            str(phone)
            for phone in business_phones
            if not is_missing(
                phone
            )
        ) or None

    return business_phones


def application_size(
    application: dict[str, Any],
) -> float | None:
    value = first_present(
        application,
        "size",
        "sizeInBytes",
        "size_in_bytes",
    )

    if value is None:
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def format_size(
    value: float,
) -> str:
    units = (
        "bytes",
        "KB",
        "MB",
        "GB",
        "TB",
    )

    size = float(
        value
    )

    unit_index = 0

    while (
        size >= 1024
        and unit_index
        < len(units) - 1
    ):
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return (
            f"{int(size)} "
            f"{units[unit_index]}"
        )

    return (
        f"{size:.2f} "
        f"{units[unit_index]}"
    )


# ==========================================
# Platform Helpers
# ==========================================

def detect_platform_target(
    question: Any,
) -> str | None:
    normalized = normalize_text(
        question
    )

    patterns = (
        (
            "Windows",
            r"\b("
            r"windows|win32|winget|microsoft store"
            r")\b",
        ),

        (
            "macOS",
            r"\b("
            r"macos|mac os|mac"
            r")\b",
        ),

        (
            "iOS/iPadOS",
            r"\b("
            r"ios|ipados|ipad"
            r")\b",
        ),

        (
            "Android",
            r"\bandroid\b",
        ),

        (
            "Web",
            r"\b(web|browser)\b",
        ),
    )

    for platform, pattern in patterns:
        if re.search(
            pattern,
            normalized,
        ):
            return platform

    return None


# ==========================================
# Generic Filters
# ==========================================

def filter_entity_records(
    question: str,
    entity_type: str,
    records: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    str | None,
]:
    normalized = normalize_text(
        question
    )

    # --------------------------------------
    # Users
    # --------------------------------------

    if entity_type == "user":
        if re.search(
            r"\b(disabled|inactive)\b",
            normalized,
        ):
            return (
                [
                    record
                    for record in records
                    if user_status(
                        record
                    ) == "Disabled"
                ],
                "disabled",
            )

        if re.search(
            r"\b(enabled|active)\b",
            normalized,
        ):
            return (
                [
                    record
                    for record in records
                    if user_status(
                        record
                    ) == "Enabled"
                ],
                "enabled",
            )

        if re.search(
            r"\b("
            r"phone|mobile|telephone"
            r")\b",
            normalized,
        ):
            without_phone = bool(
                re.search(
                    r"\b("
                    r"without|missing|no phone|"
                    r"does not have|do not have"
                    r")\b",
                    normalized,
                )
            )

            numerical = bool(
                re.search(
                    r"\b("
                    r"numeric|numerical|digit|digits"
                    r")\b",
                    normalized,
                )
            )

            if without_phone:
                return (
                    [
                        record
                        for record in records
                        if is_missing(
                            user_phone(
                                record
                            )
                        )
                    ],
                    "without a phone number",
                )

            if numerical:
                return (
                    [
                        record
                        for record in records
                        if (
                            not is_missing(
                                user_phone(
                                    record
                                )
                            )
                            and re.search(
                                r"\d",
                                str(
                                    user_phone(
                                        record
                                    )
                                ),
                            )
                        )
                    ],
                    "with digits in the phone number",
                )

            return (
                [
                    record
                    for record in records
                    if not is_missing(
                        user_phone(
                            record
                        )
                    )
                ],
                "with a phone number",
            )

    # --------------------------------------
    # Applications
    # --------------------------------------

    if entity_type == "application":
        if re.search(
            r"\b(notes?|remarks?|comments?)\b",
            normalized,
        ):
            missing_notes = bool(
                re.search(
                    r"\b("
                    r"without|missing|no notes?|"
                    r"does not have|do not have"
                    r")\b",
                    normalized,
                )
            )

            if missing_notes:
                return (
                    [
                        record
                        for record in records
                        if is_missing(
                            application_notes(
                                record
                            )
                        )
                    ],
                    "without notes",
                )

            return (
                [
                    record
                    for record in records
                    if not is_missing(
                        application_notes(
                            record
                        )
                    )
                ],
                "with notes",
            )

        if re.search(
            r"\b("
            r"published|unpublished|processing"
            r")\b",
            normalized,
        ):
            if re.search(
                r"\bunpublished\b",
                normalized,
            ):
                target = "unpublished"

            elif re.search(
                r"\bprocessing\b",
                normalized,
            ):
                target = "processing"

            else:
                target = "published"

            return (
                [
                    record
                    for record in records
                    if normalize_key(
                        first_present(
                            record,
                            "publishingState",
                            "publishing_state",
                        )
                    )
                    == normalize_key(
                        target
                    )
                ],
                f"with publishing state {target}",
            )

        platform = detect_platform_target(
            question
        )

        if platform:
            return (
                [
                    record
                    for record in records
                    if detect_application_platform(
                        record
                    ) == platform
                ],
                f"on {platform}",
            )

        if re.search(
            r"\bassigned\b",
            normalized,
        ):
            requested_value = not bool(
                re.search(
                    r"\b("
                    r"not assigned|unassigned"
                    r")\b",
                    normalized,
                )
            )

            return (
                [
                    record
                    for record in records
                    if parse_boolean(
                        first_present(
                            record,
                            "isAssigned",
                            "is_assigned",
                        )
                    )
                    is requested_value
                ],
                (
                    "that are assigned"
                    if requested_value
                    else "that are not assigned"
                ),
            )

    # --------------------------------------
    # Devices
    # --------------------------------------

    if entity_type == "device":
        if re.search(
            r"\b("
            r"non[- ]?compliant|not compliant"
            r")\b",
            normalized,
        ):
            return (
                [
                    record
                    for record in records
                    if normalize_compliance(
                        first_present(
                            record,
                            "complianceState",
                            "compliance_state",
                        )
                    )
                    == "noncompliant"
                ],
                "that are non-compliant",
            )

        if re.search(
            r"\bcompliant\b",
            normalized,
        ):
            return (
                [
                    record
                    for record in records
                    if normalize_compliance(
                        first_present(
                            record,
                            "complianceState",
                            "compliance_state",
                        )
                    )
                    == "compliant"
                ],
                "that are compliant",
            )

        operating_systems = (
            "windows",
            "macos",
            "mac os",
            "ios",
            "ipados",
            "android",
            "linux",
            "chromeos",
        )

        for operating_system in (
            operating_systems
        ):
            if re.search(
                rf"\b{re.escape(operating_system)}\b",
                normalized,
            ):
                target = normalize_key(
                    operating_system
                )

                return (
                    [
                        record
                        for record in records
                        if target in normalize_key(
                            first_present(
                                record,
                                "operatingSystem",
                                "operating_system",
                            )
                        )
                    ],
                    f"running {operating_system}",
                )

    return records, None


# ==========================================
# Count Answers
# ==========================================

def answer_count(
    question: str,
    entity_type: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    records = entity_records(
        inventory,
        entity_type,
    )

    filtered, description = (
        filter_entity_records(
            question,
            entity_type,
            records,
        )
    )

    count = len(
        filtered
    )

    singular, plural = (
        ENTITY_LABELS[
            entity_type
        ]
    )

    noun = (
        singular
        if count == 1
        else plural
    )

    if description:
        answer = (
            f"{count} enterprise {noun} "
            f"{description}."
        )

    else:
        answer = (
            f"There "
            f"{'is' if count == 1 else 'are'} "
            f"{count} enterprise {noun}."
        )

    return result(
        question,
        answer,
        inventory,
        entity_type,
    )


# ==========================================
# Platform Span Answer
# ==========================================

def answer_platform_span(
    question: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    applications = inventory[
        "applications"
    ]

    counts = Counter(
        detect_application_platform(
            application
        )
        for application in applications
    )

    known_platforms = sorted(
        platform
        for platform in counts
        if platform != "Other"
    )

    if not known_platforms:
        answer = (
            "No recognizable application platform "
            "values were returned by Microsoft Graph."
        )

    else:
        summary = ", ".join(
            f"{platform} ({counts[platform]})"
            for platform in known_platforms
        )

        answer = (
            f"The applications span "
            f"{len(known_platforms)} "
            f"{'platform' if len(known_platforms) == 1 else 'platforms'}: "
            f"{summary}."
        )

        unknown = counts.get(
            "Other",
            0,
        )

        if unknown:
            answer += (
                f" {unknown} application "
                f"{'has' if unknown == 1 else 'have'} "
                "an unknown platform."
            )

    return result(
        question,
        answer,
        inventory,
        "application",
    )


# ==========================================
# Superlative Answers
# ==========================================

def record_name(
    entity_type: str,
    record: dict[str, Any],
) -> str:
    keys = {
        "user": (
            "displayName",
            "userPrincipalName",
            "mail",
        ),

        "application": (
            "displayName",
            "name",
        ),

        "device": (
            "deviceName",
            "managedDeviceName",
        ),
    }[
        entity_type
    ]

    return str(
        first_present(
            record,
            *keys,
        )
        or f"Unknown {entity_type}"
    )


def answer_superlative(
    question: str,
    entity_type: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_text(
        question
    )

    records = entity_records(
        inventory,
        entity_type,
    )

    if not records:
        return result(
            question,
            (
                f"No enterprise "
                f"{ENTITY_LABELS[entity_type][1]} "
                "were returned by Microsoft Graph."
            ),
            inventory,
            entity_type,
        )

    if re.search(
        r"\b(oldest|earliest)\b",
        normalized,
    ):
        reverse = False
        description = "oldest"

    elif re.search(
        r"\b(newest|latest|most recent)\b",
        normalized,
    ):
        reverse = True
        description = "newest"

    elif (
        entity_type == "application"
        and re.search(
            r"\b(largest|biggest|smallest)\b",
            normalized,
        )
    ):
        reverse = not bool(
            re.search(
                r"\bsmallest\b",
                normalized,
            )
        )

        description = (
            "largest"
            if reverse
            else "smallest"
        )

        candidates: list[
            tuple[
                float,
                dict[str, Any],
            ]
        ] = []

        for record in records:
            size = application_size(
                record
            )

            if size is not None:
                candidates.append(
                    (
                        size,
                        record,
                    )
                )

        if not candidates:
            return result(
                question,
                (
                    f"The {description} application "
                    "cannot be determined because "
                    "Microsoft Graph did not return a "
                    "usable size for the applications."
                ),
                inventory,
                entity_type,
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=reverse,
        )

        size, selected = candidates[0]

        return result(
            question,
            (
                f"The {description} application is "
                f"{record_name(entity_type, selected)}, "
                f"with a recorded size of "
                f"{format_size(size)}."
            ),
            inventory,
            entity_type,
        )

    else:
        return result(
            question,
            (
                "That comparison is not supported "
                "for this live inventory question."
            ),
            inventory,
            entity_type,
        )

    date_keys = {
        "user": (
            "createdDateTime",
            "created_date_time",
        ),

        "application": (
            "createdDateTime",
            "created_date_time",
        ),

        "device": (
            "enrolledDateTime",
            "enrolled_date_time",
        ),
    }[
        entity_type
    ]

    dated_records: list[
        tuple[
            datetime,
            dict[str, Any],
        ]
    ] = []

    for record in records:
        raw_date = first_present(
            record,
            *date_keys,
        )

        parsed = parse_graph_datetime(
            raw_date
        )

        if parsed is not None:
            dated_records.append(
                (
                    parsed,
                    record,
                )
            )

    if not dated_records:
        return result(
            question,
            (
                f"The {description} "
                f"{ENTITY_LABELS[entity_type][0]} "
                "cannot be determined because "
                "Microsoft Graph did not return a "
                "usable date for these records."
            ),
            inventory,
            entity_type,
        )

    dated_records.sort(
        key=lambda item: item[0],
        reverse=reverse,
    )

    selected_date, selected = (
        dated_records[0]
    )

    formatted_date = format_graph_date(
        selected_date
    ) or "an unknown date"

    date_action = (
        "enrolled"
        if entity_type == "device"
        else "created"
    )

    return result(
        question,
        (
            f"The {description} "
            f"{ENTITY_LABELS[entity_type][0]} is "
            f"{record_name(entity_type, selected)}, "
            f"{date_action} on {formatted_date}."
        ),
        inventory,
        entity_type,
    )


# ==========================================
# Concise Listings
# ==========================================

def format_user(
    user: dict[str, Any],
) -> str:
    name = record_name(
        "user",
        user,
    )

    email = first_present(
        user,
        "mail",
        "userPrincipalName",
    )

    parts = [
        name,
        user_status(
            user
        ),
    ]

    if not is_missing(
        email
    ):
        parts.insert(
            1,
            str(email),
        )

    return (
        "- "
        + " — ".join(
            parts
        )
    )


def format_application(
    application: dict[str, Any],
) -> str:
    name = record_name(
        "application",
        application,
    )

    publisher = first_present(
        application,
        "publisher",
    )

    parts = [
        name,
    ]

    if not is_missing(
        publisher
    ):
        parts.append(
            str(publisher)
        )

    parts.append(
        detect_application_platform(
            application
        )
    )

    return (
        "- "
        + " — ".join(
            parts
        )
    )


def format_device(
    device: dict[str, Any],
) -> str:
    name = record_name(
        "device",
        device,
    )

    operating_system = first_present(
        device,
        "operatingSystem",
        "operating_system",
    )

    compliance = normalize_compliance(
        first_present(
            device,
            "complianceState",
            "compliance_state",
        )
    )

    parts = [
        name,
    ]

    if not is_missing(
        operating_system
    ):
        parts.append(
            str(
                operating_system
            )
        )

    parts.append(
        compliance
    )

    return (
        "- "
        + " — ".join(
            parts
        )
    )


def answer_list(
    question: str,
    entity_type: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    records = entity_records(
        inventory,
        entity_type,
    )

    filtered, description = (
        filter_entity_records(
            question,
            entity_type,
            records,
        )
    )

    if not filtered:
        suffix = (
            f" {description}"
            if description
            else ""
        )

        return result(
            question,
            (
                f"No enterprise "
                f"{ENTITY_LABELS[entity_type][1]}"
                f"{suffix} were returned."
            ),
            inventory,
            entity_type,
        )

    formatter: Callable[
        [dict[str, Any]],
        str,
    ] = {
        "user":
            format_user,

        "application":
            format_application,

        "device":
            format_device,
    }[
        entity_type
    ]

    heading = (
        ENTITY_LABELS[
            entity_type
        ][1]
        .capitalize()
    )

    if description:
        heading += (
            f" {description}"
        )

    lines = [
        formatter(
            record
        )
        for record in filtered
    ]

    answer = (
        f"{heading} ({len(filtered)}):\n"
        + "\n".join(
            lines
        )
    )

    return result(
        question,
        answer,
        inventory,
        entity_type,
    )


# ==========================================
# Exact Named Record Details
# ==========================================

def format_user_detail(
    user: dict[str, Any],
) -> str:
    name = record_name(
        "user",
        user,
    )

    lines = [
        f"**{name}**",
        f"- **Status:** {user_status(user)}",
    ]

    fields = (
        (
            "Email",
            first_present(
                user,
                "mail",
                "userPrincipalName",
            ),
        ),

        (
            "Mobile phone",
            user_phone(
                user
            ),
        ),

        (
            "Department",
            first_present(
                user,
                "department",
            ),
        ),

        (
            "Job title",
            first_present(
                user,
                "jobTitle",
            ),
        ),

        (
            "Office",
            first_present(
                user,
                "officeLocation",
            ),
        ),

        (
            "Created",
            format_graph_date(
                first_present(
                    user,
                    "createdDateTime",
                )
            ),
        ),
    )

    for label, value in fields:
        if not is_missing(
            value
        ):
            lines.append(
                f"- **{label}:** {value}"
            )

    return "\n".join(
        lines
    )


def format_application_detail(
    application: dict[str, Any],
) -> str:
    name = record_name(
        "application",
        application,
    )

    lines = [
        f"**{name}**",
        (
            "- **Platform:** "
            f"{detect_application_platform(application)}"
        ),
    ]

    fields = (
        (
            "Publisher",
            first_present(
                application,
                "publisher",
            ),
        ),

        (
            "Publishing state",
            first_present(
                application,
                "publishingState",
            ),
        ),

        (
            "Assigned",
            (
                "Yes"
                if parse_boolean(
                    first_present(
                        application,
                        "isAssigned",
                    )
                )
                is True
                else (
                    "No"
                    if parse_boolean(
                        first_present(
                            application,
                            "isAssigned",
                        )
                    )
                    is False
                    else None
                )
            ),
        ),

        (
            "Developer",
            first_present(
                application,
                "developer",
            ),
        ),

        (
            "Owner",
            first_present(
                application,
                "owner",
            ),
        ),

        (
            "Created",
            format_graph_date(
                first_present(
                    application,
                    "createdDateTime",
                )
            ),
        ),

        (
            "Last modified",
            format_graph_date(
                first_present(
                    application,
                    "lastModifiedDateTime",
                )
            ),
        ),

        (
            "Notes",
            application_notes(
                application
            ),
        ),
    )

    for label, value in fields:
        if not is_missing(
            value
        ):
            lines.append(
                f"- **{label}:** {value}"
            )

    return "\n".join(
        lines
    )


def format_device_detail(
    device: dict[str, Any],
) -> str:
    name = record_name(
        "device",
        device,
    )

    lines = [
        f"**{name}**",
    ]

    fields = (
        (
            "User",
            first_present(
                device,
                "userDisplayName",
                "userPrincipalName",
            ),
        ),

        (
            "Operating system",
            first_present(
                device,
                "operatingSystem",
            ),
        ),

        (
            "OS version",
            first_present(
                device,
                "osVersion",
            ),
        ),

        (
            "Compliance",
            normalize_compliance(
                first_present(
                    device,
                    "complianceState",
                )
            ),
        ),

        (
            "Management state",
            first_present(
                device,
                "managementState",
            ),
        ),

        (
            "Manufacturer",
            first_present(
                device,
                "manufacturer",
            ),
        ),

        (
            "Model",
            first_present(
                device,
                "model",
            ),
        ),

        (
            "Enrolled",
            format_graph_date(
                first_present(
                    device,
                    "enrolledDateTime",
                )
            ),
        ),

        (
            "Last sync",
            format_graph_date(
                first_present(
                    device,
                    "lastSyncDateTime",
                )
            ),
        ),
    )

    for label, value in fields:
        if not is_missing(
            value
        ):
            lines.append(
                f"- **{label}:** {value}"
            )

    return "\n".join(
        lines
    )


def answer_named_record(
    question: str,
    inventory: dict[str, Any],
    entity_hint: str | None = None,
) -> dict[str, Any]:
    lookup = find_live_record(
        question=question,
        entity_type=entity_hint,
        inventory=inventory,
    )

    status = lookup[
        "status"
    ]

    if status == "not_found":
        return result(
            question,
            (
                "No exact live Microsoft Graph record "
                "matched that name."
            ),
            inventory,
            entity_hint,
        )

    if status == "ambiguous":
        names = sorted({
            record_name(
                match[
                    "entity_type"
                ],
                match[
                    "record"
                ],
            )
            for match in lookup[
                "matches"
            ]
        })

        return result(
            question,
            (
                "That name matches multiple records: "
                + ", ".join(
                    names
                )
                + ". Use a more specific name."
            ),
            inventory,
            entity_hint,
        )

    match = lookup[
        "match"
    ]

    entity_type = match[
        "entity_type"
    ]

    record = match[
        "record"
    ]

    formatter = {
        "user":
            format_user_detail,

        "application":
            format_application_detail,

        "device":
            format_device_detail,
    }[
        entity_type
    ]

    return result(
        question,
        formatter(
            record
        ),
        inventory,
        entity_type,
    )


# ==========================================
# Live Query Eligibility
# ==========================================

def is_live_inventory_question(
    question: Any,
) -> bool:
    if is_named_record_question(
        question
    ):
        return True

    entity_type = detect_entity_type(
        question
    )

    if entity_type is None:
        return False

    normalized = normalize_text(
        question
    )

    return bool(
        is_count_question(
            question
        )
        or is_list_question(
            question
        )
        or is_superlative_question(
            question
        )
        or re.search(
            r"\b("
            r"enabled|disabled|"
            r"compliant|non[- ]?compliant|"
            r"published|unpublished|processing|"
            r"notes?|phone|mobile|"
            r"platform|publisher|version|"
            r"created|modified|assigned"
            r")\b",
            normalized,
        )
    )


# ==========================================
# Main Live Query Router
# ==========================================

def try_live_intune_query(
    question: Any,
) -> dict[str, Any] | None:
    cleaned_question = str(
        question or ""
    ).strip()

    if not cleaned_question:
        return None

    if not is_live_inventory_question(
        cleaned_question
    ):
        return None

    inventory = get_live_inventory()

    entity_type = detect_entity_type(
        cleaned_question
    )

    # Named lookups are checked before general
    # entity routes. This handles:
    #
    # "what about test-1?"
    #
    # even though no entity word is present.
    if is_named_record_question(
        cleaned_question
    ):
        return answer_named_record(
            cleaned_question,
            inventory,
            entity_type,
        )

    if is_platform_span_question(
        cleaned_question
    ):
        return answer_platform_span(
            cleaned_question,
            inventory,
        )

    if entity_type is None:
        return None

    if is_superlative_question(
        cleaned_question
    ):
        return answer_superlative(
            cleaned_question,
            entity_type,
            inventory,
        )

    if is_count_question(
        cleaned_question
    ):
        return answer_count(
            cleaned_question,
            entity_type,
            inventory,
        )

    if is_list_question(
        cleaned_question
    ):
        return answer_list(
            cleaned_question,
            entity_type,
            inventory,
        )

    # Questions such as "which users are disabled"
    # are treated as filtered listings.
    normalized = normalize_text(
        cleaned_question
    )

    if re.search(
        r"\b("
        r"enabled|disabled|"
        r"compliant|non[- ]?compliant|"
        r"published|unpublished|processing|"
        r"notes?|phone|mobile|platform|assigned"
        r")\b",
        normalized,
    ):
        return answer_list(
            cleaned_question,
            entity_type,
            inventory,
        )

    return None


# ==========================================
# Standalone Test
# ==========================================

if __name__ == "__main__":
    print(
        "\n======================================"
    )
    print(
        "Live Microsoft Graph Query Router"
    )
    print(
        "======================================"
    )
    print(
        "Type 'exit' to quit.\n"
    )

    while True:
        question = input(
            "Live Intune > "
        ).strip()

        if question.lower() == "exit":
            break

        if not question:
            continue

        try:
            response = (
                try_live_intune_query(
                    question
                )
            )

            if response is None:
                print(
                    "Not a supported live "
                    "inventory query.\n"
                )
                continue

            print(
                f"\n{response['answer']}\n"
            )

        except Exception as error:
            print(
                f"\nLive query error: {error}\n"
            )