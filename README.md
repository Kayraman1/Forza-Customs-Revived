# Forza Customs Revived

![Forza Customs Revived Header](https://i.imgur.com/Y9FKw5U.png)

**A community project dedicated to bringing Forza Customs back to a working state.**

Forza Customs became unavailable after the game's original service was shut down. One of the major consequences is that a new Profile/Save can no longer be created normally on a new device.

**Forza Customs Revived** aims to bring the game back to a working state on new devices, while also improving compatibility with newer versions of Android.

> **Having problems on a newer device?**
>
> Please open an [Issue](../../issues) and include the exact device you are using. If possible, also include the Android version and any relevant logs.

---

## What Is This Project?

Forza Customs originally relied on an online service during the first session of the game.

After the service shutdown, a clean installation can get stuck before the actual game starts because the client is still trying to complete its original first-session registration.

The original client references:

```text
customcarworks.hutchgames.io
```

That hostname no longer resolves, so the original first-session registration cannot complete.

However, the game already contains an **offline path for an established local player**.

Instead of trying to recreate the original server, this project patches the game so that a new local installation can use that existing offline path.

In simple terms:

```text
Original game

New installation
       │
       ▼
First-session registration
       │
       ▼
Original server
       │
       X
    Shutdown
```

With the preservation patch:

```text
New installation
       │
       ▼
Patched first-boot check
       │
       ▼
Existing offline game path
       │
       ▼
      Game
```

The patch changes **one boot-state decision**. It does not recreate the original backend or simulate a server response.

---

# Current Status

The game can currently be made playable using a preserved version of the client and the restoration patch.

There are still some known issues:

* Extremely long initialization times
* Remaining popups from previous versions
* Minor lag spikes
* Compatibility problems on some newer Android devices

A ready-to-use working client for **normal playthrough and speedrunning** can be found in the [Releases](../../releases) section.

The currently working client uses an older version of the game that does not enforce the Google Play verification check used by newer versions.

---

# For Normal Users

## Want to Play?

The easiest option is to use one of the prepared releases.

Go to:

**[Releases](../../releases)**

and download the appropriate build.

If the provided release does not work on your device, please open an Issue and provide:

* Device model
* Android version
* Whether the device is rooted
* What happens when starting the game
* Any relevant logcat output

Please **do not assume that a newer Android device is automatically supported**. The game is an older 32-bit ARMv7 application, and newer devices may have compatibility limitations.

---

# Patching Your Own Copy

If you want to patch your own preserved copy instead of using a prepared release, the project provides tools for doing so.

The recommended method is the **Windows ADB Patcher**.

### Requirements

You will need:

* Windows 10 or later
* Android SDK Platform Tools (`adb`)
* Python 3 when using the Windows GUI source
* A rooted Android device or emulator
* A working `su` command
* USB or Wireless Debugging
* Support for running 32-bit ARMv7 applications

Check your device's supported ABIs with:

```bash
adb shell getprop ro.product.cpu.abilist
```

You should see `armeabi-v7a` somewhere in the output.

You can also check whether root is working with:

```bash
adb shell "su -c 'id'"
```

The expected result contains:

```text
uid=0(root)
```
# Android Studio Archive With all files

**[Release Working Directory · Kayraman1/Forza-Customs-Revived](https://github.com/Kayraman1/Forza-Customs-Revived/releases/tag/Working-Directory)**

---

# Supported Game Version

The patch currently intentionally supports **one specific game build**.

| Property         | Required value                                                     |
| ---------------- | ------------------------------------------------------------------ |
| Package          | `com.hutchgames.ccw`                                               |
| Game version     | `7.0.14670`                                                        |
| ABI              | `armeabi-v7a`                                                      |
| Library          | `lib/armeabi-v7a/libil2cpp.so`                                     |
| Library size     | `63,342,500 bytes`                                                 |
| Original SHA-256 | `60b21e2496852bb99d14377aa221a8a40a2b56ac7641c6d43ff4ffafbdf5909c` |
| Patched SHA-256  | `df16cadd7fc5e31e61561aed8fbc8ed79adbcbeb50b9b71af509b6a804686e6f` |

The patcher **will refuse unknown builds**.

This is intentional.

Do **not** force the patch onto another version just because the file looks similar. A different game version can have completely different code at the same offset.

---

# Required Game Files

To patch your own copy, you need a personally preserved, untouched copy of the supported game package.

The tested package contains:

```text
com.hutchgames.ccw.apk
config.armeabi_v7a.apk
UnityDataAssetPack.apk
manifest.json
```

The asset pack is large, so keep it together with the other split APKs.

**The original game files are not included in this repository.**

You must provide your own legitimately preserved copy.

---

# Windows ADB Patcher

The Windows GUI is the recommended way to apply the patch.

It does **not** rebuild or re-sign the APK.

Instead, it:

1. Checks that the device has root access.
2. Finds the installed game's native library.
3. Checks the exact library size and SHA-256.
4. Creates a backup of the original library.
5. Applies the four-byte patch.
6. Verifies the patched library.
7. Places it back into the installed game.
8. Verifies the installed result again.

The patcher also resolves the Android installation path automatically because Android changes the `/data/app/` path after reinstalling the application.

### Quick Start

Connect your device:

```bash
adb devices
```

Make sure it appears as:

```text
device
```

Then start the patcher:

```text
START_PATCHER.bat
```

Select your device, press **Check**, and approve the root request.

If the detected library is the supported original build, select:

**Apply Patch**

Wait for:

```text
PATCH APPLIED AND VERIFIED
```

You can then launch the game.

---

# Why Do I Need Root?

The recommended method intentionally leaves the original APK files untouched.

Android extracts the game's native library into its installed application directory.

The patch is then applied to that extracted library **after installation**.

Writing to another application's `/data/app/` directory requires root access. Normal ADB access is not sufficient.

This approach also avoids modifying and re-signing the APKs, which can cause the game's PairIP signature protection to reject the modified package.

---

# What Exactly Is Being Patched?

Only one small change is made.

The patch targets:

```text
lib/armeabi-v7a/libil2cpp.so
```

At file offset:

```text
0x12B74A8
```

The original bytes are:

```text
00 10 A0 E1
```

They are changed to:

```text
00 10 A0 E3
```

This changes:

```text
mov r1, r0
```

into:

```text
mov r1, #0
```

The value is used by the game's boot sequence to determine the first-boot state.

The patch therefore makes the game take its already-existing offline-player path instead of entering the dead first-session registration flow.

---

# What This Patch Does NOT Do

This is important.

The patch does **not**:

* Recreate the original Hutch backend
* Change the server hostname
* Fake a registration response
* Disable all online functionality
* Remove Google Play verification
* Remove APK signature protection
* Change the game's signing certificate
* Add missing game assets
* Provide ARM64 support
* Add or create save progress

It only changes the first-boot decision required to reach the existing offline game path.

---

# Save Data

The game has been observed creating these external files:

```text
/sdcard/Android/data/com.hutchgames.ccw/files/user.dat
/sdcard/Android/data/com.hutchgames.ccw/files/deviceid.dat
```

You should **always back up your save before uninstalling or modifying an existing installation**.

For example:

```bash
adb pull /sdcard/Android/data/com.hutchgames.ccw/files/user.dat forza-save-backup\
adb pull /sdcard/Android/data/com.hutchgames.ccw/files/deviceid.dat forza-save-backup\
```

Copying save files alone does not completely reproduce an Android installation. Android also tracks things such as:

* Package signatures
* App UID
* Split APK membership
* Native-library extraction
* Permissions
* ABI compatibility

Therefore, install the game normally on the destination device first, then restore the save if appropriate.

---

# Troubleshooting

## The game still shows the Internet connection popup

Check that the installed library is actually patched.

The expected patched SHA-256 is:

```text
df16cadd7fc5e31e61561aed8fbc8ed79adbcbeb50b9b71af509b6a804686e6f
```

If the game was reinstalled after patching, you must patch it again because Android extracts a fresh copy of the original library.

---

## The game gets stuck on the splash screen

If you modified, repacked, or re-signed the APKs, restore the untouched original split package.

During testing, re-signing the APKs caused PairIP-related startup failures.

---

## `INSTALL_FAILED_UPDATE_INCOMPATIBLE`

This normally means an existing installation has a different signing certificate.

Back up your save and remove the existing installation before installing the preserved split set.

---

## My device does not support ARMv7

The current supported build is an ARMv7 application.

Rooting a device does **not** add a missing 32-bit runtime.

If your device cannot run `armeabi-v7a` applications, this version of the project will not currently work on it.

---

# Preservation

This project is intended to help preserve a game that can no longer initialize normally through its original service.

The project does **not** distribute the original game. Only a patched version

---

# Contributing

If you have a device on which the game does not work, **please open an Issue**.

Useful information includes:

```text
Device:
Android version:
Rooted:
Game version:
What happens:
Relevant logcat:
```
---

# Roadmap

* [x] Identify the dead first-session registration path
* [x] Identify the existing offline-player path
* [x] Develop a working first-boot patch
* [x] Create hash-checked patching tools
* [x] Create Windows ADB patcher
* [x] Create root-based Android patcher
* [x] Release working client
* [ ] Improve initialization time
* [ ] Remove remaining obsolete popups
* [ ] Improve newer Android compatibility
* [ ] Support additional game versions
* [ ] Investigate ARM64 compatibility
* [ ] Continue device testing

---

# Disclaimer

Forza Customs Revived is an **independent community preservation project**.

This project is not affiliated with or endorsed by Hutch Games, Forza, Microsoft, Xbox, Google, or any other rights holder.
Nor do we make any type of income/Ad Money from this Project
The project provides tools and documentation intended for preservation and interoperability research. You are responsible for ensuring that your use of the project and any game files you provide complies with applicable laws and licence terms.

---

# Support the Project

If this project helped you bring Forza Customs back to life and you'd like to support continued development, you can optionally support the project through the link below:

https://streamelements.com/kayraman1/tip

Support is completely optional and please take care of your needs first

---

# Credits

**Forza Customs Revived** is a community-driven preservation project.

Thank you to everyone who has helped with:

* Testing
* Reverse engineering
* Device compatibility
* Save preservation
* Documentation
* Development
* Speedrunning
* Keeping Forza Customs alive

And Special Thanks to :
EmiliaPlays for Helping with creation of a working APK
Sappytron,AllanEndopay and Shawn for Maintaining the SRC Forza Boards
---

## ~John Gauntlet

**Bringing Forza Customs back from the grave.**
