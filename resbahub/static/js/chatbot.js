
document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("chatbot-toggle");
    const windowBox = document.getElementById("chatbot-window");
    const close = document.getElementById("chatbot-close");
    const form = document.getElementById("chatbot-form");
    const input = document.getElementById("chatbot-input");
    const messages = document.getElementById("chatbot-messages");
    const suggestionButtons = document.querySelectorAll(".chatbot-suggestion");

    if (!toggle || !windowBox || !form || !input || !messages) {
        console.error("Chatbot elements are missing from base.html.");
        return;
    }

    function openChat() {
        windowBox.classList.add("open");
        windowBox.setAttribute("aria-hidden", "false");
        toggle.setAttribute("aria-expanded", "true");
        input.focus();
    }

    function closeChat() {
        windowBox.classList.remove("open");
        windowBox.setAttribute("aria-hidden", "true");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
    }

    toggle.addEventListener("click", function () {
        if (windowBox.classList.contains("open")) {
            closeChat();
        } else {
            openChat();
        }
    });

    if (close) {
        close.addEventListener("click", closeChat);
    }

    function addMessage(text, sender) {
        const message = document.createElement("div");
        message.className = "chatbot-message " + sender;
        message.textContent = text;
        messages.appendChild(message);
        messages.scrollTop = messages.scrollHeight;
    }

    function getReply(question) {
        const q = question.toLowerCase();

        if (q.includes("hello") || q === "hi" ||
            q.includes("hi ") || q.includes("good morning") ||
            q.includes("good afternoon")) {
            return "Hello! How can I help you with e-RESBAHUB today?";
        }

        if (q.includes("verify") || q.includes("verification") ||
            q.includes("pending account")) {
            return "If your account is pending verification, barangay personnel must verify your submitted details. Please contact barangay personnel if you need an update.";
        }

        if (q.includes("request") && (q.includes("submit") || q.includes("new") || q.includes("apply"))) {
            return "Open New Request from the sidebar, complete the required information, and submit the form. Then open My Requests to check the status.";
        }

        if (q.includes("request status") || q.includes("track request") ||
            q.includes("my request") || q.includes("approved") ||
            q.includes("rejected")) {
            return "Open My Requests to check your submitted requests and their current status. Contact barangay personnel if you need clarification.";
        }

        if (q.includes("medicine") || q.includes("medication") ||
            q.includes("available drug")) {
            return "Open Medicines to view the medicine information listed in the system. Please confirm stock and suitability with Health Center staff.";
        }

        if (q.includes("announcement") || q.includes("event") ||
            q.includes("schedule")) {
            return "Open Announcements in the sidebar to check the latest information posted by barangay personnel.";
        }

        if (q.includes("notification")) {
            return "Open Notifications in the sidebar to review the notifications available to your account.";
        }

        if (q.includes("profile") || q.includes("update details") ||
            q.includes("personal information")) {
            return "Open My Profile to review or update the personal information your account allows you to change.";
        }

        if (q.includes("password")) {
            return "If you forgot your password, please contact the barangay system administrator for assistance in recovering your account. For your security, never share your password with anyone. If a password reset option is available on the login page, you may use it to reset your password.";
        }

        if (q.includes("contact") || q.includes("personnel") ||
            q.includes("staff") || q.includes("help")) {
            return "For account verification, request concerns, or official assistance, please contact the barangay office or Health Center staff.";
        }

        if (q.includes("diagnosis") || q.includes("symptom") ||
            q.includes("what medicine") || q.includes("dosage")) {
            return "I cannot diagnose conditions or recommend medicines or dosages. Please consult a qualified healthcare professional or your Health Center.";
        }

        return "I'm sorry, I don't have an answer for that yet. Try asking about requests, account verification, medicines, announcements, or your profile.";
    }

    function sendMessage(question) {
        question = question.trim();

        if (!question) {
            return;
        }

        addMessage(question, "user");

        const reply = getReply(question);

        input.value = "";
        input.focus();

        window.setTimeout(function () {
            addMessage(reply, "bot");
        }, 250);
    }

    form.addEventListener("submit", function (event) {
        event.preventDefault();

        sendMessage(input.value);
    });

    // Make each suggested question work immediately.
    suggestionButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            sendMessage(button.textContent);
        });
    });
});
