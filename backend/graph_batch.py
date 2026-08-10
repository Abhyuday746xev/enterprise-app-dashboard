from __future__ import annotations

import os
from dotenv import load_dotenv
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import requests

# Load backend/.env regardless of the terminal's current directory
ENV_FILE = Path(__file__).resolve().parent / ".env"

load_dotenv(
    dotenv_path=ENV_FILE
)


# ============================================
# Microsoft Graph Configuration
# ============================================

GRAPH_VERSION = "beta"
GRAPH_ROOT = "https://graph.microsoft.com"
GRAPH_BATCH_URL = f"{GRAPH_ROOT}/{GRAPH_VERSION}/$batch"

REQUEST_TIMEOUT = (10, 60)
MAX_RETRIES = 4
MAX_BATCH_REQUESTS = 20


# ============================================
# Exceptions
# ============================================

class GraphBatchError(RuntimeError):
    """Raised when Microsoft Graph or a batch item fails."""


@dataclass
class PendingRequest:
    entity: str
    request_id: str
    url: str
    attempt: int = 0


# ============================================
# Initial Batch Requests
# ============================================

INITIAL_REQUESTS = {

    "apps": (
    "/deviceAppManagement/mobileApps"
    "?$select=id,displayName,description,publisher,"
    "createdDateTime,lastModifiedDateTime,"
    "publishingState,notes,isAssigned,owner,developer"
    ),

    "users": (
        "/users"
        "?$select=id,displayName,userPrincipalName,mail,"
        "accountEnabled,mobilePhone,businessPhones,department,"
        "jobTitle,officeLocation,createdDateTime"
    ),

    "devices": (
    "/deviceManagement/managedDevices"
    "?$select=id,deviceName,managedDeviceName,azureADDeviceId,"
    "userDisplayName,userPrincipalName,operatingSystem,osVersion,"
    "complianceState,managementState,manufacturer,model,"
    "enrolledDateTime,lastSyncDateTime"
    ),

}


# ============================================
# Header Helper
# ============================================

def build_headers(
    access_token: str,
) -> dict[str, str]:

    token = str(
        access_token or ""
    ).strip()

    if (
        not token
        or token.upper() == "REDACTED"
    ):

        raise ValueError(
            "A valid Microsoft Graph access token is required."
        )

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ============================================
# Retry Helpers
# ============================================

def retry_after_seconds(
    headers: dict[str, Any] | None,
    default: int,
) -> int:

    if not headers:

        return default

    normalized_headers = {

        str(key).lower():
            value

        for key, value
        in headers.items()

    }

    retry_after = normalized_headers.get(
        "retry-after"
    )

    try:

        return max(
            1,
            int(retry_after),
        )

    except (
        TypeError,
        ValueError,
    ):

        return max(
            1,
            default,
        )


def response_error_message(
    body: Any,
) -> str:

    if not isinstance(
        body,
        dict,
    ):

        return str(
            body
            or "Unknown Microsoft Graph error"
        )

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

    return str(
        body
    )


# ============================================
# Pagination URL Helper
# ============================================

def to_batch_relative_url(
    next_link: str,
) -> str:

    """
    Convert an @odata.nextLink into a relative
    URL that can be submitted through $batch.
    """

    value = str(
        next_link or ""
    ).strip()

    if not value:

        raise GraphBatchError(
            "Microsoft Graph returned an empty nextLink."
        )

    if value.startswith("/"):

        relative_url = value

    else:

        parsed = urlsplit(
            value
        )

        if (
            parsed.netloc.lower()
            != "graph.microsoft.com"
        ):

            raise GraphBatchError(
                "Microsoft Graph returned an unexpected "
                "nextLink host."
            )

        relative_url = parsed.path

        if parsed.query:

            relative_url = (
                f"{relative_url}?"
                f"{parsed.query}"
            )

    # Batch requests use URLs relative to
    # the selected Graph API version.
    for prefix in (
        "/beta",
        "/v1.0",
    ):

        if relative_url.lower().startswith(
            prefix
        ):

            relative_url = relative_url[
                len(prefix):
            ]

            break

    if not relative_url.startswith("/"):

        relative_url = (
            f"/{relative_url}"
        )

    return relative_url


# ============================================
# Batch Splitting
# ============================================

def split_batch_requests(
    pending_requests: list[PendingRequest],
):

    for index in range(
        0,
        len(pending_requests),
        MAX_BATCH_REQUESTS,
    ):

        yield pending_requests[
            index:
            index + MAX_BATCH_REQUESTS
        ]


# ============================================
# Send One Batch
# ============================================

def post_batch(
    session: requests.Session,
    access_token: str,
    pending_requests: list[PendingRequest],
) -> dict[str, Any]:

    body = {

        "requests": [

            {
                "id":
                    request_item.request_id,

                "method":
                    "GET",

                "url":
                    request_item.url,
            }

            for request_item
            in pending_requests

        ]

    }

    headers = build_headers(
        access_token
    )

    for attempt in range(
        MAX_RETRIES + 1
    ):

        try:

            response = session.post(

                GRAPH_BATCH_URL,

                headers=headers,

                json=body,

                timeout=REQUEST_TIMEOUT,

            )

        except requests.RequestException as error:

            if attempt >= MAX_RETRIES:

                raise GraphBatchError(
                    "Could not connect to Microsoft Graph: "
                    f"{error}"
                ) from error

            time.sleep(
                2 ** attempt
            )

            continue

        # ------------------------------------
        # Authentication Errors
        # ------------------------------------

        if response.status_code == 401:

            raise GraphBatchError(
                "Microsoft Graph rejected the access token. "
                "The token may be invalid or expired."
            )

        if response.status_code == 403:

            raise GraphBatchError(
                "Microsoft Graph denied the request. "
                "Check Graph permissions and admin consent."
            )

        # ------------------------------------
        # Outer Batch Throttling or Failure
        # ------------------------------------

        if (
            response.status_code == 429

            or 500
            <= response.status_code
            < 600
        ):

            if attempt >= MAX_RETRIES:

                raise GraphBatchError(
                    "Microsoft Graph remained unavailable "
                    "after retries. "
                    f"HTTP {response.status_code}."
                )

            wait_seconds = retry_after_seconds(

                dict(
                    response.headers
                ),

                default=
                    2 ** attempt,

            )

            time.sleep(
                wait_seconds
            )

            continue

        # ------------------------------------
        # Other HTTP Errors
        # ------------------------------------

        try:

            response.raise_for_status()

        except requests.HTTPError as error:

            try:

                response_body = (
                    response.json()
                )

            except ValueError:

                response_body = (
                    response.text
                )

            raise GraphBatchError(

                "Microsoft Graph batch request failed. "
                f"HTTP {response.status_code}: "
                f"{response_error_message(response_body)}"

            ) from error

        # ------------------------------------
        # Parse JSON
        # ------------------------------------

        try:

            result = response.json()

        except ValueError as error:

            raise GraphBatchError(
                "Microsoft Graph returned a non-JSON "
                "batch response."
            ) from error

        if not isinstance(
            result,
            dict,
        ):

            raise GraphBatchError(
                "Microsoft Graph returned an invalid "
                "batch response."
            )

        return result

    raise GraphBatchError(
        "Microsoft Graph batch request failed."
    )


# ============================================
# Fetch Complete Batch Data
# ============================================

def fetch_batch_data(
    access_token: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:

    """
    Retrieve all pages of:

    - Intune mobile applications
    - Enterprise users
    - Intune managed devices

    Return order:

    applications, users, devices
    """

    collected_data: dict[
        str,
        list[dict[str, Any]],
    ] = {

        "apps": [],
        "users": [],
        "devices": [],

    }

    page_numbers = {

        "apps": 1,
        "users": 1,
        "devices": 1,

    }

    pending_requests = [

        PendingRequest(

            entity=
                entity,

            request_id=
                f"{entity}:1",

            url=
                url,

        )

        for entity, url
        in INITIAL_REQUESTS.items()

    ]

    print(
        "Connecting to Microsoft Graph..."
    )

    with requests.Session() as session:

        while pending_requests:

            next_pending_requests: list[
                PendingRequest
            ] = []

            for batch_group in split_batch_requests(
                pending_requests
            ):

                batch_result = post_batch(

                    session=
                        session,

                    access_token=
                        access_token,

                    pending_requests=
                        batch_group,

                )

                responses = batch_result.get(
                    "responses"
                )

                if not isinstance(
                    responses,
                    list,
                ):

                    raise GraphBatchError(
                        "Microsoft Graph batch response "
                        "does not contain a responses list."
                    )

                responses_by_id = {

                    str(
                        item.get("id")
                    ):
                        item

                    for item
                    in responses

                    if isinstance(
                        item,
                        dict,
                    )

                }

                for request_item in batch_group:

                    item = responses_by_id.get(
                        request_item.request_id
                    )

                    if item is None:

                        raise GraphBatchError(

                            "Microsoft Graph omitted batch "
                            f"response '{request_item.request_id}'."

                        )

                    status = int(
                        item.get(
                            "status",
                            0,
                        )
                    )

                    response_body = (
                        item.get("body")
                        or {}
                    )

                    response_headers = (
                        item.get("headers")
                        or {}
                    )

                    # ========================
                    # Successful Batch Item
                    # ========================

                    if (
                        200
                        <= status
                        < 300
                    ):

                        values = response_body.get(
                            "value",
                            [],
                        )

                        if not isinstance(
                            values,
                            list,
                        ):

                            raise GraphBatchError(

                                f"Batch item "
                                f"'{request_item.request_id}' "
                                "returned an invalid collection."

                            )

                        collected_data[
                            request_item.entity
                        ].extend(

                            value

                            for value
                            in values

                            if isinstance(
                                value,
                                dict,
                            )

                        )

                        next_link = response_body.get(
                            "@odata.nextLink"
                        )

                        if next_link:

                            page_numbers[
                                request_item.entity
                            ] += 1

                            next_pending_requests.append(

                                PendingRequest(

                                    entity=
                                        request_item.entity,

                                    request_id=(

                                        f"{request_item.entity}:"
                                        f"{page_numbers[request_item.entity]}"

                                    ),

                                    url=
                                        to_batch_relative_url(
                                            next_link
                                        ),

                                )

                            )

                        continue

                    # ========================
                    # Retry Batch Item
                    # ========================

                    if (
                        status == 429

                        or 500
                        <= status
                        < 600
                    ):

                        if (
                            request_item.attempt
                            >= MAX_RETRIES
                        ):

                            raise GraphBatchError(

                                f"Batch item "
                                f"'{request_item.entity}' "
                                "failed after retries. "
                                f"HTTP {status}: "
                                f"{response_error_message(response_body)}"

                            )

                        wait_seconds = retry_after_seconds(

                            response_headers,

                            default=
                                2 ** request_item.attempt,

                        )

                        time.sleep(
                            wait_seconds
                        )

                        next_pending_requests.append(

                            PendingRequest(

                                entity=
                                    request_item.entity,

                                request_id=
                                    request_item.request_id,

                                url=
                                    request_item.url,

                                attempt=
                                    request_item.attempt + 1,

                            )

                        )

                        continue

                    # ========================
                    # Authentication Failure
                    # ========================

                    if status == 401:

                        raise GraphBatchError(
                            "A Microsoft Graph batch item "
                            "rejected the access token."
                        )

                    if status == 403:

                        raise GraphBatchError(

                            "Microsoft Graph denied access to "
                            f"'{request_item.entity}'. "
                            "Check the required permission."

                        )

                    # ========================
                    # Other Batch Item Error
                    # ========================

                    raise GraphBatchError(

                        f"Batch item "
                        f"'{request_item.entity}' failed. "
                        f"HTTP {status}: "
                        f"{response_error_message(response_body)}"

                    )

            pending_requests = (
                next_pending_requests
            )

    return (

        collected_data[
            "apps"
        ],

        collected_data[
            "users"
        ],

        collected_data[
            "devices"
        ],

    )


# ============================================
# Standalone Testing
# ============================================

if __name__ == "__main__":

    access_token = os.getenv(
        "GRAPH_ACCESS_TOKEN",
        "",
    ).strip()

    if not access_token:

        raise SystemExit(
            "GRAPH_ACCESS_TOKEN was not found.\n"
            f"Expected environment file: {ENV_FILE}"
        )

    applications, users, devices = fetch_batch_data(
        access_token
    )

    print("\n========== SUMMARY ==========\n")
    print(f"Applications : {len(applications)}")
    print(f"Users        : {len(users)}")
    print(f"Devices      : {len(devices)}")