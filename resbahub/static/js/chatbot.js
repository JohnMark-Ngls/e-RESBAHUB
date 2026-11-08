
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
   
        // New request
        if ((q.includes("request") || q.includes("mag-request")) &&
            (q.includes("submit") || q.includes("new") ||
            q.includes("apply") || q.includes("dokumento"))) {
            return "Para mag-request ng dokumento, pumunta sa New Request, kumpletuhin ang mga kinakailangang impormasyon, at isumite ang iyong kahilingan. Pagkatapos, buksan ang My Requests upang tingnan ang status nito.";
        }

        // Request status
        if (q.includes("request status") || q.includes("track request") ||
            q.includes("my request") || q.includes("approved") ||
            q.includes("rejected") || q.includes("status ng request") ||
            q.includes("kahilingan ko")) {
            return "Pumunta sa My Requests upang makita ang iyong mga naipasa na kahilingan at ang kasalukuyang status ng bawat isa. Makipag-ugnayan sa mga kawani ng barangay kung mayroon kang katanungan.";
        }

        // Free medicines
        if (q.includes("medicine") || q.includes("medication") ||
            q.includes("available drug") || q.includes("gamot") ||
            q.includes("libreng gamot")) {
            return "Pumunta sa Medicine upang makita ang listahan ng mga libreng gamot. Makikita mo rin kung available o ubos na ang stock. Para sa kumpirmasyon at wastong gabay, makipag-ugnayan sa mga kawani ng Health Center.";
        }

        // Account verification
        if (q.includes("verify") || q.includes("verification") ||
            q.includes("pending account") || q.includes("beripikasyon") ||
            q.includes("i-verify") || q.includes("verify account")) {
            return "Kung nakabinbin pa ang beripikasyon ng iyong account, kailangang suriin at kumpirmahin ng mga kawani ng barangay ang impormasyong iyong isinumite. Makipag-ugnayan sa kanila kung nais mong malaman ang update tungkol sa iyong account.";
        }

        // Registration
        if (q.includes("register") || q.includes("magrehistro") ||
            q.includes("gumawa ng account")) {
            return "Para gumawa ng account, pumunta sa Register page at punan ang mga kinakailangang impormasyon. Siguraduhing tama ang iyong mga detalye bago isumite ang registration form.";
        }

        // Announcements
        if (q.includes("announcement") || q.includes("event") ||
            q.includes("schedule") || q.includes("anunsyo")) {
            return "Pumunta sa Announcements upang makita ang mga pinakabagong impormasyon, aktibidad, at iskedyul na inilathala ng mga kawani ng barangay.";
        }

        // Notifications
        if (q.includes("notification") || q.includes("abiso") ||
            q.includes("paunawa")) {
            return "Pumunta sa Notifications upang makita at basahin ang mga abisong ipinadala sa iyong account.";
        }

        // Profile
        if (q.includes("profile") || q.includes("update details") ||
            q.includes("personal information") || q.includes("profile ko") ||
            q.includes("baguhin ang aking profile")) {
            return "Pumunta sa My Profile upang tingnan o i-update ang iyong personal na impormasyon, depende sa mga impormasyong pinapayagan ng system na baguhin.";
        }

        // Password
        if (q.includes("password") || q.includes("nakalimutan ang password") ||
            q.includes("nakalimutan ko ang password")) {
            return "Kung nakalimutan mo ang iyong password, pumunta sa Login page at piliin ang Forgot Password. Ilagay ang iyong rehistradong email address at sundin ang mga tagubilin upang makapag-reset ng password. Huwag ibahagi ang iyong password kaninuman.";
        }

        // Contact barangay
        if (q.includes("contact") || q.includes("personnel") ||
            q.includes("staff") || q.includes("help") ||
            q.includes("tulong") || q.includes("makipag-ugnayan")) {
            return "Para sa beripikasyon ng account, mga katanungan tungkol sa iyong request, o iba pang opisyal na tulong, mangyaring makipag-ugnayan sa tanggapan ng barangay o sa mga kawani ng Health Center.";
        }

        // Pending status
        if (q.includes("ano ang pending") ||
            q.includes("meaning ng pending")) {
            return "Ang Pending ay nangangahulugang natanggap na ng system ang iyong request ngunit hindi pa ito naaaprubahan o napoproseso ng mga kawani ng barangay.";
        }

        // Rejected request
        if (q.includes("bakit rejected") ||
            q.includes("rejected ang request")) {
            return "Kung rejected ang iyong request, tingnan ang mga detalye o dahilan kung mayroon itong nakasaad. Maaari ka ring makipag-ugnayan sa mga kawani ng barangay para malaman kung ano ang dapat gawin.";
        }

        // Login problem
        if (q.includes("hindi makapag-login") ||
            q.includes("login problem") ||
            q.includes("cannot login")) {
            return "Kung hindi ka makapag-login, tiyaking tama ang iyong email address at password. Kung nakalimutan mo ang iyong password, gamitin ang Forgot Password option sa Login page kung available ito. Kung magpapatuloy ang problema, makipag-ugnayan sa system administrator.";
        }

        if (q.includes("anong oras nagbubukas") || q.includes("office hours")) {
            return "Para malaman ang eksaktong oras ng pagbubukas ng Barangay Hall, mangyaring makipag-ugnayan sa mga kawani ng barangay.";
        }

        if (q.includes("barangay health worker") || q.includes("bhw")) {
            return "Maaari kang magtanong sa Barangay Health Center upang makipag-ugnayan sa Barangay Health Worker.";
        }

        if (q.includes("bakuna") || q.includes("vaccination")) {
            return "Para sa impormasyon tungkol sa bakuna, available na schedule, at requirements, mangyaring magtanong sa Barangay Health Center.";
        }

        if (q.includes("maternal health") || q.includes("kalusugan ng buntis")) {
            return "Para sa impormasyon tungkol sa maternal health services, mangyaring makipag-ugnayan sa Barangay Health Center.";
        }

        return "Paumanhin, wala pa akong sagot para sa iyong katanungan. Maaari kang magtanong tungkol sa mga request, beripikasyon ng account, libreng gamot, mga anunsyo, notifications, o iyong profile.";
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
