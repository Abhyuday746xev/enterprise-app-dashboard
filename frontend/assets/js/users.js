// ==========================================
// Enterprise Users
// ==========================================

let users = [];

// ------------------------------------------
// Load Users
// ------------------------------------------

document.addEventListener("DOMContentLoaded", () => {

    loadUsers();

    document
        .getElementById("searchInput")
        .addEventListener("keyup", searchUsers);

    const refresh = document.getElementById("refreshUsers");

    if (refresh) {

        refresh.addEventListener("click", loadUsers);

    }

});

// ------------------------------------------
// Fetch Users
// ------------------------------------------

async function loadUsers() {

    try {

        const response = await fetch("http://127.0.0.1:5000/api/users");

        users = await response.json();

        console.log(users);

        updateStatistics();

        renderUsers(users);

    }

    catch (error) {

        console.error(error);

    }

}

// ------------------------------------------
// Statistics
// ------------------------------------------

function updateStatistics() {

    document.getElementById("userCount").textContent =
        users.length;

    let enabled = 0;

    let disabled = 0;

    const departments = new Set();

    users.forEach(user => {

        if (user.account_enabled)

            enabled++;

        else

            disabled++;

        departments.add(user.department || "Unknown");

    });

    document.getElementById("enabledCount").textContent =
        enabled;

    document.getElementById("disabledCount").textContent =
        disabled;

    document.getElementById("departmentCount").textContent =
        departments.size;

}

// ------------------------------------------
// Render Table
// ------------------------------------------

function renderUsers(data) {

    const tbody = document.getElementById("usersTableBody");

    tbody.innerHTML = "";

    data.forEach(user => {

        tbody.innerHTML += `

<tr class="border-b hover:bg-slate-50 transition">

<td class="p-5">

<div>

<div class="font-semibold">

${user.display_name || "-"}

</div>

<div class="text-sm text-slate-500">

${user.user_principal_name || "-"}

</div>

</div>

</td>

<td class="p-5">

${user.mail || "-"}

</td>

<td class="p-5">

${
user.account_enabled

?

`<span class="px-3 py-1 rounded-full bg-green-100 text-green-700">

Enabled

</span>`

:

`<span class="px-3 py-1 rounded-full bg-red-100 text-red-700">

Disabled

</span>`

}

</td>

<td class="p-5 text-center">

<button

class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"

onclick="showUser('${user.id}')">

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

function searchUsers() {

    const value = document

        .getElementById("searchInput")

        .value

        .toLowerCase();

    const filtered = users.filter(user =>

        (user.display_name || "").toLowerCase().includes(value)

        ||

        (user.mail || "").toLowerCase().includes(value)

        ||

        (user.department || "").toLowerCase().includes(value)

        ||

        (user.office_location || "").toLowerCase().includes(value)

    );

    renderUsers(filtered);

}