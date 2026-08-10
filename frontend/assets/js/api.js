// ===========================================
// Enterprise Dashboard API Service
// ===========================================

"use strict";

const API_BASE_URL = "http://127.0.0.1:5000";

const CONTROL_PANEL_API_KEY_STORAGE = "controlPanelApiKey";
const CONTROL_PANEL_ADMIN_STORAGE = "controlPanelAdminUser";

console.log("API.JS LOADED");


// ===========================================
// Shared Helpers
// ===========================================

async function parseJsonResponse(response) {
    try {
        return await response.json();
    } catch (error) {
        console.error("Failed to parse JSON response:", error);
        return {};
    }
}

async function requestJson(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    const data = await parseJsonResponse(response);

    if (!response.ok) {
        const error = new Error(
            data.message ||
            data.error ||
            `Request failed with status ${response.status}`
        );

        error.status = response.status;
        error.errorType = data.error_type || null;
        error.details = data.details || null;
        error.response = data;
        throw error;
    }

    return { response, data };
}

async function getCollection(path, label) {
    try {
        const { data } = await requestJson(path);
        return Array.isArray(data) ? data : [];
    } catch (error) {
        console.error(`${label} API Error:`, error);
        return [];
    }
}


// ===========================================
// Existing Dashboard APIs
// ===========================================

async function getApplications() {
    return getCollection("/api/apps", "Applications");
}

async function getUsers() {
    return getCollection("/api/users", "Users");
}

async function getDevices() {
    return getCollection("/api/devices", "Devices");
}

async function syncApplications() {
    try {
        const { data } = await requestJson("/api/sync", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            }
        });

        return {
            success:
                typeof data.success === "boolean"
                    ? data.success
                    : true,
            message:
                data.message ||
                "Enterprise synchronization completed successfully.",
            stdout:
                data.stdout ||
                data.mysql_sync_output ||
                "",
            data
        };
    } catch (error) {
        console.error("Synchronization API Error:", error);

        return {
            success: false,
            message:
                error.message ||
                "Unable to synchronize enterprise data.",
            stdout: "",
            data: error.response || {}
        };
    }
}

async function askEnterpriseAI(question) {
    const cleanedQuestion = String(question || "").trim();

    if (!cleanedQuestion) {
        return {
            success: false,
            question: "",
            answer: "Please enter a question.",
            sources: []
        };
    }

    try {
        const { data } = await requestJson("/api/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                question: cleanedQuestion
            })
        });

        return {
            success: true,
            question: data.question || cleanedQuestion,
            answer: data.answer || "No answer was generated.",
            sources: Array.isArray(data.sources) ? data.sources : [],
            route: data.route || null
        };
    } catch (error) {
        console.error("Enterprise AI API Error:", error);

        return {
            success: false,
            question: cleanedQuestion,
            answer:
                error.message ||
                "Unable to connect to Enterprise AI.",
            sources: []
        };
    }
}

function formatSize(bytes) {
    const numericBytes = Number(bytes);

    if (!Number.isFinite(numericBytes) || numericBytes <= 0) {
        return "-";
    }

    const units = ["Bytes", "KB", "MB", "GB", "TB"];
    let size = numericBytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }

    return `${size.toFixed(2)} ${units[unitIndex]}`;
}


// ===========================================
// Control Panel Session and Headers
// ===========================================

function getControlPanelHeaders(includeJson = true) {
    const headers = {};

    if (includeJson) {
        headers["Content-Type"] = "application/json";
    }

    const apiKey = window.sessionStorage.getItem(
        CONTROL_PANEL_API_KEY_STORAGE
    );

    const administrator = window.sessionStorage.getItem(
        CONTROL_PANEL_ADMIN_STORAGE
    );

    if (apiKey) {
        headers["X-Control-Panel-Key"] = apiKey;
    }

    if (administrator) {
        headers["X-Admin-User"] = administrator;
    }

    return headers;
}

function setControlPanelSession({
    apiKey = "",
    administrator = ""
} = {}) {
    const cleanedApiKey = String(apiKey || "").trim();
    const cleanedAdministrator = String(administrator || "").trim();

    if (cleanedApiKey) {
        window.sessionStorage.setItem(
            CONTROL_PANEL_API_KEY_STORAGE,
            cleanedApiKey
        );
    } else {
        window.sessionStorage.removeItem(
            CONTROL_PANEL_API_KEY_STORAGE
        );
    }

    if (cleanedAdministrator) {
        window.sessionStorage.setItem(
            CONTROL_PANEL_ADMIN_STORAGE,
            cleanedAdministrator
        );
    } else {
        window.sessionStorage.removeItem(
            CONTROL_PANEL_ADMIN_STORAGE
        );
    }

    return {
        apiKeyConfigured: Boolean(cleanedApiKey),
        administrator: cleanedAdministrator || null
    };
}


// ===========================================
// Control Panel Request Helper
// ===========================================

async function controlPanelRequest(
    endpoint,
    {
        method = "GET",
        body,
        includeJson = true
    } = {}
) {
    const options = {
        method,
        headers: getControlPanelHeaders(includeJson)
    };

    if (body !== undefined) {
        options.body = JSON.stringify(body);
    }

    try {
        const { response, data } = await requestJson(
            endpoint,
            options
        );

        return {
            success: true,
            status: response.status,
            data
        };
    } catch (error) {
        console.error("Control Panel API Error:", endpoint, error);

        return {
            success: false,
            status: Number(error.status || 0),
            message:
                error.message ||
                "Unable to reach the Control Panel API.",
            errorType: error.errorType || null,
            details: error.details || null,
            data: error.response || {}
        };
    }
}


// ===========================================
// Control Panel APIs
// ===========================================

async function getControlCapabilities() {
    const result = await controlPanelRequest(
        "/api/control/capabilities",
        {
            includeJson: false
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            actions: [],
            mode: null,
            authentication: null
        };
    }

    return {
        success: true,
        message:
            result.data.message ||
            "Control Panel capabilities loaded.",
        actions:
            Array.isArray(result.data.actions)
                ? result.data.actions
                : [],
        mode: result.data.mode || null,
        authentication: result.data.authentication || null,
        data: result.data
    };
}

async function planControlAction(
    action,
    targetId,
    {
        assignmentId = null,
        groupId = null,
        intent = null,
        notifications = null
    } = {}
) {
    const cleanedAction = String(action || "").trim();
    const cleanedTargetId = String(targetId || "").trim();

    const cleanedAssignmentId = assignmentId === null
        ? null
        : String(assignmentId || "").trim();

    const cleanedGroupId = groupId === null
        ? null
        : String(groupId || "").trim();

    const cleanedIntent = intent === null
        ? null
        : String(intent || "").trim();

    const cleanedNotifications = notifications === null
        ? null
        : String(notifications || "").trim();

    if (!cleanedAction || !cleanedTargetId) {
        return {
            success: false,
            message: "Action and target ID are required."
        };
    }

    const body = {
        action: cleanedAction,
        target_id: cleanedTargetId
    };

    if (cleanedAssignmentId) {
        body.assignment_id = cleanedAssignmentId;
    }

    if (cleanedGroupId) {
        body.group_id = cleanedGroupId;
    }

    if (cleanedIntent) {
        body.intent = cleanedIntent;
    }

    if (cleanedNotifications) {
        body.notifications = cleanedNotifications;
    }

    const result = await controlPanelRequest(
        "/api/control/actions/plan",
        {
            method: "POST",
            body
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            errorType: result.errorType,
            details: result.details,
            data: result.data
        };
    }

    return {
        success: true,
        message:
            result.data.message ||
            "Action plan created.",
        requiresConfirmation: Boolean(
            result.data.requires_confirmation
        ),
        noActionRequired: Boolean(
            result.data.no_action_required
        ),
        confirmationId:
            result.data.confirmation_id ||
            null,
        action:
            result.data.action ||
            null,
        plan:
            result.data.plan ||
            null,
        data: result.data
    };
}


async function getApplicationAssignments(
    applicationId
) {
    const cleanedApplicationId = String(
        applicationId || ""
    ).trim();

    if (!cleanedApplicationId) {
        return {
            success: false,
            message: "Application ID is required.",
            application: null,
            assignments: [],
            count: 0
        };
    }

    const result = await controlPanelRequest(
        (
            "/api/control/applications/" +
            encodeURIComponent(
                cleanedApplicationId
            ) +
            "/assignments"
        ),
        {
            method: "GET",
            includeJson: false
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            errorType: result.errorType,
            details: result.details,
            application: null,
            assignments: [],
            count: 0,
            data: result.data
        };
    }

    const assignments = Array.isArray(
        result.data.assignments
    )
        ? result.data.assignments
        : [];

    return {
        success: true,
        application:
            result.data.application ||
            null,
        assignments,
        count: Number(
            result.data.count ??
            assignments.length
        ),
        data: result.data
    };
}


async function confirmControlAction(
    confirmationId,
    confirmationText = ""
) {
    const cleanedId = String(confirmationId || "").trim();

    if (!cleanedId) {
        return {
            success: false,
            message: "Confirmation ID is required."
        };
    }

    const result = await controlPanelRequest(
        "/api/control/actions/confirm",
        {
            method: "POST",
            body: {
                confirmation_id: cleanedId,
                confirmation_text:
                    String(confirmationText || "").trim()
            }
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            errorType: result.errorType,
            details: result.details,
            data: result.data
        };
    }

    return {
        success: true,
        message:
            result.data.message ||
            "Action completed successfully.",
        action:
            result.data.action ||
            null,
        result:
            result.data.result ||
            null,
        data: result.data
    };
}

async function cancelControlAction(confirmationId) {
    const cleanedId = String(confirmationId || "").trim();

    if (!cleanedId) {
        return {
            success: false,
            message: "Confirmation ID is required."
        };
    }

    const result = await controlPanelRequest(
        "/api/control/actions/cancel",
        {
            method: "POST",
            body: {
                confirmation_id: cleanedId
            }
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            errorType: result.errorType,
            details: result.details,
            data: result.data
        };
    }

    return {
        success: true,
        message:
            result.data.message ||
            "Pending action cancelled.",
        action:
            result.data.action ||
            null,
        data: result.data
    };
}

async function getControlJobs(limit = 100, statuses = []) {
    const numericLimit = Number(limit);

    const safeLimit =
        Number.isInteger(numericLimit) &&
        numericLimit > 0
            ? Math.min(numericLimit, 500)
            : 100;

    const parameters = new URLSearchParams();
    parameters.set("limit", String(safeLimit));

    if (Array.isArray(statuses)) {
        statuses.forEach((status) => {
            const value = String(status || "").trim();

            if (value) {
                parameters.append("status", value);
            }
        });
    }

    const result = await controlPanelRequest(
        `/api/control/jobs?${parameters.toString()}`,
        {
            includeJson: false
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            jobs: [],
            count: 0,
            errorType: result.errorType
        };
    }

    const jobs = Array.isArray(result.data.jobs)
        ? result.data.jobs
        : [];

    return {
        success: true,
        jobs,
        count: Number(result.data.count ?? jobs.length),
        data: result.data
    };
}

async function getControlJob(identifier) {
    const cleanedIdentifier = String(identifier || "").trim();

    if (!cleanedIdentifier) {
        return {
            success: false,
            message: "Job identifier is required.",
            job: null
        };
    }

    const result = await controlPanelRequest(
        `/api/control/jobs/${encodeURIComponent(cleanedIdentifier)}`,
        {
            includeJson: false
        }
    );

    if (!result.success) {
        return {
            success: false,
            message: result.message,
            job: null,
            errorType: result.errorType,
            data: result.data
        };
    }

    return {
        success: true,
        job: result.data.job || null,
        data: result.data
    };
}