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


/* Original FF Arena intro voice, looping menu music and UI tones.
   Audio is opt-in and generated in-browser; no official Free Fire recordings are bundled. */
function initializeArenaEffects() {
    const toggle = document.getElementById("ffSoundToggle");
    if (!toggle) return;

    let audioContext = null;
    let enabled = false;
    let musicTimer = null;
    let noteIndex = 0;
    let lastSoundAt = 0;
    let masterGain = null;
    const melody = [110, 164.81, 220, 164.81, 130.81, 196, 261.63, 196,
                    98, 146.83, 196, 146.83, 123.47, 185, 246.94, 185];

    function ensureAudio() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return false;
        if (!audioContext) {
            audioContext = new AudioContextClass();
            masterGain = audioContext.createGain();
            masterGain.gain.value = 0.24;
            masterGain.connect(audioContext.destination);
        }
        if (audioContext.state === "suspended") audioContext.resume();
        return true;
    }

    function tone(frequency, duration, volume, wave, destination, detune) {
        if (!audioContext || !destination) return;
        const start = audioContext.currentTime;
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.type = wave || "sine";
        osc.frequency.setValueAtTime(frequency, start);
        if (detune) osc.detune.setValueAtTime(detune, start);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(Math.max(volume, 0.0002), start + 0.04);
        gain.gain.setValueAtTime(Math.max(volume, 0.0002), start + Math.max(0.05, duration - 0.08));
        gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
        osc.connect(gain);
        gain.connect(destination);
        osc.start(start);
        osc.stop(start + duration + 0.02);
    }

    function playMusicStep() {
        if (!enabled || !audioContext) return;
        const root = melody[noteIndex % melody.length];
        // Soft cinematic synth bass plus a bright, short top note.
        tone(root, 0.62, 0.018, "triangle", masterGain);
        if (noteIndex % 4 === 0) tone(root * 2, 0.22, 0.010, "sine", masterGain);
        if (noteIndex % 8 === 0) tone(root * 0.5, 0.8, 0.012, "sawtooth", masterGain);
        noteIndex += 1;
    }

    function playTone(kind) {
        if (!enabled || !ensureAudio()) return;
        const now = Date.now();
        if (now - lastSoundAt < 110) return;
        lastSoundAt = now;
        const settings = kind === "confirm"
            ? { from: 520, to: 880, duration: 0.15, wave: "triangle", volume: 0.045 }
            : kind === "nav"
            ? { from: 330, to: 440, duration: 0.08, wave: "sine", volume: 0.025 }
            : { from: 180, to: 280, duration: 0.10, wave: "square", volume: 0.018 };
        const start = audioContext.currentTime;
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.type = settings.wave;
        osc.frequency.setValueAtTime(settings.from, start);
        osc.frequency.exponentialRampToValueAtTime(settings.to, start + settings.duration);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(settings.volume, start + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + settings.duration);
        osc.connect(gain);
        gain.connect(masterGain || audioContext.destination);
        osc.start(start);
        osc.stop(start + settings.duration + 0.02);
    }

    function playArenaAnnouncement() {
        if (!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance) return;
        try {
            window.speechSynthesis.cancel();
            const announcement = new SpeechSynthesisUtterance("Welcome to FF Arena. Get ready. Battle begins now!");
            announcement.lang = "en-IN";
            announcement.rate = 0.88;
            announcement.pitch = 0.72;
            announcement.volume = 0.75;
            window.speechSynthesis.speak(announcement);
        } catch (_) {
            // Browser voice support is optional.
        }
    }

    function setEnabled(value) {
        enabled = value;
        toggle.setAttribute("aria-pressed", String(enabled));
        toggle.setAttribute("aria-label", enabled ? "Turn FF Arena music and sound off" : "Enable FF Arena music and sound");
        toggle.classList.toggle("is-on", enabled);
        const label = toggle.querySelector(".ff-sound-label");
        if (label) label.textContent = enabled ? "MUSIC ON" : "MUSIC OFF";
        const icon = toggle.querySelector(".ff-sound-icon");
        if (icon) icon.textContent = enabled ? "♫" : "♪";

        if (enabled) {
            if (!ensureAudio()) {
                enabled = false;
                toggle.setAttribute("aria-pressed", "false");
                if (label) label.textContent = "MUSIC UNSUPPORTED";
                return;
            }
            playTone("confirm");
            playArenaAnnouncement();
            playMusicStep();
            musicTimer = window.setInterval(playMusicStep, 620);
        } else {
            if (musicTimer !== null) window.clearInterval(musicTimer);
            musicTimer = null;
            if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        }
    }

    toggle.addEventListener("click", () => setEnabled(!enabled));

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

    // Browsers may stop audio on navigation; the visitor can re-enable it on the next page.
}
