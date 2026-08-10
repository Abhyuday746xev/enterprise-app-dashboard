// ===========================================
// Enterprise Dashboard
// ===========================================

console.log("APP.JS LOADED");

document.addEventListener("DOMContentLoaded", async function () {

    console.log("Enterprise Dashboard Loaded");

    initializeDashboard();

    await loadDashboard();

});


// ===========================================
// Dashboard Initialization
// ===========================================

function initializeDashboard() {

    setupSyncButton();

    setupEnterpriseAI();

}


// ===========================================
// Load Dashboard Data
// ===========================================

async function loadDashboard() {

    try {

        const [
            applications,
            users,
            devices
        ] = await Promise.all([

            getApplications(),

            getUsers(),

            getDevices()

        ]);

        console.log("Applications:", applications);
        console.log("Users:", users);
        console.log("Devices:", devices);

        updateStatistics(
            applications,
            users,
            devices
        );

        updateInsights(applications);

    }

    catch (error) {

        console.error(
            "Dashboard Loading Error:",
            error
        );

    }

}


// ===========================================
// Dashboard Statistics
// ===========================================

function updateStatistics(
    applications,
    users,
    devices
) {

    const totalApps =
        document.getElementById("totalApps");

    const totalUsers =
        document.getElementById("totalUsers");

    const totalDevices =
        document.getElementById("totalDevices");

    const lastSync =
        document.getElementById("lastSync");


    if (totalApps) {

        totalApps.textContent =
            applications.length;

    }


    if (totalUsers) {

        totalUsers.textContent =
            users.length;

    }


    if (totalDevices) {

        totalDevices.textContent =
            devices.length;

    }


    if (lastSync) {

        lastSync.textContent =
            new Date().toLocaleTimeString();

    }

}


// ===========================================
// Dashboard Insights
// ===========================================

function updateInsights(applications) {

    const largestAppElement =
        document.getElementById("largestApp");

    const largestSizeElement =
        document.getElementById("largestSize");

    const topPublisherElement =
        document.getElementById("topPublisher");

    const publisherCountElement =
        document.getElementById("publisherCount");

    const totalStorageElement =
        document.getElementById("totalStorage");

    const averageSizeElement =
        document.getElementById("averageSize");


    if (!applications.length) {

        if (largestAppElement) {
            largestAppElement.textContent = "--";
        }

        if (largestSizeElement) {
            largestSizeElement.textContent = "--";
        }

        if (topPublisherElement) {
            topPublisherElement.textContent = "--";
        }

        if (publisherCountElement) {
            publisherCountElement.textContent = "--";
        }

        if (totalStorageElement) {
            totalStorageElement.textContent = "--";
        }

        if (averageSizeElement) {
            averageSizeElement.textContent = "--";
        }

        return;

    }


    // ---------------------------------------
    // Largest Application
    // ---------------------------------------

    const largestApplication =
        applications.reduce(
            function (currentLargest, application) {

                const currentSize =
                    Number(
                        currentLargest.size || 0
                    );

                const applicationSize =
                    Number(
                        application.size || 0
                    );

                return applicationSize > currentSize
                    ? application
                    : currentLargest;

            }
        );


    if (largestAppElement) {

        largestAppElement.textContent =
            largestApplication.display_name ||
            "Unknown";

    }


    if (largestSizeElement) {

        largestSizeElement.textContent =
            formatSize(
                largestApplication.size
            );

    }


    // ---------------------------------------
    // Top Publisher
    // ---------------------------------------

    const publishers = {};

    applications.forEach(
        function (application) {

            const publisher =
                application.publisher ||
                "Unknown";

            publishers[publisher] =
                (publishers[publisher] || 0) + 1;

        }
    );


    let topPublisher = "Unknown";
    let highestCount = 0;

    Object.entries(publishers).forEach(
        function ([publisher, count]) {

            if (count > highestCount) {

                topPublisher = publisher;
                highestCount = count;

            }

        }
    );


    if (topPublisherElement) {

        topPublisherElement.textContent =
            topPublisher;

    }


    if (publisherCountElement) {

        publisherCountElement.textContent =
            `${highestCount} ${
                highestCount === 1
                    ? "Application"
                    : "Applications"
            }`;

    }


    // ---------------------------------------
    // Storage Statistics
    // ---------------------------------------

    const totalBytes =
        applications.reduce(
            function (total, application) {

                return (
                    total +
                    Number(
                        application.size || 0
                    )
                );

            },
            0
        );


    if (totalStorageElement) {

        totalStorageElement.textContent =
            formatSize(totalBytes);

    }


    if (averageSizeElement) {

        const averageBytes =
            totalBytes / applications.length;

        averageSizeElement.textContent =
            formatSize(averageBytes);

    }

}


// ===========================================
// Sync Button
// ===========================================

function setupSyncButton() {

    const syncButton =
        document.getElementById("syncButton");

    if (!syncButton) {

        console.warn(
            "Sync button was not found."
        );

        return;

    }


    syncButton.addEventListener(
        "click",
        async function () {

            syncButton.disabled = true;

            syncButton.innerHTML = `
                <i class="fa-solid fa-rotate fa-spin mr-2"></i>
                Syncing...
            `;


            try {

                const result =
                    await syncApplications();

                console.log(
                    "Synchronization Result:",
                    result
                );


                if (!result.success) {

                    throw new Error(
                        result.message ||
                        "Synchronization failed."
                    );

                }


                await loadDashboard();


                syncButton.innerHTML = `
                    <i class="fa-solid fa-check mr-2"></i>
                    Sync Complete
                `;

            }

            catch (error) {

                console.error(
                    "Synchronization Error:",
                    error
                );

                syncButton.innerHTML = `
                    <i class="fa-solid fa-triangle-exclamation mr-2"></i>
                    Sync Failed
                `;

            }


            window.setTimeout(
                function () {

                    syncButton.innerHTML = `
                        <i class="fa-solid fa-rotate mr-2"></i>
                        Sync Dashboard
                    `;

                    syncButton.disabled = false;

                },
                2000
            );

        }
    );

}


// ===========================================
// Enterprise AI Initialization
// ===========================================

function setupEnterpriseAI() {

    const openAiButton =
        document.getElementById("openAiButton");

    const closeAiButton =
        document.getElementById("closeAiButton");

    const clearAiButton =
        document.getElementById("clearAiButton");

    const aiChatWindow =
        document.getElementById("aiChatWindow");

    const aiChatForm =
        document.getElementById("aiChatForm");

    const aiMessages =
        document.getElementById("aiMessages");

    const aiQuestionInput =
        document.getElementById("aiQuestionInput");

    const aiSendButton =
        document.getElementById("aiSendButton");

    const quickQuestionButtons =
        document.querySelectorAll(
            ".ai-quick-question"
        );


    if (
        !openAiButton ||
        !aiChatWindow ||
        !aiChatForm ||
        !aiMessages ||
        !aiQuestionInput ||
        !aiSendButton
    ) {

        console.warn(
            "Enterprise AI elements were not found."
        );

        return;

    }


    // =======================================
    // Open and Close Chat
    // =======================================

    function openAiChat() {

        aiChatWindow.classList.add(
            "ai-chat-visible"
        );

        aiChatWindow.setAttribute(
            "aria-hidden",
            "false"
        );

        openAiButton.setAttribute(
            "aria-expanded",
            "true"
        );

        openAiButton.classList.add(
            "ai-button-active"
        );

        window.setTimeout(
            function () {

                aiQuestionInput.focus();

            },
            200
        );

    }


    function closeAiChat() {

        aiChatWindow.classList.remove(
            "ai-chat-visible"
        );

        aiChatWindow.setAttribute(
            "aria-hidden",
            "true"
        );

        openAiButton.setAttribute(
            "aria-expanded",
            "false"
        );

        openAiButton.classList.remove(
            "ai-button-active"
        );

    }


    function toggleAiChat() {

        const isOpen =
            aiChatWindow.classList.contains(
                "ai-chat-visible"
            );

        if (isOpen) {

            closeAiChat();

        }

        else {

            openAiChat();

        }

    }


    openAiButton.addEventListener(
        "click",
        toggleAiChat
    );


    if (closeAiButton) {

        closeAiButton.addEventListener(
            "click",
            closeAiChat
        );

    }


    // =======================================
    // Message Helpers
    // =======================================

    function scrollMessagesToBottom() {

        aiMessages.scrollTop =
            aiMessages.scrollHeight;

    }


    function getSourceLabel(source) {

        const metadata =
            source?.metadata || {};

        return (
            metadata.name ||
            metadata.email ||
            metadata.device_name ||
            metadata.display_name ||
            source?.type ||
            "Enterprise record"
        );

    }


    function createMessageElement(
        role,
        text,
        sources = []
    ) {

        const message =
            document.createElement("div");

        message.className =
            role === "user"
                ? "ai-message ai-user-message"
                : "ai-message ai-assistant-message";


        if (role === "assistant") {

            const avatar =
                document.createElement("div");

            avatar.className =
                "ai-message-avatar";

            avatar.innerHTML = `
                <i class="fa-solid fa-robot"></i>
            `;

            message.appendChild(avatar);

        }


        const body =
            document.createElement("div");

        body.className =
            "ai-message-body";


        const name =
            document.createElement("div");

        name.className =
            "ai-message-name";

        name.textContent =
            role === "user"
                ? "You"
                : "Enterprise AI";


        const bubble =
            document.createElement("div");

        bubble.className =
            "ai-message-bubble";

        bubble.textContent =
            text || "No message was generated.";


        body.appendChild(name);
        body.appendChild(bubble);


        if (
            role === "assistant" &&
            Array.isArray(sources) &&
            sources.length > 0
        ) {

            const sourceContainer =
                document.createElement("div");

            sourceContainer.className =
                "ai-source-container";


            const sourceHeading =
                document.createElement("div");

            sourceHeading.className =
                "ai-source-heading";

            sourceHeading.textContent =
                "Sources";


            const sourceList =
                document.createElement("div");

            sourceList.className =
                "ai-source-list";


            const uniqueSources =
                new Set();


            sources.forEach(
                function (source) {

                    const label =
                        getSourceLabel(source);

                    if (
                        !label ||
                        uniqueSources.has(label)
                    ) {

                        return;

                    }

                    uniqueSources.add(label);


                    const badge =
                        document.createElement(
                            "span"
                        );

                    badge.className =
                        "ai-source-badge";

                    badge.textContent =
                        label;

                    sourceList.appendChild(
                        badge
                    );

                }
            );


            if (sourceList.children.length > 0) {

                sourceContainer.appendChild(
                    sourceHeading
                );

                sourceContainer.appendChild(
                    sourceList
                );

                body.appendChild(
                    sourceContainer
                );

            }

        }


        message.appendChild(body);

        return message;

    }


    function addAiMessage(
        role,
        text,
        sources = []
    ) {

        const message =
            createMessageElement(
                role,
                text,
                sources
            );

        aiMessages.appendChild(message);

        scrollMessagesToBottom();

        return message;

    }


    // =======================================
    // Typing Indicator
    // =======================================

    function createTypingIndicator() {

        const message =
            document.createElement("div");

        message.className =
            "ai-message ai-assistant-message ai-typing-message";


        const avatar =
            document.createElement("div");

        avatar.className =
            "ai-message-avatar";

        avatar.innerHTML = `
            <i class="fa-solid fa-robot"></i>
        `;


        const body =
            document.createElement("div");

        body.className =
            "ai-message-body";


        const name =
            document.createElement("div");

        name.className =
            "ai-message-name";

        name.textContent =
            "Enterprise AI";


        const bubble =
            document.createElement("div");

        bubble.className =
            "ai-message-bubble ai-typing-bubble";

        bubble.innerHTML = `
            <span class="ai-typing-dot"></span>
            <span class="ai-typing-dot"></span>
            <span class="ai-typing-dot"></span>
        `;


        body.appendChild(name);
        body.appendChild(bubble);

        message.appendChild(avatar);
        message.appendChild(body);

        return message;

    }


    // =======================================
    // Loading State
    // =======================================

    function setAiLoading(isLoading) {

        aiQuestionInput.disabled =
            isLoading;

        aiSendButton.disabled =
            isLoading;


        aiSendButton.innerHTML =
            isLoading
                ? `
                    <i class="fa-solid fa-spinner fa-spin"></i>
                `
                : `
                    <i class="fa-solid fa-paper-plane"></i>
                `;

    }


    // =======================================
    // Send Question
    // =======================================

    async function sendAiQuestion(question) {

        const cleanedQuestion =
            String(question || "").trim();


        if (!cleanedQuestion) {

            return;

        }


        openAiChat();

        addAiMessage(
            "user",
            cleanedQuestion
        );

        aiQuestionInput.value = "";

        resizeAiTextarea();

        setAiLoading(true);


        const typingIndicator =
            createTypingIndicator();

        aiMessages.appendChild(
            typingIndicator
        );

        scrollMessagesToBottom();


        try {

            const result =
                await askEnterpriseAI(
                    cleanedQuestion
                );


            typingIndicator.remove();


            if (!result.success) {

                addAiMessage(
                    "assistant",
                    result.answer ||
                    "Enterprise AI request failed."
                );

                return;

            }


            addAiMessage(
                "assistant",
                result.answer ||
                "No answer was generated.",
                result.sources || []
            );

        }

        catch (error) {

            console.error(
                "Enterprise AI Chat Error:",
                error
            );


            typingIndicator.remove();


            addAiMessage(
                "assistant",
                "An unexpected error occurred while contacting Enterprise AI."
            );

        }

        finally {

            setAiLoading(false);

            aiQuestionInput.focus();

        }

    }


    // =======================================
    // Chat Form
    // =======================================

    aiChatForm.addEventListener(
        "submit",
        async function (event) {

            event.preventDefault();

            await sendAiQuestion(
                aiQuestionInput.value
            );

        }
    );


    // =======================================
    // Enter Key Support
    // =======================================

    aiQuestionInput.addEventListener(
        "keydown",
        async function (event) {

            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {

                event.preventDefault();

                await sendAiQuestion(
                    aiQuestionInput.value
                );

            }

        }
    );


    // =======================================
    // Auto Resize Textarea
    // =======================================

    function resizeAiTextarea() {

        aiQuestionInput.style.height =
            "auto";

        aiQuestionInput.style.height =
            `${Math.min(
                aiQuestionInput.scrollHeight,
                120
            )}px`;

    }


    aiQuestionInput.addEventListener(
        "input",
        resizeAiTextarea
    );


    // =======================================
    // Quick Questions
    // =======================================

    quickQuestionButtons.forEach(
        function (button) {

            button.addEventListener(
                "click",
                async function () {

                    const question =
                        button.dataset.question;

                    await sendAiQuestion(
                        question
                    );

                }
            );

        }
    );


    // =======================================
    // Clear Chat
    // =======================================

    if (clearAiButton) {

        clearAiButton.addEventListener(
            "click",
            function () {

                aiMessages.innerHTML = "";

                addAiMessage(
                    "assistant",
                    "Chat cleared. Ask me about enterprise applications, users, or managed devices."
                );

                aiQuestionInput.focus();

            }
        );

    }


    // =======================================
    // Escape Key Closes Chat
    // =======================================

    document.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key === "Escape" &&
                aiChatWindow.classList.contains(
                    "ai-chat-visible"
                )
            ) {

                closeAiChat();

            }

        }
    );

}