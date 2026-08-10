// ==========================================
// Enterprise Applications
// ==========================================

let applications = [];

// ------------------------------------------
// Load Applications
// ------------------------------------------

document.addEventListener("DOMContentLoaded", () => {

    loadApplications();

    document
        .getElementById("searchInput")
        .addEventListener("keyup", searchApplications);

});

// ------------------------------------------
// Fetch Applications
// ------------------------------------------

async function loadApplications() {

    try {

        const response = await fetch("http://127.0.0.1:5000/api/apps");

        applications = await response.json();

        console.log("Applications:", applications);

        updateStatistics();

        renderApplicationsTable(applications);

        drawPublisherChart();

        drawPublishingChart();

        drawPlatformChart();

    }

    catch (error) {

        console.error(error);

    }

}

// ------------------------------------------
// Statistics
// ------------------------------------------
function updateStatistics() {

    document.getElementById("appCount").textContent =
        applications.length;

    document.getElementById("applicationCount").textContent =
        applications.length + " Applications";

    let windows = 0;
    let mac = 0;
    let ios = 0;
    let android = 0;

    const publishers = new Set();

    applications.forEach(app => {

        const platform = getPlatform(app.app_type);

        switch (platform) {

            case "Windows":
                windows++;
                break;

            case "macOS":
                mac++;
                break;

            case "iOS/iPadOS":
                ios++;
                break;

            case "Android":
                android++;
                break;
        }

        publishers.add(app.publisher || "Unknown");
    });

    document.getElementById("windowsCount").textContent = windows;
    document.getElementById("macCount").textContent = mac;

    // Only if you add these cards to the dashboard
    // document.getElementById("iosCount").textContent = ios;
    // document.getElementById("androidCount").textContent = android;

    document.getElementById("publisherCount").textContent =
        publishers.size;
}

// ------------------------------------------
// Platform Detection
// ------------------------------------------

function getPlatform(type) {

    if (!type) {
        return "Other";
    }

    type = String(type).toLowerCase();

    // iOS / iPadOS
    if (
        type.startsWith("ios") ||
        type.includes("ios") ||
        type.includes("ipad")
    ) {
        return "iOS/iPadOS";
    }

    // macOS
    if (
        type.startsWith("macos") ||
        type.includes("macos")
    ) {
        return "macOS";
    }

    // Android
    if (
        type.startsWith("android") ||
        type.includes("android")
    ) {
        return "Android";
    }

    // Windows
    if (
        type.startsWith("windows") ||
        type.includes("windows") ||
        type.includes("win32") ||
        type === "officesuiteapp" ||
        type.includes("microsoftstore")
    ) {
        return "Windows";
    }

    // Generic web applications
    if (type === "webapp") {
        return "Web";
    }

    return "Other";
}

// ------------------------------------------
// Size Formatter
// ------------------------------------------

function formatSize(size) {

    if (!size)
        return "-";

    return (size / 1024 / 1024).toFixed(2) + " MB";

}

// ------------------------------------------
// Render Table
// ------------------------------------------

function renderApplicationsTable(data) {

    const tbody =
        document.getElementById("applicationsTableBody");

    tbody.innerHTML = "";

    data.forEach(app => {

        tbody.innerHTML += `

<tr class="border-b hover:bg-slate-50 transition">

<td class="p-5">

<div>

<div class="font-semibold">

${app.display_name}

</div>

<div class="text-sm text-slate-500">

${app.id}

</div>

</div>

</td>

<td class="p-5">

${app.publisher || "-"}

</td>

<td class="p-5">

${getPlatform(app.app_type)}

</td>

<td class="p-5">

${app.display_version || "-"}

</td>

<td class="p-5">

${formatSize(app.size)}

</td>

<td class="p-5">

<span class="px-3 py-1 rounded-full bg-green-100 text-green-700">

${app.publishing_state}

</span>

</td>

<td class="p-5 text-center">

<button

class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"

onclick="showApplication('${app.id}')">

View

</button>

</td>

</tr>

`;

    });

}

// ------------------------------------------
// Search
// ------------------------------------------

function searchApplications() {

    const value = document
        .getElementById("searchInput")
        .value
        .toLowerCase();

    const filtered = applications.filter(app =>

        (app.display_name || "").toLowerCase().includes(value) ||

        (app.publisher || "").toLowerCase().includes(value)

    );

    renderApplicationsTable(filtered);

}