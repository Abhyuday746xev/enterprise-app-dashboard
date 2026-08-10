from __future__ import annotations

"""
Flask API for local AI issue detection and remediation planning.

Security model:
- live inventory access is read-only;
- the local LLM never receives Graph credentials;
- this API prepares protected Control Panel request bodies only;
- it does not confirm or execute Microsoft Graph actions;
- roles come from server-side configuration by default;
- typed confirmations remain enforced by backend/control_panel.
"""

from functools import wraps
from hmac import compare_digest
from typing import Any, Callable
import json
import os
import traceback

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from .agent_service import (
    AgentInputError,
    IssueNotFoundError,
    IssueStateError,
    RemediationNotFoundError,
    default_agent,
)
from .live_remediation_service import (
    LiveRemediationError,
    ProviderNotFoundError,
    ProviderResultError,
    default_live_service,
)
from .remediation_planner import (
    NoSupportedRemediationError,
    RemediationParameterError,
    RemediationPlanningError,
    RemediationTargetMismatchError,
)
from .natural_language_planner import (
    InventedIdentifierError,
    LowConfidenceCommandError,
    NaturalLanguagePlannerError,
    UnsupportedNaturalLanguageCommandError,
    handle_natural_language_command,
)


ai_remediation_bp = Blueprint(
    "ai_remediation",
    __name__,
)


# ==========================================
# Configuration
# ==========================================

LOCAL_ADDRESSES = frozenset({
    "127.0.0.1",
    "::1",
    "localhost",
})


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(
        name
    )

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _configured_api_key() -> str:
    return (
        os.getenv(
            "AI_API_KEY"
        )
        or os.getenv(
            "CONTROL_PANEL_API_KEY"
        )
        or ""
    ).strip()


def _allow_remote_without_key() -> bool:
    return _env_bool(
        "AI_ALLOW_REMOTE_WITHOUT_KEY",
        False,
    )


def _trusted_role_header_enabled() -> bool:
    return _env_bool(
        "AI_TRUST_ROLE_HEADER",
        False,
    )


def _default_roles() -> set[str]:
    raw = os.getenv(
        "AI_DEFAULT_ROLES",
        "viewer",
    )

    roles = {
        role.strip().lower()
        for role in raw.split(",")
        if role.strip()
    }

    return (
        roles
        or {
            "viewer",
        }
    )


def _role_map() -> dict[str, set[str]]:
    raw = os.getenv(
        "AI_ROLE_MAP_JSON",
        "",
    ).strip()

    if not raw:
        return {}

    try:
        parsed = json.loads(
            raw
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

    result: dict[
        str,
        set[str],
    ] = {}

    for actor, roles in parsed.items():
        actor_name = str(
            actor
        ).strip().lower()

        if not actor_name:
            continue

        if isinstance(
            roles,
            str,
        ):
            role_values = roles.split(",")

        elif isinstance(
            roles,
            list,
        ):
            role_values = roles

        else:
            raise RuntimeError(
                "Every AI_ROLE_MAP_JSON value must "
                "be a role string or list of role strings."
            )

        cleaned_roles = {
            str(role).strip().lower()
            for role in role_values
            if str(role).strip()
        }

        result[
            actor_name
        ] = (
            cleaned_roles
            or {
                "viewer",
            }
        )

    return result


# ==========================================
# Response Helpers
# ==========================================

def success_response(
    data: dict[str, Any] | None = None,
    status: int = 200,
) -> tuple[
    Response,
    int,
]:
    payload: dict[
        str,
        Any,
    ] = {
        "success":
            True,
    }

    if data:
        payload.update(
            data
        )

    return (
        jsonify(
            payload
        ),
        status,
    )


def error_response(
    message: str,
    status: int,
    *,
    error_type: str,
    details: Any = None,
) -> tuple[
    Response,
    int,
]:
    payload: dict[
        str,
        Any,
    ] = {
        "success":
            False,

        "message":
            str(
                message
            ),

        "error_type":
            error_type,
    }

    if details is not None:
        payload[
            "details"
        ] = details

    return (
        jsonify(
            payload
        ),
        status,
    )


# ==========================================
# Authentication and Roles
# ==========================================

def _request_api_key() -> str:
    return (
        request.headers.get(
            "X-AI-API-Key"
        )
        or request.headers.get(
            "X-Control-Panel-Key"
        )
        or ""
    ).strip()


def _is_local_request() -> bool:
    remote_address = (
        request.remote_addr
        or ""
    ).strip().lower()

    return (
        remote_address
        in LOCAL_ADDRESSES
    )


def _actor_identity() -> str:
    return (
        request.headers.get(
            "X-Admin-User"
        )
        or os.getenv(
            "AI_DEFAULT_ADMIN",
            "local-admin",
        )
    ).strip()


def _actor_roles() -> set[str]:
    actor = _actor_identity().lower()
    configured_roles = _role_map().get(
        actor
    )

    if configured_roles:
        return set(
            configured_roles
        )

    if _trusted_role_header_enabled():
        raw_header = request.headers.get(
            "X-Admin-Roles",
            "",
        )

        header_roles = {
            role.strip().lower()
            for role in raw_header.split(",")
            if role.strip()
        }

        if header_roles:
            return header_roles

    return _default_roles()


def require_ai_auth(
    function: Callable[..., Any],
) -> Callable[..., Any]:
    @wraps(
        function
    )
    def wrapper(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        configured_key = (
            _configured_api_key()
        )

        supplied_key = (
            _request_api_key()
        )

        if configured_key:
            if not supplied_key or not compare_digest(
                supplied_key,
                configured_key,
            ):
                return error_response(
                    "AI remediation authentication failed.",
                    401,
                    error_type=(
                        "ai_authentication_error"
                    ),
                )

        elif (
            not _is_local_request()
            and not _allow_remote_without_key()
        ):
            return error_response(
                "Remote AI remediation access requires "
                "AI_API_KEY or CONTROL_PANEL_API_KEY.",
                403,
                error_type=(
                    "ai_remote_access_denied"
                ),
            )

        return function(
            *args,
            **kwargs,
        )

    return wrapper


# ==========================================
# Request Helpers
# ==========================================

def _json_object() -> dict[str, Any]:
    data = request.get_json(
        silent=True
    )

    if data is None:
        return {}

    if not isinstance(
        data,
        dict,
    ):
        raise AgentInputError(
            "The request body must be a JSON object."
        )

    return data


def _optional_text(
    data: dict[str, Any],
    key: str,
) -> str | None:
    value = data.get(
        key
    )

    if value is None:
        return None

    cleaned = str(
        value
    ).strip()

    return (
        cleaned
        or None
    )


def _bool_value(
    value: Any,
    default: bool,
) -> bool:
    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        return value

    normalized = str(
        value
    ).strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise AgentInputError(
        "Boolean value is invalid."
    )


# ==========================================
# Error Mapping
# ==========================================

def mapped_exception_response(
    error: Exception,
) -> tuple[
    Response,
    int,
]:
    if isinstance(
        error,
        (
            IssueNotFoundError,
            RemediationNotFoundError,
        ),
    ):
        return error_response(
            str(
                error
            ),
            404,
            error_type=(
                "ai_resource_not_found"
            ),
        )

    if isinstance(
        error,
        IssueStateError,
    ):
        return error_response(
            str(
                error
            ),
            409,
            error_type=(
                "ai_issue_state_error"
            ),
        )

    if isinstance(
        error,
        UnsupportedNaturalLanguageCommandError,
    ):
        return error_response(
            str(
                error
            ),
            422,
            error_type=(
                "unsupported_ai_command"
            ),
        )

    if isinstance(
        error,
        LowConfidenceCommandError,
    ):
        return error_response(
            str(
                error
            ),
            422,
            error_type=(
                "low_confidence_ai_command"
            ),
        )

    if isinstance(
        error,
        InventedIdentifierError,
    ):
        return error_response(
            str(
                error
            ),
            400,
            error_type=(
                "invented_ai_identifier"
            ),
        )

    if isinstance(
        error,
        NaturalLanguagePlannerError,
    ):
        return error_response(
            str(
                error
            ),
            400,
            error_type=(
                "ai_command_validation_error"
            ),
        )

    if isinstance(
        error,
        NoSupportedRemediationError,
    ):
        return error_response(
            str(
                error
            ),
            422,
            error_type=(
                "no_supported_remediation"
            ),
        )

    if isinstance(
        error,
        (
            RemediationParameterError,
            RemediationTargetMismatchError,
            RemediationPlanningError,
            AgentInputError,
            ValueError,
        ),
    ):
        return error_response(
            str(
                error
            ),
            400,
            error_type=(
                "ai_validation_error"
            ),
        )

    if isinstance(
        error,
        (
            ProviderNotFoundError,
            ProviderResultError,
            LiveRemediationError,
        ),
    ):
        return error_response(
            str(
                error
            ),
            503,
            error_type=(
                "ai_live_inventory_error"
            ),
        )

    traceback.print_exc()

    return error_response(
        "The AI remediation service encountered "
        "an unexpected error.",
        500,
        error_type=(
            "ai_internal_error"
        ),
    )


# ==========================================
# Status
# ==========================================

@ai_remediation_bp.route(
    "/api/ai/status",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def get_ai_status() -> tuple[
    Response,
    int,
]:
    try:
        snapshot = (
            default_agent()
            .snapshot()
            .to_dict()
        )

        return success_response({
            "service":
                "local_remediation_agent",

            "execution_enabled":
                False,

            "natural_language_planner_enabled":
                True,

            "control_panel_required":
                True,

            "actor":
                _actor_identity(),

            "roles":
                sorted(
                    _actor_roles()
                ),

            "snapshot":
                snapshot,
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Issue Scan
# ==========================================

@ai_remediation_bp.route(
    "/api/ai/issues/scan",
    methods=[
        "POST",
    ],
)
@require_ai_auth
def scan_ai_issues() -> tuple[
    Response,
    int,
]:
    try:
        data = _json_object()

        replace_existing = _bool_value(
            data.get(
                "replace_existing"
            ),
            True,
        )

        report = (
            default_live_service()
            .scan_live_issues(
                replace_existing=(
                    replace_existing
                )
            )
        )

        return success_response(
            report,
            201,
        )

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Issue Queries
# ==========================================

@ai_remediation_bp.route(
    "/api/ai/issues",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def list_ai_issues() -> tuple[
    Response,
    int,
]:
    try:
        issues = (
            default_agent()
            .list_issues(
                status=request.args.get(
                    "status"
                ),
                severity=request.args.get(
                    "severity"
                ),
                category=request.args.get(
                    "category"
                ),
                target_type=request.args.get(
                    "target_type"
                ),
                limit=request.args.get(
                    "limit",
                    "250",
                ),
            )
        )

        return success_response({
            "count":
                len(
                    issues
                ),

            "issues": [
                issue.to_dict()
                for issue
                in issues
            ],
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/issues/<string:issue_id>",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def get_ai_issue(
    issue_id: str,
) -> tuple[
    Response,
    int,
]:
    try:
        issue = (
            default_agent()
            .get_issue(
                issue_id
            )
        )

        return success_response({
            "issue":
                issue.to_dict(),
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/issues/<string:issue_id>/acknowledge",
    methods=[
        "POST",
    ],
)
@require_ai_auth
def acknowledge_ai_issue(
    issue_id: str,
) -> tuple[
    Response,
    int,
]:
    try:
        issue = (
            default_agent()
            .acknowledge_issue(
                issue_id
            )
        )

        return success_response({
            "message":
                "Issue acknowledged.",

            "issue":
                issue.to_dict(),
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/issues/<string:issue_id>/dismiss",
    methods=[
        "POST",
    ],
)
@require_ai_auth
def dismiss_ai_issue(
    issue_id: str,
) -> tuple[
    Response,
    int,
]:
    try:
        issue = (
            default_agent()
            .dismiss_issue(
                issue_id
            )
        )

        return success_response({
            "message":
                "Issue dismissed.",

            "issue":
                issue.to_dict(),
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Remediation Planning
# ==========================================

@ai_remediation_bp.route(
    "/api/ai/issues/<string:issue_id>/remediation",
    methods=[
        "POST",
    ],
)
@require_ai_auth
def prepare_ai_remediation(
    issue_id: str,
) -> tuple[
    Response,
    int,
]:
    try:
        data = _json_object()

        parameters = data.get(
            "parameters"
        )

        if (
            parameters is not None
            and not isinstance(
                parameters,
                dict,
            )
        ):
            raise AgentInputError(
                "parameters must be a JSON object."
            )

        remediation = (
            default_agent()
            .prepare_remediation(
                issue_id=issue_id,
                actor_roles=(
                    _actor_roles()
                ),
                requested_action=(
                    _optional_text(
                        data,
                        "action",
                    )
                ),
                parameter_overrides=(
                    parameters
                ),
                requested_preapproval_policy_id=(
                    _optional_text(
                        data,
                        "preapproval_policy_id",
                    )
                ),
            )
        )

        return success_response({
            "message":
                (
                    "Remediation plan prepared."
                    if remediation
                    .permission
                    .allowed
                    else
                    "Remediation recommendation prepared, "
                    "but the current administrator is not "
                    "authorized to continue."
                ),

            "actor":
                _actor_identity(),

            "roles":
                sorted(
                    _actor_roles()
                ),

            "remediation":
                remediation.to_dict(),
        }, 201)

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/remediations/prepare-recommended",
    methods=[
        "POST",
    ],
)
@require_ai_auth
def prepare_recommended_ai_remediations() -> tuple[
    Response,
    int,
]:
    try:
        data = _json_object()

        result = (
            default_live_service()
            .prepare_recommended_remediations(
                actor_roles=(
                    _actor_roles()
                ),
                maximum_plans=(
                    data.get(
                        "maximum_plans",
                        25,
                    )
                ),
            )
        )

        return success_response({
            "actor":
                _actor_identity(),

            "roles":
                sorted(
                    _actor_roles()
                ),

            **result,
        }, 201)

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/remediations",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def list_ai_remediations() -> tuple[
    Response,
    int,
]:
    try:
        remediations = (
            default_agent()
            .list_remediations(
                issue_id=(
                    request.args.get(
                        "issue_id"
                    )
                ),
                limit=(
                    request.args.get(
                        "limit",
                        "250",
                    )
                ),
            )
        )

        return success_response({
            "count":
                len(
                    remediations
                ),

            "remediations": [
                remediation.to_dict()
                for remediation
                in remediations
            ],
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/remediations/<string:remediation_id>",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def get_ai_remediation(
    remediation_id: str,
) -> tuple[
    Response,
    int,
]:
    try:
        remediation = (
            default_agent()
            .get_remediation(
                remediation_id
            )
        )

        return success_response({
            "remediation":
                remediation.to_dict(),
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/remediations/<string:remediation_id>/control-plan",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def get_ai_control_plan(
    remediation_id: str,
) -> tuple[
    Response,
    int,
]:
    try:
        remediation = (
            default_agent()
            .get_remediation(
                remediation_id
            )
        )

        control_plan_request = (
            default_agent()
            .get_control_plan_request(
                remediation_id
            )
        )

        return success_response({
            "message":
                "Validated Control Panel planning "
                "request is ready.",

            "execution_performed":
                False,

            "approval_mode":
                remediation
                .permission
                .approval_mode
                .value,

            "confirmation_phrase":
                remediation
                .permission
                .confirmation_phrase,

            "control_plan_request":
                control_plan_request,

            "next_endpoint":
                "/api/control/actions/plan",
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )

# ==========================================
# Natural Language Planner
# ==========================================

@ai_remediation_bp.route(
    "/api/ai/command",
    methods=[
        "POST",
    ],
)
@require_ai_auth
def handle_ai_command() -> tuple[
    Response,
    int,
]:
    """
    Parse and handle one safe administrator command.

    This endpoint never confirms or executes a protected action. For
    remediation commands, it returns a prepared remediation or a validated
    request body for POST /api/control/actions/plan.
    """

    try:
        data = _json_object()

        command = _optional_text(
            data,
            "command",
        )

        if command is None:
            raise AgentInputError(
                "command is required."
            )

        execute_requested = _bool_value(
            data.get(
                "execute"
            ),
            False,
        )

        if execute_requested:
            return error_response(
                "Natural-language execution is disabled. "
                "Prepare the remediation first, then use "
                "the protected Control Panel confirmation "
                "workflow.",
                409,
                error_type=(
                    "ai_direct_execution_disabled"
                ),
            )

        result = (
            handle_natural_language_command(
                command=command,
                actor_roles=(
                    _actor_roles()
                ),
            )
        )

        return success_response({
            "actor":
                _actor_identity(),

            "roles":
                sorted(
                    _actor_roles()
                ),

            "command":
                command,

            **result,
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@ai_remediation_bp.route(
    "/api/ai/command/examples",
    methods=[
        "GET",
    ],
)
@require_ai_auth
def get_ai_command_examples() -> tuple[
    Response,
    int,
]:
    return success_response({
        "examples": [
            {
                "command":
                    "Find all current issues",

                "purpose":
                    "Load live inventory and run the "
                    "deterministic issue detectors.",
            },
            {
                "command":
                    "Show high issues",

                "purpose":
                    "List detected high-severity issues.",
            },
            {
                "command":
                    "Show issues category stale_device_sync",

                "purpose":
                    "Filter detected issues by category.",
            },
            {
                "command":
                    "Explain ISSUE-EXACT-ID",

                "purpose":
                    "Explain one exact detected issue.",
            },
            {
                "command":
                    "Prepare a fix for ISSUE-EXACT-ID",

                "purpose":
                    "Prepare the issue's safest allowlisted "
                    "remediation.",
            },
            {
                "command":
                    "Prepare restart device for ISSUE-EXACT-ID",

                "purpose":
                    "Request a specific allowlisted action. "
                    "The action must also be recommended for "
                    "the issue.",
            },
            {
                "command":
                    "Show remediation plans",

                "purpose":
                    "List prepared remediation plans.",
            },
            {
                "command":
                    "Show the control plan for REMED-EXACT-ID",

                "purpose":
                    "Return the validated body for the "
                    "protected Control Panel planning endpoint.",
            },
            {
                "command":
                    "Show AI agent status",

                "purpose":
                    "Show the in-memory issue and remediation "
                    "service status.",
            },
        ],

        "execution_enabled":
            False,

        "protected_execution_endpoint":
            "/api/control/actions/plan",
    })