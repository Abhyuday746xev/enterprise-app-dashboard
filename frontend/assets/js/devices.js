// ==========================================
// Enterprise Managed Devices
// ==========================================

let devices = [];

// ------------------------------------------
// Load Devices
// ------------------------------------------

document.addEventListener("DOMContentLoaded", () => {

    loadDevices();

    document
        .getElementById("searchInput")
        .addEventListener("keyup", searchDevices);

});

// ------------------------------------------
// Fetch Devices
// ------------------------------------------

async function loadDevices() {

    try {

        const response =
            await fetch("http://127.0.0.1:5000/api/devices");

        devices = await response.json();

        console.log(devices);

        updateStatistics();

        renderDevicesTable(devices);

    }

    catch(error){

        console.error(error);

    }

}

// ------------------------------------------
// Statistics
// ------------------------------------------

function updateStatistics(){

    document.getElementById("deviceCount").textContent =
        devices.length;

    let windows = 0;
    let mac = 0;
    let compliant = 0;

    devices.forEach(device=>{

        const os =
            (device.operating_system || "").toLowerCase();

        if(os.includes("windows"))
            windows++;

        else if(os.includes("mac"))
            mac++;

        if(
            (device.compliance_state || "")
            .toLowerCase()
            .includes("compliant")
        )
            compliant++;

    });

    document.getElementById("windowsCount").textContent =
        windows;

    document.getElementById("macCount").textContent =
        mac;

    document.getElementById("compliantCount").textContent =
        compliant;

}

// ------------------------------------------
// Render Table
// ------------------------------------------

function renderDevicesTable(data){

    const tbody =
        document.getElementById("devicesTableBody");

    tbody.innerHTML = "";

    data.forEach(device=>{

        tbody.innerHTML += `

<tr class="border-b hover:bg-slate-50 transition">

<td class="p-5">

<div>

<div class="font-semibold">

${device.device_name}

</div>

<div class="text-sm text-slate-500">

${device.id}

</div>

</div>

</td>

<td class="p-5">

${device.user_name || "-"}

</td>

<td class="p-5">

${device.operating_system}

${device.os_version
? `<span class="text-slate-500 text-sm">(${device.os_version})</span>`
: ""}

</td>

<td class="p-5">

${device.manufacturer || "-"}

</td>

<td class="p-5">

<span class="px-3 py-1 rounded-full
${device.compliance_state === "compliant"
? "bg-green-100 text-green-700"
: "bg-red-100 text-red-700"}">

${device.compliance_state || "-"}

</span>

</td>

<td class="p-5">

${device.last_sync || "-"}

</td>

<td class="p-5 text-center">

<button

class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"

onclick="showDevice('${device.id}')">

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

function searchDevices(){

    const value =
        document
        .getElementById("searchInput")
        .value
        .toLowerCase();

    const filtered = devices.filter(device=>

        (device.device_name || "")
        .toLowerCase()
        .includes(value)

        ||

        (device.user_name || "")
        .toLowerCase()
        .includes(value)

        ||

        (device.operating_system || "")
        .toLowerCase()
        .includes(value)

        ||

        (device.manufacturer || "")
        .toLowerCase()
        .includes(value)

    );

    renderDevicesTable(filtered);

}