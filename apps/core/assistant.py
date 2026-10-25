from django.shortcuts import render
from django.views.decorators.http import require_http_methods


# Simple, transparent FAQ assistant. Put specific intents before broad keywords.
ANSWERS = [
    (("hello", "hi", "hey", "hii", "namaste", "namaskar", "good morning", "good evening", "good afternoon"),
     "Hello! 👋 FF Arena mein swagat hai. Batao, tournament join karna hai, login/password reset karna hai, OTP issue hai, ya wallet/chat ke baare mein poochna hai?"),
    (("login", "log in", "sign in", "login nahi", "log in nahi"),
     "Login ke liye wahi username/email aur password use karo jo account banate waqt set kiya tha. Password yaad nahi hai to 'Forgot password' se registered email par reset link mangao. Email na aaye to Spam/Junk aur Render ke email settings/logs check karne honge."),
    (("forgot password", "password reset", "reset password", "password bhool", "password bhul", "password nahi", "password change"),
     "Password reset ke liye Login page par 'Forgot password' kholo aur account ka registered email daalo. Inbox ke saath Spam/Junk bhi dekho. Link nahi aata to SMTP settings ya Render logs mein error check karna hoga; email service fail hone par reset link nahi bheja ja sakta."),
    (("otp", "verification code", "verify code", "email verify", "email verification", "code nahi", "code nahi aa"),
     "Email OTP 6 digits ka hai aur 10 minutes tak valid hai. Pehle email spelling check karo, phir Inbox, Spam/Junk aur Promotions dekho. 60 seconds se pehle resend nahi hoga. Agar phir bhi nahi aata, Render mein EMAIL_HOST, EMAIL_PORT=587, EMAIL_USE_TLS=True, EMAIL_HOST_USER (Brevo SMTP login), EMAIL_HOST_PASSWORD (Brevo SMTP key) aur DEFAULT_FROM_EMAIL (verified sender) check karo. SMTP key/password yahan chat mein mat bhejna."),
    (("register", "registration", "account", "signup", "sign up", "account banao"),
     "Naya account banane ke liye pehle Email OTP verify karo. Uske baad Register page par wahi verified email aur baaki details bharo. Agar email pehle se account mein hai to naya account banane ke bajay Login/Forgot password use karo."),
    (("br", "battle royale"),
     "BR tournament dekhne ke liye Tournaments page kholo aur Battle Royale section dekho. Join karne se pehle entry fee, start time aur rules check karo."),
    (("vs", "1v1", "2v2", "3v3", "4v4", "clash squad"),
     "VS tournaments Tournaments page ke VS section mein alag dikhte hain. Tournament detail mein format, entry fee aur start time check karo."),
    (("wallet", "deposit", "withdraw", "upi", "payment", "balance"),
     "Wallet page par balance aur transaction status dekho. Deposit request admin verification ke baad credit hoti hai; withdrawal request ka status bhi wallet mein check karo. Payment screenshot se automatic payment verify nahi maana jana chahiye."),
    (("friend", "friends", "add friend", "friend request"),
     "Friends page par player search karke friend request bhejo. Private message ke liye Messages/Chat page kholo."),
    (("chat", "message", "messages", "baat kar"),
     "Private chat ke liye Messages/Chat page kholo. Apna password, OTP, SMTP key ya payment PIN kisi ko share mat karo."),
    (("follow", "followers", "following"),
     "Profile par Followers aur Following counts/links dekho. Follow karna friend request se alag hai."),
    (("tick", "verified badge", "blue tick", "500", "100000", "100,000"),
     "FF Tick purchase/automatic verification tabhi valid hogi jab secure payment aur eligibility verification live ho. Abhi is feature ko live payment ke liye enabled na samjho."),
    (("kill", "kills", "reward", "prize"),
     "Kill reward ka proposed rate ₹5 per approved kill hai. Submitted video/screenshots ko final proof na maano—admin ko UID aur evidence review karke reward confirm karna chahiye."),
    (("admin", "room id", "room password", "room details"),
     "Tournament room details admin ke tournament workflow se share honi chahiye. Room ID/password sirf confirmed participants ko dena chahiye."),
    (("error", "internal server error", "500", "server error", "website nahi chal"),
     "Internal Server Error ko theek karne ke liye Render dashboard → tumhari service → Logs kholo aur latest red traceback/error dekho. Password, API key, OTP ya secret hide karke error ki last 10–20 lines share karo; bina logs ke exact cause confirm nahi kiya ja sakta."),
]


def assistant_answer(question):
    normalized = " ".join(question.casefold().replace("?", " ").replace("!", " ").split())
    if not normalized:
        return "Apna sawaal likho—main FF Arena ke login, OTP, tournaments, wallet, friends aur chat mein madad karunga."

    # Exact short greetings should not be mistaken for unrelated keywords.
    greeting_words = {"hello", "hi", "hey", "hii", "namaste", "namaskar", "good morning", "good evening", "good afternoon"}
    if normalized in greeting_words:
        return ANSWERS[0][1]

    for keywords, response in ANSWERS[1:]:
        if any(keyword in normalized for keyword in keywords):
            return response

    return ("Main tumhara sawaal poori tarah match nahi kar paaya. Thoda detail mein batao—"
            "jaise 'OTP nahi aa raha', 'password reset link nahi aaya', 'login error', "
            "'tournament join' ya 'wallet deposit'. Main andaza laga kar galat jawab nahi dena chahta.")


@require_http_methods(["GET", "POST"])
def assistant_view(request):
    question = ""
    answer = ""
    if request.method == "POST":
        question = request.POST.get("question", "").strip()[:500]
        answer = assistant_answer(question)
    return render(request, "pages/assistant.html", {"question": question, "answer": answer})
