// ==========================================
// Enterprise Ticket Service
// ==========================================

const TICKET_API_BASE_URL =
    "http://127.0.0.1:5000/api";


// ==========================================
// Ticket Page State
// ==========================================

let currentTicketPage = 1;
let totalTicketPages = 1;
let ticketSearchTimer = null;

const ticketPageLimit = 25;


// ==========================================
// Initialize Ticket Page
// ==========================================

document.addEventListener(
    "DOMContentLoaded",
    async function () {

        console.log(
            "Enterprise Ticket Service Loaded"
        );

        initializeTicketPage();

        await Promise.all([
            loadTicketStatistics(),
            loadTickets()
        ]);

    }
);


// ==========================================
// Initialize Event Listeners
// ==========================================

function initializeTicketPage() {

    const ticketForm =
        document.getElementById("ticketForm");

    const refreshButton =
        document.getElementById(
            "refreshTicketsButton"
        );

    const ticketSearch =
        document.getElementById("ticketSearch");

    const statusFilter =
        document.getElementById("statusFilter");

    const priorityFilter =
        document.getElementById(
            "priorityFilter"
        );

    const previousPageButton =
        document.getElementById(
            "previousPageButton"
        );

    const nextPageButton =
        document.getElementById(
            "nextPageButton"
        );

    const closeDialogButton =
        document.getElementById(
            "closeTicketDialogButton"
        );

    const ticketDialog =
        document.getElementById(
            "ticketDialog"
        );


    // --------------------------------------
    // Create Ticket
    // --------------------------------------

    if (ticketForm) {

        ticketForm.addEventListener(
            "submit",
            createTicket
        );

    }


    // --------------------------------------
    // Refresh Tickets
    // --------------------------------------

    if (refreshButton) {

        refreshButton.addEventListener(
            "click",
            async function () {

                await refreshTicketPage();

            }
        );

    }


    // --------------------------------------
    // Search Tickets
    // --------------------------------------

    if (ticketSearch) {

        ticketSearch.addEventListener(
            "input",
            function () {

                window.clearTimeout(
                    ticketSearchTimer
                );

                ticketSearchTimer =
                    window.setTimeout(
                        async function () {

                            currentTicketPage = 1;

                            await loadTickets();

                        },
                        350
                    );

            }
        );

    }


    // --------------------------------------
    // Status Filter
    // --------------------------------------

    if (statusFilter) {

        statusFilter.addEventListener(
            "change",
            async function () {

                currentTicketPage = 1;

                await loadTickets();

            }
        );

    }


    // --------------------------------------
    // Priority Filter
    // --------------------------------------

    if (priorityFilter) {

        priorityFilter.addEventListener(
            "change",
            async function () {

                currentTicketPage = 1;

                await loadTickets();

            }
        );

    }


    // --------------------------------------
    // Previous Page
    // --------------------------------------

    if (previousPageButton) {

        previousPageButton.addEventListener(
            "click",
            async function () {

                if (currentTicketPage <= 1) {
                    return;
                }

                currentTicketPage--;

                await loadTickets();

            }
        );

    }


    // --------------------------------------
    // Next Page
    // --------------------------------------

    if (nextPageButton) {

        nextPageButton.addEventListener(
            "click",
            async function () {

                if (
                    currentTicketPage >=
                    totalTicketPages
                ) {
                    return;
                }

                currentTicketPage++;

                await loadTickets();

            }
        );

    }


    // --------------------------------------
    // Close Ticket Dialog
    // --------------------------------------

    if (closeDialogButton && ticketDialog) {

        closeDialogButton.addEventListener(
            "click",
            function () {

                ticketDialog.close();

            }
        );

    }


    // Close when clicking the dialog backdrop.
    if (ticketDialog) {

        ticketDialog.addEventListener(
            "click",
            function (event) {

                if (
                    event.target ===
                    ticketDialog
                ) {

                    ticketDialog.close();

                }

            }
        );

    }

}


// ==========================================
// API Request Helper
// ==========================================

async function ticketApiRequest(
    endpoint,
    options = {}
) {

    const response = await fetch(
        `${TICKET_API_BASE_URL}${endpoint}`,
        {
            ...options,

            headers: {
                "Content-Type":
                    "application/json",

                ...(options.headers || {})
            }
        }
    );


    let result;

    try {

        result = await response.json();

    }

    catch (error) {

        throw new Error(
            "The server returned an invalid response."
        );

    }


    if (!response.ok) {

        throw new Error(
            result.message ||
            result.error ||
            "Ticket request failed."
        );

    }

    return result;

}


// ==========================================
// Refresh Ticket Page
// ==========================================

async function refreshTicketPage() {

    const refreshButton =
        document.getElementById(
            "refreshTicketsButton"
        );

    if (refreshButton) {

        refreshButton.disabled = true;

        refreshButton.innerHTML = `
            <i class="fa-solid fa-rotate fa-spin mr-2"></i>
            Refreshing...
        `;

    }


    try {

        await Promise.all([
            loadTicketStatistics(),
            loadTickets()
        ]);

        showTicketMessage(
            "Tickets refreshed successfully.",
            "success"
        );

    }

    catch (error) {

        console.error(
            "Ticket Refresh Error:",
            error
        );

        showTicketMessage(
            error.message,
            "error"
        );

    }

    finally {

        if (refreshButton) {

            refreshButton.disabled = false;

            refreshButton.innerHTML = `
                <i class="fa-solid fa-rotate mr-2"></i>
                Refresh Tickets
            `;

        }

    }

}


// ==========================================
// Load Ticket Statistics
// ==========================================

async function loadTicketStatistics() {

    try {

        const result =
            await ticketApiRequest(
                "/tickets/stats"
            );

        const statistics =
            result.statistics || {};


        updateTextContent(
            "totalTickets",
            statistics.total || 0
        );

        updateTextContent(
            "openTickets",
            statistics.open_count || 0
        );

        updateTextContent(
            "inProgressTickets",
            statistics.in_progress_count || 0
        );

        updateTextContent(
            "criticalTickets",
            statistics.critical_count || 0
        );

    }

    catch (error) {

        console.error(
            "Ticket Statistics Error:",
            error
        );

        throw error;

    }

}


// ==========================================
// Load Tickets
// ==========================================

async function loadTickets() {

    const tableBody =
        document.getElementById(
            "ticketTableBody"
        );

    if (!tableBody) {

        console.warn(
            "Ticket table body was not found."
        );

        return;

    }


    tableBody.innerHTML = `
        <tr>
            <td
                colspan="7"
                class="p-6 text-center text-slate-500"
            >
                <i class="fa-solid fa-spinner fa-spin mr-2"></i>
                Loading tickets...
            </td>
        </tr>
    `;


    try {

        const queryParameters =
            buildTicketQueryParameters();

        const result =
            await ticketApiRequest(
                `/tickets?${queryParameters.toString()}`
            );

        const tickets =
            Array.isArray(result.tickets)
                ? result.tickets
                : [];

        const pagination =
            result.pagination || {};


        currentTicketPage =
            Number(pagination.page || 1);

        totalTicketPages =
            Number(
                pagination.total_pages || 0
            );


        renderTicketTable(tickets);

        updateTicketPagination(
            pagination
        );

    }

    catch (error) {

        console.error(
            "Load Tickets Error:",
            error
        );

        tableBody.innerHTML = `
            <tr>
                <td
                    colspan="7"
                    class="p-6 text-center text-red-600"
                >
                    ${escapeHtml(error.message)}
                </td>
            </tr>
        `;

    }

}


// ==========================================
// Build Ticket Query Parameters
// ==========================================

function buildTicketQueryParameters() {

    const query =
        new URLSearchParams();

    const search =
        document
            .getElementById("ticketSearch")
            ?.value
            ?.trim() || "";

    const status =
        document
            .getElementById("statusFilter")
            ?.value || "";

    const priority =
        document
            .getElementById("priorityFilter")
            ?.value || "";


    query.set(
        "page",
        String(currentTicketPage)
    );

    query.set(
        "limit",
        String(ticketPageLimit)
    );


    if (search) {

        query.set(
            "search",
            search
        );

    }


    if (status) {

        query.set(
            "status",
            status
        );

    }


    if (priority) {

        query.set(
            "priority",
            priority
        );

    }


    return query;

}


// ==========================================
// Render Ticket Table
// ==========================================

function renderTicketTable(tickets) {

    const tableBody =
        document.getElementById(
            "ticketTableBody"
        );

    if (!tableBody) {
        return;
    }


    if (!tickets.length) {

        tableBody.innerHTML = `
            <tr>
                <td
                    colspan="7"
                    class="p-8 text-center text-slate-500"
                >
                    No tickets were found.
                </td>
            </tr>
        `;

        return;

    }


    tableBody.innerHTML =
        tickets
            .map(
                function (ticket) {

                    return `
                        <tr
                            class="
                                border-b
                                hover:bg-slate-50
                                transition
                            "
                        >

                            <td class="p-4">

                                <button
                                    type="button"
                                    class="
                                        ticket-number-button
                                        font-semibold
                                        text-blue-600
                                        hover:text-blue-800
                                    "
                                    data-ticket-number="${
                                        escapeHtml(
                                            ticket.ticket_number
                                        )
                                    }"
                                >
                                    ${
                                        escapeHtml(
                                            ticket.ticket_number
                                        )
                                    }
                                </button>

                            </td>


                            <td class="p-4">

                                <div class="font-medium text-slate-800">

                                    ${
                                        escapeHtml(
                                            ticket.title ||
                                            "Untitled Ticket"
                                        )
                                    }

                                </div>

                                <div class="text-sm text-slate-500 mt-1">

                                    ${
                                        escapeHtml(
                                            ticket.category ||
                                            "General"
                                        )
                                    }

                                </div>

                            </td>


                            <td class="p-4">

                                ${createPriorityBadge(
                                    ticket.priority
                                )}

                            </td>


                            <td class="p-4">

                                ${createStatusBadge(
                                    ticket.status
                                )}

                            </td>


                            <td class="p-4">

                                <div>

                                    ${
                                        escapeHtml(
                                            ticket.requester_name ||
                                            "-"
                                        )
                                    }

                                </div>

                                <div class="text-sm text-slate-500">

                                    ${
                                        escapeHtml(
                                            ticket.requester_email ||
                                            ""
                                        )
                                    }

                                </div>

                            </td>


                            <td class="p-4">

                                ${
                                    escapeHtml(
                                        ticket.assigned_to ||
                                        "Unassigned"
                                    )
                                }

                            </td>


                            <td class="p-4 text-sm text-slate-600">

                                ${
                                    escapeHtml(
                                        formatTicketDate(
                                            ticket.created_at
                                        )
                                    )
                                }

                            </td>

                        </tr>
                    `;

                }
            )
            .join("");


    document
        .querySelectorAll(
            ".ticket-number-button"
        )
        .forEach(
            function (button) {

                button.addEventListener(
                    "click",
                    async function () {

                        const ticketNumber =
                            button.dataset
                                .ticketNumber;

                        await openTicketDetails(
                            ticketNumber
                        );

                    }
                );

            }
        );

}


// ==========================================
// Ticket Pagination
// ==========================================

function updateTicketPagination(
    pagination
) {

    const previousButton =
        document.getElementById(
            "previousPageButton"
        );

    const nextButton =
        document.getElementById(
            "nextPageButton"
        );

    const paginationText =
        document.getElementById(
            "paginationText"
        );


    const page =
        Number(pagination.page || 1);

    const totalPages =
        Number(
            pagination.total_pages || 0
        );

    const total =
        Number(pagination.total || 0);


    if (paginationText) {

        if (totalPages === 0) {

            paginationText.textContent =
                "No tickets";

        }

        else {

            paginationText.textContent =
                `Page ${page} of ${totalPages} · ${total} Tickets`;

        }

    }


    if (previousButton) {

        previousButton.disabled =
            page <= 1;

    }


    if (nextButton) {

        nextButton.disabled =
            totalPages === 0 ||
            page >= totalPages;

    }

}


// ==========================================
// Create Ticket
// ==========================================

async function createTicket(event) {

    event.preventDefault();


    const createButton =
        document.getElementById(
            "createTicketButton"
        );

    const ticketForm =
        document.getElementById(
            "ticketForm"
        );


    const payload = {

        title:
            document
                .getElementById("ticketTitle")
                ?.value
                ?.trim() || "",

        description:
            document
                .getElementById(
                    "ticketDescription"
                )
                ?.value
                ?.trim() || "",

        category:
            document
                .getElementById(
                    "ticketCategory"
                )
                ?.value || "General",

        priority:
            document
                .getElementById(
                    "ticketPriority"
                )
                ?.value || "Medium",

        requester_name:
            document
                .getElementById(
                    "requesterName"
                )
                ?.value
                ?.trim() || "",

        requester_email:
            document
                .getElementById(
                    "requesterEmail"
                )
                ?.value
                ?.trim() || "",

        assigned_to:
            document
                .getElementById(
                    "assignedTo"
                )
                ?.value
                ?.trim() || "",

        related_entity_type:
            document
                .getElementById(
                    "relatedEntityType"
                )
                ?.value || "general",

        related_entity_id:
            document
                .getElementById(
                    "relatedEntityId"
                )
                ?.value
                ?.trim() || ""

    };


    if (
        !payload.title ||
        !payload.description ||
        !payload.requester_name
    ) {

        showTicketMessage(
            "Title, description and requester name are required.",
            "error"
        );

        return;

    }


    if (createButton) {

        createButton.disabled = true;

        createButton.innerHTML = `
            <i class="fa-solid fa-spinner fa-spin mr-2"></i>
            Creating...
        `;

    }


    try {

        const result =
            await ticketApiRequest(
                "/tickets",
                {
                    method: "POST",
                    body: JSON.stringify(
                        payload
                    )
                }
            );


        const ticketNumber =
            result.ticket
                ?.ticket_number ||
            "New ticket";


        showTicketMessage(
            `${ticketNumber} was created successfully.`,
            "success"
        );


        if (ticketForm) {

            ticketForm.reset();

        }


        currentTicketPage = 1;


        await Promise.all([
            loadTickets(),
            loadTicketStatistics()
        ]);

    }

    catch (error) {

        console.error(
            "Create Ticket Error:",
            error
        );

        showTicketMessage(
            error.message,
            "error"
        );

    }

    finally {

        if (createButton) {

            createButton.disabled = false;

            createButton.innerHTML = `
                <i class="fa-solid fa-plus mr-2"></i>
                Create Ticket
            `;

        }

    }

}


// ==========================================
// Open Ticket Details
// ==========================================

async function openTicketDetails(
    ticketNumber
) {

    const ticketDialog =
        document.getElementById(
            "ticketDialog"
        );

    const dialogContent =
        document.getElementById(
            "ticketDialogContent"
        );

    const dialogTicketNumber =
        document.getElementById(
            "dialogTicketNumber"
        );

    const dialogTicketTitle =
        document.getElementById(
            "dialogTicketTitle"
        );


    if (
        !ticketDialog ||
        !dialogContent
    ) {

        console.warn(
            "Ticket dialog was not found."
        );

        return;

    }


    dialogContent.innerHTML = `
        <div class="p-8 text-center text-slate-500">
            <i class="fa-solid fa-spinner fa-spin mr-2"></i>
            Loading ticket details...
        </div>
    `;


    if (!ticketDialog.open) {

        ticketDialog.showModal();

    }


    try {

        const result =
            await ticketApiRequest(
                `/tickets/${
                    encodeURIComponent(
                        ticketNumber
                    )
                }`
            );

        const ticket =
            result.ticket;

        const comments =
            Array.isArray(result.comments)
                ? result.comments
                : [];


        if (dialogTicketNumber) {

            dialogTicketNumber.textContent =
                ticket.ticket_number;

        }


        if (dialogTicketTitle) {

            dialogTicketTitle.textContent =
                ticket.title;

        }


        renderTicketDetails(
            ticket,
            comments
        );

    }

    catch (error) {

        console.error(
            "Ticket Details Error:",
            error
        );

        dialogContent.innerHTML = `
            <div class="p-6 text-red-600">
                ${escapeHtml(error.message)}
            </div>
        `;

    }

}


// ==========================================
// Render Ticket Details
// ==========================================

function renderTicketDetails(
    ticket,
    comments
) {

    const dialogContent =
        document.getElementById(
            "ticketDialogContent"
        );

    if (!dialogContent) {
        return;
    }


    dialogContent.innerHTML = `

        <div class="space-y-6">


            <!-- Ticket Description -->

            <section>

                <h3 class="font-semibold text-slate-800 mb-2">
                    Description
                </h3>

                <p class="text-slate-600 whitespace-pre-wrap">

                    ${
                        escapeHtml(
                            ticket.description ||
                            "No description provided."
                        )
                    }

                </p>

            </section>


            <!-- Ticket Information -->

            <section
                class="
                    grid
                    grid-cols-1
                    md:grid-cols-2
                    gap-4
                "
            >

                <label class="text-sm font-semibold text-slate-700">

                    Status

                    <select
                        id="dialogTicketStatus"
                        class="
                            mt-2
                            w-full
                            border
                            border-slate-300
                            rounded-lg
                            p-3
                        "
                    >

                        ${createStatusOptions(
                            ticket.status
                        )}

                    </select>

                </label>


                <label class="text-sm font-semibold text-slate-700">

                    Priority

                    <select
                        id="dialogTicketPriority"
                        class="
                            mt-2
                            w-full
                            border
                            border-slate-300
                            rounded-lg
                            p-3
                        "
                    >

                        ${createPriorityOptions(
                            ticket.priority
                        )}

                    </select>

                </label>


                <label class="text-sm font-semibold text-slate-700">

                    Category

                    <input
                        id="dialogTicketCategory"
                        type="text"
                        class="
                            mt-2
                            w-full
                            border
                            border-slate-300
                            rounded-lg
                            p-3
                        "
                        value="${
                            escapeHtml(
                                ticket.category ||
                                "General"
                            )
                        }"
                    >

                </label>


                <label class="text-sm font-semibold text-slate-700">

                    Assigned To

                    <input
                        id="dialogTicketAssignedTo"
                        type="text"
                        class="
                            mt-2
                            w-full
                            border
                            border-slate-300
                            rounded-lg
                            p-3
                        "
                        value="${
                            escapeHtml(
                                ticket.assigned_to ||
                                ""
                            )
                        }"
                        placeholder="Unassigned"
                    >

                </label>

            </section>


            <!-- Requester Information -->

            <section
                class="
                    bg-slate-50
                    rounded-xl
                    p-4
                    grid
                    grid-cols-1
                    md:grid-cols-2
                    gap-4
                "
            >

                <div>

                    <div class="text-xs uppercase font-semibold text-slate-500">
                        Requester
                    </div>

                    <div class="mt-1 font-medium">

                        ${
                            escapeHtml(
                                ticket.requester_name ||
                                "-"
                            )
                        }

                    </div>

                </div>


                <div>

                    <div class="text-xs uppercase font-semibold text-slate-500">
                        Requester Email
                    </div>

                    <div class="mt-1 font-medium">

                        ${
                            escapeHtml(
                                ticket.requester_email ||
                                "-"
                            )
                        }

                    </div>

                </div>


                <div>

                    <div class="text-xs uppercase font-semibold text-slate-500">
                        Related To
                    </div>

                    <div class="mt-1 font-medium">

                        ${
                            escapeHtml(
                                ticket.related_entity_type ||
                                "general"
                            )
                        }

                    </div>

                </div>


                <div>

                    <div class="text-xs uppercase font-semibold text-slate-500">
                        Related Record ID
                    </div>

                    <div class="mt-1 font-medium break-all">

                        ${
                            escapeHtml(
                                ticket.related_entity_id ||
                                "-"
                            )
                        }

                    </div>

                </div>


                <div>

                    <div class="text-xs uppercase font-semibold text-slate-500">
                        Created
                    </div>

                    <div class="mt-1 font-medium">

                        ${
                            escapeHtml(
                                formatTicketDate(
                                    ticket.created_at
                                )
                            )
                        }

                    </div>

                </div>


                <div>

                    <div class="text-xs uppercase font-semibold text-slate-500">
                        Last Updated
                    </div>

                    <div class="mt-1 font-medium">

                        ${
                            escapeHtml(
                                formatTicketDate(
                                    ticket.updated_at
                                )
                            )
                        }

                    </div>

                </div>

            </section>


            <!-- Ticket Buttons -->

            <section class="flex flex-wrap gap-3">

                <button
                    id="saveTicketChangesButton"
                    type="button"
                    class="
                        bg-blue-600
                        hover:bg-blue-700
                        text-white
                        px-5
                        py-3
                        rounded-lg
                        font-semibold
                    "
                >
                    <i class="fa-solid fa-floppy-disk mr-2"></i>
                    Save Changes
                </button>


                <button
                    id="deleteTicketButton"
                    type="button"
                    class="
                        bg-red-50
                        hover:bg-red-100
                        text-red-700
                        px-5
                        py-3
                        rounded-lg
                        font-semibold
                    "
                >
                    <i class="fa-solid fa-trash mr-2"></i>
                    Delete Ticket
                </button>

            </section>


            <hr class="border-slate-200">


            <!-- Ticket Comments -->

            <section>

                <h3 class="font-semibold text-slate-800 mb-4">
                    Comments
                </h3>


                <div
                    id="ticketCommentsList"
                    class="space-y-3"
                >

                    ${renderTicketComments(
                        comments
                    )}

                </div>


                <form
                    id="ticketCommentForm"
                    class="
                        mt-5
                        bg-slate-50
                        rounded-xl
                        p-4
                        space-y-4
                    "
                >

                    <label class="block text-sm font-semibold text-slate-700">

                        Your Name

                        <input
                            id="commentAuthorName"
                            type="text"
                            required
                            class="
                                mt-2
                                w-full
                                border
                                border-slate-300
                                rounded-lg
                                p-3
                            "
                            placeholder="Enter your name"
                        >

                    </label>


                    <label class="block text-sm font-semibold text-slate-700">

                        Comment

                        <textarea
                            id="ticketCommentText"
                            required
                            rows="3"
                            class="
                                mt-2
                                w-full
                                border
                                border-slate-300
                                rounded-lg
                                p-3
                            "
                            placeholder="Add a ticket comment"
                        ></textarea>

                    </label>


                    <button
                        id="addTicketCommentButton"
                        type="submit"
                        class="
                            bg-slate-800
                            hover:bg-slate-900
                            text-white
                            px-5
                            py-3
                            rounded-lg
                            font-semibold
                        "
                    >
                        <i class="fa-solid fa-comment mr-2"></i>
                        Add Comment
                    </button>

                </form>

            </section>

        </div>
    `;


    const saveButton =
        document.getElementById(
            "saveTicketChangesButton"
        );

    const deleteButton =
        document.getElementById(
            "deleteTicketButton"
        );

    const commentForm =
        document.getElementById(
            "ticketCommentForm"
        );


    if (saveButton) {

        saveButton.addEventListener(
            "click",
            async function () {

                await updateTicket(
                    ticket.ticket_number
                );

            }
        );

    }


    if (deleteButton) {

        deleteButton.addEventListener(
            "click",
            async function () {

                await deleteTicket(
                    ticket.ticket_number
                );

            }
        );

    }


    if (commentForm) {

        commentForm.addEventListener(
            "submit",
            async function (event) {

                await addTicketComment(
                    event,
                    ticket.ticket_number
                );

            }
        );

    }

}


// ==========================================
// Update Ticket
// ==========================================

async function updateTicket(
    ticketNumber
) {

    const saveButton =
        document.getElementById(
            "saveTicketChangesButton"
        );


    const payload = {

        status:
            document
                .getElementById(
                    "dialogTicketStatus"
                )
                ?.value,

        priority:
            document
                .getElementById(
                    "dialogTicketPriority"
                )
                ?.value,

        category:
            document
                .getElementById(
                    "dialogTicketCategory"
                )
                ?.value
                ?.trim(),

        assigned_to:
            document
                .getElementById(
                    "dialogTicketAssignedTo"
                )
                ?.value
                ?.trim()

    };


    if (saveButton) {

        saveButton.disabled = true;

        saveButton.innerHTML = `
            <i class="fa-solid fa-spinner fa-spin mr-2"></i>
            Saving...
        `;

    }


    try {

        await ticketApiRequest(
            `/tickets/${
                encodeURIComponent(
                    ticketNumber
                )
            }`,
            {
                method: "PATCH",
                body: JSON.stringify(
                    payload
                )
            }
        );


        showTicketMessage(
            `${ticketNumber} was updated successfully.`,
            "success"
        );


        await Promise.all([
            loadTickets(),
            loadTicketStatistics()
        ]);


        await openTicketDetails(
            ticketNumber
        );

    }

    catch (error) {

        console.error(
            "Update Ticket Error:",
            error
        );

        showTicketMessage(
            error.message,
            "error"
        );

    }

    finally {

        const refreshedSaveButton =
            document.getElementById(
                "saveTicketChangesButton"
            );

        if (refreshedSaveButton) {

            refreshedSaveButton.disabled = false;

            refreshedSaveButton.innerHTML = `
                <i class="fa-solid fa-floppy-disk mr-2"></i>
                Save Changes
            `;

        }

    }

}


// ==========================================
// Delete Ticket
// ==========================================

async function deleteTicket(
    ticketNumber
) {

    const confirmed =
        window.confirm(
            `Delete ${ticketNumber}? This action cannot be undone.`
        );


    if (!confirmed) {
        return;
    }


    const deleteButton =
        document.getElementById(
            "deleteTicketButton"
        );


    if (deleteButton) {

        deleteButton.disabled = true;

        deleteButton.innerHTML = `
            <i class="fa-solid fa-spinner fa-spin mr-2"></i>
            Deleting...
        `;

    }


    try {

        await ticketApiRequest(
            `/tickets/${
                encodeURIComponent(
                    ticketNumber
                )
            }`,
            {
                method: "DELETE"
            }
        );


        const ticketDialog =
            document.getElementById(
                "ticketDialog"
            );

        if (ticketDialog?.open) {

            ticketDialog.close();

        }


        showTicketMessage(
            `${ticketNumber} was deleted successfully.`,
            "success"
        );


        currentTicketPage = 1;


        await Promise.all([
            loadTickets(),
            loadTicketStatistics()
        ]);

    }

    catch (error) {

        console.error(
            "Delete Ticket Error:",
            error
        );

        showTicketMessage(
            error.message,
            "error"
        );

    }

    finally {

        const refreshedDeleteButton =
            document.getElementById(
                "deleteTicketButton"
            );

        if (refreshedDeleteButton) {

            refreshedDeleteButton.disabled = false;

            refreshedDeleteButton.innerHTML = `
                <i class="fa-solid fa-trash mr-2"></i>
                Delete Ticket
            `;

        }

    }

}


// ==========================================
// Add Ticket Comment
// ==========================================

async function addTicketComment(
    event,
    ticketNumber
) {

    event.preventDefault();


    const authorName =
        document
            .getElementById(
                "commentAuthorName"
            )
            ?.value
            ?.trim() || "";

    const comment =
        document
            .getElementById(
                "ticketCommentText"
            )
            ?.value
            ?.trim() || "";

    const commentButton =
        document.getElementById(
            "addTicketCommentButton"
        );


    if (!authorName || !comment) {

        showTicketMessage(
            "Comment author and comment text are required.",
            "error"
        );

        return;

    }


    if (commentButton) {

        commentButton.disabled = true;

        commentButton.innerHTML = `
            <i class="fa-solid fa-spinner fa-spin mr-2"></i>
            Adding...
        `;

    }


    try {

        await ticketApiRequest(
            `/tickets/${
                encodeURIComponent(
                    ticketNumber
                )
            }/comments`,
            {
                method: "POST",
                body: JSON.stringify({
                    author_name:
                        authorName,

                    comment:
                        comment
                })
            }
        );


        showTicketMessage(
            "Comment added successfully.",
            "success"
        );


        await openTicketDetails(
            ticketNumber
        );

    }

    catch (error) {

        console.error(
            "Add Ticket Comment Error:",
            error
        );

        showTicketMessage(
            error.message,
            "error"
        );

    }

    finally {

        const refreshedCommentButton =
            document.getElementById(
                "addTicketCommentButton"
            );

        if (refreshedCommentButton) {

            refreshedCommentButton.disabled = false;

            refreshedCommentButton.innerHTML = `
                <i class="fa-solid fa-comment mr-2"></i>
                Add Comment
            `;

        }

    }

}


// ==========================================
// Render Ticket Comments
// ==========================================

function renderTicketComments(
    comments
) {

    if (!comments.length) {

        return `
            <div
                class="
                    text-slate-500
                    bg-slate-50
                    rounded-lg
                    p-4
                "
            >
                No comments have been added.
            </div>
        `;

    }


    return comments
        .map(
            function (comment) {

                return `
                    <article
                        class="
                            border
                            border-slate-200
                            rounded-xl
                            p-4
                        "
                    >

                        <div
                            class="
                                flex
                                justify-between
                                gap-4
                                mb-2
                            "
                        >

                            <strong class="text-slate-800">

                                ${
                                    escapeHtml(
                                        comment.author_name ||
                                        "Unknown"
                                    )
                                }

                            </strong>


                            <span class="text-xs text-slate-500">

                                ${
                                    escapeHtml(
                                        formatTicketDate(
                                            comment.created_at
                                        )
                                    )
                                }

                            </span>

                        </div>


                        <p class="text-slate-600 whitespace-pre-wrap">

                            ${
                                escapeHtml(
                                    comment.comment ||
                                    ""
                                )
                            }

                        </p>

                    </article>
                `;

            }
        )
        .join("");

}


// ==========================================
// Badge Helpers
// ==========================================

function createPriorityBadge(
    priority
) {

    const classes = {

        Low:
            "bg-green-100 text-green-700",

        Medium:
            "bg-yellow-100 text-yellow-700",

        High:
            "bg-orange-100 text-orange-700",

        Critical:
            "bg-red-100 text-red-700"

    };


    const badgeClass =
        classes[priority] ||
        "bg-slate-100 text-slate-700";


    return `
        <span
            class="
                inline-flex
                px-3
                py-1
                rounded-full
                text-xs
                font-semibold
                ${badgeClass}
            "
        >
            ${escapeHtml(priority || "Unknown")}
        </span>
    `;

}


function createStatusBadge(
    status
) {

    const classes = {

        Open:
            "bg-blue-100 text-blue-700",

        "In Progress":
            "bg-purple-100 text-purple-700",

        Pending:
            "bg-yellow-100 text-yellow-700",

        Resolved:
            "bg-green-100 text-green-700",

        Closed:
            "bg-slate-200 text-slate-700"

    };


    const badgeClass =
        classes[status] ||
        "bg-slate-100 text-slate-700";


    return `
        <span
            class="
                inline-flex
                px-3
                py-1
                rounded-full
                text-xs
                font-semibold
                ${badgeClass}
            "
        >
            ${escapeHtml(status || "Unknown")}
        </span>
    `;

}


// ==========================================
// Select Option Helpers
// ==========================================

function createStatusOptions(
    selectedStatus
) {

    const statuses = [
        "Open",
        "In Progress",
        "Pending",
        "Resolved",
        "Closed"
    ];


    return statuses
        .map(
            function (status) {

                const selected =
                    status === selectedStatus
                        ? "selected"
                        : "";

                return `
                    <option
                        value="${escapeHtml(status)}"
                        ${selected}
                    >
                        ${escapeHtml(status)}
                    </option>
                `;

            }
        )
        .join("");

}


function createPriorityOptions(
    selectedPriority
) {

    const priorities = [
        "Low",
        "Medium",
        "High",
        "Critical"
    ];


    return priorities
        .map(
            function (priority) {

                const selected =
                    priority ===
                    selectedPriority
                        ? "selected"
                        : "";

                return `
                    <option
                        value="${escapeHtml(priority)}"
                        ${selected}
                    >
                        ${escapeHtml(priority)}
                    </option>
                `;

            }
        )
        .join("");

}


// ==========================================
// Message Helper
// ==========================================

function showTicketMessage(
    message,
    type = "success"
) {

    const messageBox =
        document.getElementById(
            "messageBox"
        );

    if (!messageBox) {

        if (type === "error") {

            console.error(message);

        }

        else {

            console.log(message);

        }

        return;

    }


    messageBox.textContent =
        message;

    messageBox.classList.remove(
        "hidden",
        "bg-green-100",
        "text-green-700",
        "border-green-200",
        "bg-red-100",
        "text-red-700",
        "border-red-200",
        "bg-yellow-100",
        "text-yellow-700",
        "border-yellow-200"
    );


    messageBox.classList.add(
        "border",
        "rounded-lg",
        "p-4",
        "mb-5"
    );


    if (type === "error") {

        messageBox.classList.add(
            "bg-red-100",
            "text-red-700",
            "border-red-200"
        );

    }

    else if (type === "warning") {

        messageBox.classList.add(
            "bg-yellow-100",
            "text-yellow-700",
            "border-yellow-200"
        );

    }

    else {

        messageBox.classList.add(
            "bg-green-100",
            "text-green-700",
            "border-green-200"
        );

    }


    window.setTimeout(
        function () {

            messageBox.classList.add(
                "hidden"
            );

        },
        5000
    );

}


// ==========================================
// Formatting Helpers
// ==========================================

function formatTicketDate(value) {

    if (!value) {
        return "-";
    }


    const parsedDate =
        new Date(value);


    if (
        Number.isNaN(
            parsedDate.getTime()
        )
    ) {

        return String(value);

    }


    return parsedDate.toLocaleString(
        undefined,
        {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        }
    );

}


function updateTextContent(
    elementId,
    value
) {

    const element =
        document.getElementById(
            elementId
        );

    if (element) {

        element.textContent =
            String(value);

    }

}


// ==========================================
// HTML Escaping
// ==========================================

function escapeHtml(value) {

    return String(value ?? "")
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );

}