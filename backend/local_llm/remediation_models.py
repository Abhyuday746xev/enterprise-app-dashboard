from __future__ import annotations

"""
Strict data models for local AI issue detection and remediation planning.

Security boundary:
- These models describe findings and plans.
- They do not execute Microsoft Graph requests.
- They do not accept arbitrary URLs, HTTP methods, SQL, or code.
- Any executable remediation must match the fixed action allowlist.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
import hashlib
import json
import secrets


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    REMEDIATION_PLANNED = "remediation_planned"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    FAILED = "failed"


class TargetType(str, Enum):
    USER = "user"
    DEVICE = "device"
    APPLICATION = "application"
    APPLICATION_ASSIGNMENT = "application_assignment"
    CONTROL_JOB = "control_job"
    TENANT = "tenant"
    SYSTEM = "system"


class ApprovalMode(str, Enum):
    NONE = "none"
    PREAPPROVED_OR_SINGLE = "preapproved_or_single"
    SINGLE_CONFIRMATION = "single_confirmation"
    TYPED_CONFIRMATION = "typed_confirmation"
    TWO_PERSON = "two_person"
    BLOCKED = "blocked"


class RemediationAction(str, Enum):
    ENABLE_USER = "enable_user"
    DISABLE_USER = "disable_user"
    SYNC_DEVICE = "sync_device"
    RESTART_DEVICE = "restart_device"
    ASSIGN_APPLICATION_GROUP = "assign_application_group"
    DELETE_APPLICATION_ASSIGNMENT = "delete_application_assignment"
    DELETE_APPLICATION = "delete_application"


ALLOWED_REMEDIATION_ACTIONS = frozenset(
    action.value
    for action in RemediationAction
)


class QueryType(str, Enum):
    INVENTORY_QUERY = "inventory_query"
    ISSUE_SCAN = "issue_scan"
    ISSUE_EXPLANATION = "issue_explanation"
    REMEDIATION_PLAN = "remediation_plan"
    REMEDIATION_EXECUTE = "remediation_execute"
    DOCUMENTATION_QUERY = "documentation_query"
    UNSUPPORTED = "unsupported"


def utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _clean_text(
    value: Any,
    field_name: str,
    *,
    required: bool = True,
    maximum_length: int = 2048,
) -> str | None:
    if value is None:
        if required:
            raise ValueError(
                f"{field_name} is required."
            )
        return None

    cleaned = str(
        value
    ).strip()

    if not cleaned:
        if required:
            raise ValueError(
                f"{field_name} is required."
            )
        return None

    if len(cleaned) > maximum_length:
        raise ValueError(
            f"{field_name} exceeds {maximum_length} characters."
        )

    return cleaned


def _clean_confidence(
    value: Any,
) -> float:
    try:
        confidence = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "confidence must be a number."
        ) from error

    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            "confidence must be between 0 and 1."
        )

    return confidence


def _safe_mapping(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if value is None:
        return {}

    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            "Expected a mapping."
        )

    return dict(
        value
    )


def _enum_value(
    enum_type: type[Enum],
    value: Any,
    field_name: str,
) -> Enum:
    try:
        return enum_type(
            value
        )
    except ValueError as error:
        allowed = ", ".join(
            item.value
            for item in enum_type
        )

        raise ValueError(
            f"{field_name} must be one of: {allowed}."
        ) from error


def _stable_identifier(
    prefix: str,
    *parts: Any,
) -> str:
    normalized = "|".join(
        str(part or "").strip().lower()
        for part in parts
    )

    digest = hashlib.sha256(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()[:16].upper()

    return f"{prefix}-{digest}"


def _random_identifier(
    prefix: str,
) -> str:
    return (
        f"{prefix}-"
        f"{secrets.token_hex(8).upper()}"
    )


@dataclass(slots=True)
class IssueTarget:
    target_type: TargetType
    target_id: str
    name: str
    secondary_name: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.target_type = _enum_value(
            TargetType,
            self.target_type,
            "target_type",
        )

        self.target_id = _clean_text(
            self.target_id,
            "target_id",
            maximum_length=512,
        )

        self.name = _clean_text(
            self.name,
            "name",
            maximum_length=512,
        )

        self.secondary_name = _clean_text(
            self.secondary_name,
            "secondary_name",
            required=False,
            maximum_length=512,
        )

        self.metadata = _safe_mapping(
            self.metadata
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type":
                self.target_type.value,

            "id":
                self.target_id,

            "name":
                self.name,

            "secondary_name":
                self.secondary_name,

            "metadata":
                dict(
                    self.metadata
                ),
        }


@dataclass(slots=True)
class RemediationRecommendation:
    action: RemediationAction
    reason: str
    expected_result: str
    risk: Severity
    parameters: dict[str, Any] = field(
        default_factory=dict
    )
    confidence: float = 1.0

    def __post_init__(self) -> None:
        self.action = _enum_value(
            RemediationAction,
            self.action,
            "action",
        )

        self.reason = _clean_text(
            self.reason,
            "reason",
            maximum_length=4000,
        )

        self.expected_result = _clean_text(
            self.expected_result,
            "expected_result",
            maximum_length=4000,
        )

        self.risk = _enum_value(
            Severity,
            self.risk,
            "risk",
        )

        self.parameters = _safe_mapping(
            self.parameters
        )

        self.confidence = _clean_confidence(
            self.confidence
        )

        forbidden_keys = {
            "url",
            "graph_url",
            "http_method",
            "method",
            "sql",
            "query",
            "code",
            "access_token",
            "client_secret",
        }

        matching_forbidden = (
            forbidden_keys
            & {
                str(key).strip().lower()
                for key in self.parameters
            }
        )

        if matching_forbidden:
            raise ValueError(
                "Remediation parameters contain forbidden keys: "
                + ", ".join(
                    sorted(
                        matching_forbidden
                    )
                )
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action":
                self.action.value,

            "reason":
                self.reason,

            "expected_result":
                self.expected_result,

            "risk":
                self.risk.value,

            "parameters":
                dict(
                    self.parameters
                ),

            "confidence":
                self.confidence,
        }


@dataclass(slots=True)
class Issue:
    category: str
    severity: Severity
    title: str
    description: str
    target: IssueTarget
    evidence: dict[str, Any]
    recommendations: list[
        RemediationRecommendation
    ] = field(
        default_factory=list
    )
    status: IssueStatus = IssueStatus.OPEN
    source: str = "deterministic_detector"
    issue_id: str | None = None
    detected_at: str = field(
        default_factory=utc_now_iso
    )
    tags: list[str] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.category = _clean_text(
            self.category,
            "category",
            maximum_length=100,
        )

        self.severity = _enum_value(
            Severity,
            self.severity,
            "severity",
        )

        self.title = _clean_text(
            self.title,
            "title",
            maximum_length=512,
        )

        self.description = _clean_text(
            self.description,
            "description",
            maximum_length=8000,
        )

        if not isinstance(
            self.target,
            IssueTarget,
        ):
            raise ValueError(
                "target must be an IssueTarget."
            )

        self.evidence = _safe_mapping(
            self.evidence
        )

        self.status = _enum_value(
            IssueStatus,
            self.status,
            "status",
        )

        self.source = _clean_text(
            self.source,
            "source",
            maximum_length=100,
        )

        if self.issue_id is None:
            self.issue_id = _stable_identifier(
                "ISSUE",
                self.category,
                self.target.target_type.value,
                self.target.target_id,
            )
        else:
            self.issue_id = _clean_text(
                self.issue_id,
                "issue_id",
                maximum_length=64,
            )

        self.detected_at = _clean_text(
            self.detected_at,
            "detected_at",
            maximum_length=100,
        )

        validated_recommendations: list[
            RemediationRecommendation
        ] = []

        for recommendation in self.recommendations:
            if not isinstance(
                recommendation,
                RemediationRecommendation,
            ):
                raise ValueError(
                    "recommendations must contain "
                    "RemediationRecommendation objects."
                )

            validated_recommendations.append(
                recommendation
            )

        self.recommendations = (
            validated_recommendations
        )

        self.tags = [
            _clean_text(
                tag,
                "tag",
                maximum_length=100,
            )
            for tag in self.tags
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id":
                self.issue_id,

            "category":
                self.category,

            "severity":
                self.severity.value,

            "title":
                self.title,

            "description":
                self.description,

            "target":
                self.target.to_dict(),

            "evidence":
                dict(
                    self.evidence
                ),

            "recommendations": [
                recommendation.to_dict()
                for recommendation
                in self.recommendations
            ],

            "status":
                self.status.value,

            "source":
                self.source,

            "detected_at":
                self.detected_at,

            "tags":
                list(
                    self.tags
                ),
        }


@dataclass(slots=True)
class ClarificationCandidate:
    target_id: str
    name: str
    target_type: TargetType
    secondary_name: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.target_id = _clean_text(
            self.target_id,
            "target_id",
            maximum_length=512,
        )

        self.name = _clean_text(
            self.name,
            "name",
            maximum_length=512,
        )

        self.target_type = _enum_value(
            TargetType,
            self.target_type,
            "target_type",
        )

        self.secondary_name = _clean_text(
            self.secondary_name,
            "secondary_name",
            required=False,
            maximum_length=512,
        )

        self.metadata = _safe_mapping(
            self.metadata
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":
                self.target_id,

            "name":
                self.name,

            "type":
                self.target_type.value,

            "secondary_name":
                self.secondary_name,

            "metadata":
                dict(
                    self.metadata
                ),
        }


@dataclass(slots=True)
class ClarificationRequest:
    message: str
    candidates: list[
        ClarificationCandidate
    ]
    clarification_id: str = field(
        default_factory=lambda: _random_identifier(
            "CLARIFY"
        )
    )

    def __post_init__(self) -> None:
        self.message = _clean_text(
            self.message,
            "message",
            maximum_length=4000,
        )

        self.clarification_id = _clean_text(
            self.clarification_id,
            "clarification_id",
            maximum_length=64,
        )

        if not self.candidates:
            raise ValueError(
                "At least one clarification candidate is required."
            )

        if not all(
            isinstance(
                candidate,
                ClarificationCandidate,
            )
            for candidate in self.candidates
        ):
            raise ValueError(
                "candidates must contain "
                "ClarificationCandidate objects."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clarification_required":
                True,

            "clarification_id":
                self.clarification_id,

            "message":
                self.message,

            "candidates": [
                candidate.to_dict()
                for candidate
                in self.candidates
            ],
        }


@dataclass(slots=True)
class NaturalLanguagePlan:
    query_type: QueryType
    confidence: float
    explanation: str
    action: RemediationAction | None = None
    target_type: TargetType | None = None
    target_query: str | None = None
    target_id: str | None = None
    parameters: dict[str, Any] = field(
        default_factory=dict
    )
    clarification_required: bool = False
    clarification: ClarificationRequest | None = None
    plan_id: str = field(
        default_factory=lambda: _random_identifier(
            "PLAN"
        )
    )

    def __post_init__(self) -> None:
        self.query_type = _enum_value(
            QueryType,
            self.query_type,
            "query_type",
        )

        self.confidence = _clean_confidence(
            self.confidence
        )

        self.explanation = _clean_text(
            self.explanation,
            "explanation",
            maximum_length=8000,
        )

        if self.action is not None:
            self.action = _enum_value(
                RemediationAction,
                self.action,
                "action",
            )

        if self.target_type is not None:
            self.target_type = _enum_value(
                TargetType,
                self.target_type,
                "target_type",
            )

        self.target_query = _clean_text(
            self.target_query,
            "target_query",
            required=False,
            maximum_length=1000,
        )

        self.target_id = _clean_text(
            self.target_id,
            "target_id",
            required=False,
            maximum_length=512,
        )

        self.parameters = _safe_mapping(
            self.parameters
        )

        self.plan_id = _clean_text(
            self.plan_id,
            "plan_id",
            maximum_length=64,
        )

        if self.clarification_required:
            if not isinstance(
                self.clarification,
                ClarificationRequest,
            ):
                raise ValueError(
                    "clarification is required when "
                    "clarification_required is true."
                )

        if (
            self.query_type
            in {
                QueryType.REMEDIATION_PLAN,
                QueryType.REMEDIATION_EXECUTE,
            }
            and self.action is None
        ):
            raise ValueError(
                "A remediation action is required for "
                "remediation plans."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id":
                self.plan_id,

            "query_type":
                self.query_type.value,

            "confidence":
                self.confidence,

            "explanation":
                self.explanation,

            "action":
                (
                    self.action.value
                    if self.action
                    else None
                ),

            "target_type":
                (
                    self.target_type.value
                    if self.target_type
                    else None
                ),

            "target_query":
                self.target_query,

            "target_id":
                self.target_id,

            "parameters":
                dict(
                    self.parameters
                ),

            "clarification_required":
                self.clarification_required,

            "clarification":
                (
                    self.clarification.to_dict()
                    if self.clarification
                    else None
                ),
        }


@dataclass(slots=True)
class PermissionDecision:
    allowed: bool
    action: RemediationAction
    approval_mode: ApprovalMode
    reason: str
    required_role: str | None = None
    confirmation_phrase: str | None = None
    policy_id: str | None = None
    maximum_targets: int = 1

    def __post_init__(self) -> None:
        self.action = _enum_value(
            RemediationAction,
            self.action,
            "action",
        )

        self.approval_mode = _enum_value(
            ApprovalMode,
            self.approval_mode,
            "approval_mode",
        )

        self.reason = _clean_text(
            self.reason,
            "reason",
            maximum_length=4000,
        )

        self.required_role = _clean_text(
            self.required_role,
            "required_role",
            required=False,
            maximum_length=100,
        )

        self.confirmation_phrase = _clean_text(
            self.confirmation_phrase,
            "confirmation_phrase",
            required=False,
            maximum_length=100,
        )

        self.policy_id = _clean_text(
            self.policy_id,
            "policy_id",
            required=False,
            maximum_length=128,
        )

        if self.maximum_targets <= 0:
            raise ValueError(
                "maximum_targets must be greater than zero."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed":
                self.allowed,

            "action":
                self.action.value,

            "approval_mode":
                self.approval_mode.value,

            "reason":
                self.reason,

            "required_role":
                self.required_role,

            "confirmation_phrase":
                self.confirmation_phrase,

            "policy_id":
                self.policy_id,

            "maximum_targets":
                self.maximum_targets,
        }


@dataclass(slots=True)
class RemediationExecutionResult:
    remediation_id: str
    issue_id: str
    action: RemediationAction
    target_id: str
    status: str
    control_confirmation_id: str | None = None
    control_action_id: str | None = None
    verified: bool = False
    result: dict[str, Any] = field(
        default_factory=dict
    )
    error_message: str | None = None
    created_at: str = field(
        default_factory=utc_now_iso
    )

    def __post_init__(self) -> None:
        self.remediation_id = _clean_text(
            self.remediation_id,
            "remediation_id",
            maximum_length=64,
        )

        self.issue_id = _clean_text(
            self.issue_id,
            "issue_id",
            maximum_length=64,
        )

        self.action = _enum_value(
            RemediationAction,
            self.action,
            "action",
        )

        self.target_id = _clean_text(
            self.target_id,
            "target_id",
            maximum_length=512,
        )

        self.status = _clean_text(
            self.status,
            "status",
            maximum_length=100,
        )

        self.control_confirmation_id = _clean_text(
            self.control_confirmation_id,
            "control_confirmation_id",
            required=False,
            maximum_length=256,
        )

        self.control_action_id = _clean_text(
            self.control_action_id,
            "control_action_id",
            required=False,
            maximum_length=64,
        )

        self.result = _safe_mapping(
            self.result
        )

        self.error_message = _clean_text(
            self.error_message,
            "error_message",
            required=False,
            maximum_length=8000,
        )

        self.created_at = _clean_text(
            self.created_at,
            "created_at",
            maximum_length=100,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "remediation_id":
                self.remediation_id,

            "issue_id":
                self.issue_id,

            "action":
                self.action.value,

            "target_id":
                self.target_id,

            "status":
                self.status,

            "control_confirmation_id":
                self.control_confirmation_id,

            "control_action_id":
                self.control_action_id,

            "verified":
                self.verified,

            "result":
                dict(
                    self.result
                ),

            "error_message":
                self.error_message,

            "created_at":
                self.created_at,
        }


def validate_model_json(
    raw_text: str,
) -> dict[str, Any]:
    """
    Parse model output as a single JSON object.

    This deliberately rejects surrounding prose and non-object JSON.
    """

    cleaned = _clean_text(
        raw_text,
        "raw_text",
        maximum_length=100_000,
    )

    try:
        parsed = json.loads(
            cleaned
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "The model response was not valid JSON."
        ) from error

    if not isinstance(
        parsed,
        dict,
    ):
        raise ValueError(
            "The model response must be a JSON object."
        )

    return parsed