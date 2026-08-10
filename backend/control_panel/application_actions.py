from __future__ import annotations

# ==========================================
# Protected Intune Application Actions
# ==========================================
#
# This module adds fixed Microsoft Graph
# operations for existing Intune applications.
#
# Supported operations:
#
# - Read an application.
# - List its assignments.
# - Create a Win32 application assignment
#   for one exact Microsoft Entra group.
# - Delete one exact assignment.
# - Delete one exact application.
#
# It does not upload application packages and
# does not accept arbitrary Graph URLs.
#
# ==========================================

from dataclasses import dataclass
from uuid import UUID
from typing import Any
from urllib.parse import urlsplit

from control_panel.graph_actions import (
    GRAPH_API_ROOT,
    GraphActionError,
    GraphResourceNotFoundError,
    ProtectedGraphClient,
    graph_path_segment,
    validate_identifier,
)


# ==========================================
# Exceptions
# ==========================================

class ApplicationActionError(
    GraphActionError
):
    """Base error for application actions."""


class ApplicationHasAssignmentsError(
    ApplicationActionError
):
    """
    Raised when deletion is requested for an
    application that still has assignments.
    """


class ApplicationAssignmentNotFoundError(
    ApplicationActionError
):
    """Raised when an exact assignment is missing."""


class UnsupportedApplicationAssignmentTypeError(
    ApplicationActionError
):
    """Raised when the app type is not supported for assignment."""


class DuplicateApplicationAssignmentError(
    ApplicationActionError
):
    """Raised when the same group and intent are already assigned."""


# ==========================================
# Result Models
# ==========================================

@dataclass(frozen=True)
class ApplicationAssignmentCreateResult:
    application_id: str
    application_name: str | None
    application_type: str
    assignment_id: str
    group_id: str
    group_name: str | None
    intent: str
    notifications: str
    created: bool
    verified: bool

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "application_id":
                self.application_id,

            "application_name":
                self.application_name,

            "application_type":
                self.application_type,

            "assignment_id":
                self.assignment_id,

            "group_id":
                self.group_id,

            "group_name":
                self.group_name,

            "intent":
                self.intent,

            "notifications":
                self.notifications,

            "created":
                self.created,

            "verified":
                self.verified,
        }


@dataclass(frozen=True)
class ApplicationAssignmentDeleteResult:
    application_id: str
    application_name: str | None
    assignment_id: str
    deleted: bool
    remaining_assignment_count: int

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "application_id":
                self.application_id,

            "application_name":
                self.application_name,

            "assignment_id":
                self.assignment_id,

            "deleted":
                self.deleted,

            "remaining_assignment_count":
                self.remaining_assignment_count,
        }


@dataclass(frozen=True)
class ApplicationDeleteResult:
    application_id: str
    application_name: str | None
    assignment_count_before_delete: int
    deleted: bool
    verified_deleted: bool

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "application_id":
                self.application_id,

            "application_name":
                self.application_name,

            "assignment_count_before_delete":
                self.assignment_count_before_delete,

            "deleted":
                self.deleted,

            "verified_deleted":
                self.verified_deleted,
        }


# ==========================================
# Application Graph Client
# ==========================================

class ProtectedApplicationGraphClient(
    ProtectedGraphClient
):
    """
    Fixed Intune application operations built on
    the protected Graph client.
    """

    # ======================================
    # Application Read
    # ======================================

    def get_mobile_application(
        self,
        mobile_app_id: Any,
    ) -> dict[str, Any]:
        identifier = graph_path_segment(
            mobile_app_id,
            "mobile_app_id",
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceAppManagement/mobileApps/"
            f"{identifier}"
            "?$select=id,displayName,description,"
            "publisher,createdDateTime,"
            "lastModifiedDateTime,publishingState,"
            "owner,developer,notes"
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
            raise ApplicationActionError(
                "Microsoft Graph returned a non-JSON "
                "mobile-application response."
            ) from error

        if not isinstance(
            body,
            dict,
        ):
            raise ApplicationActionError(
                "Microsoft Graph returned an invalid "
                "mobile-application response."
            )

        return body

    # ======================================
    # Assignment Reads
    # ======================================

    def list_mobile_app_assignments(
        self,
        mobile_app_id: Any,
    ) -> list[dict[str, Any]]:
        application = self.get_mobile_application(
            mobile_app_id
        )

        exact_app_id = validate_identifier(
            application.get("id"),
            "resolved mobile-application ID",
        )

        identifier = graph_path_segment(
            exact_app_id,
            "resolved mobile-application ID",
        )

        next_url: str | None = (
            f"{GRAPH_API_ROOT}"
            "/deviceAppManagement/mobileApps/"
            f"{identifier}/assignments"
        )

        assignments: list[
            dict[str, Any]
        ] = []

        visited_urls: set[str] = set()

        while next_url:
            if next_url in visited_urls:
                raise ApplicationActionError(
                    "Microsoft Graph returned an assignment "
                    "pagination loop."
                )

            visited_urls.add(
                next_url
            )

            response = self._request(
                "GET",
                next_url,
                expected_statuses=(
                    200,
                ),
            )

            try:
                body = response.json()

            except ValueError as error:
                raise ApplicationActionError(
                    "Microsoft Graph returned a non-JSON "
                    "assignment response."
                ) from error

            if not isinstance(
                body,
                dict,
            ):
                raise ApplicationActionError(
                    "Microsoft Graph returned an invalid "
                    "assignment response."
                )

            values = body.get(
                "value",
                [],
            )

            if not isinstance(
                values,
                list,
            ):
                raise ApplicationActionError(
                    "Microsoft Graph returned an invalid "
                    "assignment collection."
                )

            assignments.extend(
                item
                for item in values
                if isinstance(
                    item,
                    dict,
                )
            )

            raw_next_link = body.get(
                "@odata.nextLink"
            )

            if not raw_next_link:
                next_url = None
                continue

            next_url = self._validate_next_link(
                raw_next_link
            )

        return assignments

    @staticmethod
    def _validate_next_link(
        value: Any,
    ) -> str:
        next_link = str(
            value or ""
        ).strip()

        if not next_link:
            raise ApplicationActionError(
                "Microsoft Graph returned an empty "
                "assignment nextLink."
            )

        parsed = urlsplit(
            next_link
        )

        if (
            parsed.scheme.lower()
            != "https"
            or parsed.netloc.lower()
            != "graph.microsoft.com"
        ):
            raise ApplicationActionError(
                "Microsoft Graph returned an unexpected "
                "assignment nextLink host."
            )

        return next_link

    def get_mobile_app_assignment(
        self,
        mobile_app_id: Any,
        assignment_id: Any,
    ) -> dict[str, Any]:
        assignments = (
            self.list_mobile_app_assignments(
                mobile_app_id
            )
        )

        cleaned_assignment_id = (
            validate_identifier(
                assignment_id,
                "assignment_id",
            )
        )

        assignment = next(
            (
                item
                for item in assignments
                if str(
                    item.get(
                        "id",
                        "",
                    )
                ).strip()
                == cleaned_assignment_id
            ),
            None,
        )

        if assignment is None:
            raise ApplicationAssignmentNotFoundError(
                "The requested application assignment "
                "was not found."
            )

        return assignment

    # ======================================
    # Group Validation
    # ======================================

    @staticmethod
    def _validate_guid(
        value: Any,
        label: str,
    ) -> str:
        cleaned = validate_identifier(
            value,
            label,
        )

        try:
            parsed = UUID(
                cleaned
            )

        except ValueError as error:
            raise ValueError(
                f"{label} must be a valid GUID."
            ) from error

        return str(
            parsed
        )

    def get_group(
        self,
        group_id: Any,
    ) -> dict[str, Any]:
        exact_group_id = self._validate_guid(
            group_id,
            "group_id",
        )

        encoded_group_id = graph_path_segment(
            exact_group_id,
            "group_id",
        )

        url = (
            f"{GRAPH_API_ROOT}/groups/"
            f"{encoded_group_id}"
            "?$select=id,displayName,description,"
            "mail,mailEnabled,securityEnabled,"
            "groupTypes,membershipRule"
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
            raise ApplicationActionError(
                "Microsoft Graph returned a non-JSON "
                "group response."
            ) from error

        if not isinstance(
            body,
            dict,
        ):
            raise ApplicationActionError(
                "Microsoft Graph returned an invalid "
                "group response."
            )

        returned_group_id = self._validate_guid(
            body.get("id"),
            "resolved group ID",
        )

        if returned_group_id != exact_group_id:
            raise ApplicationActionError(
                "Microsoft Graph returned an unexpected "
                "group ID."
            )

        return body

    # ======================================
    # Win32 Group Assignment
    # ======================================

    @staticmethod
    def _normalized_odata_type(
        value: Any,
    ) -> str:
        return str(
            value or ""
        ).strip().lower().lstrip("#")

    @staticmethod
    def _validate_win32_intent(
        intent: Any,
    ) -> str:
        cleaned = str(
            intent or ""
        ).strip()

        allowed = {
            "available",
            "required",
            "uninstall",
        }

        if cleaned not in allowed:
            raise ValueError(
                "intent must be available, required, "
                "or uninstall for a Win32 application."
            )

        return cleaned

    @staticmethod
    def _validate_win32_notifications(
        notifications: Any,
    ) -> str:
        cleaned = str(
            notifications or ""
        ).strip()

        allowed = {
            "showAll",
            "showReboot",
            "hideAll",
        }

        if cleaned not in allowed:
            raise ValueError(
                "notifications must be showAll, "
                "showReboot, or hideAll."
            )

        return cleaned

    @staticmethod
    def _assignment_target_type(
        assignment: dict[str, Any],
    ) -> str:
        target = assignment.get(
            "target"
        )

        if not isinstance(
            target,
            dict,
        ):
            return ""

        return (
            str(
                target.get(
                    "@odata.type",
                    "",
                )
            )
            .strip()
            .lower()
            .lstrip("#")
        )

    @staticmethod
    def _assignment_group_id(
        assignment: dict[str, Any],
    ) -> str:
        target = assignment.get(
            "target"
        )

        if not isinstance(
            target,
            dict,
        ):
            return ""

        return str(
            target.get(
                "groupId",
                "",
            )
        ).strip().lower()

    def find_group_assignment(
        self,
        mobile_app_id: Any,
        group_id: Any,
        intent: Any | None = None,
    ) -> dict[str, Any] | None:
        exact_group_id = self._validate_guid(
            group_id,
            "group_id",
        ).lower()

        cleaned_intent = (
            None
            if intent is None
            else str(
                intent
            ).strip()
        )

        for assignment in (
            self.list_mobile_app_assignments(
                mobile_app_id
            )
        ):
            target_type = (
                self._assignment_target_type(
                    assignment
                )
            )

            if target_type != (
                "microsoft.graph."
                "groupassignmenttarget"
            ):
                continue

            if (
                self._assignment_group_id(
                    assignment
                )
                != exact_group_id
            ):
                continue

            if (
                cleaned_intent is not None
                and str(
                    assignment.get(
                        "intent",
                        "",
                    )
                ).strip()
                != cleaned_intent
            ):
                continue

            return assignment

        return None

    def create_win32_group_assignment(
        self,
        mobile_app_id: Any,
        group_id: Any,
        *,
        intent: Any,
        notifications: Any = "showAll",
    ) -> ApplicationAssignmentCreateResult:
        application = self.get_mobile_application(
            mobile_app_id
        )

        exact_app_id = validate_identifier(
            application.get("id"),
            "resolved mobile-application ID",
        )

        application_type = (
            self._normalized_odata_type(
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
                    "This assignment tool currently supports "
                    "only Microsoft Graph win32LobApp objects. "
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

        exact_group_id = self._validate_guid(
            group_id,
            "group_id",
        )

        group = self.get_group(
            exact_group_id
        )

        cleaned_intent = (
            self._validate_win32_intent(
                intent
            )
        )

        cleaned_notifications = (
            self._validate_win32_notifications(
                notifications
            )
        )

        duplicate = self.find_group_assignment(
            exact_app_id,
            exact_group_id,
            cleaned_intent,
        )

        if duplicate is not None:
            raise DuplicateApplicationAssignmentError(
                "The selected application already has "
                f"a '{cleaned_intent}' assignment for "
                f"{group.get('displayName') or exact_group_id}."
            )

        encoded_app_id = graph_path_segment(
            exact_app_id,
            "resolved mobile-application ID",
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceAppManagement/mobileApps/"
            f"{encoded_app_id}/assignments"
        )

        body = {
            "@odata.type":
                "#microsoft.graph.mobileAppAssignment",

            "intent":
                cleaned_intent,

            "target": {
                "@odata.type":
                    "#microsoft.graph.groupAssignmentTarget",

                "groupId":
                    exact_group_id,
            },

            "settings": {
                "@odata.type":
                    (
                        "#microsoft.graph."
                        "win32LobAppAssignmentSettings"
                    ),

                "notifications":
                    cleaned_notifications,

                "deliveryOptimizationPriority":
                    "notConfigured",
            },
        }

        response = self._request(
            "POST",
            url,
            json_body=body,
            expected_statuses=(
                201,
            ),
        )

        try:
            created_assignment = response.json()

        except ValueError as error:
            raise ApplicationActionError(
                "Microsoft Graph returned a non-JSON "
                "created assignment response."
            ) from error

        if not isinstance(
            created_assignment,
            dict,
        ):
            raise ApplicationActionError(
                "Microsoft Graph returned an invalid "
                "created assignment response."
            )

        assignment_id = validate_identifier(
            created_assignment.get("id"),
            "created assignment ID",
        )

        verified_assignment = (
            self.get_mobile_app_assignment(
                exact_app_id,
                assignment_id,
            )
        )

        verified_group_id = (
            self._assignment_group_id(
                verified_assignment
            )
        )

        verified_intent = str(
            verified_assignment.get(
                "intent",
                "",
            )
        ).strip()

        if (
            verified_group_id
            != exact_group_id.lower()
            or verified_intent
            != cleaned_intent
        ):
            raise ApplicationActionError(
                "Microsoft Graph created the assignment, "
                "but verification returned a different "
                "target or intent."
            )

        return ApplicationAssignmentCreateResult(
            application_id=(
                exact_app_id
            ),
            application_name=(
                application.get(
                    "displayName"
                )
            ),
            application_type=(
                application_type
            ),
            assignment_id=(
                assignment_id
            ),
            group_id=(
                exact_group_id
            ),
            group_name=(
                group.get(
                    "displayName"
                )
            ),
            intent=(
                cleaned_intent
            ),
            notifications=(
                cleaned_notifications
            ),
            created=True,
            verified=True,
        )

    # ======================================
    # Delete One Assignment
    # ======================================

    def delete_mobile_app_assignment(
        self,
        mobile_app_id: Any,
        assignment_id: Any,
    ) -> ApplicationAssignmentDeleteResult:
        application = self.get_mobile_application(
            mobile_app_id
        )

        exact_app_id = validate_identifier(
            application.get("id"),
            "resolved mobile-application ID",
        )

        assignment = self.get_mobile_app_assignment(
            exact_app_id,
            assignment_id,
        )

        exact_assignment_id = (
            validate_identifier(
                assignment.get("id"),
                "resolved assignment ID",
            )
        )

        encoded_app_id = graph_path_segment(
            exact_app_id,
            "resolved mobile-application ID",
        )

        encoded_assignment_id = (
            graph_path_segment(
                exact_assignment_id,
                "resolved assignment ID",
            )
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceAppManagement/mobileApps/"
            f"{encoded_app_id}/assignments/"
            f"{encoded_assignment_id}"
        )

        self._request(
            "DELETE",
            url,
            expected_statuses=(
                204,
            ),
        )

        remaining_assignments = (
            self.list_mobile_app_assignments(
                exact_app_id
            )
        )

        still_exists = any(
            str(
                item.get(
                    "id",
                    "",
                )
            ).strip()
            == exact_assignment_id
            for item in remaining_assignments
        )

        if still_exists:
            raise ApplicationActionError(
                "Microsoft Graph accepted the assignment "
                "deletion, but verification still returned "
                "the assignment."
            )

        return ApplicationAssignmentDeleteResult(
            application_id=(
                exact_app_id
            ),
            application_name=(
                application.get(
                    "displayName"
                )
            ),
            assignment_id=(
                exact_assignment_id
            ),
            deleted=True,
            remaining_assignment_count=(
                len(
                    remaining_assignments
                )
            ),
        )

    # ======================================
    # Delete Application
    # ======================================

    def delete_mobile_application(
        self,
        mobile_app_id: Any,
        *,
        allow_assigned: bool = False,
    ) -> ApplicationDeleteResult:
        if not isinstance(
            allow_assigned,
            bool,
        ):
            raise TypeError(
                "allow_assigned must be a boolean."
            )

        application = self.get_mobile_application(
            mobile_app_id
        )

        exact_app_id = validate_identifier(
            application.get("id"),
            "resolved mobile-application ID",
        )

        assignments = (
            self.list_mobile_app_assignments(
                exact_app_id
            )
        )

        assignment_count = len(
            assignments
        )

        if (
            assignment_count > 0
            and not allow_assigned
        ):
            raise ApplicationHasAssignmentsError(
                "The application still has "
                f"{assignment_count} assignment"
                f"{'' if assignment_count == 1 else 's'}. "
                "Review or remove assignments before "
                "deleting the application."
            )

        encoded_app_id = graph_path_segment(
            exact_app_id,
            "resolved mobile-application ID",
        )

        url = (
            f"{GRAPH_API_ROOT}"
            "/deviceAppManagement/mobileApps/"
            f"{encoded_app_id}"
        )

        self._request(
            "DELETE",
            url,
            expected_statuses=(
                204,
            ),
        )

        verified_deleted = False

        try:
            self.get_mobile_application(
                exact_app_id
            )

        except GraphResourceNotFoundError:
            verified_deleted = True

        if not verified_deleted:
            raise ApplicationActionError(
                "Microsoft Graph accepted the application "
                "deletion, but verification still returned "
                "the application."
            )

        return ApplicationDeleteResult(
            application_id=(
                exact_app_id
            ),
            application_name=(
                application.get(
                    "displayName"
                )
            ),
            assignment_count_before_delete=(
                assignment_count
            ),
            deleted=True,
            verified_deleted=(
                verified_deleted
            ),
        )


# ==========================================
# Convenience Functions
# ==========================================

def get_mobile_application(
    mobile_app_id: Any,
) -> dict[str, Any]:
    with ProtectedApplicationGraphClient() as client:
        return client.get_mobile_application(
            mobile_app_id
        )


def list_mobile_app_assignments(
    mobile_app_id: Any,
) -> list[dict[str, Any]]:
    with ProtectedApplicationGraphClient() as client:
        return client.list_mobile_app_assignments(
            mobile_app_id
        )


def create_win32_group_assignment(
    mobile_app_id: Any,
    group_id: Any,
    *,
    intent: Any,
    notifications: Any = "showAll",
) -> dict[str, Any]:
    with ProtectedApplicationGraphClient() as client:
        return (
            client
            .create_win32_group_assignment(
                mobile_app_id,
                group_id,
                intent=intent,
                notifications=notifications,
            )
            .to_dict()
        )


def delete_mobile_app_assignment(
    mobile_app_id: Any,
    assignment_id: Any,
) -> dict[str, Any]:
    with ProtectedApplicationGraphClient() as client:
        return (
            client
            .delete_mobile_app_assignment(
                mobile_app_id,
                assignment_id,
            )
            .to_dict()
        )


def delete_mobile_application(
    mobile_app_id: Any,
    *,
    allow_assigned: bool = False,
) -> dict[str, Any]:
    with ProtectedApplicationGraphClient() as client:
        return (
            client
            .delete_mobile_application(
                mobile_app_id,
                allow_assigned=(
                    allow_assigned
                ),
            )
            .to_dict()
        )