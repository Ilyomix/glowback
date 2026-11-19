#!/usr/bin/env python3
"""
Glowback - Ambilight for any monitor with RGB LEDs on the back.

Real-time, screen-synced bias lighting for every Windows "Dynamic Lighting"
(HID LampArray) device: monitors with rear RGB (e.g. AOC AGON PRO Light FX),
LED strips, cases... Each LED follows the part of the image it sits behind,
like Philips Ambilight - no camera, no vendor app, no extra hardware.

Single file, zero dependencies, pure Python + Win32 (ctypes).

    glowback                 start the ambilight (each LED follows its own zone)
    glowback --mode average  one average color for all LEDs
    glowback --list          show detected LED devices and screens
    glowback --test          orientation test pattern
    glowback --stop          stop the running instance

https://github.com/Ilyomix/glowback  -  MIT License
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import math
import os
import sys
import threading
import time
from ctypes import byref, sizeof
from operator import itemgetter, mul

__version__ = "0.1.0"

if sys.platform != "win32":
    sys.exit("Glowback runs on Windows 10/11 (it drives HID LampArray / Dynamic Lighting devices).")

try:
    from math import sumprod
except ImportError:  # Python < 3.12
    def sumprod(a, b):
        return sum(map(mul, a, b))

# =============================================================================
# Win32 declarations
# =============================================================================
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)

HANDLE = ctypes.c_void_p
INVALID_HANDLE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("a", wt.DWORD), ("b", wt.WORD), ("c", wt.WORD), ("d", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("guid", GUID), ("flags", wt.DWORD), ("res", ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT), ("ProductID", wt.USHORT), ("Version", wt.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT), ("InLen", wt.USHORT),
                ("OutLen", wt.USHORT), ("FeatLen", wt.USHORT), ("Reserved", wt.USHORT * 17),
                ("Counts", wt.USHORT * 10)]  # Counts[8] = NumberFeatureValueCaps


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [("UsagePage", wt.USHORT), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                ("BitField", wt.USHORT), ("LinkCollection", wt.USHORT), ("LinkUsage", wt.USHORT),
                ("LinkUsagePage", wt.USHORT), ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte), ("HasNull", ctypes.c_ubyte),
                ("Reserved", ctypes.c_ubyte), ("BitSize", wt.USHORT), ("ReportCount", wt.USHORT),
                ("Reserved2", wt.USHORT * 5), ("UnitsExp", wt.ULONG), ("Units", wt.ULONG),
                ("LogicalMin", wt.LONG), ("LogicalMax", wt.LONG), ("PhysicalMin", wt.LONG), ("PhysicalMax", wt.LONG),
                ("UsageMin", wt.USHORT), ("UsageMax", wt.USHORT), ("StringMin", wt.USHORT), ("StringMax", wt.USHORT),
                ("DesignatorMin", wt.USHORT), ("DesignatorMax", wt.USHORT),
                ("DataIndexMin", wt.USHORT), ("DataIndexMax", wt.USHORT)]


class HIDP_DATA(ctypes.Structure):
    _fields_ = [("DataIndex", wt.USHORT), ("Reserved", wt.USHORT), ("RawValue", wt.ULONG)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("DeviceName", wt.WCHAR * 32), ("DeviceString", wt.WCHAR * 128),
                ("StateFlags", wt.DWORD), ("DeviceID", wt.WCHAR * 128), ("DeviceKey", wt.WCHAR * 128)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD), ("szDevice", wt.WCHAR * 32)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, HANDLE, HANDLE, ctypes.POINTER(wt.RECT), wt.LPARAM)
CTRLHANDLER = ctypes.WINFUNCTYPE(wt.BOOL, wt.DWORD)


def _sig(fn, res, *args):
    fn.restype = res
    fn.argtypes = list(args)


_sig(user32.GetDC, HANDLE, HANDLE)
_sig(user32.ReleaseDC, ctypes.c_int, HANDLE, HANDLE)
_sig(user32.EnumDisplayDevicesW, wt.BOOL, wt.LPCWSTR, wt.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wt.DWORD)
_sig(user32.EnumDisplayMonitors, wt.BOOL, HANDLE, ctypes.c_void_p, MONITORENUMPROC, wt.LPARAM)
_sig(user32.GetMonitorInfoW, wt.BOOL, HANDLE, ctypes.POINTER(MONITORINFOEXW))
_sig(gdi32.CreateCompatibleDC, HANDLE, HANDLE)
_sig(gdi32.CreateDIBSection, HANDLE, HANDLE, ctypes.POINTER(BITMAPINFO), wt.UINT,
     ctypes.POINTER(ctypes.c_void_p), HANDLE, wt.DWORD)
_sig(gdi32.SelectObject, HANDLE, HANDLE, HANDLE)
_sig(gdi32.DeleteObject, wt.BOOL, HANDLE)
_sig(gdi32.DeleteDC, wt.BOOL, HANDLE)
_sig(gdi32.SetStretchBltMode, ctypes.c_int, HANDLE, ctypes.c_int)
_sig(gdi32.SetBrushOrgEx, wt.BOOL, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
_sig(gdi32.StretchBlt, wt.BOOL, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
     HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.DWORD)
_sig(gdi32.GdiFlush, wt.BOOL)
_sig(k32.CreateFileW, HANDLE, wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, HANDLE)
_sig(k32.CloseHandle, wt.BOOL, HANDLE)
_sig(k32.CreateEventW, HANDLE, ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR)
_sig(k32.OpenEventW, HANDLE, wt.DWORD, wt.BOOL, wt.LPCWSTR)
_sig(k32.SetEvent, wt.BOOL, HANDLE)
_sig(k32.WaitForSingleObject, wt.DWORD, HANDLE, wt.DWORD)
_sig(k32.SetConsoleCtrlHandler, wt.BOOL, CTRLHANDLER, wt.BOOL)
_sig(k32.FreeConsole, wt.BOOL)
_sig(setupapi.SetupDiGetClassDevsW, HANDLE, ctypes.POINTER(GUID), wt.LPCWSTR, HANDLE, wt.DWORD)
_sig(setupapi.SetupDiEnumDeviceInterfaces, wt.BOOL, HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID),
     wt.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA))
_sig(setupapi.SetupDiGetDeviceInterfaceDetailW, wt.BOOL, HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
     ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p)
_sig(setupapi.SetupDiDestroyDeviceInfoList, wt.BOOL, HANDLE)
_sig(hid.HidD_GetHidGuid, None, ctypes.POINTER(GUID))
_sig(hid.HidD_GetAttributes, wt.BOOLEAN, HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES))
_sig(hid.HidD_GetProductString, wt.BOOLEAN, HANDLE, ctypes.c_void_p, wt.ULONG)
_sig(hid.HidD_GetPreparsedData, wt.BOOLEAN, HANDLE, ctypes.POINTER(ctypes.c_void_p))
_sig(hid.HidD_FreePreparsedData, wt.BOOLEAN, ctypes.c_void_p)
_sig(hid.HidD_GetFeature, wt.BOOLEAN, HANDLE, ctypes.c_void_p, wt.ULONG)
_sig(hid.HidD_SetFeature, wt.BOOLEAN, HANDLE, ctypes.c_void_p, wt.ULONG)
_sig(hid.HidP_GetCaps, wt.LONG, ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS))
_sig(hid.HidP_GetValueCaps, wt.LONG, ctypes.c_int, ctypes.POINTER(HIDP_VALUE_CAPS),
     ctypes.POINTER(wt.USHORT), ctypes.c_void_p)
_sig(hid.HidP_GetUsageValue, wt.LONG, ctypes.c_int, wt.USHORT, wt.USHORT, wt.USHORT,
     ctypes.POINTER(wt.ULONG), ctypes.c_void_p, ctypes.c_void_p, wt.ULONG)
_sig(hid.HidP_InitializeReportForID, wt.LONG, ctypes.c_int, ctypes.c_ubyte, ctypes.c_void_p,
     ctypes.c_void_p, wt.ULONG)
_sig(hid.HidP_SetData, wt.LONG, ctypes.c_int, ctypes.POINTER(HIDP_DATA), ctypes.POINTER(wt.ULONG),
     ctypes.c_void_p, ctypes.c_void_p, wt.ULONG)
_sig(hid.HidP_SetUsageValueArray, wt.LONG, ctypes.c_int, wt.USHORT, wt.USHORT, wt.USHORT,
     ctypes.c_void_p, wt.USHORT, ctypes.c_void_p, ctypes.c_void_p, wt.ULONG)

HIDP_FEATURE = 2
HIDP_OK = 0x00110000
PAGE = 0x59  # HID Usage Page "Lighting And Illumination"
# LampArray collections (HID Usage Tables 1.4, chapter 25)
C_ATTRS, C_REQ, C_RESP, C_MULTI, C_RANGE, C_CTRL = 0x02, 0x20, 0x22, 0x50, 0x60, 0x70
U_COUNT, U_KIND, U_MIN_INTERVAL = 0x03, 0x07, 0x08
U_WIDTH, U_HEIGHT = 0x04, 0x05
U_ID, U_X, U_Y, U_Z, U_INT_LEVELS = 0x21, 0x23, 0x24, 0x25, 0x2B
U_R, U_G, U_B, U_I, U_FLAGS, U_START, U_END, U_AUTO = 0x51, 0x52, 0x53, 0x54, 0x55, 0x61, 0x62, 0x71
KINDS = {0: "undefined", 1: "keyboard", 2: "mouse", 3: "game controller", 4: "peripheral", 5: "scene",
         6: "notification", 7: "chassis", 8: "wearable", 9: "furniture", 10: "art"}
NOT_AMBIENT_KINDS = {1, 2, 3}  # skipped unless --device all / a name filter selects them

STOP_EVENT = "Local\\Glowback.Stop"
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Glowback")
LOG_PATH = os.path.join(LOG_DIR, "glowback.log")


def log(msg):
    line = time.strftime("%H:%M:%S  ") + msg
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _ok(status):
    return (status & 0xFFFFFFFF) == HIDP_OK


class Unsupported(OSError):
    pass


# =============================================================================
# HID LampArray device (Windows Dynamic Lighting standard)
# =============================================================================
def enumerate_lamparrays():
    """Yield (path, product name, vid, pid) for every HID LampArray interface."""
    guid = GUID()
    hid.HidD_GetHidGuid(byref(guid))
    hset = setupapi.SetupDiGetClassDevsW(byref(guid), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
    found = []
    try:
        i = 0
        while True:
            data = SP_DEVICE_INTERFACE_DATA()
            data.cbSize = sizeof(data)
            if not setupapi.SetupDiEnumDeviceInterfaces(hset, None, byref(guid), i, byref(data)):
                break
            i += 1
            need = wt.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(hset, byref(data), None, 0, byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if sizeof(ctypes.c_void_p) == 8 else 6
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(hset, byref(data), buf, need, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            h = k32.CreateFileW(path, 0, 3, None, 3, 0, None)  # query-only handle
            if h in (None, INVALID_HANDLE):
                continue
            try:
                pp = ctypes.c_void_p()
                if not hid.HidD_GetPreparsedData(h, byref(pp)):
                    continue
                caps = HIDP_CAPS()
                hid.HidP_GetCaps(pp, byref(caps))
                hid.HidD_FreePreparsedData(pp)
                if caps.UsagePage != PAGE or caps.Usage != 0x01:
                    continue
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = sizeof(attrs)
                hid.HidD_GetAttributes(h, byref(attrs))
                name = ctypes.create_unicode_buffer(256)
                hid.HidD_GetProductString(h, name, sizeof(name))
                found.append((path, name.value or "LampArray", attrs.VendorID, attrs.ProductID))
            finally:
                k32.CloseHandle(h)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hset)
    return found


class Lamp:
    __slots__ = ("id", "x", "y", "z")

    def __init__(self, lamp_id, x, y, z):
        self.id, self.x, self.y, self.z = lamp_id, x, y, z


class LampArray:
    """A HID LampArray. Report layout is discovered from the HID descriptor."""

    def __init__(self, path, name="LampArray", vid=0, pid=0):
        self.path, self.name, self.vid, self.pid = path, name, vid, pid
        self.pp = None
        self.h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)  # read/write, shared
        if self.h in (None, INVALID_HANDLE):
            self.h = None
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.pp = ctypes.c_void_p()
            if not hid.HidD_GetPreparsedData(self.h, byref(self.pp)):
                raise Unsupported("cannot read HID descriptor")
            caps = HIDP_CAPS()
            hid.HidP_GetCaps(self.pp, byref(caps))
            self.flen = caps.FeatLen
            self._discover(caps.Counts[8])
            self._read_attributes()
        except Exception:
            self.close()
            raise

    # ---- descriptor parsing ----------------------------------------------
    def _discover(self, n_caps):
        n = wt.USHORT(n_caps)
        vc = (HIDP_VALUE_CAPS * max(1, n_caps))()
        hid.HidP_GetValueCaps(HIDP_FEATURE, vc, byref(n), self.pp)
        self.rid, self.link, fields = {}, {}, {}
        for c in vc[:n.value]:
            if c.UsagePage != PAGE:
                continue
            self.rid.setdefault(c.LinkUsage, c.ReportID)
            self.link.setdefault(c.LinkUsage, c.LinkCollection)
            if c.IsRange:
                for k, u in enumerate(range(c.UsageMin, c.UsageMax + 1)):
                    fields.setdefault(c.LinkUsage, []).append((c.DataIndexMin + k, u, c.BitSize, 1, c.LinkCollection))
            else:
                fields.setdefault(c.LinkUsage, []).append((c.DataIndexMin, c.UsageMin, c.BitSize, c.ReportCount, c.LinkCollection))
        missing = [hex(cu) for cu in (C_ATTRS, C_REQ, C_RESP, C_MULTI, C_RANGE, C_CTRL) if cu not in self.rid]
        if missing:
            raise Unsupported(f"incomplete LampArray descriptor (missing {', '.join(missing)})")
        self.tpl = {cu: self._blank(self.rid[cu]) for cu in self.rid}

        def locate(cu, usage):
            """(offset, size) of each occurrence of `usage` in collection `cu`, sorted by byte position."""
            slots = []
            for di, u, bits, count, link in fields.get(cu, []):
                if u != usage:
                    continue
                if bits % 8:
                    raise Unsupported("non byte-aligned LampArray field")
                size = bits // 8
                buf = bytearray(self.tpl[cu])
                arr = (ctypes.c_ubyte * self.flen).from_buffer(buf)
                if count == 1:
                    d = HIDP_DATA(di, 0, (1 << bits) - 1)
                    ln = wt.ULONG(1)
                    st = hid.HidP_SetData(HIDP_FEATURE, byref(d), byref(ln), self.pp, arr, self.flen)
                else:
                    ones = (ctypes.c_ubyte * (size * count))(*([0xFF] * (size * count)))
                    st = hid.HidP_SetUsageValueArray(HIDP_FEATURE, PAGE, link, u, ones, size * count,
                                                     self.pp, arr, self.flen)
                if not _ok(st):
                    raise Unsupported(f"cannot map usage {u:#x} ({st & 0xFFFFFFFF:#x})")
                off = next(i for i in range(self.flen) if buf[i] != self.tpl[cu][i])
                slots.extend((off + k * size, size) for k in range(count))
            if not slots:
                raise Unsupported(f"usage {usage:#x} not found in collection {cu:#x}")
            return sorted(slots)

        self.m_count = locate(C_MULTI, U_COUNT)[0]
        self.m_flags = locate(C_MULTI, U_FLAGS)[0]
        self.m_ids = locate(C_MULTI, U_ID)
        self.m_rgbi = [locate(C_MULTI, u) for u in (U_R, U_G, U_B, U_I)]
        self.batch = min(len(self.m_ids), *(len(ch) for ch in self.m_rgbi))
        self.r_flags = locate(C_RANGE, U_FLAGS)[0]
        self.r_start = locate(C_RANGE, U_START)[0]
        self.r_end = locate(C_RANGE, U_END)[0]
        self.r_rgbi = [locate(C_RANGE, u)[0] for u in (U_R, U_G, U_B, U_I)]
        self.c_auto = locate(C_CTRL, U_AUTO)[0]
        self.q_id = locate(C_REQ, U_ID)[0]

    def _blank(self, rid):
        b = (ctypes.c_ubyte * self.flen)()
        st = hid.HidP_InitializeReportForID(HIDP_FEATURE, rid, self.pp, b, self.flen)
        if not _ok(st):
            b = (ctypes.c_ubyte * self.flen)()
            b[0] = rid
        return bytes(b)

    # ---- low level I/O -----------------------------------------------------
    def _get(self, cu):
        b = (ctypes.c_ubyte * self.flen).from_buffer_copy(self.tpl[cu])
        if not hid.HidD_GetFeature(self.h, b, self.flen):
            raise ctypes.WinError(ctypes.get_last_error())
        return b

    def _val(self, report, cu, usage, default=0):
        v = wt.ULONG()
        st = hid.HidP_GetUsageValue(HIDP_FEATURE, PAGE, self.link[cu], usage, byref(v), self.pp, report, self.flen)
        return v.value if _ok(st) else default

    def _send(self, buf):
        arr = (ctypes.c_ubyte * self.flen).from_buffer(buf)
        if not hid.HidD_SetFeature(self.h, arr, self.flen):
            raise ctypes.WinError(ctypes.get_last_error())

    @staticmethod
    def _put(buf, field, value):
        off, size = field
        buf[off:off + size] = int(value).to_bytes(size, "little")

    def _read_attributes(self):
        a = self._get(C_ATTRS)
        count = self._val(a, C_ATTRS, U_COUNT)
        self.kind = self._val(a, C_ATTRS, U_KIND)
        self.width_mm = self._val(a, C_ATTRS, U_WIDTH) / 1000
        self.height_mm = self._val(a, C_ATTRS, U_HEIGHT) / 1000
        self.min_interval = self._val(a, C_ATTRS, U_MIN_INTERVAL) / 1e6
        self.lamps, self.intensity = [], 1
        for i in range(count):
            q = bytearray(self.tpl[C_REQ])
            self._put(q, self.q_id, i)
            self._send(q)
            r = self._get(C_RESP)
            self.lamps.append(Lamp(self._val(r, C_RESP, U_ID, i), self._val(r, C_RESP, U_X),
                                   self._val(r, C_RESP, U_Y), self._val(r, C_RESP, U_Z)))
            self.intensity = max(self.intensity, self._val(r, C_RESP, U_INT_LEVELS, 1))
        if not self.lamps:
            raise Unsupported("device reports 0 lamps")

    # ---- public API ---------------------------------------------------------
    def set_autonomous(self, on):
        b = bytearray(self.tpl[C_CTRL])
        self._put(b, self.c_auto, 1 if on else 0)
        self._send(b)

    def send_all(self, rgb):
        b = bytearray(self.tpl[C_RANGE])
        self._put(b, self.r_flags, 1)
        self._put(b, self.r_start, 0)
        self._put(b, self.r_end, len(self.lamps) - 1)
        for f, v in zip(self.r_rgbi, (*rgb, self.intensity)):
            b[f[0]] = v
        self._send(b)

    def send(self, colors):
        """colors: one (r, g, b) per lamp, same order as self.lamps."""
        n, step = len(colors), self.batch
        for start in range(0, n, step):
            chunk = colors[start:start + step]
            b = bytearray(self.tpl[C_MULTI])
            self._put(b, self.m_count, len(chunk))
            self._put(b, self.m_flags, 1 if start + step >= n else 0)  # LampUpdateComplete
            r_, g_, b_, i_ = self.m_rgbi
            for k, (r, g, bl) in enumerate(chunk):
                self._put(b, self.m_ids[k], self.lamps[start + k].id)
                b[r_[k][0]] = r
                b[g_[k][0]] = g
                b[b_[k][0]] = bl
                b[i_[k][0]] = self.intensity
            self._send(b)

    def close(self):
        if self.pp:
            hid.HidD_FreePreparsedData(self.pp)
            self.pp = None
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None


def dynamic_lighting_enabled(path):
    """True if Windows Dynamic Lighting is also driving this device (they would fight)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Lighting") as k:
            if winreg.QueryValueEx(k, "AmbientLightingEnabled")[0] == 0:
                return False
        key = path[4:] if path.startswith("\\\\?\\") else path
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Lighting\Devices") as k:
            i = 0
            while True:
                sub = winreg.EnumKey(k, i)
                i += 1
                if sub.lower() == key.lower():
                    with winreg.OpenKey(k, sub) as d:
                        return winreg.QueryValueEx(d, "AmbientLightingEnabled")[0] != 0
    except OSError:
        return None


# =============================================================================
# Screens
# =============================================================================
class Monitor:
    def __init__(self, index, device, rect, primary, pnp, name):
        self.index, self.device, self.rect, self.primary, self.pnp, self.name = index, device, rect, primary, pnp, name

    @property
    def size(self):
        return self.rect[2] - self.rect[0], self.rect[3] - self.rect[1]

    def label(self):
        w, h = self.size
        return f"#{self.index} {self.name or '?'} [{self.pnp}] {w}x{h}{' (primary)' if self.primary else ''}"


def _edid_name(interface_path):
    """(PnP id, model name from EDID) for a monitor interface path."""
    p = interface_path[4:] if interface_path.startswith("\\\\?\\") else interface_path
    parts = p.split("#")
    if len(parts) < 3:
        return "", ""
    pnp, name = parts[1], ""
    try:
        import winreg
        sub = rf"SYSTEM\CurrentControlSet\Enum\{parts[0]}\{parts[1]}\{parts[2]}\Device Parameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as k:
            edid = bytes(winreg.QueryValueEx(k, "EDID")[0])
        for off in (54, 72, 90, 108):
            d = edid[off:off + 18]
            if len(d) == 18 and d[0] == 0 and d[1] == 0 and d[3] == 0xFC:
                name = d[5:18].split(b"\n")[0].decode("ascii", "replace").strip()
    except OSError:
        pass
    return pnp, name


def list_monitors():
    ids = {}
    i = 0
    while True:
        ad = DISPLAY_DEVICEW()
        ad.cb = sizeof(ad)
        if not user32.EnumDisplayDevicesW(None, i, byref(ad), 0):
            break
        i += 1
        mon = DISPLAY_DEVICEW()
        mon.cb = sizeof(mon)
        if (ad.StateFlags & 1) and user32.EnumDisplayDevicesW(ad.DeviceName, 0, byref(mon), 1):
            ids[ad.DeviceName] = _edid_name(mon.DeviceID)
    mons = []

    def cb(hmon, _hdc, _rc, _data):
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        if user32.GetMonitorInfoW(hmon, byref(mi)):
            rc = mi.rcMonitor
            pnp, name = ids.get(mi.szDevice, ("", ""))
            mons.append(Monitor(len(mons) + 1, mi.szDevice, (rc.left, rc.top, rc.right, rc.bottom),
                                bool(mi.dwFlags & 1), pnp, name))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return mons


def _norm(s):
    return "".join(ch for ch in s.upper() if ch.isalnum())


def pick_monitor(device_name, monitors, choice="auto"):
    """Screen whose image drives a device: --screen choice, EDID model match, or primary."""
    if not monitors:
        return None
    primary = next((m for m in monitors if m.primary), monitors[0])
    if choice == "primary":
        return primary
    if choice.isdigit():
        return next((m for m in monitors if m.index == int(choice)), None)
    if choice != "auto":
        c = _norm(choice)
        return next((m for m in monitors if c in _norm(m.name + m.pnp + m.device)), None)
    dev = _norm(device_name)
    for m in monitors:  # e.g. monitor "AG276QZD2" <-> device "AGON3 AG276QZD2 Light FX Device"
        if len(_norm(m.name)) >= 4 and _norm(m.name) in dev:
            return m
    return primary


class ScreenGrabber:
    """Shrinks a screen area to a tiny grid: fast sampling, then a HALFTONE (averaging) pass."""

    def __init__(self, rect, grid_w):
        self.rect = rect
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        self.gw = grid_w
        self.gh = max(4, round(grid_w * h / w))
        self.sw = min(w, 320)
        self.sh = max(1, round(self.sw * h / w))
        self.sdc = user32.GetDC(None)
        self.s1 = self._dib(self.sw, self.sh, 3)  # COLORONCOLOR: cheap read of the screen
        self.s2 = self._dib(self.gw, self.gh, 4)  # HALFTONE: proper block average

    def _dib(self, w, h, mode):
        dc = gdi32.CreateCompatibleDC(self.sdc)
        bmi = BITMAPINFO()
        hd = bmi.bmiHeader
        hd.biSize, hd.biWidth, hd.biHeight, hd.biPlanes, hd.biBitCount = sizeof(BITMAPINFOHEADER), w, -h, 1, 32
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(dc, byref(bmi), 0, byref(bits), None, 0)
        old = gdi32.SelectObject(dc, bmp)
        gdi32.SetStretchBltMode(dc, mode)
        gdi32.SetBrushOrgEx(dc, 0, 0, None)
        return dc, bmp, old, bits

    def grab(self):
        l, t, r, b = self.rect
        if not gdi32.StretchBlt(self.s1[0], 0, 0, self.sw, self.sh, self.sdc, l, t, r - l, b - t, 0x00CC0020):
            return None
        gdi32.StretchBlt(self.s2[0], 0, 0, self.gw, self.gh, self.s1[0], 0, 0, self.sw, self.sh, 0x00CC0020)
        gdi32.GdiFlush()
        raw = ctypes.string_at(self.s2[3], self.gw * self.gh * 4)  # BGRA
        return raw[2::4], raw[1::4], raw[0::4]

    def close(self):
        for dc, bmp, old, _ in (self.s1, self.s2):
            gdi32.SelectObject(dc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, self.sdc)


# =============================================================================
# LED <-> screen mapping
# =============================================================================
def lamp_uv(lamps, mirror=False, flip=False):
    """Normalized (0..1) position of each lamp inside the lamps' bounding box (as seen from the front)."""
    xs, ys = [l.x for l in lamps], [l.y for l in lamps]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    out = []
    for l in lamps:
        u = (l.x - x0) / (x1 - x0) if x1 > x0 else 0.5
        v = (l.y - y0) / (y1 - y0) if y1 > y0 else 0.5
        out.append((1 - u if mirror else u, 1 - v if flip else v))
    return out


def edge_point(u, v):
    """Project a lamp outward from the center onto the screen border (Ambilight-style)."""
    dx, dy = u - 0.5, v - 0.5
    m = max(abs(dx), abs(dy))
    if m < 1e-3:
        return None  # lamp at the center: follows the whole picture
    return 0.5 + dx * 0.5 / m, 0.5 + dy * 0.5 / m


def build_weights(points, gw, gh, aspect, radius):
    """For each lamp: (cell getter, gaussian weights) around its border point; None = whole screen."""
    res = []
    two_s2 = 2 * radius * radius
    for p in points:
        if p is None:
            res.append(None)
            continue
        px, py = p[0] * aspect, p[1]
        idx, w = [], []
        for cy in range(gh):
            for cx in range(gw):
                dx = (cx + 0.5) / gw * aspect - px
                dy = (cy + 0.5) / gh - py
                wt_ = math.exp(-(dx * dx + dy * dy) / two_s2)
                if wt_ > 0.02:
                    idx.append(cy * gw + cx)
                    w.append(wt_)
        if not idx:  # radius smaller than a cell: take the nearest one
            cx = min(gw - 1, int(p[0] * gw))
            cy = min(gh - 1, int(p[1] * gh))
            idx, w = [cy * gw + cx], [1.0]
        if len(idx) == 1:  # itemgetter must return a tuple
            idx, w = idx * 2, [w[0], 0.0]
        s = sum(w)
        res.append((itemgetter(*idx), tuple(x / s for x in w)))
    return res


def make_shaper(saturation, gamma, brightness):
    scale = 255.0 * brightness

    def shape(r, g, b):
        if saturation != 1.0:
            l = 0.299 * r + 0.587 * g + 0.114 * b
            r, g, b = l + (r - l) * saturation, l + (g - l) * saturation, l + (b - l) * saturation
        return tuple(scale * (min(255.0, max(0.0, c)) / 255.0) ** gamma for c in (r, g, b))

    return shape


# =============================================================================
# Runtime
# =============================================================================
class StopSignal:
    """Named event: single instance + clean stop (--stop, Ctrl+C, closing the console)."""

    def __init__(self):
        self.h = k32.CreateEventW(None, True, False, STOP_EVENT)
        self.already_running = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        self.done = threading.Event()

        @CTRLHANDLER
        def handler(_evt):
            k32.SetEvent(self.h)
            self.done.wait(3)
            return True

        self._handler = handler
        k32.SetConsoleCtrlHandler(handler, True)

    def wait(self, seconds):
        return k32.WaitForSingleObject(self.h, max(0, int(seconds * 1000))) == 0


def request_stop():
    h = k32.OpenEventW(0x0002, False, STOP_EVENT)  # EVENT_MODIFY_STATE
    if not h:
        print("Glowback is not running.")
        return False
    k32.SetEvent(h)
    k32.CloseHandle(h)
    print("Stop requested.")
    return True


def wanted(dev, device_filter):
    if device_filter == "all":
        return True
    if device_filter:
        f = _norm(device_filter)
        return f in _norm(dev.name) or f in f"{dev.vid:04X}{dev.pid:04X}"
    return dev.kind not in NOT_AMBIENT_KINDS


def open_devices(device_filter, known=()):
    devs, skipped = [], []
    for path, name, vid, pid in enumerate_lamparrays():
        if path in known:
            continue
        try:
            dev = LampArray(path, name, vid, pid)
        except OSError as e:
            skipped.append(f"{name}: {e}")
            continue
        if wanted(dev, device_filter):
            devs.append(dev)
        else:
            dev.close()
    return devs, skipped


class Output:
    """One LED device bound to one screen."""

    def __init__(self, dev):
        self.dev = dev
        self.monitor = None
        self.weights = None
        self.smooth = None
        self.last = None


def run(args, stop):
    shape = make_shaper(args.saturation, args.gamma, max(0.0, min(100.0, args.brightness)) / 100.0)
    outputs, grabbers = {}, {}
    period = 1.0 / max(1.0, args.fps)
    next_scan = next_keep = 0.0
    monitors = []
    frames, t_stat = 0, time.perf_counter()
    t_prev = time.perf_counter()
    warned = False
    try:
        while True:
            t0 = time.perf_counter()
            dt, t_prev = t0 - t_prev, t0

            # ---- (re)scan devices and screens: hot-plug, monitor power cycles, resolution changes
            if t0 >= next_scan:
                next_scan = t0 + 5
                new_monitors = list_monitors()
                changed = [(m.device, m.rect) for m in new_monitors] != [(m.device, m.rect) for m in monitors]
                monitors = new_monitors
                devs, _ = open_devices(args.device, outputs.keys())
                for dev in devs:
                    try:
                        dev.set_autonomous(False)
                    except OSError as e:
                        log(f"{dev.name}: cannot take control ({e})")
                        dev.close()
                        continue
                    outputs[dev.path] = Output(dev)
                    period = max(period, dev.min_interval)
                    log(f"Connected: {dev.name} ({len(dev.lamps)} LEDs, {KINDS.get(dev.kind, dev.kind)})")
                    if dynamic_lighting_enabled(dev.path):
                        log("  ! Windows Dynamic Lighting is ON for this device and will fight Glowback: turn it off in "
                            "Settings > Personalization > Dynamic Lighting > (device) > 'Use Dynamic Lighting on my devices'.")
                    changed = True
                if changed:
                    for o in outputs.values():
                        m = pick_monitor(o.dev.name, monitors, args.screen)
                        if m is not o.monitor or o.weights is None:
                            o.monitor, o.weights, o.smooth = m, None, None
                            if m:
                                log(f"  {o.dev.name}  <-  screen {m.label()}")
                    for rect in list(grabbers):
                        grabbers.pop(rect).close()
                if not outputs and not warned:
                    log("Waiting for a Dynamic Lighting (HID LampArray) device... (glowback --list to check)")
                    warned = True

            # ---- one frame
            keep = t0 >= next_keep
            if keep:
                next_keep = t0 + 5
            grids = {}
            for path, o in list(outputs.items()):
                m = o.monitor
                if m is None:
                    continue
                g = grabbers.get(m.rect)
                if g is None:
                    g = grabbers[m.rect] = ScreenGrabber(m.rect, args.grid)
                if m.rect not in grids:
                    grids[m.rect] = g.grab()
                grid = grids[m.rect]
                if grid is None:
                    continue
                R, G, B = grid
                n = len(R)
                avg = (sum(R) / n, sum(G) / n, sum(B) / n)
                if args.mode == "average":
                    targets = [shape(*avg)]
                else:
                    if o.weights is None:
                        w, h = m.size
                        pts = [edge_point(u, v) for u, v in lamp_uv(o.dev.lamps, args.mirror, args.flip)]
                        o.weights = build_weights(pts, g.gw, g.gh, w / h, args.radius)
                    bl = args.blend
                    targets = []
                    for wgt in o.weights:
                        if wgt is None:
                            targets.append(shape(*avg))
                            continue
                        get, w = wgt
                        r, gg, b = sumprod(get(R), w), sumprod(get(G), w), sumprod(get(B), w)
                        if bl:
                            r, gg, b = r + (avg[0] - r) * bl, gg + (avg[1] - gg) * bl, b + (avg[2] - b) * bl
                        targets.append(shape(r, gg, b))
                a = 1.0 - math.exp(-dt / args.smoothing) if args.smoothing > 0 else 1.0
                if o.smooth is None or len(o.smooth) != len(targets):
                    o.smooth = [list(t) for t in targets]
                else:
                    for s, t in zip(o.smooth, targets):
                        s[0] += (t[0] - s[0]) * a
                        s[1] += (t[1] - s[1]) * a
                        s[2] += (t[2] - s[2]) * a
                out = [(min(255, max(0, round(s[0]))), min(255, max(0, round(s[1]))), min(255, max(0, round(s[2]))))
                       for s in o.smooth]
                try:
                    if keep:
                        o.dev.set_autonomous(False)  # in case the device fell back to its own effects
                    if out != o.last or keep:
                        if args.mode == "average":
                            o.dev.send_all(out[0])
                        else:
                            o.dev.send(out)
                        o.last = out
                except OSError as e:
                    log(f"Lost {o.dev.name}: {e}")
                    o.dev.close()
                    del outputs[path]
                    next_scan = min(next_scan, t0 + 2)

            frames += 1
            if args.verbose and t0 - t_stat >= 2:
                print(f"  {frames / (t0 - t_stat):5.1f} fps   frame {1000 * (time.perf_counter() - t0):4.1f} ms   "
                      f"devices {len(outputs)}", flush=True)
                frames, t_stat = 0, t0

            if stop.wait(period - (time.perf_counter() - t0)):
                break
    finally:
        for o in outputs.values():
            try:
                o.dev.set_autonomous(True)  # hand the LEDs back to the device's own effects
            except OSError:
                pass
            o.dev.close()
        for g in grabbers.values():
            g.close()
        log("Glowback stopped.")


def cmd_list(args):
    monitors = list_monitors()
    print("Screens:")
    for m in monitors:
        print(f"  {m.label()}")
    print("\nDynamic Lighting / HID LampArray devices:")
    found = enumerate_lamparrays()
    if not found:
        print("  none found. Is the device's USB cable plugged into the PC? (monitors need their USB upstream cable)")
    for path, name, vid, pid in found:
        try:
            d = LampArray(path, name, vid, pid)
        except OSError as e:
            print(f"  {name} [{vid:04X}:{pid:04X}]  -> not usable: {e}")
            continue
        sel = "used" if wanted(d, args.device) else "ignored (use --device all or --device NAME)"
        m = pick_monitor(d.name, monitors, args.screen)
        dl = dynamic_lighting_enabled(path)
        print(f"  {d.name} [{vid:04X}:{pid:04X}]  {len(d.lamps)} LEDs, {KINDS.get(d.kind, d.kind)}, "
              f"{d.width_mm:.0f}x{d.height_mm:.0f} mm, max {1 / d.min_interval if d.min_interval else 0:.0f} Hz  -> {sel}")
        if m:
            print(f"      screen: {m.label()}")
        if dl:
            print("      ! Windows Dynamic Lighting is ON for this device: turn it off so it does not fight Glowback")
        d.close()


def cmd_test(args, stop):
    devs, skipped = open_devices(args.device)
    for s in skipped:
        print(f"  skipped {s}")
    if not devs:
        print("No Dynamic Lighting device found (glowback --list).")
        return
    print("Look at the wall behind the screen:")
    try:
        for d in devs:
            d.uv = lamp_uv(d.lamps, args.mirror, args.flip)
            d.set_autonomous(False)
        steps = [
            ("all LEDs WHITE", lambda u, v: (255, 255, 255)),
            ("LEFT = RED, RIGHT = BLUE (seen from your seat; if reversed use --mirror)",
             lambda u, v: (255, 0, 0) if u < 0.5 else (0, 0, 255)),
            ("TOP = GREEN, BOTTOM = YELLOW (if reversed use --flip)",
             lambda u, v: (0, 255, 0) if v < 0.5 else (255, 180, 0)),
        ]
        for label, fn in steps:
            print(f"  {label}")
            for d in devs:
                d.send([fn(u, v) for u, v in d.uv])
            if stop.wait(5):
                return
        print("  rainbow sweep around the LEDs")
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 6 and not stop.wait(0.03):
            t = time.perf_counter() - t0
            for d in devs:
                cols = []
                for u, v in d.uv:
                    hue = (math.atan2(v - 0.5, u - 0.5) / (2 * math.pi) + t * 0.5) % 1.0
                    cols.append(tuple(round(255 * max(0.0, min(1.0, abs((hue * 6 + k) % 6 - 3) - 1))) for k in (0, 4, 2)))
                d.send(cols)
    finally:
        for d in devs:
            try:
                d.set_autonomous(True)
            except OSError:
                pass
            d.close()
        print("Done, LEDs handed back to the device.")


def set_autostart(enable, argv):
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        if not enable:
            try:
                winreg.DeleteValue(k, "Glowback")
            except FileNotFoundError:
                pass
            print("Autostart disabled.")
            return
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}" --background'
        else:
            exe = sys.executable
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            cmd = f'"{pyw if os.path.exists(pyw) else exe}" "{os.path.abspath(__file__)}"'
        extra = " ".join(f'"{a}"' if " " in a else a for a in argv)
        winreg.SetValueEx(k, "Glowback", 0, winreg.REG_SZ, f"{cmd} {extra}".strip())
        print("Autostart enabled: Glowback will start with Windows, in the background.")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="glowback",
        description="Ambilight for monitors with RGB LEDs on the back (Windows Dynamic Lighting / HID LampArray).",
        epilog="Example: glowback --brightness 70 --smoothing 0.2")
    p.add_argument("--mode", choices=["zones", "average"], default="zones",
                   help="zones: each LED follows the part of the image it sits behind (default); average: one color")
    p.add_argument("--screen", default="auto",
                   help="screen to follow: auto (EDID model match, else primary), primary, a number from --list, or a name")
    p.add_argument("--device", default=None,
                   help="LED devices to drive: part of a name or VID:PID, or 'all' (default: all but keyboards/mice)")
    p.add_argument("--fps", type=float, default=30, help="updates per second (default 30)")
    p.add_argument("--brightness", type=float, default=100, help="0-100 (default 100)")
    p.add_argument("--saturation", type=float, default=1.3, help="color boost, 1 = none (default 1.3)")
    p.add_argument("--gamma", type=float, default=1.6, help="LED gamma correction (default 1.6)")
    p.add_argument("--smoothing", type=float, default=0.1, help="transition time in seconds (default 0.1)")
    p.add_argument("--radius", type=float, default=0.12, help="size of each LED's zone, fraction of screen height (default 0.12)")
    p.add_argument("--blend", type=float, default=0.0, help="0-1, mix of the whole-screen average into each zone (default 0)")
    p.add_argument("--grid", type=int, default=48, help="capture grid width in cells (default 48)")
    p.add_argument("--mirror", action="store_true", help="swap left/right if your device reports mirrored positions")
    p.add_argument("--flip", action="store_true", help="swap top/bottom")
    p.add_argument("--list", action="store_true", help="list LED devices and screens, then exit")
    p.add_argument("--test", action="store_true", help="play an orientation test pattern, then exit")
    p.add_argument("--stop", action="store_true", help="stop the running Glowback instance")
    p.add_argument("--autostart", choices=["on", "off"], help="start Glowback with Windows (with the other options given)")
    p.add_argument("--background", action="store_true", help="detach from the console (log in %%LOCALAPPDATA%%\\Glowback)")
    p.add_argument("-v", "--verbose", action="store_true", help="print fps")
    p.add_argument("--version", action="version", version=f"glowback {__version__}")
    return p.parse_args(argv)


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw)
    if args.stop:
        request_stop()
        return
    if args.autostart:
        set_autostart(args.autostart == "on", [a for a in raw if not a.startswith("--autostart") and a not in ("on", "off")])
        return
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixels
    except AttributeError:
        user32.SetProcessDPIAware()
    if args.list:
        cmd_list(args)
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    stop = StopSignal()
    if stop.already_running:
        print("Glowback is already running. Stop it first: glowback --stop")
        sys.exit(1)
    if args.background or sys.stdout is None:
        k32.FreeConsole()
        sys.stdout = sys.stderr = None
    try:
        if args.test:
            cmd_test(args, stop)
        else:
            try:
                open(LOG_PATH, "w").close()
            except OSError:
                pass
            log(f"Glowback {__version__} - mode {args.mode}, {args.fps:g} fps. Ctrl+C or 'glowback --stop' to quit.")
            run(args, stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.done.set()


if __name__ == "__main__":
    main()
