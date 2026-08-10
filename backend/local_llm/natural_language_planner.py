from __future__ import annotations

"""
Safe Natural Language Planner for the local remediation agent.

Supported operations:
- scan live tenant issues;
- list and filter detected issues;
- explain one exact issue ID;
- prepare an allowlisted remediation for one exact issue ID;
- list prepared remediations;
- retrieve a validated Control Panel planning request.

The planner never:
- calls Microsoft Graph write endpoints;
- confirms or executes Control Panel actions;
- accepts arbitrary URLs, HTTP methods, SQL, code, tokens, or secrets;
- invents issue IDs, remediation IDs, or tenant object IDs;
- bypasses role checks or typed confirmation.

A local LLM may be supplied as a JSON-only classifier, but deterministic
parsing is attempted first.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping
import json
import re

from .agent_service import LocalRemediationAgent, default_agent
from .live_remediation_service import (
    LiveRemediationService,
    default_live_service,
)
from .remediation_models import (
    ALLOWED_REMEDIATION_ACTIONS,
    RemediationAction,
    Severity,
    validate_model_json,
)


ModelGenerateCallable = Callable[
    [str],
    str | Mapping[str, Any],
]


class NaturalLanguagePlannerError(
    ValueError
):
    """Base exception for Natural Language Planner failures."""


class UnsupportedNaturalLanguageCommandError(
    NaturalLanguagePlannerError
):
    """Raised when the command cannot be safely mapped to a supported task."""


class LowConfidenceCommandError(
    NaturalLanguagePlannerError
):
    """Raised when model-assisted classification is below the threshold."""


class InventedIdentifierError(
    NaturalLanguagePlannerError
):
    """Raised when a model returns an ID not present in the administrator text."""


class CommandIntent(str, Enum):
    ISSUE_SCAN = "issue_scan"
    ISSUE_LIST = "issue_list"
    ISSUE_EXPLANATION = "issue_explanation"
    REMEDIATION_PLAN = "remediation_plan"
    REMEDIATION_LIST = "remediation_list"
    CONTROL_PLAN = "control_plan"
    STATUS = "status"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True)
class ParsedCommand:
    intent: CommandIntent
    confidence: float
    command: str
    issue_id: str | None = None
    remediation_id: str | None = None
    requested_action: RemediationAction | None = None
    severity: Severity | None = None
    category: str | None = None
    parameters: dict[str, Any] = field(
        default_factory=dict
    )
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent":
                self.intent.value,

            "confidence":
                self.confidence,

            "command":
                self.command,

            "issue_id":
                self.issue_id,

            "remediation_id":
                self.remediation_id,

            "requested_action":
                (
                    self.requested_action.value
                    if self.requested_action
                    else None
                ),

            "severity":
                (
                    self.severity.value
                    if self.severity
                    else None
                ),

            "category":
                self.category,

            "parameters":
                dict(
                    self.parameters
                ),

            "explanation":
                self.explanation,
        }


@dataclass(slots=True)
class NaturalLanguageResult:
    parsed: ParsedCommand
    result: dict[str, Any]
    execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success":
                True,

            "execution_performed":
                self.execution_performed,

            "parsed":
                self.parsed.to_dict(),

            "result":
                dict(
                    self.result
                ),
        }


ISSUE_ID_PATTERN = re.compile(
    r"\bISSUE-[A-Z0-9-]+\b",
    re.IGNORECASE,
)

REMEDIATION_ID_PATTERN = re.compile(
    r"\bREMED-[A-Z0-9-]+\b",
    re.IGNORECASE,
)

GUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-"
    r"[0-9a-f]{12}\b",
    re.IGNORECASE,
)

SEVERITY_WORDS = {
    severity.value:
        severity
    for severity
    in Severity
}

ACTION_PHRASES: tuple[
    tuple[
        re.Pattern[str],
        RemediationAction,
    ],
    ...,
] = (
    (
        re.compile(
            r"\benable(?:\s+user)?\b",
            re.IGNORECASE,
        ),
        RemediationAction.ENABLE_USER,
    ),
    (
        re.compile(
            r"\bdisable(?:\s+user)?\b",
            re.IGNORECASE,
        ),
        RemediationAction.DISABLE_USER,
    ),
    (
        re.compile(
            r"\bsync(?:hronize)?(?:\s+device)?\b",
            re.IGNORECASE,
        ),
        RemediationAction.SYNC_DEVICE,
    ),
    (
        re.compile(
            r"\b(?:restart|reboot)(?:\s+device)?\b",
            re.IGNORECASE,
        ),
        RemediationAction.RESTART_DEVICE,
    ),
    (
        re.compile(
            r"\bassign(?:\s+application)?(?:\s+to\s+group)?\b",
            re.IGNORECASE,
        ),
        RemediationAction.ASSIGN_APPLICATION_GROUP,
    ),
    (
        re.compile(
            r"\b(?:remove|delete)\s+(?:application\s+)?assignment\b",
            re.IGNORECASE,
        ),
        RemediationAction.DELETE_APPLICATION_ASSIGNMENT,
    ),
    (
        re.compile(
            r"\bdelete\s+(?:the\s+)?application\b",
            re.IGNORECASE,
        ),
        RemediationAction.DELETE_APPLICATION,
    ),
)


_ALLOWED_PARAMETER_KEYS = frozenset({
    "group_id",
    "assignment_id",
    "intent",
    "notifications",
})


_FORBIDDEN_TEXT_MARKERS = (
    "access_token",
    "client_secret",
    "authorization: bearer",
    "graph.microsoft.com/",
    "drop table",
    "delete from ",
    "insert into ",
    "update set ",
)


def _clean_command(
    value: Any,
) -> str:
    command = str(
        value or ""
    ).strip()

    if not command:
        raise NaturalLanguagePlannerError(
            "command is required."
        )

    if len(command) > 4000:
        raise NaturalLanguagePlannerError(
            "command exceeds 4000 characters."
        )

    lowered = command.lower()

    if any(
        marker in lowered
        for marker
        in _FORBIDDEN_TEXT_MARKERS
    ):
        raise NaturalLanguagePlannerError(
            "The command contains credentials, arbitrary "
            "Graph access, SQL, or another forbidden operation."
        )

    return command


def _extract_exact_identifier(
    pattern: re.Pattern[str],
    command: str,
) -> str | None:
    match = pattern.search(
        command
    )

    if not match:
        return None

    return match.group(
        0
    ).upper()


def _extract_severity(
    command: str,
) -> Severity | None:
    lowered = command.lower()

    for word, severity in SEVERITY_WORDS.items():
        if re.search(
            rf"\b{re.escape(word)}\b",
            lowered,
        ):
            return severity

    return None


def _extract_action(
    command: str,
) -> RemediationAction | None:
    for pattern, action in ACTION_PHRASES:
        if pattern.search(
            command
        ):
            return action

    return None


def _extract_parameters(
    command: str,
    action: RemediationAction | None,
) -> dict[str, Any]:
    parameters: dict[
        str,
        Any,
    ] = {}

    if (
        action
        == RemediationAction
        .ASSIGN_APPLICATION_GROUP
    ):
        guid_matches = GUID_PATTERN.findall(
            command
        )

        if guid_matches:
            parameters[
                "group_id"
            ] = guid_matches[-1]

        intent_match = re.search(
            r"\b(available|required|uninstall)\b",
            command,
            re.IGNORECASE,
        )

        if intent_match:
            parameters[
                "intent"
            ] = (
                intent_match.group(
                    1
                )
            )

        notification_match = re.search(
            r"\b(showAll|showReboot|hideAll)\b",
            command,
            re.IGNORECASE,
        )

        if notification_match:
            parameters[
                "notifications"
            ] = (
                notification_match.group(
                    1
                )
            )

    elif (
        action
        == RemediationAction
        .DELETE_APPLICATION_ASSIGNMENT
    ):
        assignment_match = re.search(
            r"\bassignment(?:\s+id)?\s*[:=]?\s*"
            r"([A-Za-z0-9-]{6,512})\b",
            command,
            re.IGNORECASE,
        )

        if assignment_match:
            parameters[
                "assignment_id"
            ] = assignment_match.group(
                1
            )

    return parameters


def _deterministic_parse(
    command: str,
) -> ParsedCommand | None:
    lowered = command.lower()

    issue_id = _extract_exact_identifier(
        ISSUE_ID_PATTERN,
        command,
    )

    remediation_id = _extract_exact_identifier(
        REMEDIATION_ID_PATTERN,
        command,
    )

    requested_action = _extract_action(
        command
    )

    if re.search(
        r"\b(?:status|health)\b.*\b(?:ai|agent|planner)\b"
        r"|\b(?:ai|agent|planner)\b.*\b(?:status|health)\b",
        lowered,
    ):
        return ParsedCommand(
            intent=CommandIntent.STATUS,
            confidence=1.0,
            command=command,
            explanation=(
                "Matched the local remediation "
                "agent status command."
            ),
        )

    if (
        remediation_id
        and re.search(
            r"\b(?:control\s+plan|request\s+body|protected\s+plan)\b",
            lowered,
        )
    ):
        return ParsedCommand(
            intent=CommandIntent.CONTROL_PLAN,
            confidence=1.0,
            command=command,
            remediation_id=remediation_id,
            explanation=(
                "Matched an exact remediation ID "
                "and Control Panel plan request."
            ),
        )

    if (
        issue_id
        and re.search(
            r"\b(?:fix|remediate|repair|resolve|prepare|plan)\b",
            lowered,
        )
    ):
        return ParsedCommand(
            intent=CommandIntent.REMEDIATION_PLAN,
            confidence=1.0,
            command=command,
            issue_id=issue_id,
            requested_action=requested_action,
            parameters=_extract_parameters(
                command,
                requested_action,
            ),
            explanation=(
                "Matched an exact issue ID and "
                "a remediation planning verb."
            ),
        )

    if (
        issue_id
        and re.search(
            r"\b(?:explain|why|details?|describe|show)\b",
            lowered,
        )
    ):
        return ParsedCommand(
            intent=CommandIntent.ISSUE_EXPLANATION,
            confidence=1.0,
            command=command,
            issue_id=issue_id,
            explanation=(
                "Matched an exact issue ID and "
                "an explanation request."
            ),
        )

    if re.search(
        r"\b(?:scan|find|detect|analyse|analyze|check)\b"
        r".*\b(?:issue|issues|problem|problems)\b"
        r"|\b(?:issue|issues|problem|problems)\b"
        r".*\b(?:scan|find|detect|analyse|analyze|check)\b",
        lowered,
    ):
        return ParsedCommand(
            intent=CommandIntent.ISSUE_SCAN,
            confidence=0.99,
            command=command,
            explanation=(
                "Matched a live issue scan request."
            ),
        )

    if re.search(
        r"\b(?:list|show|get|display)\b"
        r".*\b(?:remediation|remediations|plans)\b",
        lowered,
    ):
        return ParsedCommand(
            intent=CommandIntent.REMEDIATION_LIST,
            confidence=0.98,
            command=command,
            issue_id=issue_id,
            explanation=(
                "Matched a prepared remediation list request."
            ),
        )

    if re.search(
        r"\b(?:list|show|get|display)\b"
        r".*\b(?:issue|issues|problems)\b"
        r"|\b(?:issue|issues|problems)\b"
        r".*\b(?:list|show|get|display)\b",
        lowered,
    ):
        category_match = re.search(
            r"\bcategory\s*[:=]?\s*([a-z0-9_-]+)\b",
            lowered,
        )

        return ParsedCommand(
            intent=CommandIntent.ISSUE_LIST,
            confidence=0.98,
            command=command,
            severity=_extract_severity(
                command
            ),
            category=(
                category_match.group(
                    1
                )
                if category_match
                else None
            ),
            explanation=(
                "Matched a detected issue list request."
            ),
        )

    return None


def _classifier_prompt(
    command: str,
) -> str:
    allowed_actions = ", ".join(
        sorted(
            ALLOWED_REMEDIATION_ACTIONS
        )
    )

    return f"""
You are a strict command classifier for a local Microsoft Intune
remediation planner.

Classify the administrator command into exactly one supported intent:
- issue_scan
- issue_list
- issue_explanation
- remediation_plan
- remediation_list
- control_plan
- status
- unsupported

Allowed remediation actions:
{allowed_actions}

Rules:
1. Return one JSON object only. Do not use markdown.
2. Do not invent issue IDs, remediation IDs, tenant object IDs, group IDs,
   or assignment IDs.
3. An issue ID or remediation ID may be returned only when it appears
   literally in the administrator command.
4. Never produce a Graph URL, HTTP method, SQL, code, token, secret,
   request headers, or arbitrary request body.
5. The planner prepares actions only; it never executes them.
6. When uncertain, use unsupported.

Required JSON shape:
{{
  "intent": "unsupported",
  "confidence": 0.0,
  "issue_id": null,
  "remediation_id": null,
  "requested_action": null,
  "severity": null,
  "category": null,
  "parameters": {{}},
  "explanation": "brief reason"
}}

Administrator command:
{json.dumps(command)}
""".strip()


def _parse_model_response(
    *,
    command: str,
    raw_response: (
        str
        | Mapping[str, Any]
    ),
) -> ParsedCommand:
    if isinstance(
        raw_response,
        Mapping,
    ):
        data = dict(
            raw_response
        )
    else:
        data = validate_model_json(
            raw_response
        )

    try:
        intent = CommandIntent(
            data.get(
                "intent",
                "unsupported",
            )
        )
    except ValueError as error:
        raise NaturalLanguagePlannerError(
            "The model returned an unsupported intent."
        ) from error

    try:
        confidence = float(
            data.get(
                "confidence",
                0.0,
            )
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise NaturalLanguagePlannerError(
            "The model confidence is invalid."
        ) from error

    if not 0.0 <= confidence <= 1.0:
        raise NaturalLanguagePlannerError(
            "The model confidence must be "
            "between zero and one."
        )

    issue_id = data.get(
        "issue_id"
    )

    remediation_id = data.get(
        "remediation_id"
    )

    if issue_id is not None:
        issue_id = str(
            issue_id
        ).strip().upper()

        if (
            not ISSUE_ID_PATTERN.fullmatch(
                issue_id
            )
            or issue_id.lower()
            not in command.lower()
        ):
            raise InventedIdentifierError(
                "The model returned an issue ID "
                "that was not present in the command."
            )

    if remediation_id is not None:
        remediation_id = str(
            remediation_id
        ).strip().upper()

        if (
            not REMEDIATION_ID_PATTERN.fullmatch(
                remediation_id
            )
            or remediation_id.lower()
            not in command.lower()
        ):
            raise InventedIdentifierError(
                "The model returned a remediation ID "
                "that was not present in the command."
            )

    action_value = data.get(
        "requested_action"
    )

    requested_action = (
        RemediationAction(
            action_value
        )
        if action_value
        is not None
        else None
    )

    severity_value = data.get(
        "severity"
    )

    severity = (
        Severity(
            severity_value
        )
        if severity_value
        is not None
        else None
    )

    category_value = data.get(
        "category"
    )

    category = (
        str(
            category_value
        ).strip()
        if category_value
        is not None
        else None
    )

    parameters = data.get(
        "parameters"
    ) or {}

    if not isinstance(
        parameters,
        Mapping,
    ):
        raise NaturalLanguagePlannerError(
            "The model parameters must be a JSON object."
        )

    unexpected = (
        set(
            str(key)
            for key in parameters
        )
        - set(
            _ALLOWED_PARAMETER_KEYS
        )
    )

    if unexpected:
        raise NaturalLanguagePlannerError(
            "The model returned unsupported parameter(s): "
            + ", ".join(
                sorted(
                    unexpected
                )
            )
        )

    safe_parameters = {
        str(key):
            value
        for key, value
        in parameters.items()
        if value is not None
    }

    # Group and assignment identifiers must also appear literally in the
    # administrator command. This prevents the classifier from inventing them.
    for identifier_key in (
        "group_id",
        "assignment_id",
    ):
        identifier = safe_parameters.get(
            identifier_key
        )

        if (
            identifier is not None
            and str(
                identifier
            ).lower()
            not in command.lower()
        ):
            raise InventedIdentifierError(
                f"The model returned {identifier_key} "
                "that was not present in the command."
            )

    explanation = str(
        data.get(
            "explanation"
        )
        or "Classified by the local model."
    ).strip()

    return ParsedCommand(
        intent=intent,
        confidence=confidence,
        command=command,
        issue_id=issue_id,
        remediation_id=remediation_id,
        requested_action=requested_action,
        severity=severity,
        category=category,
        parameters=safe_parameters,
        explanation=explanation,
    )


def _issue_explanation(
    issue: Any,
) -> dict[str, Any]:
    recommendations = [
        recommendation.to_dict()
        for recommendation
        in issue.recommendations
    ]

    return {
        "issue":
            issue.to_dict(),

        "summary":
            issue.description,

        "evidence":
            dict(
                issue.evidence
            ),

        "recommended_remediations":
            recommendations,

        "requires_human_review":
            True,

        "execution_performed":
            False,
    }


class NaturalLanguagePlanner:
    def __init__(
        self,
        *,
        agent: LocalRemediationAgent | None = None,
        live_service: LiveRemediationService | None = None,
        model_generate: ModelGenerateCallable | None = None,
        minimum_model_confidence: float = 0.80,
    ) -> None:
        if not 0.0 <= minimum_model_confidence <= 1.0:
            raise ValueError(
                "minimum_model_confidence must be "
                "between zero and one."
            )

        self.agent = (
            agent
            or default_agent()
        )

        self.live_service = (
            live_service
            or default_live_service()
        )

        self.model_generate = (
            model_generate
        )

        self.minimum_model_confidence = (
            minimum_model_confidence
        )

    def parse(
        self,
        command: Any,
    ) -> ParsedCommand:
        cleaned = _clean_command(
            command
        )

        deterministic = _deterministic_parse(
            cleaned
        )

        if deterministic is not None:
            return deterministic

        if self.model_generate is None:
            raise UnsupportedNaturalLanguageCommandError(
                "The command did not match a supported "
                "Natural Language Planner operation."
            )

        raw_response = self.model_generate(
            _classifier_prompt(
                cleaned
            )
        )

        parsed = _parse_model_response(
            command=cleaned,
            raw_response=raw_response,
        )

        if (
            parsed.intent
            == CommandIntent.UNSUPPORTED
        ):
            raise UnsupportedNaturalLanguageCommandError(
                parsed.explanation
            )

        if (
            parsed.confidence
            < self.minimum_model_confidence
        ):
            raise LowConfidenceCommandError(
                "The local model was not confident "
                "enough to prepare this operation."
            )

        return parsed

    def handle(
        self,
        *,
        command: Any,
        actor_roles: Iterable[str],
    ) -> NaturalLanguageResult:
        parsed = self.parse(
            command
        )

        if (
            parsed.intent
            == CommandIntent.STATUS
        ):
            result = (
                self.agent
                .snapshot()
                .to_dict()
            )

        elif (
            parsed.intent
            == CommandIntent.ISSUE_SCAN
        ):
            result = (
                self.live_service
                .scan_live_issues()
            )

        elif (
            parsed.intent
            == CommandIntent.ISSUE_LIST
        ):
            issues = self.agent.list_issues(
                severity=parsed.severity,
                category=parsed.category,
                limit=250,
            )

            result = {
                "count":
                    len(
                        issues
                    ),

                "issues": [
                    issue.to_dict()
                    for issue
                    in issues
                ],
            }

        elif (
            parsed.intent
            == CommandIntent.ISSUE_EXPLANATION
        ):
            if not parsed.issue_id:
                raise NaturalLanguagePlannerError(
                    "An exact ISSUE-... ID is required."
                )

            issue = self.agent.get_issue(
                parsed.issue_id
            )

            result = _issue_explanation(
                issue
            )

        elif (
            parsed.intent
            == CommandIntent.REMEDIATION_PLAN
        ):
            if not parsed.issue_id:
                raise NaturalLanguagePlannerError(
                    "An exact ISSUE-... ID is required."
                )

            remediation = (
                self.agent
                .prepare_remediation(
                    issue_id=(
                        parsed.issue_id
                    ),
                    actor_roles=(
                        actor_roles
                    ),
                    requested_action=(
                        parsed.requested_action
                    ),
                    parameter_overrides=(
                        parsed.parameters
                    ),
                )
            )

            result = {
                "remediation":
                    remediation.to_dict(),

                "execution_performed":
                    False,

                "next_step":
                    (
                        "Retrieve the validated Control "
                        "Panel request, then submit it to "
                        "/api/control/actions/plan."
                    ),
            }

        elif (
            parsed.intent
            == CommandIntent.REMEDIATION_LIST
        ):
            remediations = (
                self.agent
                .list_remediations(
                    issue_id=(
                        parsed.issue_id
                    ),
                    limit=250,
                )
            )

            result = {
                "count":
                    len(
                        remediations
                    ),

                "remediations": [
                    remediation.to_dict()
                    for remediation
                    in remediations
                ],
            }

        elif (
            parsed.intent
            == CommandIntent.CONTROL_PLAN
        ):
            if not parsed.remediation_id:
                raise NaturalLanguagePlannerError(
                    "An exact REMED-... ID is required."
                )

            remediation = (
                self.agent
                .get_remediation(
                    parsed.remediation_id
                )
            )

            result = {
                "remediation_id":
                    remediation.remediation_id,

                "approval_mode":
                    remediation
                    .permission
                    .approval_mode
                    .value,

                "confirmation_phrase":
                    remediation
                    .permission
                    .confirmation_phrase,

                "control_plan_request":
                    self.agent
                    .get_control_plan_request(
                        parsed.remediation_id
                    ),

                "next_endpoint":
                    "/api/control/actions/plan",

                "execution_performed":
                    False,
            }

        else:
            raise UnsupportedNaturalLanguageCommandError(
                "The command is not supported."
            )

        return NaturalLanguageResult(
            parsed=parsed,
            result=result,
            execution_performed=False,
        )


_default_planner: NaturalLanguagePlanner | None = None


def default_natural_language_planner(
) -> NaturalLanguagePlanner:
    global _default_planner

    if _default_planner is None:
        _default_planner = (
            NaturalLanguagePlanner()
        )

    return _default_planner


def handle_natural_language_command(
    *,
    command: Any,
    actor_roles: Iterable[str],
) -> dict[str, Any]:
    return (
        default_natural_language_planner()
        .handle(
            command=command,
            actor_roles=actor_roles,
        )
        .to_dict()
    )