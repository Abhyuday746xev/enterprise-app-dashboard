from __future__ import annotations

# ==========================================
# Enterprise Control Panel API Routes
# ==========================================
#
# Protected workflow:
#
# 1. Resolve the exact live Graph target.
# 2. Create a short-lived action plan.
# 3. Require one-use confirmation.
# 4. Execute a fixed allowlisted operation.
# 5. Verify and store the result.
#
# Supported actions:
#
# - enable_user
# - disable_user
# - sync_device
# - restart_device
# - assign_application_group
# - delete_application_assignment
# - delete_application
#
# ==========================================

import os
import secrets
import traceback
from typing import Any

from flask import Blueprint, jsonify, request

from control_panel.audit_log import (
    AuditLogError,
    get_audit_event,
    list_audit_events,
    record_audit_event,
)
from control_panel.application_actions import (
    ApplicationActionError,
    ApplicationAssignmentNotFoundError,
    ApplicationHasAssignmentsError,
    DuplicateApplicationAssignmentError,
    ProtectedApplicationGraphClient,
    UnsupportedApplicationAssignmentTypeError,
)
from control_panel.confirmation_store import (
    ACTION_POLICIES,
    ConfirmationAlreadyUsedError,
    ConfirmationExpiredError,
    ConfirmationNotFoundError,
    ConfirmationOwnershipError,
    ConfirmationStoreError,
    ConfirmationTextError,
    UnsupportedActionError,
    confirmation_store,
)
from control_panel.graph_actions import (
    GraphActionConflictError,
    GraphActionError,
    GraphAuthenticationError,
    GraphPermissionError,
    GraphResourceNotFoundError,
    ProtectedGraphClient,
)


# ==========================================
# Blueprint
# ==========================================

control_bp = Blueprint(
    "control_panel",
    __name__,
)


# ==========================================
# Configuration
# ==========================================

CONTROL_PANEL_API_KEY = os.getenv(
    "CONTROL_PANEL_API_KEY",
    "",
).strip()

CONTROL_DEFAULT_ADMIN = os.getenv(
    "CONTROL_DEFAULT_ADMIN",
    "local-admin",
).strip() or "local-admin"

CONTROL_ALLOW_REMOTE_WITHOUT_KEY = (
    os.getenv(
        "CONTROL_ALLOW_REMOTE_WITHOUT_KEY",
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

LOCAL_ADDRESSES = {
    "127.0.0.1",
    "::1",
    "localhost",
}


# ==========================================
# Response Helpers
# ==========================================

def error_response(
    message: str,
    status_code: int,
    *,
    error_type: str | None = None,
    details: Any = None,
):
    payload: dict[str, Any] = {
        "success": False,
        "message": message,
    }

    if error_type:
        payload["error_type"] = error_type

    if details is not None:
        payload["details"] = details

    return jsonify(payload), status_code


def success_response(
    payload: dict[str, Any],
    status_code: int = 200,
):
    return jsonify({
        "success": True,
        **payload,
    }), status_code


# ==========================================
# Access Protection
# ==========================================

def request_is_local() -> bool:
    remote_address = str(
        request.remote_addr or ""
    ).strip()

    return remote_address in LOCAL_ADDRESSES


def request_actor() -> str:
    """
    Temporary development identity.

    Replace this with the authenticated
    administrator identity before production.
    """

    header_value = str(
        request.headers.get(
            "X-Admin-User",
            "",
        )
    ).strip()

    if header_value:
        return header_value[:512]

    return CONTROL_DEFAULT_ADMIN


def check_control_access():
    """
    Require an API key when configured.

    Without a configured key, requests are
    restricted to localhost unless explicitly
    overridden through the environment.
    """

    if request.method == "OPTIONS":
        return None

    if CONTROL_PANEL_API_KEY:
        supplied_key = str(
            request.headers.get(
                "X-Control-Panel-Key",
                "",
            )
        )

        if not secrets.compare_digest(
            supplied_key,
            CONTROL_PANEL_API_KEY,
        ):
            return error_response(
                "Control Panel authentication failed.",
                401,
                error_type=(
                    "control_authentication_error"
                ),
            )

        return None

    if (
        not request_is_local()
        and not CONTROL_ALLOW_REMOTE_WITHOUT_KEY
    ):
        return error_response(
            (
                "Control Panel operations are restricted "
                "to localhost because "
                "CONTROL_PANEL_API_KEY is not configured."
            ),
            403,
            error_type=(
                "control_access_restricted"
            ),
        )

    return None


@control_bp.before_request
def protect_control_routes():
    return check_control_access()


# ==========================================
# Request Helpers
# ==========================================

def read_json_object() -> dict[str, Any]:
    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        raise ValueError(
            "A JSON object is required."
        )

    return data


def required_text(
    data: dict[str, Any],
    field_name: str,
    *,
    maximum_length: int = 512,
) -> str:
    value = str(
        data.get(
            field_name,
            "",
        )
    ).strip()

    if not value:
        raise ValueError(
            f"{field_name} is required."
        )

    if len(value) > maximum_length:
        raise ValueError(
            f"{field_name} is too long."
        )

    return value


def optional_text(
    data: dict[str, Any],
    field_name: str,
    *,
    maximum_length: int = 512,
) -> str | None:
    raw_value = data.get(
        field_name
    )

    if raw_value is None:
        return None

    value = str(
        raw_value
    ).strip()

    if not value:
        return None

    if len(value) > maximum_length:
        raise ValueError(
            f"{field_name} is too long."
        )

    return value


# ==========================================
# Persistent Audit Helpers
# ==========================================

def action_target_type(
    action: Any,
) -> str | None:
    metadata = getattr(
        action,
        "metadata",
        None,
    )

    if not isinstance(
        metadata,
        dict,
    ):
        return None

    value = metadata.get(
        "entity_type"
    )

    return (
        str(value).strip()
        if value
        else None
    )


def record_action_audit(
    action: Any,
    *,
    event_type: str,
    status: str,
    actor: str,
    request_data: Any = None,
    result_data: Any = None,
    error_message: Any = None,
) -> dict[str, Any]:
    return record_audit_event(
        event_type=event_type,
        status=status,
        actor=actor,
        action_id=getattr(
            action,
            "action_id",
            None,
        ),
        confirmation_id=getattr(
            action,
            "confirmation_id",
            None,
        ),
        action_type=getattr(
            action,
            "action_type",
            None,
        ),
        target_type=action_target_type(
            action
        ),
        target_id=getattr(
            action,
            "target_id",
            None,
        ),
        target_name=getattr(
            action,
            "target_name",
            None,
        ),
        risk=getattr(
            action,
            "risk",
            None,
        ),
        request_data=request_data,
        result_data=result_data,
        error_message=error_message,
    )


def try_record_action_audit(
    action: Any,
    *,
    event_type: str,
    status: str,
    actor: str,
    request_data: Any = None,
    result_data: Any = None,
    error_message: Any = None,
) -> tuple[bool, str | None]:
    try:
        record_action_audit(
            action,
            event_type=event_type,
            status=status,
            actor=actor,
            request_data=request_data,
            result_data=result_data,
            error_message=error_message,
        )

        return True, None

    except Exception as audit_error:
        traceback.print_exc()

        return (
            False,
            str(audit_error),
        )


# ==========================================
# Target Formatting
# ==========================================

def user_status_label(
    value: Any,
) -> str:
    if value is True:
        return "Enabled"

    if value is False:
        return "Disabled"

    return "Unknown"


def assignment_target_summary(
    assignment: dict[str, Any],
) -> dict[str, Any]:
    target = assignment.get(
        "target"
    )

    if not isinstance(target, dict):
        target = {}

    target_type = str(
        target.get(
            "@odata.type",
            "unknown",
        )
    ).split(".")[-1]

    target_identifier = (
        target.get("groupId")
        or target.get("deviceAndAppManagementAssignmentFilterId")
        or target.get("id")
    )

    return {
        "assignment_id":
            assignment.get("id"),

        "intent":
            assignment.get("intent"),

        "target_type":
            target_type,

        "target_id":
            target_identifier,

        "settings":
            assignment.get("settings"),
    }


# ==========================================
# Live Graph Action Planning
# ==========================================

def resolve_user_or_device_plan(
    action_type: str,
    target_id: str,
) -> dict[str, Any]:
    with ProtectedGraphClient() as client:
        if action_type in {
            "enable_user",
            "disable_user",
        }:
            user = client.get_user(
                target_id
            )

            resolved_id = required_text(
                user,
                "id",
            )

            display_name = (
                user.get("displayName")
                or user.get("userPrincipalName")
                or resolved_id
            )

            current_enabled = user.get(
                "accountEnabled"
            )

            requested_enabled = (
                action_type == "enable_user"
            )

            before = user_status_label(
                current_enabled
            )

            after = user_status_label(
                requested_enabled
            )

            return {
                "action_type":
                    action_type,

                "target_id":
                    resolved_id,

                "target_name":
                    str(display_name),

                "before":
                    before,

                "after":
                    after,

                "no_action_required":
                    current_enabled is requested_enabled,

                "metadata": {
                    "entity_type":
                        "user",

                    "user_principal_name":
                        user.get(
                            "userPrincipalName"
                        ),

                    "mail":
                        user.get("mail"),

                    "before":
                        before,

                    "after":
                        after,
                },
            }

        if action_type in {
            "sync_device",
            "restart_device",
        }:
            device = client.get_managed_device(
                target_id
            )

            resolved_id = required_text(
                device,
                "id",
            )

            display_name = (
                device.get("deviceName")
                or device.get("managedDeviceName")
                or resolved_id
            )

            before = (
                "Current device inventory state"
            )

            if action_type == "restart_device":
                after = (
                    "Managed-device reboot requested"
                )

            else:
                after = (
                    "Device synchronization requested"
                )

            return {
                "action_type":
                    action_type,

                "target_id":
                    resolved_id,

                "target_name":
                    str(display_name),

                "before":
                    before,

                "after":
                    after,

                "no_action_required":
                    False,

                "metadata": {
                    "entity_type":
                        "device",

                    "device_action":
                        (
                            "reboot"
                            if action_type
                            == "restart_device"
                            else "sync"
                        ),

                    "user_display_name":
                        device.get(
                            "userDisplayName"
                        ),

                    "user_principal_name":
                        device.get(
                            "userPrincipalName"
                        ),

                    "operating_system":
                        device.get(
                            "operatingSystem"
                        ),

                    "compliance_state":
                        device.get(
                            "complianceState"
                        ),

                    "last_sync_date_time":
                        device.get(
                            "lastSyncDateTime"
                        ),

                    "before":
                        before,

                    "after":
                        after,
                },
            }

    raise UnsupportedActionError(
        "The requested action is not allowed."
    )


def resolve_application_plan(
    action_type: str,
    target_id: str,
    assignment_id: str | None,
    group_id: str | None,
    intent: str | None,
    notifications: str | None,
) -> dict[str, Any]:
    with ProtectedApplicationGraphClient() as client:
        application = client.get_mobile_application(
            target_id
        )

        resolved_app_id = required_text(
            application,
            "id",
        )

        application_name = str(
            application.get(
                "displayName"
            )
            or resolved_app_id
        )

        if action_type == "assign_application_group":
            if not group_id:
                raise ValueError(
                    "group_id is required for "
                    "assign_application_group."
                )

            if not intent:
                raise ValueError(
                    "intent is required for "
                    "assign_application_group."
                )

            cleaned_intent = (
                client._validate_win32_intent(
                    intent
                )
            )

            cleaned_notifications = (
                client._validate_win32_notifications(
                    notifications
                    or "showAll"
                )
            )

            application_type = (
                client._normalized_odata_type(
                    application.get(
                        "@odata.type"
                    )
                )
            )

            if application_type != (
                "microsoft.graph.win32lobapp"
            ):
                raise (
                    UnsupportedApplicationAssignmentTypeError(
                        "This assignment workflow currently "
                        "supports only Intune Win32 applications. "
                        f"The selected application type is "
                        f"'{application_type or 'unknown'}'."
                    )
                )

            publishing_state = str(
                application.get(
                    "publishingState",
                    "",
                )
            ).strip().lower()

            if publishing_state != "published":
                raise ApplicationActionError(
                    "The Win32 application must be published "
                    "before it can be assigned."
                )

            group = client.get_group(
                group_id
            )

            resolved_group_id = required_text(
                group,
                "id",
            )

            group_name = str(
                group.get(
                    "displayName"
                )
                or resolved_group_id
            )

            duplicate = (
                client.find_group_assignment(
                    resolved_app_id,
                    resolved_group_id,
                    cleaned_intent,
                )
            )

            if duplicate is not None:
                raise DuplicateApplicationAssignmentError(
                    (
                        f"{application_name} already has a "
                        f"'{cleaned_intent}' assignment for "
                        f"{group_name}."
                    )
                )

            before = (
                "No matching application assignment exists"
            )

            after = (
                f"Application assigned to {group_name} "
                f"with intent '{cleaned_intent}'"
            )

            return {
                "action_type":
                    action_type,

                "target_id":
                    resolved_app_id,

                "target_name":
                    (
                        f"{application_name} → "
                        f"{group_name}"
                    ),

                "before":
                    before,

                "after":
                    after,

                "no_action_required":
                    False,

                "metadata": {
                    "entity_type":
                        "application_group_assignment",

                    "application_name":
                        application_name,

                    "application_type":
                        application_type,

                    "publishing_state":
                        application.get(
                            "publishingState"
                        ),

                    "group_id":
                        resolved_group_id,

                    "group_name":
                        group_name,

                    "group_mail":
                        group.get(
                            "mail"
                        ),

                    "group_security_enabled":
                        group.get(
                            "securityEnabled"
                        ),

                    "intent":
                        cleaned_intent,

                    "notifications":
                        cleaned_notifications,

                    "before":
                        before,

                    "after":
                        after,
                },
            }

        if action_type == "delete_application":
            assignments = (
                client.list_mobile_app_assignments(
                    resolved_app_id
                )
            )

            assignment_count = len(
                assignments
            )

            if assignment_count > 0:
                raise ApplicationHasAssignmentsError(
                    (
                        f"{application_name} still has "
                        f"{assignment_count} assignment"
                        f"{'' if assignment_count == 1 else 's'}. "
                        "Remove its assignments before deleting "
                        "the application."
                    )
                )

            before = (
                "Application exists with no assignments"
            )

            after = (
                "Application permanently deleted"
            )

            return {
                "action_type":
                    action_type,

                "target_id":
                    resolved_app_id,

                "target_name":
                    application_name,

                "before":
                    before,

                "after":
                    after,

                "no_action_required":
                    False,

                "metadata": {
                    "entity_type":
                        "application",

                    "publisher":
                        application.get(
                            "publisher"
                        ),

                    "publishing_state":
                        application.get(
                            "publishingState"
                        ),

                    "is_assigned":
                        application.get(
                            "isAssigned"
                        ),

                    "assignment_count":
                        assignment_count,

                    "allow_assigned":
                        False,

                    "before":
                        before,

                    "after":
                        after,
                },
            }

        if action_type == (
            "delete_application_assignment"
        ):
            if not assignment_id:
                raise ValueError(
                    "assignment_id is required for "
                    "delete_application_assignment."
                )

            assignment = (
                client.get_mobile_app_assignment(
                    resolved_app_id,
                    assignment_id,
                )
            )

            resolved_assignment_id = (
                required_text(
                    assignment,
                    "id",
                )
            )

            assignment_summary = (
                assignment_target_summary(
                    assignment
                )
            )

            assignment_intent = (
                assignment_summary.get(
                    "intent"
                )
                or "unknown"
            )

            target_type = (
                assignment_summary.get(
                    "target_type"
                )
                or "unknown"
            )

            before = (
                f"Assignment exists: {assignment_intent} "
                f"to {target_type}"
            )

            after = (
                "Application assignment removed"
            )

            return {
                "action_type":
                    action_type,

                "target_id":
                    resolved_app_id,

                "target_name":
                    (
                        f"{application_name} — "
                        f"assignment "
                        f"{resolved_assignment_id}"
                    ),

                "before":
                    before,

                "after":
                    after,

                "no_action_required":
                    False,

                "metadata": {
                    "entity_type":
                        "application_assignment",

                    "application_name":
                        application_name,

                    "assignment_id":
                        resolved_assignment_id,

                    "assignment":
                        assignment_summary,

                    "before":
                        before,

                    "after":
                        after,
                },
            }

    raise UnsupportedActionError(
        "The requested action is not allowed."
    )


def resolve_action_plan(
    action_type: str,
    target_id: str,
    *,
    assignment_id: str | None = None,
    group_id: str | None = None,
    intent: str | None = None,
    notifications: str | None = None,
) -> dict[str, Any]:
    if action_type in {
        "enable_user",
        "disable_user",
        "sync_device",
        "restart_device",
    }:
        return resolve_user_or_device_plan(
            action_type,
            target_id,
        )

    if action_type in {
        "assign_application_group",
        "delete_application",
        "delete_application_assignment",
    }:
        return resolve_application_plan(
            action_type,
            target_id,
            assignment_id,
            group_id,
            intent,
            notifications,
        )

    raise UnsupportedActionError(
        "The requested action is not allowed."
    )


# ==========================================
# Execute a Claimed Action
# ==========================================

def execute_claimed_action(
    action: Any,
) -> dict[str, Any]:
    action_type = str(
        action.action_type
    )

    target_id = str(
        action.target_id
    )

    if action_type in {
        "enable_user",
        "disable_user",
        "sync_device",
        "restart_device",
    }:
        with ProtectedGraphClient() as client:
            if action_type == "enable_user":
                return client.enable_user(
                    target_id
                ).to_dict()

            if action_type == "disable_user":
                return client.disable_user(
                    target_id
                ).to_dict()

            if action_type == "restart_device":
                return client.reboot_managed_device(
                    target_id
                ).to_dict()

            return client.sync_managed_device(
                target_id
            ).to_dict()

    if action_type in {
        "assign_application_group",
        "delete_application",
        "delete_application_assignment",
    }:
        with ProtectedApplicationGraphClient() as client:
            if action_type == "assign_application_group":
                group_id = str(
                    action.metadata.get(
                        "group_id",
                        "",
                    )
                ).strip()

                intent = str(
                    action.metadata.get(
                        "intent",
                        "",
                    )
                ).strip()

                notifications = str(
                    action.metadata.get(
                        "notifications",
                        "showAll",
                    )
                ).strip()

                if not group_id:
                    raise ApplicationActionError(
                        "The confirmed action does not "
                        "contain a group ID."
                    )

                if not intent:
                    raise ApplicationActionError(
                        "The confirmed action does not "
                        "contain an assignment intent."
                    )

                return (
                    client
                    .create_win32_group_assignment(
                        target_id,
                        group_id,
                        intent=intent,
                        notifications=notifications,
                    )
                    .to_dict()
                )

            if action_type == "delete_application":
                return (
                    client
                    .delete_mobile_application(
                        target_id,
                        allow_assigned=False,
                    )
                    .to_dict()
                )

            assignment_id = str(
                action.metadata.get(
                    "assignment_id",
                    "",
                )
            ).strip()

            if not assignment_id:
                raise ApplicationActionError(
                    "The confirmed action does not contain "
                    "an assignment ID."
                )

            return (
                client
                .delete_mobile_app_assignment(
                    target_id,
                    assignment_id,
                )
                .to_dict()
            )

    raise UnsupportedActionError(
        "The requested action is not allowed."
    )


# ==========================================
# Error Mapping
# ==========================================

def mapped_exception_response(
    error: Exception,
):
    if isinstance(
        error,
        ValueError,
    ):
        return error_response(
            str(error),
            400,
            error_type=(
                "validation_error"
            ),
        )

    if isinstance(
        error,
        UnsupportedActionError,
    ):
        return error_response(
            str(error),
            400,
            error_type=(
                "unsupported_action"
            ),
        )

    if isinstance(
        error,
        ConfirmationNotFoundError,
    ):
        return error_response(
            str(error),
            404,
            error_type=(
                "confirmation_not_found"
            ),
        )

    if isinstance(
        error,
        ConfirmationExpiredError,
    ):
        return error_response(
            str(error),
            410,
            error_type=(
                "confirmation_expired"
            ),
        )

    if isinstance(
        error,
        ConfirmationTextError,
    ):
        return error_response(
            str(error),
            400,
            error_type=(
                "confirmation_text_error"
            ),
        )

    if isinstance(
        error,
        ConfirmationOwnershipError,
    ):
        return error_response(
            str(error),
            403,
            error_type=(
                "confirmation_ownership_error"
            ),
        )

    if isinstance(
        error,
        ConfirmationAlreadyUsedError,
    ):
        return error_response(
            str(error),
            409,
            error_type=(
                "confirmation_already_used"
            ),
        )

    if isinstance(
        error,
        DuplicateApplicationAssignmentError,
    ):
        return error_response(
            str(error),
            409,
            error_type=(
                "duplicate_application_assignment"
            ),
        )

    if isinstance(
        error,
        UnsupportedApplicationAssignmentTypeError,
    ):
        return error_response(
            str(error),
            400,
            error_type=(
                "unsupported_application_assignment_type"
            ),
        )

    if isinstance(
        error,
        ApplicationHasAssignmentsError,
    ):
        return error_response(
            str(error),
            409,
            error_type=(
                "application_has_assignments"
            ),
        )

    if isinstance(
        error,
        ApplicationAssignmentNotFoundError,
    ):
        return error_response(
            str(error),
            404,
            error_type=(
                "application_assignment_not_found"
            ),
        )

    if isinstance(
        error,
        GraphAuthenticationError,
    ):
        return error_response(
            str(error),
            401,
            error_type=(
                "graph_authentication_error"
            ),
        )

    if isinstance(
        error,
        GraphPermissionError,
    ):
        return error_response(
            str(error),
            403,
            error_type=(
                "graph_permission_error"
            ),
        )

    if isinstance(
        error,
        GraphResourceNotFoundError,
    ):
        return error_response(
            str(error),
            404,
            error_type=(
                "graph_resource_not_found"
            ),
        )

    if isinstance(
        error,
        GraphActionConflictError,
    ):
        return error_response(
            str(error),
            409,
            error_type=(
                "graph_action_conflict"
            ),
        )

    if isinstance(
        error,
        ApplicationActionError,
    ):
        return error_response(
            str(error),
            502,
            error_type=(
                "application_action_error"
            ),
        )

    if isinstance(
        error,
        GraphActionError,
    ):
        return error_response(
            str(error),
            502,
            error_type=(
                "graph_action_error"
            ),
        )

    if isinstance(
        error,
        AuditLogError,
    ):
        return error_response(
            str(error),
            503,
            error_type=(
                "audit_log_error"
            ),
        )

    if isinstance(
        error,
        ConfirmationStoreError,
    ):
        return error_response(
            str(error),
            409,
            error_type=(
                "confirmation_store_error"
            ),
        )

    traceback.print_exc()

    return error_response(
        "Unexpected Control Panel error.",
        500,
        error_type=(
            "control_panel_error"
        ),
        details=str(error),
    )


# ==========================================
# Capabilities
# ==========================================

@control_bp.route(
    "/api/control/capabilities",
    methods=[
        "GET",
    ],
)
def get_capabilities():
    actions = []

    for (
        action_type,
        policy,
    ) in ACTION_POLICIES.items():
        actions.append({
            "type":
                action_type,

            "label":
                policy.get(
                    "label"
                ),

            "risk":
                policy.get(
                    "risk"
                ),

            "confirmation":
                policy.get(
                    "confirmation_phrase"
                ),
        })

    return success_response({
        "mode":
            "protected_write",

        "actions":
            actions,

        "authentication": (
            "api_key"
            if CONTROL_PANEL_API_KEY
            else "localhost_only"
        ),
    })


# ==========================================
# Application Assignment Review
# ==========================================

@control_bp.route(
    (
        "/api/control/applications/"
        "<string:application_id>/assignments"
    ),
    methods=[
        "GET",
    ],
)
def get_application_assignments(
    application_id: str,
):
    try:
        with ProtectedApplicationGraphClient() as client:
            application = (
                client.get_mobile_application(
                    application_id
                )
            )

            assignments = (
                client.list_mobile_app_assignments(
                    application_id
                )
            )

        return success_response({
            "application": {
                "id":
                    application.get("id"),

                "display_name":
                    application.get(
                        "displayName"
                    ),

                "publisher":
                    application.get(
                        "publisher"
                    ),

                "publishing_state":
                    application.get(
                        "publishingState"
                    ),

                "is_assigned":
                    len(assignments) > 0,
            },

            "count":
                len(assignments),

            "assignments": [
                assignment_target_summary(
                    assignment
                )
                for assignment in assignments
            ],
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Plan Action
# ==========================================

@control_bp.route(
    "/api/control/actions/plan",
    methods=[
        "POST",
    ],
)
def plan_action():
    try:
        data = read_json_object()
        actor = request_actor()

        action_type = required_text(
            data,
            "action",
            maximum_length=100,
        )

        target_id = required_text(
            data,
            "target_id",
        )

        assignment_id = optional_text(
            data,
            "assignment_id",
        )

        group_id = optional_text(
            data,
            "group_id",
        )

        intent = optional_text(
            data,
            "intent",
            maximum_length=50,
        )

        notifications = optional_text(
            data,
            "notifications",
            maximum_length=50,
        )

        plan = resolve_action_plan(
            action_type,
            target_id,
            assignment_id=assignment_id,
            group_id=group_id,
            intent=intent,
            notifications=notifications,
        )

        if plan["no_action_required"]:
            record_audit_event(
                event_type=(
                    "action_not_required"
                ),
                status=(
                    "no_action_required"
                ),
                actor=actor,
                action_type=(
                    plan.get(
                        "action_type"
                    )
                ),
                target_type=(
                    plan.get(
                        "metadata",
                        {},
                    ).get(
                        "entity_type"
                    )
                ),
                target_id=(
                    plan.get(
                        "target_id"
                    )
                ),
                target_name=(
                    plan.get(
                        "target_name"
                    )
                ),
                request_data={
                    "request":
                        data,

                    "plan":
                        plan,
                },
            )

            return success_response({
                "requires_confirmation":
                    False,

                "no_action_required":
                    True,

                "message": (
                    f"No action is required for "
                    f"{plan['target_name']}."
                ),

                "plan":
                    plan,
            })

        action = confirmation_store.create(
            action_type=(
                plan["action_type"]
            ),
            target_id=(
                plan["target_id"]
            ),
            target_name=(
                plan["target_name"]
            ),
            requested_by=actor,
            metadata=(
                plan["metadata"]
            ),
        )

        try:
            record_action_audit(
                action,
                event_type=(
                    "action_planned"
                ),
                status=(
                    "awaiting_confirmation"
                ),
                actor=actor,
                request_data={
                    "request":
                        data,

                    "plan":
                        plan,
                },
            )

        except Exception:
            try:
                confirmation_store.cancel(
                    action.confirmation_id,
                    requested_by=actor,
                )

            except Exception:
                traceback.print_exc()

            raise

        return success_response({
            "requires_confirmation":
                True,

            "no_action_required":
                False,

            "message":
                "Action plan created.",

            "confirmation_id":
                action.confirmation_id,

            "action":
                action.to_public_dict(),

            "plan":
                plan,
        }, 201)

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Confirm and Execute Action
# ==========================================

@control_bp.route(
    "/api/control/actions/confirm",
    methods=[
        "POST",
    ],
)
def confirm_action():
    action = None
    actor = request_actor()

    try:
        data = read_json_object()

        confirmation_id = required_text(
            data,
            "confirmation_id",
            maximum_length=256,
        )

        confirmation_text = optional_text(
            data,
            "confirmation_text",
            maximum_length=100,
        )

        action = (
            confirmation_store
            .claim_for_execution(
                confirmation_id,
                confirmation_text=(
                    confirmation_text
                ),
                requested_by=actor,
            )
        )

        try:
            record_action_audit(
                action,
                event_type=(
                    "action_execution_started"
                ),
                status=(
                    "executing"
                ),
                actor=actor,
                request_data={
                    "confirmation_submitted":
                        True,
                },
            )

        except Exception as audit_error:
            confirmation_store.mark_failed(
                confirmation_id,
                audit_error,
            )

            raise

        try:
            result = execute_claimed_action(
                action
            )

        except Exception as execution_error:
            failed_action = (
                confirmation_store
                .mark_failed(
                    confirmation_id,
                    execution_error,
                )
            )

            try_record_action_audit(
                failed_action,
                event_type=(
                    "action_failed"
                ),
                status=(
                    "failed"
                ),
                actor=actor,
                error_message=(
                    execution_error
                ),
            )

            raise

        completed_action = (
            confirmation_store
            .mark_completed(
                confirmation_id,
                result,
            )
        )

        (
            audit_persisted,
            audit_warning,
        ) = try_record_action_audit(
            completed_action,
            event_type=(
                "action_completed"
            ),
            status=(
                "completed"
            ),
            actor=actor,
            result_data=result,
        )

        response_payload: dict[
            str,
            Any,
        ] = {
            "message":
                "Action completed successfully.",

            "action":
                completed_action.to_public_dict(),

            "result":
                result,

            "audit_persisted":
                audit_persisted,
        }

        if audit_warning:
            response_payload[
                "warning"
            ] = (
                "The action completed, but the "
                "completion audit event could not "
                "be persisted: "
                f"{audit_warning}"
            )

        return success_response(
            response_payload
        )

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Cancel Pending Action
# ==========================================

@control_bp.route(
    "/api/control/actions/cancel",
    methods=[
        "POST",
    ],
)
def cancel_action():
    try:
        data = read_json_object()
        actor = request_actor()

        confirmation_id = required_text(
            data,
            "confirmation_id",
            maximum_length=256,
        )

        action = confirmation_store.cancel(
            confirmation_id,
            requested_by=actor,
        )

        (
            audit_persisted,
            audit_warning,
        ) = try_record_action_audit(
            action,
            event_type=(
                "action_cancelled"
            ),
            status=(
                "cancelled"
            ),
            actor=actor,
        )

        payload: dict[
            str,
            Any,
        ] = {
            "message":
                "Pending action cancelled.",

            "action":
                action.to_public_dict(),

            "audit_persisted":
                audit_persisted,
        }

        if audit_warning:
            payload["warning"] = (
                "The action was cancelled, but "
                "the cancellation audit event "
                "could not be persisted: "
                f"{audit_warning}"
            )

        return success_response(
            payload
        )

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# List Action Jobs
# ==========================================

@control_bp.route(
    "/api/control/jobs",
    methods=[
        "GET",
    ],
)
def list_action_jobs():
    try:
        raw_limit = request.args.get(
            "limit",
            "100",
        )

        try:
            limit = int(
                raw_limit
            )

        except ValueError as error:
            raise ValueError(
                "limit must be an integer."
            ) from error

        status_values = {
            value.strip()
            for value in request.args.getlist(
                "status"
            )
            if value.strip()
        }

        actions = (
            confirmation_store
            .list_actions(
                limit=limit,
                statuses=(
                    status_values
                    if status_values
                    else None
                ),
            )
        )

        return success_response({
            "count":
                len(actions),

            "jobs": [
                action.to_public_dict()
                for action in actions
            ],
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


# ==========================================
# Read One Action Job
# ==========================================

@control_bp.route(
    "/api/control/jobs/<string:identifier>",
    methods=[
        "GET",
    ],
)
def get_action_job(
    identifier: str,
):
    try:
        try:
            action = confirmation_store.get(
                identifier
            )

        except ConfirmationNotFoundError:
            action = next(
                (
                    item
                    for item in
                    confirmation_store.list_actions(
                        limit=500
                    )
                    if item.action_id
                    == identifier
                ),
                None,
            )

            if action is None:
                raise ConfirmationNotFoundError(
                    "The action job was not found."
                )

        return success_response({
            "job":
                action.to_public_dict(),
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )

# ==========================================
# Persistent Audit API
# ==========================================

@control_bp.route(
    "/api/control/audit",
    methods=[
        "GET",
    ],
)
def get_control_audit():
    try:
        raw_limit = request.args.get(
            "limit",
            "100",
        )

        events = list_audit_events(
            limit=raw_limit,
            status=request.args.get(
                "status"
            ),
            action_type=request.args.get(
                "action_type"
            ),
            actor=request.args.get(
                "actor"
            ),
        )

        return success_response({
            "count":
                len(events),

            "events":
                events,
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )


@control_bp.route(
    "/api/control/audit/<string:event_id>",
    methods=[
        "GET",
    ],
)
def get_control_audit_event(
    event_id: str,
):
    try:
        event = get_audit_event(
            event_id
        )

        if event is None:
            return error_response(
                "The audit event was not found.",
                404,
                error_type=(
                    "audit_event_not_found"
                ),
            )

        return success_response({
            "event":
                event,
        })

    except Exception as error:
        return mapped_exception_response(
            error
        )