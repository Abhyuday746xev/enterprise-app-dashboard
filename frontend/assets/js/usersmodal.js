// ==========================================
// Enterprise User Modal
// ==========================================

function showUser(id) {

    const user = users.find(u => u.id === id);

    if (!user) return;

    document
        .getElementById("detailsModal")
        .classList.remove("hidden");

    document
        .getElementById("detailsModal")
        .classList.add("flex");

    document.body.classList.add("overflow-hidden");

    document.getElementById("modalContent").innerHTML = `

<div class="space-y-8">

    <div class="border-b pb-6">

        <h2 class="text-3xl font-bold text-slate-800">

            ${user.display_name || "-"}

        </h2>

        <p class="text-slate-500 mt-2">

            ${user.user_principal_name || "-"}

        </p>

    </div>

    <div class="grid grid-cols-2 gap-8">

        <div>

            <p class="text-sm text-slate-500">

                Email

            </p>

            <p class="font-semibold mt-1">

                ${user.mail || "-"}

            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">

                Department

            </p>

            <p class="font-semibold mt-1">

                ${user.department || "-"}

            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">

                Job Title

            </p>

            <p class="font-semibold mt-1">

                ${user.job_title || "-"}

            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">

                Office Location

            </p>

            <p class="font-semibold mt-1">

                ${user.office_location || "-"}

            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">

                Mobile Phone

            </p>

            <p class="font-semibold mt-1">

                ${user.mobile_phone || "-"}

            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">

                Account Status

            </p>

            <p class="font-semibold mt-1">

                ${
                    user.account_enabled
                    ? '<span class="px-3 py-1 rounded-full bg-green-100 text-green-700">Enabled</span>'
                    : '<span class="px-3 py-1 rounded-full bg-red-100 text-red-700">Disabled</span>'
                }

            </p>

        </div>

        <div class="col-span-2">

            <p class="text-sm text-slate-500">

                User ID

            </p>

            <p class="font-mono text-sm break-all mt-1">

                ${user.id}

            </p>

        </div>

    </div>

    <div class="flex justify-end pt-4">

        <button

            id="closeDrawer"

            class="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold transition">

            Close

        </button>

    </div>

</div>

`;

}

// ==========================================
// Close Modal
// ==========================================

document.addEventListener("click", function (e) {

    if (

        e.target.id === "closeDrawer" ||

        e.target.id === "closeModal" ||

        e.target.id === "detailsModal"

    ) {

        document
            .getElementById("detailsModal")
            .classList.add("hidden");

        document
            .getElementById("detailsModal")
            .classList.remove("flex");

        document.body.classList.remove("overflow-hidden");

    }

});