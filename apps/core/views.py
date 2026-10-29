from django.db import DatabaseError, connection
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render

from apps.tournaments.models import Tournament


def home(request):
    now = timezone.now()
    try:
        tournaments = list(
            Tournament.objects.filter(
                Q(status=Tournament.Status.UPCOMING, start_time__gte=now)
                | Q(status=Tournament.Status.LIVE)
            ).order_by("start_time")[:6]
        )
    except DatabaseError:
        # Keep the public homepage available during a temporary database outage.
        tournaments = []
    return render(request, "pages/home.html", {"featured_tournaments": tournaments})


def health_check(request):
    """Lightweight Render health endpoint; never expose internal error details."""
    try:
        connection.ensure_connection()
    except DatabaseError:
        return JsonResponse({"status": "unhealthy", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})



def faq(request):
    """Public FAQ using the site's current documented feature and payment rules."""
    faq_sections = [
        {
            "title": "Accounts & Profile",
            "items": [
                {"question": "How do I create an account?", "answer": "Register using your details and complete email OTP verification when requested. If the email does not arrive, check Spam/Junk and confirm the email address."},
                {"question": "I forgot my password. What should I do?", "answer": "Use the Forgot Password link on the login page and follow the email instructions. Never share your password or OTP with another person."},
                {"question": "Why should my Free Fire UID be correct?", "answer": "Your registered UID is used to identify you for tournament eligibility and result review. Check the UID carefully before joining and follow the evidence requirements shown for that tournament."},
            ],
        },
        {
            "title": "Tournaments & Rewards",
            "items": [
                {"question": "How do I join a tournament?", "answer": "Open Tournaments, choose an event, and read its mode, entry fee, date, eligibility, capacity and rules. Registration is available only when the event is open and has space; complete the displayed verification/payment steps."},
                {"question": "What is the difference between BR and VS/CS?", "answer": "BR means Battle Royale. VS/CS means Clash Squad and may have separate formats such as 1v1, 2v2, 3v3 or 4v4. Check each tournament's own detail page for its format, entry requirements and prize rules."},
                {"question": "How are kill rewards and match results approved?", "answer": "Submit genuine match evidence and the correct UID as requested by the event. Automated/AI review can make mistakes and is advisory; an administrator must complete the final review before a reward is approved. Check the tournament page for the exact reward and minimum requirements."},
                {"question": "When will room ID and password be shared?", "answer": "Room details are intended for eligible registered players through the tournament/admin workflow. Follow the event's readiness instructions and never trust unofficial accounts asking you to pay them."},
            ],
        },
        {
            "title": "Wallet, Payments & Refunds",
            "items": [
                {"question": "What is the wallet deposit limit?", "answer": "The currently documented deposit range is ₹10 to ₹5,000. Availability and verification depend on the wallet flow shown on your account."},
                {"question": "Will my wallet update immediately after a UPI payment?", "answer": "Not necessarily. A QR code, payment screen or screenshot does not prove that money was received. The transaction must be matched against the actual bank/UPI record before it is credited. Keep your UTR/reference for support."},
                {"question": "Is the website wallet a bank account?", "answer": "No. The website wallet is an internal ledger record, not a bank account. Do not treat an on-screen balance as proof that a deposit or payout has settled."},
                {"question": "How do refunds and withdrawals work?", "answer": "Eligibility depends on the event rules, the refund policy and applicable law. Read the Refunds & Withdrawals policy before paying. A payout is complete only after the actual transfer has been made and its reference recorded; do not assume every request is automatic."},
            ],
        },
        {
            "title": "Party Rooms, Chat & Help",
            "items": [
                {"question": "How do I use Party Rooms?", "answer": "Open Party Rooms while logged in, then create or join a room using the available controls. Voice depends on the room membership and LiveKit configuration. If Create/Join shows a server error or voice does not connect, contact support and include the time and action that failed."},
                {"question": "Can I message another player?", "answer": "Use the Messages page for private chat and the available player/community pages for social features. Never share passwords, OTPs, UPI PINs or private payment details in chat."},
                {"question": "Where can I get help with a payment or account issue?", "answer": "Open the Support Centre or email workload139@gmail.com. Include your username, the page/tournament involved and the transaction UTR/reference if relevant. Do not email passwords, OTPs, UPI PINs or API keys."},
            ],
        },
    ]
    return render(request, "pages/faq.html", {"faq_sections": faq_sections})


def support(request):
    """Public support page for players and payment-provider reviewers."""
    return render(request, "pages/support.html")


def _policy_page(request, title, intro, sections):
    return render(request, "pages/policy.html", {
        "policy_title": title,
        "policy_intro": intro,
        "policy_sections": sections,
        "policy_updated": "26 October 2026",
    })


def terms(request):
    return _policy_page(request, "Terms & Conditions",
        "These terms explain the rules for using FF Arena. By using the platform, you agree to follow them.",
        [
            ("1. About this service", [
                "FF Arena is an independent community website for tournament listings, registrations, player profiles, match evidence review and results. It is not owned, operated, sponsored or endorsed by Garena unless a written relationship is expressly announced.",
                "Tournament-specific details—mode, date, entry fee, eligibility, prize calculation, deadlines and dispute process—must be shown before registration and apply alongside these terms."
            ]),
            ("2. Eligibility and legal restrictions", [
                "Paid-entry and real-money prize features are intended only for adults aged 18 or older. Do not participate where paid gaming, entry fees or prizes are prohibited or restricted by applicable law. Users are responsible for checking the rules that apply to their location.",
                "Publishing these terms does not itself make a paid tournament lawful. The operator must obtain suitable legal advice and required approvals before enabling paid entry or cash prizes, including payment-provider approval and any applicable registrations or permissions."
            ]),
            ("3. Accounts and fair conduct", [
                "Provide accurate account details and your own Free Fire UID. Keep credentials private. Impersonation, unauthorised use of another person's payment details, duplicate/fraudulent accounts, hacks, exploits, collusion, harassment and manipulated evidence are prohibited.",
                "Room details may be shared only with eligible registered players. A registration is not confirmed until the required payment and eligibility checks have completed."
            ]),
            ("4. Wallet and payment status", [
                "A website-wallet balance is an internal ledger record, not a bank account or regulated deposit account. A UPI QR code or payment intent only helps initiate a payment; it does not prove receipt, verify settlement or automatically send a payout.",
                "Deposits must be reconciled against the actual receiving bank/UPI record before being credited. Screenshots alone are not proof. Withdrawals and prizes are complete only after the actual transfer has been made and its reference recorded. Do not advertise automatic payments unless an authorised integration actually performs and confirms them."
            ]),
            ("5. Evidence, results and prizes", [
                "Video, screenshots, UID and match records may be reviewed using automated tools and human review. AI output is advisory and can be wrong; an authorised administrator must make the final decision under the published rules.",
                "Prize calculations, minimum qualifying thresholds, rounding, review deadlines and dispute steps must be published before an event. No prize is guaranteed until results are verified and approved."
            ]),
            ("6. Suspensions, errors and changes", [
                "We may pause an event or account to investigate fraud, correct errors, protect users or comply with law. Where practical, affected users will be told the reason and how to request review.",
                "The service may be unavailable or contain errors. Nothing here excludes consumer rights that cannot legally be excluded. Terms may change; material changes should be communicated before they apply to a new paid entry."
            ]),
            ("7. Contact", [
                "Questions or complaints: workload139@gmail.com. Include your username, tournament and transaction reference. Never send passwords, OTPs, UPI PINs or secret API keys."
            ])
        ])


def privacy_policy(request):
    return _policy_page(request, "Privacy Policy",
        "This policy describes the personal information FF Arena may process, how it is used and how to submit a privacy request.",
        [
            ("1. Information collected", [
                "Depending on the features used, information may include username, email, phone number, profile photo, Free Fire UID, UPI ID, voluntarily uploaded UPI QR image, registrations, match videos/screenshots, messages, support requests, payment references and wallet-ledger records.",
                "Hosting and security systems may also create technical logs such as IP address, browser/device details, timestamps, error reports and security events."
            ]),
            ("2. Why information is used", [
                "Information is used to operate accounts, register players, verify payments and eligibility, administer tournaments, review results/evidence, prevent fraud, provide support, maintain accounting records and secure the website.",
                "If AI-assisted review is enabled, submitted match media or selected frames may be sent to the configured AI service for analysis. Do not upload unrelated personal information. AI output is only a proposal and needs human review."
            ]),
            ("3. Service providers and sharing", [
                "Information may be processed by hosting, database, email, AI, moderation or payment providers when needed for enabled features, security or legal compliance. Their own terms and privacy notices may apply.",
                "We do not intentionally display private UPI details, QR images or uploaded match evidence publicly. We do not claim that data is never shared or that a provider is certified unless verified."
            ]),
            ("4. Security and retention", [
                "Reasonable safeguards should be used, but no website or transmission can be guaranteed completely secure. Access to administrative tools and secrets should be restricted.",
                "Records may be retained as needed for service operation, fraud prevention, disputes, legal obligations and accounting. Some transaction records may need to be kept even after account deletion."
            ]),
            ("5. Your requests and children", [
                "To request access, correction or deletion, email workload139@gmail.com from your registered email. We may verify your identity, and may retain records where legally required or needed to resolve a transaction or dispute.",
                "Paid-entry and real-money prize features are intended only for adults aged 18 or older. If you believe a child has submitted personal information, contact support for review. Never include passwords, OTPs or payment secrets in a request."
            ])
        ])


def refund_policy(request):
    return _policy_page(request, "Refund, Cancellation & Withdrawal Policy",
        "This policy explains the intended handling of deposits, tournament cancellations, entry fees and withdrawal requests. Applicable law and event-specific rules take priority where required.",
        [
            ("1. Before paying", [
                "Check the event mode, date, entry fee, eligibility, prize calculation and cancellation rules before registering. Pay only when the recipient and amount match the instructions shown on the site.",
                "A QR code or UPI app opening is not confirmation that FF Arena received money. Keep the transaction reference/UTR for support."
            ]),
            ("2. Deposits and duplicate payments", [
                "Deposits are credited only after matching the actual receiving bank/UPI record. Pending deposits may require manual reconciliation. If you paid but the balance was not updated, email workload139@gmail.com with your username, amount, date/time and UTR; hide unrelated financial details.",
                "Duplicate, mistaken or unrecognised payments will be checked against transaction records. Do not repeatedly pay while a transaction is pending."
            ]),
            ("3. Event cancellation and non-play", [
                "If FF Arena cancels an event or does not run it, eligible entry fees should be returned to the original payment method where supported, or to the internal website wallet only where lawful and clearly disclosed. The event page should state the expected method and timing.",
                "If a player misses a match, fails readiness confirmation, submits incorrect details or breaks published rules, refund eligibility depends on the rules shown before entry and applicable law. Fees or forfeitures must not be invented after payment."
            ]),
            ("4. Withdrawals and prizes", [
                "A withdrawal request is not a completed transfer. It may require verification and administrator review. A payout is complete only after the actual transfer is sent and its reference recorded.",
                "Keep your UPI ID accurate and notify support if it changes. Never share your UPI PIN or OTP. A QR image cannot itself make an automatic transfer."
            ]),
            ("5. Delays and complaints", [
                "Processing may depend on reconciliation, verification, banks and providers. If an event page gives a timeline, refer to it; otherwise contact support for a status update rather than assuming an instant refund.",
                "For a refund or withdrawal complaint, email workload139@gmail.com with your username, event, amount and transaction reference. We will review available records and explain the outcome. Statutory consumer rights remain unaffected."
            ])
        ])


def fair_play(request):
    return _policy_page(request, "Fair Play & Tournament Rules",
        "These baseline rules support consistent reviews. Each tournament may publish additional rules that should be visible before registration.",
        [
            ("1. Identity and eligibility", [
                "Use an account you control and enter your own registered Free Fire UID. Submitted UID and evidence must match the registration. Do not use another player's evidence or payment details without permission.",
                "Paid-entry or real-money prize activity is restricted to adults aged 18 or older and locations where it is lawful."
            ]),
            ("2. Prohibited behaviour", [
                "Hacks, scripts, modified clients, exploits, prohibited teaming/collusion, fake or edited evidence presented as original, harassment, threats, spam and deliberate disruption are prohibited.",
                "Do not publish another user's private phone number, email, UPI ID, QR image, account details or private messages without permission."
            ]),
            ("3. Evidence and review", [
                "Submit genuine, readable evidence from the relevant match. Each event page should state required video, screenshots, UID proof and deadlines.",
                "AI tools can make mistakes. An administrator should inspect evidence and may request clarification. UID mismatch, duplicate evidence or suspected tampering may cause a review hold."
            ]),
            ("4. Reports and appeals", [
                "Report suspected cheating or a result error to workload139@gmail.com with the event name and relevant evidence. Do not threaten or harass other players.",
                "Actions may include result correction, disqualification or account restriction after review. Where practical, the affected player will be told the reason and how to request reconsideration."
            ])
        ])


def about(request):
    return _policy_page(request, "About FF Arena",
        "FF Arena is a community project intended to organise Free Fire tournament listings, registrations, player profiles, match evidence review and results.",
        [
            ("1. Features and payment transparency", [
                "Depending on the current deployment, the site may offer event listings, account tools, community features, internal wallet records and evidence review.",
                "Payment buttons and QR codes do not prove settlement, and internal wallet balances are not bank balances. Deposits require the stated verification process; payouts are manual unless a verified, authorised integration is explicitly active."
            ]),
            ("2. Independent platform notice", [
                "FF Arena is an independent, unofficial platform and is not affiliated with, endorsed by or sponsored by Garena or the Free Fire brand owner unless a written relationship is expressly disclosed. Game names and marks belong to their respective owners.",
                "We do not claim registered-company status, government approval, a payment licence, partnership or certification unless it has been independently verified and expressly published."
            ]),
            ("3. Contact", [
                "Support: workload139@gmail.com. Include your username and relevant event or transaction reference. Never send your password, OTP, UPI PIN or API secret."
            ])
        ])
