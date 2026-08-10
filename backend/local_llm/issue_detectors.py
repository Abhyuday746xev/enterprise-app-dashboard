from __future__ import annotations

"""
Deterministic issue detection for live Intune, Entra, Control Panel,
and audit data.

The local LLM may explain and rank these findings, but it is not used
to decide whether a simple rule is true.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from .remediation_models import (
    Issue,
    IssueTarget,
    RemediationAction,
    RemediationRecommendation,
    Severity,
    TargetType,
)


PERMISSION_ERROR_MARKERS = (
    "authorization_requestdenied",
    "insufficient privileges",
    "insufficient privilege",
    "forbidden",
    "access denied",
    "permission",
    "http 403",
    "status 403",
)


@dataclass(slots=True)
class DetectorConfig:
    stale_device_hours: int = 24
    critical_stale_device_hours: int = 168
    application_processing_hours: int = 6
    repeated_permission_error_threshold: int = 3
    include_disabled_users: bool = True

    def __post_init__(self) -> None:
        positive_fields = {
            "stale_device_hours":
                self.stale_device_hours,

            "critical_stale_device_hours":
                self.critical_stale_device_hours,

            "application_processing_hours":
                self.application_processing_hours,

            "repeated_permission_error_threshold":
                self.repeated_permission_error_threshold,
        }

        for name, value in positive_fields.items():
            if int(value) <= 0:
                raise ValueError(
                    f"{name} must be greater than zero."
                )

        if (
            self.critical_stale_device_hours
            < self.stale_device_hours
        ):
            raise ValueError(
                "critical_stale_device_hours must be "
                "greater than or equal to stale_device_hours."
            )


def _as_mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(
        value,
        Mapping,
    ):
        return value

    return {}


def _first_value(
    item: Mapping[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        value = item.get(
            key
        )

        if value not in {
            None,
            "",
        }:
            return value

    return default


def _text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _normalized(
    value: Any,
) -> str:
    return _text(
        value
    ).lower()


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        parsed = value
    else:
        raw = _text(
            value
        )

        if not raw:
            return None

        if raw.endswith(
            "Z"
        ):
            raw = (
                raw[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                raw
            )
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _age_hours(
    value: Any,
    *,
    now: datetime,
) -> float | None:
    parsed = _parse_datetime(
        value
    )

    if parsed is None:
        return None

    delta = (
        now
        - parsed
    )

    return max(
        0.0,
        delta.total_seconds()
        / 3600.0,
    )


def _device_target(
    device: Mapping[str, Any],
) -> IssueTarget:
    device_id = _text(
        _first_value(
            device,
            "id",
            "managedDeviceId",
            "device_id",
            default="unknown-device",
        )
    )

    device_name = _text(
        _first_value(
            device,
            "deviceName",
            "managedDeviceName",
            "name",
            default=device_id,
        )
    )

    user_name = _text(
        _first_value(
            device,
            "userPrincipalName",
            "userDisplayName",
            "email",
            default="",
        )
    )

    return IssueTarget(
        target_type=TargetType.DEVICE,
        target_id=device_id,
        name=device_name,
        secondary_name=(
            user_name
            or None
        ),
        metadata={
            "operating_system":
                _first_value(
                    device,
                    "operatingSystem",
                    "os",
                ),

            "model":
                _first_value(
                    device,
                    "model",
                    "deviceModel",
                ),
        },
    )


def _application_target(
    application: Mapping[str, Any],
) -> IssueTarget:
    application_id = _text(
        _first_value(
            application,
            "id",
            "application_id",
            default="unknown-application",
        )
    )

    display_name = _text(
        _first_value(
            application,
            "displayName",
            "name",
            default=application_id,
        )
    )

    return IssueTarget(
        target_type=TargetType.APPLICATION,
        target_id=application_id,
        name=display_name,
        secondary_name=(
            _text(
                _first_value(
                    application,
                    "publisher",
                    default="",
                )
            )
            or None
        ),
    )


def _user_target(
    user: Mapping[str, Any],
) -> IssueTarget:
    user_id = _text(
        _first_value(
            user,
            "id",
            "user_id",
            default="unknown-user",
        )
    )

    display_name = _text(
        _first_value(
            user,
            "displayName",
            "name",
            default=user_id,
        )
    )

    principal_name = _text(
        _first_value(
            user,
            "userPrincipalName",
            "mail",
            "email",
            default="",
        )
    )

    return IssueTarget(
        target_type=TargetType.USER,
        target_id=user_id,
        name=display_name,
        secondary_name=(
            principal_name
            or None
        ),
    )


def _job_target(
    job: Mapping[str, Any],
) -> IssueTarget:
    job_id = _text(
        _first_value(
            job,
            "action_id",
            "job_id",
            "confirmation_id",
            "id",
            default="unknown-job",
        )
    )

    target_name = _text(
        _first_value(
            job,
            "target_name",
            "targetName",
            "target_id",
            default=job_id,
        )
    )

    return IssueTarget(
        target_type=TargetType.CONTROL_JOB,
        target_id=job_id,
        name=target_name,
        secondary_name=(
            _text(
                _first_value(
                    job,
                    "action_type",
                    "action",
                    default="",
                )
            )
            or None
        ),
    )


class IssueDetector:
    def __init__(
        self,
        config: DetectorConfig | None = None,
    ) -> None:
        self.config = (
            config
            or DetectorConfig()
        )

    def scan(
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
        now: datetime | None = None,
    ) -> list[Issue]:
        current_time = (
            now
            or datetime.now(
                timezone.utc
            )
        )

        if current_time.tzinfo is None:
            current_time = current_time.replace(
                tzinfo=timezone.utc
            )

        issues: list[Issue] = []

        device_rows = [
            _as_mapping(
                item
            )
            for item in devices
        ]

        user_rows = [
            _as_mapping(
                item
            )
            for item in users
        ]

        application_rows = [
            _as_mapping(
                item
            )
            for item in applications
        ]

        job_rows = [
            _as_mapping(
                item
            )
            for item in jobs
        ]

        audit_rows = [
            _as_mapping(
                item
            )
            for item in audit_events
        ]

        issues.extend(
            self.detect_device_issues(
                device_rows,
                now=current_time,
            )
        )

        issues.extend(
            self.detect_user_issues(
                user_rows
            )
        )

        issues.extend(
            self.detect_application_issues(
                application_rows,
                now=current_time,
            )
        )

        issues.extend(
            self.detect_job_issues(
                job_rows
            )
        )

        issues.extend(
            self.detect_permission_issues(
                audit_rows
            )
        )

        unique: dict[
            str,
            Issue,
        ] = {}

        for issue in issues:
            unique[
                str(
                    issue.issue_id
                )
            ] = issue

        return sorted(
            unique.values(),
            key=lambda issue: (
                self._severity_rank(
                    issue.severity
                ),
                issue.detected_at,
            ),
            reverse=True,
        )

    def detect_device_issues(
        self,
        devices: Sequence[
            Mapping[str, Any]
        ],
        *,
        now: datetime,
    ) -> list[Issue]:
        issues: list[Issue] = []

        for device in devices:
            target = _device_target(
                device
            )

            compliance = _normalized(
                _first_value(
                    device,
                    "complianceState",
                    "compliance_state",
                    default="unknown",
                )
            )

            last_sync = _first_value(
                device,
                "lastSyncDateTime",
                "last_sync_date_time",
                "lastSync",
            )

            sync_age = _age_hours(
                last_sync,
                now=now,
            )

            if compliance in {
                "noncompliant",
                "non-compliant",
                "notcompliant",
            }:
                issues.append(
                    Issue(
                        category=(
                            "noncompliant_device"
                        ),
                        severity=Severity.HIGH,
                        title=(
                            "Managed device is non-compliant"
                        ),
                        description=(
                            f"{target.name} currently reports a "
                            "non-compliant Intune state."
                        ),
                        target=target,
                        evidence={
                            "compliance_state":
                                compliance,

                            "last_sync_date_time":
                                last_sync,

                            "last_sync_age_hours":
                                (
                                    round(
                                        sync_age,
                                        2,
                                    )
                                    if sync_age
                                    is not None
                                    else None
                                ),
                        },
                        recommendations=[
                            RemediationRecommendation(
                                action=(
                                    RemediationAction
                                    .SYNC_DEVICE
                                ),
                                reason=(
                                    "Request fresh Intune state "
                                    "before considering a more "
                                    "disruptive remediation."
                                ),
                                expected_result=(
                                    "Intune accepts a managed-device "
                                    "synchronization request."
                                ),
                                risk=Severity.LOW,
                                confidence=0.95,
                            )
                        ],
                        tags=[
                            "intune",
                            "device",
                            "compliance",
                        ],
                    )
                )

            elif compliance in {
                "",
                "unknown",
                "notapplicable",
                "not applicable",
                "configmanager",
            }:
                issues.append(
                    Issue(
                        category=(
                            "unknown_compliance_device"
                        ),
                        severity=Severity.MEDIUM,
                        title=(
                            "Device compliance state is unknown"
                        ),
                        description=(
                            f"{target.name} does not currently "
                            "report a clear compliant or "
                            "non-compliant state."
                        ),
                        target=target,
                        evidence={
                            "compliance_state":
                                compliance
                                or "unknown",

                            "last_sync_date_time":
                                last_sync,
                        },
                        recommendations=[
                            RemediationRecommendation(
                                action=(
                                    RemediationAction
                                    .SYNC_DEVICE
                                ),
                                reason=(
                                    "A fresh synchronization may "
                                    "update the reported state."
                                ),
                                expected_result=(
                                    "Intune accepts a managed-device "
                                    "synchronization request."
                                ),
                                risk=Severity.LOW,
                                confidence=0.8,
                            )
                        ],
                        tags=[
                            "intune",
                            "device",
                            "unknown_state",
                        ],
                    )
                )

            if (
                sync_age is not None
                and sync_age
                >= self.config.stale_device_hours
            ):
                severity = (
                    Severity.HIGH
                    if sync_age
                    >= self.config
                    .critical_stale_device_hours
                    else Severity.MEDIUM
                )

                issues.append(
                    Issue(
                        category=(
                            "stale_device_sync"
                        ),
                        severity=severity,
                        title=(
                            "Managed device has stale Intune data"
                        ),
                        description=(
                            f"{target.name} has not synchronized "
                            f"for approximately {sync_age:.1f} hours."
                        ),
                        target=target,
                        evidence={
                            "last_sync_date_time":
                                last_sync,

                            "last_sync_age_hours":
                                round(
                                    sync_age,
                                    2,
                                ),

                            "threshold_hours":
                                self.config
                                .stale_device_hours,
                        },
                        recommendations=[
                            RemediationRecommendation(
                                action=(
                                    RemediationAction
                                    .SYNC_DEVICE
                                ),
                                reason=(
                                    "Request a current inventory and "
                                    "compliance check-in."
                                ),
                                expected_result=(
                                    "Intune accepts a synchronization "
                                    "request for the exact device."
                                ),
                                risk=Severity.LOW,
                                confidence=0.98,
                            )
                        ],
                        tags=[
                            "intune",
                            "device",
                            "stale_sync",
                        ],
                    )
                )

        return issues

    def detect_user_issues(
        self,
        users: Sequence[
            Mapping[str, Any]
        ],
    ) -> list[Issue]:
        if not self.config.include_disabled_users:
            return []

        issues: list[Issue] = []

        for user in users:
            enabled_value = _first_value(
                user,
                "accountEnabled",
                "account_enabled",
            )

            is_disabled = (
                enabled_value is False
                or _normalized(
                    enabled_value
                )
                in {
                    "false",
                    "disabled",
                    "0",
                }
            )

            if not is_disabled:
                continue

            target = _user_target(
                user
            )

            issues.append(
                Issue(
                    category=(
                        "disabled_user"
                    ),
                    severity=Severity.INFO,
                    title=(
                        "User account is disabled"
                    ),
                    description=(
                        f"{target.name} is disabled. This may be "
                        "intentional and is not automatically "
                        "treated as a fault."
                    ),
                    target=target,
                    evidence={
                        "account_enabled":
                            False,
                    },
                    recommendations=[],
                    tags=[
                        "entra",
                        "user",
                        "informational",
                    ],
                )
            )

        return issues

    def detect_application_issues(
        self,
        applications: Sequence[
            Mapping[str, Any]
        ],
        *,
        now: datetime,
    ) -> list[Issue]:
        issues: list[Issue] = []

        for application in applications:
            state = _normalized(
                _first_value(
                    application,
                    "publishingState",
                    "publishing_state",
                    "state",
                    default="unknown",
                )
            )

            if state not in {
                "processing",
                "publishing",
                "uploading",
            }:
                continue

            changed_at = _first_value(
                application,
                "lastModifiedDateTime",
                "last_modified_date_time",
                "createdDateTime",
                "created_at",
            )

            processing_age = _age_hours(
                changed_at,
                now=now,
            )

            if (
                processing_age is None
                or processing_age
                < self.config
                .application_processing_hours
            ):
                continue

            target = _application_target(
                application
            )

            issues.append(
                Issue(
                    category=(
                        "application_processing_too_long"
                    ),
                    severity=Severity.MEDIUM,
                    title=(
                        "Application publishing is taking too long"
                    ),
                    description=(
                        f"{target.name} has remained in "
                        f"{state} state for approximately "
                        f"{processing_age:.1f} hours."
                    ),
                    target=target,
                    evidence={
                        "publishing_state":
                            state,

                        "last_changed_at":
                            changed_at,

                        "processing_age_hours":
                            round(
                                processing_age,
                                2,
                            ),

                        "threshold_hours":
                            self.config
                            .application_processing_hours,
                    },
                    recommendations=[],
                    tags=[
                        "intune",
                        "application",
                        "publishing",
                    ],
                )
            )

        return issues

    def detect_job_issues(
        self,
        jobs: Sequence[
            Mapping[str, Any]
        ],
    ) -> list[Issue]:
        issues: list[Issue] = []

        for job in jobs:
            status = _normalized(
                _first_value(
                    job,
                    "status",
                    default="unknown",
                )
            )

            if status not in {
                "failed",
                "expired",
            }:
                continue

            target = _job_target(
                job
            )

            action_type = _text(
                _first_value(
                    job,
                    "action_type",
                    "action",
                    default="unknown",
                )
            )

            error_message = _text(
                _first_value(
                    job,
                    "error_message",
                    "error",
                    "message",
                    default="",
                )
            )

            category = (
                "failed_control_job"
                if status == "failed"
                else "expired_control_job"
            )

            severity = (
                Severity.HIGH
                if status == "failed"
                else Severity.MEDIUM
            )

            issues.append(
                Issue(
                    category=category,
                    severity=severity,
                    title=(
                        "Protected Control Panel action failed"
                        if status == "failed"
                        else "Protected action expired"
                    ),
                    description=(
                        f"The {action_type} action for "
                        f"{target.name} ended with status "
                        f"{status}."
                    ),
                    target=target,
                    evidence={
                        "status":
                            status,

                        "action_type":
                            action_type,

                        "error_message":
                            error_message
                            or None,

                        "created_at":
                            _first_value(
                                job,
                                "created_at",
                                "createdAt",
                            ),

                        "completed_at":
                            _first_value(
                                job,
                                "completed_at",
                                "completedAt",
                            ),
                    },
                    recommendations=[],
                    tags=[
                        "control_panel",
                        "job",
                        status,
                    ],
                )
            )

            if (
                status == "failed"
                and action_type
                == RemediationAction
                .ASSIGN_APPLICATION_GROUP
                .value
            ):
                issues.append(
                    Issue(
                        category=(
                            "failed_application_assignment"
                        ),
                        severity=Severity.HIGH,
                        title=(
                            "Application assignment action failed"
                        ),
                        description=(
                            f"The assignment operation for "
                            f"{target.name} did not complete."
                        ),
                        target=target,
                        evidence={
                            "action_type":
                                action_type,

                            "error_message":
                                error_message
                                or None,
                        },
                        recommendations=[],
                        tags=[
                            "intune",
                            "application",
                            "assignment",
                        ],
                    )
                )

        return issues

    def detect_permission_issues(
        self,
        audit_events: Sequence[
            Mapping[str, Any]
        ],
    ) -> list[Issue]:
        matching_events: list[
            Mapping[str, Any]
        ] = []

        for event in audit_events:
            error_text = " ".join([
                _text(
                    _first_value(
                        event,
                        "error_message",
                        "message",
                        default="",
                    )
                ),
                _text(
                    _first_value(
                        event,
                        "result_data",
                        "result",
                        default="",
                    )
                ),
            ]).lower()

            if any(
                marker in error_text
                for marker
                in PERMISSION_ERROR_MARKERS
            ):
                matching_events.append(
                    event
                )

        if (
            len(
                matching_events
            )
            < self.config
            .repeated_permission_error_threshold
        ):
            return []

        action_types = sorted({
            _text(
                _first_value(
                    event,
                    "action_type",
                    "action",
                    default="unknown",
                )
            )
            for event in matching_events
        })

        return [
            Issue(
                category=(
                    "repeated_graph_permission_error"
                ),
                severity=Severity.HIGH,
                title=(
                    "Repeated Microsoft Graph permission failures"
                ),
                description=(
                    "Multiple recent Control Panel operations "
                    "reported authorization or permission errors."
                ),
                target=IssueTarget(
                    target_type=TargetType.SYSTEM,
                    target_id=(
                        "microsoft-graph-permissions"
                    ),
                    name=(
                        "Microsoft Graph permissions"
                    ),
                ),
                evidence={
                    "matching_event_count":
                        len(
                            matching_events
                        ),

                    "threshold":
                        self.config
                        .repeated_permission_error_threshold,

                    "action_types":
                        action_types,
                },
                recommendations=[],
                tags=[
                    "graph",
                    "permissions",
                    "authorization",
                ],
            )
        ]

    @staticmethod
    def _severity_rank(
        severity: Severity,
    ) -> int:
        ranking = {
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

        return ranking[
            severity
        ]


def scan_issues(
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
    config: DetectorConfig | None = None,
) -> list[dict[str, Any]]:
    detector = IssueDetector(
        config=config
    )

    return [
        issue.to_dict()
        for issue
        in detector.scan(
            devices=devices,
            users=users,
            applications=applications,
            jobs=jobs,
            audit_events=audit_events,
        )
    ]