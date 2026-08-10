// ==============================================
// Enterprise Dashboard Table
// ==============================================

// Render Applications Table
function renderTable(applications) {

    const tableBody = document.getElementById("tableBody");

    tableBody.innerHTML = "";

    if (applications.length === 0) {

        tableBody.innerHTML = `

        <tr>

            <td colspan="7" class="text-center py-12 text-slate-500">

                No Applications Found

            </td>

        </tr>

        `;

        return;

    }

    applications.forEach(app => {

        const row = document.createElement("tr");

        row.className = "hover:bg-blue-50 transition";

        row.innerHTML = `

            <td class="p-4 font-semibold">

                ${app.display_name}

            </td>

            <td class="p-4">

                ${app.publisher}

            </td>

            <td class="p-4">

                ${app.app_type}

            </td>

            <td class="p-4">

                ${createBadge(app.publishing_state)}

            </td>

            <td class="p-4">

                ${app.file_name}

            </td>

            <td class="p-4">

                ${formatSize(app.size)}

            </td>

            <td class="p-4 text-center">

                <button
                    class="view-btn bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition"
                    data-id="${app.id}">

                    <i class="fa-solid fa-eye mr-2"></i>

                    View

                </button>

            </td>

        `;

        tableBody.appendChild(row);

    });

    setupViewButtons(applications);

}

// ==============================================
// View Button
// ==============================================

function setupViewButtons(applications){

    document.querySelectorAll(".view-btn").forEach(button=>{

        button.addEventListener("click",()=>{

            const id = button.dataset.id;

            const app = applications.find(a=>a.id===id);

            if(app){

                openModal(app);

            }

        });

    });

}

// ==============================================
// Size Formatter
// ==============================================

function formatSize(bytes){

    if(!bytes) return "-";

    return (bytes/1024/1024).toFixed(2)+" MB";

}

// ==============================================
// Publishing Badge
// ==============================================

function createBadge(state){

    state = state.toLowerCase();

    if(state==="published"){

        return `

        <span
        class="bg-green-100 text-green-700 px-3 py-1 rounded-full text-sm font-semibold">

        Published

        </span>

        `;

    }

    if(state==="processing"){

        return `

        <span
        class="bg-yellow-100 text-yellow-700 px-3 py-1 rounded-full text-sm font-semibold">

        Processing

        </span>

        `;

    }

    if(state==="failed"){

        return `

        <span
        class="bg-red-100 text-red-700 px-3 py-1 rounded-full text-sm font-semibold">

        Failed

        </span>

        `;

    }

    return `

    <span
    class="bg-slate-100 text-slate-700 px-3 py-1 rounded-full text-sm font-semibold">

    ${state}

    </span>

    `;

}