// ==========================================
// Enterprise Device Details Modal
// ==========================================

function showDevice(id) {

    const device = devices.find(d => d.id === id);

    if (!device) return;

    document
        .getElementById("detailsModal")
        .classList.remove("hidden");

    document
        .getElementById("detailsModal")
        .classList.add("flex");

    document.body.classList.add("overflow-hidden");

    const complianceClass =
        (device.compliance_state || "").toLowerCase() === "compliant"
            ? "bg-green-100 text-green-700"
            : "bg-red-100 text-red-700";

    document.getElementById("modalContent").innerHTML = `

<div class="flex justify-between items-center border-b pb-6">

    <div>

        <h2 class="text-3xl font-bold text-slate-800">

            ${device.device_name}

        </h2>

        <p class="text-slate-500 mt-2">

            ${device.id}

        </p>

    </div>

    <span class="px-4 py-2 rounded-full font-semibold ${complianceClass}">

        ${device.compliance_state || "-"}

    </span>

</div>

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

<p class="text-slate-500 text-sm">

Assigned User

</p>

<p class="font-semibold mt-1">

${device.user_name || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

Operating System

</p>

<p class="font-semibold mt-1">

${device.operating_system || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

OS Version

</p>

<p class="font-semibold mt-1">

${device.os_version || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

Manufacturer

</p>

<p class="font-semibold mt-1">

${device.manufacturer || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

Model

</p>

<p class="font-semibold mt-1">

${device.model || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

Compliance State

</p>

<p class="font-semibold mt-1">

${device.compliance_state || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

Last Sync

</p>

<p class="font-semibold mt-1">

${device.last_sync || "-"}

</p>

</div>

<div>

<p class="text-slate-500 text-sm">

Device ID

</p>

<p class="font-semibold mt-1 break-all">

${device.id}

</p>

</div>

</div>

<div class="mt-10">

<div class="rounded-2xl bg-slate-50 border p-6">

<h3 class="font-bold text-lg mb-4">

Device Summary

</h3>

<div class="space-y-2 text-slate-600">

<p>

<strong>Name:</strong>
${device.device_name}

</p>

<p>

<strong>User:</strong>
${device.user_name || "-"}

</p>

<p>

<strong>Platform:</strong>
${device.operating_system || "-"}

</p>

<p>

<strong>Manufacturer:</strong>
${device.manufacturer || "-"}

</p>

<p>

<strong>Model:</strong>
${device.model || "-"}

</p>

<p>

<strong>Compliance:</strong>
${device.compliance_state || "-"}

</p>

</div>

</div>

</div>

<div class="flex justify-end mt-10">

<button

id="closeDeviceModal"

class="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold transition">

Close

</button>

</div>

`;

}

// ==========================================
// Close Modal
// ==========================================

document.addEventListener("click", function(e){

    if(

        e.target.id === "closeDeviceModal"

        ||

        e.target.id === "closeModal"

        ||

        e.target.id === "detailsModal"

    ){

        document
            .getElementById("detailsModal")
            .classList.add("hidden");

        document
            .getElementById("detailsModal")
            .classList.remove("flex");

        document.body.classList.remove("overflow-hidden");

    }

});