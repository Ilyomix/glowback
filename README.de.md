<p align="center">
  <img src="assets/banner-de.svg" alt="Glowback: Umgebungslicht für die RGB-LEDs auf der Rückseite deines Monitors, jede LED in Echtzeit mit dem Bild synchronisiert" width="100%">
</p>

<h1 align="center">Glowback</h1>

<p align="center">
  <b>Umgebungslicht für Monitore mit RGB-LEDs auf der Rückseite.</b><br>
  Eine kostenlose Open-Source-App für Windows: Jede LED folgt in Echtzeit dem Bild direkt vor ihr, auf Geräten für die dynamische Beleuchtung von Windows 11 und OpenRGB.
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest"><img alt="Neuestes Release" src="https://img.shields.io/github/v/release/Ilyomix/glowback?label=release&color=8b6cff"></a>
  <a href="https://github.com/Ilyomix/glowback/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/Ilyomix/glowback/total?color=00ccff"></a>
  <a href="https://github.com/Ilyomix/glowback/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/Ilyomix/glowback/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Windows 10 und 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4">
  <a href="LICENSE"><img alt="MIT-Lizenz" src="https://img.shields.io/badge/license-MIT-3ddc97"></a>
</p>

<p align="center">
  <a href="https://apps.microsoft.com/detail/9P1G8XDDQCN2"><img src="https://get.microsoft.com/images/de%20dark.svg" width="200" alt="Im Microsoft Store herunterladen"></a>
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe"><b>⬇ Für Windows herunterladen</b></a>
  &nbsp;·&nbsp; <a href="https://ilyomix.github.io/glowback/de/"><b>Website</b></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <b>Deutsch</b> · <a href="README.it.md">Italiano</a> · <a href="README.pt.md">Português</a>
</p>

---

Immer mehr Gaming-Monitore haben RGB-LEDs auf der Rückseite, doch ihre Software bietet nur statische, pulsierende oder Regenbogen-Effekte. **Glowback** macht daraus **echtes Umgebungslicht**: Es erfasst den Bildschirm 30-mal pro Sekunde und gibt **jeder LED ihre eigene Farbe**, genommen vom Bildrand direkt vor ihr. Ein Sonnenuntergang links im Bild färbt die linke Wand orange.

Glowback ist an keine Marke gebunden: Es steuert jedes Gerät, das die **dynamische Beleuchtung von Windows** (der HID-LampArray-Standard) oder **[OpenRGB](https://openrgb.org)** ansprechen kann: Monitore, LED-Streifen, PC-Gehäuse, Lampen.

## ✨ Funktionen

- 🎯 **Eine Zone pro LED**, projiziert auf den nächstgelegenen Bildschirmrand. Alternativ ein Modus mit einer Durchschnittsfarbe.
- 🎬 **Filme, Spiele, HDR**: GPU-Erfassung (DXGI) im Vollbild, HDR-fähig, **schwarze Balken werden ignoriert**.
- 💡 **Helle, natürliche Farben**, auch in dunklen Szenen.
- 🪟 **Eine echte Windows-App**: ein Fenster mit einer Live-Vorschau deiner LEDs, schnelle Einstellungen über das Symbol neben der Uhr, Installer, Startmenü, Start mit Windows und saubere Deinstallation unter *Einstellungen → Apps*.
- 🎨 **Farben, Verläufe und Musik**: neben dem Bildschirm eine Farbe, ein Verlauf (still oder in Bewegung) oder LEDs, die dem Ton deines PCs folgen: Puls, Spektrum oder Wellen.
- 🌙 **Profile**: nachts ein sanfteres Licht zu den Uhrzeiten deiner Wahl und ein Licht für jede App: Musik, während Spotify spielt, der Bildschirm für Spiele, Blau in deinem Code-Editor.
- 🔄 **Update-Hinweise** einmal am Tag (abschaltbar).
- 📱 **Apple Home, Google Home und Alexa, ohne Home Assistant**: mit Matter ist Glowback eine Lampe in der Home-App deines Handys. Seite *Apple & Google* in Glowback; Anleitung im [englischen README](README.md#-apple-home-google-home-and-alexa).
- 🏠 **Home Assistant, Google Assistant, Alexa und Siri**: Glowback erscheint als Licht, steuerbar über Dashboards, Automationen oder per Sprache.
- 🌍 **6 Sprachen**, passend zur Windows-Sprache.
- 🔌 **Plug and play**: findet Geräte mit dynamischer Beleuchtung und OpenRGB automatisch.
- 🪶 **Leichtgewichtig**: etwa 0,5 ms CPU pro Bild.

## 🚀 Installation

1. **Verbinde das USB-Upstream-Kabel des Monitors** mit dem PC (USB-B oder USB-C).
2. **Schalte die dynamische Beleuchtung von Windows für dieses Gerät aus**: *Einstellungen → Personalisierung → Dynamische Beleuchtung → dein Gerät → „Dynamische Beleuchtung auf meinen Geräten verwenden“ → Aus*.
3. **Installiere Glowback aus dem [Microsoft Store](https://apps.microsoft.com/detail/9P1G8XDDQCN2)**: Windows installiert und aktualisiert es, ohne SmartScreen-Warnung. Oder lade [GlowbackSetup.exe](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe) herunter und folge dem Assistenten (keine Administratorrechte nötig).

Jedes Release wird von [GitHub Actions](.github/workflows/release.yml) aus diesem Quellcode gebaut, getestet (Installation und Deinstallation inklusive) und mit SHA-256-Prüfsummen veröffentlicht.

> **Code-Signatur**: Glowback bewirbt sich um die kostenlose Code-Signatur der [SignPath Foundation](https://signpath.org/) für Open-Source-Projekte; die Windows-Dateien werden damit signiert, sobald das Projekt angenommen ist. Bis dahin warnt Windows SmartScreen eventuell vor einem unbekannten Herausgeber: klicke auf *Weitere Informationen → Trotzdem ausführen*. [Richtlinie zur Codesignierung](CODE_SIGNING.md) · [Datenschutz](PRIVACY.md)

Ausrichtung der LEDs prüfen: *Startmenü → Glowback-Werkzeuge → LEDs testen* (links rot, rechts blau).

## ✅ Funktioniert mein Monitor?

Ja, wenn **eine** dieser Bedingungen erfüllt ist:

1. **Er erscheint in Windows** unter *Einstellungen → Personalisierung → Dynamische Beleuchtung*.
2. **Er wird von [OpenRGB](https://openrgb.org) unterstützt**: OpenRGB mit seinem SDK-Server starten, Glowback erkennt ihn automatisch.
3. **Weder noch?** Einen LED-Streifen mit einem 5-$-RP2040-Board nachrüsten: [DIY-Anleitung](docs/DIY-LED-strip.md) (auf Englisch).

Getestet mit: AOC AGON PRO AG276QZD2 (47 LEDs). Läuft es auf deinem Monitor? [Sag uns Bescheid](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml).

## 🪟 Die App

Startest du Glowback über das Startmenü, öffnet sich sein Fenster: **Umgebungslicht** (Live-Vorschau deines Bildschirms und deiner LEDs, an/aus, Licht, Helligkeit), **Profile**, **Home Assistant**, **Einstellungen** (Start mit Windows, Updates, Sprache) und **Info**. Schließt du es, läuft Glowback im Hintergrund weiter: Ein Doppelklick auf das Symbol neben der Uhr öffnet es wieder, ein einfacher Klick das Schnellmenü.

## 🎨 Licht und Profile

Auf der Seite **Umgebungslicht** wählst du, was die LEDs zeigen: den **Bildschirm** (jede LED ihre Zone oder eine Durchschnittsfarbe), eine **Farbe**, einen **Verlauf** (2 bis 4 Farben, still oder in Bewegung) oder die **Musik**: Die LEDs folgen dem Ton, den dein PC abspielt (Puls, Spektrum oder Wellen), ohne Mikrofon und ohne Aufnahme. Auf der Seite **Profile** wechselt das Licht von selbst: ein **Nachtprofil** (Uhrzeit, Helligkeit und Licht), ein Licht **pro App** (solange sie läuft, im Vordergrund oder im Vollbild ist oder Ton abspielt) und was **die übrige Zeit** geschieht. Zum Beispiel: Musik, während Spotify spielt, der Bildschirm für Spiele im Vollbild. [Ausführliche Anleitung (Englisch)](README.md#-looks).

## 🏠 Home Assistant und Google Assistant

Glowback kann in Home Assistant als Licht erscheinen (an/aus, Helligkeit, Farbe und Modus), steuerbar über Dashboards, Automationen, Google Assistant, Alexa und Siri (Apple Home, über die Integration HomeKit Bridge von Home Assistant). Installiere in Home Assistant die App **Mosquitto broker**, klicke dann im Glowback-Panel auf **Home Assistant** und gib Adresse, Benutzer und Passwort ein. [Ausführliche Anleitung (Englisch)](README.md#-home-assistant--google-assistant).

## 🗑️ Deinstallieren

- **Installer**: *Einstellungen → Apps → Installierte Apps → Glowback → Deinstallieren*. Die LEDs kehren zum Effekt des Geräts zurück.
- **Python-Version**: `glowback --uninstall`, dann `pip uninstall glowback`.
- **Portabel**: `glowback.exe --uninstall`, dann die .exe-Dateien löschen.

## ❓ FAQ

**Welche Monitore werden unterstützt?** Jeder Monitor, dessen RGB-Beleuchtung auf der Rückseite über die dynamische Beleuchtung von Windows oder OpenRGB steuerbar ist. Prüfen mit `glowback --list`.

**Funktioniert es mit HDR, Spielen und Filmen im Vollbild?** Ja. DRM-geschützte Inhalte erscheinen für alle Aufnahmetools meist schwarz.

**Nichts leuchtet.** USB-Kabel des Monitors prüfen, RGB im Monitormenü aktivieren und die dynamische Beleuchtung von Windows für das Gerät ausschalten.

**Die Farben sind auf der falschen Seite.** *LEDs testen* verwenden; sind links und rechts vertauscht, `--mirror` hinzufügen.

Kommandozeilenoptionen und technische Details: [englische README](README.md#%EF%B8%8F-command-line).

## 🧩 Auch von mir

[**Keyboard Clock**](https://github.com/Ilyomix/keyboard-clock): die Uhrzeit in großen Ziffern auf deiner RGB-Tastatur, für Tastaturen von Logitech G, Razer, Corsair, ASUS, SteelSeries, HyperX und OpenRGB.

## ⭐ Unterstützung

Wenn Glowback deinen Schreibtisch erhellt, **gib dem Repository einen Stern**: So finden es andere Besitzer von RGB-Monitoren.

---

<sub>Ambilight ist eine Marke von Koninklijke Philips N.V. / TP Vision. Glowback ist ein unabhängiges Open-Source-Projekt ohne Verbindung zu ihnen.</sub>

MIT © [Ilyomix](https://github.com/Ilyomix) · [Richtlinie zur Codesignierung](CODE_SIGNING.md) · [Datenschutz](PRIVACY.md)
