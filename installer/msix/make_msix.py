"""Builds the Microsoft Store package (MSIX) from the PyInstaller app in dist/Glowback.

    python installer/msix/make_msix.py 0.8.0

The Store signs the package itself, so a Store install never meets SmartScreen. The package identity is Glowback's
in Partner Center (Product management > Product identity); the environment variables MSIX_IDENTITY_NAME,
MSIX_PUBLISHER and MSIX_PUBLISHER_NAME replace it, for a test package.

In the package, Glowback.exe is the app and GlowbackBackground.exe, the same file, is what Windows starts at sign-in
(StartupTask): Glowback starts without its window when it runs under that name. Its firewall rules let phones' Home
apps reach it through Matter (UDP 5540, and mDNS on 5353).

Writes build/msix/ (the layout) and dist/Glowback.msix (unsigned, for the Store). Needs makeappx.exe from the Windows
SDK (on GitHub's windows-latest runners).
"""
import glob
import os
import shutil
import struct
import subprocess
import sys
import zlib
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
import glowback  # noqa: E402  (the app draws its own icon)

IDENTITY = {"MSIX_IDENTITY_NAME": "Ilyomix.Glowback",
            "MSIX_PUBLISHER": "CN=1086910A-7B63-40D7-8B50-6BF71E2EB5C4",
            "MSIX_PUBLISHER_NAME": "Ilyomix"}
LANGS = ["en-us", "fr-fr", "es-es", "de-de", "it-it", "pt-br"]  # the app's languages; the first is the default
DESCRIPTION = "Ambient light for the RGB LEDs on the back of your monitor"
# name: (width, height, icon size). Tiles get some room around the ring; app list and taskbar icons fill their square.
LOGOS = {"StoreLogo.png": (50, 50, 50), "Square44x44Logo.png": (44, 44, 44),
         "Square71x71Logo.png": (71, 71, 50), "Square150x150Logo.png": (150, 150, 96),
         "Square310x310Logo.png": (310, 310, 200), "Wide310x150Logo.png": (310, 150, 96)}
for size in (16, 24, 32, 48, 256):  # taskbar, Start, Alt+Tab: without a plate behind them
    for form in ("targetsize-{}", "altform-unplated_targetsize-{}", "altform-lightunplated_targetsize-{}"):
        LOGOS[f"Square44x44Logo.{form.format(size)}.png"] = (size, size, size)
FIREWALL = [("UDP", glowback.MATTER_PORT), ("UDP", 5353)]  # Matter, and mDNS so phones find it

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
         xmlns:desktop2="http://schemas.microsoft.com/appx/manifest/desktop/windows10/2"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap desktop desktop2 rescap">
  <Identity Name="{name}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>Glowback</DisplayName>
    <PublisherDisplayName>{publisher_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
{resources}
  </Resources>
  <Applications>
    <Application Id="Glowback" Executable="Glowback.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="Glowback" Description="{description}" BackgroundColor="transparent"
                          Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Square71x71Logo="Assets\\Square71x71Logo.png" Square310x310Logo="Assets\\Square310x310Logo.png"
                         Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <!-- Starts with Windows, in the background (the user turns it off in Settings > Apps > Startup) -->
        <desktop:Extension Category="windows.startupTask" Executable="GlowbackBackground.exe"
                           EntryPoint="Windows.FullTrustApplication">
          <desktop:StartupTask TaskId="GlowbackStartup" Enabled="true" DisplayName="Glowback" />
        </desktop:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
  <Extensions>
{firewall}
  </Extensions>
</Package>
"""


def png(width, height, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * width * 4:(y + 1) * width * 4]) for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def logo(path, width, height, size):
    """Glowback's ring, `size` pixels wide, centred on a transparent width x height image."""
    bgra = glowback.icon_pixels(size)
    rgba = bytearray(width * height * 4)
    x0, y0 = (width - size) // 2, (height - size) // 2
    for y in range(size):
        row = bgra[y * size * 4:(y + 1) * size * 4]
        conv = bytearray(len(row))
        conv[0::4], conv[1::4], conv[2::4], conv[3::4] = row[2::4], row[1::4], row[0::4], row[3::4]
        i = ((y0 + y) * width + x0) * 4
        rgba[i:i + size * 4] = conv
    with open(path, "wb") as f:
        f.write(png(width, height, rgba))


def firewall_rules():
    rules = "\n".join(f'          <desktop2:Rule Direction="in" IPProtocol="{proto}" Profile="all" '
                      f'LocalPortMin="{port}" LocalPortMax="{port}" />' for proto, port in FIREWALL)
    return "\n".join(f'    <desktop2:Extension Category="windows.firewallRules">\n'
                     f'      <desktop2:FirewallRules Executable="{exe}">\n{rules}\n'
                     f'      </desktop2:FirewallRules>\n    </desktop2:Extension>'
                     for exe in ("Glowback.exe", "GlowbackBackground.exe"))


def makeappx():
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makeappx.exe"))
    if not found:
        sys.exit("makeappx.exe not found (Windows SDK)")
    return found[-1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("usage: python installer/msix/make_msix.py VERSION [--layout]  (--layout: the folder, no .msix)")
    numbers = [int(n) for n in args[0].split("-")[0].split(".")][:3]
    version = ".".join(str(n) for n in numbers + [0] * (3 - len(numbers))) + ".0"  # the Store wants x.y.z.0
    app = os.path.join(ROOT, "dist", "Glowback")
    out = os.path.join(ROOT, "build", "msix")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(app, out)
    shutil.copy(os.path.join(out, "Glowback.exe"), os.path.join(out, "GlowbackBackground.exe"))
    os.makedirs(os.path.join(out, "Assets"))
    for name, (width, height, size) in LOGOS.items():
        logo(os.path.join(out, "Assets", name), width, height, size)
    identity = {k: escape(os.environ.get(k) or v) for k, v in IDENTITY.items()}
    manifest = MANIFEST.format(
        name=identity["MSIX_IDENTITY_NAME"], publisher=identity["MSIX_PUBLISHER"],
        publisher_name=identity["MSIX_PUBLISHER_NAME"], version=version, description=escape(DESCRIPTION),
        resources="\n".join(f'    <Resource Language="{tag}" />' for tag in LANGS), firewall=firewall_rules())
    with open(os.path.join(out, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    if "--layout" in sys.argv:
        return
    target = os.path.join(ROOT, "dist", "Glowback.msix")
    subprocess.run([makeappx(), "pack", "/d", out, "/p", target, "/o"], check=True)
    print(f"{target} ({version})")


if __name__ == "__main__":
    main()
