"SEARCH FUNCTIONALITY"

// =============================================
// Enterprise Dashboard Search
// =============================================

let allApplications = [];
let filteredApplications = [];

// =============================================
// Initialize Search
// =============================================

function initializeSearch() {

    const searchInput = document.getElementById("searchInput");

    if (!searchInput) return;

    searchInput.addEventListener("input", function () {

        searchApplications(this.value);

    });

}

// =============================================
// Search Applications
// =============================================

function searchApplications(keyword) {

    keyword = keyword.toLowerCase().trim();

    if (keyword === "") {

        filteredApplications = allApplications;

    } else {

        filteredApplications = allApplications.filter(app =>

            app.display_name.toLowerCase().includes(keyword) ||

            app.publisher.toLowerCase().includes(keyword) ||

            app.app_type.toLowerCase().includes(keyword) ||

            app.file_name.toLowerCase().includes(keyword)

        );

    }

    renderTable(filteredApplications);

    updateSearchCount();

}

// =============================================
// Store Applications
// =============================================

function setApplications(data) {

    allApplications = data;

    filteredApplications = data;

    renderTable(filteredApplications);

    updateSearchCount();

}

// =============================================
// Update Search Count
// =============================================

function updateSearchCount() {

    const count = document.getElementById("resultCount");

    if (!count) return;

    count.innerHTML =

        `Showing ${filteredApplications.length} of ${allApplications.length} Applications`;

}