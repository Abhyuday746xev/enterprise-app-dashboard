// ==========================================
// Enterprise Application Details Drawer
// ==========================================

function showApplication(id) {

    const app = applications.find(a => a.id === id);

    if (!app) return;

    document
        .getElementById("detailsModal")
        .classList.remove("hidden");

    document
        .getElementById("detailsModal")
        .classList.add("flex");

    document
        .body
        .classList.add("overflow-hidden");

    document.getElementById("modalContent").innerHTML = `

<div class="flex items-center justify-between border-b pb-5">

    <div>

        <h2 class="text-3xl font-bold text-slate-800">

            ${app.display_name}

        </h2>

        <p class="text-slate-500 mt-1">

            ${app.id}

        </p>

    </div>

    <span class="px-4 py-2 rounded-full bg-green-100 text-green-700 font-medium">

        ${app.publishing_state}

    </span>

</div>


<div class="grid grid-cols-2 gap-8 mt-8">

<div>

<p class="text-sm text-slate-500">

Publisher

</p>

<p class="font-semibold mt-1">

${app.publisher || "-"}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Platform

</p>

<p class="font-semibold mt-1">

${getPlatform(app.app_type)}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Version

</p>

<p class="font-semibold mt-1">

${app.display_version || "-"}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Developer

</p>

<p class="font-semibold mt-1">

${app.developer || "-"}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Owner

</p>

<p class="font-semibold mt-1">

${app.owner || "-"}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Application Size

</p>

<p class="font-semibold mt-1">

${formatSize(app.size)}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Created

</p>

<p class="font-semibold mt-1">

${app.created_date || "-"}

</p>

</div>


<div>

<p class="text-sm text-slate-500">

Last Modified

</p>

<p class="font-semibold mt-1">

${app.last_modified_date || "-"}

</p>

</div>

</div>


<div class="mt-10">

<h3 class="font-bold text-xl">

Notes

</h3>

<div class="mt-3 rounded-xl bg-slate-50 p-5 border">

${app.notes || "No notes available."}

</div>

</div>


<div class="mt-10 flex justify-end">

<button

id="closeDrawer"

class="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold transition">

Close

</button>

</div>

`;

}

// ==========================================
// Close Drawer
// ==========================================

document.addEventListener("click", function (e) {

    if (

        e.target.id === "closeDrawer" ||

        e.target.id === "detailsModal"

    ) {

        document
            .getElementById("detailsModal")
            .classList.add("hidden");

        document
            .getElementById("detailsModal")
            .classList.remove("flex");

        document
            .body
            .classList.remove("overflow-hidden");

    }

});