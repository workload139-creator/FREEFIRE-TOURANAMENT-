"use strict";

document.addEventListener("DOMContentLoaded", () => {
    initializeMobileMenu();
    initializeFormSubmission();
    initializeArenaEffects();
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
