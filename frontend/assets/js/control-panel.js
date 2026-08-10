// ===========================================
// Enterprise Control Panel
// ===========================================
//
// Supported real backend actions:
//
// - enable_user
// - disable_user
// - sync_device
// - restart_device
// - assign_application_group
// - delete_application
// - delete_application_assignment
//
// Application upload remains disabled.
// ===========================================

"use strict";

const CONTROL_AUDIT_STORAGE_KEY =
    "enterpriseControlPanelAuditV2";

const controlState = {
    applications: [],
    users: [],
    devices: [],
    jobs: [],
    audit: readStoredArray(CONTROL_AUDIT_STORAGE_KEY),
    capabilities: new Map(),
    pendingAction: null,
    loading: false,
    authPromptActive: false
};

let controlToastTimer = null;


// ===========================================
// Start
// ===========================================

document.addEventListener(
    "DOMContentLoaded",
    async function () {
        setupTabs();
        setupFilters();
        setupButtons();
        setupCommandPlanner();
        setupActionDialog();
        renderAudit();

        await refreshControlPanel();
    }
);


// ===========================================
// Storage and General Helpers
// ===========================================

function readStoredArray(key) {
    try {
        const value = JSON.parse(
            window.localStorage.getItem(key) || "[]"
        );

        return Array.isArray(value) ? value : [];
    } catch (error) {
        console.warn(`Could not read ${key}:`, error);
        return [];
    }
}

function saveStoredArray(key, value) {
    try {
        window.localStorage.setItem(
            key,
            JSON.stringify(value)
        );
    } catch (error) {
        console.warn(`Could not save ${key}:`, error);
    }
}

function byId(id) {
    return document.getElementById(id);
}

function normalizeText(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, " ");
}

function normalizeKey(value) {
    return normalizeText(value)
        .replace(/[^a-z0-9]/g, "");
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function setText(id, value) {
    const element = byId(id);

    if (element) {
        element.textContent = String(value);
    }
}

function formatDate(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? String(value)
        : date.toLocaleString();
}

function parseBoolean(value) {
    if (typeof value === "boolean") {
        return value;
    }

    if (value === 1 || value === "1") {
        return true;
    }

    if (value === 0 || value === "0") {
        return false;
    }

    const normalized = normalizeText(value);

    if (["true", "yes", "enabled", "active"].includes(normalized)) {
        return true;
    }

    if (["false", "no", "disabled", "inactive"].includes(normalized)) {
        return false;
    }

    return null;
}

function getUserStatus(user) {
    const value = parseBoolean(
        user.account_enabled ??
        user.accountEnabled
    );

    return value === true
        ? "enabled"
        : value === false
            ? "disabled"
            : "unknown";
}

function getApplicationState(application) {
    return (
        normalizeText(
            application.publishing_state ??
            application.publishingState
        ) ||
        "unknown"
    );
}

function getDeviceCompliance(device) {
    const value = normalizeKey(
        device.compliance_state ??
        device.complianceState
    );

    if (value === "compliant") {
        return "compliant";
    }

    if (["noncompliant", "notcompliant"].includes(value)) {
        return "noncompliant";
    }

    return "unknown";
}

function getTargetName(kind, record) {
    if (kind === "user") {
        return (
            record.display_name ||
            record.displayName ||
            record.mail ||
            record.user_principal_name ||
            record.userPrincipalName ||
            record.id ||
            "Unknown user"
        );
    }

    if (kind === "application") {
        return (
            record.display_name ||
            record.displayName ||
            record.id ||
            "Unknown application"
        );
    }

    if (kind === "device") {
        return (
            record.device_name ||
            record.deviceName ||
            record.id ||
            "Unknown device"
        );
    }

    return record.name || "Unknown target";
}

function statusPill(status) {
    const key = normalizeKey(status) || "unknown";

    const labels = {
        enabled: "Enabled",
        disabled: "Disabled",
        compliant: "Compliant",
        noncompliant: "Non-compliant",
        published: "Published",
        processing: "Processing",
        unpublished: "Unpublished",
        awaitingconfirmation: "Awaiting confirmation",
        executing: "Executing",
        completed: "Completed",
        failed: "Failed",
        cancelled: "Cancelled",
        expired: "Expired",
        unknown: "Unknown"
    };

    const classes = {
        enabled: "status-pill-success",
        disabled: "status-pill-danger",
        compliant: "status-pill-success",
        noncompliant: "status-pill-danger",
        published: "status-pill-success",
        processing: "status-pill-warning",
        unpublished: "status-pill-neutral",
        awaitingconfirmation: "status-pill-warning",
        executing: "status-pill-info",
        completed: "status-pill-success",
        failed: "status-pill-danger",
        cancelled: "status-pill-neutral",
        expired: "status-pill-neutral",
        unknown: "status-pill-neutral"
    };

    return `
        <span class="status-pill ${classes[key] || "status-pill-neutral"}">
            ${labels[key] || escapeHtml(status)}
        </span>
    `;
}

function riskPill(risk) {
    const normalized = normalizeText(risk) || "unknown";

    return `
        <span class="risk-pill risk-${escapeHtml(normalized)}">
            ${escapeHtml(normalized)}
        </span>
    `;
}




// ===========================================
// Control Panel Authentication
// ===========================================

function isControlAuthenticationError(result) {
    return Boolean(
        result &&
        (
            result.errorType ===
                "control_authentication_error" ||
            result.status === 401 ||
            normalizeText(result.message).includes(
                "control panel authentication failed"
            )
        )
    );
}

async function requestControlPanelAuthentication() {
    if (controlState.authPromptActive) {
        return false;
    }

    controlState.authPromptActive = true;

    try {
        const existingKey = window.sessionStorage.getItem(
            "controlPanelApiKey"
        ) || "";

        const apiKey = window.prompt(
            "The Flask Control Panel requires CONTROL_PANEL_API_KEY. " +
            "Enter the exact value from backend/.env. " +
            "Cancel to remain in read-only mode.",
            existingKey
        );

        if (apiKey === null) {
            showToast(
                "Authentication was not configured. Protected actions remain unavailable.",
                "warning"
            );
            return false;
        }

        const cleanedKey = String(apiKey).trim();

        if (!cleanedKey) {
            setControlPanelSession({
                apiKey: "",
                administrator: ""
            });

            showToast(
                "No API key was entered. Either enter the configured key or leave CONTROL_PANEL_API_KEY empty and restart Flask for localhost-only mode.",
                "error"
            );
            return false;
        }

        const existingAdministrator =
            window.sessionStorage.getItem(
                "controlPanelAdminUser"
            ) || "local-admin";

        const administrator = window.prompt(
            "Administrator identity for the action log:",
            existingAdministrator
        );

        setControlPanelSession({
            apiKey: cleanedKey,
            administrator:
                String(administrator || "local-admin").trim() ||
                "local-admin"
        });

        showToast(
            "Control Panel credentials saved for this browser session.",
            "success"
        );

        return true;
    } finally {
        controlState.authPromptActive = false;
    }
}

async function runAuthenticatedControlOperation(operation) {
    let result = await operation();

    if (!isControlAuthenticationError(result)) {
        return result;
    }

    const configured = await requestControlPanelAuthentication();

    if (!configured) {
        return result;
    }

    result = await operation();

    if (isControlAuthenticationError(result)) {
        showToast(
            "The API key was rejected. Check CONTROL_PANEL_API_KEY in backend/.env, then restart Flask.",
            "error"
        );
    }

    return result;
}

// ===========================================
// Refresh and Capabilities
// ===========================================

async function refreshControlPanel() {
    if (controlState.loading) {
        return;
    }

    controlState.loading = true;
    setLoading(true);
    setConnection("loading", "Loading Control Panel");

    try {
        const [applications, users, devices] = await Promise.all([
            getApplications(),
            getUsers(),
            getDevices()
        ]);

        let [capabilitiesResult, jobsResult] = await Promise.all([
            getControlCapabilities(),
            getControlJobs(100)
        ]);

        if (
            isControlAuthenticationError(capabilitiesResult) ||
            isControlAuthenticationError(jobsResult)
        ) {
            const configured = await requestControlPanelAuthentication();

            if (configured) {
                [capabilitiesResult, jobsResult] = await Promise.all([
                    getControlCapabilities(),
                    getControlJobs(100)
                ]);
            }
        }

        controlState.applications = Array.isArray(applications)
            ? applications
            : [];

        controlState.users = Array.isArray(users)
            ? users
            : [];

        controlState.devices = Array.isArray(devices)
            ? devices
            : [];

        controlState.jobs = jobsResult.success
            ? jobsResult.jobs
            : [];

        updateCapabilities(capabilitiesResult);
        renderAll();

        addAudit({
            event: "inventory_refreshed",
            action: "read_inventory",
            target: "enterprise",
            details:
                `${controlState.users.length} users, ` +
                `${controlState.applications.length} applications, ` +
                `${controlState.devices.length} devices`
        });

        const protectedConnected =
            capabilitiesResult.success &&
            jobsResult.success;

        setConnection(
            protectedConnected ? "connected" : "error",
            protectedConnected
                ? "Protected actions connected"
                : "Read-only mode"
        );

        showToast(
            protectedConnected
                ? "Control Panel refreshed."
                : "Inventory loaded. Protected actions require authentication.",
            protectedConnected ? "success" : "warning"
        );
    } catch (error) {
        console.error("Control Panel refresh failed:", error);
        setConnection("error", "Control Panel unavailable");
        showToast(
            error.message ||
            "Unable to refresh the Control Panel.",
            "error"
        );
    } finally {
        controlState.loading = false;
        setLoading(false);
    }
}

function setLoading(isLoading) {
    const button = byId("refreshControlPanelButton");

    if (!button) {
        return;
    }

    button.disabled = isLoading;
    button.innerHTML = isLoading
        ? '<i class="fa-solid fa-spinner fa-spin"></i> Loading'
        : '<i class="fa-solid fa-rotate"></i> Refresh';
}

function setConnection(state, text) {
    const badge = byId("controlConnectionStatus");
    const label = byId("controlConnectionText");

    if (label) {
        label.textContent = text;
    }

    if (!badge) {
        return;
    }

    badge.classList.remove(
        "control-connection-loading",
        "control-connection-connected",
        "control-connection-error"
    );

    badge.classList.add(`control-connection-${state}`);
}

function updateCapabilities(result) {
    controlState.capabilities.clear();

    if (result?.success && Array.isArray(result.actions)) {
        result.actions.forEach((action) => {
            if (action?.type) {
                controlState.capabilities.set(
                    action.type,
                    action
                );
            }
        });
    }

    const banner = document.querySelector(".control-safety-banner");

    if (!banner) {
        return;
    }

    const title = banner.querySelector("strong");
    const description = banner.querySelector("p");

    if (result?.success && result.mode === "protected_write") {
        if (title) {
            title.textContent = "Protected backend mode";
        }

        if (description) {
            description.textContent =
                "Supported actions are planned against live Microsoft Graph, " +
                "require confirmation, execute through fixed backend tools, " +
                "and are stored as backend action jobs.";
        }
    } else {
        if (title) {
            title.textContent = "Read-only fallback mode";
        }

        if (description) {
            description.textContent =
                "Inventory can still be reviewed, but protected action " +
                "endpoints are unavailable.";
        }
    }
}

function actionIsSupported(actionType) {
    return controlState.capabilities.has(actionType);
}


// ===========================================
// Rendering
// ===========================================

function renderAll() {
    renderStatistics();
    renderOverview();
    renderUsers();
    renderApplications();
    renderDevices();
    renderCompliance();
    renderJobs();
    renderAudit();
}

function renderStatistics() {
    const enabledUsers = controlState.users.filter(
        (user) => getUserStatus(user) === "enabled"
    ).length;

    const disabledUsers = controlState.users.filter(
        (user) => getUserStatus(user) === "disabled"
    ).length;

    const publishedApplications = controlState.applications.filter(
        (application) =>
            getApplicationState(application) === "published"
    ).length;

    const compliantDevices = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "compliant"
    ).length;

    const nonCompliantDevices = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "noncompliant"
    ).length;

    const pendingJobs = controlState.jobs.filter(
        (job) =>
            ["awaiting_confirmation", "executing"].includes(
                job.status
            )
    ).length;

    setText("controlUserCount", controlState.users.length);
    setText(
        "controlUserBreakdown",
        `${enabledUsers} enabled · ${disabledUsers} disabled`
    );

    setText(
        "controlApplicationCount",
        controlState.applications.length
    );

    setText(
        "controlApplicationBreakdown",
        `${publishedApplications} published`
    );

    setText("controlDeviceCount", controlState.devices.length);
    setText(
        "controlDeviceBreakdown",
        `${compliantDevices} compliant · ` +
        `${nonCompliantDevices} non-compliant`
    );

    setText("controlPlannedActionCount", pendingJobs);
}

function renderOverview() {
    const enabled = controlState.users.filter(
        (user) => getUserStatus(user) === "enabled"
    ).length;

    const disabled = controlState.users.filter(
        (user) => getUserStatus(user) === "disabled"
    ).length;

    const published = controlState.applications.filter(
        (application) =>
            getApplicationState(application) === "published"
    ).length;

    const processing = controlState.applications.filter(
        (application) =>
            getApplicationState(application) === "processing"
    ).length;

    const compliant = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "compliant"
    ).length;

    const nonCompliant = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "noncompliant"
    ).length;

    renderHealthList("overviewUserHealth", [
        ["Enabled", enabled],
        ["Disabled", disabled],
        ["Unknown status", controlState.users.length - enabled - disabled]
    ]);

    renderHealthList("overviewApplicationHealth", [
        ["Published", published],
        ["Processing", processing],
        [
            "Other states",
            controlState.applications.length - published - processing
        ]
    ]);

    renderHealthList("overviewDeviceHealth", [
        ["Compliant", compliant],
        ["Non-compliant", nonCompliant],
        [
            "Unknown",
            controlState.devices.length - compliant - nonCompliant
        ]
    ]);

    const badge = byId("overviewComplianceBadge");

    if (badge) {
        badge.className = nonCompliant > 0
            ? "status-pill status-pill-danger"
            : "status-pill status-pill-success";

        badge.textContent = nonCompliant > 0
            ? `${nonCompliant} issue${nonCompliant === 1 ? "" : "s"}`
            : "Healthy";
    }
}

function renderHealthList(id, entries) {
    const element = byId(id);

    if (!element) {
        return;
    }

    element.innerHTML = entries
        .map(
            ([label, value]) => `
                <div>
                    <span>${escapeHtml(label)}</span>
                    <strong>${escapeHtml(value)}</strong>
                </div>
            `
        )
        .join("");
}


// ===========================================
// Tabs and Filters
// ===========================================

function setupTabs() {
    document.querySelectorAll("[data-control-tab]")
        .forEach((button) => {
            button.addEventListener("click", () => {
                openTab(button.dataset.controlTab);
            });
        });

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest?.(
            "[data-open-control-tab]"
        );

        if (trigger) {
            openTab(trigger.dataset.openControlTab);
        }
    });
}

function openTab(name) {
    document.querySelectorAll("[data-control-tab]")
        .forEach((button) => {
            button.classList.toggle(
                "control-tab-active",
                button.dataset.controlTab === name
            );
        });

    document.querySelectorAll("[data-control-section]")
        .forEach((section) => {
            section.classList.toggle(
                "hidden",
                section.dataset.controlSection !== name
            );
        });
}

function setupFilters() {
    [
        "controlUserSearch",
        "controlUserStatusFilter",
        "controlApplicationSearch",
        "controlApplicationStateFilter",
        "controlDeviceSearch",
        "controlDeviceComplianceFilter"
    ].forEach((id) => {
        const element = byId(id);

        if (!element) {
            return;
        }

        element.addEventListener("input", renderFilteredTables);
        element.addEventListener("change", renderFilteredTables);
    });
}

function renderFilteredTables() {
    renderUsers();
    renderApplications();
    renderDevices();
}


// ===========================================
// Users
// ===========================================

function renderUsers() {
    const tableBody = byId("controlUsersTableBody");
    const emptyState = byId("controlUsersEmpty");

    if (!tableBody) {
        return;
    }

    const search = normalizeText(
        byId("controlUserSearch")?.value
    );

    const statusFilter =
        byId("controlUserStatusFilter")?.value ||
        "all";

    const users = controlState.users.filter((user) => {
        const status = getUserStatus(user);

        if (
            statusFilter !== "all" &&
            status !== statusFilter
        ) {
            return false;
        }

        if (!search) {
            return true;
        }

        return normalizeText([
            user.display_name,
            user.displayName,
            user.mail,
            user.user_principal_name,
            user.userPrincipalName,
            user.mobile_phone,
            user.mobilePhone
        ].join(" ")).includes(search);
    });

    tableBody.innerHTML = users
        .map((user) => {
            const status = getUserStatus(user);
            const name = getTargetName("user", user);

            const email =
                user.mail ||
                user.user_principal_name ||
                user.userPrincipalName ||
                "—";

            const phone =
                user.mobile_phone ||
                user.mobilePhone ||
                "—";

            let actionsHtml = "";

            if (status === "enabled") {
                actionsHtml = actionButtonHtml(
                    "disable_user",
                    "user",
                    user.id,
                    "Disable",
                    "control-action-warning"
                );
            } else if (status === "disabled") {
                actionsHtml = actionButtonHtml(
                    "enable_user",
                    "user",
                    user.id,
                    "Enable",
                    "control-action-success"
                );
            } else {
                actionsHtml = `
                    ${actionButtonHtml(
                        "enable_user",
                        "user",
                        user.id,
                        "Enable",
                        "control-action-success"
                    )}
                    ${actionButtonHtml(
                        "disable_user",
                        "user",
                        user.id,
                        "Disable",
                        "control-action-warning"
                    )}
                `;
            }

            return `
                <tr>
                    <td><strong>${escapeHtml(name)}</strong></td>
                    <td>${escapeHtml(email)}</td>
                    <td>${escapeHtml(phone)}</td>
                    <td>${statusPill(status)}</td>
                    <td>
                        <div class="control-row-actions">
                            ${actionsHtml}
                        </div>
                    </td>
                </tr>
            `;
        })
        .join("");

    emptyState?.classList.toggle(
        "hidden",
        users.length > 0
    );
}


// ===========================================
// Applications
// ===========================================

function renderApplications() {
    const tableBody = byId("controlApplicationsTableBody");
    const emptyState = byId("controlApplicationsEmpty");

    if (!tableBody) {
        return;
    }

    const search = normalizeText(
        byId("controlApplicationSearch")?.value
    );

    const stateFilter =
        byId("controlApplicationStateFilter")?.value ||
        "all";

    const applications = controlState.applications.filter(
        (application) => {
            const currentState = getApplicationState(application);

            if (
                stateFilter !== "all" &&
                currentState !== stateFilter
            ) {
                return false;
            }

            if (!search) {
                return true;
            }

            return normalizeText([
                application.display_name,
                application.displayName,
                application.publisher,
                application.app_type,
                application.appType,
                application.display_version,
                application.displayVersion
            ].join(" ")).includes(search);
        }
    );

    tableBody.innerHTML = applications
        .map((application) => {
            const name = getTargetName(
                "application",
                application
            );

            const publisher = application.publisher || "—";

            const applicationType =
                application.app_type ||
                application.appType ||
                "—";

            const version =
                application.display_version ||
                application.displayVersion ||
                "—";

            return `
                <tr>
                    <td><strong>${escapeHtml(name)}</strong></td>
                    <td>${escapeHtml(publisher)}</td>
                    <td>${escapeHtml(applicationType)}</td>
                    <td>
                        ${statusPill(
                            getApplicationState(application)
                        )}
                    </td>
                    <td>${escapeHtml(version)}</td>
                    <td>
                        <div class="control-row-actions">
                            <button
                                class="control-row-action control-action-success"
                                type="button"
                                data-assign-app-group="${escapeHtml(application.id || "")}"
                                ${
                                    actionIsSupported(
                                        "assign_application_group"
                                    )
                                        ? ""
                                        : "disabled"
                                }
                                title="${
                                    actionIsSupported(
                                        "assign_application_group"
                                    )
                                        ? "Assign this Win32 application to an Entra group"
                                        : "Application assignment backend is unavailable"
                                }"
                            >
                                Assign
                            </button>

                            <button
                                class="control-row-action"
                                type="button"
                                data-review-app-assignments="${escapeHtml(application.id || "")}"
                            >
                                Assignments
                            </button>

                            ${actionButtonHtml(
                                "delete_application",
                                "application",
                                application.id,
                                "Delete",
                                "control-action-danger"
                            )}
                        </div>
                    </td>
                </tr>
            `;
        })
        .join("");

    emptyState?.classList.toggle(
        "hidden",
        applications.length > 0
    );
}

// ===========================================
// Devices
// ===========================================

function renderDevices() {
    const tableBody = byId("controlDevicesTableBody");
    const emptyState = byId("controlDevicesEmpty");

    if (!tableBody) {
        return;
    }

    const search = normalizeText(
        byId("controlDeviceSearch")?.value
    );

    const complianceFilter =
        byId("controlDeviceComplianceFilter")?.value ||
        "all";

    const devices = controlState.devices.filter((device) => {
        const compliance = getDeviceCompliance(device);

        if (
            complianceFilter !== "all" &&
            compliance !== complianceFilter
        ) {
            return false;
        }

        if (!search) {
            return true;
        }

        return normalizeText([
            device.device_name,
            device.deviceName,
            device.user_name,
            device.userName,
            device.operating_system,
            device.operatingSystem,
            device.manufacturer,
            device.model
        ].join(" ")).includes(search);
    });

    tableBody.innerHTML = devices
        .map((device) => {
            const name = getTargetName("device", device);

            const user =
                device.user_name ||
                device.userName ||
                "—";

            const operatingSystem =
                device.operating_system ||
                device.operatingSystem ||
                "—";

            const osVersion =
                device.os_version ||
                device.osVersion ||
                "";

            const hardware =
                [
                    device.manufacturer,
                    device.model
                ].filter(Boolean).join(" ") ||
                "—";

            return `
                <tr>
                    <td><strong>${escapeHtml(name)}</strong></td>
                    <td>${escapeHtml(user)}</td>
                    <td>
                        ${escapeHtml(operatingSystem)}
                        ${
                            osVersion
                                ? `
                                    <small class="control-table-subtext">
                                        ${escapeHtml(osVersion)}
                                    </small>
                                `
                                : ""
                        }
                    </td>
                    <td>${escapeHtml(hardware)}</td>
                    <td>
                        ${statusPill(
                            getDeviceCompliance(device)
                        )}
                    </td>
                    <td>
                        <div class="control-row-actions">
                            ${actionButtonHtml(
                                "sync_device",
                                "device",
                                device.id,
                                "Sync",
                                "control-action-success"
                            )}
                            ${actionButtonHtml(
                                "restart_device",
                                "device",
                                device.id,
                                "Restart",
                                "control-action-warning"
                            )}
                        </div>
                    </td>
                </tr>
            `;
        })
        .join("");

    emptyState?.classList.toggle(
        "hidden",
        devices.length > 0
    );
}

function actionButtonHtml(
    actionType,
    targetKind,
    targetId,
    label,
    className = ""
) {
    const supported = actionIsSupported(actionType);

    return `
        <button
            class="control-row-action ${className}"
            type="button"
            data-protected-action="${escapeHtml(actionType)}"
            data-target-kind="${escapeHtml(targetKind)}"
            data-target-id="${escapeHtml(targetId || "")}"
            ${supported ? "" : "disabled"}
            title="${
                supported
                    ? escapeHtml(label)
                    : "Backend action is unavailable"
            }"
        >
            ${escapeHtml(label)}
        </button>
    `;
}

function comingSoonButtonHtml(
    label,
    message,
    className = ""
) {
    return `
        <button
            class="control-row-action ${className}"
            type="button"
            data-coming-soon="${escapeHtml(message)}"
        >
            ${escapeHtml(label)}
        </button>
    `;
}


// ===========================================
// Compliance
// ===========================================

function renderCompliance() {
    const summary = byId("controlComplianceSummary");
    const issues = byId("controlComplianceIssues");

    if (!summary || !issues) {
        return;
    }

    const compliant = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "compliant"
    );

    const nonCompliant = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "noncompliant"
    );

    const unknown = controlState.devices.filter(
        (device) => getDeviceCompliance(device) === "unknown"
    );

    summary.innerHTML = `
        <article>
            <strong>${compliant.length}</strong>
            <span>Compliant</span>
        </article>
        <article>
            <strong>${nonCompliant.length}</strong>
            <span>Non-compliant</span>
        </article>
        <article>
            <strong>${unknown.length}</strong>
            <span>Unknown</span>
        </article>
    `;

    const cards = [];

    if (nonCompliant.length > 0) {
        cards.push(
            complianceCardHtml(
                "Non-compliant devices",
                nonCompliant.length,
                "Review each affected device and request a sync. " +
                "Exact policy-setting remediation will be added later.",
                "high",
                "noncompliant"
            )
        );
    }

    if (unknown.length > 0) {
        cards.push(
            complianceCardHtml(
                "Unknown compliance state",
                unknown.length,
                "A managed-device sync may refresh stale state. " +
                "Unresolved devices still require manual investigation.",
                "medium",
                "unknown"
            )
        );
    }

    issues.innerHTML = cards.length > 0
        ? cards.join("")
        : `
            <article class="control-issue-card control-issue-card-success">
                <div class="control-issue-icon">
                    <i class="fa-solid fa-circle-check"></i>
                </div>
                <div>
                    <h3>No inventory compliance issues detected</h3>
                    <p>
                        All returned devices currently report
                        a compliant state.
                    </p>
                </div>
            </article>
        `;
}

function complianceCardHtml(
    title,
    count,
    description,
    risk,
    filter
) {
    return `
        <article class="control-issue-card">
            <div class="control-issue-card-heading">
                <div>
                    ${riskPill(risk)}
                    <h3>${escapeHtml(title)}</h3>
                </div>
                <strong>${escapeHtml(count)}</strong>
            </div>
            <p>${escapeHtml(description)}</p>
            <button
                class="secondary-button"
                type="button"
                data-review-device-compliance="${escapeHtml(filter)}"
            >
                Review affected devices
            </button>
        </article>
    `;
}


// ===========================================
// Buttons and Protected Planning
// ===========================================

function setupButtons() {
    byId("refreshControlPanelButton")
        ?.addEventListener(
            "click",
            refreshControlPanel
        );

    byId("controlAddApplicationButton")
        ?.addEventListener(
            "click",
            () => showToast(
                "Application package upload is not implemented yet.",
                "info"
            )
        );

    byId("analyseComplianceButton")
        ?.addEventListener(
            "click",
            function () {
                openTab("compliance");

                const count = controlState.devices.filter(
                    (device) =>
                        getDeviceCompliance(device) ===
                        "noncompliant"
                ).length;

                showCommandFeedback(
                    `${count} non-compliant device${
                        count === 1 ? "" : "s"
                    } found.`,
                    count > 0 ? "warning" : "success"
                );
            }
        );

    const jobsButton = byId("clearControlJobsButton");

    if (jobsButton) {
        jobsButton.innerHTML =
            '<i class="fa-solid fa-rotate"></i> Refresh jobs';

        jobsButton.addEventListener(
            "click",
            refreshJobs
        );
    }

    byId("clearControlAuditButton")
        ?.addEventListener(
            "click",
            function () {
                controlState.audit = [];

                saveStoredArray(
                    CONTROL_AUDIT_STORAGE_KEY,
                    controlState.audit
                );

                renderAudit();
                showToast(
                    "Local browser audit log cleared.",
                    "success"
                );
            }
        );

    document.addEventListener(
        "click",
        async function (event) {
            const protectedButton = event.target.closest?.(
                "[data-protected-action]"
            );

            if (protectedButton) {
                await handleProtectedActionButton(
                    protectedButton
                );
                return;
            }

            const assignApplicationButton = event.target.closest?.(
                "[data-assign-app-group]"
            );

            if (assignApplicationButton) {
                await assignApplicationToGroup(
                    assignApplicationButton.dataset.assignAppGroup
                );
                return;
            }

            const assignmentsButton = event.target.closest?.(
                "[data-review-app-assignments]"
            );

            if (assignmentsButton) {
                await reviewApplicationAssignments(
                    assignmentsButton.dataset.reviewAppAssignments
                );
                return;
            }

            const comingSoonButton = event.target.closest?.(
                "[data-coming-soon]"
            );

            if (comingSoonButton) {
                showToast(
                    comingSoonButton.dataset.comingSoon,
                    "info"
                );
                return;
            }

            const complianceButton = event.target.closest?.(
                "[data-review-device-compliance]"
            );

            if (complianceButton) {
                const select = byId(
                    "controlDeviceComplianceFilter"
                );

                if (select) {
                    select.value =
                        complianceButton.dataset
                            .reviewDeviceCompliance;
                }

                renderDevices();
                openTab("devices");
            }
        }
    );
}

function isGuid(value) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
        .test(
            String(value || "").trim()
        );
}

async function assignApplicationToGroup(applicationId) {
    const application = findTargetById(
        "application",
        applicationId
    );

    if (!application) {
        showToast(
            "The selected application could not be found.",
            "error"
        );
        return;
    }

    if (!actionIsSupported("assign_application_group")) {
        showToast(
            "The application assignment action is not available on the backend.",
            "error"
        );
        return;
    }

    const applicationName = getTargetName(
        "application",
        application
    );

    const groupIdInput = window.prompt(
        `Assign ${applicationName} to a Microsoft Entra group.\n\n` +
        "Enter the exact Entra group object ID (GUID):"
    );

    if (groupIdInput === null) {
        return;
    }

    const groupId = String(
        groupIdInput
    ).trim();

    if (!isGuid(groupId)) {
        showToast(
            "Enter a valid Microsoft Entra group GUID.",
            "error"
        );
        return;
    }

    const intentInput = window.prompt(
        "Assignment intent:\n\n" +
        "available\nrequired\nuninstall",
        "required"
    );

    if (intentInput === null) {
        return;
    }

    const intent = String(
        intentInput
    ).trim();

    if (
        ![
            "available",
            "required",
            "uninstall"
        ].includes(intent)
    ) {
        showToast(
            "Intent must be available, required, or uninstall.",
            "error"
        );
        return;
    }

    const notificationsInput = window.prompt(
        "User notification setting:\n\n" +
        "showAll\nshowReboot\nhideAll",
        "showAll"
    );

    if (notificationsInput === null) {
        return;
    }

    const notifications = String(
        notificationsInput
    ).trim();

    if (
        ![
            "showAll",
            "showReboot",
            "hideAll"
        ].includes(notifications)
    ) {
        showToast(
            "Notifications must be showAll, showReboot, or hideAll.",
            "error"
        );
        return;
    }

    try {
        await planAndOpenAction(
            "assign_application_group",
            "application",
            application,
            {
                groupId,
                intent,
                notifications
            }
        );
    } catch (error) {
        console.error(
            "Application assignment planning failed:",
            error
        );

        showToast(
            error.message ||
            "Unable to prepare the application assignment.",
            "error"
        );
    }
}


async function reviewApplicationAssignments(applicationId) {
    const application = findTargetById(
        "application",
        applicationId
    );

    if (!application) {
        showToast(
            "The selected application could not be found.",
            "error"
        );
        return;
    }

    const result = await runAuthenticatedControlOperation(
        () => getApplicationAssignments(applicationId)
    );

    if (!result.success) {
        showToast(
            result.message ||
            "Unable to load application assignments.",
            "error"
        );
        return;
    }

    if (result.assignments.length === 0) {
        showToast(
            `${getTargetName("application", application)} has no assignments.`,
            "info"
        );
        return;
    }

    const lines = result.assignments.map(
        (assignment, index) => {
            const targetType =
                assignment.target_type ||
                "unknown target";

            const targetId =
                assignment.target_id ||
                "no target ID";

            const intent =
                assignment.intent ||
                "unknown intent";

            return `${index + 1}. ${intent} → ${targetType} (${targetId})`;
        }
    );

    const choice = window.prompt(
        `Assignments for ${getTargetName("application", application)}:\n\n` +
        `${lines.join("\n")}\n\n` +
        "Enter the assignment number to prepare its removal. " +
        "Cancel to close."
    );

    if (choice === null) {
        return;
    }

    const selectedIndex = Number.parseInt(
        String(choice).trim(),
        10
    ) - 1;

    if (
        !Number.isInteger(selectedIndex) ||
        selectedIndex < 0 ||
        selectedIndex >= result.assignments.length
    ) {
        showToast(
            "Choose a valid assignment number.",
            "error"
        );
        return;
    }

    const selectedAssignment =
        result.assignments[selectedIndex];

    try {
        await planAndOpenAction(
            "delete_application_assignment",
            "application",
            application,
            {
                assignmentId:
                    selectedAssignment.assignment_id
            }
        );
    } catch (error) {
        showToast(
            error.message ||
            "Unable to prepare assignment removal.",
            "error"
        );
    }
}

async function handleProtectedActionButton(button) {
    const actionType = button.dataset.protectedAction;
    const targetKind = button.dataset.targetKind;
    const targetId = button.dataset.targetId;

    const target = findTargetById(
        targetKind,
        targetId
    );

    if (!target) {
        showToast(
            "The selected inventory record could not be found.",
            "error"
        );
        return;
    }

    const originalHtml = button.innerHTML;

    button.disabled = true;
    button.innerHTML =
        '<i class="fa-solid fa-spinner fa-spin"></i>';

    try {
        await planAndOpenAction(
            actionType,
            targetKind,
            target
        );
    } finally {
        button.disabled = false;
        button.innerHTML = originalHtml;
    }
}

async function planAndOpenAction(
    actionType,
    targetKind,
    target,
    {
        assignmentId = null,
        groupId = null,
        intent = null,
        notifications = null
    } = {}
) {
    if (!actionIsSupported(actionType)) {
        showToast(
            "This protected action is not available on the backend.",
            "error"
        );
        return;
    }

    const result = await runAuthenticatedControlOperation(
        () => planControlAction(
            actionType,
            target.id,
            {
                assignmentId,
                groupId,
                intent,
                notifications
            }
        )
    );

    if (!result.success) {
        throw new Error(
            result.message ||
            "The backend could not create the action plan."
        );
    }

    if (result.noActionRequired) {
        applyNoActionState(result.plan);

        showToast(
            result.message ||
            "No action is required.",
            "success"
        );

        renderAll();
        return;
    }

    if (
        !result.requiresConfirmation ||
        !result.confirmationId ||
        !result.action
    ) {
        throw new Error(
            "The backend returned an incomplete confirmation plan."
        );
    }

    openActionDialog({
        confirmationId: result.confirmationId,
        action: result.action,
        plan: result.plan || {},
        targetKind,
        target
    });

    addAudit({
        event: "action_planned",
        action: actionType,
        target: getTargetName(targetKind, target),
        details:
            `Action ID: ${result.action.action_id || "unknown"}`
    });

    await refreshJobs();
}

function applyNoActionState(plan) {
    if (!plan || plan.action_type === undefined) {
        return;
    }

    if (
        ["enable_user", "disable_user"].includes(
            plan.action_type
        )
    ) {
        const user = findTargetById(
            "user",
            plan.target_id
        );

        if (user) {
            user.account_enabled =
                plan.action_type === "enable_user";
        }
    }
}

function findTargetById(kind, id) {
    const collection = {
        user: controlState.users,
        application: controlState.applications,
        device: controlState.devices
    }[kind] || [];

    return collection.find(
        (record) =>
            String(record.id || "") ===
            String(id || "")
    );
}


// ===========================================
// Confirmation Dialog
// ===========================================

function setupActionDialog() {
    byId("closeControlActionDialogButton")
        ?.addEventListener(
            "click",
            cancelPendingAction
        );

    byId("cancelControlActionButton")
        ?.addEventListener(
            "click",
            cancelPendingAction
        );

    byId("confirmControlActionButton")
        ?.addEventListener(
            "click",
            executePendingAction
        );

    byId("controlTypedConfirmationInput")
        ?.addEventListener(
            "input",
            updateConfirmButton
        );

    const dialog = byId("controlActionDialog");

    dialog?.addEventListener(
        "click",
        function (event) {
            if (event.target === dialog) {
                cancelPendingAction();
            }
        }
    );

    dialog?.addEventListener(
        "cancel",
        function (event) {
            event.preventDefault();
            cancelPendingAction();
        }
    );
}

function openActionDialog(pendingAction) {
    controlState.pendingAction = pendingAction;

    const { action, plan } = pendingAction;

    setText(
        "controlActionDialogTitle",
        action.label || "Review Action"
    );

    const risk = action.risk || "medium";
    const riskBanner = byId("controlActionRiskBanner");

    if (riskBanner) {
        riskBanner.className =
            `control-risk-banner control-risk-${risk}`;

        riskBanner.innerHTML = `
            ${riskPill(risk)}
            <p>
                This plan was resolved against live Microsoft Graph.
                Confirming it will execute the fixed backend action.
            </p>
        `;
    }

    const details = byId("controlActionDetails");

    if (details) {
        const values = [
            ["Action ID", action.action_id],
            ["Action", action.label],
            ["Target", action.target_name],
            ["Target ID", action.target_id],
            [
                "Current state",
                plan.before ||
                action.metadata?.before ||
                "Current state"
            ],
            [
                "Requested state",
                plan.after ||
                action.metadata?.after ||
                "Requested state"
            ],
            ["Expires", formatDate(action.expires_at)]
        ];

        details.innerHTML = values
            .map(
                ([label, value]) => `
                    <div>
                        <dt>${escapeHtml(label)}</dt>
                        <dd>${escapeHtml(value || "—")}</dd>
                    </div>
                `
            )
            .join("");
    }

    const typedLabel = byId(
        "controlTypedConfirmationLabel"
    );

    const typedInput = byId(
        "controlTypedConfirmationInput"
    );

    if (
        action.requires_typed_confirmation &&
        action.confirmation_phrase
    ) {
        typedLabel?.classList.remove("hidden");

        setText(
            "controlConfirmationPhrase",
            action.confirmation_phrase
        );
    } else {
        typedLabel?.classList.add("hidden");
    }

    if (typedInput) {
        typedInput.value = "";
    }

    const note = document.querySelector(
        ".control-dialog-note"
    );

    if (note) {
        note.textContent =
            "The backend will execute only the allowlisted Graph action " +
            "shown above and store the verified result as an action job.";
    }

    updateConfirmButton();

    const dialog = byId("controlActionDialog");

    if (typeof dialog?.showModal === "function") {
        dialog.showModal();
    } else {
        dialog?.setAttribute("open", "");
    }
}

function closeActionDialog() {
    const dialog = byId("controlActionDialog");

    if (dialog?.open) {
        dialog.close();
    }

    controlState.pendingAction = null;
}

function updateConfirmButton() {
    const button = byId("confirmControlActionButton");
    const input = byId("controlTypedConfirmationInput");
    const pending = controlState.pendingAction;

    if (!button || !pending) {
        return;
    }

    const { action } = pending;

    const valid =
        !action.requires_typed_confirmation ||
        (
            String(input?.value || "")
                .trim()
                .toUpperCase()
            ===
            String(action.confirmation_phrase || "")
                .trim()
                .toUpperCase()
        );

    button.disabled = !valid;
    button.innerHTML =
        '<i class="fa-solid fa-check"></i> Confirm and Execute';
}

async function executePendingAction() {
    const pending = controlState.pendingAction;

    if (!pending) {
        return;
    }

    const button = byId("confirmControlActionButton");
    const input = byId("controlTypedConfirmationInput");

    if (button) {
        button.disabled = true;
        button.innerHTML =
            '<i class="fa-solid fa-spinner fa-spin"></i> Executing';
    }

    const result = await runAuthenticatedControlOperation(
        () => confirmControlAction(
            pending.confirmationId,
            String(input?.value || "").trim()
        )
    );

    if (!result.success) {
        addAudit({
            event: "action_failed",
            action: pending.action.action_type,
            target: pending.action.target_name,
            details:
                result.message ||
                "Unknown action error"
        });

        closeActionDialog();
        await refreshJobs();

        showToast(
            result.message ||
            "The protected action failed.",
            "error"
        );
        return;
    }

    applyCompletedResult(result);

    addAudit({
        event: "action_completed",
        action:
            result.action?.action_type ||
            pending.action.action_type,
        target:
            result.action?.target_name ||
            pending.action.target_name,
        details:
            `Action ID: ${
                result.action?.action_id ||
                pending.action.action_id
            }`
    });

    closeActionDialog();
    await refreshJobs();
    renderAll();

    showToast(
        result.message ||
        "Action completed successfully.",
        "success"
    );
}

function applyCompletedResult(response) {
    const actionType =
        response.action?.action_type;

    const result = response.result || {};

    if (
        ["enable_user", "disable_user"].includes(
            actionType
        )
    ) {
        const user = findTargetById(
            "user",
            result.user_id ||
            response.action?.target_id
        );

        if (user) {
            user.account_enabled =
                Boolean(result.verified_enabled);
        }

        return;
    }

    if (actionType === "delete_application") {
        const deletedId =
            result.application_id ||
            response.action?.target_id;

        controlState.applications =
            controlState.applications.filter(
                (application) =>
                    String(application.id || "") !==
                    String(deletedId || "")
            );
    }
}

async function cancelPendingAction() {
    const pending = controlState.pendingAction;

    if (!pending) {
        closeActionDialog();
        return;
    }

    const result = await runAuthenticatedControlOperation(
        () => cancelControlAction(
            pending.confirmationId
        )
    );

    if (result.success) {
        addAudit({
            event: "action_cancelled",
            action: pending.action.action_type,
            target: pending.action.target_name,
            details:
                `Action ID: ${pending.action.action_id}`
        });
    }

    closeActionDialog();
    await refreshJobs();
}

// ===========================================
// Jobs and Audit
// ===========================================

async function refreshJobs() {
    const result = await runAuthenticatedControlOperation(
        () => getControlJobs(100)
    );

    if (!result.success) {
        showToast(
            result.message ||
            "Unable to load action jobs.",
            "error"
        );
        return;
    }

    controlState.jobs = result.jobs;
    renderJobs();
    renderStatistics();
}

function renderJobs() {
    const tableBody = byId("controlJobsTableBody");
    const emptyState = byId("controlJobsEmpty");

    if (!tableBody) {
        return;
    }

    tableBody.innerHTML = controlState.jobs
        .map((job) => {
            const details = job.error
                ? `Error: ${job.error}`
                : job.result
                    ? "Verified result stored"
                    : "—";

            return `
                <tr>
                    <td>
                        <code>
                            ${escapeHtml(
                                job.action_id ||
                                job.confirmation_id ||
                                "—"
                            )}
                        </code>
                    </td>
                    <td>
                        ${escapeHtml(
                            job.label ||
                            job.action_type ||
                            "—"
                        )}
                    </td>
                    <td>
                        ${escapeHtml(
                            job.target_name ||
                            job.target_id ||
                            "—"
                        )}
                        <small class="control-table-subtext">
                            ${escapeHtml(details)}
                        </small>
                    </td>
                    <td>${riskPill(job.risk || "unknown")}</td>
                    <td>${statusPill(job.status || "unknown")}</td>
                    <td>${escapeHtml(formatDate(job.created_at))}</td>
                </tr>
            `;
        })
        .join("");

    emptyState?.classList.toggle(
        "hidden",
        controlState.jobs.length > 0
    );
}

function addAudit(event) {
    controlState.audit.unshift({
        timestamp: new Date().toISOString(),
        event: event.event || "unknown",
        action: event.action || "—",
        target: event.target || "—",
        details: event.details || "—"
    });

    controlState.audit = controlState.audit.slice(0, 250);

    saveStoredArray(
        CONTROL_AUDIT_STORAGE_KEY,
        controlState.audit
    );

    renderAudit();
}

function renderAudit() {
    const tableBody = byId("controlAuditTableBody");
    const emptyState = byId("controlAuditEmpty");

    if (!tableBody) {
        return;
    }

    tableBody.innerHTML = controlState.audit
        .map(
            (entry) => `
                <tr>
                    <td>${escapeHtml(formatDate(entry.timestamp))}</td>
                    <td>${escapeHtml(entry.event)}</td>
                    <td>${escapeHtml(entry.action)}</td>
                    <td>${escapeHtml(entry.target)}</td>
                    <td>${escapeHtml(entry.details)}</td>
                </tr>
            `
        )
        .join("");

    emptyState?.classList.toggle(
        "hidden",
        controlState.audit.length > 0
    );
}


// ===========================================
// Natural-Language Planner
// ===========================================

function setupCommandPlanner() {
    byId("controlCommandForm")
        ?.addEventListener(
            "submit",
            async function (event) {
                event.preventDefault();
                await analyseCommand();
            }
        );
}

async function analyseCommand() {
    const command = String(
        byId("controlCommandInput")?.value ||
        ""
    ).trim();

    if (!command) {
        return;
    }

    const normalized = normalizeText(command);

    if (
        /(check|analyse|analyze|review)/.test(normalized) &&
        /non[- ]?compliant|compliance/.test(normalized)
    ) {
        const count = controlState.devices.filter(
            (device) =>
                getDeviceCompliance(device) ===
                "noncompliant"
        ).length;

        showCommandFeedback(
            `${count} non-compliant device${
                count === 1 ? "" : "s"
            } found. Opened Compliance Review.`,
            count > 0
                ? "warning"
                : "success"
        );

        openTab("compliance");
        return;
    }

    const patterns = [
        {
            expression:
                /^(?:please\s+)?enable\s+(?:user\s+)?(.+)$/i,
            actionType: "enable_user",
            targetKind: "user"
        },
        {
            expression:
                /^(?:please\s+)?disable\s+(?:user\s+)?(.+)$/i,
            actionType: "disable_user",
            targetKind: "user"
        },
        {
            expression:
                /^(?:please\s+)?sync\s+(?:device\s+)?(.+)$/i,
            actionType: "sync_device",
            targetKind: "device"
        },
        {
            expression:
                /^(?:please\s+)?(?:restart|reboot)\s+(?:device\s+)?(.+)$/i,
            actionType: "restart_device",
            targetKind: "device"
        }
    ];

    for (const pattern of patterns) {
        const match = command.match(pattern.expression);

        if (!match) {
            continue;
        }

        const lookup = findTargetByText(
            pattern.targetKind,
            match[1]
        );

        if (lookup.status === "not_found") {
            showCommandFeedback(
                `No exact ${pattern.targetKind} matched ` +
                `“${match[1].trim()}”.`,
                "error"
            );
            return;
        }

        if (lookup.status === "ambiguous") {
            showCommandFeedback(
                "Multiple records matched: " +
                lookup.matches
                    .map((record) =>
                        getTargetName(
                            pattern.targetKind,
                            record
                        )
                    )
                    .join(", "),
                "warning"
            );
            return;
        }

        try {
            await planAndOpenAction(
                pattern.actionType,
                pattern.targetKind,
                lookup.target
            );
        } catch (error) {
            showCommandFeedback(
                error.message ||
                "Unable to plan the requested action.",
                "error"
            );
        }

        return;
    }

    if (
        /(delete|assign|unassign|upload|add)\s+(app|application)/i
            .test(command)
    ) {
        showCommandFeedback(
            "Application write actions are visible, but their " +
            "protected backend tools are not installed yet.",
            "info"
        );
        return;
    }

    showCommandFeedback(
        "Supported commands include enabling or disabling a user, " +
        "synchronizing a managed device, and reviewing compliance.",
        "info"
    );
}

function findTargetByText(kind, searchValue) {
    const collection = {
        user: controlState.users,
        application: controlState.applications,
        device: controlState.devices
    }[kind] || [];

    const searchKey = normalizeKey(searchValue);

    if (!searchKey) {
        return {
            status: "not_found",
            matches: []
        };
    }

    const matches = collection.filter((record) =>
        getAliases(kind, record).some((alias) => {
            const aliasKey = normalizeKey(alias);

            return (
                aliasKey &&
                (
                    aliasKey === searchKey ||
                    aliasKey.includes(searchKey) ||
                    searchKey.includes(aliasKey)
                )
            );
        })
    );

    if (matches.length === 0) {
        return {
            status: "not_found",
            matches: []
        };
    }

    const exactMatches = matches.filter((record) =>
        getAliases(kind, record).some(
            (alias) => normalizeKey(alias) === searchKey
        )
    );

    if (exactMatches.length === 1) {
        return {
            status: "found",
            target: exactMatches[0],
            matches: exactMatches
        };
    }

    if (matches.length === 1) {
        return {
            status: "found",
            target: matches[0],
            matches
        };
    }

    return {
        status: "ambiguous",
        matches: matches.slice(0, 8)
    };
}

function getAliases(kind, record) {
    if (kind === "user") {
        const aliases = [
            record.display_name,
            record.displayName,
            record.mail,
            record.user_principal_name,
            record.userPrincipalName,
            record.id
        ];

        [
            record.mail,
            record.user_principal_name,
            record.userPrincipalName
        ].forEach((value) => {
            if (
                typeof value === "string" &&
                value.includes("@")
            ) {
                aliases.push(value.split("@")[0]);
            }
        });

        return aliases.filter(Boolean);
    }

    if (kind === "application") {
        return [
            record.display_name,
            record.displayName,
            record.file_name,
            record.fileName,
            record.id
        ].filter(Boolean);
    }

    return [
        record.device_name,
        record.deviceName,
        record.user_name,
        record.userName,
        record.id
    ].filter(Boolean);
}

function showCommandFeedback(message, type) {
    const element = byId("controlCommandFeedback");

    if (!element) {
        return;
    }

    element.className =
        `control-command-feedback control-feedback-${type}`;

    element.textContent = message;
}


// ===========================================
// Toast
// ===========================================

function showToast(message, type = "info") {
    const element = byId("controlToast");

    if (!element) {
        return;
    }

    window.clearTimeout(controlToastTimer);

    element.className =
        `control-toast control-toast-${type} ` +
        "control-toast-visible";

    element.textContent = message;

    controlToastTimer = window.setTimeout(
        function () {
            element.classList.remove(
                "control-toast-visible"
            );
        },
        3500
    );
}