# xyz.com ERP Mobile App — Store Submission Checklist

Complete every item here before submitting to Google Play or the App Store.

---

## 1. One-Time EAS Setup

- [ ] Run `npm install -g eas-cli && eas login` with the Expo organization account.
- [ ] Run `eas init` from the `app/` directory → fills `extra.eas.projectId` in `app.json`.
  - Commit the updated `app.json` (the project ID is safe to commit; it is not a secret).

---

## 2. Bundle / Package Identifier (Permanent — decide before first submission)

> ⚠️ **The package name cannot be changed after first store publish.**

- [ ] Replace `com.erpcampus.mobile` in `app.json` with your organization's reverse-domain identifier:
  - `android.package` → e.g. `com.yourcompany.erp`
  - `ios.bundleIdentifier` → same value

---

## 3. EAS Secrets (credentials — never committed to git)

Set these once per EAS project via `eas secret:create`:

```bash
# Backend API (HTTPS only — required for production builds)
eas secret:create --name EXPO_PUBLIC_API_URL   --value https://api.yourdomain.com

# Web console URL (enables in-app live classroom browser)
eas secret:create --name EXPO_PUBLIC_WEB_URL   --value https://erp.yourdomain.com

# iOS App Store Connect (for eas submit --platform ios)
eas secret:create --name APPLE_ID              --value your@appleid.com
eas secret:create --name ASC_APP_ID            --value 1234567890        # App Store Connect App ID
eas secret:create --name APPLE_TEAM_ID         --value ABCDE12345
```

---

## 4. Google Play Setup (Android)

- [ ] Create a **Google Play Console** account and a new application.
- [ ] Generate a **service account key** (Google Play Console → Setup → API access → Create service account):
  1. Download the JSON key file.
  2. Save it as `app/google-play-key.json` (already gitignored).
- [ ] Grant the service account **Release manager** permission in Play Console.

---

## 5. App Store Connect Setup (iOS)

- [ ] Register the app in **App Store Connect** with the correct Bundle ID.
- [ ] Create a new App ID in the Apple Developer portal.
- [ ] Fill in `APPLE_ID`, `ASC_APP_ID`, and `APPLE_TEAM_ID` EAS secrets (step 3 above).

---

## 6. Store Assets

| Asset | Required Size | Location | Status |
|-------|--------------|----------|--------|
| App icon (PNG, no alpha) | 1024×1024 | `assets/images/icon.png` | ✅ exists |
| Android adaptive foreground | 432×432 | `assets/images/android-icon-foreground.png` | ✅ exists |
| Android adaptive background | 432×432 | `assets/images/android-icon-background.png` | ✅ exists |
| Android monochrome | 432×432 | `assets/images/android-icon-monochrome.png` | ✅ exists |
| Splash screen icon | 76×76+ | `assets/images/splash-icon.png` | ✅ exists |
| Play Store feature graphic | 1024×500 | `assets/store/feature-graphic.png` | ✅ exists |
| Play Store icon | 512×512 | `assets/store/icon-512.png` | ✅ exists |
| **Screenshots** | Phone + 7"/10" tablet | *to capture from preview build* | ❌ needed |

---

## 7. Screenshots

Capture from the **preview** build (not from marketing renders):

```bash
eas build --profile preview --platform android
# Install on a device/emulator, take screenshots for:
# - phone (1080×1920 or similar)
# - 7-inch tablet (1200×1920)
# - 10-inch tablet (1600×2560) — optional but recommended
```

---

## 8. Store Listing Copy

- [ ] **App name** ≤ 30 characters
- [ ] **Short description** ≤ 80 characters (Play) / subtitle ≤ 30 chars (App Store)
- [ ] **Full description** ≤ 4,000 characters
- [ ] **Privacy Policy URL** — mandatory for both stores (the app collects names, emails, attendance, grades, and uses FCM push).
  Use the `/privacy` URL from the web frontend (already created in Blocker #3 fix).
- [ ] **Content rating** — complete the Play Store questionnaire (Educational / 3+).

---

## 9. Build & Submit

```bash
# 1. Build for both platforms
eas build --profile production --platform android
eas build --profile production --platform ios

# 2. Submit to stores
eas submit --profile production --platform android   # uploads to Play → Internal track
eas submit --profile production --platform ios       # uploads to App Store Connect

# 3. In the respective console, promote from Internal → Production
```

---

## 10. Backend Checklist (before going live)

- [ ] Production API at `EXPO_PUBLIC_API_URL` is **HTTPS** with a valid TLS cert.
- [ ] CORS: the web console origin (`EXPO_PUBLIC_WEB_URL`) is in `ALLOWED_ORIGINS`.
- [ ] Firebase Cloud Messaging: `FCM_SERVICE_ACCOUNT_JSON` or `FCM_SERVICE_ACCOUNT_B64` is configured for push notifications.
- [ ] `STORAGE_BACKEND=s3` with a valid `S3_BUCKET` is set (see Issue #7 fix).
