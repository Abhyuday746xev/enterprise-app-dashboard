# ==========================================
# Enterprise Ticket Service
# ==========================================

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from flask import Blueprint, jsonify, request

from database import get_connection


# All routes in this file will start with /api
ticket_bp = Blueprint(
    "ticket_service",
    __name__,
    url_prefix="/api"
)


# ==========================================
# Allowed Values
# ==========================================

ALLOWED_PRIORITIES = {
    "Low",
    "Medium",
    "High",
    "Critical"
}

ALLOWED_STATUSES = {
    "Open",
    "In Progress",
    "Pending",
    "Resolved",
    "Closed"
}

ALLOWED_ENTITY_TYPES = {
    "general",
    "user",
    "application",
    "device"
}


# ==========================================
# General Helpers
# ==========================================

def clean_text(
    value,
    default="",
    maximum_length=None
):
    """
    Convert a value to a trimmed string.
    """

    if value is None:
        value = default

    value = str(value).strip()

    if maximum_length is not None:
        value = value[:maximum_length]

    return value


def serialize_value(value):
    """
    Convert database values into JSON-safe values.
    """

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    return value


def serialize_row(row):
    """
    Convert every value in a database row into
    a JSON-safe representation.
    """

    if row is None:
        return None

    return {
        key: serialize_value(value)
        for key, value in row.items()
    }


def generate_ticket_number():
    """
    Example:
    TKT-20260730-A1B2C3D4
    """

    date_part = datetime.now().strftime("%Y%m%d")
    random_part = uuid4().hex[:8].upper()

    return f"TKT-{date_part}-{random_part}"


def get_ticket_record(
    cursor,
    ticket_number
):
    """
    Retrieve one ticket using its public ticket number.
    """

    cursor.execute(
        """
        SELECT
            id,
            ticket_number,
            title,
            description,
            category,
            priority,
            status,
            requester_name,
            requester_email,
            assigned_to,
            related_entity_type,
            related_entity_id,
            created_at,
            updated_at,
            resolved_at
        FROM tickets
        WHERE ticket_number = %s
        """,
        (ticket_number,)
    )

    return cursor.fetchone()


# ==========================================
# Ticket Statistics
# ==========================================

@ticket_bp.route(
    "/tickets/stats",
    methods=["GET"]
)
def get_ticket_statistics():

    conn = None
    cursor = None

    try:

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,

                SUM(
                    CASE
                        WHEN status = 'Open'
                        THEN 1
                        ELSE 0
                    END
                ) AS open_count,

                SUM(
                    CASE
                        WHEN status = 'In Progress'
                        THEN 1
                        ELSE 0
                    END
                ) AS in_progress_count,

                SUM(
                    CASE
                        WHEN status = 'Pending'
                        THEN 1
                        ELSE 0
                    END
                ) AS pending_count,

                SUM(
                    CASE
                        WHEN status = 'Resolved'
                        THEN 1
                        ELSE 0
                    END
                ) AS resolved_count,

                SUM(
                    CASE
                        WHEN status = 'Closed'
                        THEN 1
                        ELSE 0
                    END
                ) AS closed_count,

                SUM(
                    CASE
                        WHEN priority = 'Critical'
                        THEN 1
                        ELSE 0
                    END
                ) AS critical_count,

                SUM(
                    CASE
                        WHEN priority = 'High'
                        THEN 1
                        ELSE 0
                    END
                ) AS high_count

            FROM tickets
            """
        )

        statistics = cursor.fetchone() or {}

        # SUM returns NULL when the table is empty.
        for key, value in statistics.items():

            if value is None:
                statistics[key] = 0

        return jsonify({
            "success": True,
            "statistics": serialize_row(
                statistics
            )
        }), 200

    except Exception as error:

        return jsonify({
            "success": False,
            "message": "Could not load ticket statistics.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ==========================================
# List Tickets
# ==========================================

@ticket_bp.route(
    "/tickets",
    methods=["GET"]
)
def get_tickets():

    conn = None
    cursor = None

    try:

        search = clean_text(
            request.args.get("search")
        )

        status = clean_text(
            request.args.get("status")
        )

        priority = clean_text(
            request.args.get("priority")
        )

        category = clean_text(
            request.args.get("category")
        )

        assigned_to = clean_text(
            request.args.get("assigned_to")
        )

        try:
            page = max(
                int(request.args.get("page", 1)),
                1
            )
        except (TypeError, ValueError):
            page = 1

        try:
            limit = int(
                request.args.get("limit", 25)
            )
        except (TypeError, ValueError):
            limit = 25

        limit = max(
            1,
            min(limit, 100)
        )

        offset = (page - 1) * limit

        conditions = []
        parameters = []

        if status:

            if status not in ALLOWED_STATUSES:

                return jsonify({
                    "success": False,
                    "message": "Invalid ticket status."
                }), 400

            conditions.append(
                "status = %s"
            )

            parameters.append(status)

        if priority:

            if priority not in ALLOWED_PRIORITIES:

                return jsonify({
                    "success": False,
                    "message": "Invalid ticket priority."
                }), 400

            conditions.append(
                "priority = %s"
            )

            parameters.append(priority)

        if category:

            conditions.append(
                "category = %s"
            )

            parameters.append(category)

        if assigned_to:

            conditions.append(
                "assigned_to = %s"
            )

            parameters.append(assigned_to)

        if search:

            search_value = f"%{search}%"

            conditions.append(
                """
                (
                    ticket_number LIKE %s
                    OR title LIKE %s
                    OR description LIKE %s
                    OR requester_name LIKE %s
                    OR requester_email LIKE %s
                    OR assigned_to LIKE %s
                )
                """
            )

            parameters.extend([
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            ])

        where_clause = ""

        if conditions:

            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        # Count matching tickets.
        count_query = f"""
            SELECT COUNT(*) AS total
            FROM tickets
            {where_clause}
        """

        cursor.execute(
            count_query,
            tuple(parameters)
        )

        total = int(
            cursor.fetchone()["total"]
        )

        # Retrieve matching tickets.
        ticket_query = f"""
            SELECT
                id,
                ticket_number,
                title,
                description,
                category,
                priority,
                status,
                requester_name,
                requester_email,
                assigned_to,
                related_entity_type,
                related_entity_id,
                created_at,
                updated_at,
                resolved_at
            FROM tickets
            {where_clause}
            ORDER BY
                FIELD(
                    priority,
                    'Critical',
                    'High',
                    'Medium',
                    'Low'
                ),
                created_at DESC
            LIMIT %s
            OFFSET %s
        """

        query_parameters = (
            parameters
            + [limit, offset]
        )

        cursor.execute(
            ticket_query,
            tuple(query_parameters)
        )

        tickets = [
            serialize_row(ticket)
            for ticket in cursor.fetchall()
        ]

        total_pages = (
            (total + limit - 1) // limit
            if total > 0
            else 0
        )

        return jsonify({
            "success": True,
            "tickets": tickets,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages
            }
        }), 200

    except Exception as error:

        return jsonify({
            "success": False,
            "message": "Could not load tickets.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ==========================================
# Get One Ticket
# ==========================================

@ticket_bp.route(
    "/tickets/<string:ticket_number>",
    methods=["GET"]
)
def get_ticket(ticket_number):

    conn = None
    cursor = None

    try:

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        ticket = get_ticket_record(
            cursor,
            ticket_number
        )

        if ticket is None:

            return jsonify({
                "success": False,
                "message": "Ticket not found."
            }), 404

        cursor.execute(
            """
            SELECT
                id,
                author_name,
                comment,
                created_at
            FROM ticket_comments
            WHERE ticket_id = %s
            ORDER BY created_at ASC
            """,
            (ticket["id"],)
        )

        comments = [
            serialize_row(comment)
            for comment in cursor.fetchall()
        ]

        return jsonify({
            "success": True,
            "ticket": serialize_row(ticket),
            "comments": comments
        }), 200

    except Exception as error:

        return jsonify({
            "success": False,
            "message": "Could not load the ticket.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ==========================================
# Create Ticket
# ==========================================

@ticket_bp.route(
    "/tickets",
    methods=["POST"]
)
def create_ticket():

    conn = None
    cursor = None

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            return jsonify({
                "success": False,
                "message": "Invalid JSON request."
            }), 400

        title = clean_text(
            data.get("title"),
            maximum_length=255
        )

        description = clean_text(
            data.get("description")
        )

        requester_name = clean_text(
            data.get("requester_name"),
            maximum_length=150
        )

        requester_email = clean_text(
            data.get("requester_email"),
            maximum_length=255
        ) or None

        category = clean_text(
            data.get("category"),
            default="General",
            maximum_length=100
        )

        priority = clean_text(
            data.get("priority"),
            default="Medium"
        )

        status = clean_text(
            data.get("status"),
            default="Open"
        )

        assigned_to = clean_text(
            data.get("assigned_to"),
            maximum_length=255
        ) or None

        related_entity_type = clean_text(
            data.get("related_entity_type"),
            default="general"
        ).lower()

        related_entity_id = clean_text(
            data.get("related_entity_id"),
            maximum_length=255
        ) or None

        if not title:

            return jsonify({
                "success": False,
                "message": "Ticket title is required."
            }), 400

        if not description:

            return jsonify({
                "success": False,
                "message": (
                    "Ticket description is required."
                )
            }), 400

        if not requester_name:

            return jsonify({
                "success": False,
                "message": (
                    "Requester name is required."
                )
            }), 400

        if priority not in ALLOWED_PRIORITIES:

            return jsonify({
                "success": False,
                "message": "Invalid ticket priority."
            }), 400

        if status not in ALLOWED_STATUSES:

            return jsonify({
                "success": False,
                "message": "Invalid ticket status."
            }), 400

        if (
            related_entity_type
            not in ALLOWED_ENTITY_TYPES
        ):

            return jsonify({
                "success": False,
                "message": (
                    "Invalid related entity type."
                )
            }), 400

        ticket_number = generate_ticket_number()

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_number,
                title,
                description,
                category,
                priority,
                status,
                requester_name,
                requester_email,
                assigned_to,
                related_entity_type,
                related_entity_id
            )
            VALUES (
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
                ticket_number,
                title,
                description,
                category,
                priority,
                status,
                requester_name,
                requester_email,
                assigned_to,
                related_entity_type,
                related_entity_id
            )
        )

        conn.commit()

        ticket = get_ticket_record(
            cursor,
            ticket_number
        )

        return jsonify({
            "success": True,
            "message": "Ticket created successfully.",
            "ticket": serialize_row(ticket)
        }), 201

    except Exception as error:

        if conn is not None:
            conn.rollback()

        return jsonify({
            "success": False,
            "message": "Could not create the ticket.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ==========================================
# Update Ticket
# ==========================================

@ticket_bp.route(
    "/tickets/<string:ticket_number>",
    methods=["PATCH"]
)
def update_ticket(ticket_number):

    conn = None
    cursor = None

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            return jsonify({
                "success": False,
                "message": "Invalid JSON request."
            }), 400

        allowed_fields = {
            "title",
            "description",
            "category",
            "priority",
            "status",
            "requester_name",
            "requester_email",
            "assigned_to",
            "related_entity_type",
            "related_entity_id"
        }

        updates = []
        parameters = []

        for field, value in data.items():

            if field not in allowed_fields:
                continue

            if field == "priority":

                value = clean_text(value)

                if value not in ALLOWED_PRIORITIES:

                    return jsonify({
                        "success": False,
                        "message": (
                            "Invalid ticket priority."
                        )
                    }), 400

            elif field == "status":

                value = clean_text(value)

                if value not in ALLOWED_STATUSES:

                    return jsonify({
                        "success": False,
                        "message": (
                            "Invalid ticket status."
                        )
                    }), 400

            elif field == "related_entity_type":

                value = clean_text(
                    value
                ).lower()

                if value not in ALLOWED_ENTITY_TYPES:

                    return jsonify({
                        "success": False,
                        "message": (
                            "Invalid related entity type."
                        )
                    }), 400

            elif field in {
                "title",
                "description",
                "requester_name"
            }:

                value = clean_text(value)

                if not value:

                    return jsonify({
                        "success": False,
                        "message": (
                            f"{field.replace('_', ' ').title()} "
                            f"cannot be empty."
                        )
                    }), 400

            else:

                value = clean_text(value) or None

            updates.append(
                f"{field} = %s"
            )

            parameters.append(value)

        if not updates:

            return jsonify({
                "success": False,
                "message": (
                    "No valid ticket fields were provided."
                )
            }), 400

        requested_status = data.get("status")

        if requested_status == "Resolved":

            updates.append(
                "resolved_at = CURRENT_TIMESTAMP"
            )

        elif (
            "status" in data
            and requested_status != "Resolved"
        ):

            updates.append(
                "resolved_at = NULL"
            )

        parameters.append(ticket_number)

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute(
            f"""
            UPDATE tickets
            SET
                {", ".join(updates)}
            WHERE ticket_number = %s
            """,
            tuple(parameters)
        )

        if cursor.rowcount == 0:

            conn.rollback()

            existing_ticket = get_ticket_record(
                cursor,
                ticket_number
            )

            if existing_ticket is None:

                return jsonify({
                    "success": False,
                    "message": "Ticket not found."
                }), 404

        conn.commit()

        ticket = get_ticket_record(
            cursor,
            ticket_number
        )

        return jsonify({
            "success": True,
            "message": "Ticket updated successfully.",
            "ticket": serialize_row(ticket)
        }), 200

    except Exception as error:

        if conn is not None:
            conn.rollback()

        return jsonify({
            "success": False,
            "message": "Could not update the ticket.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ==========================================
# Add Ticket Comment
# ==========================================

@ticket_bp.route(
    "/tickets/<string:ticket_number>/comments",
    methods=["POST"]
)
def create_ticket_comment(ticket_number):

    conn = None
    cursor = None

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            return jsonify({
                "success": False,
                "message": "Invalid JSON request."
            }), 400

        author_name = clean_text(
            data.get("author_name"),
            maximum_length=150
        )

        comment = clean_text(
            data.get("comment")
        )

        if not author_name:

            return jsonify({
                "success": False,
                "message": "Comment author is required."
            }), 400

        if not comment:

            return jsonify({
                "success": False,
                "message": "Comment cannot be empty."
            }), 400

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        ticket = get_ticket_record(
            cursor,
            ticket_number
        )

        if ticket is None:

            return jsonify({
                "success": False,
                "message": "Ticket not found."
            }), 404

        cursor.execute(
            """
            INSERT INTO ticket_comments (
                ticket_id,
                author_name,
                comment
            )
            VALUES (%s, %s, %s)
            """,
            (
                ticket["id"],
                author_name,
                comment
            )
        )

        comment_id = cursor.lastrowid

        conn.commit()

        cursor.execute(
            """
            SELECT
                id,
                author_name,
                comment,
                created_at
            FROM ticket_comments
            WHERE id = %s
            """,
            (comment_id,)
        )

        created_comment = cursor.fetchone()

        return jsonify({
            "success": True,
            "message": "Comment added successfully.",
            "comment": serialize_row(
                created_comment
            )
        }), 201

    except Exception as error:

        if conn is not None:
            conn.rollback()

        return jsonify({
            "success": False,
            "message": "Could not add the comment.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ==========================================
# Delete Ticket
# ==========================================

@ticket_bp.route(
    "/tickets/<string:ticket_number>",
    methods=["DELETE"]
)
def delete_ticket(ticket_number):

    conn = None
    cursor = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM tickets
            WHERE ticket_number = %s
            """,
            (ticket_number,)
        )

        if cursor.rowcount == 0:

            conn.rollback()

            return jsonify({
                "success": False,
                "message": "Ticket not found."
            }), 404

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Ticket deleted successfully."
        }), 200

    except Exception as error:

        if conn is not None:
            conn.rollback()

        return jsonify({
            "success": False,
            "message": "Could not delete the ticket.",
            "error": str(error)
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()