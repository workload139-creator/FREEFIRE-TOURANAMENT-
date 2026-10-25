from django.shortcuts import render
from django.views.decorators.http import require_http_methods

ANSWERS = [
    (("register", "account", "signup", "sign up"), "Account banane ke liye pehle email OTP verify karein, phir Register page par details bharein."),
    (("email", "otp", "gmail", "code"), "Registration email OTP 6 digits ka hota hai aur 10 minutes mein expire hota hai. Inbox ke saath Spam/Junk folder bhi check karein."),
    (("br", "battle royale"), "BR tournaments Tournaments page ke Battle Royale section mein alag dikhte hain."),
    (("vs", "1v1", "2v2", "3v3", "4v4", "clash squad"), "VS tournaments alag section mein hote hain. Tournament details par format, entry fee aur start time check karein."),
    (("wallet", "deposit", "withdraw", "upi", "payment"), "Wallet transaction status check karein. Payment screenshot ya typed reference se akela automatic credit nahi hona chahiye; verification zaroori hai."),
    (("friend", "friends", "add friend"), "Friends page par player search karke friend request bhej sakte hain."),
    (("chat", "message"), "Private chat ke liye Messages page kholein. Apna password, OTP ya payment PIN kisi ko na bhejein."),
    (("follow", "followers", "following"), "Following/follower feature abhi full rollout mein nahi hai. Friend request aur following alag systems hote hain."),
    (("tick", "verified", "blue tick", "500", "100000", "100,000"), "FF Tick purchase abhi live payment ke liye enabled nahi hai. ₹500 payment ya 1 lakh followers ka claim tabhi valid hoga jab verification aur secure payment flow active ho."),
    (("kill", "kills", "reward", "prize"), "Kill evidence AI sirf suggestion de sakta hai; admin final review ke baad hi reward approve karta hai. Project rules ₹5 per approved kill aur minimum 2 verified kills hain."),
    (("admin", "room id", "password", "room details"), "Room details tournament/admin workflow ke through share hoti hain. Kisi unofficial account ko payment ya password mat dein."),
]

@require_http_methods(["GET", "POST"])
def assistant_view(request):
    question = ""
    answer = ""
    if request.method == "POST":
        question = request.POST.get("question", "").strip()[:500]
        normalized = question.casefold()
        if not question:
            answer = "Apna sawaal likhein, main FF Arena ke features ke baare mein madad karunga."
        else:
            for keywords, response in ANSWERS:
                if any(keyword in normalized for keyword in keywords):
                    answer = response
                    break
            if not answer:
                answer = "Is sawaal ka exact jawab abhi mere help topics mein nahi hai. Email OTP, BR/VS tournaments, wallet, friends/chat ya kill reward ke baare mein poochhein."
    return render(request, "pages/assistant.html", {"question": question, "answer": answer})
