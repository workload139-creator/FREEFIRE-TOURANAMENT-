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


/* Original synthesized esports UI tones. Audio starts only after the visitor opts in. */
function initializeArenaEffects() {
    const toggle = document.getElementById("ffSoundToggle");
    if (!toggle) return;

    let audioContext = null;
    let enabled = false;
    let lastSoundAt = 0;

    function playTone(kind) {
        if (!enabled) return;
        const now = Date.now();
        if (now - lastSoundAt < 110) return;
        lastSoundAt = now;
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return;
            if (!audioContext) audioContext = new AudioContextClass();
            if (audioContext.state === "suspended") audioContext.resume();

            const start = audioContext.currentTime;
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            const filter = audioContext.createBiquadFilter();
            const settings = kind === "confirm"
                ? { from: 520, to: 880, duration: 0.13, wave: "triangle", volume: 0.045 }
                : kind === "nav"
                ? { from: 330, to: 440, duration: 0.075, wave: "sine", volume: 0.025 }
                : { from: 180, to: 280, duration: 0.10, wave: "square", volume: 0.018 };

            oscillator.type = settings.wave;
            oscillator.frequency.setValueAtTime(settings.from, start);
            oscillator.frequency.exponentialRampToValueAtTime(settings.to, start + settings.duration);
            filter.type = "lowpass";
            filter.frequency.setValueAtTime(2200, start);
            gain.gain.setValueAtTime(0.0001, start);
            gain.gain.exponentialRampToValueAtTime(settings.volume, start + 0.012);
            gain.gain.exponentialRampToValueAtTime(0.0001, start + settings.duration);
            oscillator.connect(filter);
            filter.connect(gain);
            gain.connect(audioContext.destination);
            oscillator.start(start);
            oscillator.stop(start + settings.duration + 0.02);
        } catch (_) {
            // Sound is decorative; the site remains fully usable if audio is unavailable.
        }
    }

    function setEnabled(value) {
        enabled = value;
        toggle.setAttribute("aria-pressed", String(enabled));
        toggle.setAttribute("aria-label", enabled ? "Turn FF Arena sound effects off" : "Enable FF Arena sound effects");
        toggle.classList.toggle("is-on", enabled);
        const label = toggle.querySelector(".ff-sound-label");
        if (label) label.textContent = enabled ? "SOUND ON" : "SOUND OFF";
        const icon = toggle.querySelector(".ff-sound-icon");
        if (icon) icon.textContent = enabled ? "♫" : "♪";
        if (enabled) playTone("confirm");
    }

    toggle.addEventListener("click", () => {
        if (!enabled) {
            if (!audioContext) {
                const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                if (AudioContextClass) audioContext = new AudioContextClass();
            }
            setEnabled(true);
        } else {
            enabled = false;
            setEnabled(false);
        }
    });

    document.addEventListener("click", (event) => {
        if (!enabled || event.defaultPrevented) return;
        const target = event.target.closest("a, button, input[type='submit']");
        if (!target || target === toggle || target.disabled) return;
        if (target.matches("a, button[type='submit'], input[type='submit']")) {
            playTone(target.matches("button[type='submit'], input[type='submit']") ? "confirm" : "nav");
        } else {
            playTone("click");
        }
    }, true);
}
