# Running ARTEMIS on the Android phone it controls (experimental)

**Status: experimental, not an officially supported deployment target.** The upstream quick-start is written for a Linux/macOS/Windows host with ADB, FFmpeg, scrcpy, Python 3.12+, and optional Node-based UI build tooling. It does not currently provide a first-party Termux installer. This guide describes a phone-only experiment; it is not a claim of verified compatibility with every Android/OEM build.

## Recommended layout

Use Termux as the entry point, and run ARTEMIS inside an Ubuntu userland provided by `proot-distro`. The Ubuntu userland gives Python packages a glibc Linux environment, which is generally easier for scientific/media dependencies than installing the full Python dependency graph directly into Termux's Android/Bionic environment.

The ARTEMIS controller process and the Android device are still on the same physical phone. ARTEMIS uses ADB's local server at `127.0.0.1:5037`; the device is registered with that server through Android Wireless debugging. Wireless ADB self-connection has worked in community-tested setups, but OEM builds can differ, so treat the ADB smoke test below as a gate, not an assumption.

## Requirements and cautions

- Android 11 or newer with **Developer options → Wireless debugging**. This is a local ADB setup, not a remote cloud service.
- Enough free storage/RAM for an Ubuntu userland, Python environment, and native dependencies.
- A supported remote model provider API key. The orchestration runs locally, but model inference may run remotely and consume network/data/API budget.
- Keep the phone unlocked during initial setup. Android 12+ and some OEMs can kill long-running Termux processes; disable battery optimization for Termux and keep it in the foreground for the first test.
- This setup can observe and operate other apps. Start with read-only tasks. Do not aim agents at banking, payment, password-manager, or other sensitive apps.
- Do not expose the ARTEMIS web/admin server or ADB ports to a public network. Keep API keys in a local, ignored `.env` file. Turn Wireless debugging off and revoke pairings when finished.

## 1. Install Termux and prepare the userland

Install Termux from its official [GitHub releases](https://github.com/termux/termux-app/releases) or [F-Droid listing](https://f-droid.org/packages/com.termux/). Do not mix APKs/plugins from different signing sources.

In Termux:

```bash
pkg update && pkg upgrade
pkg install git proot-distro
termux-wake-lock
proot-distro list
```

Choose the available Ubuntu distro entry from `proot-distro list`, then install and enter it (the alias may vary by Termux version):

```bash
proot-distro install ubuntu
proot-distro login ubuntu
```

Inside Ubuntu, install the host tools:

```bash
apt update
apt install -y ca-certificates curl git python3 python3-venv ffmpeg android-tools-adb
```

Install the repository's required Python version in this userland with uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
sed -n '1,220p' /tmp/uv-install.sh
sh /tmp/uv-install.sh
. "$HOME/.local/bin/env"
uv python install 3.12
```

Review downloaded installer scripts before executing them. Package names and availability depend on the Ubuntu release; fix package errors explicitly rather than running the standard desktop installer.

## 2. Pair ADB with this same phone

Keep these commands in the **same Ubuntu userland** where ARTEMIS will run so its local ADB server and the CLI share state.

1. On Android, open **Settings → Developer options → Wireless debugging** and enable it.
2. Tap **Pair device with pairing code**. Keep the dialog open; its pairing port is different from the normal connection port.
3. In Ubuntu/Termux, run the command using the current pairing endpoint shown by Android:

   ```bash
   adb pair 127.0.0.1:PAIRING_PORT
   ```

   Enter the temporary pairing code when prompted. Replace the placeholder with the displayed port; do not type the placeholder literally.
4. Return to the main Wireless debugging screen and use its current **IP address & Port** as the connect endpoint (a different port):

   ```bash
   adb connect 127.0.0.1:CONNECT_PORT
   adb devices -l
   adb shell getprop ro.build.version.release
   ```

Expected result: the ADB device list contains the phone with status `device`, and the last command prints the Android release. If pairing/connection fails, stop here. Reopen Wireless debugging, check the current ports, and try the displayed IP address instead of `127.0.0.1` if supported on your OEM build. Do not proceed until the test passes.

This self-connection route is community-documented, not a Google-supported way of running the ARTEMIS host on Android. See the [Android ADB documentation](https://developer.android.com/tools/adb) and [Termux ADB self-connect notes](https://gist.github.com/WuhDaFak/dd4415150bf8cb1e38d5ca23a726ec63).

## 3. Install ARTEMIS in Ubuntu

Clone the fork:

```bash
git clone https://github.com/looloofy69-sketch/artemis.git
cd artemis
uv sync --dev --locked --python 3.12
```

The dependency installation can still fail because package wheel availability changes with Python/architecture, and some optional media/device tools expect a desktop host. If it fails, retain the complete error and address the specific missing wheel/library. Do **not** run `start.sh` blindly in Termux: its Linux installer assumes conventional Linux package managers and attempts to manage host tools including scrcpy; Termux is not a conventional Linux desktop distribution.

Create local configuration, then edit `.env` to set one supported LLM provider key. Never commit it:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Set `ADB_HOST=127.0.0.1` and `ADB_PORT=5037` for the local ADB server. Supply exactly one provider key needed for your chosen model. Verify `.env` is ignored by Git before storing a secret:

```gitignore
.env
```

Check with `git check-ignore .env`. If it is not ignored, do not enter the key until repository ignore rules are corrected.

## 4. Validate in increasing-risk order

Start with diagnostics:

```bash
uv run artemis doctor
uv run artemis status
```

Then run one read-only task, staying present to observe the phone:

```bash
uv run artemis run "Open Settings, read the Android version, then stop without changing any settings." --profile pro
```

If the UI or recording path reports missing desktop dependencies, do not treat that as proof the device connection is broken. First establish whether the CLI agent path works with video features disabled (where supported by the CLI options) and add optional media support only when needed.

For the web console, build the frontend using the Node version required by `apps/showcase_ui` and its locked npm dependencies, start the ARTEMIS UI service, and navigate on the same phone's browser to `http://127.0.0.1:8000`. The web UI build is optional for the first CLI/device smoke test.

## 5. What is and is not proven

**Potentially feasible:** running Python orchestration locally in an Android-hosted Linux userland, using a remote model API and ADB self-connection to control the same phone.

**Not yet proven by this repository:** a clean install on Termux/Ubuntu PRoot, reliable self-ADB pairing on a specific OEM, long-running stability under Android process management, all media/recording features, and production-grade background operation.

A proper first-party implementation should add a Termux-specific setup path, a dependency profile that separates required runtime packages from desktop-only recording/UI features, ADB self-connection diagnostics, and a real-device acceptance test on supported Android/OEM versions. Do not advertise full Android-host support until those tests pass.


## 6. First-party ARTEMIS Runtime APK (phone-local control path)

The repository now contains a native Android runtime app under `packages/artemis-accessibility-helper`. It exposes an authenticated loopback API on `127.0.0.1:18888`, creates its own pairing token on the phone, and supports a direct Python client selected with `ARTEMIS_ON_DEVICE_RUNTIME=1`. This path does **not** depend on ADB pairing to discover a device for routine screen/gesture interactions.

### Get and install the APK

1. Open the repository's Pull Requests page and select the open **ARTEMIS launch-readiness** PR. Open its **Actions** run for `Android Runtime APK` after GitHub Actions finishes.
2. Download the artifact named `artemis-runtime-root-dev-debug-apk` and extract `app-debug.apk` on the phone. If the workflow is unavailable or no run exists, Actions may be disabled for the fork; enable Actions in repository Settings and trigger the branch workflow.
3. Install the APK. Android may ask you to allow installation from the browser/file manager used to download it.
4. Open **ARTEMIS Runtime** → **Open Accessibility settings** → enable the ARTEMIS Runtime service. Return to the app and tap **Refresh runtime status**. It should report the service as running and display the local API endpoint.
5. Tap **Copy token**. The token is a credential: do not post it in a public issue, commit it to Git, or include it in screenshots. If you rotate the token, update the environment variable used by the controller.

**Signing note:** the previous public repository included a debug signing keystore. It has been removed from the branch. New CI debug APKs may have a different debug signature; if Android refuses to install the new APK over an older `com.artemis.helper` build, uninstall the old helper first, then install the new APK. Uninstalling clears that app's private preferences and token. This CI artifact is for development/testing, not a production release; a stable release must use a private release-signing key that is not committed to the repository.

### Connect ARTEMIS's Python controller without ADB pairing

Run ARTEMIS inside the same phone-hosted Ubuntu/Termux environment described above. You still need the Python environment and dependencies from `uv sync`, and the `adb` executable must be installed because parts of the existing agent initialization still check for it. In phone-local mode the target device identity is synthetic; no ADB device must be paired.

In the Ubuntu terminal:

```bash
export ARTEMIS_ON_DEVICE_RUNTIME=1
export ARTEMIS_RUNTIME_URL=http://127.0.0.1:18888
export ARTEMIS_RUNTIME_TOKEN='PASTE_THE_TOKEN_COPIED_FROM_ARTEMIS_RUNTIME'
# Configure one supported model provider, for example:
export GEMINI_API_KEY='YOUR_PROVIDER_KEY'

uv run artemis run \
  "Open Settings, read the Android version, and stop without changing anything." \
  --profile flash \
  --without-video-recording-tools
```

Replace both credential placeholders with real values in your private shell. Do not paste API keys or runtime tokens into this documentation or your Git repository. When you close the shell, exported variables are lost unless you store them securely in a local ignored `.env` file.

### Capability tiers

**Stock Android, no root:** the app can use the AccessibilityService APIs after you explicitly enable the service. The intended first tier includes hierarchy/screenshot capture (screenshot API requires Android 11+ and can still be denied), taps, swipes, supported global actions, text/clipboard operations, and launching an installed app. This is not unrestricted system access; password-protected/secure surfaces, OS restrictions, and apps that hide accessibility content remain limitations.

**Rooted Android (this development branch):** this branch intentionally restores the first version's root-enabled path for owner-operated testing. The app requires the user to test `su` access and explicitly enable Root Mode before an authenticated local controller can execute shell commands as root. The Root Mode switch is process-local and returns to disabled when the app process exits or restarts; root availability is a cached diagnostic and is not a grant of root by itself. Root Mode is still dangerous: a controller holding the pairing token can issue commands that alter files, settings, and system state. Keep Root Mode off except during a deliberate test, keep the token private, and never use this debug build for sensitive daily-phone use. Stock Android remains unrooted; ARTEMIS cannot grant itself root. The separate standard branch does not package the root executor.

**True privileged/system-app access:** on stock Android, an ordinary installed APK cannot grant itself signature/privileged permissions. A system-signed or privileged deployment requires a compatible custom/system image and its permission allowlist (or a separately provisioned enterprise device-owner configuration for the device-policy capabilities it supports). The current app does not modify the system partition, unlock the bootloader, root the phone, or bypass Xiaomi/Android security.

### Native runtime capabilities and MCP tools

The root-enabled development branch now routes ARTEMIS's MCP action layer through a first-party `OnDeviceRuntimeActuator` when `ARTEMIS_ON_DEVICE_RUNTIME=1`. The canonical action schemas remain shared with the usual actuator; the device-control path for this mode uses the phone's local AccessibilityService endpoint rather than an ADB-forwarded helper.

Supported phone-local tools include the standard click/long-press/swipe/text/global-action actions, app launch by visible launcher label or package name, opening HTTP(S) links, clearing text, and deleting one Unicode code point from a focused **non-password** editable field. The phone-local MCP backend additionally advertises:

- `get_runtime_capabilities` — read what this runtime build reports it can do.
- `get_device_info` — Android release/SDK, device model, screen dimensions/rotation, ABIs and foreground activity/package.
- `list_apps` — discover launchable apps exposed by Android's package-visibility rules; this is not an inventory of hidden/non-launchable packages.
- `open_settings` — navigate to an allowlisted Settings page (Accessibility, applications, display, Wi-Fi, Bluetooth, developer options, location, notifications, sound or date/time). The person still confirms changes in Android Settings.

The native API rejects out-of-display touch coordinates and bounds gesture duration. Key actions are deliberately limited: Home/Back/Recents/notifications/quick settings and other declared Accessibility global actions work where Android permits them; Enter invokes the focused field's IME action only on Android 11+; Delete is refused for password or non-focused fields.

**Still unavailable without ADB/root or extra Android provisioning:** arbitrary shell commands, force-stop, silently granting permissions, controlling secure/hidden surfaces, and video recording through scrcpy. Android's screenshot API requires Android 11+ and can still be denied. ARTEMIS does not gain root because the Root Mode button exists; this phone's root probe reported unavailable, so root commands should be treated as unavailable. App listing and app launch availability also depend on OEM/package visibility policy.

This is an experimental integration. The APK compiling does not validate the MCP path on the actual phone: verify runtime capability discovery, diagnostics, one harmless app launch, read-only screen observation, and one reversible gesture before running any model-driven multi-step task. If a model/tool calls an unsupported capability, the correct result is a typed failure rather than falling back to an unpaired ADB command.


### Play Protect and debug build

The CI APK from this branch is a development/debug artifact, not a store-reviewed or production-signed release. This root-enabled variant combines an AccessibilityService and local UI-control API with optional root-shell execution; it is a high-privilege test build, not a production recommendation. Keep Play Protect enabled. If it blocks the APK, do not bypass the warning merely to install it; verify the artifact source/hash and investigate or appeal a false-positive through Google's official Play Protect/App verification support flow. A successful build does not mean Google has classified the app as safe.
