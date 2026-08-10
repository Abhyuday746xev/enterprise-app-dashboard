from __future__ import annotations

# =====================================
# Enterprise Dashboard Backend
# =====================================

import json
import os
import subprocess
import sys
import threading
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from database import get_connection
from local_llm.agent_service import AgentServiceError
from local_llm.live_remediation_service import LiveRemediationError
from local_llm.natural_language_planner import (
    NaturalLanguagePlannerError,
    UnsupportedNaturalLanguageCommandError,
    handle_natural_language_command,
)
from local_llm.rag_pipeline import ask_enterprise_ai
from local_llm.remediation_planner import RemediationPlanningError
from local_llm.remediation_routes import ai_remediation_bp
from ticket_service import ticket_bp
from control_panel.routes import control_bp


# =====================================
# Environment Configuration
# =====================================

BACKEND_DIRECTORY = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIRECTORY / ".env"

load_dotenv(
    dotenv_path=ENV_FILE
)


# =====================================
# Optional Live Intune Router
# =====================================
#
# The file local_llm/live_query_router.py will
# be added next. Until it exists, the backend
# continues to use the existing RAG pipeline.
#
# =====================================

try:
    from local_llm.live_query_router import try_live_intune_query

except ModuleNotFoundError as error:
    if error.name != "local_llm.live_query_router":
        raise

    try_live_intune_query = None


# =====================================
# Flask Application
# =====================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "FLASK_SECRET_KEY",
    "development-only-secret-key",
)

app.register_blueprint(
    ticket_bp
)

app.register_blueprint(
    control_bp
)

app.register_blueprint(
    ai_remediation_bp
)


# =====================================
# CORS Configuration
# =====================================

cors_value = os.getenv(
    "CORS_ORIGINS",
    "*",
).strip()

if cors_value == "*":
    cors_origins: str | list[str] = "*"

else:
    cors_origins = [
        origin.strip()
        for origin in cors_value.split(",")
        if origin.strip()
    ]

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": cors_origins
        }
    },
)


# Prevent two synchronization requests from
# running simultaneously in this Flask process.
sync_lock = threading.Lock()


# =====================================
# Database Helpers
# =====================================

def fetch_all(
    query: str,
    parameters: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    connection = None
    cursor = None

    try:
        connection = get_connection()

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            query,
            parameters or (),
        )

        return list(
            cursor.fetchall()
        )

    finally:
        if cursor is not None:
            cursor.close()

        if (
            connection is not None
            and connection.is_connected()
        ):
            connection.close()


def json_safe(value: Any) -> Any:
    """
    Convert database values into JSON-safe values.
    """

    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    if isinstance(value, dict):
        return {
            key: json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            json_safe(item)
            for item in value
        ]

    return value


# =====================================
# Subprocess Helpers
# =====================================

def clean_subprocess_output(
    output: Any,
) -> str:
    if output is None:
        return ""

    if isinstance(output, bytes):
        return output.decode(
            "utf-8",
            errors="replace",
        )

    return str(output)


def run_backend_command(
    command: list[str],
    timeout: int,
) -> dict[str, str]:
    result = subprocess.run(
        command,
        cwd=str(BACKEND_DIRECTORY),
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )

    return {
        "stdout": clean_subprocess_output(
            result.stdout
        ),
        "stderr": clean_subprocess_output(
            result.stderr
        ),
    }


# =====================================
# Request Helpers
# =====================================

def read_question() -> tuple[str | None, Any | None]:
    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        return None, (
            jsonify({
                "success": False,
                "message": "Invalid JSON request.",
            }),
            400,
        )

    question = str(
        data.get(
            "question",
            "",
        )
    ).strip()

    if not question:
        return None, (
            jsonify({
                "success": False,
                "message": "Question cannot be empty.",
            }),
            400,
        )

    return question, None


# =====================================
# Home and Health
# =====================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "Enterprise Dashboard API Running",
    })


@app.route("/api/health", methods=["GET"])
def health():
    database_status = "unavailable"
    live_intune_router = (
        "available"
        if try_live_intune_query is not None
        else "not installed"
    )

    connection = None

    try:
        connection = get_connection()
        database_status = "connected"

    except Exception:
        database_status = "unavailable"

    finally:
        if (
            connection is not None
            and connection.is_connected()
        ):
            connection.close()

    return jsonify({
        "success": database_status == "connected",
        "database": database_status,
        "live_intune_router": live_intune_router,
        "rag": "available",
        "control_panel": "available",
        "ai_remediation": "available",
        "natural_language_planner": "available",
    })


# =====================================
# Applications API
# =====================================

@app.route("/api/apps", methods=["GET"])
def get_apps():
    try:
        applications = fetch_all("""
            SELECT
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
            FROM mobile_apps
            ORDER BY display_name ASC
        """)

        return jsonify(
            json_safe(
                applications
            )
        )

    except Exception as error:
        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


# =====================================
# Devices API
# =====================================

@app.route("/api/devices", methods=["GET"])
def get_devices():
    try:
        devices = fetch_all("""
            SELECT
                id,
                device_name,
                user_name,
                operating_system,
                os_version,
                manufacturer,
                model,
                compliance_state,
                last_sync
            FROM managed_devices
            ORDER BY device_name ASC
        """)

        return jsonify(
            json_safe(
                devices
            )
        )

    except Exception as error:
        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


# =====================================
# Users API
# =====================================

@app.route("/api/users", methods=["GET"])
def get_users():
    try:
        users = fetch_all("""
            SELECT
                id,
                display_name,
                user_principal_name,
                mail,
                mobile_phone,
                account_enabled
            FROM users
            ORDER BY display_name ASC
        """)

        return jsonify(
            json_safe(
                users
            )
        )

    except Exception as error:
        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


# =====================================
# Synchronize Enterprise Data
# =====================================
#
# Microsoft Graph
#       ↓
# batch_sync.py
#       ↓
# MySQL
#       ↓
# local_llm.ingest
#       ↓
# ChromaDB
#
# =====================================

@app.route("/api/sync", methods=["POST"])
def sync_everything():
    if not sync_lock.acquire(
        blocking=False
    ):
        return jsonify({
            "success": False,
            "message": (
                "Enterprise synchronization is already "
                "running. Wait for it to finish."
            ),
        }), 409

    current_step = "starting synchronization"
    mysql_output = ""
    knowledge_base_output = ""

    try:
        print(
            "\n======================================"
        )
        print(
            "Enterprise Synchronization Started"
        )
        print(
            "======================================\n"
        )

        # =================================
        # Step 1: Graph to MySQL
        # =================================

        current_step = "Microsoft Graph to MySQL"

        print(
            "[1/2] Synchronizing Microsoft Graph "
            "with MySQL...",
            flush=True,
        )

        sync_result = run_backend_command(
            [
                sys.executable,
                str(
                    BACKEND_DIRECTORY
                    / "batch_sync.py"
                ),
            ],
            timeout=300,
        )

        mysql_output = sync_result[
            "stdout"
        ]

        if mysql_output:
            print(
                mysql_output,
                flush=True,
            )

        if sync_result["stderr"]:
            print(
                sync_result["stderr"],
                flush=True,
            )

        # =================================
        # Step 2: MySQL to ChromaDB
        # =================================

        current_step = "MySQL to ChromaDB"

        print(
            "[2/2] Updating the Enterprise AI "
            "knowledge base...",
            flush=True,
        )

        ingest_result = run_backend_command(
            [
                sys.executable,
                "-m",
                "local_llm.ingest",
            ],
            timeout=600,
        )

        knowledge_base_output = ingest_result[
            "stdout"
        ]

        if knowledge_base_output:
            print(
                knowledge_base_output,
                flush=True,
            )

        if ingest_result["stderr"]:
            print(
                ingest_result["stderr"],
                flush=True,
            )

        print(
            "\n======================================"
        )
        print(
            "Enterprise Synchronization Completed"
        )
        print(
            "======================================\n"
        )

        return jsonify({
            "success": True,
            "message": (
                "Microsoft Graph, MySQL and the "
                "Enterprise AI knowledge base were "
                "synchronized successfully."
            ),
            "steps": {
                "graph_to_mysql": "completed",
                "mysql_to_chromadb": "completed",
            },
            "mysql_sync_output": mysql_output,
            "knowledge_base_output": (
                knowledge_base_output
            ),
        }), 200

    except subprocess.TimeoutExpired as error:
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": (
                "Synchronization timed out during "
                f"{current_step}."
            ),
            "failed_step": current_step,
            "stdout": clean_subprocess_output(
                error.stdout
            ),
            "stderr": clean_subprocess_output(
                error.stderr
            ),
            "error": str(error),
        }), 504

    except subprocess.CalledProcessError as error:
        traceback.print_exc()

        stdout = clean_subprocess_output(
            error.stdout
        )

        stderr = clean_subprocess_output(
            error.stderr
        )

        return jsonify({
            "success": False,
            "message": (
                "Synchronization failed during "
                f"{current_step}."
            ),
            "failed_step": current_step,
            "stdout": stdout,
            "stderr": stderr,
            "error": (
                stderr
                or stdout
                or str(error)
            ),
        }), 500

    except Exception as error:
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": (
                "Unexpected synchronization error "
                f"during {current_step}."
            ),
            "failed_step": current_step,
            "error": str(error),
        }), 500

    finally:
        sync_lock.release()


# =====================================
# AI Remediation Helpers
# =====================================

def get_ai_actor() -> str:
    """
    Resolve the administrator identity used by the
    remediation permission engine.
    """

    return (
        request.headers.get(
            "X-Admin-User"
        )
        or os.getenv(
            "AI_DEFAULT_ADMIN",
            "local-admin",
        )
    ).strip()


def get_ai_role_map() -> dict[str, set[str]]:
    """
    Load trusted, server-side administrator roles.

    Example:
        AI_ROLE_MAP_JSON={
          "admin@company.com": ["control_admin"]
        }
    """

    raw_value = os.getenv(
        "AI_ROLE_MAP_JSON",
        "",
    ).strip()

    if not raw_value:
        return {}

    try:
        parsed = json.loads(
            raw_value
        )

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "AI_ROLE_MAP_JSON is not valid JSON."
        ) from error

    if not isinstance(
        parsed,
        dict,
    ):
        raise RuntimeError(
            "AI_ROLE_MAP_JSON must be a JSON object."
        )

    role_map: dict[
        str,
        set[str],
    ] = {}

    for actor, configured_roles in parsed.items():
        actor_name = str(
            actor
        ).strip().lower()

        if not actor_name:
            continue

        if isinstance(
            configured_roles,
            str,
        ):
            role_values = (
                configured_roles.split(",")
            )

        elif isinstance(
            configured_roles,
            list,
        ):
            role_values = (
                configured_roles
            )

        else:
            raise RuntimeError(
                "Each AI_ROLE_MAP_JSON value must be "
                "a role string or a list of role strings."
            )

        roles = {
            str(role).strip().lower()
            for role in role_values
            if str(role).strip()
        }

        role_map[
            actor_name
        ] = (
            roles
            or {
                "viewer",
            }
        )

    return role_map


def get_ai_actor_roles() -> set[str]:
    """
    Resolve roles from server-side configuration.

    X-Admin-Roles is ignored unless
    AI_TRUST_ROLE_HEADER=true.
    """

    actor = (
        get_ai_actor()
        .lower()
    )

    mapped_roles = (
        get_ai_role_map()
        .get(
            actor
        )
    )

    if mapped_roles:
        return set(
            mapped_roles
        )

    trust_role_header = (
        os.getenv(
            "AI_TRUST_ROLE_HEADER",
            "false",
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )

    if trust_role_header:
        header_roles = {
            role.strip().lower()
            for role in request.headers.get(
                "X-Admin-Roles",
                "",
            ).split(",")
            if role.strip()
        }

        if header_roles:
            return header_roles

    default_roles = {
        role.strip().lower()
        for role in os.getenv(
            "AI_DEFAULT_ROLES",
            "viewer",
        ).split(",")
        if role.strip()
    }

    return (
        default_roles
        or {
            "viewer",
        }
    )


def format_issue_line(
    issue: dict[str, Any],
) -> str:
    issue_id = issue.get(
        "issue_id",
        "Unknown issue",
    )

    severity = str(
        issue.get(
            "severity",
            "unknown",
        )
    ).upper()

    title = issue.get(
        "title",
        "Untitled issue",
    )

    target = issue.get(
        "target"
    )

    target_name = ""

    if isinstance(
        target,
        dict,
    ):
        target_name = str(
            target.get(
                "name",
                "",
            )
        ).strip()

    suffix = (
        f" — {target_name}"
        if target_name
        else ""
    )

    return (
        f"- [{severity}] {issue_id}: "
        f"{title}{suffix}"
    )


def format_remediation_line(
    remediation: dict[str, Any],
) -> str:
    remediation_id = remediation.get(
        "remediation_id",
        "Unknown remediation",
    )

    issue_id = remediation.get(
        "issue_id",
        "Unknown issue",
    )

    recommendation = remediation.get(
        "recommendation"
    )

    action = "unknown_action"

    if isinstance(
        recommendation,
        dict,
    ):
        action = str(
            recommendation.get(
                "action",
                action,
            )
        )

    permission = remediation.get(
        "permission"
    )

    approval_mode = "unknown"

    if isinstance(
        permission,
        dict,
    ):
        approval_mode = str(
            permission.get(
                "approval_mode",
                approval_mode,
            )
        )

    return (
        f"- {remediation_id}: {action} "
        f"for {issue_id} "
        f"(approval: {approval_mode})"
    )


def format_ai_planner_answer(
    planner_payload: dict[str, Any],
) -> str:
    """
    Convert the structured planner response into text
    suitable for the existing Enterprise AI frontend.
    """

    parsed = planner_payload.get(
        "parsed"
    )

    result = planner_payload.get(
        "result"
    )

    if not isinstance(
        parsed,
        dict,
    ):
        parsed = {}

    if not isinstance(
        result,
        dict,
    ):
        return json.dumps(
            planner_payload,
            indent=2,
            default=str,
        )

    intent = parsed.get(
        "intent",
        "unknown",
    )

    if intent == "issue_scan":
        scan = result.get(
            "scan"
        )

        if not isinstance(
            scan,
            dict,
        ):
            return (
                "The issue scan completed, but no "
                "structured scan result was returned."
            )

        issues = scan.get(
            "issues"
        )

        if not isinstance(
            issues,
            list,
        ):
            issues = []

        if not issues:
            return (
                "The live issue scan completed. "
                "No configured issues were detected."
            )

        lines = [
            (
                "The live issue scan detected "
                f"{len(issues)} issue(s):"
            )
        ]

        lines.extend(
            format_issue_line(
                issue
            )
            for issue in issues[:25]
            if isinstance(
                issue,
                dict,
            )
        )

        if len(
            issues
        ) > 25:
            lines.append(
                f"- {len(issues) - 25} additional issue(s) "
                "were omitted from this summary."
            )

        return "\n".join(
            lines
        )

    if intent == "issue_list":
        issues = result.get(
            "issues"
        )

        if not isinstance(
            issues,
            list,
        ):
            issues = []

        if not issues:
            return (
                "No detected issues matched the "
                "requested filters."
            )

        lines = [
            f"Found {len(issues)} matching issue(s):"
        ]

        lines.extend(
            format_issue_line(
                issue
            )
            for issue in issues
            if isinstance(
                issue,
                dict,
            )
        )

        return "\n".join(
            lines
        )

    if intent == "issue_explanation":
        issue = result.get(
            "issue"
        )

        if not isinstance(
            issue,
            dict,
        ):
            return json.dumps(
                result,
                indent=2,
                default=str,
            )

        evidence = issue.get(
            "evidence",
            {},
        )

        recommendations = issue.get(
            "recommendations",
            [],
        )

        lines = [
            format_issue_line(
                issue
            ),
            "",
            str(
                issue.get(
                    "description",
                    "No description was provided.",
                )
            ),
            "",
            "Evidence:",
            json.dumps(
                evidence,
                indent=2,
                default=str,
            ),
        ]

        if isinstance(
            recommendations,
            list,
        ) and recommendations:
            lines.extend([
                "",
                "Recommended remediation:",
                json.dumps(
                    recommendations,
                    indent=2,
                    default=str,
                ),
            ])

        return "\n".join(
            lines
        )

    if intent == "remediation_plan":
        remediation = result.get(
            "remediation"
        )

        if not isinstance(
            remediation,
            dict,
        ):
            return json.dumps(
                result,
                indent=2,
                default=str,
            )

        return "\n".join([
            "Remediation plan prepared.",
            format_remediation_line(
                remediation
            ),
            "",
            (
                "No action was executed. Retrieve its "
                "Control Panel request and complete the "
                "protected confirmation workflow."
            ),
        ])

    if intent == "remediation_list":
        remediations = result.get(
            "remediations"
        )

        if not isinstance(
            remediations,
            list,
        ):
            remediations = []

        if not remediations:
            return (
                "No remediation plans have been prepared yet. "
                "Run an issue scan, then prepare a fix for an "
                "exact ISSUE-... ID."
            )

        lines = [
            (
                f"Found {len(remediations)} prepared "
                "remediation plan(s):"
            )
        ]

        lines.extend(
            format_remediation_line(
                remediation
            )
            for remediation in remediations
            if isinstance(
                remediation,
                dict,
            )
        )

        return "\n".join(
            lines
        )

    if intent == "control_plan":
        return "\n".join([
            (
                "The validated Control Panel planning "
                "request is ready:"
            ),
            "",
            json.dumps(
                result.get(
                    "control_plan_request",
                    {},
                ),
                indent=2,
                default=str,
            ),
            "",
            (
                "No action was executed. Submit this only "
                "to POST /api/control/actions/plan."
            ),
        ])

    if intent == "status":
        return "\n".join([
            "Local remediation agent status:",
            json.dumps(
                result,
                indent=2,
                default=str,
            ),
        ])

    return json.dumps(
        result,
        indent=2,
        default=str,
    )


# =====================================
# Enterprise AI
# =====================================

@app.route("/api/ask", methods=["POST"])
def ask_ai():
    question, validation_error = (
        read_question()
    )

    if validation_error is not None:
        return validation_error

    assert question is not None

    print(
        "\n======================================"
    )
    print(
        "Enterprise AI Request"
    )
    print(
        "======================================"
    )
    print(
        f"\nQuestion:\n{question}\n"
    )

    try:
        # =================================
        # Local AI Remediation Planner
        # =================================
        #
        # This must run before the old live
        # Intune entity router. Otherwise a
        # command such as "List remediations"
        # is incorrectly treated as a user,
        # device or application name.
        #
        # Unsupported planner commands fall
        # through to the existing live router
        # and RAG pipeline.
        #
        # =================================

        try:
            planner_result = (
                handle_natural_language_command(
                    command=question,
                    actor_roles=(
                        get_ai_actor_roles()
                    ),
                )
            )

        except UnsupportedNaturalLanguageCommandError:
            planner_result = None

        except LiveRemediationError as error:
            return jsonify({
                "success": False,
                "question": question,
                "message": (
                    "The live AI issue inventory "
                    "could not be loaded."
                ),
                "error": str(error),
                "route": "ai_remediation",
            }), 503

        except (
            NaturalLanguagePlannerError,
            RemediationPlanningError,
            AgentServiceError,
            ValueError,
        ) as error:
            return jsonify({
                "success": False,
                "question": question,
                "message": (
                    "The AI remediation request "
                    "could not be prepared."
                ),
                "error": str(error),
                "route": "ai_remediation",
            }), 400

        if planner_result is not None:
            if not isinstance(
                planner_result,
                dict,
            ):
                raise ValueError(
                    "The Natural Language Planner "
                    "returned an invalid result."
                )

            return jsonify({
                "success": True,
                "question": question,
                "answer": format_ai_planner_answer(
                    planner_result
                ),
                "sources": [
                    "Local AI Remediation Planner",
                    "Protected Control Panel",
                ],
                "route": "ai_remediation",
                "planner": json_safe(
                    planner_result
                ),
            }), 200

        # =================================
        # Live Microsoft Graph / Intune
        # =================================
        #
        # Exact inventory questions are
        # answered from live Graph data.
        #
        # The router returns None only when
        # the question is not a live inventory
        # question.
        #
        # =================================

        if try_live_intune_query is not None:
            live_result = try_live_intune_query(
                question
            )

            if live_result is not None:
                if not isinstance(
                    live_result,
                    dict,
                ):
                    raise ValueError(
                        "The live Intune router returned "
                        "an invalid result."
                    )

                return jsonify({
                    "success": True,
                    "question": live_result.get(
                        "question",
                        question,
                    ),
                    "answer": live_result.get(
                        "answer",
                        "No answer was generated.",
                    ),
                    "sources": live_result.get(
                        "sources",
                        [
                            "Microsoft Graph"
                        ],
                    ),
                    "route": "live_intune",
                }), 200

        # =================================
        # ChromaDB RAG Fallback
        # =================================

        result = ask_enterprise_ai(
            question
        )

        if not isinstance(
            result,
            dict,
        ):
            raise ValueError(
                "Enterprise AI returned "
                "an invalid result."
            )

        return jsonify({
            "success": True,
            "question": result.get(
                "question",
                question,
            ),
            "answer": result.get(
                "answer",
                "No answer was generated.",
            ),
            "sources": result.get(
                "sources",
                [],
            ),
            "route": result.get(
                "route",
                "rag",
            ),
        }), 200

    except Exception as error:
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": (
                "The Enterprise AI request failed."
            ),
            "error": str(error),
        }), 500


# =====================================
# Run
# =====================================

if __name__ == "__main__":
    debug_mode = (
        os.getenv(
            "FLASK_DEBUG",
            "true",
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
        }
    )

    port_value = os.getenv(
        "FLASK_PORT",
        "5000",
    ).strip()

    try:
        port = int(
            port_value
        )

    except ValueError as error:
        raise RuntimeError(
            "FLASK_PORT must be an integer."
        ) from error

    print(
        "\n=============================="
    )
    print(
        "Enterprise Dashboard Backend"
    )
    print(
        "==============================\n"
    )

    app.run(
        host=os.getenv(
            "FLASK_HOST",
            "127.0.0.1",
        ),
        port=port,
        debug=debug_mode,
        use_reloader=False,
        threaded=True,
    )