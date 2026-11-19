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

Glowback reads the screen image in memory to compute the LED colors, many times per second. It never saves or sends it.

## Files on your computer

`%LOCALAPPDATA%\Glowback` holds your settings (`settings.json`) and the log of the last session (`glowback.log`). If you connect Home Assistant, the settings also hold the broker address and user name, and the password encrypted for your Windows account. Uninstalling Glowback removes this folder, the startup entry and the Start menu shortcuts, and removes Glowback from Home Assistant. For the portable and Python versions, `glowback --uninstall` does the same.

## Changes

This policy is part of the Glowback repository: its history shows every change.
