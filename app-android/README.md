# Freehands Operator Console (Android)

A phone app for running the Freehands bot in the Eternal server. Kotlin, Jetpack
Compose, Material 3.

## What it does

| Tab | What you get |
| --- | --- |
| **Live** | Start/stop button, then a feed of every message, deletion, edit and media link as it happens |
| **Commands** | All 37 commands grouped by who can use them. Tap one for a plain-English explanation |
| **Settings** | Feature toggles, tuning values, force restart, and the creator card |

The creator card shows the live GitHub profile for [Lynxifyy](https://github.com/Lynxifyy)
with a link to the repository.

## How it talks to the bot

```
phone  ──HTTPS──▶  console_api.py  ──loopback──▶  bot process
        (token)     port 8790                      port 8791
```

The bot listens only on `127.0.0.1`. `console_api.py` is the one public door, and
it requires a bearer token on every request. That way the bot token never leaves
the server.

## Build

```bash
cd app-android
printf 'sdk.dir=/path/to/android-sdk\n' > local.properties
JAVA_HOME=/path/to/jdk-21 ./gradlew :app:assembleDebug
```

The APK lands in `app/build/outputs/apk/debug/app-debug.apk`.

Needs JDK 17 or newer, Android SDK 35, and Gradle 8.9.

## First run

1. Start the supervisor on the machine that runs the bot:
   ```bash
   FH_CONSOLE_TOKEN='choose-a-long-secret' python3 console_api.py
   ```
2. Open the app. Enter the URL and the same token.
3. Tap **Start**.

The token is kept on the phone in private storage. Nothing is sent anywhere
except your own control API.

## Honest limits

- **Device tracking is not possible.** Discord does not say which platform sent a
  message; no such field exists in the API. What the app can show is *presence*:
  whether someone is online from desktop, mobile or web. That needs the
  privileged `GUILD_PRESENCES` intent, so it is off by default. Turn on
  `presence_enabled` in Settings to use it. It will show nothing until the intent
  is enabled in the Discord developer portal too.
- Presence is a snapshot of right now, not a history of what device a past
  message came from.
- The app is a control surface. It does not run the bot on the phone.
