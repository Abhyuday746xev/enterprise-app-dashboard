from __future__ import annotations

# ==========================================
# Control Panel Confirmation Store
# ==========================================
#
# This module creates short-lived, one-use
# confirmation records for protected actions.
#
# It does not call Microsoft Graph.
#
# Current supported actions:
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
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


# ==========================================
# Configuration
# ==========================================

def read_positive_integer(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = int(
            raw_value
        )

    except ValueError as error:
        raise RuntimeError(
            f"{name} must be an integer."
        ) from error

    if value <= 0:
        raise RuntimeError(
            f"{name} must be greater than zero."
        )

    return value


DEFAULT_ACTION_TTL_SECONDS = (
    read_positive_integer(
        "CONTROL_ACTION_TTL_SECONDS",
        300,
    )
)

MAX_PENDING_ACTIONS = (
    read_positive_integer(
        "CONTROL_MAX_PENDING_ACTIONS",
        500,
    )
)


# ==========================================
# Action Policies
# ==========================================

ACTION_POLICIES: dict[
    str,
    dict[str, Any],
] = {
    "enable_user": {
        "label":
            "Enable user account",

        "risk":
            "medium",

        "confirmation_phrase":
            "CONFIRM",
    },

    "disable_user": {
        "label":
            "Disable user account",

        "risk":
            "high",

        "confirmation_phrase":
            "DISABLE",
    },

    "sync_device": {
        "label":
            "Synchronize managed device",

        "risk":
            "low",

        # An explicit confirmation request is
        # still required, but no typed phrase
        # is required for this low-risk action.
        "confirmation_phrase":
            None,
    },

    "restart_device": {
        "label":
            "Restart managed device",

        "risk":
            "high",

        "confirmation_phrase":
            "RESTART",
    },

    "assign_application_group": {
        "label":
            "Assign Intune application to group",

        "risk":
            "high",

        "confirmation_phrase":
            "ASSIGN",
    },

    "delete_application_assignment": {
        "label":
            "Delete application assignment",

        "risk":
            "high",

        "confirmation_phrase":
            "REMOVE",
    },

    "delete_application": {
        "label":
            "Delete Intune application",

        "risk":
            "critical",

        "confirmation_phrase":
            "DELETE",
    },
}


# ==========================================
# Exceptions
# ==========================================

class ConfirmationStoreError(
    RuntimeError
):
    """Base confirmation-store exception."""


class UnsupportedActionError(
    ConfirmationStoreError
):
    """Raised for actions outside the allowlist."""


class ConfirmationNotFoundError(
    ConfirmationStoreError
):
    """Raised when a confirmation ID does not exist."""


class ConfirmationExpiredError(
    ConfirmationStoreError
):
    """Raised when a confirmation has expired."""


class ConfirmationAlreadyUsedError(
    ConfirmationStoreError
):
    """Raised when a one-use confirmation is reused."""


class ConfirmationTextError(
    ConfirmationStoreError
):
    """Raised when typed confirmation is incorrect."""


class ConfirmationOwnershipError(
    ConfirmationStoreError
):
    """Raised when another administrator owns the action."""


# ==========================================
# Date Helpers
# ==========================================

def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def datetime_to_json(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return value.astimezone(
        timezone.utc
    ).isoformat()


# ==========================================
# Pending Action Model
# ==========================================

@dataclass
class PendingAction:
    confirmation_id: str
    action_id: str
    action_type: str
    label: str
    target_id: str
    target_name: str
    risk: str
    confirmation_phrase: str | None
    created_at: datetime
    expires_at: datetime
    requested_by: str | None = None
    status: str = "awaiting_confirmation"
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def is_expired(
        self,
    ) -> bool:
        return (
            utc_now()
            >= self.expires_at
        )

    @property
    def requires_typed_confirmation(
        self,
    ) -> bool:
        return (
            self.confirmation_phrase
            is not None
        )

    def to_public_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "confirmation_id":
                self.confirmation_id,

            "action_id":
                self.action_id,

            "action_type":
                self.action_type,

            "label":
                self.label,

            "target_id":
                self.target_id,

            "target_name":
                self.target_name,

            "risk":
                self.risk,

            "status":
                self.status,

            "requires_confirmation":
                True,

            "requires_typed_confirmation":
                self.requires_typed_confirmation,

            "confirmation_phrase":
                self.confirmation_phrase,

            "requested_by":
                self.requested_by,

            "created_at":
                datetime_to_json(
                    self.created_at
                ),

            "expires_at":
                datetime_to_json(
                    self.expires_at
                ),

            "confirmed_at":
                datetime_to_json(
                    self.confirmed_at
                ),

            "completed_at":
                datetime_to_json(
                    self.completed_at
                ),

            "cancelled_at":
                datetime_to_json(
                    self.cancelled_at
                ),

            "expired":
                self.is_expired,

            "result":
                self.result,

            "error":
                self.error,

            "metadata":
                dict(
                    self.metadata
                ),
        }


# ==========================================
# Confirmation Store
# ==========================================

class ConfirmationStore:
    """
    Thread-safe in-memory action store.

    This is suitable for one local Flask process.

    A production deployment with multiple workers
    should replace it with a shared database or
    Redis implementation.
    """

    def __init__(
        self,
    ) -> None:
        self._lock = (
            threading.RLock()
        )

        self._actions: dict[
            str,
            PendingAction,
        ] = {}

    # ======================================
    # Internal Helpers
    # ======================================

    def _cleanup_locked(
        self,
    ) -> None:
        now = utc_now()

        removable_ids: list[str] = []

        for (
            confirmation_id,
            action,
        ) in self._actions.items():
            if (
                action.status
                == "awaiting_confirmation"
                and now
                >= action.expires_at
            ):
                action.status = "expired"

            if (
                action.status
                in {
                    "completed",
                    "failed",
                    "cancelled",
                    "expired",
                }
                and now
                >= (
                    action.expires_at
                    + timedelta(hours=24)
                )
            ):
                removable_ids.append(
                    confirmation_id
                )

        for confirmation_id in removable_ids:
            self._actions.pop(
                confirmation_id,
                None,
            )

    def _enforce_capacity_locked(
        self,
    ) -> None:
        if (
            len(self._actions)
            < MAX_PENDING_ACTIONS
        ):
            return

        ordered_actions = sorted(
            self._actions.values(),
            key=lambda action:
                action.created_at,
        )

        removable = [
            action
            for action in ordered_actions
            if action.status
            in {
                "completed",
                "failed",
                "cancelled",
                "expired",
            }
        ]

        while (
            len(self._actions)
            >= MAX_PENDING_ACTIONS
            and removable
        ):
            action = removable.pop(0)

            self._actions.pop(
                action.confirmation_id,
                None,
            )

        if (
            len(self._actions)
            >= MAX_PENDING_ACTIONS
        ):
            raise ConfirmationStoreError(
                "The pending-action store is full."
            )

    @staticmethod
    def _validate_text(
        value: Any,
        field_name: str,
        maximum_length: int,
    ) -> str:
        cleaned = str(
            value or ""
        ).strip()

        if not cleaned:
            raise ValueError(
                f"{field_name} is required."
            )

        if (
            len(cleaned)
            > maximum_length
        ):
            raise ValueError(
                f"{field_name} is too long."
            )

        return cleaned

    @staticmethod
    def _check_owner(
        action: PendingAction,
        requested_by: str | None,
    ) -> None:
        if (
            action.requested_by
            and requested_by
            and action.requested_by
            != requested_by
        ):
            raise ConfirmationOwnershipError(
                "This action belongs to another "
                "administrator."
            )

    def _get_locked(
        self,
        confirmation_id: Any,
    ) -> PendingAction:
        cleaned_id = self._validate_text(
            confirmation_id,
            "confirmation_id",
            256,
        )

        action = self._actions.get(
            cleaned_id
        )

        if action is None:
            raise ConfirmationNotFoundError(
                "The confirmation record was not found."
            )

        if (
            action.status
            == "awaiting_confirmation"
            and action.is_expired
        ):
            action.status = "expired"

        return action

    # ======================================
    # Create
    # ======================================

    def create(
        self,
        *,
        action_type: Any,
        target_id: Any,
        target_name: Any,
        requested_by: Any = None,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> PendingAction:
        cleaned_action_type = (
            self._validate_text(
                action_type,
                "action_type",
                100,
            )
        )

        policy = ACTION_POLICIES.get(
            cleaned_action_type
        )

        if policy is None:
            raise UnsupportedActionError(
                "The requested action is not allowed."
            )

        cleaned_target_id = (
            self._validate_text(
                target_id,
                "target_id",
                512,
            )
        )

        cleaned_target_name = (
            self._validate_text(
                target_name,
                "target_name",
                512,
            )
        )

        cleaned_requested_by = (
            str(requested_by).strip()
            if requested_by
            else None
        )

        if (
            cleaned_requested_by
            and len(cleaned_requested_by)
            > 512
        ):
            raise ValueError(
                "requested_by is too long."
            )

        effective_ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else DEFAULT_ACTION_TTL_SECONDS
        )

        if (
            not isinstance(
                effective_ttl,
                int,
            )
            or effective_ttl <= 0
        ):
            raise ValueError(
                "ttl_seconds must be a positive integer."
            )

        created_at = utc_now()

        action = PendingAction(
            confirmation_id=(
                secrets.token_urlsafe(
                    32
                )
            ),
            action_id=(
                "ACT-"
                + secrets.token_hex(
                    8
                ).upper()
            ),
            action_type=(
                cleaned_action_type
            ),
            label=str(
                policy["label"]
            ),
            target_id=(
                cleaned_target_id
            ),
            target_name=(
                cleaned_target_name
            ),
            risk=str(
                policy["risk"]
            ),
            confirmation_phrase=(
                policy[
                    "confirmation_phrase"
                ]
            ),
            created_at=(
                created_at
            ),
            expires_at=(
                created_at
                + timedelta(
                    seconds=effective_ttl
                )
            ),
            requested_by=(
                cleaned_requested_by
            ),
            metadata=dict(
                metadata or {}
            ),
        )

        with self._lock:
            self._cleanup_locked()

            self._enforce_capacity_locked()

            self._actions[
                action.confirmation_id
            ] = action

        return action

    # ======================================
    # Read
    # ======================================

    def get(
        self,
        confirmation_id: Any,
    ) -> PendingAction:
        with self._lock:
            self._cleanup_locked()

            return self._get_locked(
                confirmation_id
            )

    def list_actions(
        self,
        *,
        limit: int = 100,
        statuses: set[str] | None = None,
    ) -> list[PendingAction]:
        if (
            not isinstance(
                limit,
                int,
            )
            or limit <= 0
        ):
            raise ValueError(
                "limit must be a positive integer."
            )

        limit = min(
            limit,
            500,
        )

        with self._lock:
            self._cleanup_locked()

            actions = list(
                self._actions.values()
            )

            if statuses:
                actions = [
                    action
                    for action in actions
                    if action.status
                    in statuses
                ]

            actions.sort(
                key=lambda action:
                    action.created_at,
                reverse=True,
            )

            return actions[:limit]

    # ======================================
    # Claim for Execution
    # ======================================

    def claim_for_execution(
        self,
        confirmation_id: Any,
        *,
        confirmation_text: Any = None,
        requested_by: Any = None,
    ) -> PendingAction:
        cleaned_requested_by = (
            str(requested_by).strip()
            if requested_by
            else None
        )

        with self._lock:
            self._cleanup_locked()

            action = self._get_locked(
                confirmation_id
            )

            self._check_owner(
                action,
                cleaned_requested_by,
            )

            if action.status == "expired":
                raise ConfirmationExpiredError(
                    "This confirmation has expired."
                )

            if (
                action.status
                != "awaiting_confirmation"
            ):
                raise ConfirmationAlreadyUsedError(
                    "This confirmation cannot be reused."
                )

            expected_phrase = (
                action.confirmation_phrase
            )

            if expected_phrase is not None:
                supplied_phrase = str(
                    confirmation_text or ""
                ).strip().upper()

                if (
                    supplied_phrase
                    != expected_phrase
                ):
                    raise ConfirmationTextError(
                        "The confirmation text is incorrect."
                    )

            # Marking the action as executing is atomic.
            # A second request cannot claim the same
            # confirmation ID.
            action.status = "executing"
            action.confirmed_at = utc_now()
            action.error = None

            return action

    # ======================================
    # Completion
    # ======================================

    def mark_completed(
        self,
        confirmation_id: Any,
        result: dict[str, Any] | None = None,
    ) -> PendingAction:
        with self._lock:
            action = self._get_locked(
                confirmation_id
            )

            if action.status != "executing":
                raise ConfirmationStoreError(
                    "Only an executing action can "
                    "be completed."
                )

            action.status = "completed"
            action.completed_at = utc_now()
            action.result = dict(
                result or {}
            )
            action.error = None

            return action

    def mark_failed(
        self,
        confirmation_id: Any,
        error: Any,
    ) -> PendingAction:
        with self._lock:
            action = self._get_locked(
                confirmation_id
            )

            if action.status != "executing":
                raise ConfirmationStoreError(
                    "Only an executing action can "
                    "be marked as failed."
                )

            action.status = "failed"
            action.completed_at = utc_now()
            action.error = str(
                error or "Unknown action failure"
            )
            action.result = None

            return action

    # ======================================
    # Cancellation
    # ======================================

    def cancel(
        self,
        confirmation_id: Any,
        *,
        requested_by: Any = None,
    ) -> PendingAction:
        cleaned_requested_by = (
            str(requested_by).strip()
            if requested_by
            else None
        )

        with self._lock:
            self._cleanup_locked()

            action = self._get_locked(
                confirmation_id
            )

            self._check_owner(
                action,
                cleaned_requested_by,
            )

            if action.status == "expired":
                raise ConfirmationExpiredError(
                    "This confirmation has expired."
                )

            if (
                action.status
                != "awaiting_confirmation"
            ):
                raise ConfirmationAlreadyUsedError(
                    "Only an awaiting confirmation "
                    "can be cancelled."
                )

            action.status = "cancelled"
            action.cancelled_at = utc_now()

            return action


# ==========================================
# Shared Store
# ==========================================

confirmation_store = (
    ConfirmationStore()
)


# ==========================================
# Convenience Functions
# ==========================================

def create_action_confirmation(
    *,
    action_type: Any,
    target_id: Any,
    target_name: Any,
    requested_by: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = confirmation_store.create(
        action_type=action_type,
        target_id=target_id,
        target_name=target_name,
        requested_by=requested_by,
        metadata=metadata,
    )

    return action.to_public_dict()


def get_action_confirmation(
    confirmation_id: Any,
) -> dict[str, Any]:
    return confirmation_store.get(
        confirmation_id
    ).to_public_dict()