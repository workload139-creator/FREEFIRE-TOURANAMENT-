package com.ffarena.app;

import android.Manifest;
import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.PermissionRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ImageView;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final String BASE_URL = "https://freefire-touranament-74nr.onrender.com";
    private static final int BG = Color.rgb(9, 12, 20);
    private static final int PANEL = Color.rgb(20, 26, 39);
    private static final int ORANGE = Color.rgb(255, 126, 35);
    private static final int MUTED = Color.rgb(166, 178, 198);
    private LinearLayout root;
    private LinearLayout content;
    private LinearLayout bottomNav;
    private LinearLayout tournamentResults;
    private WebView featureWebView;
    private String currentTab = "Home";
    private static final int REQUEST_MIC_PERMISSION = 7021;
    private PermissionRequest pendingMicRequest;

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

        ImageView appLogo = new ImageView(this);
        appLogo.setImageResource(R.drawable.ff_arena_logo);
        appLogo.setScaleType(ImageView.ScaleType.FIT_CENTER);
        LinearLayout.LayoutParams logoParams = new LinearLayout.LayoutParams(dp(54), dp(54));
        logoParams.rightMargin = dp(12);
        header.addView(appLogo, logoParams);

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        TextView logo = text("FF ARENA", 22, Color.WHITE, true);
        TextView tagline = text("TOURNAMENTS • ESPORTS", 10, ORANGE, true);
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
        String[] tabs = {"Home", "Matches", "Party", "Wallet", "Profile"};
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
            addSectionTitle("TOURNAMENTS", "Live tournament data from FF Arena");
            LinearLayout filters = new LinearLayout(this);
            filters.setOrientation(LinearLayout.HORIZONTAL);
            String[] modes = {"ALL", "BR", "VS"};
            for (String mode : modes) {
                Button filter = button(mode);
                filter.setTextSize(12);
                filter.setOnClickListener(v -> loadTournamentCards("ALL".equals(mode) ? "" : mode));
                LinearLayout.LayoutParams fp = new LinearLayout.LayoutParams(0, dp(42), 1);
                fp.setMargins(dp(2), 0, dp(2), dp(10));
                filters.addView(filter, fp);
            }
            content.addView(filters);
            tournamentResults = new LinearLayout(this);
            tournamentResults.setOrientation(LinearLayout.VERTICAL);
            content.addView(tournamentResults, new LinearLayout.LayoutParams(-1, -2));
            loadTournamentCards("");
            addActionRow("My registrations", "See joined matches and room updates", "/tournaments/my-registrations/");
            addActionRow("Results", "Completed matches and standings", "/tournaments/results/");
            addActionRow("Free tournaments", "Explore free-to-enter events", "/tournaments/free-tournament/");
        } else if ("Party".equals(currentTab)) {
            addSectionTitle("FF ARENA PARTY", "Live rooms, voice chat and the three-round FF quiz");
            addFeatureCard("Party Rooms", "Create a 12-player room or random join an available room", "Open Party Rooms", "/chat/party/");
            addNote("Room games use in-app Fan Tokens only. Party Room page works through the same website account.");
        } else if ("Wallet".equals(currentTab)) {
            addSectionTitle("PLAYER WALLET", "Your live wallet balance and recent transactions");
            tournamentResults = new LinearLayout(this);
            tournamentResults.setOrientation(LinearLayout.VERTICAL);
            content.addView(tournamentResults, new LinearLayout.LayoutParams(-1, -2));
            addFeatureCard("Add funds", "Use the available secure deposit options", "Deposit options", "/accounts/wallet/deposit/");
            addFeatureCard("Withdraw", "Manage your withdrawal request and payout details", "Withdrawal options", "/accounts/wallet/withdraw/");
            addNote("Never share your UPI PIN or OTP. Wallet balance is shown from the FF Arena account ledger.");
            loadWalletData();
        } else {
            addSectionTitle("PLAYER PROFILE", "Your FF Arena account details");
            tournamentResults = new LinearLayout(this);
            tournamentResults.setOrientation(LinearLayout.VERTICAL);
            content.addView(tournamentResults, new LinearLayout.LayoutParams(-1, -2));
            addFeatureCard("Login / Register", "Sign in or create your player account", "Open account", "/login/");
            addFeatureCard("Edit profile", "Update your player details", "Edit profile", "/accounts/profile/edit/");
            addFeatureCard("Password & settings", "Manage your account settings", "Account settings", "/accounts/settings/");
            loadPlayerProfile();
        }
        if (bottomNav != null) {
            for (int i = 0; i < bottomNav.getChildCount(); i++) {
                Button b = (Button) bottomNav.getChildAt(i);
                String label = b.getText().toString();
                b.setTextColor(label.equals(currentTab) ? ORANGE : MUTED);
            }
        }
    }

    private void loadTournamentCards(String mode) {
        if (tournamentResults == null) return;
        tournamentResults.removeAllViews();
        addNoteToResults("Loading tournaments from the FF Arena server…");
        final String endpoint = BASE_URL + "/tournaments/api/" + (mode.isEmpty() ? "" : "?mode=" + mode);
        new Thread(() -> {
            HttpURLConnection connection = null;
            String response = null;
            String error = null;
            try {
                connection = (HttpURLConnection) new URL(endpoint).openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(10000);
                connection.setRequestProperty("Accept", "application/json");
                int status = connection.getResponseCode();
                InputStream stream = status >= 200 && status < 300
                        ? connection.getInputStream() : connection.getErrorStream();
                if (stream == null) throw new IllegalStateException("Server returned HTTP " + status);
                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream))) {
                    String line;
                    while ((line = reader.readLine()) != null) body.append(line);
                }
                if (status >= 200 && status < 300) response = body.toString();
                else error = "Server returned HTTP " + status;
            } catch (Exception exception) {
                error = "Could not load tournaments. Check your internet connection and try again.";
            } finally {
                if (connection != null) connection.disconnect();
            }
            final String json = response;
            final String failure = error;
            runOnUiThread(() -> {
                if (!"Matches".equals(currentTab)) return;
                if (json == null) {
                    tournamentResults.removeAllViews();
                    addNoteToResults(failure == null ? "Tournament data is temporarily unavailable." : failure);
                    return;
                }
                try {
                    JSONObject payload = new JSONObject(json);
                    JSONArray results = payload.optJSONArray("results");
                    tournamentResults.removeAllViews();
                    if (results == null || results.length() == 0) {
                        addNoteToResults("No tournaments are listed right now. Please check again soon.");
                        return;
                    }
                    TextView count = text(results.length() + " TOURNAMENTS", 11, ORANGE, true);
                    count.setPadding(0, dp(4), 0, dp(10));
                    tournamentResults.addView(count);
                    for (int i = 0; i < results.length(); i++) {
                        JSONObject item = results.optJSONObject(i);
                        if (item != null) addTournamentCard(item);
                    }
                } catch (Exception exception) {
                    tournamentResults.removeAllViews();
                    addNoteToResults("Tournament data could not be read. Please try again later.");
                }
            });
        }).start();
    }

    private void addTournamentCard(JSONObject item) {
        String title = item.optString("title", "FF Arena Tournament");
        String mode = item.optString("mode", "BR");
        String format = item.optString("vs_format", "");
        String status = item.optString("status", "upcoming").toUpperCase();
        String fee = item.optString("entry_fee", "0");
        String prize = item.optString("prize_pool", "0");
        int joined = item.optInt("players_joined", 0);
        int capacity = item.optInt("max_players", 49);
        int id = item.optInt("id", 0);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(15), dp(16), dp(14));
        card.setBackground(background(new int[]{PANEL, PANEL}, dp(16), Color.rgb(48, 57, 75)));
        TextView badge = text(mode + (format.isEmpty() ? "" : "  •  " + format) + "     " + status,
                11, ORANGE, true);
        TextView heading = text(title, 18, Color.WHITE, true);
        heading.setPadding(0, dp(7), 0, dp(7));
        TextView details = text("Entry ₹" + fee + "     Prize ₹" + prize
                + "\\nPlayers " + joined + "/" + capacity, 13, MUTED, false);
        details.setPadding(0, 0, 0, dp(12));
        card.addView(badge);
        card.addView(heading);
        card.addView(details);
        Button open = button("VIEW TOURNAMENT");
        open.setOnClickListener(v -> openFeature("/tournaments/" + id + "/"));
        card.addView(open, new LinearLayout.LayoutParams(-1, dp(44)));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.bottomMargin = dp(12);
        tournamentResults.addView(card, p);
    }

    private void addNoteToResults(String message) {
        TextView note = text(message, 12, MUTED, false);
        note.setPadding(dp(15), dp(14), dp(15), dp(14));
        note.setBackground(background(new int[]{PANEL, PANEL}, dp(14), Color.rgb(48, 57, 75)));
        tournamentResults.addView(note);
    }

    private JSONObject fetchJson(String path) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(BASE_URL + path).openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(10000);
            connection.setRequestProperty("Accept", "application/json");
            String cookies = CookieManager.getInstance().getCookie(BASE_URL);
            if (cookies != null && !cookies.isEmpty()) connection.setRequestProperty("Cookie", cookies);
            int status = connection.getResponseCode();
            InputStream stream = status >= 200 && status < 300
                    ? connection.getInputStream() : connection.getErrorStream();
            if (stream == null) throw new IllegalStateException("HTTP " + status);
            StringBuilder body = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream))) {
                String line;
                while ((line = reader.readLine()) != null) body.append(line);
            }
            if (status == 401) throw new SecurityException("Please log in to your FF Arena account.");
            if (status < 200 || status >= 300) throw new IllegalStateException("Server returned HTTP " + status);
            return new JSONObject(body.toString());
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void loadPlayerProfile() {
        if (tournamentResults == null) return;
        addNoteToResults("Loading your profile…");
        new Thread(() -> {
            JSONObject data = null;
            String error = null;
            try { data = fetchJson("/accounts/api/me/"); }
            catch (Exception exception) { error = exception.getMessage(); }
            final JSONObject result = data;
            final String failure = error;
            runOnUiThread(() -> {
                if (!"Profile".equals(currentTab) || tournamentResults == null) return;
                tournamentResults.removeAllViews();
                if (result == null) {
                    addNoteToResults(failure == null ? "Profile could not be loaded." : failure);
                    return;
                }
                JSONObject p = result.optJSONObject("profile");
                if (p == null) { addNoteToResults("Profile data is unavailable."); return; }
                addAccountInfo("PLAYER", p.optString("username", "Player"));
                addAccountInfo("EMAIL", p.optString("email", "Not added"));
                addAccountInfo("PHONE", p.optString("phone_number", "Not added")
                        + (p.optBoolean("phone_verified") ? "  •  Verified" : ""));
                addAccountInfo("FREE FIRE UID", p.optString("free_fire_uid", "Not added")
                        + (p.optBoolean("uid_verified") ? "  •  Verified" : ""));
            });
        }).start();
    }

    private void loadWalletData() {
        if (tournamentResults == null) return;
        addNoteToResults("Loading wallet balance…");
        new Thread(() -> {
            JSONObject data = null;
            String error = null;
            try { data = fetchJson("/accounts/api/wallet/"); }
            catch (Exception exception) { error = exception.getMessage(); }
            final JSONObject result = data;
            final String failure = error;
            runOnUiThread(() -> {
                if (!"Wallet".equals(currentTab) || tournamentResults == null) return;
                tournamentResults.removeAllViews();
                if (result == null) {
                    addNoteToResults(failure == null ? "Wallet could not be loaded." : failure);
                    return;
                }
                JSONObject wallet = result.optJSONObject("wallet");
                if (wallet == null) { addNoteToResults("Wallet data is unavailable."); return; }
                addAccountInfo("AVAILABLE BALANCE", "₹" + wallet.optString("balance", "0.00"));
                addAccountInfo("WALLET ID", wallet.optString("wallet_id", "—"));
                JSONArray transactions = result.optJSONArray("transactions");
                if (transactions == null || transactions.length() == 0) {
                    addNoteToResults("No wallet transactions yet.");
                } else {
                    TextView heading = text("RECENT TRANSACTIONS", 12, ORANGE, true);
                    heading.setPadding(0, dp(12), 0, dp(8));
                    tournamentResults.addView(heading);
                    for (int i = 0; i < transactions.length(); i++) {
                        JSONObject item = transactions.optJSONObject(i);
                        if (item == null) continue;
                        String description = item.optString("description", "");
                        if (description.isEmpty()) description = item.optString("type", "Transaction").replace('_', ' ');
                        addAccountInfo(description.toUpperCase(),
                                "₹" + item.optString("amount", "0.00") + "  •  " + item.optString("status", ""));
                    }
                }
            });
        }).start();
    }

    private void addAccountInfo(String label, String value) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(15), dp(12), dp(15), dp(12));
        card.setBackground(background(new int[]{PANEL, PANEL}, dp(13), Color.rgb(48, 57, 75)));
        TextView key = text(label, 10, ORANGE, true);
        TextView val = text(value, 15, Color.WHITE, true);
        val.setPadding(0, dp(4), 0, 0);
        card.addView(key);
        card.addView(val);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.bottomMargin = dp(9);
        tournamentResults.addView(card, p);
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
        featureWebView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> {
                    Uri origin = request.getOrigin();
                    boolean trustedOrigin = origin != null
                            && "https".equalsIgnoreCase(origin.getScheme())
                            && "freefire-touranament-74nr.onrender.com".equalsIgnoreCase(origin.getHost());
                    boolean asksForAudio = false;
                    for (String resource : request.getResources()) {
                        if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) asksForAudio = true;
                    }
                    if (!trustedOrigin || !asksForAudio) {
                        request.deny();
                        return;
                    }
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                    } else {
                        pendingMicRequest = request;
                        requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQUEST_MIC_PERMISSION);
                    }
                });
            }

            @Override
            public void onPermissionRequestCanceled(PermissionRequest request) {
                if (pendingMicRequest == request) pendingMicRequest = null;
            }
        });
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
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_MIC_PERMISSION && pendingMicRequest != null) {
            PermissionRequest request = pendingMicRequest;
            pendingMicRequest = null;
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            } else {
                request.deny();
            }
        }
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
