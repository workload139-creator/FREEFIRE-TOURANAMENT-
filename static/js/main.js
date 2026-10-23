"use strict";

/**
 * FF Tournament
 * Main JavaScript
 */

document.addEventListener("DOMContentLoaded", () => {
    initializeMobileMenu();
    initializeAlerts();
});


/**
 * Mobile navigation menu.
 */
function initializeMobileMenu() {
    const menuToggle = document.getElementById("menuToggle");
    const navLinks = document.getElementById("navLinks");

    if (!menuToggle || !navLinks) {
        return;
    }

    menuToggle.addEventListener("click", () => {
        const isOpen = navLinks.classList.toggle("is-open");

        menuToggle.setAttribute(
            "aria-expanded",
            String(isOpen)
        );

        menuToggle.setAttribute(
            "aria-label",
            isOpen ? "Close navigation" : "Open navigation"
        );

        menuToggle.textContent = isOpen ? "✕" : "☰";
    });

    navLinks.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
            navLinks.classList.remove("is-open");

            menuToggle.setAttribute("aria-expanded", "false");
            menuToggle.setAttribute(
                "aria-label",
                "Open navigation"
            );

            menuToggle.textContent = "☰";
        });
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 768) {
            navLinks.classList.remove("is-open");

            menuToggle.setAttribute("aria-expanded", "false");
            menuToggle.setAttribute(
                "aria-label",
                "Open navigation"
            );

            menuToggle.textContent = "☰";
        }
    });
}


/**
 * Prevent accidental double-clicks on forms.
 * The button is restored if browser validation fails.
 */
function initializeAlerts() {
    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!form.checkValidity()) {
                event.preventDefault();
                form.reportValidity();
                return;
            }

            const submitButton = event.submitter;

            if (!submitButton || submitButton.disabled) {
                return;
            }

            submitButton.dataset.originalText =
                submitButton.textContent;

            submitButton.disabled = true;
            submitButton.textContent = "Please wait...";

            window.setTimeout(() => {
                if (submitButton.isConnected) {
                    submitButton.disabled =
