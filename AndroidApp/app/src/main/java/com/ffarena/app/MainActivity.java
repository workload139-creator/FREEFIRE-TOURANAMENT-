package com.ffarena.app;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final String BASE_URL = "https://freefire-touranament-74nr.onrender.com";
    private static final int BG = Color.rgb(9, 12, 20);
    private static final int PANEL = Color.rgb(20, 26, 39);
    private static final int ORANGE = Color.rgb(255, 126, 35);
    private static final int MUTED = Color.rgb(166, 178, 198);
    private LinearLayout root;
    private LinearLayout content;
    private LinearLayout bottomNav;
    private WebView featureWebView;
    private String currentTab = "Home";

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        showNativeShell();
    }

    private void showNativeShell() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(20), dp(18), dp(20), dp(16));
        header.setOrientation(LinearLayout.HORIZONTAL);

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        TextView logo = text("FF  ARENA", 23, Color.WHITE, true);
        TextView tagline = text("MOBILE ESPORTS ARENA", 10, ORANGE, true);
        brand.addView(logo);
        brand.addView(tagline);
        header.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
        TextView online = text("● LIVE", 12, Color.rgb(100, 245, 170), true);
        header.addView(online);
        root.addView(header);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(16), dp(4), dp(16), dp(18));
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        bottomNav = new LinearLayout(this);
        bottomNav.setPadding(dp(5), dp(8), dp(5), dp(8));
        bottomNav.setBackgroundColor(Color.rgb(14, 18, 28));
        String[] tabs = {"Home", "Matches", "Wallet", "Profile"};
        for (String tab : tabs) {
            Button b = new Button(this);
            b.setAllCaps(false);
            b.setText(tab);
            b.setTextSize(11);
            b.setTextColor(tab.equals(currentTab) ? ORANGE : MUTED);
            b.setBackgroundColor(Color.TRANSPARENT);
            b.setOnClickListener(v -> selectTab(tab));
            bottomNav.addView(b, new LinearLayout.LayoutParams(0, dp(48), 1));
        }
        root.addView(bottomNav);
        setContentView(root);
        renderTab();
    }

    private void selectTab(String tab) {
        currentTab = tab;
        if (featureWebView != null) {
            featureWebView.stopLoading();
            featureWebView.destroy();
            featureWebView = null;
        }
        showNativeShell();
    }

    private void renderTab() {
        content.removeAllViews();
        if ("Home".equals(currentTab)) {
            addHero();
            addSectionTitle("QUICK ACCESS", "Your tournament hub");
            addFeatureCard("Battle Royale", "Solo and squad tournaments", "Explore BR tournaments", "/tournaments/");
            addFeatureCard("VS ARENA", "1v1 • 2v2 • 3v3 • 4v4", "Explore VS matches", "/tournaments/");
            addFeatureCard("Leaderboard", "Check tournament standings and results", "View leaderboard & results", "/tournaments/results/");
            addSectionTitle("PLAYER ZONE", "Everything for your account");
            addActionRow("My registrations", "Track your joined matches", "/tournaments/my-registrations/");
            addActionRow("AI Tournament Assistant", "Get help about FF Arena tournaments", "/assistant/");
        } else if ("Matches".equals(currentTab)) {
            addSectionTitle("TOURNAMENTS", "Find your next match");
            addFeatureCard("All tournaments", "Browse available BR and VS events", "Browse tournaments", "/tournaments/");
            addFeatureCard("My registrations", "See joined tournaments and room updates", "My registrations", "/tournaments/my-registrations/");
            addFeatureCard("Results", "Completed matches and standings", "View results", "/tournaments/results/");
            addActionRow("Free tournaments", "Explore free-to-enter events", "/tournaments/free-tournament/");
        } else if ("Wallet".equals(currentTab)) {
            addSectionTitle("PLAYER WALLET", "Manage your account balance");
            addFeatureCard("Wallet & transactions", "View balance and wallet history", "Open wallet", "/accounts/wallet/");
            addFeatureCard("Add funds", "See available deposit options", "Deposit options", "/accounts/wallet/deposit/");
            addFeatureCard("Withdraw", "Manage withdrawal request and payout details", "Withdrawal options", "/accounts/wallet/withdraw/");
            addNote("Payments and withdrawals are handled by the secure FF Arena account system. Never share your UPI PIN or OTP.");
        } else {
            addSectionTitle("PLAYER PROFILE", "Your FF Arena account");
            addFeatureCard("Login / Register", "Sign in or create your player account", "Open account", "/login/");
            addFeatureCard("My profile", "Profile details and player information", "View profile", "/accounts/profile/");
            addFeatureCard("Edit profile", "Update your player details", "Edit profile", "/accounts/profile/edit/");
            addFeatureCard("Password & settings", "Manage your account settings", "Account settings", "/accounts/settings/");
        }
        if (bottomNav != null) {
            for (int i = 0; i < bottomNav.getChildCount(); i++) {
                Button b = (Button) bottomNav.getChildAt(i);
                String label = b.getText().toString();
                b.setTextColor(label.equals(currentTab) ? ORANGE : MUTED);
            }
        }
    }

    private void addHero() {
        LinearLayout hero = new LinearLayout(this);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setPadding(dp(20), dp(22), dp(20), dp(22));
        hero.setBackground(background(new int[]{Color.rgb(54, 29, 29), Color.rgb(25, 24, 37)}, dp(20), ORANGE));
        TextView eyebrow = text("WELCOME TO THE ARENA", 11, ORANGE, true);
        TextView title = text("Play sharp.\nRise to the top.", 29, Color.WHITE, true);
        title.setPadding(0, dp(8), 0, dp(8));
        TextView sub = text("Discover tournaments, track results and build your player profile.", 14, MUTED, false);
        hero.addView(eyebrow);
        hero.addView(title);
        hero.addView(sub);
        Button browse = button("EXPLORE TOURNAMENTS");
        browse.setOnClickListener(v -> openFeature("/tournaments/"));
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(-1, dp(50));
        bp.topMargin = dp(16);
        hero.addView(browse, bp);
        LinearLayout.LayoutParams hp = new LinearLayout.LayoutParams(-1, -2);
        hp.bottomMargin = dp(22);
        content.addView(hero, hp);
    }

    private void addSectionTitle(String title, String subtitle) {
        TextView t = text(title, 16, Color.WHITE, true);
        TextView s = text(subtitle, 12, MUTED, false);
        s.setPadding(0, dp(3), 0, dp(10));
        content.addView(t);
        content.addView(s);
    }

    private void addFeatureCard(String title, String desc, String action, String route) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(15), dp(16), dp(14));
        card.setBackground(background(new int[]{PANEL, PANEL}, dp(16), Color.rgb(48, 57, 75)));
        TextView t = text(title, 17, Color.WHITE, true);
        TextView d = text(desc, 13, MUTED, false);
        d.setPadding(0, dp(5), 0, dp(12));
        card.addView(t);
        card.addView(d);
        Button b = button(action);
        b.setOnClickListener(v -> openFeature(route));
        card.addView(b, new LinearLayout.LayoutParams(-1, dp(44)));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.bottomMargin = dp(12);
        content.addView(card, p);
    }

    private void addActionRow(String title, String desc, String route) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(dp(15), dp(13), dp(12), dp(13));
        row.setBackground(background(new int[]{PANEL, PANEL}, dp(14), Color.rgb(48, 57, 75)));
        LinearLayout labels = new LinearLayout(this);
        labels.setOrientation(LinearLayout.VERTICAL);
        labels.addView(text(title, 15, Color.WHITE, true));
        TextView d = text(desc, 12, MUTED, false);
        d.setPadding(0, dp(4), 0, 0);
        labels.addView(d);
        row.addView(labels, new LinearLayout.LayoutParams(0, -2, 1));
        TextView arrow = text("›", 28, ORANGE, true);
        row.addView(arrow);
        row.setOnClickListener(v -> openFeature(route));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.bottomMargin = dp(10);
        content.addView(row, p);
    }

    private void addNote(String message) {
        TextView note = text(message, 12, MUTED, false);
        note.setPadding(dp(15), dp(14), dp(15), dp(14));
        note.setBackground(background(new int[]{PANEL, PANEL}, dp(14), Color.rgb(48, 57, 75)));
        content.addView(note);
    }

    private void openFeature(String route) {
        String url = BASE_URL + route;
        root.removeAllViews();
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setBackgroundColor(BG);
        Button back = button("‹  BACK TO FF ARENA");
        back.setOnClickListener(v -> {
            if (featureWebView != null) {
                featureWebView.stopLoading();
                featureWebView.destroy();
                featureWebView = null;
            }
            showNativeShell();
        });
        page.addView(back, new LinearLayout.LayoutParams(-1, dp(48)));
        featureWebView = new WebView(this);
        WebSettings settings = featureWebView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setSupportZoom(false);
        CookieManager.getInstance().setAcceptCookie(true);
        featureWebView.setWebViewClient(new WebViewClient());
        featureWebView.setWebChromeClient(new WebChromeClient());
        featureWebView.loadUrl(url);
        page.addView(featureWebView, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(page, new LinearLayout.LayoutParams(-1, -1));
    }

    private Button button(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(13);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        b.setTextColor(Color.WHITE);
        b.setBackground(background(new int[]{ORANGE, Color.rgb(255, 92, 30)}, dp(12), ORANGE));
        return b;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(size);
        t.setTextColor(color);
        t.setGravity(Gravity.START);
        t.setTypeface(Typeface.DEFAULT, bold ? Typeface.BOLD : Typeface.NORMAL);
        return t;
    }

    private GradientDrawable background(int[] colors, int radius, int strokeColor) {
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.TL_BR, colors);
        d.setCornerRadius(radius);
        d.setStroke(dp(1), strokeColor);
        return d;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    public void onBackPressed() {
        if (featureWebView != null && featureWebView.canGoBack()) {
            featureWebView.goBack();
        } else if (featureWebView != null) {
            featureWebView.stopLoading();
            featureWebView.destroy();
            featureWebView = null;
            showNativeShell();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (featureWebView != null) {
            featureWebView.stopLoading();
            featureWebView.destroy();
            featureWebView = null;
        }
        super.onDestroy();
    }
}
