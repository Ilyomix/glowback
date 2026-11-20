<p align="center">
  <img src="assets/banner.svg" alt="Glowback: ambient light for the RGB LEDs on the back of your monitor, each LED synced to the screen in real time" width="100%">
</p>

<h1 align="center">Glowback</h1>

<p align="center">
  <b>Ambient light for monitors with RGB LEDs on the back.</b><br>
  A free, open-source Windows app: each LED follows the picture in front of it, in real time, on Windows 11 Dynamic Lighting and OpenRGB devices.
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Ilyomix/glowback?label=release&color=8b6cff"></a>
  <a href="https://github.com/Ilyomix/glowback/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/Ilyomix/glowback/total?color=00ccff"></a>
  <a href="https://github.com/Ilyomix/glowback/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/Ilyomix/glowback/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Windows 10 and 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-3ddc97"></a>
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe"><b>⬇ Download for Windows</b></a>
  &nbsp;·&nbsp; <a href="https://ilyomix.github.io/glowback/"><b>Website</b></a>
</p>

<p align="center">
  <b>English</b> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.de.md">Deutsch</a> · <a href="README.it.md">Italiano</a> · <a href="README.pt.md">Português</a>
</p>

---

More and more gaming monitors ship with RGB LEDs on the back, but their software only offers static, breathing or rainbow effects. **Glowback** turns those LEDs into **real ambient light**: it captures your screen 30 times per second and gives **each LED its own color**, taken from the edge of the picture right in front of it. A sunset on the left of the screen turns the wall on the left orange; an explosion on the right lights the right side.

Glowback is not tied to one brand. It drives any LED device that **Windows Dynamic Lighting** (the HID LampArray standard) or **[OpenRGB](https://openrgb.org)** can control: monitors, LED strips, PC cases, lamps. No compatible LEDs? [Add a $5 DIY strip](docs/DIY-LED-strip.md).

## ✨ Features

- 🎯 **One zone per LED**: each LED is projected onto the nearest screen edge, so the light around your monitor matches the picture. A single "average color" mode is also available.
- 🎨 **Colors, gradients and music**: besides the screen, show one color, a gradient (still or flowing), or let the LEDs follow the sound your PC plays: pulse, spectrum or waves.
- 🎬 **Movies, games, HDR**: GPU capture (DXGI) sees fullscreen video and games, handles HDR, and **ignores movie black bars**.
- 💡 **Bright, true colors**: a hue-preserving brightness curve keeps the glow visible in dark scenes.
- 🪟 **A real Windows app**: a window with a live preview of your screen and your LEDs, quick settings from the icon next to the clock, installer, Start menu, start with Windows, and clean uninstall from *Settings → Apps*.
- 🌙 **Profiles**: a softer light at night, at the hours you choose, and a look for each app: music while Spotify plays, the screen for games, blue in your code editor. Or follow the screen only while an app is open.
- 🔄 **Update notifications**: Glowback checks GitHub once a day and tells you when a new version is out. One switch turns it off.
- 📱 **Apple Home, Google Home & Alexa, without Home Assistant**: with Matter, Glowback is a light in your phone's Home app. Switch it, dim it and color it by hand, in scenes or by voice.
- 🏠 **Home Assistant, Google Assistant, Alexa & Siri**: Glowback shows up as a light you switch, dim and color from dashboards, automations or by voice.
- 🌍 **6 languages**: English, French, Spanish, German, Italian and Portuguese, picked from your Windows language.
- 🔌 **Plug and play**: finds Dynamic Lighting devices and OpenRGB automatically, and reads the physical position of every LED.
- 🖥️ **Multi-monitor**: each LED device follows its own screen (matched by the monitor's EDID name).
- 🎨 **White balance** per device, so the wall looks white when the screen is white.
- 🪶 **Lightweight**: about 0.5 ms of CPU per frame. The Python version is a single file with zero dependencies.

## 🚀 Install

1. **Connect the monitor's USB upstream cable** to the PC (USB-B or USB-C). Monitors usually need it so the PC can reach their LEDs.
2. **Turn off Windows Dynamic Lighting for that device**, otherwise Windows and Glowback fight over the LEDs: *Settings → Personalization → Dynamic Lighting → your device → "Use Dynamic Lighting on my devices" → Off*.
3. **Install Glowback:**

| | |
|---|---|
| **Installer (recommended)** | Download [**GlowbackSetup.exe**](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe) and follow the wizard. No admin rights needed. |
| Portable | [GlowbackTray.exe](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackTray.exe) (app) and [glowback.exe](https://github.com/Ilyomix/glowback/releases/latest/download/glowback.exe) (command line) |
| Python 3.9+ | `pip install git+https://github.com/Ilyomix/glowback`, then `glowback --install` |

Every release is built by [GitHub Actions](.github/workflows/release.yml) from this source code, tested (install and uninstall included) and published with SHA-256 checksums.

> **Code signing**: Glowback is applying for [SignPath Foundation](https://signpath.org/)'s free code signing for open source; the Windows files will be signed through it once the project is accepted. Until then Windows SmartScreen may warn about an unknown publisher: click *More info → Run anyway*. [Code signing policy](CODE_SIGNING.md) · [Privacy policy](PRIVACY.md)

Glowback then sits next to the clock. To check the LED orientation, use *Start menu → Glowback tools → Test the LEDs*: left must be red, right blue.

## ✅ Does my monitor work?

Glowback works with your monitor (or LED strip, case, lamp…) if **one** of these is true:

1. **It appears in Windows** under *Settings → Personalization → Dynamic Lighting*. Glowback drives it directly.
2. **It is supported by [OpenRGB](https://openrgb.org)**. Start OpenRGB with its SDK server and Glowback picks it up automatically.
3. **Neither?** Stick an LED strip behind the screen and drive it with a $5 RP2040 board: [DIY guide](docs/DIY-LED-strip.md).

Run `glowback --list` (or check the tray menu status) to see what Glowback found.

**Tested devices**

| Device | LEDs | How | Status |
|---|---|---|---|
| AOC AGON PRO AG276QZD2 | 47 | Dynamic Lighting | ✅ Tested |
| *Your monitor?* | | | [Add it](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) |

Got it working on another monitor? Open a [device report](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) with your `glowback --list` output and a short video. Every report adds a line to this table.

## 🪟 The app

<p align="center"><img src="docs/img/app-en.webp" width="760" alt="Glowback's window: a live preview of the screen and the light behind it, the five looks and the brightness"></p>

Start Glowback from the Start menu and its window opens. Close it and Glowback keeps running in the background: double-click its icon next to the clock to bring the window back, or click it once for a quick panel.

- **Ambient light**: a live preview of your screen and of the light your LEDs throw on the wall, the on/off switch, the [look](#-looks) (screen, average, color, gradient or music) and the brightness
- **Profiles**: a [night profile and a look per app](#-profiles)
- **Home Assistant**: connection status and setup, what Home Assistant sees, voice assistants
- **Apple & Google**: Glowback as a [Matter light](#-apple-home-google-home-and-alexa) in Apple Home, Google Home or Alexa: its pairing code and the apps it is paired with
- **Settings**: start with Windows, updates (now, or automatically once a day), interface language, log
- **About**: version, website, source code, report a problem

When paused, the LEDs go back to the device's own effect. Settings are remembered. Extra tools are in the Start menu: *Test the LEDs* and *Calibrate the white balance*.

## 🎨 Looks

Glowback does more than follow the screen. On the **Ambient light** page, pick what the LEDs show:

| Look | What the LEDs show |
|---|---|
| **Screen** | Each LED follows the part of the picture next to it (the default) |
| **Average** | One color for all the LEDs: the screen's average |
| **Color** | One color: 10 swatches, or any hue and saturation |
| **Gradient** | 2 to 4 colors from left to right, still or slowly flowing, and 6 presets |
| **Music** | The LEDs follow the sound your PC plays: **Pulse** (they all beat together), **Spectrum** (bass at the bottom, treble at the top) or **Waves** (each beat sends light up both sides). Their colors: a rainbow, the screen's colors, your color or your gradient |

<p align="center"><img src="docs/img/looks-en.webp" width="760" alt="The Music look: the LEDs beat with the sound, in rainbow colors, with its style and sensitivity"></p>

The Music look listens to what Windows plays on its default output (Spotify, YouTube, games...), in memory: no microphone, nothing recorded or sent. From the command line: `glowback --mode color --color "#2864FF"`, `glowback --mode gradient --gradient "#FF326E,#FFDC3C"` or `glowback --mode music`.

## 🌙 Profiles

On the **Profiles** page, the look changes by itself:

- **Night profile**: from 22:00 to 07:00 (your hours), a lower brightness and, if you like, another look, a warm white for example.
- **By app**: a look for each app, while it **is running**, **is in front**, **is full screen** (on a given screen) or **plays sound**. *Auto* keeps the look of the Ambient light page.
- **The rest of the time**: when none of these apps matches, keep the Ambient light page's look, give the LEDs back their own effect, or turn them off.

<p align="center"><img src="docs/img/profiles-en.webp" width="760" alt="The Profiles page: a night profile from 22:30 to 07:00 at 35 %, and a look for Spotify, full-screen games and Notepad"></p>

| App | When | Look |
|---|---|---|
| Spotify | Plays sound | Music · Pulse |
| Any app | Is full screen on the LED screen | Screen |
| Visual Studio Code | Is in front | Blue |

The first app of the list that matches wins, and the night profile's brightness applies to all of them. Glowback checks four times a second and recognizes Store apps (Netflix, Disney+...) too.

From the command line, Glowback can follow the screen only while one of these holds, the LEDs showing their own effect the rest of the time (saved; a running Glowback follows within 2 seconds):

```
glowback --sync-when foreground:vlc.exe --sync-when "fullscreen:*@leds" --sync-when playing:spotify.exe
glowback --sync-when always
```

## 🏠 Home Assistant & Google Assistant

Glowback can show up in [Home Assistant](https://www.home-assistant.io) as a light: switch, dim or color the ambient light from your dashboards and automations, or by voice with Google Assistant, Alexa and Siri.

1. **In Home Assistant**: *Settings → Apps → Install app → Mosquitto broker*, install it and start it. Home Assistant then offers the **MQTT** integration in *Settings → Devices & services*: add it.
2. **A user for Glowback** (recommended): *Settings → People → Users → Add user*, for example `glowback`. If you don't see *Users*, turn on *Advanced mode* in your profile.
3. **In Glowback**: open the panel, click **Home Assistant**, enter the address (`homeassistant.local` usually works, or the IP of Home Assistant), the user and its password, then **Connect**.

Glowback then appears in *Settings → Devices & services → MQTT*:

| Entity | What it does |
|---|---|
| `light.glowback` | On/off = ambient light, brightness, color (choosing one switches to the Color look), and the look as an effect (*Zones*, *Average*, *Color*, *Gradient* or *Music*) |
| `sensor.glowback_leds` | Number of LEDs Glowback drives |
| `update.glowback` | Shows when a new version is out, and installs it |

It shows as *unavailable* while the PC is off or Glowback is closed. The password is encrypted for your Windows account and only sent to your broker.

**Google Assistant**: with [Home Assistant Cloud](https://www.nabucasa.com), open *Settings → Voice assistants → Expose* and expose **Glowback**, then say *"Hey Google, turn off Glowback"*, *"Hey Google, set Glowback to 50%"* or *"Hey Google, make Glowback blue"*. Without the subscription, follow Home Assistant's [manual Google Assistant setup](https://www.home-assistant.io/integrations/google_assistant/). Alexa works the same way.

**Siri and Apple Home**: add Home Assistant's [HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/) integration (*Settings → Devices & services → Add integration*; the *Light* domain is enough). Then, in the Home app on your iPhone, tap *Add Accessory* and scan the pairing code Home Assistant shows in its notifications. Say *"Hey Siri, turn off Glowback"*, *"Hey Siri, set Glowback to 50%"* or *"Hey Siri, set Glowback to blue"*. Apple Home has no light effects, so the other looks stay in Glowback's app and in Home Assistant.

Example automation, ambient light off at midnight:

```yaml
automation:
  - alias: Glowback off at night
    triggers:
      - trigger: time
        at: "00:00:00"
    actions:
      - action: light.turn_off
        target:
          entity_id: light.glowback
```

From the command line: `glowback --home-assistant mqtt://glowback:PASSWORD@homeassistant.local` (`mqtts://` for TLS on port 8883, `off` to remove Glowback from Home Assistant).

## 📱 Apple Home, Google Home and Alexa

Glowback can also be a **Matter** light, without Home Assistant: your phone's Home app switches it, dims it and changes its color, by hand, in scenes and automations, or by voice with Siri, Google Assistant or Alexa.

1. **In Glowback**: open the **Apple & Google** page and turn on **Matter light**. A QR code and an 11-digit code show up for 15 minutes. Windows may ask to let Glowback through its firewall: allow it (installed for all users, Glowback already lets in the devices of your local network).
2. **On your phone**, on the same network as the PC:
   - **Apple Home**: tap **+** → *Add Accessory* and scan the QR code (or *More options…* and type the code). Glowback is not certified by the Connectivity Standards Alliance, so Apple Home says *Uncertified Accessory*: tap *Add Anyway*.
   - **Google Home**: Google only adds uncertified devices to accounts set up for testing. Once, in the [Google Home Developer Console](https://console.home.google.com): create a project, then a **Matter integration** with vendor ID `0xFFF1` and product ID `0x8000`. Then, in the Google Home app signed in with the same account: *Devices → Add → Matter-enabled device*, and scan the code.
   - **Other Matter apps** (Alexa, SmartThings, Home Assistant's Matter integration…): add a Matter device and scan the code, if the app accepts uncertified devices.
3. **A second app** (Google Home after Apple Home, say): click **Pair a phone** in Glowback and scan again from the other app. Or share the light from the first app (Apple Home: the light's settings → *Turn On Pairing Mode*) and type that code in the other one.

| In the phone's app | In Glowback |
|---|---|
| On / off | Ambient light on / paused |
| Brightness | Brightness |
| A color or a white | The Color look, in that color |
| Identify | The LEDs blink white |

The other looks (screen, gradient, music) and the profiles are chosen in Glowback; the phone still turns them on and off and sets their brightness. The light shows as unavailable while the PC sleeps or Glowback is closed.

Everything stays on your network: Glowback answers on UDP port 5540 and announces itself with mDNS (port 5353). It keeps its pairings in `%LOCALAPPDATA%\Glowback\matter.json`, keys encrypted for your Windows account. To unpair an app, click **Remove** next to it; to hide the light, turn Matter off.

## 🗑️ Uninstall

- **Installed with GlowbackSetup.exe:** *Settings → Apps → Installed apps → Glowback → Uninstall*. Glowback stops, the LEDs go back to the device's own effect, and its startup entry, settings and logs are removed.
- **Python version:** run `glowback --uninstall`, then `pip uninstall glowback`.
- **Portable:** run `glowback.exe --uninstall`, then delete the .exe files.

To turn it off for a while, use the **Ambient light** switch in the tray menu. To stop it from starting with Windows, turn off **Start with Windows**.

## ⚙️ Command line

| Option | Default | Description |
|---|---|---|
| `--mode zones\|average\|color\|gradient\|music` | `zones` | The [look](#-looks): each LED its zone, one average color, a color, a gradient, or the sound |
| `--color #RRGGBB` · `--gradient #RRGGBB,#RRGGBB[,...]` | the app's | The color of the Color look, the 2 to 4 colors of the Gradient look |
| `--brightness 0-100` | `100` | LED brightness |
| `--boost` | `1.8` | Lifts dim colors without changing their hue (`1` = off) |
| `--saturation` | `1.25` | Color boost (`1` = true colors) |
| `--smoothing` | `0.1` | Transition time in seconds |
| `--radius` | `0.12` | Size of each LED's zone, as a fraction of screen height |
| `--blend 0-1` | `0` | Mixes the whole-screen average into each zone for a calmer glow |
| `--letterbox on\|off` | `on` | Ignore movie black bars |
| `--capture auto\|dxgi\|gdi` | `auto` | GPU capture (DXGI) with GDI fallback |
| `--fps` | `30` | Updates per second (devices may cap this) |
| `--screen` | `auto` | `auto`, `primary`, a number from `--list`, or a name |
| `--device` | ambient devices | Part of a name or `VID:PID`, or `all` to include keyboards and mice |
| `--openrgb [HOST:PORT\|off]` | `auto` | OpenRGB SDK server to use (auto-detected on this PC) |
| `--home-assistant mqtt://USER:PASSWORD@HOST\|off` | | Show Glowback in [Home Assistant](#-home-assistant--google-assistant) (saved) |
| `--sync-when WHEN:APP[@SCREEN]\|always` | | Follow the screen only while an app runs, is in front, is full screen or plays sound ([profiles](#-profiles); saved, repeatable) |
| `--strip-start` / `--strip-ccw` | `bottom-left` | Where OpenRGB LED strips begin, and their direction |
| `--mirror` / `--flip` | off | Swap left/right or top/bottom |
| `--calibrate` · `--white-balance R,G,B` | | Per-device white balance (interactive) or fixed multipliers |
| `--lang en\|fr\|es\|de\|it\|pt` | Windows language | Interface language |
| `--install` / `--uninstall` | | Add to or remove from Windows (startup, Start menu) |
| `--check-updates on\|off` | `on` | Look for a new version on GitHub once a day ([privacy](PRIVACY.md)) |
| `--list` · `--test` · `--stop` | | List devices and screens · test pattern · stop Glowback |
| `--diy-layout WxH:L,T,R,B` | | Print LED positions for the [DIY firmware](docs/DIY-LED-strip.md) |

## 🔬 How it works

```mermaid
flowchart LR
    A[Screen] -->|DXGI Desktop Duplication<br/>+ GPU mipmaps| B[80x45 color grid]
    B -->|black bars removed,<br/>Gaussian zone per LED| C[One color per LED]
    C -->|saturation, brightness curve,<br/>smoothing, white balance| D[HID LampArray / OpenRGB]
    D -->|USB| E[LEDs light the wall]
```

1. **Devices**: Glowback looks for HID interfaces with usage page `0x59` (*Lighting and Illumination*), usage `LampArray`, and reads their report layout from the HID descriptor, so there is no device-specific code. OpenRGB devices are reached through its SDK protocol.
2. **Geometry**: each LampArray LED reports its X/Y/Z position. Glowback projects every LED from the center onto the screen border. LED strips are laid out around the screen.
3. **Capture**: DXGI Desktop Duplication hands over each frame on the GPU, `GenerateMips` averages it down to about 80×45, and only that tiny image is read. HDR frames (FP16 scRGB) are converted using your *SDR content brightness* setting.
4. **Output**: colors are smoothed and sent in `LampMultiUpdateReport`s after switching the device out of `AutonomousMode`, which is restored on exit.
5. **Music**: WASAPI loopback reads what the default output plays; 30 times a second a 512-point FFT splits it into 14 frequency bands, with an automatic gain and beat detection, all in plain Python.

The whole program is one readable file: [`glowback.py`](glowback.py).

## ❓ FAQ

### Which monitors are supported?
Any monitor whose rear RGB lighting can be controlled through Windows Dynamic Lighting or OpenRGB. Run `glowback --list`, or look for your monitor in *Settings → Personalization → Dynamic Lighting*.

### How do I sync my monitor's RGB lighting with what's on screen?
Install Glowback, turn off Windows Dynamic Lighting for the monitor, and you're done. The LEDs follow the picture from then on.

### Can I get screen-synced ambient light without an LED strip?
Yes, if your monitor already has rear RGB LEDs that Windows Dynamic Lighting or OpenRGB can control. Otherwise, the [DIY guide](docs/DIY-LED-strip.md) adds a strip for about $10.

### Does it work with HDR, fullscreen games and movies?
Yes. DXGI capture handles fullscreen and borderless games, video players and HDR desktops, and black bars are ignored. DRM-protected streams (for example some Netflix playback in browsers) are usually blacked out by Windows for every capture tool.

### Does it slow down my games?
It is built not to: the GPU does the downscaling, and Glowback uses about 0.5 ms of CPU per frame at 30 fps.

### Can the LEDs follow my music?
Yes. Choose the **Music** look: the LEDs pulse, show the spectrum or send waves with the sound your PC plays, from any app. To switch to it by itself, add a profile on the Profiles page: for example *Spotify · Plays sound · Music*.

### Nothing lights up.
Check that the monitor's USB upstream cable is connected to the PC, that its RGB lighting is enabled in the monitor's menu, and that Windows Dynamic Lighting is off for that device. The tray menu status and `glowback --list` show what Glowback sees.

### The colors are on the wrong side.
Use *Test the LEDs* in the Start menu (or `glowback --test`). If left and right are swapped, add `--mirror`. If top and bottom are swapped, add `--flip`.

## 🗺️ Roadmap

- [x] An app with a live preview, quick panel, installer, start with Windows, uninstall, update notifications
- [x] DXGI capture, HDR, letterbox detection
- [x] OpenRGB output (auto-detected), DIY RP2040 guide, white balance
- [x] 6 languages
- [x] Home Assistant, and through it Google Assistant, Alexa and Siri
- [x] Sync conditions: an app running, in front or full screen, on a given screen
- [x] Color, gradient and music looks; night and per-app profiles
- [ ] Code-signed installer and `winget install Glowback`
- [ ] Rotated (portrait) screens in DXGI capture
- [ ] Prebuilt RP2040 firmware (.uf2)

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## 🧩 Also by me

[**Keyboard Clock**](https://github.com/Ilyomix/keyboard-clock): the time in big digits on your RGB keyboard, for Logitech G, Razer, Corsair, ASUS, SteelSeries, HyperX and OpenRGB keyboards.

## ⭐ Support

If Glowback lit up your desk, **star the repo**. It helps other owners of RGB monitors find it.

---

<sub>Keywords: ambient light PC, monitor ambient lighting, screen sync RGB, bias lighting, monitor RGB sync with screen, gaming monitor RGB, Windows 11 Dynamic Lighting, HID LampArray, OpenRGB screen sync, rear RGB monitor, immersive lighting, HDR ambient light, ambilight alternative for PC, Hyperion alternative, Prismatik alternative, Home Assistant ambient light, Apple HomeKit, Siri, music reactive lighting, sound reactive RGB, audio visualizer LEDs.</sub>

<sub>Ambilight is a trademark of Koninklijke Philips N.V. / TP Vision. Other product names are trademarks of their respective owners. Glowback is an independent open-source project, not affiliated with or endorsed by them. Inter is licensed under the [SIL Open Font License](licenses/Inter-OFL.txt).</sub>

MIT © [Ilyomix](https://github.com/Ilyomix) · [Code signing policy](CODE_SIGNING.md) · [Privacy policy](PRIVACY.md)
