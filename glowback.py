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
import json
import math
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from ctypes import byref, sizeof
from operator import itemgetter, mul

__version__ = "0.2.0"

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
    """GDI fallback: shrinks a screen area to a tiny grid (fast sampling, then a HALFTONE average)."""
    kind = "GDI"

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
# DXGI Desktop Duplication capture: sees fullscreen video and games, and the
# GPU averages the picture down (mipmaps) so the CPU only reads ~80x45 pixels.
# =============================================================================
dxgi = ctypes.WinDLL("dxgi")
d3d11 = ctypes.WinDLL("d3d11")
VP = ctypes.c_void_p
PVP = ctypes.POINTER(ctypes.c_void_p)


def _iid(s):
    import uuid
    u = uuid.UUID(s)
    g = GUID(u.time_low, u.time_mid, u.time_hi_version)
    for i, b in enumerate(u.bytes[8:]):
        g.d[i] = b
    return g


IID_IDXGIFactory1 = _iid("770aae78-f26f-4dba-a829-253c83d1b387")
IID_IDXGIOutput1 = _iid("00cddea8-939b-4b83-a340-a685226666cc")
IID_ID3D11Texture2D = _iid("6f15aaf2-d208-4e89-9ab4-489535d34f9c")
DXGI_ERROR_WAIT_TIMEOUT = 0x887A0027


class DXGI_OUTPUT_DESC(ctypes.Structure):
    _fields_ = [("DeviceName", wt.WCHAR * 32), ("DesktopCoordinates", wt.RECT), ("AttachedToDesktop", wt.BOOL),
                ("Rotation", wt.UINT), ("Monitor", HANDLE)]


class DXGI_OUTDUPL_DESC(ctypes.Structure):
    _fields_ = [("Width", wt.UINT), ("Height", wt.UINT), ("RefreshNum", wt.UINT), ("RefreshDen", wt.UINT),
                ("Format", wt.UINT), ("ScanlineOrdering", wt.UINT), ("Scaling", wt.UINT), ("Rotation", wt.UINT),
                ("DesktopImageInSystemMemory", wt.BOOL)]


class D3D11_TEXTURE2D_DESC(ctypes.Structure):
    _fields_ = [(n, wt.UINT) for n in ("Width", "Height", "MipLevels", "ArraySize", "Format", "SampleCount",
                                       "SampleQuality", "Usage", "BindFlags", "CPUAccessFlags", "MiscFlags")]


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    _fields_ = [("pData", ctypes.c_void_p), ("RowPitch", wt.UINT), ("DepthPitch", wt.UINT)]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]


class DC_HEADER(ctypes.Structure):
    _fields_ = [("type", wt.UINT), ("size", wt.UINT), ("adapterId", LUID), ("id", wt.UINT)]


class DC_SOURCE_NAME(ctypes.Structure):
    _fields_ = [("header", DC_HEADER), ("name", wt.WCHAR * 32)]


class DC_SDR_WHITE(ctypes.Structure):
    _fields_ = [("header", DC_HEADER), ("level", wt.ULONG)]


class DC_PATH(ctypes.Structure):  # DISPLAYCONFIG_PATH_INFO (72 bytes)
    _fields_ = [("srcAdapter", LUID), ("srcId", wt.UINT), ("srcMode", wt.UINT), ("srcFlags", wt.UINT),
                ("tgtAdapter", LUID), ("tgtId", wt.UINT), ("tgtRest", wt.UINT * 9), ("flags", wt.UINT)]


_sig(user32.GetDisplayConfigBufferSizes, wt.LONG, wt.UINT, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT))
_sig(user32.QueryDisplayConfig, wt.LONG, wt.UINT, ctypes.POINTER(wt.UINT), ctypes.POINTER(DC_PATH),
     ctypes.POINTER(wt.UINT), ctypes.c_void_p, ctypes.c_void_p)
_sig(user32.DisplayConfigGetDeviceInfo, wt.LONG, ctypes.c_void_p)


def sdr_white_scale(device_name):
    """On an HDR screen: scRGB value of SDR white (Windows "SDR content brightness"), 1.0 = 80 nits."""
    try:
        n_paths, n_modes = wt.UINT(), wt.UINT()
        if user32.GetDisplayConfigBufferSizes(2, byref(n_paths), byref(n_modes)):  # QDC_ONLY_ACTIVE_PATHS
            return None
        paths = (DC_PATH * max(1, n_paths.value))()
        modes = (ctypes.c_ubyte * (64 * max(1, n_modes.value)))()
        if user32.QueryDisplayConfig(2, byref(n_paths), paths, byref(n_modes), modes, None):
            return None
        for p in paths[:n_paths.value]:
            src = DC_SOURCE_NAME()
            src.header.type, src.header.size, src.header.adapterId, src.header.id = 1, sizeof(src), p.srcAdapter, p.srcId
            if user32.DisplayConfigGetDeviceInfo(byref(src)) or src.name != device_name:
                continue
            w = DC_SDR_WHITE()
            w.header.type, w.header.size, w.header.adapterId, w.header.id = 11, sizeof(w), p.tgtAdapter, p.tgtId
            if user32.DisplayConfigGetDeviceInfo(byref(w)) == 0 and w.level:
                return w.level / 1000.0
    except (OSError, AttributeError):
        pass
    return None


def _srgb(x):
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


SRGB_LUT = bytes(round(255 * _srgb(i / 4095)) for i in range(4096))  # linear (0..1, 4096 steps) -> sRGB byte

_sig(dxgi.CreateDXGIFactory1, ctypes.c_long, ctypes.POINTER(GUID), PVP)
_sig(d3d11.D3D11CreateDevice, ctypes.c_long, VP, wt.UINT, VP, wt.UINT, VP, wt.UINT, wt.UINT, PVP,
     ctypes.POINTER(wt.UINT), PVP)


def _call(ptr, index, argtypes, *args, restype=ctypes.c_long):
    """Call COM method #index of the interface `ptr`."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, VP, *argtypes)(vtbl[index])(ptr, *args)


def _hr(hr, what):
    if hr < 0:
        raise OSError(f"{what} failed (0x{hr & 0xFFFFFFFF:08X})")
    return hr


def _release(ptr):
    if ptr is not None and ptr.value:
        _call(ptr, 2, [], restype=wt.ULONG)
        ptr.value = None


def _qi(ptr, iid):
    out = VP()
    _hr(_call(ptr, 0, [ctypes.POINTER(GUID), PVP], byref(iid), byref(out)), "QueryInterface")
    return out


class DxgiGrabber:
    kind = "DXGI"

    def __init__(self, monitor, grid_w):
        self.rect = monitor.rect
        self.factory, self.adapter, self.output, self.output1 = VP(), VP(), VP(), VP()
        self.device, self.ctx, self.dup = VP(), VP(), VP()
        self.mip, self.srv, self.staging = VP(), VP(), VP()
        self.last, self.fmt = None, None
        try:
            self._open(monitor.device, grid_w)
        except Exception:
            self.close()
            raise

    def _open(self, device_name, grid_w):
        _hr(dxgi.CreateDXGIFactory1(byref(IID_IDXGIFactory1), byref(self.factory)), "CreateDXGIFactory1")
        i = 0
        while not self.output.value:
            adapter = VP()
            if _call(self.factory, 12, [wt.UINT, PVP], i, byref(adapter)) < 0:  # EnumAdapters1
                raise OSError(f"no DXGI output for {device_name}")
            i += 1
            j = 0
            while True:
                out = VP()
                if _call(adapter, 7, [wt.UINT, PVP], j, byref(out)) < 0:  # EnumOutputs
                    break
                j += 1
                desc = DXGI_OUTPUT_DESC()
                _call(out, 7, [ctypes.POINTER(DXGI_OUTPUT_DESC)], byref(desc))  # GetDesc
                if desc.DeviceName == device_name:
                    self.adapter, self.output = adapter, out
                    break
                _release(out)
            if not self.output.value:
                _release(adapter)
        level = wt.UINT()
        _hr(d3d11.D3D11CreateDevice(self.adapter, 0, None, 0x20, None, 0, 7, byref(self.device), byref(level),
                                    byref(self.ctx)), "D3D11CreateDevice")
        self.output1 = _qi(self.output, IID_IDXGIOutput1)
        _hr(_call(self.output1, 22, [VP, PVP], self.device, byref(self.dup)), "DuplicateOutput")
        d = DXGI_OUTDUPL_DESC()
        _call(self.dup, 7, [ctypes.POINTER(DXGI_OUTDUPL_DESC)], byref(d), restype=None)
        if d.Rotation not in (0, 1):
            raise OSError("rotated screen")
        self.w, self.h = d.Width, d.Height
        k = 0
        while (self.w >> (k + 1)) >= grid_w and (self.h >> (k + 1)) >= 8:
            k += 1
        self.level, self.gw, self.gh = k, max(1, self.w >> k), max(1, self.h >> k)
        self.hdr_white = sdr_white_scale(device_name) or 2.5  # only used if the desktop is HDR (FP16)

    def _textures(self, fmt):
        tex2d = [ctypes.POINTER(D3D11_TEXTURE2D_DESC), VP, PVP]
        # mip chain down to the grid size, GPU-averaged by GenerateMips
        md = D3D11_TEXTURE2D_DESC(self.w, self.h, self.level + 1, 1, fmt, 1, 0, 0, 0x28, 0, 0x1)
        _hr(_call(self.device, 5, tex2d, byref(md), None, byref(self.mip)), "CreateTexture2D")
        _hr(_call(self.device, 7, [VP, VP, PVP], self.mip, None, byref(self.srv)), "CreateShaderResourceView")
        sd = D3D11_TEXTURE2D_DESC(self.gw, self.gh, 1, 1, fmt, 1, 0, 3, 0, 0x20000, 0)  # staging, CPU read
        _hr(_call(self.device, 5, tex2d, byref(sd), None, byref(self.staging)), "CreateTexture2D")
        self.bgr = fmt in (87, 91)
        self.hdr = fmt == 10  # R16G16B16A16_FLOAT: HDR desktop, linear scRGB

    def grab(self):
        for _ in range(4 if self.last is None else 1):
            info = (ctypes.c_ubyte * 64)()
            res = VP()
            hr = _call(self.dup, 8, [wt.UINT, VP, PVP], 100 if self.last is None else 0, info, byref(res))
            if (hr & 0xFFFFFFFF) == DXGI_ERROR_WAIT_TIMEOUT:
                continue  # nothing changed on screen
            _hr(hr, "AcquireNextFrame")  # e.g. ACCESS_LOST (mode change, UAC): the caller recreates us
            if struct.unpack_from("<q", bytes(info))[0] == 0:  # LastPresentTime 0: only the mouse moved
                _release(res)
                _call(self.dup, 14, [])  # ReleaseFrame
                continue
            return self._read(res)
        return self.last

    def _read(self, res):
        copy = [VP, wt.UINT, wt.UINT, wt.UINT, wt.UINT, VP, wt.UINT, VP]
        try:
            tex = _qi(res, IID_ID3D11Texture2D)
            try:
                td = D3D11_TEXTURE2D_DESC()
                _call(tex, 10, [ctypes.POINTER(D3D11_TEXTURE2D_DESC)], byref(td), restype=None)
                if not self.mip.value or td.Format != self.fmt:  # first frame, or SDR <-> HDR switch
                    if td.Format not in (87, 91, 28, 29, 10):
                        raise OSError(f"unsupported desktop format {td.Format}")
                    for p in (self.staging, self.srv, self.mip):
                        _release(p)
                    self._textures(td.Format)
                    self.fmt = td.Format
                _call(self.ctx, 46, copy, self.mip, 0, 0, 0, 0, tex, 0, None, restype=None)  # CopySubresourceRegion
            finally:
                _release(tex)
            _call(self.ctx, 54, [VP], self.srv, restype=None)  # GenerateMips
            _call(self.ctx, 46, copy, self.staging, 0, 0, 0, 0, self.mip, self.level, None, restype=None)
            m = D3D11_MAPPED_SUBRESOURCE()
            _hr(_call(self.ctx, 14, [VP, wt.UINT, wt.UINT, wt.UINT, ctypes.POINTER(D3D11_MAPPED_SUBRESOURCE)],
                      self.staging, 0, 1, 0, byref(m)), "Map")
            try:
                row = self.gw * (8 if self.hdr else 4)
                raw = b"".join(ctypes.string_at(m.pData + y * m.RowPitch, row) for y in range(self.gh))
            finally:
                _call(self.ctx, 15, [VP, wt.UINT], self.staging, 0, restype=None)  # Unmap
        finally:
            _release(res)
            _call(self.dup, 14, [])  # ReleaseFrame
        if self.hdr:
            # linear scRGB half floats -> SDR sRGB bytes, SDR white = Windows "SDR content brightness"
            vals = struct.unpack(f"<{self.gw * self.gh * 4}e", raw)
            s, lut = 4095.0 / self.hdr_white, SRGB_LUT
            self.last = tuple(bytes(lut[min(4095, int(v * s))] if v > 0.0 else 0 for v in vals[c::4]) for c in range(3))
        elif self.bgr:
            self.last = (raw[2::4], raw[1::4], raw[0::4])
        else:
            self.last = (raw[0::4], raw[1::4], raw[2::4])
        return self.last

    def close(self):
        for p in (self.staging, self.srv, self.mip, self.dup, self.output1, self.output, self.adapter,
                  self.ctx, self.device, self.factory):
            try:
                _release(p)
            except OSError:
                pass


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


def make_shaper(saturation, gamma, brightness, boost):
    """Screen color -> LED color: saturation, optional gamma, then a hue-preserving brightness lift."""

    def shape(r, g, b):
        if saturation != 1.0:
            l = 0.299 * r + 0.587 * g + 0.114 * b
            r, g, b = l + (r - l) * saturation, l + (g - l) * saturation, l + (b - l) * saturation
        r, g, b = min(255.0, max(0.0, r)), min(255.0, max(0.0, g)), min(255.0, max(0.0, b))
        if gamma != 1.0:
            r, g, b = (255.0 * (c / 255.0) ** gamma for c in (r, g, b))
        v = max(r, g, b) / 255.0
        if v <= 0.0:
            return 0.0, 0.0, 0.0
        if boost != 1.0:
            nv = v ** (1.0 / boost)  # dim colors get brighter, same hue
            if v < 0.03:
                nv *= v / 0.03       # a black screen stays black (no noise glow)
            k = nv / v
            r, g, b = r * k, g * k, b * k
        return r * brightness, g * brightness, b * brightness

    return shape


def detect_bars(R, G, B, gw, gh, threshold=14):
    """Content box (left, top, right, bottom) in grid cells, without letterbox / pillarbox black bars."""
    if max(R) <= threshold and max(G) <= threshold and max(B) <= threshold:
        return None  # black frame: no information

    def dark(s):
        return max(R[s]) <= threshold and max(G[s]) <= threshold and max(B[s]) <= threshold

    t = 0
    while t < gh // 3 and dark(slice(t * gw, (t + 1) * gw)):
        t += 1
    b = gh
    while b > gh - gh // 3 and dark(slice((b - 1) * gw, b * gw)):
        b -= 1
    l = 0
    while l < gw // 3 and dark(slice(l, None, gw)):
        l += 1
    r = gw
    while r > gw - gw // 3 and dark(slice(r - 1, None, gw)):
        r -= 1
    tb, lr = min(t, gh - b), min(l, gw - r)  # bars are symmetric; this ignores a dark sky on one side
    return lr, tb, gw - lr, gh - tb


def crop(R, G, B, gw, box):
    l, t, r, b = box
    rows = range(t, b)
    return tuple(b"".join(ch[y * gw + l:y * gw + r] for y in rows) for ch in (R, G, B))


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


def request_stop(quiet=False):
    h = k32.OpenEventW(0x0002, False, STOP_EVENT)  # EVENT_MODIFY_STATE
    if not h:
        if not quiet:
            print("Glowback is not running.")
        return False
    k32.SetEvent(h)
    k32.CloseHandle(h)
    if not quiet:
        print("Stop requested.")
    return True


def wanted(dev, device_filter):
    if device_filter == "all":
        return True
    if device_filter:
        f = _norm(device_filter)
        return f in _norm(dev.name) or f in f"{dev.vid:04X}{dev.pid:04X}"
    return dev.kind not in NOT_AMBIENT_KINDS


# =============================================================================
# OpenRGB SDK output: LED strips, monitors and any RGB gear OpenRGB supports
# =============================================================================
ORGB_TYPES = {0: "motherboard", 1: "RAM", 2: "GPU", 3: "cooler", 4: "LED strip", 5: "keyboard", 6: "mouse",
              7: "mousemat", 8: "headset", 9: "headset stand", 10: "gamepad", 11: "light", 12: "speaker",
              13: "virtual", 14: "storage", 15: "case", 16: "microphone", 17: "accessory", 18: "keypad"}
ORGB_AMBIENT_TYPES = {4, 11, 13, 15, 17}  # used by default; others need --device all or a name


class _Reader:
    def __init__(self, data):
        self.d, self.i = data, 0

    def take(self, fmt):
        v = struct.unpack_from("<" + fmt, self.d, self.i)
        self.i += struct.calcsize("<" + fmt)
        return v[0]

    def string(self):
        n = self.take("H")
        s = self.d[self.i:self.i + n]
        self.i += n
        return s.rstrip(b"\0").decode("utf-8", "replace")


def parse_orgb_controller(data, version):
    """Name, type, modes (raw bytes, to restore the user's effect) and zones of an OpenRGB controller."""
    r = _Reader(data)
    r.take("I")  # data size
    dtype = r.take("i")
    name = r.string()
    for _ in range(5 if version >= 1 else 4):  # vendor (v1+), description, version, serial, location
        r.string()
    n_modes, active = r.take("H"), r.take("i")
    modes = []
    for _ in range(n_modes):
        start = r.i
        r.string()
        r.i += 4 * (9 + (3 if version >= 3 else 0))  # value, flags, speed/(brightness)/colors fields, direction, color mode
        n_colors = r.take("H")
        r.i += 4 * n_colors
        modes.append(bytes(data[start:r.i]))
    zones = []
    for _ in range(r.take("H")):
        r.string()
        ztype, _min, _max, n_leds, msize = r.take("i"), r.take("I"), r.take("I"), r.take("I"), r.take("H")
        matrix = None
        if msize > 0:
            h, w = r.take("I"), r.take("I")
            matrix = (h, w, struct.unpack_from(f"<{h * w}I", data, r.i))
            r.i += 4 * h * w
        if version >= 4:
            for _ in range(r.take("H")):  # segments
                r.string()
                r.i += 12
        zones.append((ztype, n_leds, matrix))
    n_leds = r.take("H")
    return {"type": dtype, "name": name, "modes": modes, "active": active, "zones": zones, "leds": n_leds}


def perimeter_lamps(n, start="bottom-left", ccw=False, aspect=16 / 9):
    """n lamps evenly spread around the screen border, in strip order (clockwise as seen from the front)."""
    W, H = aspect, 1.0
    P = 2 * (W + H)
    offset = {"bottom-left": 0.0, "top-left": H, "top-right": H + W, "bottom-right": 2 * H + W,
              "bottom-center": 2 * H + 1.5 * W}[start]
    lamps = []
    for i in range(n):
        d = (offset + (-1 if ccw else 1) * (i + 0.5) / n * P) % P
        if d < H:
            x, y = 0.0, H - d
        elif d < H + W:
            x, y = d - H, 0.0
        elif d < 2 * H + W:
            x, y = W, d - H - W
        else:
            x, y = W - (d - 2 * H - W), H
        lamps.append(Lamp(i, round(x * 1000), round(y * 1000), 0))
    return lamps


class OpenRGBClient:
    def __init__(self, address):
        host, _, port = address.partition(":")
        self.address = f"{host or '127.0.0.1'}:{port or 6742}"
        self.sock = socket.create_connection((host or "127.0.0.1", int(port or 6742)), timeout=2)
        self.version = 0
        self.send(0, 40, struct.pack("<I", 4))  # REQUEST_PROTOCOL_VERSION
        try:
            self.sock.settimeout(1)
            self.version = min(4, struct.unpack("<I", self.recv(0, 40)[:4])[0])
        except socket.timeout:
            self.version = 0  # very old server: no reply
        self.sock.settimeout(3)
        self.send(0, 50, b"Glowback\0")  # SET_CLIENT_NAME

    def send(self, dev, pkt, payload=b""):
        self.sock.sendall(b"ORGB" + struct.pack("<III", dev, pkt, len(payload)) + payload)

    def _exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OSError("OpenRGB closed the connection")
            buf += chunk
        return buf

    def recv(self, dev, pkt):
        """Next reply of type `pkt` for `dev`, skipping notifications (e.g. device list updated)."""
        while True:
            hdr = self._exact(16)
            if hdr[:4] != b"ORGB":
                raise OSError("unexpected data from OpenRGB")
            d, p, size = struct.unpack("<III", hdr[4:])
            data = self._exact(size)
            if d == dev and p == pkt:
                return data

    def controllers(self):
        self.send(0, 0)  # REQUEST_CONTROLLER_COUNT
        count = struct.unpack("<I", self.recv(0, 0)[:4])[0]
        out = []
        for idx in range(count):
            self.send(idx, 1, struct.pack("<I", self.version) if self.version else b"")  # REQUEST_CONTROLLER_DATA
            out.append((idx, parse_orgb_controller(self.recv(idx, 1), self.version)))
        return out

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class OpenRGBDevice:
    """An OpenRGB controller, driven like a LampArray (same interface as LampArray)."""
    vid = pid = 0
    intensity = 1
    width_mm = height_mm = 0

    def __init__(self, client, idx, info, start, ccw):
        self.client, self.idx = client, idx
        self.path = f"openrgb:{client.address}:{idx}:{info['name']}"
        self.name = info["name"]
        self.orgb_type = info["type"]
        self.kind = 5 if info["type"] in ORGB_AMBIENT_TYPES or "monitor" in info["name"].lower() else 1
        self.kind_label = f"OpenRGB {ORGB_TYPES.get(info['type'], 'device')}"
        self.min_interval = 1 / 60
        a = info["active"]
        self.restore = (a, info["modes"][a]) if 0 <= a < len(info["modes"]) else None
        n = info["leds"]
        zones = info["zones"]
        if zones and all(m for _, _, m in zones) and len(zones) == 1:
            h, w, cells = zones[0][2]  # matrix device: use the matrix positions
            pos = {v: (i % w, i // w) for i, v in enumerate(cells) if v != 0xFFFFFFFF}
            self.lamps = [Lamp(i, *(pos.get(i, (w / 2, h / 2))), 0) for i in range(n)]
        else:  # LED strip: assume it runs around the screen, in order
            self.lamps = perimeter_lamps(n, start, ccw)
        if not self.lamps:
            raise Unsupported("no LEDs")

    def set_autonomous(self, on):
        if not on:
            self.client.send(self.idx, 1100)  # SETCUSTOMMODE (direct control)
        elif self.restore:
            mode_idx, raw = self.restore  # UPDATEMODE: put the user's effect back
            self.client.send(self.idx, 1101, struct.pack("<Ii", 8 + len(raw), mode_idx) + raw)

    def send(self, colors):
        body = struct.pack("<H", len(colors)) + b"".join(bytes((r, g, b, 0)) for r, g, b in colors)
        self.client.send(self.idx, 1050, struct.pack("<I", 4 + len(body)) + body)  # UPDATELEDS

    def send_all(self, rgb):
        self.send([rgb] * len(self.lamps))

    def close(self):
        pass  # the shared connection is closed by the client


_openrgb = {"client": None, "warned": False}


def open_openrgb_devices(args, known=(), include_all=False):
    if not args.openrgb:
        return [], []
    client = _openrgb["client"]
    try:
        if client is None:
            client = _openrgb["client"] = OpenRGBClient(args.openrgb)
            log(f"OpenRGB SDK connected ({client.address}, protocol {client.version})")
            _openrgb["warned"] = False
        found = client.controllers()
    except OSError as e:
        if client:
            client.close()
        _openrgb["client"] = None
        if not _openrgb["warned"]:
            log(f"OpenRGB SDK server not reachable at {args.openrgb} ({e}). Start OpenRGB and click 'Start Server' "
                "in its SDK Server tab.")
            _openrgb["warned"] = True
        return [], []
    devs, skipped = [], []
    for idx, info in found:
        try:
            dev = OpenRGBDevice(client, idx, info, args.strip_start, args.strip_ccw)
        except OSError as e:
            skipped.append(f"{info['name']}: {e}")
            continue
        if dev.path not in known and (include_all or wanted(dev, args.device)):
            devs.append(dev)
    return devs, skipped


def open_devices(device_filter, known=(), args=None):
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
    if args is not None:
        d2, s2 = open_openrgb_devices(args, known)
        devs += d2
        skipped += s2
    return devs, skipped


def device_key(dev):
    return f"openrgb:{dev.name}" if isinstance(dev, OpenRGBDevice) else f"{dev.vid:04X}:{dev.pid:04X}"


def kind_label(dev):
    return getattr(dev, "kind_label", None) or KINDS.get(dev.kind, dev.kind)


def cmd_calibrate(args, stop):
    """Interactive white balance per device: make the wall look neutral white."""
    import msvcrt
    devs, _ = open_devices(args.device, (), args)
    if not devs:
        print("No LED device found (glowback --list).")
        return
    all_wb = load_settings().get("white_balance", {})
    print("White balance: adjust until the light on the wall looks neutral white.")
    print("  r / R  less / more red     g / G  green     b / B  blue")
    print("  1 2 3 4  test at 100 / 50 / 25 / 10 %     Enter  save     Esc  skip this device\n")
    try:
        for d in devs:
            key = device_key(d)
            wb = list(all_wb.get(key, (1.0, 1.0, 1.0)))
            level = 1.0
            d.set_autonomous(False)
            print(f"{d.name}:")
            while not stop.wait(0):
                d.send([tuple(min(255, round(255 * level * c)) for c in wb)] * len(d.lamps))
                print(f"\r  red {wb[0]:.2f}   green {wb[1]:.2f}   blue {wb[2]:.2f}   (level {level:.0%})   ", end="", flush=True)
                ch = msvcrt.getwch()
                if ch and ch in "rgb":
                    i = "rgb".index(ch)
                    wb[i] = max(0.0, round(wb[i] - 0.02, 2))
                elif ch and ch in "RGB":
                    i = "RGB".index(ch)
                    wb[i] = min(1.0, round(wb[i] + 0.02, 2))
                elif ch in ("1", "2", "3", "4"):
                    level = {"1": 1.0, "2": 0.5, "3": 0.25, "4": 0.1}[ch]
                elif ch == "\r":
                    all_wb[key] = wb
                    save_settings({"white_balance": all_wb})
                    print("\n  saved.")
                    break
                elif ch == "\x1b":
                    print("\n  skipped.")
                    break
            d.set_autonomous(True)
    finally:
        for d in devs:
            d.close()
    print("Restart Glowback (or it picks this up at its next start).")


def cmd_diy_layout(spec):
    """C code for Microsoft's RP2040 LampArray sample (src/util.h): LEDs around a monitor, strip order."""
    try:
        size, counts = spec.lower().split(":")
        w_mm, h_mm = (float(v) for v in size.split("x"))
        left, top, right, bottom = (int(v) for v in counts.split(","))
    except ValueError:
        sys.exit("Format: WIDTHxHEIGHT:LEFT,TOP,RIGHT,BOTTOM in mm and LEDs per side, e.g. 600x340:17,30,17,30")
    W, H = round(w_mm * 1000), round(h_mm * 1000)  # micrometers
    pts = []
    for i in range(left):    # strip starts bottom-left, goes up the left side (clockwise seen from the front)
        pts.append((0, round(H - (i + 0.5) * H / left)))
    for i in range(top):
        pts.append((round((i + 0.5) * W / top), 0))
    for i in range(right):
        pts.append((W, round((i + 0.5) * H / right)))
    for i in range(bottom):
        pts.append((round(W - (i + 0.5) * W / bottom), H))
    n = len(pts)
    print(f"// Generated by: glowback --diy-layout {spec}")
    print(f"// Strip: starts at the bottom-left corner, goes up the left side, then clockwise ({n} LEDs)")
    print("#define NEOPIXEL                    19       // GPIO of the strip's DIN wire")
    print(f"#define NEOPIXEL_COUNT              {n}")
    print("#define LAMPARRAY_LAMP_COUNT        NEOPIXEL_COUNT")
    print(f"#define LAMPARRAY_WIDTH             {W}")
    print(f"#define LAMPARRAY_HEIGHT            {H}")
    print("#define LAMPARRAY_DEPTH             10000")
    print("#define LAMPARRAY_KIND              5        // LampArrayKindScene (ambient light)")
    print("static Position LampPositions[NEOPIXEL_COUNT] = {")
    for i in range(0, n, 4):
        print("    " + " ".join(f"{{{x}, {y}, 0}}," for x, y in pts[i:i + 4]))
    print("};")


class Output:
    """One LED device bound to one screen."""

    def __init__(self, dev):
        self.dev = dev
        self.monitor = None
        self.weights = {}  # (grid w, grid h, content w, content h) -> per-lamp weights
        self.smooth = None
        self.last = None
        self.box = self.box_grid = None  # letterbox detection, with hysteresis
        self.cand, self.cand_since = None, 0.0
        self.wb = (1.0, 1.0, 1.0)  # white balance multipliers (glowback --calibrate)


class State:
    """Live settings shared between the capture loop and the tray icon."""

    def __init__(self, args, enabled=True):
        self.enabled = enabled
        self.mode = args.mode
        self.brightness = max(0.0, min(100.0, float(args.brightness)))
        self.version = 0

    def update(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.version += 1
        save_settings({"enabled": self.enabled, "mode": self.mode, "brightness": self.brightness})


def make_grabber(monitor, args, failed):
    if args.capture != "gdi":
        try:
            g = DxgiGrabber(monitor, args.grid)
            failed.discard(monitor.rect)
            return g
        except OSError as e:
            if monitor.rect not in failed:
                log(f"  DXGI capture unavailable ({e}), falling back to GDI")
                failed.add(monitor.rect)
    return ScreenGrabber(monitor.rect, args.grid)


def run(args, stop, state=None):
    state = state or State(args)
    outputs, grabbers, dxgi_failed = {}, {}, set()
    period = 1.0 / max(1.0, args.fps)
    next_scan = next_keep = 0.0
    monitors = []
    frames, t_stat = 0, time.perf_counter()
    t_prev = time.perf_counter()
    warned = paused = False
    seen, shape = -1, None
    try:
        while True:
            t0 = time.perf_counter()
            dt, t_prev = t0 - t_prev, t0
            if state.version != seen:
                seen = state.version
                shape = make_shaper(args.saturation, args.gamma, state.brightness / 100.0, args.boost)
                for o in outputs.values():
                    o.last = None

            # ---- paused from the tray: the LEDs go back to the device's own effect
            if not state.enabled:
                if not paused:
                    paused = True
                    for o in outputs.values():
                        try:
                            o.dev.set_autonomous(True)
                        except OSError:
                            pass
                    log("Paused: LEDs handed back to the device.")
                if stop.wait(0.25):
                    break
                continue
            if paused:
                paused = False
                next_keep = 0.0
                for o in outputs.values():
                    o.smooth = o.last = None
                log("Resumed.")

            # ---- (re)scan devices and screens: hot-plug, monitor power cycles, resolution changes
            if t0 >= next_scan:
                next_scan = t0 + 5
                new_monitors = list_monitors()
                changed = [(m.device, m.rect) for m in new_monitors] != [(m.device, m.rect) for m in monitors]
                monitors = new_monitors
                devs, _ = open_devices(args.device, outputs.keys(), args)
                for dev in devs:
                    try:
                        dev.set_autonomous(False)
                    except OSError as e:
                        log(f"{dev.name}: cannot take control ({e})")
                        dev.close()
                        continue
                    o = outputs[dev.path] = Output(dev)
                    o.wb = args.white_balance or tuple(load_settings().get("white_balance", {}).get(device_key(dev), o.wb))
                    period = max(period, dev.min_interval)
                    log(f"Connected: {dev.name} ({len(dev.lamps)} LEDs, {kind_label(dev)})")
                    if dynamic_lighting_enabled(dev.path):
                        log("  ! Windows Dynamic Lighting is ON for this device and will fight Glowback: turn it off in "
                            "Settings > Personalization > Dynamic Lighting > (device) > 'Use Dynamic Lighting on my devices'.")
                    changed = True
                if changed:
                    for o in outputs.values():
                        m = pick_monitor(o.dev.name, monitors, args.screen)
                        if m is not o.monitor or not o.weights:
                            o.monitor, o.weights, o.smooth, o.box = m, {}, None, None
                            if m:
                                log(f"  {o.dev.name}  <-  screen {m.label()}")
                    for rect in list(grabbers):
                        grabbers.pop(rect).close()
                elif args.capture == "auto":
                    for rect, g in list(grabbers.items()):  # retry DXGI (e.g. it failed on the lock screen)
                        if g.kind == "GDI":
                            grabbers.pop(rect).close()
                if not outputs and not warned:
                    log("Waiting for a Dynamic Lighting (HID LampArray) device... (glowback --list to check)")
                    warned = True

            # ---- one frame
            keep = t0 >= next_keep
            if keep:
                next_keep = t0 + 5
            frames_by_rect = {}
            for path, o in list(outputs.items()):
                m = o.monitor
                if m is None:
                    continue
                if m.rect not in frames_by_rect:
                    g = grabbers.get(m.rect)
                    if g is None:
                        g = grabbers[m.rect] = make_grabber(m, args, dxgi_failed)
                        log(f"  capture: {g.kind}, {g.gw}x{g.gh} grid")
                    try:
                        px = g.grab()
                    except OSError as e:
                        log(f"  capture restarted ({e})")
                        grabbers.pop(m.rect).close()
                        px = None
                    frames_by_rect[m.rect] = (px, g.gw, g.gh) if px else None
                frame = frames_by_rect[m.rect]
                if frame is None:
                    continue
                (R, G, B), gw, gh = frame

                # letterbox / pillarbox: follow the picture, not the black bars
                box = (0, 0, gw, gh)
                if args.letterbox == "on":
                    if o.box_grid != (gw, gh):
                        o.box, o.box_grid, o.cand = None, (gw, gh), None
                    cand = detect_bars(R, G, B, gw, gh) or o.box or box
                    if o.box is None:
                        o.box = cand
                    elif cand != o.box:
                        if cand != o.cand:
                            o.cand, o.cand_since = cand, t0
                        elif t0 - o.cand_since > 0.4:
                            o.box, o.cand = cand, None
                    box = o.box
                cw, ch = box[2] - box[0], box[3] - box[1]
                if (cw, ch) != (gw, gh):
                    R, G, B = crop(R, G, B, gw, box)
                n = len(R)
                avg = (sum(R) / n, sum(G) / n, sum(B) / n)

                if state.mode == "average":
                    targets = [shape(*avg)]
                else:
                    key = (gw, gh, cw, ch)
                    weights = o.weights.get(key)
                    if weights is None:
                        sw, sh = m.size
                        aspect = (cw / gw * sw) / (ch / gh * sh)
                        pts = [edge_point(u, v) for u, v in lamp_uv(o.dev.lamps, args.mirror, args.flip)]
                        weights = o.weights[key] = build_weights(pts, cw, ch, aspect, args.radius)
                    bl = args.blend
                    targets = []
                    for wgt in weights:
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
                wr, wg, wb = o.wb
                out = [(min(255, max(0, round(s[0] * wr))), min(255, max(0, round(s[1] * wg))),
                        min(255, max(0, round(s[2] * wb)))) for s in o.smooth]
                try:
                    if keep:
                        o.dev.set_autonomous(False)  # in case the device fell back to its own effects
                    if out != o.last or keep:
                        if len(out) == 1:
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
    if args.openrgb:
        print(f"\nOpenRGB devices ({args.openrgb}):")
        devs, skipped = open_openrgb_devices(args, include_all=True)
        if not devs and not skipped:
            print("  none (is OpenRGB running with its SDK server started?)")
        for d in devs:
            sel = "used" if wanted(d, args.device) else "ignored (use --device all or --device NAME)"
            print(f"  {d.name}  {len(d.lamps)} LEDs, {kind_label(d)}  -> {sel}")
        for s_ in skipped:
            print(f"  {s_}  -> not usable")


def cmd_test(args, stop):
    devs, skipped = open_devices(args.device, (), args)
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


# =============================================================================
# Windows integration: settings, icon, autostart, Start menu, tray icon
# =============================================================================
SETTINGS_PATH = os.path.join(LOG_DIR, "settings.json")
START_MENU_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs", "Glowback.lnk")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REPO_URL = "https://github.com/Ilyomix/glowback"


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    """Merge `data` into settings.json."""
    try:
        merged = load_settings()
        merged.update(data)
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=1)
    except OSError:
        pass


def icon_pixels(size, paused=False):
    """BGRA pixels of the Glowback icon: a glowing ring, blue -> violet -> orange."""
    stops = ((0.0, (64, 112, 255)), (0.35, (168, 76, 255)), (0.7, (255, 84, 128)), (1.0, (255, 170, 60)))

    def grad(t):
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t <= t1:
                f = (t - t0) / (t1 - t0)
                return tuple(c0[i] + (c1[i] - c0[i]) * f for i in range(3))
        return stops[-1][1]

    px = bytearray(size * size * 4)
    c = size / 2
    for y in range(size):
        for x in range(size):
            dx, dy = x + 0.5 - c, y + 0.5 - c
            r = math.hypot(dx, dy) / c
            ring = max(0.0, 1.0 - abs(r - 0.66) / 0.2) ** 0.8  # soft ring
            glow = max(0.0, 1.0 - r) * 0.35                     # inner glow
            alpha = min(1.0, ring * 1.6 + glow)
            t = (math.atan2(dx, -dy) / (2 * math.pi)) % 1.0
            col = grad(1.0 - abs(2 * t - 1.0))
            if paused:
                l = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
                col, alpha = (l, l, l), alpha * 0.75
            i = (y * size + x) * 4
            px[i:i + 4] = bytes((int(col[2]), int(col[1]), int(col[0]), int(255 * alpha)))
    return px


def write_ico(path, paused=False, sizes=(16, 20, 24, 32, 48, 64, 256)):
    images = []
    for s in sizes:
        rows = icon_pixels(s, paused)
        xor = b"".join(bytes(rows[y * s * 4:(y + 1) * s * 4]) for y in reversed(range(s)))
        andmask = bytes(((s + 31) // 32) * 4 * s)
        bih = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, len(xor) + len(andmask), 0, 0, 0, 0)
        images.append((s, bih + xor + andmask))
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, data in images:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(d for _, d in images))


def ensure_icons():
    os.makedirs(LOG_DIR, exist_ok=True)
    paths = os.path.join(LOG_DIR, f"glowback-{__version__}.ico"), os.path.join(LOG_DIR, f"glowback-{__version__}-paused.ico")
    for p, paused in zip(paths, (False, True)):
        if not os.path.exists(p):
            write_ico(p, paused)
    return paths


def launch_command(extra=()):
    """Command line that starts Glowback in the background (tray icon, no console)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background", *extra]
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return [pyw if os.path.exists(pyw) else sys.executable, os.path.abspath(__file__), *extra]


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "Glowback")
            return True
    except OSError:
        return False


def set_autostart(enable, argv=()):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, "Glowback", 0, winreg.REG_SZ,
                              subprocess.list2cmdline(launch_command(["--from-autostart", *argv])))
        else:
            try:
                winreg.DeleteValue(k, "Glowback")
            except FileNotFoundError:
                pass


def make_start_menu_shortcut(argv=()):
    icon = ensure_icons()[0]
    cmd = launch_command(argv)
    q = lambda s: "'" + s.replace("'", "''") + "'"  # PowerShell single-quoted string
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({q(START_MENU_LNK)});"
              f"$s.TargetPath={q(cmd[0])};$s.Arguments={q(subprocess.list2cmdline(cmd[1:]))};"
              f"$s.IconLocation={q(icon)};$s.Description={q('Glowback - Ambilight for your monitor RGB LEDs')};$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                   creationflags=0x08000000, capture_output=True)  # CREATE_NO_WINDOW


def cmd_install(argv):
    set_autostart(True, argv)
    make_start_menu_shortcut(argv)
    print("Glowback is installed:")
    print("  - starts with Windows, in the background (tray icon next to the clock)")
    print("  - 'Glowback' is in the Start menu")
    print("Right-click the tray icon to pause it, change mode or brightness, or quit.")
    print("To remove it: glowback --uninstall")


def cmd_uninstall():
    if request_stop(quiet=True):
        for _ in range(30):  # wait for the running instance to hand the LEDs back and exit
            h = k32.OpenEventW(0x00100000, False, STOP_EVENT)  # SYNCHRONIZE
            if not h:
                break
            k32.CloseHandle(h)
            time.sleep(0.1)
    set_autostart(False)
    for path in (START_MENU_LNK,):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    import shutil
    shutil.rmtree(LOG_DIR, ignore_errors=True)
    print("Glowback was stopped and removed from startup, the Start menu and %LOCALAPPDATA%\\Glowback.")
    if getattr(sys, "frozen", False):
        print(f"Last step: delete {sys.executable}")
    else:
        print("Last step: pip uninstall glowback   (or delete glowback.py)")


# ---- tray icon (notification area), pure Win32
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", HANDLE), ("hIcon", HANDLE), ("hCursor", HANDLE),
                ("hbrBackground", HANDLE), ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
                ("hIconSm", HANDLE)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", HANDLE), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", HANDLE), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", HANDLE)]


_sig(user32.RegisterClassExW, wt.WORD, ctypes.POINTER(WNDCLASSEXW))
_sig(user32.CreateWindowExW, HANDLE, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, ctypes.c_int, HANDLE, HANDLE, HANDLE, ctypes.c_void_p)
_sig(user32.DefWindowProcW, LRESULT, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
_sig(user32.GetMessageW, wt.BOOL, ctypes.POINTER(wt.MSG), HANDLE, wt.UINT, wt.UINT)
_sig(user32.TranslateMessage, wt.BOOL, ctypes.POINTER(wt.MSG))
_sig(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wt.MSG))
_sig(user32.PostMessageW, wt.BOOL, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
_sig(user32.PostQuitMessage, None, ctypes.c_int)
_sig(user32.DestroyWindow, wt.BOOL, HANDLE)
_sig(user32.CreatePopupMenu, HANDLE)
_sig(user32.AppendMenuW, wt.BOOL, HANDLE, wt.UINT, ctypes.c_size_t, wt.LPCWSTR)
_sig(user32.TrackPopupMenu, ctypes.c_int, HANDLE, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, HANDLE, ctypes.c_void_p)
_sig(user32.DestroyMenu, wt.BOOL, HANDLE)
_sig(user32.GetCursorPos, wt.BOOL, ctypes.POINTER(wt.POINT))
_sig(user32.SetForegroundWindow, wt.BOOL, HANDLE)
_sig(user32.RegisterWindowMessageW, wt.UINT, wt.LPCWSTR)
_sig(user32.LoadImageW, HANDLE, HANDLE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT)
_sig(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
_sig(user32.DestroyIcon, wt.BOOL, HANDLE)
_sig(shell32.Shell_NotifyIconW, wt.BOOL, wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_sig(k32.GetModuleHandleW, HANDLE, wt.LPCWSTR)


class Tray:
    """Notification-area icon: pause/resume, mode, brightness, start with Windows, quit."""
    WM_TRAY, WM_CLOSE_APP = 0x8001, 0x8002

    def __init__(self, state, stop, argv):
        self.state, self.stop, self.argv = state, stop, argv
        on, off = ensure_icons()
        cx, cy = user32.GetSystemMetrics(49), user32.GetSystemMetrics(50)  # SM_CXSMICON, SM_CYSMICON
        self.icons = (user32.LoadImageW(None, on, 1, cx, cy, 0x10), user32.LoadImageW(None, off, 1, cx, cy, 0x10))
        self._proc_ref = WNDPROC(self._proc)
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._proc_ref, hinst, "GlowbackTray"
        user32.RegisterClassExW(byref(wc))
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = user32.CreateWindowExW(0, "GlowbackTray", "Glowback", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.seen = state.version
        shell32.Shell_NotifyIconW(0, byref(self._nid()))  # NIM_ADD

    def _nid(self, info=None):
        n = NOTIFYICONDATAW()
        n.cbSize, n.hWnd, n.uID, n.uCallbackMessage = sizeof(n), self.hwnd, 1, self.WM_TRAY
        n.uFlags = 0x1 | 0x2 | 0x4  # MESSAGE | ICON | TIP
        n.hIcon = self.icons[0 if self.state.enabled else 1]
        n.szTip = "Glowback: ambilight on" if self.state.enabled else "Glowback: paused"
        if info:
            n.uFlags |= 0x10  # NIF_INFO
            n.szInfoTitle, n.szInfo = info
        return n

    def refresh(self, info=None):
        shell32.Shell_NotifyIconW(1, byref(self._nid(info)))  # NIM_MODIFY

    def close_from_thread(self):
        user32.PostMessageW(self.hwnd, self.WM_CLOSE_APP, 0, 0)

    def loop(self):
        msg = wt.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            if (lparam & 0xFFFF) in (0x0202, 0x0205, 0x007B):  # left/right click, context menu
                self._menu()
            return 0
        if msg == self.WM_CLOSE_APP:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            shell32.Shell_NotifyIconW(2, byref(self._nid()))  # NIM_DELETE
            user32.PostQuitMessage(0)
            return 0
        if self.taskbar_created and msg == self.taskbar_created:  # Explorer restarted
            shell32.Shell_NotifyIconW(0, byref(self._nid()))
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self):
        s = self.state
        menu, sub = user32.CreatePopupMenu(), user32.CreatePopupMenu()
        add = lambda m, flags, cid, text: user32.AppendMenuW(m, flags, cid, text)
        CHECK, GRAY, SEP, POPUP = 0x8, 0x1, 0x800, 0x10
        add(menu, GRAY, 0, f"Glowback {__version__}")
        add(menu, SEP, 0, None)
        add(menu, CHECK if s.enabled else 0, 1, "Ambilight enabled")
        add(menu, SEP, 0, None)
        add(menu, CHECK if s.mode == "zones" else 0, 2, "Each LED follows its zone")
        add(menu, CHECK if s.mode == "average" else 0, 3, "One average color")
        for i, v in enumerate((100, 75, 50, 25)):
            add(sub, CHECK if round(s.brightness) == v else 0, 10 + i, f"{v} %")
        add(menu, POPUP, sub, "Brightness")
        add(menu, SEP, 0, None)
        add(menu, CHECK if autostart_enabled() else 0, 20, "Start with Windows")
        add(menu, 0, 21, "Open log")
        add(menu, 0, 22, "Help and updates")
        add(menu, SEP, 0, None)
        add(menu, 0, 99, "Quit")
        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0080 | 0x0002, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, 0, 0, 0)
        user32.DestroyMenu(menu)
        if cmd == 1:
            s.update(enabled=not s.enabled)
            self.refresh()
        elif cmd in (2, 3):
            s.update(mode="zones" if cmd == 2 else "average")
        elif 10 <= cmd <= 13:
            s.update(brightness=(100, 75, 50, 25)[cmd - 10])
        elif cmd == 20:
            set_autostart(not autostart_enabled(), self.argv)
        elif cmd == 21:
            os.startfile(LOG_PATH)
        elif cmd == 22:
            os.startfile(REPO_URL)
        elif cmd == 99:
            k32.SetEvent(self.stop.h)


def run_with_tray(args, stop, state, argv):
    try:
        tray = Tray(state, stop, argv)
    except OSError as e:
        log(f"Tray icon unavailable ({e}), running without it.")
        return run(args, stop, state)
    worker_error = []

    def worker():
        try:
            run(args, stop, state)
        except Exception as e:  # keep the tray from hanging if the loop crashes
            worker_error.append(e)
            log(f"Error: {e!r}")
        finally:
            tray.close_from_thread()

    t = threading.Thread(target=worker, name="glowback-capture", daemon=True)
    t.start()
    if not args.from_autostart:
        tray.refresh(("Glowback is running", "Right-click this icon to pause it, change mode or brightness, or quit."))
    tray.loop()
    k32.SetEvent(stop.h)
    t.join(5)
    for icon in tray.icons:
        user32.DestroyIcon(icon)
    if worker_error:
        raise worker_error[0]


# =============================================================================
# Command line
# =============================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="glowback",
        description="Ambilight for monitors with RGB LEDs on the back (Windows Dynamic Lighting / HID LampArray).",
        epilog="Example: glowback --brightness 70 --smoothing 0.2")
    p.add_argument("--mode", choices=["zones", "average"], default=None,
                   help="zones: each LED follows the part of the image it sits behind (default); average: one color")
    p.add_argument("--screen", default="auto",
                   help="screen to follow: auto (EDID model match, else primary), primary, a number from --list, or a name")
    p.add_argument("--device", default=None,
                   help="LED devices to drive: part of a name or VID:PID, or 'all' (default: all but keyboards/mice)")
    p.add_argument("--fps", type=float, default=30, help="updates per second (default 30)")
    p.add_argument("--brightness", type=float, default=None, help="0-100 (default 100, or the tray setting)")
    p.add_argument("--boost", type=float, default=1.8, help="lifts dim colors, same hue; 1 = off (default 1.8)")
    p.add_argument("--saturation", type=float, default=1.25, help="color boost, 1 = none (default 1.25)")
    p.add_argument("--gamma", type=float, default=1.0, help="per-channel LED gamma, >1 = deeper darks (default 1.0)")
    p.add_argument("--smoothing", type=float, default=0.1, help="transition time in seconds (default 0.1)")
    p.add_argument("--radius", type=float, default=0.12, help="size of each LED's zone, fraction of screen height (default 0.12)")
    p.add_argument("--blend", type=float, default=0.0, help="0-1, mix of the whole-screen average into each zone (default 0)")
    p.add_argument("--letterbox", choices=["on", "off"], default="on", help="ignore movie black bars (default on)")
    p.add_argument("--capture", choices=["auto", "dxgi", "gdi"], default="auto",
                   help="screen capture: DXGI (GPU, sees fullscreen video and games) with GDI fallback (default auto)")
    p.add_argument("--grid", type=int, default=48, help="minimum capture grid width in cells (default 48)")
    p.add_argument("--mirror", action="store_true", help="swap left/right if your device reports mirrored positions")
    p.add_argument("--flip", action="store_true", help="swap top/bottom")
    p.add_argument("--openrgb", nargs="?", const="127.0.0.1:6742", metavar="HOST:PORT",
                   help="also drive OpenRGB devices through its SDK server (default 127.0.0.1:6742)")
    p.add_argument("--strip-start", default="bottom-left",
                   choices=["bottom-left", "bottom-center", "bottom-right", "top-left", "top-right"],
                   help="OpenRGB LED strips: where the first LED is (strip runs around the screen)")
    p.add_argument("--strip-ccw", action="store_true", help="OpenRGB LED strips run counter-clockwise (seen from the front)")
    p.add_argument("--white-balance", type=lambda v: tuple(float(x) for x in v.split(",")), metavar="R,G,B",
                   help="color multipliers 0-1 for all devices, e.g. 1,0.9,0.8 (default: from --calibrate)")
    p.add_argument("--calibrate", action="store_true", help="interactive per-device white balance, then exit")
    p.add_argument("--diy-layout", metavar="WxH:L,T,R,B",
                   help="print LED positions for a DIY RP2040 strip (see docs/DIY-LED-strip.md), then exit")
    p.add_argument("--no-tray", action="store_true", help="no notification-area icon")
    p.add_argument("--list", action="store_true", help="list LED devices and screens, then exit")
    p.add_argument("--test", action="store_true", help="play an orientation test pattern, then exit")
    p.add_argument("--stop", action="store_true", help="stop the running Glowback instance")
    p.add_argument("--install", action="store_true", help="start with Windows + Start menu entry (keeps the other options)")
    p.add_argument("--uninstall", action="store_true", help="stop Glowback and remove it from startup, Start menu and app data")
    p.add_argument("--autostart", choices=["on", "off"], help="start Glowback with Windows (with the other options given)")
    p.add_argument("--background", action="store_true", help="detach from the console (log in %%LOCALAPPDATA%%\\Glowback)")
    p.add_argument("--from-autostart", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("-v", "--verbose", action="store_true", help="print fps")
    p.add_argument("--version", action="version", version=f"glowback {__version__}")
    return p.parse_args(argv)


def _passthrough(raw):
    """Options to keep when Glowback relaunches itself (autostart, Start menu)."""
    out, skip = [], False
    for a in raw:
        if skip:
            skip = False
            continue
        if a in ("--install", "--uninstall", "--from-autostart", "--background", "--stop"):
            continue
        if a == "--autostart":
            skip = True
            continue
        if a.startswith("--autostart="):
            continue
        out.append(a)
    return out


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw)
    keep = _passthrough(raw)
    if args.stop:
        request_stop()
        return
    if args.diy_layout:
        cmd_diy_layout(args.diy_layout)
        return
    if args.uninstall:
        cmd_uninstall()
        return
    if args.install:
        cmd_install(keep)
        return
    if args.autostart:
        set_autostart(args.autostart == "on", keep)
        print("Autostart enabled." if args.autostart == "on" else "Autostart disabled.")
        return
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixels
    except AttributeError:
        user32.SetProcessDPIAware()
    if args.list:
        cmd_list(args)
        return
    saved = load_settings()
    if args.mode is None:
        args.mode = saved.get("mode", "zones")
    if args.brightness is None:
        args.brightness = saved.get("brightness", 100)
    enabled = saved.get("enabled", True) if args.from_autostart else True
    os.makedirs(LOG_DIR, exist_ok=True)
    stop = StopSignal()
    if stop.already_running:
        print("Glowback is already running (see the tray icon). Stop it first: glowback --stop")
        sys.exit(1)
    if args.background or sys.stdout is None:
        k32.FreeConsole()
        sys.stdout = sys.stderr = None
    try:
        if args.test:
            cmd_test(args, stop)
        elif args.calibrate:
            cmd_calibrate(args, stop)
        else:
            try:
                open(LOG_PATH, "w").close()
            except OSError:
                pass
            log(f"Glowback {__version__} - mode {args.mode}, {args.fps:g} fps. Ctrl+C or 'glowback --stop' to quit.")
            state = State(args, enabled)
            if args.no_tray:
                run(args, stop, state)
            else:
                run_with_tray(args, stop, state, keep)
    except KeyboardInterrupt:
        pass
    finally:
        stop.done.set()


if __name__ == "__main__":
    main()
