from __future__ import annotations

# ==========================================
# Persistent Control Panel Audit Log
# ==========================================
#
# Stores protected Control Panel activity in
# MySQL using fixed, parameterized statements.
#
# This module does not execute Microsoft Graph
# operations and does not accept arbitrary SQL.
#
# ==========================================

import json
import secrets
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from database import get_connection


# ==========================================
# Configuration
# ==========================================

AUDIT_TABLE_NAME = (
    "control_panel_audit_log"
)

_table_lock = threading.Lock()
_table_ready = False


# ==========================================
# Exceptions
# ==========================================

class AuditLogError(
    RuntimeError
):
    """Raised when an audit-log operation fails."""


# ==========================================
# Serialization
# ==========================================

def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def json_default(
    value: Any,
) -> Any:
    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        bytes,
    ):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    if hasattr(
        value,
        "to_public_dict",
    ):
        return value.to_public_dict()

    if hasattr(
        value,
        "to_dict",
    ):
        return value.to_dict()

    return str(
        value
    )


def serialize_json(
    value: Any,
) -> str | None:
    if value is None:
        return None

    try:
        return json.dumps(
            value,
            default=json_default,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise AuditLogError(
            "Audit data could not be serialized."
        ) from error


def deserialize_json(
    value: Any,
) -> Any:
    if value in {
        None,
        "",
    }:
        return None

    if isinstance(
        value,
        (
            dict,
            list,
        ),
    ):
        return value

    try:
        return json.loads(
            str(value)
        )

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return value


# ==========================================
# Validation
# ==========================================

def optional_text(
    value: Any,
    *,
    maximum_length: int,
) -> str | None:
    if value is None:
        return None

    cleaned = str(
        value
    ).strip()

    if not cleaned:
        return None

    if len(cleaned) > maximum_length:
        raise ValueError(
            "Audit field is too long."
        )

    return cleaned


def required_text(
    value: Any,
    field_name: str,
    *,
    maximum_length: int,
) -> str:
    cleaned = optional_text(
        value,
        maximum_length=maximum_length,
    )

    if cleaned is None:
        raise ValueError(
            f"{field_name} is required."
        )

    return cleaned


def validate_limit(
    value: Any,
) -> int:
    try:
        limit = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "limit must be an integer."
        ) from error

    if limit <= 0:
        raise ValueError(
            "limit must be greater than zero."
        )

    return min(
        limit,
        500,
    )


# ==========================================
# Database Setup
# ==========================================

def ensure_audit_table() -> None:
    global _table_ready

    if _table_ready:
        return

    with _table_lock:
        if _table_ready:
            return

        connection = None
        cursor = None

        try:
            connection = get_connection()
            cursor = connection.cursor()

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS
                {AUDIT_TABLE_NAME}
                (
                    id BIGINT UNSIGNED
                        NOT NULL
                        AUTO_INCREMENT,

                    event_id VARCHAR(64)
                        NOT NULL,

                    action_id VARCHAR(64)
                        NULL,

                    confirmation_id VARCHAR(256)
                        NULL,

                    actor VARCHAR(512)
                        NULL,

                    event_type VARCHAR(100)
                        NOT NULL,

                    action_type VARCHAR(100)
                        NULL,

                    target_type VARCHAR(100)
                        NULL,

                    target_id VARCHAR(512)
                        NULL,

                    target_name VARCHAR(512)
                        NULL,

                    status VARCHAR(100)
                        NOT NULL,

                    risk VARCHAR(50)
                        NULL,

                    request_data LONGTEXT
                        NULL,

                    result_data LONGTEXT
                        NULL,

                    error_message TEXT
                        NULL,

                    created_at TIMESTAMP(6)
                        NOT NULL
                        DEFAULT CURRENT_TIMESTAMP(6),

                    PRIMARY KEY (id),

                    UNIQUE KEY
                        uq_control_audit_event_id
                        (event_id),

                    KEY
                        idx_control_audit_action_id
                        (action_id),

                    KEY
                        idx_control_audit_status
                        (status),

                    KEY
                        idx_control_audit_action_type
                        (action_type),

                    KEY
                        idx_control_audit_created_at
                        (created_at)
                )
                ENGINE=InnoDB
                DEFAULT CHARSET=utf8mb4
                COLLATE=utf8mb4_unicode_ci
            """)

            connection.commit()
            _table_ready = True

        except Exception as error:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass

            raise AuditLogError(
                "Could not initialize the Control "
                "Panel audit table."
            ) from error

        finally:
            if cursor is not None:
                cursor.close()

            if (
                connection is not None
                and connection.is_connected()
            ):
                connection.close()


# ==========================================
# Write Audit Event
# ==========================================

def record_audit_event(
    *,
    event_type: Any,
    status: Any,
    actor: Any = None,
    action_id: Any = None,
    confirmation_id: Any = None,
    action_type: Any = None,
    target_type: Any = None,
    target_id: Any = None,
    target_name: Any = None,
    risk: Any = None,
    request_data: Any = None,
    result_data: Any = None,
    error_message: Any = None,
) -> dict[str, Any]:
    ensure_audit_table()

    event_id = (
        "EVT-"
        + secrets.token_hex(
            12
        ).upper()
    )

    cleaned_event_type = required_text(
        event_type,
        "event_type",
        maximum_length=100,
    )

    cleaned_status = required_text(
        status,
        "status",
        maximum_length=100,
    )

    values = {
        "event_id":
            event_id,

        "action_id":
            optional_text(
                action_id,
                maximum_length=64,
            ),

        "confirmation_id":
            optional_text(
                confirmation_id,
                maximum_length=256,
            ),

        "actor":
            optional_text(
                actor,
                maximum_length=512,
            ),

        "event_type":
            cleaned_event_type,

        "action_type":
            optional_text(
                action_type,
                maximum_length=100,
            ),

        "target_type":
            optional_text(
                target_type,
                maximum_length=100,
            ),

        "target_id":
            optional_text(
                target_id,
                maximum_length=512,
            ),

        "target_name":
            optional_text(
                target_name,
                maximum_length=512,
            ),

        "status":
            cleaned_status,

        "risk":
            optional_text(
                risk,
                maximum_length=50,
            ),

        "request_data":
            serialize_json(
                request_data
            ),

        "result_data":
            serialize_json(
                result_data
            ),

        "error_message":
            optional_text(
                error_message,
                maximum_length=65535,
            ),
    }

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            f"""
                INSERT INTO
                    {AUDIT_TABLE_NAME}
                (
                    event_id,
                    action_id,
                    confirmation_id,
                    actor,
                    event_type,
                    action_type,
                    target_type,
                    target_id,
                    target_name,
                    status,
                    risk,
                    request_data,
                    result_data,
                    error_message
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """,
            (
                values["event_id"],
                values["action_id"],
                values["confirmation_id"],
                values["actor"],
                values["event_type"],
                values["action_type"],
                values["target_type"],
                values["target_id"],
                values["target_name"],
                values["status"],
                values["risk"],
                values["request_data"],
                values["result_data"],
                values["error_message"],
            ),
        )

        connection.commit()

        return {
            **values,
            "created_at":
                utc_now().isoformat(),
        }

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        raise AuditLogError(
            "Could not write the Control "
            "Panel audit event."
        ) from error

    finally:
        if cursor is not None:
            cursor.close()

        if (
            connection is not None
            and connection.is_connected()
        ):
            connection.close()


# ==========================================
# Read Audit Events
# ==========================================

def list_audit_events(
    *,
    limit: Any = 100,
    status: Any = None,
    action_type: Any = None,
    actor: Any = None,
) -> list[dict[str, Any]]:
    ensure_audit_table()

    safe_limit = validate_limit(
        limit
    )

    conditions: list[str] = []
    parameters: list[Any] = []

    cleaned_status = optional_text(
        status,
        maximum_length=100,
    )

    cleaned_action_type = optional_text(
        action_type,
        maximum_length=100,
    )

    cleaned_actor = optional_text(
        actor,
        maximum_length=512,
    )

    if cleaned_status:
        conditions.append(
            "status = %s"
        )

        parameters.append(
            cleaned_status
        )

    if cleaned_action_type:
        conditions.append(
            "action_type = %s"
        )

        parameters.append(
            cleaned_action_type
        )

    if cleaned_actor:
        conditions.append(
            "actor = %s"
        )

        parameters.append(
            cleaned_actor
        )

    where_clause = (
        " WHERE "
        + " AND ".join(
            conditions
        )
        if conditions
        else ""
    )

    query = f"""
        SELECT
            id,
            event_id,
            action_id,
            confirmation_id,
            actor,
            event_type,
            action_type,
            target_type,
            target_id,
            target_name,
            status,
            risk,
            request_data,
            result_data,
            error_message,
            created_at
        FROM
            {AUDIT_TABLE_NAME}
        {where_clause}
        ORDER BY
            id DESC
        LIMIT %s
    """

    parameters.append(
        safe_limit
    )

    connection = None
    cursor = None

    try:
        connection = get_connection()

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            query,
            tuple(
                parameters
            ),
        )

        rows = list(
            cursor.fetchall()
        )

        for row in rows:
            row["request_data"] = (
                deserialize_json(
                    row.get(
                        "request_data"
                    )
                )
            )

            row["result_data"] = (
                deserialize_json(
                    row.get(
                        "result_data"
                    )
                )
            )

            created_at = row.get(
                "created_at"
            )

            if isinstance(
                created_at,
                datetime,
            ):
                row["created_at"] = (
                    created_at.isoformat()
                )

        return rows

    except Exception as error:
        raise AuditLogError(
            "Could not read the Control "
            "Panel audit log."
        ) from error

    finally:
        if cursor is not None:
            cursor.close()

        if (
            connection is not None
            and connection.is_connected()
        ):
            connection.close()


def get_audit_event(
    event_id: Any,
) -> dict[str, Any] | None:
    ensure_audit_table()

    cleaned_event_id = required_text(
        event_id,
        "event_id",
        maximum_length=64,
    )

    connection = None
    cursor = None

    try:
        connection = get_connection()

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            f"""
                SELECT
                    id,
                    event_id,
                    action_id,
                    confirmation_id,
                    actor,
                    event_type,
                    action_type,
                    target_type,
                    target_id,
                    target_name,
                    status,
                    risk,
                    request_data,
                    result_data,
                    error_message,
                    created_at
                FROM
                    {AUDIT_TABLE_NAME}
                WHERE
                    event_id = %s
                LIMIT 1
            """,
            (
                cleaned_event_id,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        row["request_data"] = deserialize_json(
            row.get(
                "request_data"
            )
        )

        row["result_data"] = deserialize_json(
            row.get(
                "result_data"
            )
        )

        created_at = row.get(
            "created_at"
        )

        if isinstance(
            created_at,
            datetime,
        ):
            row["created_at"] = (
                created_at.isoformat()
            )

        return row

    except Exception as error:
        raise AuditLogError(
            "Could not read the requested "
            "Control Panel audit event."
        ) from error

    finally:
        if cursor is not None:
            cursor.close()

        if (
            connection is not None
            and connection.is_connected()
        ):
            connection.close()