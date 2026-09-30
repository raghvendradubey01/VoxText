/* VoxText account flows: sign in, sign up, session bootstrap and sign out.
 *
 * The session lives in an HttpOnly cookie set by the server, so this file never
 * sees - and could never store - the token itself.
 */
(function () {
    "use strict";

    const ENDPOINTS = {
        signup: "/api/auth/signup",
        login: "/api/auth/login",
        me: "/api/auth/me",
        logout: "/api/auth/logout"
    };

    function el(id) {
        return document.getElementById(id);
    }

    function showError(text) {
        const box = el("authError");
        if (!box) return;
        box.textContent = text;
        box.classList.remove("hidden");
    }

    function clearError() {
        const box = el("authError");
        if (!box) return;
        box.textContent = "";
        box.classList.add("hidden");
    }

    function setBusy(isBusy) {
        const button = el("authSubmit");
        const label = el("authSubmitLabel");
        const spinner = el("authSpinner");
        if (button) button.disabled = isBusy;
        if (spinner) spinner.classList.toggle("hidden", !isBusy);
        if (label && label.dataset.idle) {
            label.textContent = isBusy ? (label.dataset.busy || "Working...") : label.dataset.idle;
        }
    }

    /** Turn a FastAPI error body into one human-readable line. */
    function describeError(status, payload) {
        const detail = payload && payload.detail;
        if (Array.isArray(detail)) {
            return detail
                .map(function (item) {
                    const field = (item.loc || [])
                        .filter(function (part) { return part !== "body"; })
                        .join(" \u2192 ");
                    return (field ? field + ": " : "") + item.msg;
                })
                .join("  \u2022  ");
        }
        if (typeof detail === "string" && detail.length) return detail;
        return "Something went wrong (HTTP " + status + "). Please try again.";
    }

    async function post(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(body)
        });
        let payload = null;
        try { payload = await response.json(); } catch (ignored) { payload = null; }
        return { ok: response.ok, status: response.status, payload: payload };
    }

    async function submit(endpoint, body) {
        clearError();
        setBusy(true);
        try {
            const result = await post(endpoint, body);
            if (!result.ok) {
                showError(describeError(result.status, result.payload));
                setBusy(false);
                return;
            }
            // Signed in: the server decides where a valid session lands.
            window.location.assign("/");
        } catch (networkError) {
            showError("Could not reach the server. Check your connection and retry.");
            setBusy(false);
        }
    }

    function wirePasswordToggles() {
        document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
            button.addEventListener("click", function () {
                const input = el(button.dataset.togglePassword);
                if (!input) return;
                const revealing = input.type === "password";
                input.type = revealing ? "text" : "password";
                button.textContent = revealing ? "Hide" : "Show";
            });
        });
    }

    function wireLoginForm() {
        const form = el("loginForm");
        if (!form) return;
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            const email = el("loginEmail").value.trim();
            const password = el("loginPassword").value;
            if (!email || !password) {
                showError("Enter both your email and password.");
                return;
            }
            submit(ENDPOINTS.login, { email: email, password: password });
        });
    }

    function wireSignupForm() {
        const form = el("signupForm");
        if (!form) return;
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            const email = el("signupEmail").value.trim();
            const password = el("signupPassword").value;
            const confirmed = el("signupPasswordConfirm").value;

            if (!email) { showError("Enter your email address."); return; }
            if (password.length < 8) {
                showError("Password must be at least 8 characters.");
                return;
            }
            if (password !== confirmed) {
                showError("The two passwords do not match.");
                return;
            }

            const body = { email: email, password: password };
            const fullName = el("signupName").value.trim();
            if (fullName) body.full_name = fullName;
            submit(ENDPOINTS.signup, body);
        });
    }

    async function fetchCurrentUser() {
        try {
            const response = await fetch(ENDPOINTS.me, { credentials: "same-origin" });
            if (response.status === 401) {
                // Cookie missing, expired or revoked.
                window.location.replace("/login");
                return null;
            }
            return response.ok ? await response.json() : null;
        } catch (networkError) {
            return null;
        }
    }

    async function wireAccountWidget() {
        const area = el("accountArea");
        if (!area) return;

        const user = await fetchCurrentUser();
        if (!user) return;

        const emailEl = el("accountEmail");
        if (emailEl) {
            emailEl.textContent = user.full_name || user.email;
            emailEl.title = user.email;
        }
        area.classList.remove("hidden");

        const logoutBtn = el("logoutBtn");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", function () {
                logoutBtn.disabled = true;
                fetch(ENDPOINTS.logout, { method: "POST", credentials: "same-origin" })
                    .then(function () { window.location.assign("/login"); })
                    .catch(function () { window.location.assign("/login"); });
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        const label = el("authSubmitLabel");
        if (label) {
            label.dataset.idle = label.textContent.trim();
            if (el("signupForm")) label.dataset.busy = "Creating account...";
            else if (el("loginForm")) label.dataset.busy = "Signing in...";
        }

        wirePasswordToggles();
        wireLoginForm();
        wireSignupForm();
        wireAccountWidget();
    });
})();
