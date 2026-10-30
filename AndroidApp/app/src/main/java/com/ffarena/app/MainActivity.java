package com.ffarena.app;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.IntentFilter;
import android.graphics.Color;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Environment;
import android.view.Gravity;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.PermissionRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.ValueCallback;
import android.webkit.JavascriptInterface;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ImageView;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.File;
import android.database.Cursor;
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
    private static final int REQUEST_FILE_CHOOSER = 7022;
    private ValueCallback<Uri[]> pendingFileCallback;
    private PermissionRequest pendingMicRequest;
    private long pendingApkDownloadId = -1L;
    private int pendingApkVersionCode = -1;
    private String pendingApkFileName = "";
    private Uri pendingInstallUri;
    private DownloadManager apkDownloadManager;
    private BroadcastReceiver apkDownloadReceiver;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        // Keep the app UI server-driven so website changes appear without reinstalling the APK.
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        setContentView(root);
        openFeature("/");
        registerApkDownloadReceiver();
        checkForAppUpdate();
    }

    private void checkForAppUpdate() {
        new Thread(() -> {
            HttpURLConnection connection = null;
            try {
                URL url = new URL("https://api.github.com/repos/workload139-creator/FREEFIRE-TOURANAMENT-/releases/tags/ff-arena-latest?cache=" + System.currentTimeMillis());
                connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(8000);
                connection.setRequestProperty("Accept", "application/vnd.github+json");
                connection.setRequestProperty("Cache-Control", "no-cache");
                connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                int status = connection.getResponseCode();
                if (status < 200 || status >= 300) return;
                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) body.append(line);
                }
                JSONObject release = new JSONObject(body.toString());
                String releaseNotes = release.optString("body", "");
                java.util.regex.Matcher matcher = java.util.regex.Pattern
                        .compile("versionCode\\s*:\\s*(\\d+)", java.util.regex.Pattern.CASE_INSENSITIVE)
                        .matcher(releaseNotes);
                if (!matcher.find()) return;
                int latestVersion = Integer.parseInt(matcher.group(1));
                if (latestVersion <= BuildConfig.VERSION_CODE) return;
                String apkUrl = "";
                JSONArray assets = release.optJSONArray("assets");
                if (assets != null) {
                    for (int i = 0; i < assets.length(); i++) {
                        JSONObject asset = assets.optJSONObject(i);
                        if (asset != null && "app-release.apk".equals(asset.optString("name"))) {
                            apkUrl = asset.optString("browser_download_url", "");
                            break;
                        }
                    }
                }
                if (apkUrl.isEmpty()) return;
                final String downloadUrl = apkUrl;
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    new AlertDialog.Builder(MainActivity.this)
                            .setTitle("FF Arena update available")
                            .setMessage("A new app version is available ("
                                    + BuildConfig.VERSION_NAME + " → 1.0." + latestVersion
                                    + "). Update the app to get the latest features.")
                            .setCancelable(true)
                            .setNegativeButton("Later", (dialog, which) -> dialog.dismiss())
                            .setPositiveButton("Download & install", (dialog, which) -> {
                                enqueueApkDownload(downloadUrl, latestVersion);
                            })
                            .show();
                });
            } catch (Exception ignored) {
                // Update checks are optional; offline users can continue using the app.
            } finally {
                if (connection != null) connection.disconnect();
            }
        }).start();
    }

    private void registerApkDownloadReceiver() {
        apkDownloadManager = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
        apkDownloadReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (intent == null || !DownloadManager.ACTION_DOWNLOAD_COMPLETE.equals(intent.getAction())) return;
                long completedId = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L);
                if (completedId != pendingApkDownloadId || apkDownloadManager == null) return;

                DownloadManager.Query query = new DownloadManager.Query().setFilterById(completedId);
                try (Cursor cursor = apkDownloadManager.query(query)) {
                    if (cursor == null || !cursor.moveToFirst()) {
                        showUpdateError("The update download could not be checked. Please try again.");
                        return;
                    }
                    int statusColumn = cursor.getColumnIndex(DownloadManager.COLUMN_STATUS);
                    int status = statusColumn >= 0 ? cursor.getInt(statusColumn) : -1;
                    pendingApkDownloadId = -1L;
                    if (status != DownloadManager.STATUS_SUCCESSFUL) {
                        showUpdateError("The update download failed. Check your internet connection and try again.");
                        return;
                    }
                    Uri apkUri = apkDownloadManager.getUriForDownloadedFile(completedId);
                    if (apkUri == null) {
                        showUpdateError("The downloaded update file could not be opened. Please download it again.");
                        return;
                    }
                    File downloadDirectory = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                    File apkFile = downloadDirectory == null ? null : new File(downloadDirectory, pendingApkFileName);
                    if (apkFile == null || !apkFile.isFile() || apkFile.length() < 1024) {
                        showUpdateError("The update file is incomplete. Please download it again.");
                        return;
                    }
                    android.content.pm.PackageInfo archive = getPackageManager().getPackageArchiveInfo(
                            apkFile.getAbsolutePath(), PackageManager.GET_SIGNATURES);
                    if (archive == null || !getPackageName().equals(archive.packageName)
                            || archive.versionCode < pendingApkVersionCode
                            || archive.versionCode <= BuildConfig.VERSION_CODE) {
                        showUpdateError("The downloaded APK is not a valid newer FF Arena update. Please try again later.");
                        return;
                    }
                    try {
                        android.content.pm.PackageInfo installed = getPackageManager().getPackageInfo(
                                getPackageName(), PackageManager.GET_SIGNATURES);
                        if (archive.signatures != null && installed.signatures != null
                                && archive.signatures.length > 0 && installed.signatures.length > 0
                                && !archive.signatures[0].equals(installed.signatures[0])) {
                            showUpdateError("This phone has an older test-signed FF Arena APK. Uninstall that test version once, then install the official release APK. Your online FF Arena account and tournament data will remain safe; you may need to log in again.");
                            return;
                        }
                    } catch (Exception signatureCheckError) {
                        // Android's installer performs the final signature validation.
                    }
                    installDownloadedApk(apkUri);
                } catch (Exception exception) {
                    pendingApkDownloadId = -1L;
                    showUpdateError("Could not prepare the update installer. Please try again.");
                }
            }
        };
        IntentFilter filter = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(apkDownloadReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(apkDownloadReceiver, filter);
        }
    }

    private void enqueueApkDownload(String downloadUrl, int versionCode) {
        try {
            if (apkDownloadManager == null) {
                apkDownloadManager = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            }
            if (apkDownloadManager == null) {
                showUpdateError("Android's download service is unavailable on this device.");
                return;
            }
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(downloadUrl));
            request.setTitle("FF Arena update");
            request.setDescription("Downloading the latest FF Arena app version");
            request.setMimeType("application/vnd.android.package-archive");
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setAllowedOverMetered(true);
            request.setAllowedOverRoaming(false);
            pendingApkVersionCode = versionCode;
            pendingApkFileName = "ff-arena-update-" + versionCode + ".apk";
            File downloadDirectory = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
            if (downloadDirectory != null) {
                File previousDownload = new File(downloadDirectory, pendingApkFileName);
                if (previousDownload.exists() && !previousDownload.delete()) {
                    showUpdateError("The previous update file could not be replaced. Clear FF Arena app downloads and try again.");
                    return;
                }
            }
            request.setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, pendingApkFileName);
            pendingApkDownloadId = apkDownloadManager.enqueue(request);
            Toast.makeText(this, "Update download started. You can continue using FF Arena.", Toast.LENGTH_LONG).show();
        } catch (Exception exception) {
            showUpdateError("Could not start the update download. Please try again.");
        }
    }

    private void installDownloadedApk(Uri apkUri) {
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            pendingInstallUri = apkUri;
            try {
                Intent settingsIntent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + getPackageName()));
                startActivity(settingsIntent);
            } catch (Exception exception) {
                showUpdateError("Allow FF Arena to install updates from this source in Android settings, then try again.");
            }
            return;
        }
        try {
            Intent installIntent = new Intent(Intent.ACTION_INSTALL_PACKAGE);
            installIntent.setData(apkUri);
            installIntent.setFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            installIntent.putExtra(Intent.EXTRA_RETURN_RESULT, true);
            startActivityForResult(installIntent, 7023);
        } catch (Exception exception) {
            showUpdateError("Android could not open the installer. The downloaded update is still available in FF Arena's app downloads.");
        }
    }

    private void showUpdateError(String message) {
        runOnUiThread(() -> {
            if (isFinishing() || isDestroyed()) return;
            new AlertDialog.Builder(MainActivity.this)
                    .setTitle("FF Arena update")
                    .setMessage(message)
                    .setPositiveButton("OK", (dialog, which) -> dialog.dismiss())
                    .show();
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (pendingInstallUri != null
                && (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls())) {
            Uri uri = pendingInstallUri;
            pendingInstallUri = null;
            installDownloadedApk(uri);
        }
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
        String[] tabs = {"Home", "Matches", "Wallet", "Voice Party", "Profile"};
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
        if (featureWebView != null) featureWebView.stopLoading();
        // Reuse the WebView between tabs to retain its page cache and cookies.
        if ("Voice Party".equals(tab)) {
            openFeature("/chat/party/");
            return;
        }
        showNativeShell();
    }

    private void renderTab() {
        content.removeAllViews();
        if ("Home".equals(currentTab)) {
            addHero();
            addSectionTitle("ARENA DASHBOARD", "Your important FF Arena features");
            addFeatureCard("MATCHES", "BR • CS • Free • Diwali (1 Diamond) • Unlimited • Girl vs Boy", "Explore tournament categories", "/tournaments/");
            addFeatureCard("WALLET & VIRTUAL CREDITS", "Wallet, Diamonds, Coins and transaction history", "Open wallet", "/accounts/wallet/");
            addFeatureCard("LEADERBOARD & RESULTS", "Track your performance and match results", "View standings", "/tournaments/results/");
            addFeatureCard("COMMUNITY", "Player posts, friends, followers and updates", "Open community", "/friends/feed/");
            addFeatureCard("DIAMOND & COIN SHOP", "View virtual credit packs and payment QR", "Open Shop", "/friends/shop/");
            addFeatureCard("CHAT & PARTY ROOMS", "Connect with players and your squad", "Open Chat", "/chat/");
            addFeatureCard("PLAYER PROFILE", "Your photo, player ID and account settings", "Open profile", "/accounts/profile/");
            addFeatureCard("AI ARENA ASSISTANT", "Get help about FF Arena features and rules", "Ask assistant", "/assistant/");
            addSectionTitle("OFFICIAL COMMUNITY LINKS", "Follow FF Arena outside the app");
            addExternalLinkRow("WhatsApp Channel", "Tournament announcements and updates", "https://whatsapp.com/channel/0029Vb9NpfeBadmbTK4XDJ3p");
            addExternalLinkRow("YouTube", "Gameplay and live tournaments", "https://www.youtube.com/@freefire_tour");
            addExternalLinkRow("Instagram", "Photos and tournament news", "https://www.instagram.com/freefiretournament0/");
        } else if ("Matches".equals(currentTab)) {
            addSectionTitle("MATCH CATEGORIES", "Choose the arena you want to play");
            addFeatureCard("BATTLE ROYALE", "Solo, Duo and Squad survival matches", "Open BR tournaments", "/tournaments/#regular-br-tournaments");
            addFeatureCard("CLASH SQUAD (CS)", "1v1 • 2v2 • 3v3 • 4v4", "Open CS tournaments", "/tournaments/#game-modes");
            addFeatureCard("FREE TOURNAMENTS", "Free entry community events", "Open Free tournaments", "/tournaments/#free-fan-tournaments");
            addFeatureCard("UNLIMITED", "Unlimited BR and open-entry formats", "Open Unlimited arena", "/tournaments/#unlimited-tournaments");
            addFeatureCard("DIWALI SOLO BR", "1 Diamond entry • 49 players • 20 Diamonds first prize", "Open Diwali Offer", "/tournaments/diwali-offer/");
            addFeatureCard("GIRL VS BOY", "Special community showdown", "Open Girl vs Boy", "/tournaments/#girls-vs-boys");
            addActionRow("My registrations", "See joined matches and room updates", "/tournaments/my-registrations/");
            addActionRow("Results", "Completed matches and standings", "/tournaments/results/");
        } else if ("Voice Party".equals(currentTab)) {
            addSectionTitle("VOICE PARTY", "Squad voice rooms • microphone • live chat");
            addFeatureCard("PARTY ROOMS", "Create a room or join your squad. Inside the room tap Join voice + Mic on and allow microphone permission.", "Open Voice Party", "/chat/party/");
            addNote("Mic troubleshooting: allow microphone permission for FF Arena in Android app settings. Live voice also requires LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET configured by the server administrator.");
        } else if ("Wallet".equals(currentTab)) {
            addSectionTitle("PLAYER WALLET", "Your live wallet balance and recent transactions");
            tournamentResults = new LinearLayout(this);
            tournamentResults.setOrientation(LinearLayout.VERTICAL);
            content.addView(tournamentResults, new LinearLayout.LayoutParams(-1, -2));
            addFeatureCard("Add funds", "Use the available secure deposit options", "Deposit options", "/accounts/wallet/deposit/");
            addFeatureCard("Withdraw", "Manage your withdrawal request and payout details", "Withdrawal options", "/accounts/wallet/withdraw/");
            addFeatureCard("My Tournaments & Refunds", "See registrations, payment status, refund eligibility and refund references", "Open registrations", "/tournaments/my-registrations/");
            addFeatureCard("Full Transaction History", "Review wallet deposits, withdrawals, tournament entries, refunds and rewards", "View history", "/accounts/wallet/");
            addNote("Never share your UPI PIN or OTP. Wallet balance is shown from the FF Arena account ledger.");
            loadWalletData();
        } else {
            addSectionTitle("PLAYER PROFILE", "Your FF Arena account details");
            tournamentResults = new LinearLayout(this);
            tournamentResults.setOrientation(LinearLayout.VERTICAL);
            content.addView(tournamentResults, new LinearLayout.LayoutParams(-1, -2));
            addFeatureCard("PLAYER PROFILE", "View your account identity and Free Fire UID", "My profile", "/accounts/profile/");
            addFeatureCard("FOLLOWERS", "See players who follow your account", "View followers", "/friends/followers/");
            addFeatureCard("FOLLOWING", "See accounts you follow", "View following", "/friends/following/");
            addFeatureCard("CHAT & FRIENDS", "Open direct messages, friend requests and squad conversations", "Open chat", "/chat/");
            addFeatureCard("PHOTO POSTS", "Post images only, browse the community photo feed and share Booyah moments", "Open photo feed", "/friends/feed/");
            addFeatureCard("☰ SETTINGS & ACCOUNT DETAILS", "Email, phone, UID, profile editing, password and account options", "Open settings", "/accounts/settings/");
            addFeatureCard("Edit profile", "Update your player details and profile photo", "Edit profile", "/accounts/profile/edit/");
            addFeatureCard("Login / Register", "Sign in or create your player account", "Open account", "/login/");
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
                String photoUrl = p.optString("profile_photo", "");
                if (!photoUrl.isEmpty()) loadProfilePhoto(photoUrl);
                addAccountInfo("PLAYER", p.optString("username", "Player"));
                addAccountInfo("EMAIL", p.optString("email", "Not added"));
                addAccountInfo("PHONE", p.optString("phone_number", "Not added")
                        + (p.optBoolean("phone_verified") ? "  •  Verified" : ""));
                addAccountInfo("FREE FIRE UID", p.optString("free_fire_uid", "Not added")
                        + (p.optBoolean("uid_verified") ? "  •  Verified" : ""));
            });
        }).start();
    }

    private void loadProfilePhoto(String photoUrl) {
        if (tournamentResults == null || photoUrl == null || photoUrl.isEmpty()) return;
        ImageView avatar = new ImageView(this);
        avatar.setScaleType(ImageView.ScaleType.CENTER_CROP);
        avatar.setBackground(background(new int[]{PANEL, PANEL}, dp(44), ORANGE));
        avatar.setClipToOutline(true);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(88), dp(88));
        params.bottomMargin = dp(12);
        tournamentResults.addView(avatar, 0, params);

        new Thread(() -> {
            HttpURLConnection connection = null;
            Bitmap bitmap = null;
            try {
                connection = (HttpURLConnection) new URL(photoUrl).openConnection();
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(10000);
                connection.setRequestProperty("Accept", "image/*");
                String cookies = CookieManager.getInstance().getCookie(BASE_URL);
                if (cookies != null && !cookies.isEmpty()) connection.setRequestProperty("Cookie", cookies);
                if (connection.getResponseCode() == HttpURLConnection.HTTP_OK) {
                    try (InputStream stream = connection.getInputStream()) {
                        bitmap = BitmapFactory.decodeStream(stream);
                    }
                }
            } catch (Exception ignored) {
                // Profile text remains available if the photo cannot be fetched.
            } finally {
                if (connection != null) connection.disconnect();
            }
            final Bitmap loadedBitmap = bitmap;
            runOnUiThread(() -> {
                if (!"Profile".equals(currentTab) || tournamentResults == null) return;
                if (loadedBitmap != null) avatar.setImageBitmap(loadedBitmap);
                else avatar.setVisibility(View.GONE);
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
                        String currency = item.optString("currency", "INR");
                        String quantity = item.optString("quantity", "");
                        String value = "INR".equalsIgnoreCase(currency)
                                ? "₹" + item.optString("amount", "0.00")
                                : (quantity.isEmpty() ? item.optString("amount", "0.00") : quantity + " " + currency);
                        String reference = item.optString("reference", "");
                        String details = value + "  •  " + item.optString("status", "");
                        if (!reference.isEmpty()) details += "\\nRef: " + reference;
                        addAccountInfo(description.toUpperCase(), details);
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

    private void addExternalLinkRow(String title, String desc, String url) {
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
        row.addView(text("↗", 22, ORANGE, true));
        row.setOnClickListener(v -> {
            try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
            catch (Exception ignored) { Toast.makeText(this, "Compatible app nahi mili.", Toast.LENGTH_SHORT).show(); }
        });
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
        Button back = button("/".equals(route) ? "↻  REFRESH FF ARENA" : "‹  BACK TO FF ARENA");
        back.setOnClickListener(v -> {
            if ("/".equals(route) && featureWebView != null) {
                featureWebView.reload();
                return;
            }
            showNativeShell();
        });
        page.addView(back, new LinearLayout.LayoutParams(-1, dp(48)));
        if (featureWebView == null) {
            featureWebView = createFeatureWebView();
        } else if (featureWebView.getParent() instanceof ViewGroup) {
            ((ViewGroup) featureWebView.getParent()).removeView(featureWebView);
        }
        page.addView(featureWebView, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(page, new LinearLayout.LayoutParams(-1, -1));
        setContentView(root);
        featureWebView.loadUrl(url);
    }

    private WebView createFeatureWebView() {
        WebView webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setUserAgentString(settings.getUserAgentString() + " FFArenaAndroidApp");
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setSupportMultipleWindows(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setSupportZoom(false);
        settings.setLoadsImagesAutomatically(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        webView.addJavascriptInterface(new ShareBridge(), "FFArenaShare");
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleWebViewNavigation(view, request.getUrl().toString());
            }
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleWebViewNavigation(view, url);
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView target, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (pendingFileCallback != null) {
                    pendingFileCallback.onReceiveValue(null);
                    pendingFileCallback = null;
                }
                pendingFileCallback = callback;
                try {
                    Intent chooserIntent = params.createIntent();
                    if (chooserIntent.getType() == null || chooserIntent.getType().isEmpty()) {
                        chooserIntent.setType("image/*");
                    }
                    chooserIntent.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(Intent.createChooser(chooserIntent, "Select photo"), REQUEST_FILE_CHOOSER);
                    return true;
                } catch (Exception exception) {
                    pendingFileCallback = null;
                    callback.onReceiveValue(null);
                    return false;
                }
            }
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
                    if (!trustedOrigin || !asksForAudio || isFinishing() || isDestroyed()) {
                        request.deny();
                        return;
                    }
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                    } else {
                        if (pendingMicRequest != null && pendingMicRequest != request) {
                            try { pendingMicRequest.deny(); } catch (Exception ignored) {}
                        }
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
        return webView;
    }

    private boolean handleWebViewNavigation(WebView view, String url) {
        if (url == null || url.isEmpty()) return false;
        Uri uri = Uri.parse(url);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
        if ("https".equals(scheme) && "freefire-touranament-74nr.onrender.com".equals(host)) {
            return false;
        }
        if ("http".equals(scheme) || "https".equals(scheme)
                || "upi".equals(scheme) || "tel".equals(scheme)
                || "mailto".equals(scheme) || "intent".equals(scheme)) {
            try {
                Intent intent = "intent".equals(scheme)
                        ? Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
                        : new Intent(Intent.ACTION_VIEW, uri);
                startActivity(intent);
            } catch (Exception ignored) {
                Toast.makeText(this, "Is link ko kholne ke liye compatible app nahi mili.", Toast.LENGTH_SHORT).show();
            }
            return true;
        }
        return true;
    }

    private final class ShareBridge {
        @JavascriptInterface
        public void share() {
            runOnUiThread(() -> {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/plain");
                send.putExtra(Intent.EXTRA_SUBJECT, "FF Arena - Free Fire Tournaments");
                send.putExtra(Intent.EXTRA_TEXT,
                        "Join FF Arena for Free Fire tournaments! Download the Android app: "
                        + "https://github.com/workload139-creator/FREEFIRE-TOURANAMENT-/releases/download/ff-arena-latest/app-release.apk"
                        + "\nWebsite: " + BASE_URL);
                startActivity(Intent.createChooser(send, "Share FF Arena"));
            });
        }
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
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_FILE_CHOOSER && pendingFileCallback != null) {
            Uri[] results = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            pendingFileCallback.onReceiveValue(results);
            pendingFileCallback = null;
        } else if (requestCode == 7023) {
            if (resultCode == RESULT_OK) {
                Toast.makeText(this, "FF Arena update installed. Reopen the app.", Toast.LENGTH_LONG).show();
            } else {
                Toast.makeText(this, "Installer closed. If the app did not update, approve Android's install prompt and try again.", Toast.LENGTH_LONG).show();
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_MIC_PERMISSION && pendingMicRequest != null) {
            PermissionRequest request = pendingMicRequest;
            pendingMicRequest = null;
            if (grantResults.length > 0
                    && grantResults[0] == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                    && !isFinishing() && !isDestroyed()) {
                request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            } else {
                try { request.deny(); } catch (Exception ignored) {}
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (featureWebView != null && featureWebView.canGoBack()) {
            featureWebView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (apkDownloadReceiver != null) {
            try { unregisterReceiver(apkDownloadReceiver); } catch (IllegalArgumentException ignored) {}
            apkDownloadReceiver = null;
        }
        if (featureWebView != null) {
            featureWebView.stopLoading();
            featureWebView.destroy();
            featureWebView = null;
        }
        super.onDestroy();
    }
}
