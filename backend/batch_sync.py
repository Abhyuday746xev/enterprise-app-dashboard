from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from database import get_connection
from graph_batch import fetch_batch_data


# ============================================
# Environment Configuration
# ============================================

BACKEND_DIRECTORY = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIRECTORY / ".env"

load_dotenv(
    dotenv_path=ENV_FILE
)


# ============================================
# SQL Statements
# ============================================

APPLICATION_SQL = """
INSERT INTO mobile_apps
(
    id,
    display_name,
    publisher,
    app_type,
    publishing_state,
    file_name,
    size,
    display_version,
    developer,
    owner,
    created_date,
    last_modified_date,
    notes
)
VALUES
(
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    publisher = VALUES(publisher),
    app_type = VALUES(app_type),
    publishing_state = VALUES(publishing_state),
    file_name = VALUES(file_name),
    size = VALUES(size),
    display_version = VALUES(display_version),
    developer = VALUES(developer),
    owner = VALUES(owner),
    created_date = VALUES(created_date),
    last_modified_date = VALUES(last_modified_date),
    notes = VALUES(notes)
"""


USER_SQL = """
INSERT INTO users
(
    id,
    display_name,
    user_principal_name,
    mail,
    mobile_phone,
    account_enabled
)
VALUES
(
    %s, %s, %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    user_principal_name = VALUES(user_principal_name),
    mail = VALUES(mail),
    mobile_phone = VALUES(mobile_phone),
    account_enabled = VALUES(account_enabled)
"""


DEVICE_SQL = """
INSERT INTO managed_devices
(
    id,
    device_name,
    user_name,
    operating_system,
    os_version,
    manufacturer,
    model,
    compliance_state,
    last_sync
)
VALUES
(
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    device_name = VALUES(device_name),
    user_name = VALUES(user_name),
    operating_system = VALUES(operating_system),
    os_version = VALUES(os_version),
    manufacturer = VALUES(manufacturer),
    model = VALUES(model),
    compliance_state = VALUES(compliance_state),
    last_sync = VALUES(last_sync)
"""


# ============================================
# Configuration Helpers
# ============================================

def get_access_token() -> str:
    """
    Read the temporary Microsoft Graph access
    token from backend/.env.
    """

    access_token = os.getenv(
        "GRAPH_ACCESS_TOKEN",
        "",
    ).strip()

    if not access_token:
        raise RuntimeError(
            "GRAPH_ACCESS_TOKEN was not found.\n"
            f"Expected environment file: {ENV_FILE}"
        )

    if access_token.lower().startswith("bearer "):
        access_token = access_token[7:].strip()

    if not access_token:
        raise RuntimeError(
            "GRAPH_ACCESS_TOKEN is empty."
        )

    return access_token


# ============================================
# General Data Helpers
# ============================================

def first_present(
    record: dict[str, Any],
    *keys: str,
) -> Any:
    """
    Return the first value that is not None
    or an empty string.
    """

    for key in keys:
        value = record.get(key)

        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return None


def normalize_graph_type(value: Any) -> str | None:
    """
    Convert:

    #microsoft.graph.win32LobApp

    into:

    win32LobApp
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    prefixes = (
        "#microsoft.graph.",
        "microsoft.graph.",
    )

    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):]

    return text


def parse_graph_datetime(value: Any) -> datetime | None:
    """
    Parse a Microsoft Graph ISO-8601 timestamp.

    MySQL DATETIME values are stored as naive UTC
    datetime objects.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError(
                f"Invalid Microsoft Graph datetime: {value}"
            ) from error

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(
            timezone.utc
        ).replace(
            tzinfo=None
        )

    return parsed


def require_record_id(
    record: dict[str, Any],
    entity_name: str,
) -> str:
    record_id = str(
        record.get("id") or ""
    ).strip()

    if not record_id:
        display_name = first_present(
            record,
            "displayName",
            "deviceName",
            "userPrincipalName",
        )

        raise ValueError(
            f"{entity_name} record has no ID: "
            f"{display_name or 'unknown record'}"
        )

    return record_id


def deduplicate_by_id(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Remove duplicate Graph objects using their ID.
    The last object with a given ID is retained.
    """

    unique_records: dict[
        str,
        dict[str, Any],
    ] = {}

    for record in records:
        if not isinstance(record, dict):
            continue

        record_id = str(
            record.get("id") or ""
        ).strip()

        if not record_id:
            raise ValueError(
                "Microsoft Graph returned a record "
                "without an ID."
            )

        unique_records[record_id] = record

    return list(
        unique_records.values()
    )


# ============================================
# Application Data Preparation
# ============================================

def prepare_application_rows(
    applications: Iterable[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    rows = []

    for app in applications:
        app_id = require_record_id(
            app,
            "Application",
        )

        # These fields exist only for some
        # application subtypes. They remain NULL
        # when Graph does not provide them.
        file_name = first_present(
            app,
            "fileName",
            "filename",
            "setupFilePath",
        )

        size = first_present(
            app,
            "size",
            "sizeInBytes",
            "committedContentVersion",
        )

        display_version = first_present(
            app,
            "displayVersion",
            "versionNumber",
            "identityVersion",
            "version",
        )

        rows.append(
            (
                app_id,
                first_present(
                    app,
                    "displayName",
                    "name",
                ),
                app.get("publisher"),
                normalize_graph_type(
                    app.get("@odata.type")
                ),
                app.get("publishingState"),
                file_name,
                size,
                display_version,
                app.get("developer"),
                app.get("owner"),
                parse_graph_datetime(
                    app.get("createdDateTime")
                ),
                parse_graph_datetime(
                    app.get("lastModifiedDateTime")
                ),
                app.get("notes"),
            )
        )

    return rows


# ============================================
# User Data Preparation
# ============================================

def prepare_user_rows(
    users: Iterable[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    rows = []

    for user in users:
        user_id = require_record_id(
            user,
            "User",
        )

        user_principal_name = first_present(
            user,
            "userPrincipalName",
        )

        mail = first_present(
            user,
            "mail",
            "userPrincipalName",
        )

        # Do not replace missing phone numbers
        # with the text "N/A". Store SQL NULL.
        mobile_phone = first_present(
            user,
            "mobilePhone",
        )

        # Do not use False as a default.
        # Missing status must remain unknown.
        account_enabled = (
            user.get("accountEnabled")
            if "accountEnabled" in user
            else None
        )

        rows.append(
            (
                user_id,
                first_present(
                    user,
                    "displayName",
                    "userPrincipalName",
                ),
                user_principal_name,
                mail,
                mobile_phone,
                account_enabled,
            )
        )

    return rows


# ============================================
# Device Data Preparation
# ============================================

def prepare_device_rows(
    devices: Iterable[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    rows = []

    for device in devices:
        device_id = require_record_id(
            device,
            "Device",
        )

        # userDisplayName is preferred.
        # userPrincipalName is used when the display
        # name was not requested or is unavailable.
        user_name = first_present(
            device,
            "userDisplayName",
            "userPrincipalName",
        )

        rows.append(
            (
                device_id,
                first_present(
                    device,
                    "deviceName",
                    "managedDeviceName",
                ),
                user_name,
                device.get("operatingSystem"),
                device.get("osVersion"),
                device.get("manufacturer"),
                device.get("model"),
                device.get("complianceState"),
                parse_graph_datetime(
                    device.get("lastSyncDateTime")
                ),
            )
        )

    return rows


# ============================================
# Database Synchronization
# ============================================

def execute_table_sync(
    cursor: Any,
    table_name: str,
    insert_sql: str,
    rows: list[tuple[Any, ...]],
) -> None:
    """
    Replace one table inside the current database
    transaction.

    A later failure causes the outer transaction
    to roll back, restoring the previous data.
    """

    cursor.execute(
        f"DELETE FROM {table_name}"
    )

    if rows:
        cursor.executemany(
            insert_sql,
            rows,
        )


def validate_graph_results(
    applications: list[dict[str, Any]],
    users: list[dict[str, Any]],
    devices: list[dict[str, Any]],
) -> None:
    """
    Prevent an accidental full database wipe when
    every Graph collection is unexpectedly empty.
    """

    if applications or users or devices:
        return

    allow_empty_sync = (
        os.getenv(
            "ALLOW_EMPTY_SYNC",
            "false",
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
        }
    )

    if not allow_empty_sync:
        raise RuntimeError(
            "Microsoft Graph returned zero applications, "
            "zero users and zero devices. Synchronization "
            "was stopped to protect the existing database. "
            "Set ALLOW_EMPTY_SYNC=true only when an empty "
            "tenant is expected."
        )


# ============================================
# Main Synchronization
# ============================================

def synchronize_enterprise_data() -> dict[str, int]:
    access_token = get_access_token()

    print(
        "Fetching live data from Microsoft Graph..."
    )

    applications, users, devices = fetch_batch_data(
        access_token
    )

    applications = deduplicate_by_id(
        applications
    )

    users = deduplicate_by_id(
        users
    )

    devices = deduplicate_by_id(
        devices
    )

    validate_graph_results(
        applications,
        users,
        devices,
    )

    print(
        "\n========== GRAPH SUMMARY ==========\n"
    )

    print(
        f"Applications : {len(applications)}"
    )

    print(
        f"Users        : {len(users)}"
    )

    print(
        f"Devices      : {len(devices)}"
    )

    print(
        "\nPreparing database records..."
    )

    application_rows = prepare_application_rows(
        applications
    )

    user_rows = prepare_user_rows(
        users
    )

    device_rows = prepare_device_rows(
        devices
    )

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        print(
            "Connected to MySQL"
        )

        # All three replacements run inside the
        # same transaction. Any failure rolls back
        # the complete synchronization.
        print(
            "\nSyncing applications..."
        )

        execute_table_sync(
            cursor=cursor,
            table_name="mobile_apps",
            insert_sql=APPLICATION_SQL,
            rows=application_rows,
        )

        print(
            f"Applications synced: "
            f"{len(application_rows)}"
        )

        print(
            "\nSyncing users..."
        )

        execute_table_sync(
            cursor=cursor,
            table_name="users",
            insert_sql=USER_SQL,
            rows=user_rows,
        )

        print(
            f"Users synced: {len(user_rows)}"
        )

        print(
            "\nSyncing devices..."
        )

        execute_table_sync(
            cursor=cursor,
            table_name="managed_devices",
            insert_sql=DEVICE_SQL,
            rows=device_rows,
        )

        print(
            f"Devices synced: {len(device_rows)}"
        )

        connection.commit()

        print(
            "\n==================================="
        )

        print(
            "Enterprise Synchronization Complete"
        )

        print(
            "==================================="
        )

        return {
            "applications":
                len(application_rows),

            "users":
                len(user_rows),

            "devices":
                len(device_rows),
        }

    except Exception:
        if connection is not None:
            connection.rollback()

        print(
            "\nSynchronization failed."
        )

        print(
            "All database changes were rolled back."
        )

        raise

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# ============================================
# Standalone Execution
# ============================================

if __name__ == "__main__":
    synchronize_enterprise_data()