from __future__ import annotations

"""
Permission and approval policy for local AI remediations.

The local LLM must never decide authorization. This module makes
deterministic decisions from trusted application roles and fixed
action policies.
"""

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .remediation_models import (
    ApprovalMode,
    PermissionDecision,
    RemediationAction,
)


class RemediationPermissionError(
    PermissionError
):
    """Raised when an actor cannot perform the requested action."""


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    action: RemediationAction
    approval_mode: ApprovalMode
    confirmation_phrase: str | None
    maximum_targets: int
    preapproval_allowed: bool
    minimum_role: str
    description: str


ACTION_POLICIES: dict[
    RemediationAction,
    ActionPolicy,
] = {
    RemediationAction.SYNC_DEVICE:
        ActionPolicy(
            action=(
                RemediationAction
                .SYNC_DEVICE
            ),
            approval_mode=(
                ApprovalMode
                .PREAPPROVED_OR_SINGLE
            ),
            confirmation_phrase=None,
            maximum_targets=5,
            preapproval_allowed=True,
            minimum_role="operator",
            description=(
                "Request an Intune managed-device synchronization."
            ),
        ),

    RemediationAction.RESTART_DEVICE:
        ActionPolicy(
            action=(
                RemediationAction
                .RESTART_DEVICE
            ),
            approval_mode=(
                ApprovalMode
                .TYPED_CONFIRMATION
            ),
            confirmation_phrase=(
                "RESTART"
            ),
            maximum_targets=1,
            preapproval_allowed=False,
            minimum_role="device_admin",
            description=(
                "Request an Intune managed-device reboot."
            ),
        ),

    RemediationAction.ENABLE_USER:
        ActionPolicy(
            action=(
                RemediationAction
                .ENABLE_USER
            ),
            approval_mode=(
                ApprovalMode
                .TYPED_CONFIRMATION
            ),
            confirmation_phrase=(
                "CONFIRM"
            ),
            maximum_targets=1,
            preapproval_allowed=False,
            minimum_role="user_admin",
            description=(
                "Enable a Microsoft Entra user account."
            ),
        ),

    RemediationAction.DISABLE_USER:
        ActionPolicy(
            action=(
                RemediationAction
                .DISABLE_USER
            ),
            approval_mode=(
                ApprovalMode
                .TYPED_CONFIRMATION
            ),
            confirmation_phrase=(
                "DISABLE"
            ),
            maximum_targets=1,
            preapproval_allowed=False,
            minimum_role="user_admin",
            description=(
                "Disable a Microsoft Entra user account."
            ),
        ),

    RemediationAction.ASSIGN_APPLICATION_GROUP:
        ActionPolicy(
            action=(
                RemediationAction
                .ASSIGN_APPLICATION_GROUP
            ),
            approval_mode=(
                ApprovalMode
                .TYPED_CONFIRMATION
            ),
            confirmation_phrase=(
                "ASSIGN"
            ),
            maximum_targets=1,
            preapproval_allowed=False,
            minimum_role=(
                "application_admin"
            ),
            description=(
                "Assign a published Win32 application "
                "to an exact Microsoft Entra group."
            ),
        ),

    RemediationAction.DELETE_APPLICATION_ASSIGNMENT:
        ActionPolicy(
            action=(
                RemediationAction
                .DELETE_APPLICATION_ASSIGNMENT
            ),
            approval_mode=(
                ApprovalMode
                .TYPED_CONFIRMATION
            ),
            confirmation_phrase=(
                "REMOVE"
            ),
            maximum_targets=1,
            preapproval_allowed=False,
            minimum_role=(
                "application_admin"
            ),
            description=(
                "Remove one exact Intune application assignment."
            ),
        ),

    RemediationAction.DELETE_APPLICATION:
        ActionPolicy(
            action=(
                RemediationAction
                .DELETE_APPLICATION
            ),
            approval_mode=(
                ApprovalMode
                .TYPED_CONFIRMATION
            ),
            confirmation_phrase=(
                "DELETE"
            ),
            maximum_targets=1,
            preapproval_allowed=False,
            minimum_role=(
                "control_admin"
            ),
            description=(
                "Delete an unassigned Intune application."
            ),
        ),
}


ROLE_ACTIONS: dict[
    str,
    frozenset[
        RemediationAction
    ],
] = {
    "viewer":
        frozenset(),

    "operator":
        frozenset({
            RemediationAction
            .SYNC_DEVICE,
        }),

    "device_admin":
        frozenset({
            RemediationAction
            .SYNC_DEVICE,

            RemediationAction
            .RESTART_DEVICE,
        }),

    "user_admin":
        frozenset({
            RemediationAction
            .ENABLE_USER,

            RemediationAction
            .DISABLE_USER,
        }),

    "application_admin":
        frozenset({
            RemediationAction
            .ASSIGN_APPLICATION_GROUP,

            RemediationAction
            .DELETE_APPLICATION_ASSIGNMENT,
        }),

    "control_admin":
        frozenset(
            RemediationAction
        ),
}


@dataclass(frozen=True, slots=True)
class PreapprovedPolicy:
    policy_id: str
    action: RemediationAction
    enabled: bool = True
    maximum_targets: int = 1
    allowed_target_ids: frozenset[
        str
    ] = frozenset()

    def allows(
        self,
        *,
        action: RemediationAction,
        target_ids: Iterable[str],
    ) -> bool:
        if not self.enabled:
            return False

        if self.action != action:
            return False

        cleaned_targets = [
            str(target_id).strip()
            for target_id in target_ids
            if str(target_id).strip()
        ]

        if (
            not cleaned_targets
            or len(cleaned_targets)
            > self.maximum_targets
        ):
            return False

        if not self.allowed_target_ids:
            return True

        return all(
            target_id
            in self.allowed_target_ids
            for target_id
            in cleaned_targets
        )


class RemediationPolicyEngine:
    def __init__(
        self,
        *,
        role_actions: Mapping[
            str,
            frozenset[
                RemediationAction
            ],
        ] | None = None,
        action_policies: Mapping[
            RemediationAction,
            ActionPolicy,
        ] | None = None,
        preapproved_policies: Iterable[
            PreapprovedPolicy
        ] = (),
    ) -> None:
        self.role_actions = dict(
            role_actions
            or ROLE_ACTIONS
        )

        self.action_policies = dict(
            action_policies
            or ACTION_POLICIES
        )

        self.preapproved_policies = {
            policy.policy_id:
                policy
            for policy
            in preapproved_policies
        }

    def authorize(
        self,
        *,
        actor_roles: Iterable[str],
        action: RemediationAction | str,
        target_ids: Iterable[str],
        requested_preapproval_policy_id: str | None = None,
    ) -> PermissionDecision:
        action_enum = RemediationAction(
            action
        )

        cleaned_roles = {
            str(role).strip().lower()
            for role
            in actor_roles
            if str(role).strip()
        }

        cleaned_targets = [
            str(target_id).strip()
            for target_id
            in target_ids
            if str(target_id).strip()
        ]

        policy = self.action_policies.get(
            action_enum
        )

        if policy is None:
            return PermissionDecision(
                allowed=False,
                action=action_enum,
                approval_mode=(
                    ApprovalMode
                    .BLOCKED
                ),
                reason=(
                    "The action does not have a fixed "
                    "remediation policy."
                ),
                maximum_targets=1,
            )

        if not cleaned_targets:
            return PermissionDecision(
                allowed=False,
                action=action_enum,
                approval_mode=(
                    ApprovalMode
                    .BLOCKED
                ),
                reason=(
                    "At least one exact target ID is required."
                ),
                required_role=(
                    policy.minimum_role
                ),
                maximum_targets=(
                    policy.maximum_targets
                ),
            )

        if (
            len(
                cleaned_targets
            )
            > policy.maximum_targets
        ):
            return PermissionDecision(
                allowed=False,
                action=action_enum,
                approval_mode=(
                    ApprovalMode
                    .BLOCKED
                ),
                reason=(
                    f"{action_enum.value} supports at most "
                    f"{policy.maximum_targets} target(s) per request."
                ),
                required_role=(
                    policy.minimum_role
                ),
                maximum_targets=(
                    policy.maximum_targets
                ),
            )

        permitted_actions: set[
            RemediationAction
        ] = set()

        for role in cleaned_roles:
            permitted_actions.update(
                self.role_actions.get(
                    role,
                    frozenset(),
                )
            )

        if action_enum not in permitted_actions:
            return PermissionDecision(
                allowed=False,
                action=action_enum,
                approval_mode=(
                    ApprovalMode
                    .BLOCKED
                ),
                reason=(
                    "The current administrator does not "
                    "have an application role that permits "
                    f"{action_enum.value}."
                ),
                required_role=(
                    policy.minimum_role
                ),
                maximum_targets=(
                    policy.maximum_targets
                ),
            )

        if requested_preapproval_policy_id:
            preapproval = (
                self.preapproved_policies
                .get(
                    requested_preapproval_policy_id
                )
            )

            if preapproval is None:
                return PermissionDecision(
                    allowed=False,
                    action=action_enum,
                    approval_mode=(
                        ApprovalMode
                        .BLOCKED
                    ),
                    reason=(
                        "The requested preapproval policy "
                        "does not exist."
                    ),
                    required_role=(
                        policy.minimum_role
                    ),
                    maximum_targets=(
                        policy.maximum_targets
                    ),
                )

            if not policy.preapproval_allowed:
                return PermissionDecision(
                    allowed=False,
                    action=action_enum,
                    approval_mode=(
                        ApprovalMode
                        .BLOCKED
                    ),
                    reason=(
                        f"{action_enum.value} cannot use "
                        "preapproved execution."
                    ),
                    required_role=(
                        policy.minimum_role
                    ),
                    maximum_targets=(
                        policy.maximum_targets
                    ),
                )

            if not preapproval.allows(
                action=action_enum,
                target_ids=cleaned_targets,
            ):
                return PermissionDecision(
                    allowed=False,
                    action=action_enum,
                    approval_mode=(
                        ApprovalMode
                        .BLOCKED
                    ),
                    reason=(
                        "The requested preapproval policy "
                        "does not cover this action and "
                        "target set."
                    ),
                    required_role=(
                        policy.minimum_role
                    ),
                    maximum_targets=(
                        policy.maximum_targets
                    ),
                )

            return PermissionDecision(
                allowed=True,
                action=action_enum,
                approval_mode=(
                    ApprovalMode.NONE
                ),
                reason=(
                    "The administrator role and fixed "
                    "preapproval policy permit this action."
                ),
                required_role=(
                    policy.minimum_role
                ),
                confirmation_phrase=None,
                policy_id=(
                    preapproval.policy_id
                ),
                maximum_targets=(
                    min(
                        policy.maximum_targets,
                        preapproval
                        .maximum_targets,
                    )
                ),
            )

        return PermissionDecision(
            allowed=True,
            action=action_enum,
            approval_mode=(
                policy.approval_mode
            ),
            reason=(
                "The administrator role permits the action. "
                "The configured approval policy must be "
                "satisfied before execution."
            ),
            required_role=(
                policy.minimum_role
            ),
            confirmation_phrase=(
                policy.confirmation_phrase
            ),
            maximum_targets=(
                policy.maximum_targets
            ),
        )

    def assert_authorized(
        self,
        **kwargs: Any,
    ) -> PermissionDecision:
        decision = self.authorize(
            **kwargs
        )

        if not decision.allowed:
            raise RemediationPermissionError(
                decision.reason
            )

        return decision


def default_policy_engine() -> RemediationPolicyEngine:
    """
    Default-deny policy engine.

    No preapproved execution is enabled by default.
    """

    return RemediationPolicyEngine()