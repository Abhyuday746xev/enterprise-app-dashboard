from __future__ import annotations

"""
Local remediation agent orchestration service.

This service coordinates deterministic issue detection and permission-aware
remediation planning inside backend/local_llm.

It deliberately stops before execution:
- it does not call Microsoft Graph;
- it does not call the protected Control Panel confirm endpoint;
- it does not store or accept Graph access tokens;
- it does not bypass typed confirmations;
- it does not invent target IDs.

The returned control_plan_request is intended for the existing protected
Control Panel planning layer.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable, Mapping, Sequence
import secrets

from .issue_detectors import (
    DetectorConfig,
    IssueDetector,
)
from .remediation_models import (
    Issue,
    IssueStatus,
    RemediationAction,
    Severity,
)
from .remediation_planner import (
    PreparedRemediation,
    RemediationPlanner,
)
from .remediation_policy import (
    PreapprovedPolicy,
    RemediationPolicyEngine,
)


class AgentServiceError(
    RuntimeError
):
    """Base exception for remediation-agent failures."""


class IssueNotFoundError(
    AgentServiceError
):
    """Raised when a requested issue ID is not present."""


class RemediationNotFoundError(
    AgentServiceError
):
    """Raised when a requested remediation ID is not present."""


class IssueStateError(
    AgentServiceError
):
    """Raised when an issue cannot transition to the requested state."""


class AgentInputError(
    AgentServiceError
):
    """Raised when the caller supplies invalid inventory or filters."""


def _utc_now_iso() -> str:
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
            raise AgentInputError(
                f"{field_name} is required."
            )

        return None

    cleaned = str(
        value
    ).strip()

    if not cleaned:
        if required:
            raise AgentInputError(
                f"{field_name} is required."
            )

        return None

    if len(cleaned) > maximum_length:
        raise AgentInputError(
            f"{field_name} exceeds "
            f"{maximum_length} characters."
        )

    return cleaned


def _clean_roles(
    actor_roles: Iterable[str],
) -> set[str]:
    roles = {
        str(role).strip().lower()
        for role
        in actor_roles
        if str(role).strip()
    }

    if not roles:
        roles.add(
            "viewer"
        )

    return roles


def _new_scan_id() -> str:
    return (
        "SCAN-"
        + secrets.token_hex(
            8
        ).upper()
    )


@dataclass(slots=True)
class IssueScanResult:
    scan_id: str
    scanned_at: str
    issues: list[Issue]
    counts: dict[str, int]
    source_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id":
                self.scan_id,

            "scanned_at":
                self.scanned_at,

            "count":
                len(
                    self.issues
                ),

            "counts":
                dict(
                    self.counts
                ),

            "source_counts":
                dict(
                    self.source_counts
                ),

            "issues": [
                issue.to_dict()
                for issue
                in self.issues
            ],
        }


@dataclass(slots=True)
class AgentSnapshot:
    scan_id: str | None
    scanned_at: str | None
    issue_count: int
    remediation_count: int
    open_issue_count: int
    awaiting_approval_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id":
                self.scan_id,

            "scanned_at":
                self.scanned_at,

            "issue_count":
                self.issue_count,

            "remediation_count":
                self.remediation_count,

            "open_issue_count":
                self.open_issue_count,

            "awaiting_approval_count":
                self.awaiting_approval_count,
        }


class LocalRemediationAgent:
    """
    In-process issue and remediation planning service.

    The store is intentionally in memory for this phase. A later route/service
    integration may persist issues and remediation plans in MySQL.
    """

    def __init__(
        self,
        *,
        detector_config: DetectorConfig | None = None,
        preapproved_policies: Iterable[
            PreapprovedPolicy
        ] = (),
        minimum_recommendation_confidence: float = 0.70,
    ) -> None:
        self._lock = RLock()

        self._detector = IssueDetector(
            config=detector_config
        )

        self._policy_engine = (
            RemediationPolicyEngine(
                preapproved_policies=(
                    preapproved_policies
                )
            )
        )

        self._planner = RemediationPlanner(
            policy_engine=(
                self._policy_engine
            ),
            minimum_confidence=(
                minimum_recommendation_confidence
            ),
        )

        self._issues: dict[
            str,
            Issue,
        ] = {}

        self._remediations: dict[
            str,
            PreparedRemediation,
        ] = {}

        self._last_scan_id: str | None = None
        self._last_scan_time: str | None = None

    # ==========================================
    # Issue Scanning
    # ==========================================

    def scan_issues(
        self,
        *,
        devices: Iterable[
            Mapping[str, Any]
        ] = (),
        users: Iterable[
            Mapping[str, Any]
        ] = (),
        applications: Iterable[
            Mapping[str, Any]
        ] = (),
        jobs: Iterable[
            Mapping[str, Any]
        ] = (),
        audit_events: Iterable[
            Mapping[str, Any]
        ] = (),
        replace_existing: bool = True,
    ) -> IssueScanResult:
        device_rows = list(
            devices
        )
        user_rows = list(
            users
        )
        application_rows = list(
            applications
        )
        job_rows = list(
            jobs
        )
        audit_rows = list(
            audit_events
        )

        issues = self._detector.scan(
            devices=device_rows,
            users=user_rows,
            applications=application_rows,
            jobs=job_rows,
            audit_events=audit_rows,
        )

        scan_id = _new_scan_id()
        scanned_at = _utc_now_iso()

        with self._lock:
            if replace_existing:
                retained = {
                    issue_id:
                        issue
                    for issue_id, issue
                    in self._issues.items()
                    if issue.status
                    in {
                        IssueStatus
                        .REMEDIATION_PLANNED,

                        IssueStatus
                        .AWAITING_APPROVAL,

                        IssueStatus
                        .EXECUTING,

                        IssueStatus
                        .RESOLVED,

                        IssueStatus
                        .DISMISSED,
                    }
                }

                self._issues = retained

            for issue in issues:
                existing = self._issues.get(
                    str(
                        issue.issue_id
                    )
                )

                if existing is not None:
                    issue.status = (
                        existing.status
                    )

                self._issues[
                    str(
                        issue.issue_id
                    )
                ] = issue

            self._last_scan_id = scan_id
            self._last_scan_time = scanned_at

        counts: dict[
            str,
            int,
        ] = {
            severity.value:
                0
            for severity
            in Severity
        }

        for issue in issues:
            counts[
                issue.severity.value
            ] += 1

        return IssueScanResult(
            scan_id=scan_id,
            scanned_at=scanned_at,
            issues=issues,
            counts=counts,
            source_counts={
                "devices":
                    len(
                        device_rows
                    ),

                "users":
                    len(
                        user_rows
                    ),

                "applications":
                    len(
                        application_rows
                    ),

                "jobs":
                    len(
                        job_rows
                    ),

                "audit_events":
                    len(
                        audit_rows
                    ),
            },
        )

    # ==========================================
    # Issue Queries
    # ==========================================

    def list_issues(
        self,
        *,
        status: IssueStatus | str | None = None,
        severity: Severity | str | None = None,
        category: str | None = None,
        target_type: str | None = None,
        limit: int = 250,
    ) -> list[Issue]:
        try:
            safe_limit = int(
                limit
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise AgentInputError(
                "limit must be an integer."
            ) from error

        if safe_limit <= 0:
            raise AgentInputError(
                "limit must be greater than zero."
            )

        safe_limit = min(
            safe_limit,
            1000,
        )

        status_value = (
            IssueStatus(
                status
            )
            if status is not None
            else None
        )

        severity_value = (
            Severity(
                severity
            )
            if severity is not None
            else None
        )

        category_value = _clean_text(
            category,
            "category",
            required=False,
            maximum_length=100,
        )

        target_type_value = _clean_text(
            target_type,
            "target_type",
            required=False,
            maximum_length=100,
        )

        with self._lock:
            issues = list(
                self._issues.values()
            )

        filtered: list[
            Issue
        ] = []

        for issue in issues:
            if (
                status_value is not None
                and issue.status
                != status_value
            ):
                continue

            if (
                severity_value is not None
                and issue.severity
                != severity_value
            ):
                continue

            if (
                category_value is not None
                and issue.category
                != category_value
            ):
                continue

            if (
                target_type_value is not None
                and issue.target
                .target_type
                .value
                != target_type_value
            ):
                continue

            filtered.append(
                issue
            )

        severity_rank = {
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

        return sorted(
            filtered,
            key=lambda issue: (
                severity_rank[
                    issue.severity
                ],
                issue.detected_at,
            ),
            reverse=True,
        )[:safe_limit]

    def get_issue(
        self,
        issue_id: Any,
    ) -> Issue:
        cleaned_id = _clean_text(
            issue_id,
            "issue_id",
            maximum_length=64,
        )

        with self._lock:
            issue = self._issues.get(
                cleaned_id
            )

        if issue is None:
            raise IssueNotFoundError(
                "The requested issue was not found."
            )

        return issue

    def acknowledge_issue(
        self,
        issue_id: Any,
    ) -> Issue:
        return self._set_issue_status(
            issue_id,
            IssueStatus.ACKNOWLEDGED,
            allowed_from={
                IssueStatus.OPEN,
            },
        )

    def dismiss_issue(
        self,
        issue_id: Any,
    ) -> Issue:
        return self._set_issue_status(
            issue_id,
            IssueStatus.DISMISSED,
            allowed_from={
                IssueStatus.OPEN,
                IssueStatus.ACKNOWLEDGED,
                IssueStatus.FAILED,
            },
        )

    def mark_issue_resolved(
        self,
        issue_id: Any,
    ) -> Issue:
        return self._set_issue_status(
            issue_id,
            IssueStatus.RESOLVED,
            allowed_from={
                IssueStatus.REMEDIATION_PLANNED,
                IssueStatus.AWAITING_APPROVAL,
                IssueStatus.EXECUTING,
                IssueStatus.FAILED,
            },
        )

    # ==========================================
    # Remediation Planning
    # ==========================================

    def prepare_remediation(
        self,
        *,
        issue_id: Any,
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
        issue = self.get_issue(
            issue_id
        )

        if issue.status in {
            IssueStatus.RESOLVED,
            IssueStatus.DISMISSED,
        }:
            raise IssueStateError(
                "Resolved or dismissed issues cannot "
                "receive a new remediation plan."
            )

        prepared = self._planner.prepare(
            issue=issue,
            actor_roles=_clean_roles(
                actor_roles
            ),
            requested_action=(
                requested_action
            ),
            parameter_overrides=(
                parameter_overrides
            ),
            requested_preapproval_policy_id=(
                requested_preapproval_policy_id
            ),
        )

        with self._lock:
            self._remediations[
                prepared.remediation_id
            ] = prepared

            issue.status = (
                IssueStatus
                .AWAITING_APPROVAL
                if prepared.permission.allowed
                and prepared.permission
                .approval_mode
                .value
                != "none"
                else IssueStatus
                .REMEDIATION_PLANNED
            )

        return prepared

    def list_remediations(
        self,
        *,
        issue_id: str | None = None,
        limit: int = 250,
    ) -> list[PreparedRemediation]:
        try:
            safe_limit = int(
                limit
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise AgentInputError(
                "limit must be an integer."
            ) from error

        if safe_limit <= 0:
            raise AgentInputError(
                "limit must be greater than zero."
            )

        safe_limit = min(
            safe_limit,
            1000,
        )

        issue_filter = _clean_text(
            issue_id,
            "issue_id",
            required=False,
            maximum_length=64,
        )

        with self._lock:
            remediations = list(
                self._remediations.values()
            )

        if issue_filter is not None:
            remediations = [
                remediation
                for remediation
                in remediations
                if remediation.issue_id
                == issue_filter
            ]

        return remediations[
            :safe_limit
        ]

    def get_remediation(
        self,
        remediation_id: Any,
    ) -> PreparedRemediation:
        cleaned_id = _clean_text(
            remediation_id,
            "remediation_id",
            maximum_length=64,
        )

        with self._lock:
            remediation = (
                self._remediations
                .get(
                    cleaned_id
                )
            )

        if remediation is None:
            raise RemediationNotFoundError(
                "The requested remediation plan "
                "was not found."
            )

        return remediation

    def get_control_plan_request(
        self,
        remediation_id: Any,
    ) -> dict[str, Any]:
        remediation = self.get_remediation(
            remediation_id
        )

        if not remediation.permission.allowed:
            raise IssueStateError(
                "The remediation is not authorized "
                "for Control Panel planning."
            )

        if not remediation.ready_for_control_panel:
            raise IssueStateError(
                "The remediation is not ready for "
                "the protected Control Panel."
            )

        return dict(
            remediation.control_plan_request
        )

    # ==========================================
    # Snapshot
    # ==========================================

    def snapshot(
        self,
    ) -> AgentSnapshot:
        with self._lock:
            issues = list(
                self._issues.values()
            )

            remediations = list(
                self._remediations.values()
            )

            last_scan_id = (
                self._last_scan_id
            )

            last_scan_time = (
                self._last_scan_time
            )

        return AgentSnapshot(
            scan_id=last_scan_id,
            scanned_at=last_scan_time,
            issue_count=len(
                issues
            ),
            remediation_count=len(
                remediations
            ),
            open_issue_count=sum(
                1
                for issue
                in issues
                if issue.status
                in {
                    IssueStatus.OPEN,
                    IssueStatus.ACKNOWLEDGED,
                    IssueStatus.FAILED,
                }
            ),
            awaiting_approval_count=sum(
                1
                for issue
                in issues
                if issue.status
                == IssueStatus
                .AWAITING_APPROVAL
            ),
        )

    # ==========================================
    # Internal State Transition
    # ==========================================

    def _set_issue_status(
        self,
        issue_id: Any,
        new_status: IssueStatus,
        *,
        allowed_from: set[
            IssueStatus
        ],
    ) -> Issue:
        issue = self.get_issue(
            issue_id
        )

        with self._lock:
            if issue.status not in allowed_from:
                raise IssueStateError(
                    f"Issue status {issue.status.value} "
                    f"cannot transition to "
                    f"{new_status.value}."
                )

            issue.status = new_status

            return issue


_default_agent = LocalRemediationAgent()


def default_agent() -> LocalRemediationAgent:
    return _default_agent


def scan_current_issues(
    *,
    devices: Iterable[
        Mapping[str, Any]
    ] = (),
    users: Iterable[
        Mapping[str, Any]
    ] = (),
    applications: Iterable[
        Mapping[str, Any]
    ] = (),
    jobs: Iterable[
        Mapping[str, Any]
    ] = (),
    audit_events: Iterable[
        Mapping[str, Any]
    ] = (),
    replace_existing: bool = True,
) -> dict[str, Any]:
    return default_agent().scan_issues(
        devices=devices,
        users=users,
        applications=applications,
        jobs=jobs,
        audit_events=audit_events,
        replace_existing=replace_existing,
    ).to_dict()


def prepare_issue_remediation(
    *,
    issue_id: Any,
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
) -> dict[str, Any]:
    return default_agent().prepare_remediation(
        issue_id=issue_id,
        actor_roles=actor_roles,
        requested_action=requested_action,
        parameter_overrides=parameter_overrides,
        requested_preapproval_policy_id=(
            requested_preapproval_policy_id
        ),
    ).to_dict()