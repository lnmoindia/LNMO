# Building the LNMO Android app (with Emergent) and turning on push notifications

This guide is written for you, the school owner. You don't need to run any commands.

## Before you build

1. **Deploy (or Redeploy) first.** The app build uses the latest deployed code and the **deployed** backend. Click **Deploy / Redeploy** in Emergent and wait until it's live.
2. **Check the backend address.** The installed app talks to the address in `EXPO_PUBLIC_BACKEND_URL`.
   - For the real app, this must be your **deployed website address** (its origin), for example `https://your-school-app.emergent.host`.
   - Don't add `/api`. The app adds it. If `/api` is there by mistake, it's ignored.
   - It must **not** be the preview address (`…preview.emergentagent.com`). Preview addresses can sleep or change.

## Build the APK

1. In Emergent, open **Publish → Mobile → Android**.
2. Confirm the app details:
   - **App name:** LNMO
   - **Package name:** `com.lnmo.app`
   - **Version:** 1.0.0 (version code 1)
3. Emergent manages the Expo account and the signing keys for you. You don't need an Expo account or `eas.json`.
4. **Push notifications (optional, recommended):** when Emergent asks for the **Firebase service account JSON**, upload it. To get it:
   - Go to **https://console.firebase.google.com**, then **Add project**, and name it `LNMO`.
   - Add an **Android app** with package name **`com.lnmo.app`**.
   - Go to the gear icon, then **Project settings → Service accounts → Generate new private key**. A `.json` file downloads. That's the file to upload.
   - On the same Firebase screen (**Project settings → General → Your apps**), also download **`google-services.json`** and send it to me. See the note below.
5. Start the build. When it finishes, download the APK and install it on an Android phone. Android may ask you to allow installing from your browser once.

## About push on Android (important)

Android push needs **two** Firebase files:

| File | What it's for | Where it goes |
|------|---------------|---------------|
| **Service account JSON** | Lets Expo's servers *send* notifications | Upload in **Publish → Mobile** |
| **google-services.json** | Lets the phone *receive* notifications (registers with Firebase) | Must be inside the app. Send it to me and I add it with one line in `app.json` |

- **Without `google-services.json`:** the app builds and works normally, but the phone can't register for push. The Notifications screen says it couldn't register, and every other feature still works.
- **With both files:** rebuild once, then open **More → Notifications → Send test notification** on the phone.

## What works where

- **Expo Go (testing):** everything except push. The Notifications screen still saves your alert choices.
- **Installed APK:** everything. Push works too once both Firebase files are in place.

## Good to know

- Students, parents and teachers can switch each alert type on or off in **More → Notifications**. Their choices are saved to their account.
- Signing out stops notifications on that phone. If the app is uninstalled, the server stops sending automatically.
- Every push is listed in the school's message history with the channel **push**.
- No passwords or OTP codes are ever sent in a notification.
