"use strict";

document.addEventListener("DOMContentLoaded", () => {
    initializeMobileMenu();
    initializeFormSubmission();
    initializeArenaEffects();
    initializeThemeSettings();
    initializeAndroidLiveSync();
});

function initializeMobileMenu() {
    const toggle = document.getElementById("menuToggle");
    const nav = document.getElementById("mainNav");
    if (!toggle || !nav) return;

    const closeMenu = () => {
        nav.classList.remove("nav-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open navigation");
        toggle.textContent = "☰";
    };

    toggle.addEventListener("click", () => {
        const isOpen = nav.classList.toggle("nav-open");
        toggle.setAttribute("aria-expanded", String(isOpen));
        toggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
        toggle.textContent = isOpen ? "✕" : "☰";
    });

    nav.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", closeMenu);
    });

    nav.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", closeMenu);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeMenu();
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 850) closeMenu();
    });
}

function initializeFormSubmission() {
    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!form.checkValidity()) {
                event.preventDefault();
                form.reportValidity();
                return;
            }

            const button = event.submitter;
            if (!button || button.disabled || button.dataset.allowRepeat === "true") return;

            button.dataset.originalText = button.textContent.trim();
            button.disabled = true;
            button.textContent = "Please wait…";

            // Re-enable on browser-side navigation failures or server validation rerenders.
            window.setTimeout(() => {
                if (button.isConnected) {
                    button.disabled = false;
                    button.textContent = button.dataset.originalText || "Submit";
                }
            }, 10000);
        });
    });
}


/* Lightweight opt-in UI sounds only. No background ambience, timers, or large audio buffers. */
function initializeArenaEffects() {
    const toggle = document.getElementById("ffSoundToggle");
    if (!toggle) return;
    let enabled = false;
    let audioContext = null;
    let lastPlayed = 0;

    function playClick(confirm = false) {
        if (!enabled) return;
        const nowMs = Date.now();
        if (nowMs - lastPlayed < 120) return;
        lastPlayed = nowMs;
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        try {
            if (!audioContext) audioContext = new AudioContextClass();
            if (audioContext.state === "suspended") audioContext.resume();
            const now = audioContext.currentTime;
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            oscillator.type = "sine";
            oscillator.frequency.setValueAtTime(confirm ? 680 : 420, now);
            oscillator.frequency.exponentialRampToValueAtTime(confirm ? 920 : 520, now + 0.055);
            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(0.025, now + 0.008);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.075);
            oscillator.connect(gain);
            gain.connect(audioContext.destination);
            oscillator.start(now);
            oscillator.stop(now + 0.08);
        } catch (_) { /* Audio is decorative; never interrupt navigation. */ }
    }

    toggle.addEventListener("click", () => {
        enabled = !enabled;
        toggle.setAttribute("aria-pressed", String(enabled));
        toggle.classList.toggle("is-on", enabled);
        const label = toggle.querySelector(".ff-sound-label");
        const icon = toggle.querySelector(".ff-sound-icon");
        if (label) label.textContent = enabled ? "SOUND ON" : "SOUND OFF";
        if (icon) icon.textContent = enabled ? "🔊" : "♫";
        if (enabled) playClick(true);
    });

    document.addEventListener("click", (event) => {
        if (!enabled || event.defaultPrevented) return;
        const target = event.target.closest("a, button[type='submit'], input[type='submit']");
        if (target && target !== toggle && !target.disabled) playClick(target.matches("button[type='submit'], input[type='submit']"));
    }, true);
}


/* User-selected theme is a visual preference only; it does not change account data. */
function initializeThemeSettings() {
    const root = document.documentElement;
    const allowedThemes = new Set(["arena", "red", "purple", "blue"]);
    let savedTheme = "arena";
    try {
        const stored = window.localStorage.getItem("ff-arena-theme");
        if (stored && allowedThemes.has(stored)) savedTheme = stored;
    } catch (_) { /* Storage may be disabled in private browsing. */ }
    root.dataset.ffTheme = savedTheme;

    const buttons = document.querySelectorAll("[data-theme-choice]");
    const applyTheme = (theme) => {
        if (!allowedThemes.has(theme)) return;
        root.dataset.ffTheme = theme;
        try { window.localStorage.setItem("ff-arena-theme", theme); } catch (_) { /* Theme still works for this page. */ }
        buttons.forEach((button) => {
            const selected = button.dataset.themeChoice === theme;
            button.setAttribute("aria-pressed", String(selected));
            button.classList.toggle("is-selected", selected);
        });
    };
    buttons.forEach((button) => button.addEventListener("click", () => applyTheme(button.dataset.themeChoice)));
    applyTheme(savedTheme);
}


/*
 * The installed APK is a WebView. Poll the public tournament feed every 15 seconds
 * so admin-side tournament changes appear without asking players to reinstall,
 * tap Update, or manually refresh. Never reload over unsaved form input.
 */
function initializeAndroidLiveSync() {
    if (!/FFArenaAndroidApp/i.test(navigator.userAgent || "")) return;

    const endpoint = "/tournaments/api/?limit=50";
    const storageKey = "ff-arena-tournament-snapshot-v1";
    let lastSnapshot = "";
    let checkInProgress = false;
    let refreshPending = false;

    try {
        lastSnapshot = window.sessionStorage.getItem(storageKey) || "";
    } catch (_) { /* Polling still works without storage. */ }

    function hasUnsavedFormData() {
        return Array.from(document.querySelectorAll("form")).some((form) => {
            return Array.from(form.elements).some((field) => {
                if (!field.name || field.disabled || field.type === "submit" || field.type === "button" || field.type === "hidden") return false;
                if (field.type === "file") return Boolean(field.files && field.files.length);
                if (field.type === "checkbox" || field.type === "radio") return field.checked !== field.defaultChecked;
                return field.value !== field.defaultValue;
            });
        });
    }

    function refreshIfSafe() {
        if (!refreshPending || document.visibilityState !== "visible" || hasUnsavedFormData()) return;
        window.location.reload();
    }

    async function checkForAdminChanges() {
        if (checkInProgress || document.visibilityState !== "visible") return;
        checkInProgress = true;
        try {
            const response = await fetch(endpoint, {
                method: "GET",
                cache: "no-store",
                credentials: "same-origin",
                headers: { "Accept": "application/json" }
            });
            if (!response.ok) return;
            const payload = await response.json();
            if (!payload || payload.success !== true || !Array.isArray(payload.results)) return;

            const snapshot = JSON.stringify(payload.results);
            if (lastSnapshot && snapshot !== lastSnapshot) {
                refreshPending = true;
                refreshIfSafe();
            }
            lastSnapshot = snapshot;
            try { window.sessionStorage.setItem(storageKey, snapshot); } catch (_) { /* Non-fatal. */ }
        } catch (_) {
            // A temporary network outage must not interrupt the player's current screen.
        } finally {
            checkInProgress = false;
        }
    }

    // Establish a baseline immediately, then check regularly while the app is open.
    checkForAdminChanges();
    window.setInterval(checkForAdminChanges, 15000);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            if (refreshPending) refreshIfSafe();
            else checkForAdminChanges();
        }
    });
    window.addEventListener("focus", () => {
        if (refreshPending) refreshIfSafe();
        else checkForAdminChanges();
    });
    document.addEventListener("input", refreshIfSafe, true);
    document.addEventListener("change", refreshIfSafe, true);
}
