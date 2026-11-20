# Privacy policy

Glowback runs on your computer. It has no account, no telemetry, no analytics and no ads, and it collects no personal data.

## Network

| When | Where | What is sent | Turn it off |
|---|---|---|---|
| About 30 seconds after Glowback starts, then once a day. On by default | `api.github.com`, to read the latest release | An HTTPS request with the user agent `Glowback/<version>` | Untick *Check for a new version once a day* in the installer, switch off *Check automatically* in Glowback's panel, or run `glowback --check-updates off` |
| When you click *Check for updates* or *Update to …* | `api.github.com` and `github.com`, to read the latest release and download it with its `SHA256SUMS.txt` | HTTPS requests with the same user agent | Only happens when you click |
| When OpenRGB runs on your PC, or when you use `--openrgb` | The OpenRGB SDK server on your PC (`127.0.0.1:6742`) or the address you gave | Requests for the device list, then LED colors | `--openrgb off` |
| Only after you connect Home Assistant (*Home Assistant* in Glowback's panel, or `--home-assistant`), while Glowback runs | Your MQTT broker, at the address you entered (usually the Mosquitto broker app of Home Assistant) | The user name and password you entered; on/off, brightness, mode and LED count; the installed and latest Glowback versions; an ID for this PC (10 characters of a one-way hash of the Windows machine ID) so Home Assistant can tell your PCs apart | *Disconnect* in the *Home Assistant* window, or `glowback --home-assistant off`: Glowback also removes itself from Home Assistant |

GitHub sees your IP address with its requests, as with any website: see the [GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Glowback sends GitHub nothing else: no device list, no screen content, no identifier.

The Home Assistant connection uses plain MQTT, as usual on a home network, unless you enter an `mqtts://` address for TLS.

## Screen

Glowback reads the screen image in memory to compute the LED colors, many times per second. While its window shows the *Ambient light* page, a small copy of the picture (about 400 pixels wide) appears in the preview. Glowback never saves or sends either of them.

## Apps and windows

Only if you add apps on the *Profiles* page (or with `--sync-when`), Glowback checks four times a second which app is in front, whether it is full screen, which apps are running, which screens their windows are on and, for the *Plays sound* condition, which apps play sound (their volume meters), to know what the LEDs show. When you open the list of apps on that page, it reads the names and icons of the apps with an open window. All of this stays on your computer: Glowback keeps only the apps you add, and sends nothing.

## Sound

Only while the *Music* look shows, Glowback listens to what Windows plays on its default output (the sound you hear, never a microphone) to compute the LED colors 30 times a second. The sound is analysed in memory and dropped right away: it is never recorded, saved or sent. Ten seconds after the Music look ends, Glowback stops listening.

## Files on your computer

`%LOCALAPPDATA%\Glowback` holds your settings (`settings.json`) and the log of the last session (`glowback.log`). The settings include your colors, your profiles and the apps you add, with each app's name and file path. If you connect Home Assistant, the settings also hold the broker address and user name, and the password encrypted for your Windows account. Uninstalling Glowback removes this folder, the startup entry and the Start menu shortcuts, and removes Glowback from Home Assistant. For the portable and Python versions, `glowback --uninstall` does the same.

## Changes

This policy is part of the Glowback repository: its history shows every change.
