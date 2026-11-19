# Privacy policy

Glowback runs on your computer. It has no account, no telemetry, no analytics and no ads, and it collects no personal data.

## Network

| When | Where | What is sent | Turn it off |
|---|---|---|---|
| About 30 seconds after Glowback starts, then once a day. On by default | `api.github.com`, to read the latest release | An HTTPS request with the user agent `Glowback/<version>` | Untick *Check for a new version once a day* in the installer, switch off *Check automatically* in Glowback's panel, or run `glowback --check-updates off` |
| When you click *Check for updates* or *Update to …* | `api.github.com` and `github.com`, to read the latest release and download it with its `SHA256SUMS.txt` | HTTPS requests with the same user agent | Only happens when you click |
| When OpenRGB runs on your PC, or when you use `--openrgb` | The OpenRGB SDK server on your PC (`127.0.0.1:6742`) or the address you gave | Requests for the device list, then LED colors | `--openrgb off` |

GitHub sees your IP address with these requests, as with any website: see the [GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Glowback sends nothing else: no device list, no screen content, no identifier.

## Screen

Glowback reads the screen image in memory to compute the LED colors, many times per second. It never saves or sends it.

## Files on your computer

`%LOCALAPPDATA%\Glowback` holds your settings (`settings.json`) and the log of the last session (`glowback.log`). Uninstalling Glowback removes this folder, the startup entry and the Start menu shortcuts. For the portable and Python versions, `glowback --uninstall` does the same.

## Changes

This policy is part of the Glowback repository: its history shows every change.
