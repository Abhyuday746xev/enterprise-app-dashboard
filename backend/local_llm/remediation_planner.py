from __future__ import annotations

"""
Safe remediation planning for the local LLM layer.

This module:
- selects an allowlisted remediation for a detected issue;
- validates target and action compatibility;
- checks administrator roles through remediation_policy.py;
- creates the exact request body expected by the protected Control Panel;
- never calls Microsoft Graph;
- never confirms or executes an action.

Execution remains the responsibility of backend/control_panel.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
import secrets

from .remediation_models import (
    ApprovalMode,
    Issue,
    IssueTarget,
    PermissionDecision,
    RemediationAction,
    RemediationRecommendation,
    Severity,
    TargetType,
)
from .remediation_policy import (
    RemediationPolicyEngine,
    default_policy_engine,
)


class RemediationPlanningError(
    ValueError
):
    """Raised when a safe remediation plan cannot be created."""


class NoSupportedRemediationError(
    RemediationPlanningError
):
    """Raised when an issue has no allowlisted remediation."""


class RemediationTargetMismatchError(
    RemediationPlanningError
):
    """Raised when an action is incompatible with the issue target."""


class RemediationParameterError(
    RemediationPlanningError
):
    """Raised when an action is missing required fixed parameters."""


ACTION_TARGET_TYPES: dict[
    RemediationAction,
    frozenset[TargetType],
] = {
    RemediationAction.ENABLE_USER:
        frozenset({
            TargetType.USER,
        }),

    RemediationAction.DISABLE_USER:
        frozenset({
            TargetType.USER,
        }),

    RemediationAction.SYNC_DEVICE:
        frozenset({
            TargetType.DEVICE,
        }),

    RemediationAction.RESTART_DEVICE:
        frozenset({
            TargetType.DEVICE,
        }),

    RemediationAction.ASSIGN_APPLICATION_GROUP:
        frozenset({
            TargetType.APPLICATION,
        }),

    RemediationAction.DELETE_APPLICATION_ASSIGNMENT:
        frozenset({
            TargetType.APPLICATION,
            TargetType.APPLICATION_ASSIGNMENT,
        }),

    RemediationAction.DELETE_APPLICATION:
        frozenset({
            TargetType.APPLICATION,
        }),
}


RISK_RANK: dict[
    Severity,
    int,
] = {
    Severity.INFO:
        0,

    Severity.LOW:
        1,

    Severity.MEDIUM:
        2,

    Severity.HIGH:
        3,

    Severity.CRITICAL:
        4,
}


CONTROL_PARAMETER_ALLOWLIST: dict[
    RemediationAction,
    frozenset[str],
] = {
    RemediationAction.ENABLE_USER:
        frozenset(),

    RemediationAction.DISABLE_USER:
        frozenset(),

    RemediationAction.SYNC_DEVICE:
        frozenset(),

    RemediationAction.RESTART_DEVICE:
        frozenset(),

    RemediationAction.ASSIGN_APPLICATION_GROUP:
        frozenset({
            "group_id",
            "intent",
            "notifications",
        }),

    RemediationAction.DELETE_APPLICATION_ASSIGNMENT:
        frozenset({
            "assignment_id",
        }),

    RemediationAction.DELETE_APPLICATION:
        frozenset(),
}


FORBIDDEN_PARAMETER_KEYS = frozenset({
    "url",
    "graph_url",
    "endpoint",
    "http_method",
    "method",
    "headers",
    "access_token",
    "token",
    "client_secret",
    "secret",
    "sql",
    "query",
    "code",
    "body",
    "payload",
})


@dataclass(slots=True)
class PreparedRemediation:
    remediation_id: str
    issue_id: str
    issue_category: str
    issue_title: str
    target: IssueTarget
    recommendation: RemediationRecommendation
    permission: PermissionDecision
    control_plan_request: dict[str, Any]
    ready_for_control_panel: bool
    explanation: str
    warnings: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "remediation_id":
                self.remediation_id,

            "issue_id":
                self.issue_id,

            "issue_category":
                self.issue_category,

            "issue_title":
                self.issue_title,

            "target":
                self.target.to_dict(),

            "recommendation":
                self.recommendation.to_dict(),

            "permission":
                self.permission.to_dict(),

            "control_plan_request":
                dict(
                    self.control_plan_request
                ),

            "ready_for_control_panel":
                self.ready_for_control_panel,

            "explanation":
                self.explanation,

            "warnings":
                list(
                    self.warnings
                ),
        }


def _new_remediation_id() -> str:
    return (
        "REMED-"
        + secrets.token_hex(
            8
        ).upper()
    )


def _clean_text(
    value: Any,
    field_name: str,
    *,
    required: bool = True,
    maximum_length: int = 2048,
) -> str | None:
    if value is None:
        if required:
            raise RemediationPlanningError(
                f"{field_name} is required."
            )

        return None

    cleaned = str(
        value
    ).strip()

    if not cleaned:
        if required:
            raise RemediationPlanningError(
                f"{field_name} is required."
            )

        return None

    if len(cleaned) > maximum_length:
        raise RemediationPlanningError(
            f"{field_name} exceeds "
            f"{maximum_length} characters."
        )

    return cleaned


def _as_issue_target(
    raw: IssueTarget | Mapping[str, Any],
) -> IssueTarget:
    if isinstance(
        raw,
        IssueTarget,
    ):
        return raw

    if not isinstance(
        raw,
        Mapping,
    ):
        raise RemediationPlanningError(
            "Issue target must be an IssueTarget "
            "or a mapping."
        )

    return IssueTarget(
        target_type=(
            raw.get("target_type")
            or raw.get("type")
        ),
        target_id=(
            raw.get("target_id")
            or raw.get("id")
        ),
        name=(
            raw.get("name")
            or raw.get("display_name")
            or raw.get("target_name")
        ),
        secondary_name=(
            raw.get("secondary_name")
            or raw.get("user_principal_name")
            or raw.get("publisher")
        ),
        metadata=(
            raw.get("metadata")
            or {}
        ),
    )


def _as_recommendation(
    raw: RemediationRecommendation | Mapping[str, Any],
) -> RemediationRecommendation:
    if isinstance(
        raw,
        RemediationRecommendation,
    ):
        return raw

    if not isinstance(
        raw,
        Mapping,
    ):
        raise RemediationPlanningError(
            "Recommendation must be a "
            "RemediationRecommendation or a mapping."
        )

    return RemediationRecommendation(
        action=raw.get(
            "action"
        ),
        reason=raw.get(
            "reason"
        ),
        expected_result=raw.get(
            "expected_result"
        ),
        risk=raw.get(
            "risk",
            Severity.MEDIUM,
        ),
        parameters=(
            raw.get(
                "parameters"
            )
            or {}
        ),
        confidence=raw.get(
            "confidence",
            1.0,
        ),
    )


def _as_issue(
    raw: Issue | Mapping[str, Any],
) -> Issue:
    if isinstance(
        raw,
        Issue,
    ):
        return raw

    if not isinstance(
        raw,
        Mapping,
    ):
        raise RemediationPlanningError(
            "issue must be an Issue or a mapping."
        )

    recommendations = [
        _as_recommendation(
            recommendation
        )
        for recommendation
        in (
            raw.get(
                "recommendations"
            )
            or []
        )
    ]

    return Issue(
        issue_id=raw.get(
            "issue_id"
        ),
        category=raw.get(
            "category"
        ),
        severity=raw.get(
            "severity"
        ),
        title=raw.get(
            "title"
        ),
        description=raw.get(
            "description"
        ),
        target=_as_issue_target(
            raw.get(
                "target"
            )
            or {}
        ),
        evidence=(
            raw.get(
                "evidence"
            )
            or {}
        ),
        recommendations=(
            recommendations
        ),
        status=raw.get(
            "status",
            "open",
        ),
        source=raw.get(
            "source",
            "deterministic_detector",
        ),
        detected_at=raw.get(
            "detected_at"
        ),
        tags=(
            raw.get(
                "tags"
            )
            or []
        ),
    )


def _normalize_action(
    value: RemediationAction | str,
) -> RemediationAction:
    try:
        return RemediationAction(
            value
        )
    except ValueError as error:
        raise RemediationPlanningError(
            "The requested remediation action "
            "is not allowlisted."
        ) from error


def _validate_target_for_action(
    *,
    action: RemediationAction,
    target: IssueTarget,
) -> None:
    allowed_types = ACTION_TARGET_TYPES[
        action
    ]

    if (
        target.target_type
        not in allowed_types
    ):
        allowed = ", ".join(
            sorted(
                target_type.value
                for target_type
                in allowed_types
            )
        )

        raise RemediationTargetMismatchError(
            f"{action.value} cannot be used for "
            f"{target.target_type.value}. "
            f"Allowed target type(s): {allowed}."
        )


def _clean_control_parameters(
    *,
    action: RemediationAction,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        parameters,
        Mapping,
    ):
        raise RemediationParameterError(
            "Remediation parameters must be a mapping."
        )

    normalized_parameters = {
        str(key).strip():
            value
        for key, value
        in parameters.items()
        if str(key).strip()
    }

    lowered_keys = {
        key.lower()
        for key
        in normalized_parameters
    }

    forbidden = (
        lowered_keys
        & FORBIDDEN_PARAMETER_KEYS
    )

    if forbidden:
        raise RemediationParameterError(
            "Forbidden remediation parameters: "
            + ", ".join(
                sorted(
                    forbidden
                )
            )
        )

    allowed_keys = CONTROL_PARAMETER_ALLOWLIST[
        action
    ]

    unexpected = (
        set(
            normalized_parameters
        )
        - set(
            allowed_keys
        )
    )

    if unexpected:
        raise RemediationParameterError(
            f"{action.value} received unsupported "
            "parameter(s): "
            + ", ".join(
                sorted(
                    unexpected
                )
            )
        )

    cleaned: dict[str, Any] = {}

    for key in allowed_keys:
        if key not in normalized_parameters:
            continue

        value = normalized_parameters[
            key
        ]

        if value is None:
            continue

        cleaned_value = str(
            value
        ).strip()

        if cleaned_value:
            cleaned[
                key
            ] = cleaned_value

    if (
        action
        == RemediationAction
        .ASSIGN_APPLICATION_GROUP
    ):
        group_id = _clean_text(
            cleaned.get(
                "group_id"
            ),
            "group_id",
            maximum_length=128,
        )

        intent = (
            _clean_text(
                cleaned.get(
                    "intent",
                    "required",
                ),
                "intent",
                maximum_length=50,
            )
            or "required"
        )

        notifications = (
            _clean_text(
                cleaned.get(
                    "notifications",
                    "showAll",
                ),
                "notifications",
                maximum_length=50,
            )
            or "showAll"
        )

        if intent not in {
            "available",
            "required",
            "uninstall",
        }:
            raise RemediationParameterError(
                "intent must be available, "
                "required, or uninstall."
            )

        if notifications not in {
            "showAll",
            "showReboot",
            "hideAll",
        }:
            raise RemediationParameterError(
                "notifications must be showAll, "
                "showReboot, or hideAll."
            )

        cleaned = {
            "group_id":
                group_id,

            "intent":
                intent,

            "notifications":
                notifications,
        }

    elif (
        action
        == RemediationAction
        .DELETE_APPLICATION_ASSIGNMENT
    ):
        cleaned = {
            "assignment_id":
                _clean_text(
                    cleaned.get(
                        "assignment_id"
                    ),
                    "assignment_id",
                    maximum_length=512,
                ),
        }

    return cleaned


def _build_control_plan_request(
    *,
    action: RemediationAction,
    target: IssueTarget,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    cleaned_parameters = (
        _clean_control_parameters(
            action=action,
            parameters=parameters,
        )
    )

    request_body: dict[
        str,
        Any,
    ] = {
        "action":
            action.value,

        "target_id":
            target.target_id,
    }

    request_body.update(
        cleaned_parameters
    )

    return request_body


def _select_recommendation(
    *,
    issue: Issue,
    requested_action: (
        RemediationAction
        | str
        | None
    ),
    minimum_confidence: float,
) -> RemediationRecommendation:
    if not issue.recommendations:
        raise NoSupportedRemediationError(
            "This issue has no allowlisted "
            "automatic remediation."
        )

    candidates = list(
        issue.recommendations
    )

    if requested_action is not None:
        selected_action = _normalize_action(
            requested_action
        )

        candidates = [
            recommendation
            for recommendation
            in candidates
            if recommendation.action
            == selected_action
        ]

        if not candidates:
            raise NoSupportedRemediationError(
                "The requested action is not one of "
                "the issue's approved recommendations."
            )

    candidates = [
        recommendation
        for recommendation
        in candidates
        if recommendation.confidence
        >= minimum_confidence
    ]

    if not candidates:
        raise NoSupportedRemediationError(
            "No recommendation met the configured "
            "confidence threshold."
        )

    return sorted(
        candidates,
        key=lambda recommendation: (
            RISK_RANK[
                recommendation.risk
            ],
            -recommendation.confidence,
            recommendation.action.value,
        ),
    )[0]


class RemediationPlanner:
    def __init__(
        self,
        *,
        policy_engine: (
            RemediationPolicyEngine
            | None
        ) = None,
        minimum_confidence: float = 0.70,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "minimum_confidence must be "
                "between 0 and 1."
            )

        self.policy_engine = (
            policy_engine
            or default_policy_engine()
        )

        self.minimum_confidence = (
            minimum_confidence
        )

    def prepare(
        self,
        *,
        issue: Issue | Mapping[str, Any],
        actor_roles: Iterable[str],
        requested_action: (
            RemediationAction
            | str
            | None
        ) = None,
        parameter_overrides: (
            Mapping[str, Any]
            | None
        ) = None,
        requested_preapproval_policy_id: (
            str
            | None
        ) = None,
    ) -> PreparedRemediation:
        normalized_issue = _as_issue(
            issue
        )

        recommendation = (
            _select_recommendation(
                issue=normalized_issue,
                requested_action=(
                    requested_action
                ),
                minimum_confidence=(
                    self.minimum_confidence
                ),
            )
        )

        _validate_target_for_action(
            action=(
                recommendation.action
            ),
            target=(
                normalized_issue.target
            ),
        )

        parameters = dict(
            recommendation.parameters
        )

        if parameter_overrides:
            parameters.update(
                dict(
                    parameter_overrides
                )
            )

        control_request = (
            _build_control_plan_request(
                action=(
                    recommendation.action
                ),
                target=(
                    normalized_issue.target
                ),
                parameters=(
                    parameters
                ),
            )
        )

        permission = (
            self.policy_engine.authorize(
                actor_roles=actor_roles,
                action=(
                    recommendation.action
                ),
                target_ids={
                    normalized_issue
                    .target
                    .target_id
                },
                requested_preapproval_policy_id=(
                    requested_preapproval_policy_id
                ),
            )
        )

        warnings: list[str] = []

        if (
            recommendation.action
            in {
                RemediationAction
                .SYNC_DEVICE,

                RemediationAction
                .RESTART_DEVICE,
            }
        ):
            warnings.append(
                "Microsoft Graph acceptance does not "
                "prove that the device has completed "
                "the asynchronous operation."
            )

        if (
            recommendation.action
            == RemediationAction
            .DELETE_APPLICATION
        ):
            warnings.append(
                "The protected Control Panel must "
                "verify that the application has zero "
                "assignments before deletion."
            )

        ready = bool(
            permission.allowed
        )

        if permission.allowed:
            explanation = (
                f"{recommendation.action.value} is "
                "allowlisted and the current role permits "
                "creating a protected Control Panel plan."
            )
        else:
            explanation = (
                "The issue was detected, but the current "
                "administrator is not authorized to prepare "
                "the recommended remediation."
            )

        return PreparedRemediation(
            remediation_id=(
                _new_remediation_id()
            ),
            issue_id=str(
                normalized_issue.issue_id
            ),
            issue_category=(
                normalized_issue.category
            ),
            issue_title=(
                normalized_issue.title
            ),
            target=(
                normalized_issue.target
            ),
            recommendation=(
                recommendation
            ),
            permission=(
                permission
            ),
            control_plan_request=(
                control_request
            ),
            ready_for_control_panel=(
                ready
            ),
            explanation=(
                explanation
            ),
            warnings=(
                warnings
            ),
        )


def prepare_remediation(
    *,
    issue: Issue | Mapping[str, Any],
    actor_roles: Iterable[str],
    requested_action: (
        RemediationAction
        | str
        | None
    ) = None,
    parameter_overrides: (
        Mapping[str, Any]
        | None
    ) = None,
    requested_preapproval_policy_id: (
        str
        | None
    ) = None,
    minimum_confidence: float = 0.70,
) -> dict[str, Any]:
    planner = RemediationPlanner(
        minimum_confidence=(
            minimum_confidence
        )
    )

    return planner.prepare(
        issue=issue,
        actor_roles=actor_roles,
        requested_action=(
            requested_action
        ),
        parameter_overrides=(
            parameter_overrides
        ),
        requested_preapproval_policy_id=(
            requested_preapproval_policy_id
        ),
        ).to_dict()