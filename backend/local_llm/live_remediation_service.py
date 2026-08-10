from __future__ import annotations

"""
Read-only live inventory bridge for the local remediation agent.

The language model never receives Graph credentials and never performs
Microsoft Graph writes. This module only loads inventory and passes it to
LocalRemediationAgent for issue detection and safe plan preparation.
"""

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Iterable, Mapping, Sequence

from .agent_service import LocalRemediationAgent, default_agent
from .remediation_models import RemediationAction
from .remediation_planner import PreparedRemediation


class LiveRemediationError(RuntimeError):
    pass


class ProviderNotFoundError(LiveRemediationError):
    pass


class ProviderResultError(LiveRemediationError):
    pass


InventoryCallable = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class LiveInventoryProvider:
    users: InventoryCallable
    devices: InventoryCallable
    applications: InventoryCallable
    jobs: InventoryCallable | None = None
    audit_events: InventoryCallable | None = None


@dataclass(slots=True)
class InventorySnapshot:
    users: list[Mapping[str, Any]]
    devices: list[Mapping[str, Any]]
    applications: list[Mapping[str, Any]]
    jobs: list[Mapping[str, Any]]
    audit_events: list[Mapping[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": {
                "users": len(self.users),
                "devices": len(self.devices),
                "applications": len(self.applications),
                "jobs": len(self.jobs),
                "audit_events": len(self.audit_events),
            },
            "users": list(self.users),
            "devices": list(self.devices),
            "applications": list(self.applications),
            "jobs": list(self.jobs),
            "audit_events": list(self.audit_events),
        }


_PROVIDER_NAMES: dict[str, tuple[str, ...]] = {
    "users": (
        "get_users",
        "list_users",
        "fetch_users",
        "get_all_users",
        "get_live_users",
    ),
    "devices": (
        "get_devices",
        "list_devices",
        "fetch_devices",
        "get_managed_devices",
        "list_managed_devices",
        "get_live_devices",
    ),
    "applications": (
        "get_applications",
        "list_applications",
        "fetch_applications",
        "get_mobile_apps",
        "list_mobile_apps",
        "get_live_applications",
    ),
    "jobs": (
        "get_control_jobs",
        "list_control_jobs",
        "get_jobs",
        "list_jobs",
    ),
    "audit_events": (
        "get_control_audit",
        "list_control_audit",
        "get_audit_events",
        "list_audit_events",
    ),
}

_COLLECTION_KEYS = (
    "items",
    "value",
    "results",
    "data",
    "users",
    "devices",
    "applications",
    "apps",
    "jobs",
    "events",
    "audit_events",
)


def _find_callable(
    source: Any,
    names: Sequence[str],
) -> InventoryCallable | None:
    for name in names:
        value = getattr(source, name, None)

        if callable(value):
            return value

    return None


def _normalize_rows(
    value: Any,
    provider_name: str,
) -> list[Mapping[str, Any]]:
    current = value

    for _ in range(5):
        if current is None:
            return []

        if isinstance(current, (list, tuple)):
            rows = list(current)

            if not all(isinstance(row, Mapping) for row in rows):
                raise ProviderResultError(
                    f"{provider_name} returned non-object rows."
                )

            return rows

        if isinstance(current, Mapping):
            if current.get("success") is False:
                raise ProviderResultError(
                    f"{provider_name} failed: "
                    f"{current.get('message') or current.get('error') or 'unknown error'}"
                )

            for key in _COLLECTION_KEYS:
                if key in current and current[key] is not current:
                    current = current[key]
                    break
            else:
                raise ProviderResultError(
                    f"{provider_name} returned an unsupported object."
                )

            continue

        for key in _COLLECTION_KEYS:
            if hasattr(current, key):
                candidate = getattr(current, key)

                if not callable(candidate):
                    current = candidate
                    break
        else:
            raise ProviderResultError(
                f"{provider_name} returned unsupported type "
                f"{type(current).__name__}."
            )

    raise ProviderResultError(
        f"{provider_name} returned too many nested wrappers."
    )


def _run_provider(
    provider: InventoryCallable | None,
    provider_name: str,
    *,
    required: bool,
) -> list[Mapping[str, Any]]:
    if provider is None:
        if required:
            raise ProviderNotFoundError(
                f"No provider is configured for {provider_name}."
            )

        return []

    try:
        result = provider()
    except TypeError as error:
        raise ProviderResultError(
            f"{provider_name} must be a zero-argument callable. "
            "Wrap parameterized functions in a lambda."
        ) from error
    except Exception as error:
        raise LiveRemediationError(
            f"{provider_name} provider failed: {error}"
        ) from error

    return _normalize_rows(result, provider_name)


def provider_from_source(source: Any) -> LiveInventoryProvider:
    users = _find_callable(source, _PROVIDER_NAMES["users"])
    devices = _find_callable(source, _PROVIDER_NAMES["devices"])
    applications = _find_callable(
        source,
        _PROVIDER_NAMES["applications"],
    )

    missing = [
        name
        for name, provider in (
            ("users", users),
            ("devices", devices),
            ("applications", applications),
        )
        if provider is None
    ]

    if missing:
        raise ProviderNotFoundError(
            "Could not discover provider functions for: "
            + ", ".join(missing)
            + ". Construct LiveInventoryProvider explicitly."
        )

    return LiveInventoryProvider(
        users=users,
        devices=devices,
        applications=applications,
        jobs=_find_callable(source, _PROVIDER_NAMES["jobs"]),
        audit_events=_find_callable(
            source,
            _PROVIDER_NAMES["audit_events"],
        ),
    )


def provider_from_live_intune_tools() -> LiveInventoryProvider:
    module = import_module("local_llm.live_intune_tools")
    return provider_from_source(module)


class LiveRemediationService:
    def __init__(
        self,
        provider: LiveInventoryProvider,
        *,
        agent: LocalRemediationAgent | None = None,
    ) -> None:
        self.provider = provider
        self.agent = agent or default_agent()

    def load_inventory(self) -> InventorySnapshot:
        return InventorySnapshot(
            users=_run_provider(
                self.provider.users,
                "users",
                required=True,
            ),
            devices=_run_provider(
                self.provider.devices,
                "devices",
                required=True,
            ),
            applications=_run_provider(
                self.provider.applications,
                "applications",
                required=True,
            ),
            jobs=_run_provider(
                self.provider.jobs,
                "jobs",
                required=False,
            ),
            audit_events=_run_provider(
                self.provider.audit_events,
                "audit_events",
                required=False,
            ),
        )

    def scan_live_issues(
        self,
        *,
        replace_existing: bool = True,
    ) -> dict[str, Any]:
        inventory = self.load_inventory()

        scan = self.agent.scan_issues(
            users=inventory.users,
            devices=inventory.devices,
            applications=inventory.applications,
            jobs=inventory.jobs,
            audit_events=inventory.audit_events,
            replace_existing=replace_existing,
        )

        return {
            "inventory": inventory.to_dict(),
            "scan": scan.to_dict(),
        }

    def prepare_issue_remediation(
        self,
        *,
        issue_id: str,
        actor_roles: Iterable[str],
        requested_action: RemediationAction | str | None = None,
        parameter_overrides: Mapping[str, Any] | None = None,
        requested_preapproval_policy_id: str | None = None,
    ) -> PreparedRemediation:
        return self.agent.prepare_remediation(
            issue_id=issue_id,
            actor_roles=actor_roles,
            requested_action=requested_action,
            parameter_overrides=parameter_overrides,
            requested_preapproval_policy_id=(
                requested_preapproval_policy_id
            ),
        )

    def prepare_recommended_remediations(
        self,
        *,
        actor_roles: Iterable[str],
        maximum_plans: int = 25,
    ) -> dict[str, Any]:
        maximum = max(1, min(int(maximum_plans), 100))
        prepared: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for issue in self.agent.list_issues(limit=1000):
            if len(prepared) >= maximum:
                break

            if not issue.recommendations:
                skipped.append({
                    "issue_id": issue.issue_id,
                    "reason": "No allowlisted remediation is available.",
                })
                continue

            try:
                plan = self.agent.prepare_remediation(
                    issue_id=issue.issue_id,
                    actor_roles=actor_roles,
                )
            except Exception as error:
                skipped.append({
                    "issue_id": issue.issue_id,
                    "reason": str(error),
                })
                continue

            if not plan.permission.allowed:
                skipped.append({
                    "issue_id": issue.issue_id,
                    "reason": plan.permission.reason,
                })
                continue

            prepared.append(plan.to_dict())

        return {
            "prepared_count": len(prepared),
            "skipped_count": len(skipped),
            "prepared": prepared,
            "skipped": skipped,
        }


_default_service: LiveRemediationService | None = None


def default_live_service() -> LiveRemediationService:
    global _default_service

    if _default_service is None:
        _default_service = LiveRemediationService(
            provider_from_live_intune_tools()
        )

    return _default_service


def scan_live_issues(
    *,
    replace_existing: bool = True,
) -> dict[str, Any]:
    return default_live_service().scan_live_issues(
        replace_existing=replace_existing
    )