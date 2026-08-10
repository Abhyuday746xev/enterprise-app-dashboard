from __future__ import annotations

# ==========================================
# Protected Microsoft Graph Actions
# ==========================================
#
# First supported write operations:
#
# 1. Enable or disable a Microsoft Entra user.
# 2. Request an Intune managed-device sync.
# 3. Request an Intune managed-device reboot.
#
# This module exposes fixed, allowlisted actions.
# It does not execute arbitrary Graph URLs or
# arbitrary request bodies supplied by an LLM.
#
# ==========================================

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv


# ==========================================
# Environment
# ==========================================

BACKEND_DIRECTORY = Path(
    __file__
).resolve().parents[1]

ENV_FILE = (
    BACKEND_DIRECTORY / ".env"
)

load_dotenv(
    dotenv_path=ENV_FILE
)


# ==========================================
# Configuration
# ==========================================

GRAPH_API_ROOT = os.getenv(
    "GRAPH_ACTION_API_ROOT",
    "https://graph.microsoft.com/v1.0",
).rstrip("/")

REQUEST_TIMEOUT = (
    10,
    60,
)

MAX_RETRIES = int(
    os.getenv(
        "GRAPH_ACTION_MAX_RETRIES",
        "3",
    )
)


# ==========================================
# Exceptions
# ==========================================

class GraphActionError(RuntimeError):
    """Base exception for protected Graph actions."""


class GraphAuthenticationError(
    GraphActionError
):
    """Raised when the Graph token is invalid or expired."""


class GraphPermissionError(
    GraphActionError
):
    """Raised when Graph denies an operation."""


class GraphResourceNotFoundError(
    GraphActionError
):
    """Raised when a requested Graph object does not exist."""


class GraphActionConflictError(
    GraphActionError
):
    """Raised when Graph rejects an operation due to state conflict."""


# ==========================================
# Result Models
# ==========================================

@dataclass(frozen=True)
class UserAccountActionResult:
    user_id: str
    display_name: str | None
    user_principal_name: str | None
    requested_enabled: bool
    verified_enabled: bool
    changed: bool

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "user_id":
                self.user_id,

            "display_name":
                self.display_name,

            "user_principal_name":
                self.user_principal_name,

            "requested_enabled":
                self.requested_enabled,

            "verified_enabled":
                self.verified_enabled,

            "changed":
                self.changed,
        }


@dataclass(frozen=True)
class DeviceRestartActionResult:
    device_id: str
    device_name: str | None
    accepted: bool

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "device_id":
                self.device_id,

            "device_name":
                self.device_name,

            "accepted":
                self.accepted,

            "verification":
                (
                    "The reboot request was accepted. "
                    "Device completion must be checked later."
                ),
        }


@dataclass(frozen=True)
class DeviceSyncActionResult:
    device_id: str
    device_name: str | None
    accepted: bool

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "device_id":
                self.device_id,

            "device_name":
                self.device_name,

            "accepted":
                self.accepted,

            "verification":
                (
                    "The sync request was accepted. "
                    "Device completion must be checked later."
                ),
        }


# ==========================================
# General Helpers
# ==========================================

def get_graph_access_token() -> str:
    token = os.getenv(
        "GRAPH_ACCESS_TOKEN",
        "",
    ).strip()

    if token.lower().startswith(
        "bearer "
    ):
        token = token[7:].strip()

    if not token:
        raise GraphAuthenticationError(
            "GRAPH_ACCESS_TOKEN was not found. "
            f"Expected environment file: {ENV_FILE}"
        )

    if token.upper() == "REDACTED":
        raise GraphAuthenticationError(
            "GRAPH_ACCESS_TOKEN contains a placeholder."
        )

    return token


def validate_identifier(
    value: Any,
    label: str,
) -> str:
    identifier = str(
        value or ""
    ).strip()

    if not identifier:
        raise ValueError(
            f"{label} is required."
        )

    if len(identifier) > 512:
        raise ValueError(
            f"{label} is too long."
        )

    if any(
        character in identifier
        for character in (
            "/",
            "\\",
            "?",
            "#",
        )
    ):
        raise ValueError(
            f"{label} contains invalid characters."
        )

    return identifier


def graph_path_segment(
    value: Any,
    label: str,
) -> str:
    identifier = validate_identifier(
        value,
        label,
    )

    return quote(
        identifier,
        safe="@._-",
    )


def build_headers(
    access_token: str,
    include_json: bool = True,
) -> dict[str, str]:
    headers = {
        "Authorization":
            f"Bearer {access_token}",

        "Accept":
            "application/json",
    }

    if include_json:
        headers[
            "Content-Type"
        ] = "application/json"

    return headers


def retry_after_seconds(
    response: requests.Response,
    default: int,
) -> int:
    value = response.headers.get(
        "Retry-After"
    )

    try:
        return max(
            1,
            int(value),
        )

    except (
        TypeError,
        ValueError,
    ):
        return max(
            1,
            default,
        )


def graph_error_message(
    response: requests.Response,
) -> str:
    try:
        body = response.json()

    except ValueError:
        body = response.text

    if isinstance(
        body,
        dict,
    ):
        error = body.get(
            "error",
            body,
        )

        if isinstance(
            error,
            dict,
        ):
            code = error.get(
                "code"
            )

            message = error.get(
                "message"
            )

            if code and message:
                return (
                    f"{code}: {message}"
                )

            if message:
                return str(
                    message
                )

    text = str(
        body or ""
    ).strip()

    return (
        text
        if text
        else "Unknown Microsoft Graph error"
    )


def raise_for_graph_error(
    response: requests.Response,
) -> None:
    if response.status_code == 401:
        raise GraphAuthenticationError(
            "Microsoft Graph rejected the access token. "
            "It may be invalid or expired."
        )

    if response.status_code == 403:
        raise GraphPermissionError(
            "Microsoft Graph denied the action. "
            "Check Graph permissions, admin consent, "
            "and the administrator role required for "
            "the target resource."
        )

    if response.status_code == 404:
        raise GraphResourceNotFoundError(
            "The requested Microsoft Graph resource "
            "was not found."
        )

    if response.status_code == 409:
        raise GraphActionConflictError(
            "Microsoft Graph rejected the action "
            "because the resource state conflicts "
            "with the requested operation."
        )

    try:
        response.raise_for_status()

    except requests.HTTPError as error:
        raise GraphActionError(
            "Microsoft Graph action failed. "
            f"HTTP {response.status_code}: "
            f"{graph_error_message(response)}"
        ) from error


# ==========================================
# Fixed Graph Client
# ==========================================

class ProtectedGraphClient:
    """
    Small client for allowlisted Graph operations.

    The public methods construct their own fixed
    endpoints and bodies. Callers cannot supply an
    arbitrary URL or HTTP method.
    """

    def __init__(
        self,
        access_token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.access_token = (
            str(access_token).strip()
            if access_token
            else get_graph_access_token()
        )

        self.session = (
            session
            if session is not None
            else requests.Session()
        )

    def close(
        self,
    ) -> None:
        self.session.close()

    def __enter__(
        self,
    ) -> "ProtectedGraphClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...],
    ) -> requests.Response:
        last_error: Exception | None = None

        for attempt in range(
            MAX_RETRIES + 1
        ):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=build_headers(
                        self.access_token,
                        include_json=(
                            json_body is not None
                        ),
                    ),
                    json=json_body,
                    timeout=REQUEST_TIMEOUT,
                )

            except requests.RequestException as error:
                last_error = error

                if attempt >= MAX_RETRIES:
                    raise GraphActionError(
                        "Could not connect to Microsoft Graph: "
                        f"{error}"
                    ) from error

                time.sleep(
                    2 ** attempt
                )

                continue

            if (
                response.status_code == 429
                or 500
                <= response.status_code
                < 600
            ):
                if attempt >= MAX_RETRIES:
                    raise GraphActionError(
                        "Microsoft Graph remained unavailable "
                        "after retries. "
                        f"HTTP {response.status_code}: "
                        f"{graph_error_message(response)}"
                    )

                time.sleep(
                    retry_after_seconds(
                        response,
                        default=2 ** attempt,
                    )
                )

                continue

            if response.status_code not in (
                expected_statuses
            ):
                raise_for_graph_error(
                    response
                )

                raise GraphActionError(
                    "Microsoft Graph returned an "
                    f"unexpected HTTP status "
                    f"{response.status_code}."
                )

            return response

        raise GraphActionError(
            "Microsoft Graph request failed."
        ) from last_error

    # ======================================
    # User Reads
    # ======================================

    def get_user(
        self,
        user_id_or_upn: Any,
    ) -> dict[str, Any]:
        identifier = graph_path_segment(
            user_id_or_upn,
            "user_id_or_upn",
        )

        url = (
            f"{GRAPH_API_ROOT}/users/"
            f"{identifier}"
            "?$select=id,displayName,"
            "userPrincipalName,mail,"
            "accountEnabled"
        )

        response = self._request(
            "GET",
            url,
            expected_statuses=(
                200,
            ),
        )

        try:
            body = response.json()

        except ValueError as error:
            raise GraphActionError(
                "Microsoft Graph returned a non-JSON "
                "user response."
            ) from error

        if not isinstance(
            body,
            dict,
        ):
            raise GraphActionError(
                "Microsoft Graph returned an invalid "
                "user response."
            )

        return body

    # ======================================
    # User Enable / Disable
    # ======================================

    def set_user_enabled(
        self,
        user_id_or_upn: Any,
        enabled: bool,
    ) -> UserAccountActionResult:
        if not isinstance(
            enabled,
            bool,
        ):
            raise TypeError(
                "enabled must be a boolean."
            )

        before = self.get_user(
            user_id_or_upn
        )

        exact_user_id = validate_identifier(
            before.get("id"),
            "resolved user ID",
        )

        previous_enabled = before.get(
            "accountEnabled"
        )

        if previous_enabled is enabled:
            return UserAccountActionResult(
                user_id=exact_user_id,
                display_name=before.get(
                    "displayName"
                ),
                user_principal_name=before.get(
                    "userPrincipalName"
                ),
                requested_enabled=enabled,
                verified_enabled=enabled,
                changed=False,
            )

        encoded_user_id = graph_path_segment(
            exact_user_id,
            "resolved user ID",
        )

        url = (
            f"{GRAPH_API_ROOT}/users/"
            f"{encoded_user_id}"
        )

        self._request(
            "PATCH",
            url,
            json_body={
                "accountEnabled":
                    enabled,
            },
            expected_statuses=(
                204,
            ),
        )

        verified = self.get_user(
            exact_user_id
        )

        verified_enabled = verified.get(
            "accountEnabled"
        )

        if verified_enabled is not enabled:
            raise GraphActionError(
                "Microsoft Graph accepted the user update, "
                "but verification did not return the "
                "requested accountEnabled value."
            )

        return UserAccountActionResult(
            user_id=exact_user_id,
            display_name=verified.get(
                "displayName"
            ),
            user_principal_name=verified.get(
                "userPrincipalName"
            ),
            requested_enabled=enabled,
            verified_enabled=verified_enabled,
            changed=True,
        )

    def enable_user(
        self,
        user_id_or_upn: Any,
    ) -> UserAccountActionResult:
        return self.set_user_enabled(
            user_id_or_upn,
            True,
        )

    def disable_user(
        self,
        user_id_or_upn: Any,
    ) -> UserAccountActionResult:
        return self.set_user_enabled(
            user_id_or_upn,
            False,
        )

    # ======================================
    # Managed Device Reads
    # ======================================

    def get_managed_device(
        self,
        managed_device_id: Any,
    ) -> dict[str, Any]:
        identifier = graph_path_segment(
            managed_device_id,
            "managed_device_id",
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceManagement/managedDevices/"
            f"{identifier}"
            "?$select=id,deviceName,"
            "managedDeviceName,userDisplayName,"
            "userPrincipalName,operatingSystem,"
            "complianceState,lastSyncDateTime"
        )

        response = self._request(
            "GET",
            url,
            expected_statuses=(
                200,
            ),
        )

        try:
            body = response.json()

        except ValueError as error:
            raise GraphActionError(
                "Microsoft Graph returned a non-JSON "
                "managed-device response."
            ) from error

        if not isinstance(
            body,
            dict,
        ):
            raise GraphActionError(
                "Microsoft Graph returned an invalid "
                "managed-device response."
            )

        return body

    # ======================================
    # Managed Device Reboot
    # ======================================

    def reboot_managed_device(
        self,
        managed_device_id: Any,
    ) -> DeviceRestartActionResult:
        device = self.get_managed_device(
            managed_device_id
        )

        exact_device_id = validate_identifier(
            device.get("id"),
            "resolved managed-device ID",
        )

        identifier = graph_path_segment(
            exact_device_id,
            "resolved managed-device ID",
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceManagement/managedDevices/"
            f"{identifier}/rebootNow"
        )

        self._request(
            "POST",
            url,
            expected_statuses=(
                204,
            ),
        )

        return DeviceRestartActionResult(
            device_id=exact_device_id,
            device_name=(
                device.get("deviceName")
                or device.get(
                    "managedDeviceName"
                )
            ),
            accepted=True,
        )

    # ======================================
    # Managed Device Sync
    # ======================================

    def sync_managed_device(
        self,
        managed_device_id: Any,
    ) -> DeviceSyncActionResult:
        device = self.get_managed_device(
            managed_device_id
        )

        exact_device_id = validate_identifier(
            device.get("id"),
            "resolved managed-device ID",
        )

        identifier = graph_path_segment(
            exact_device_id,
            "resolved managed-device ID",
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceManagement/managedDevices/"
            f"{identifier}/syncDevice"
        )

        self._request(
            "POST",
            url,
            expected_statuses=(
                204,
            ),
        )

        return DeviceSyncActionResult(
            device_id=exact_device_id,
            device_name=(
                device.get("deviceName")
                or device.get(
                    "managedDeviceName"
                )
            ),
            accepted=True,
        )


# ==========================================
# Convenience Functions
# ==========================================

def enable_user(
    user_id_or_upn: Any,
) -> dict[str, Any]:
    with ProtectedGraphClient() as client:
        return client.enable_user(
            user_id_or_upn
        ).to_dict()


def disable_user(
    user_id_or_upn: Any,
) -> dict[str, Any]:
    with ProtectedGraphClient() as client:
        return client.disable_user(
            user_id_or_upn
        ).to_dict()


def reboot_managed_device(
    managed_device_id: Any,
) -> dict[str, Any]:
    with ProtectedGraphClient() as client:
        return client.reboot_managed_device(
            managed_device_id
        ).to_dict()


def sync_managed_device(
    managed_device_id: Any,
) -> dict[str, Any]:
    with ProtectedGraphClient() as client:
        return client.sync_managed_device(
            managed_device_id
        ).to_dict()