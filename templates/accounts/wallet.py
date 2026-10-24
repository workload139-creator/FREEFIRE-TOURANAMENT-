
{% extends "base.html" %}

{% block content %}
<section style="max-width:900px; margin:40px auto; padding:20px;">
    <h1>My Wallet</h1>

    <div style="padding:24px; border-radius:16px; background:#171923; color:white;">
        <p>Available Balance</p>
        <h2>₹{{ wallet.balance }}</h2>
        <p>Deposit aur withdrawal features agle step mein jodenge.</p>
    </div>

    <h2 style="margin-top:30px;">Transaction History</h2>

    {% for transaction in transactions %}
        <div style="padding:15px; margin:10px 0; border:1px solid #ddd; border-radius:10px;">
            <strong>{{ transaction.get_transaction_type_display }}</strong>
            <p>Amount: ₹{{ transaction.amount }}</p>
            <p>Status: {{ transaction.get_status_display }}</p>
            <small>{{ transaction.created_at|date:"d M Y, h:i A" }}</small>
            {% if transaction.description %}
                <p>{{ transaction.description }}</p>
            {% endif %}
        </div>
    {% empty %}
        <p>Abhi koi transaction nahi hai.</p>
    {% endfor %}
</section>
{% endblock %}
