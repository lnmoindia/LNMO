# Getting real push notifications on Android (and iOS)

This guide is written for you, the school owner. You don't need to write any code. It takes about 30 minutes, most of it waiting for a build.

## Why a separate app build is needed

- **Android:** since Expo SDK 53, the Expo Go app can't receive push notifications on Android. This project is on **SDK 57**. Android needs our own LNMO app file (an **APK**), built once by Expo's servers.
- **iPhone:** Expo Go can *sometimes* receive Expo push, but Apple requires a paid Apple Developer account ($99/year) for a proper iOS build. iPhone push can come later.
- **What works today in Expo Go:** the Notifications settings screen, choosing alert types, and the "Local test" alert (tap it and the app opens the right screen).

Our app's ID (Android "package name" and iOS bundle ID) is **`com.lnmo.app`**.

---

## Step 1 — Create a free Expo account (5 min)

1. Go to **https://expo.dev/signup** and create an account. Free is fine.
2. Create an access token so I can start builds for you:
   - Go to **https://expo.dev/settings/access-tokens**.
   - Click **Create token** and name it `lnmo-builder`.
   - Copy the token. It is shown only once.
3. **Send me the token.** I store it only as a secret on the build machine (`EXPO_TOKEN`), never in the code.

## Step 2 — Create a Firebase project for Android push (10 min)

Google's Firebase is what delivers notifications to Android phones. It's free.

1. Go to **https://console.firebase.google.com**, then **Add project**, and name it `LNMO`.
   - You can switch Google Analytics off. Then click **Create project**.
2. In the project, click the **Android** icon (**Add app**):
   - **Android package name:** `com.lnmo.app` (exactly this)
   - **App nickname:** LNMO
   - Click **Register app**.
3. Click **Download google-services.json**, then **Next**, **Next**, **Continue to console**.
4. **Send me the `google-services.json` file.** I put it in the app folder and switch it on in the app settings with one line.

## Step 3 — Give Expo permission to send through Firebase (5 min)

1. In Firebase, click the gear icon, then **Project settings**, then the **Service accounts** tab.
2. Click **Generate new private key**, then **Generate key**. A `.json` file downloads.
   - Keep it private. It works like a password.
3. Go to **https://expo.dev**, open the **LNMO** project (it appears after I run Step 4a), then **Credentials**, then **Android**, then `com.lnmo.app`.
4. Under **FCM V1 service account key**, click **Upload** and choose the file from step 2.
   - If you'd rather I do this, send me the file and I'll upload it. Either way it never goes into the code.

## Step 4 — Build the Android app

Once I have the token (Step 1) and `google-services.json` (Step 2), I run:

```
# 4a. Link this project to your Expo account (writes the projectId into app.json)
EXPO_TOKEN=… npx eas-cli init --non-interactive --force

# 4b. Build an installable Android app on Expo's servers (about 15–20 min)
EXPO_TOKEN=… npx eas-cli build --profile preview --platform android --non-interactive --no-wait
```

- **`preview`** (recommended first): a normal, complete app. It talks to the preview server and needs no laptop running.
- **`development`**: a "developer" app that loads the latest code live from our dev server, like Expo Go but with push.
  - Before this build, I add one package (`expo-dev-client`).
  - I haven't added it yet on purpose, because it changes how the Expo Go QR code behaves.
  - Ask for it only if you want live updates on the installed app.

You can also run the same commands yourself on a computer with Node.js. Without `--non-interactive`, it asks a couple of Yes/No questions; answer **Yes**.

## Step 5 — Install it on an Android phone (2 min)

1. When the build finishes, Expo shows a link and a QR code at **https://expo.dev** → LNMO → **Builds**. I'll also send you the link.
2. Open the link on the Android phone, then **Download**, then **Install**.
   - Android may ask you to allow installing apps from your browser. Allow it once.
3. Open **LNMO**, choose school `sunrise`, and sign in.
   - Tap **Allow notifications** on the friendly screen.
4. Go to **More → Notifications**, then **Send test notification**. An alert should arrive within seconds.
5. *(Development build only)* The app asks for the dev server URL. Use `https://lnmo-fees.expo.preview.emergentagent.com`.

---

## What I need from you (checklist)

| # | What | Where you get it |
|---|------|------------------|
| 1 | **EXPO_TOKEN** (access token) | expo.dev → Settings → Access tokens |
| 2 | **google-services.json** | Firebase → Add Android app `com.lnmo.app` |
| 3 | **FCM V1 service account key (.json)**: upload it on expo.dev yourself, *or* send it to me | Firebase → Project settings → Service accounts |
| 4 | *(Later, iPhone only)* an Apple Developer account | developer.apple.com ($99/year) |

## Good to know

- Students, parents and teachers can switch each alert type on or off in **More → Notifications**. Their choices are saved to their account.
- Signing out stops notifications on that phone.
- If a phone uninstalls the app, the server notices automatically and stops sending to it.
- Every push is listed in the school's message history (**Communication → History**) with the channel **push** and its status.
- No passwords or OTP codes are ever sent in a notification. Only a short preview is sent.
