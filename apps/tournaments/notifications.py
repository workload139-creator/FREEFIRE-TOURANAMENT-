
from urllib.parse import quote


def build_match_start_message(tournament, room_id=None):
    """Create a WhatsApp message for a tournament starting soon."""
    lines = [
        f"🎮 Free Fire Tournament: {tournament.title}",
        "",
        "Match start hone wala hai!",
        f"Start Time: {tournament.start_time:%d %b %Y, %I:%M %p}",
        "",
        "Apni game aur internet connection ready rakhein.",
    ]

    if room_id:
        lines.extend([
            "",
            f"Room ID: {room_id}",
            "Room password sirf eligible players ko secure tareeke se dein.",
        ])

    lines.extend([
        "",
        "Good luck, Booyah! 🏆",
    ])

    return "\n".join(lines)


def build_whatsapp_link(phone_number, message):
    """
    Create a WhatsApp click-to-chat URL.
    Phone number must include country code, digits only.
    This link does not send the message automatically.
    """
    phone = "".join(char for char in str(phone_number) if char.isdigit())

    if not phone:
        raise ValueError("Valid WhatsApp phone number required.")

    return f"https://wa.me/{phone}?text={quote(message)}"
