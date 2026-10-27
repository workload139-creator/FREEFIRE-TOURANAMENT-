from django.shortcuts import render
from django.views.decorators.http import require_http_methods

ANSWERS = [
    (("register", "account", "signup", "sign up"), "Account banane ke liye pehle email OTP verify karein, phir Register page par details bharein."),
    (("email", "otp", "gmail", "code"), "Registration email OTP 6 digits ka hota hai aur 10 minutes mein expire hota hai. Inbox ke saath Spam/Junk folder bhi check karein."),
    (("girl", "girls", "boy", "boys", "gender"), "Profile/Edit Profile mein Boy ya Girl category set karein. Admin tournament banate waqt Open to All, Boys Only, Girls Only ya Girls vs Boys category chunta hai. Boys Only/Girls Only tournaments mein profile category match hona zaroori hai."),
    (("br", "battle royale"), "BR tournaments Tournaments page ke Battle Royale section mein alag dikhte hain. Har card se tournament detail kholo, entry fee, prize pool, player capacity aur status check karo. Registration sirf Upcoming aur non-full tournament mein khulti hai."),
    (("vs", "1v1", "2v2", "3v3", "4v4", "clash squad", "cs tournament"), "CS / Clash Squad tournaments Tournaments page ke alag CS section mein hote hain. Admin 1v1, 2v2, 3v3 ya 4v4 format chunta hai; har event ki fee, status, registration aur leaderboard usi event ke page par hote hain."),
    (("wallet", "deposit", "withdraw", "upi", "payment", "utr"), "Wallet transaction status check karein. Deposit ₹10–₹5,000 ke beech hota hai. Payment UTR ko actual UPI/bank record se match karne ke baad admin credit/entry verify kare. Screenshot ya typed reference apne aap payment proof nahi hai. Winner/refund transfer manually karne ke baad real UTR record karein."),
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
