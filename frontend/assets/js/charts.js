// ======================================
// Enterprise Dashboard Charts
// ======================================

let publisherChart = null;
let publishingChart = null;

// --------------------------------------
// Publisher Distribution
// --------------------------------------

function drawPublisherChart() {

    const publishers = {};

    applications.forEach(app => {

        const publisher = app.publisher || "Unknown";

        publishers[publisher] = (publishers[publisher] || 0) + 1;

    });

    const ctx = document
        .getElementById("publisherChart")
        .getContext("2d");

    if (publisherChart)
        publisherChart.destroy();

    publisherChart = new Chart(ctx, {

        type: "pie",

        data: {

            labels: Object.keys(publishers),

            datasets: [{

                data: Object.values(publishers),

                backgroundColor: [

                    "#2563eb",
                    "#22c55e",
                    "#f97316",
                    "#8b5cf6",
                    "#06b6d4",
                    "#ec4899",
                    "#facc15",
                    "#64748b"

                ],

                borderWidth: 2,

                borderColor: "#ffffff"

            }]

        },

        options: {

            responsive: true,

            plugins: {

                legend: {

                    position: "bottom"

                }

            }

        }

    });

}

// --------------------------------------
// Publishing State
// --------------------------------------

function drawPublishingChart() {

    const states = {};

    applications.forEach(app => {

        const state = app.publishing_state || "Unknown";

        states[state] = (states[state] || 0) + 1;

    });

    const ctx = document
        .getElementById("publishingChart")
        .getContext("2d");

    if (publishingChart)
        publishingChart.destroy();

    publishingChart = new Chart(ctx, {

        type: "doughnut",

        data: {

            labels: Object.keys(states),

            datasets: [{

                data: Object.values(states),

                backgroundColor: [

                    "#22c55e",
                    "#2563eb",
                    "#f97316",
                    "#ef4444"

                ],

                borderWidth: 2,

                borderColor: "#ffffff"

            }]

        },

        options: {

            responsive: true,

            plugins: {

                legend: {

                    position: "bottom"

                }

            }

        }

    });

}
// --------------------------------------
// Platform Chart
// --------------------------------------

let platformChart = null;

function drawPlatformChart() {

    const platforms = {
        Windows: 0,
        macOS: 0,
        iOS: 0,
        Android: 0,
        Web: 0,
        Other: 0
    };

    applications.forEach(app => {

        const platform = getPlatform(app.app_type);

        switch (platform) {

            case "Windows":
                platforms.Windows++;
                break;

            case "macOS":
                platforms.macOS++;
                break;

            case "iOS/iPadOS":
                platforms.iOS++;
                break;

            case "Android":
                platforms.Android++;
                break;

            default:
                platforms.Web++;
                break;

        }

    });

    console.log("Platform Counts:", platforms);

    const canvas = document.getElementById("platformChart");

    if (!canvas) {
        console.error("platformChart canvas not found");
        return;
    }

    const ctx = canvas.getContext("2d");

    if (platformChart) {
        platformChart.destroy();
    }

    platformChart = new Chart(ctx, {

        type: "bar",

        data: {

            labels: [
                "Windows",
                "macOS",
                "iOS/iPadOS",
                "Android",
                "Web"
            ],

            datasets: [
                {
                    label: "Applications",

                    data: [
                        platforms.Windows,
                        platforms.macOS,
                        platforms.iOS,
                        platforms.Android,
                        platforms.Web
                    ],

                    backgroundColor: [
                        "#2563eb",
                        "#22c55e",
                        "#0ea5e9",
                        "#f97316",
                        "#8b5cf6"
                    ],

                    borderRadius: 8,
                    borderSkipped: false
                }
            ]
        },

        options: {

            responsive: true,
            maintainAspectRatio: false,

            plugins: {
                legend: {
                    display: false
                }
            },

            scales: {

                x: {
                    grid: {
                        display: false
                    }
                },

                y: {
                    beginAtZero: true,

                    ticks: {
                        stepSize: 1,
                        precision: 0
                    }
                }
            }
        }
    });
}