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


/* Opt-in original Free Fire-inspired battle ambience: punchy gunfire, distant bursts and UI cues.
   No rainfall and no official Free Fire recordings or copyrighted assets are bundled. */
function initializeArenaEffects() {
    const toggle = document.getElementById("ffSoundToggle");
    if (!toggle) return;

    let audioContext = null;
    let masterGain = null;
    let ambienceTimer = null;
    let enabled = false;
    let resumeNeeded = false;
    let lastSoundAt = 0;
    let noiseBuffer = null;

    function ensureAudio() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return false;
        if (!audioContext) {
            audioContext = new AudioContextClass();
            masterGain = audioContext.createGain();
            masterGain.gain.value = 0.58;
            masterGain.connect(audioContext.destination);
        }
        if (audioContext.state === "suspended") audioContext.resume();
        return true;
    }

    function getNoiseBuffer() {
        if (noiseBuffer || !audioContext) return noiseBuffer;
        const length = audioContext.sampleRate * 3;
        noiseBuffer = audioContext.createBuffer(1, length, audioContext.sampleRate);
        const data = noiseBuffer.getChannelData(0);
        for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * 0.7;
        return noiseBuffer;
    }

    function playGunshot(distant) {
        if (!enabled || !ensureAudio()) return;
        const now = audioContext.currentTime;
        const noise = audioContext.createBufferSource();
        noise.buffer = getNoiseBuffer();
        const band = audioContext.createBiquadFilter();
        band.type = "lowpass";
        band.frequency.setValueAtTime(distant ? 1000 : 2200, now);
        const crack = audioContext.createGain();
        crack.gain.setValueAtTime(0.0001, now);
        crack.gain.exponentialRampToValueAtTime(distant ? 0.075 : 0.18, now + 0.008);
        crack.gain.exponentialRampToValueAtTime(0.0001, now + (distant ? 0.19 : 0.11));
        noise.connect(band);
        band.connect(crack);
        crack.connect(masterGain);
        noise.start(now);
        noise.stop(now + 0.23);

        const thump = audioContext.createOscillator();
        const thumpGain = audioContext.createGain();
        thump.type = "sine";
        thump.frequency.setValueAtTime(distant ? 100 : 75, now);
        thump.frequency.exponentialRampToValueAtTime(35, now + 0.22);
        thumpGain.gain.setValueAtTime(0.0001, now);
        thumpGain.gain.exponentialRampToValueAtTime(distant ? 0.09 : 0.2, now + 0.012);
        thumpGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.26);
        thump.connect(thumpGain);
        thumpGain.connect(masterGain);
        thump.start(now);
        thump.stop(now + 0.28);

        if (distant) {
            const echo = audioContext.createGain();
            echo.gain.value = 0.22;
            const delay = audioContext.createDelay(0.35);
            delay.delayTime.value = 0.16;
            thump.connect(delay);
            delay.connect(echo);
            echo.connect(masterGain);
        }
    }

    function playUI(kind) {
        if (!enabled || !ensureAudio()) return;
        const stamp = Date.now();
        if (stamp - lastSoundAt < 100) return;
        lastSoundAt = stamp;
        const start = audioContext.currentTime;
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.type = kind === "confirm" ? "triangle" : "sine";
        osc.frequency.setValueAtTime(kind === "confirm" ? 620 : 340, start);
        osc.frequency.exponentialRampToValueAtTime(kind === "confirm" ? 980 : 460, start + 0.11);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(kind === "confirm" ? 0.04 : 0.018, start + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.13);
        osc.connect(gain);
        gain.connect(masterGain);
        osc.start(start);
        osc.stop(start + 0.15);
    }

    function scheduleBattleAmbience() {
        if (!enabled) return;
        // Intermittent distant fire, occasional quick bursts, and rare closer shots.
        const wait = 3000 + Math.random() * 6500;
        ambienceTimer = window.setTimeout(() => {
            if (!enabled) return;
            const roll = Math.random();
            if (roll > 0.88) {
                playGunshot(false);
                window.setTimeout(() => { if (enabled) playGunshot(false); }, 170 + Math.random() * 150);
                window.setTimeout(() => { if (enabled) playGunshot(false); }, 360 + Math.random() * 180);
            } else {
                playGunshot(true);
                if (roll > 0.48) window.setTimeout(() => { if (enabled) playGunshot(true); }, 240 + Math.random() * 420);
            }
            scheduleBattleAmbience();
        }, wait);
    }

    function setEnabled(value) {
        enabled = value;
        toggle.setAttribute("aria-pressed", String(enabled));
        toggle.setAttribute("aria-label", enabled ? "Turn battle ambience off" : "Turn battle ambience on");
        toggle.classList.toggle("is-on", enabled);
        const label = toggle.querySelector(".ff-sound-label");
        if (label) label.textContent = enabled ? "BATTLE SOUND ON" : "BATTLE SOUND OFF";
        const icon = toggle.querySelector(".ff-sound-icon");
        if (icon) icon.textContent = enabled ? "🔊" : "♪";

        if (enabled) {
            if (!ensureAudio()) {
                enabled = false;
                toggle.setAttribute("aria-pressed", "false");
                if (label) label.textContent = "AUDIO NOT SUPPORTED";
                return;
            }
            resumeNeeded = false;
            playUI("confirm");
            scheduleBattleAmbience();
            try { sessionStorage.setItem("ffArenaSoundEnabled", "true"); } catch (_) {}
        } else {
            if (ambienceTimer !== null) window.clearTimeout(ambienceTimer);
            ambienceTimer = null;
            try { sessionStorage.setItem("ffArenaSoundEnabled", "false"); } catch (_) {}
        }
    }

    toggle.addEventListener("click", () => {
        if (resumeNeeded && !enabled) {
            resumeNeeded = false;
            setEnabled(true);
            return;
        }
        setEnabled(!enabled);
    });

    document.addEventListener("click", (event) => {
        if (!enabled || event.defaultPrevented) return;
        const target = event.target.closest("a, button, input[type='submit']");
        if (!target || target === toggle || target.disabled) return;
        if (target.matches("a, button[type='submit'], input[type='submit']")) {
            playUI(target.matches("button[type='submit'], input[type='submit']") ? "confirm" : "nav");
        } else {
            playUI("click");
        }
    }, true);

    // Remember preference across page navigation. Browsers may require one click again after reload.
    try {
        if (sessionStorage.getItem("ffArenaSoundEnabled") === "true") {
            resumeNeeded = true;
            toggle.classList.add("sound-ready");
            const label = toggle.querySelector(".ff-sound-label");
            if (label) label.textContent = "CLICK TO RESUME SOUND";
        }
    } catch (_) {}
}
