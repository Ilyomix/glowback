#!/usr/bin/env python3
"""
Glowback - ambient light for any monitor with RGB LEDs on the back.

Real-time, screen-synced bias lighting for every Windows "Dynamic Lighting"
(HID LampArray) device: monitors with rear RGB (e.g. AOC AGON PRO Light FX),
LED strips, cases... Each LED follows the part of the image it sits behind,
like Philips Ambilight - no camera, no vendor app, no extra hardware.

Single file, zero dependencies, pure Python + Win32 (ctypes).

    glowback                 start the ambilight (each LED follows its own zone)
    glowback --mode average  one average color for all LEDs
    glowback --mode music    the LEDs follow the sound the PC plays
    glowback --list          show detected LED devices and screens
    glowback --test          orientation test pattern
    glowback --stop          stop the running instance

https://github.com/Ilyomix/glowback  -  MIT License
"""
import argparse
import base64
import cmath
import colorsys
import ctypes
import ctypes.wintypes as wt
import hashlib
import hmac
import json
import math
import os
import queue
import random
import re
import select
import socket
import struct
import subprocess
import sys
import threading
import time
from array import array
from ctypes import byref, sizeof
from operator import itemgetter, mul

__version__ = "0.8.0"

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
_sig(k32.GetCurrentPackageFamilyName, wt.LONG, ctypes.POINTER(wt.UINT), wt.LPWSTR)


def package_family():
    """Package family name when Glowback runs from its Microsoft Store package (MSIX), else None."""
    n = wt.UINT(0)
    if k32.GetCurrentPackageFamilyName(byref(n), None) != 122:  # ERROR_INSUFFICIENT_BUFFER: there is a package
        return None  # APPMODEL_ERROR_NO_PACKAGE: GlowbackSetup.exe, portable, pip or the .py file
    name = ctypes.create_unicode_buffer(n.value)
    return name.value if k32.GetCurrentPackageFamilyName(byref(n), name) == 0 else None


PACKAGE = package_family()  # the Store version: the Store updates it, Windows starts it at sign-in (StartupTask)
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
LOG_DIR = (os.path.join(LOCAL_APPDATA, "Packages", PACKAGE, "LocalState") if PACKAGE  # removed with the Store app
           else os.path.join(LOCAL_APPDATA, "Glowback"))
LOG_PATH = os.path.join(LOG_DIR, "glowback.log")
LOG_PREVIOUS = os.path.join(LOG_DIR, "glowback.previous.log")


def log(msg):
    line = time.strftime("%H:%M:%S  ") + msg
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _log_unraisable(u):
    """An error in a Windows callback (window procedure, timer...) is "unraisable": without a console it would
    vanish, and the window it belongs to silently stop working."""
    log(f"Error: {u.exc_value!r} in {getattr(u.object, '__qualname__', u.object)!r}")
    if sys.stderr is not None:
        sys.__unraisablehook__(u)


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

    def thumbnail(self):
        """The last capture, 320 pixels wide, for the app's preview: (width, height, BGRA rows top-down)."""
        return self.sw, self.sh, ctypes.string_at(self.s1[3], self.sw * self.sh * 4)

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
        self.thumb_tex, self.thumb_size = VP(), None
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

    def thumbnail(self):
        """The last frame, about 400 pixels wide (a level of the GPU's mip chain), for the app's preview:
        (width, height, BGRA rows top-down), or None before the first frame."""
        if not self.mip.value:
            return None
        target = 200 if self.hdr else 400  # HDR pixels are converted one by one here: fewer of them
        lv = min(range(self.level + 1), key=lambda k: abs((self.w >> k) - target))
        tw, th = max(1, self.w >> lv), max(1, self.h >> lv)
        if self.thumb_size != (tw, th, self.fmt):
            _release(self.thumb_tex)
            sd = D3D11_TEXTURE2D_DESC(tw, th, 1, 1, self.fmt, 1, 0, 3, 0, 0x20000, 0)  # staging, CPU read
            _hr(_call(self.device, 5, [ctypes.POINTER(D3D11_TEXTURE2D_DESC), VP, PVP], byref(sd), None,
                      byref(self.thumb_tex)), "CreateTexture2D")
            self.thumb_size = (tw, th, self.fmt)
        _call(self.ctx, 46, [VP, wt.UINT, wt.UINT, wt.UINT, wt.UINT, VP, wt.UINT, VP], self.thumb_tex, 0, 0, 0, 0,
              self.mip, lv, None, restype=None)  # CopySubresourceRegion
        m = D3D11_MAPPED_SUBRESOURCE()
        _hr(_call(self.ctx, 14, [VP, wt.UINT, wt.UINT, wt.UINT, ctypes.POINTER(D3D11_MAPPED_SUBRESOURCE)],
                  self.thumb_tex, 0, 1, 0, byref(m)), "Map")
        try:
            row = tw * (8 if self.hdr else 4)
            raw = b"".join(ctypes.string_at(m.pData + y * m.RowPitch, row) for y in range(th))
        finally:
            _call(self.ctx, 15, [VP, wt.UINT], self.thumb_tex, 0, restype=None)  # Unmap
        if self.hdr:
            vals = struct.unpack(f"<{tw * th * 4}e", raw)
            s, lut, out = 4095.0 / self.hdr_white, SRGB_LUT, bytearray(tw * th * 4)
            for dst, src in ((0, 2), (1, 1), (2, 0)):  # BGRA from RGBA
                out[dst::4] = bytes(lut[min(4095, int(v * s))] if v > 0.0 else 0 for v in vals[src::4])
            raw = bytes(out)
        elif not self.bgr:  # RGBA -> BGRA, as GDI+ wants it
            out = bytearray(raw)
            out[0::4], out[2::4] = raw[2::4], raw[0::4]
            raw = bytes(out)
        return tw, th, raw

    def close(self):
        for p in (self.thumb_tex, self.staging, self.srv, self.mip, self.dup, self.output1, self.output, self.adapter,
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
# Looks: what the LEDs show. The screen (each LED its own zone, or one average color), one color, a gradient
# (still or flowing), or the music the PC plays. Profiles (night, apps) can switch to another look.
# =============================================================================
MODES = ("zones", "average", "color", "gradient", "music")
SCREEN_MODES = ("zones", "average")
LOOK_MODES = MODES + ("device", "off")  # device: the LEDs' own effect; off: the LEDs stay dark
MUSIC_STYLES = ("pulse", "spectrum", "wave")
MUSIC_PALETTES = ("rainbow", "screen", "color", "gradient")
SWATCHES = (("red", 0xFF3030), ("orange", 0xFF8000), ("yellow", 0xFFD60A), ("green", 0x28FF6E), ("cyan", 0x00E6FF),
            ("blue", 0x2864FF), ("purple", 0x8B6CFF), ("pink", 0xFF3CBE), ("warm", 0xFFAA5A), ("white", 0xFFFFFF))
GRADIENTS = (("sunset", (0xFF326E, 0xFF9628, 0xFFDC3C)), ("ocean", (0x00DCFF, 0x2846FF)),
             ("aurora", (0x28FF96, 0x00AAFF, 0x8C64FF)), ("neon", (0xFF28D2, 0x643CFF)),
             ("ember", (0xFF2800, 0xFF9600)), ("forest", (0xA0FF50, 0x00FF96)))
DEFAULT_COLOR, DEFAULT_GRADIENT = 0x8B6CFF, GRADIENTS[0][1]


def hex_color(value, default=None):
    """'#FF8800', 'ff8800', 'f80' or 0xFF8800 -> 0xFF8800; anything else -> default."""
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFFFF:
        return value
    if isinstance(value, str):
        v = value.strip().lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        if len(v) == 6:
            try:
                return int(v, 16)
            except ValueError:
                pass
    return default


def color_hex(c):
    return f"#{c:06X}"


def rgb(c):
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def hsv_color(h, s, v=1.0):
    """Hue 0..360, saturation and value 0..1 -> 0xRRGGBB."""
    r, g, b = colorsys.hsv_to_rgb((h % 360.0) / 360.0, min(1.0, max(0.0, s)), min(1.0, max(0.0, v)))
    return (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)


def color_hsv(c):
    h, s, v = colorsys.rgb_to_hsv(*(x / 255.0 for x in rgb(c)))
    return h * 360.0, s, v


def clean_stops(stops):
    """A gradient: 2 to 4 colors (a list, or "#ff0080,#7928ca"), as a tuple of 0xRRGGBB; else None."""
    if isinstance(stops, str):
        stops = stops.split(",")
    if not isinstance(stops, (list, tuple)):
        return None
    out = [c for c in map(hex_color, stops) if c is not None][:4]
    return tuple(out) if len(out) >= 2 else None


def gradient_at(stops, t):
    """Color (0..255 floats) at t (0..1) along evenly spaced stops, mixed in linear light: no muddy middle."""
    n = len(stops) - 1
    t = min(1.0, max(0.0, t)) * n
    i = min(int(t), n - 1)
    f = t - i
    return tuple(math.sqrt(a * a * (1 - f) + b * b * f) for a, b in zip(rgb(stops[i]), rgb(stops[i + 1])))


def gradient_colors(uv, stops, flow, now):
    """A gradient from the left of the screen to its right. Flowing, it slides sideways slowly and comes round."""
    if not flow:
        return [gradient_at(stops, u) for u, v in uv]
    loop, phase = tuple(stops) + (stops[0],), (now / 24.0) % 1.0
    return [gradient_at(loop, (u * 0.5 + phase) % 1.0) for u, v in uv]


def clean_look(look):
    """A profile's look: {"mode": one of LOOK_MODES, maybe "color", "gradient" or "style"}; what it leaves out
    comes from the Ambient light page (its color, gradient, music). None: auto, the Ambient light page as it is."""
    if not isinstance(look, dict) or look.get("mode") not in LOOK_MODES:
        return None
    out = {"mode": look["mode"]}
    if out["mode"] == "color" and hex_color(look.get("color")) is not None:
        out["color"] = color_hex(hex_color(look["color"]))
    elif out["mode"] == "gradient" and clean_stops(look.get("gradient")):
        out["gradient"] = [color_hex(c) for c in clean_stops(look["gradient"])]
    elif out["mode"] == "music" and look.get("style") in MUSIC_STYLES:
        out["style"] = look["style"]
    return out


def hhmm(minutes):
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _minutes(text, default):
    """'22:30' -> 1350 (minutes after midnight); 1350 stays 1350."""
    if isinstance(text, int) and not isinstance(text, bool):
        return text if 0 <= text < 1440 else default
    try:
        h, m = (int(x) for x in str(text).split(":"))
    except ValueError:
        return default
    return h * 60 + m if 0 <= h < 24 and 0 <= m < 60 else default


def clean_night(night):
    """The night profile: {"on", "from", "to" (minutes after midnight), "brightness" (0-100), "look" (None: same)}."""
    n = night if isinstance(night, dict) else {}
    try:
        bright = max(0, min(100, int(n.get("brightness", 40))))
    except (TypeError, ValueError):
        bright = 40
    return {"on": bool(n.get("on", False)), "from": _minutes(n.get("from"), 22 * 60),
            "to": _minutes(n.get("to"), 7 * 60), "brightness": bright, "look": clean_look(n.get("look"))}


def night_json(night):
    return {"on": night["on"], "from": hhmm(night["from"]), "to": hhmm(night["to"]),
            "brightness": night["brightness"], "look": night["look"]}


def night_now(night, now=None):
    """Is it night by the night profile's hours? (22:00 to 07:00 runs over midnight.)"""
    if not night["on"] or night["from"] == night["to"]:
        return False
    t = time.localtime(now)
    m, a, b = t.tm_hour * 60 + t.tm_min, night["from"], night["to"]
    return a <= m < b if a < b else (m >= a or m < b)


# =============================================================================
# Sound: the Music look follows what the PC plays (WASAPI loopback of the default output), analysed in memory
# and never recorded; the "plays sound" condition reads the apps' peak meters.
# =============================================================================
ole32 = ctypes.WinDLL("ole32")
_sig(ole32.CoInitializeEx, ctypes.c_long, VP, wt.DWORD)
_sig(ole32.CoCreateInstance, ctypes.c_long, ctypes.POINTER(GUID), VP, wt.DWORD, ctypes.POINTER(GUID), PVP)
_sig(ole32.CoTaskMemFree, None, VP)
CLSID_MMDeviceEnumerator = _iid("bcde0395-e52f-467c-8e3d-c4579291692e")
IID_IMMDeviceEnumerator = _iid("a95664d2-9614-4f35-a746-de8db63617e6")
IID_IAudioClient = _iid("1cb9ad4c-dbfa-4c32-b178-c2f568a703b2")
IID_IAudioCaptureClient = _iid("c8adbd64-e71e-48a0-a4de-185c395cd317")
IID_IAudioSessionManager2 = _iid("77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f")
IID_IAudioSessionControl2 = _iid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d")
IID_IAudioMeterInformation = _iid("c02216f6-8c67-4b5b-9d00-d008e73e0064")


def com_init():
    """COM in this thread (the capture loop), for the sound APIs."""
    ole32.CoInitializeEx(None, 0)  # multithreaded; already set up another way: fine too


def _method(ptr, index, *argtypes):
    """COM method #index of `ptr`, made once for calls many times a second."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, VP, *argtypes)(vtbl[index])


def default_output():
    """The default sound output (an IMMDevice, to release) and its ID."""
    enum, dev, sid = VP(), VP(), VP()
    _hr(ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, 23, byref(IID_IMMDeviceEnumerator),
                               byref(enum)), "MMDeviceEnumerator")
    try:
        _hr(_call(enum, 4, [ctypes.c_int, ctypes.c_int, PVP], 0, 0, byref(dev)), "GetDefaultAudioEndpoint")
    finally:
        _release(enum)
    ident = ""
    if _call(dev, 5, [PVP], byref(sid)) >= 0 and sid.value:  # GetId
        ident = ctypes.wstring_at(sid.value)
        ole32.CoTaskMemFree(sid)
    return dev, ident


def _activate(dev, iid):
    out = VP()
    _hr(_call(dev, 3, [ctypes.POINTER(GUID), wt.DWORD, VP, PVP], byref(iid), 23, None, byref(out)), "Activate")
    return out


class SoundCapture:
    """What the default output plays, as mono samples at about 24 kHz. Loopback: no microphone, nothing saved."""

    def __init__(self):
        self.client, self.capture, self.dev, self.ident = VP(), VP(), VP(), ""
        try:
            self.dev, self.ident = default_output()
            self.client = _activate(self.dev, IID_IAudioClient)
            fmt = VP()
            _hr(_call(self.client, 8, [PVP], byref(fmt)), "GetMixFormat")
            try:
                tag, self.channels, rate, _, self.align, bits, extra = struct.unpack(
                    "<HHIIHHH", ctypes.string_at(fmt.value, 18))
                if tag == 0xFFFE and extra >= 22:  # WAVEFORMATEXTENSIBLE: its sub-format's first number
                    tag = struct.unpack("<I", ctypes.string_at(fmt.value + 24, 4))[0]
                self.code = {(3, 32): "f", (1, 16): "h", (1, 32): "i"}.get((tag, bits))
                if not self.code or not self.channels:
                    raise OSError(f"sound format {tag}/{bits} bits not supported")
                _hr(_call(self.client, 3, [ctypes.c_int, wt.DWORD, ctypes.c_longlong, ctypes.c_longlong, VP, VP],
                          0, 0x00020000, 5_000_000, 0, fmt, None), "Initialize")  # shared, LOOPBACK, 0.5 s
            finally:
                ole32.CoTaskMemFree(fmt)
            _hr(_call(self.client, 14, [ctypes.POINTER(GUID), PVP], byref(IID_IAudioCaptureClient),
                      byref(self.capture)), "GetService")
            self.dec = max(1, round(rate / 24000))
            self.rate = rate / self.dec
            self.scale = {"f": 1.0, "h": 1 / 32768, "i": 1 / 2147483648}[self.code] / (self.dec * self.channels)
            self._next = _method(self.capture, 5, ctypes.POINTER(wt.UINT))
            self._get = _method(self.capture, 3, PVP, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.DWORD), VP, VP)
            self._done = _method(self.capture, 4, wt.UINT)
            _hr(_call(self.client, 10, []), "Start")
        except Exception:
            self.close()
            raise

    def read(self):
        """The samples played since the last call: mono, -1..1."""
        out, n, data, frames, flags = [], wt.UINT(), VP(), wt.UINT(), wt.DWORD()
        step, k = self.dec * self.channels, self.scale
        for _ in range(64):
            _hr(self._next(self.capture, byref(n)), "GetNextPacketSize")
            if not n.value:
                break
            _hr(self._get(self.capture, byref(data), byref(frames), byref(flags), None, None), "GetBuffer")
            count = frames.value
            try:
                if flags.value & 0x2 or not data.value:  # AUDCLNT_BUFFERFLAGS_SILENT
                    out.extend([0.0] * (count // self.dec))
                elif count:
                    a = array(self.code)
                    a.frombytes(ctypes.string_at(data.value, count * self.align))
                    out.extend(sum(a[i:i + step]) * k for i in range(0, len(a) - step + 1, step))
            finally:
                self._done(self.capture, count)
        return out

    def close(self):
        if self.client.value:
            try:
                _call(self.client, 11, [])  # Stop
            except OSError:
                pass
        for p in (self.capture, self.client, self.dev):
            _release(p)


def _fft(x, tw):
    """Radix-2 FFT of a list whose length is a power of 2, with the twiddles tw[size]: plain Python."""
    n = len(x)
    if n == 2:
        return [x[0] + x[1], x[0] - x[1]]
    even, odd = _fft(x[0::2], tw), _fft(x[1::2], tw)
    t = [w * o for w, o in zip(tw[n], odd)]
    return [e + o for e, o in zip(even, t)] + [e - o for e, o in zip(even, t)]


class MusicAnalyser:
    """Loudness, beats and 14 frequency bands (0..1, bass first) of the sound, with an automatic gain."""
    N = 512
    EDGES = (40, 80, 120, 180, 260, 380, 550, 800, 1150, 1700, 2500, 3700, 5500, 8000, 12000)  # Hz

    def __init__(self, rate):
        n = self.N
        self.window = [(0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))) * 4.0 / n for i in range(n)]  # Hann
        self.tw, size = {}, n
        while size > 2:
            self.tw[size] = [cmath.exp(-2j * math.pi * k / size) for k in range(size // 2)]
            size //= 2
        bins = [max(1, min(n // 2, round(f * n / rate))) for f in self.EDGES]
        self.bands = [(a, max(a + 1, b)) for a, b in zip(bins, bins[1:])]
        self.rate, self.buf = rate, [0.0] * n
        self.level = [0.0] * len(self.bands)  # what the LEDs show, per band
        self.peak = [1e-3] * len(self.bands)  # recent loudest, per band: the automatic gain
        self.loud, self.loud_peak, self.pulse = 0.0, 1e-3, 0.0
        self.bass_avg, self.last_beat, self.beats = 0.0, -1.0, 0
        self.quiet, self.silent = 9.0, True
        self.waves = []  # (start, strength) of the light waves sent by the beats

    def update(self, samples, dt, sensitivity=50, now=None):
        now = time.monotonic() if now is None else now
        n = self.N
        if not samples:  # loopback gets nothing while nothing plays: that is silence
            samples = [0.0] * min(n, int(self.rate * dt))
        self.buf = (self.buf + samples)[-n:]
        spec = _fft([s * w for s, w in zip(self.buf, self.window)], self.tw)
        power = [c.real * c.real + c.imag * c.imag for c in spec[:n // 2 + 1]]
        amps = [math.sqrt(sum(power[a:b]) / (b - a)) for a, b in self.bands]
        rms = math.sqrt(sum(s * s for s in self.buf) / n)
        self.quiet = self.quiet + dt if rms < 3e-4 else 0.0
        self.silent = self.quiet > 1.5
        gain = 2.0 ** ((sensitivity - 50) / 25.0)
        fall = math.exp(-dt / 6.0)  # the gain follows the music's level within a few seconds
        attack, release = 1 - math.exp(-dt / 0.025), 1 - math.exp(-dt / 0.16)
        self.peak = [max(a, p * fall, 1e-6) for a, p in zip(amps, self.peak)]
        ref = max(self.peak)
        for i, a in enumerate(amps):
            v = min(1.0, (a / max(self.peak[i], ref * 0.15, 3e-3) * gain) ** 1.5)
            self.level[i] += (v - self.level[i]) * (attack if v > self.level[i] else release)
        self.loud_peak = max(rms, self.loud_peak * fall, 1e-6)
        v = min(1.0, (rms / max(self.loud_peak, 3e-3) * gain) ** 1.5)
        self.loud += (v - self.loud) * (attack if v > self.loud else release)
        bass, bass_peak = sum(amps[:3]) / 3, max(self.peak[:3])  # beats: the bass jumps above its recent level
        self.bass_avg += (bass - self.bass_avg) * (1 - math.exp(-dt / 0.45))
        if bass > self.bass_avg * 1.4 and bass > bass_peak * 0.35 and bass > 3e-3 and now - self.last_beat > 0.22:
            self.last_beat, self.pulse, self.beats = now, 1.0, self.beats + 1
            self.waves = self.waves[-5:] + [(now, min(1.0, 0.55 + 0.45 * bass / bass_peak))]
        else:
            self.pulse *= math.exp(-dt / 0.18)
        self.waves = [w for w in self.waves if now - w[0] < 1.2]


def music_geometry(uv):
    """Per LED, for the music: (f, ring). f: 0 = bass at the bottom middle, 1 = treble at the top middle (one row
    of LEDs: bass in the middle, treble at the ends); ring: where it sits around the screen, 0..1."""
    flat = not uv or max(v for u, v in uv) - min(v for u, v in uv) < 0.15
    geo = []
    for u, v in uv:
        dx, dy = u - 0.5, v - 0.5
        f = min(1.0, abs(dx) * 2) if flat else math.atan2(abs(dx), dy) / math.pi
        geo.append((f, (math.atan2(dy, dx) / (2 * math.pi) + 0.25) % 1.0))
    return geo


def rainbow_colors(geo, style, now):
    """The Music look's own colors: bass red to treble violet for the spectrum, else a rainbow turning slowly."""
    if style == "spectrum":
        return [tuple(255 * x for x in colorsys.hsv_to_rgb(f * 0.75, 1, 1)) for f, ring in geo]
    return [tuple(255 * x for x in colorsys.hsv_to_rgb((ring + now / 30.0) % 1.0, 1, 1)) for f, ring in geo]


def music_colors(geo, an, style, colors, brightness, now):
    """LED colors of the Music look: each LED's color (0..255 floats) lit by the sound, at `brightness` (0..1)."""
    lv, nb, out = an.level, len(an.level), []
    pulse = min(1.0, 0.08 + 0.5 * an.loud + 0.55 * an.pulse)
    for (f, ring), c in zip(geo, colors):
        if style == "spectrum":
            x = f * (nb - 1)
            j = min(int(x), nb - 2)
            k = lv[j] + (lv[j + 1] - lv[j]) * (x - j)
        elif style == "wave":  # beats send light from the bottom middle up both sides
            k = 0.05 + 0.25 * an.loud
            for t0, s in an.waves:
                age = now - t0
                d = f - age * 1.4
                k += s * math.exp(-d * d / 0.02) * (1 - age / 1.2)
        else:
            k = pulse
        k = min(1.0, k) * brightness
        out.append((c[0] * k, c[1] * k, c[2] * k))
    return out


class SoundApps:
    """Which apps play sound now: their sessions' peak meters on the default output (for "plays sound")."""

    def __init__(self):
        self.mgr, self.opened, self.heard = VP(), -99.0, {}  # heard: process ID -> last time it played sound

    def pids(self, hold=2.0):
        """Processes that played sound in the last `hold` seconds."""
        now = time.monotonic()
        try:
            if now - self.opened > 5:  # follow the default output (headphones plugged in...)
                self.opened = now
                dev, _ = default_output()
                try:
                    mgr = _activate(dev, IID_IAudioSessionManager2)
                finally:
                    _release(dev)
                _release(self.mgr)
                self.mgr = mgr
            en = VP()
            _hr(_call(self.mgr, 5, [PVP], byref(en)), "GetSessionEnumerator")
            try:
                count = ctypes.c_int()
                _call(en, 3, [ctypes.POINTER(ctypes.c_int)], byref(count))
                for i in range(count.value):
                    ctl = VP()
                    if _call(en, 4, [ctypes.c_int, PVP], i, byref(ctl)) < 0:
                        continue
                    try:
                        self._session(ctl, now)
                    except OSError:
                        pass
                    finally:
                        _release(ctl)
            finally:
                _release(en)
        except OSError:
            _release(self.mgr)
            self.opened = now - 4  # no output, or it went away: look again in a second
        self.heard = {pid: t for pid, t in self.heard.items() if now - t < hold}
        return set(self.heard)

    def _session(self, ctl, now):
        state, peak, pid = ctypes.c_int(), ctypes.c_float(), wt.DWORD()
        _call(ctl, 3, [ctypes.POINTER(ctypes.c_int)], byref(state))
        if state.value != 1:  # AudioSessionStateActive
            return
        meter = _qi(ctl, IID_IAudioMeterInformation)
        try:
            _call(meter, 3, [ctypes.POINTER(ctypes.c_float)], byref(peak))
        finally:
            _release(meter)
        if peak.value > 0.003:
            c2 = _qi(ctl, IID_IAudioSessionControl2)
            try:
                _call(c2, 14, [ctypes.POINTER(wt.DWORD)], byref(pid))
            finally:
                _release(c2)
            if pid.value:
                self.heard[pid.value] = now

    def close(self):
        _release(self.mgr)


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


def _other_quit(stop, tries=50):
    """Waits (tries x 0.1 s) for the running Glowback to quit and takes its single-instance slot; still taken
    (stop.already_running) if it did not quit."""
    for _ in range(tries):
        k32.CloseHandle(stop.h)
        time.sleep(0.1)
        stop = StopSignal()
        if not stop.already_running:
            break
    return stop


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
    def __init__(self, address, connect_timeout=2.0):
        host, _, port = address.partition(":")
        self.address = f"{host or '127.0.0.1'}:{port or 6742}"
        self.sock = socket.create_connection((host or "127.0.0.1", int(port or 6742)), timeout=connect_timeout)
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


_openrgb = {"client": None, "warned": False, "next_try": 0.0}


def open_openrgb_devices(args, known=(), include_all=False):
    if not args.openrgb or args.openrgb == "off":
        return [], []
    auto = args.openrgb == "auto"  # default: use OpenRGB if it runs on this PC, stay silent otherwise
    client = _openrgb["client"]
    if client is None and auto and time.monotonic() < _openrgb["next_try"]:
        return [], []  # not running a moment ago: don't slow the capture loop down, retry later
    try:
        if client is None:
            # a closed local port takes ~2 s to be refused on Windows: keep the probe short in auto mode
            client = _openrgb["client"] = OpenRGBClient("127.0.0.1:6742" if auto else args.openrgb,
                                                        connect_timeout=0.1 if auto else 2.0)
            log(f"OpenRGB SDK connected ({client.address}, protocol {client.version})")
            _openrgb["warned"] = False
        found = client.controllers()
    except OSError as e:
        if client:
            client.close()
        _openrgb["client"] = None
        _openrgb["next_try"] = time.monotonic() + 60
        if not _openrgb["warned"] and not auto:
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
        print(tr("no_device"))
        return
    all_wb = load_settings().get("white_balance", {})
    print(tr("cal_intro"))
    print(tr("cal_keys1"))
    print(tr("cal_keys2") + "\n")
    try:
        for d in devs:
            key = device_key(d)
            wb = list(all_wb.get(key, (1.0, 1.0, 1.0)))
            level = 1.0
            d.set_autonomous(False)
            print(f"{d.name}:")
            while not stop.wait(0):
                d.send([tuple(min(255, round(255 * level * c)) for c in wb)] * len(d.lamps))
                print("\r" + tr("cal_state", r=wb[0], g=wb[1], b=wb[2], level=level), end="", flush=True)
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
                    print("\n  " + tr("cal_saved"))
                    break
                elif ch == "\x1b":
                    print("\n  " + tr("cal_skipped"))
                    break
            d.set_autonomous(True)
    finally:
        for d in devs:
            d.close()
    print(tr("cal_restart"))


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
        self.uv = []  # lamp positions 0..1, for the app's live preview
        self.geo = None  # where each LED sits for the Music look


class State:
    """Live settings shared between the capture loop, the tray icon, the app and Home Assistant."""

    def __init__(self, args, enabled=True):
        saved = load_settings()
        self.enabled = enabled
        # switched off from a phone or Home Assistant: Glowback keeps the LEDs, dark (pausing hands them back to the
        # device's own effect instead). Kept across a restart at sign-in; started by hand, the light comes back.
        self.dark = bool(saved.get("dark")) and bool(getattr(args, "from_autostart", False))
        self.mode = args.mode if args.mode in MODES else "zones"
        self.brightness = max(0.0, min(100.0, float(args.brightness)))
        self.color = hex_color(getattr(args, "color", None), hex_color(saved.get("color"), DEFAULT_COLOR))
        self.gradient = (clean_stops(getattr(args, "gradient", None)) or clean_stops(saved.get("gradient"))
                         or DEFAULT_GRADIENT)
        self.flow = bool(saved.get("flow", True))
        music = saved.get("music") if isinstance(saved.get("music"), dict) else {}
        self.music_style = music.get("style") if music.get("style") in MUSIC_STYLES else "pulse"
        self.music_palette = music.get("palette") if music.get("palette") in MUSIC_PALETTES else "rainbow"
        try:
            self.sensitivity = max(0, min(100, int(music.get("sensitivity", 50))))
        except (TypeError, ValueError):
            self.sensitivity = 50
        self.check_updates = bool(saved.get("check_updates", True))
        self.leds = 0              # LEDs currently driven (shown in the tray menu)
        self.new_version = None    # newer version found on GitHub (not `update`: that is the method below)
        self.version = 0
        self.rules = clean_rules(saved.get("sync_when"))  # apps' profiles: a condition, maybe a look
        self.otherwise = saved.get("otherwise")  # when no app's condition holds: auto, device or off
        if self.otherwise not in ("auto", "device", "off"):  # 0.5.0: conditions meant "follow the screen only then"
            self.otherwise = "device" if self.rules else "auto"
            save_settings({"otherwise": self.otherwise})
        self.night = clean_night(saved.get("night"))
        self.screens = []          # names of the screens the LEDs follow
        self.preview = []          # [(lamp positions 0..1, colors)] per device, for the app's live preview
        self.thumb, self.thumb_want = None, -99.0  # the LED screen's picture, while the app asks for it
        self.sound = None          # Music look: "on" (something plays), "silent", or None (not listening)
        self.identify_until = 0.0  # a phone's app asked the light to show itself (Matter "Identify") until then
        self.notify = lambda: None  # the tray: something shown in the app or the panel changed
        self.rule_hit = None
        self.active = self.resolve(None)
        self.waiting = self.active["look"]["mode"] == "device"  # a profile hands the LEDs to their own effect

    def update(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.version += 1
        saved = {"enabled": self.enabled, "dark": self.dark, "mode": self.mode, "brightness": self.brightness,
                 "color": color_hex(self.color), "gradient": [color_hex(c) for c in self.gradient], "flow": self.flow,
                 "music": {"style": self.music_style, "palette": self.music_palette, "sensitivity": self.sensitivity}}
        if "check_updates" in kw:  # only when switched here: the installer and --check-updates also set it
            saved["check_updates"] = self.check_updates
        save_settings(saved)
        self._activate(self.rule_hit)
        self.notify()

    def lit(self):
        """The ambient light shows (neither paused nor switched off)."""
        return self.enabled and not self.dark

    def switch(self):
        """The app's and the panel's on/off switch: pause (the LEDs go back to the device), or light up again."""
        if self.lit():
            self.update(enabled=False)
        else:
            self.update(enabled=True, dark=False)

    # ---- profiles: the night, the apps, and what to show the rest of the time
    def base_look(self):
        return {"mode": self.mode, "color": self.color, "gradient": self.gradient, "flow": self.flow,
                "style": self.music_style, "palette": self.music_palette}

    def full_look(self, look):
        """A profile's look, completed with the Ambient light page's colors and music."""
        out = self.base_look()
        if look:
            out["mode"] = look["mode"]
            if "color" in look:
                out["color"] = hex_color(look["color"], self.color)
            if "gradient" in look:
                out["gradient"] = clean_stops(look["gradient"]) or self.gradient
            if "style" in look:
                out["style"] = look["style"]
        return out

    def resolve(self, hit, night=None):
        """What the LEDs show now: {"source": base, night, app or rest, "rule", "night", "look", "brightness"}."""
        night = night_now(self.night) if night is None else night
        look, bright, source = None, self.brightness, "base"
        if night:
            look, bright, source = self.night["look"], self.night["brightness"], "night"
        if hit is not None:
            source = "app"
            if hit.get("look"):
                look = hit["look"]
        elif self.rules and self.otherwise != "auto":
            look, source = {"mode": self.otherwise}, "rest"
        if getattr(self, "dark", False):  # switched off from a phone or Home Assistant: over any profile
            look = {"mode": "off"}
        return {"source": source, "rule": hit, "night": night, "look": self.full_look(look), "brightness": bright}

    def _activate(self, rule):
        active = self.resolve(rule)
        changed = active != self.active or rule != self.rule_hit
        self.active, self.rule_hit = active, rule
        self.waiting = active["look"]["mode"] == "device"
        return changed

    def _same_hit(self):
        """The rule that held, as it is now in the list (its look may have changed), or None."""
        h = self.rule_hit
        if h is None:
            return None
        return next((r for r in self.rules if (r["app"], r["when"], r["screen"]) == (h["app"], h["when"], h["screen"])),
                    None)

    def set_rules(self, rules, save=True):
        """New apps' profiles (the app, or glowback --sync-when through settings.json)."""
        rules = clean_rules(rules)
        if save:
            save_settings({"sync_when": rules})
        if rules != self.rules:
            self.rules = rules
            self._activate(self._same_hit())
            self.notify()

    def set_profiles(self, night=None, otherwise=None, save=True):
        """The night profile, or what to show when no app's condition holds."""
        if night is not None:
            self.night = clean_night(night)
        if otherwise in ("auto", "device", "off"):
            self.otherwise = otherwise
        if save:
            save_settings({"night": night_json(self.night), "otherwise": self.otherwise})
        self._activate(self.rule_hit)
        self.notify()

    def set_match(self, rule):
        """What the capture loop found: the app's condition that holds now, or None. Also follows the clock."""
        if self._activate(rule):
            self.notify()

    def status(self):
        """(text, dot): dot is "on", "off" (paused) or "none" (the LEDs' own effect, dark, no device)."""
        mode = self.active["look"]["mode"]
        if not self.enabled:
            return tr("state_paused"), "off"
        if mode == "device":
            return tr("state_device"), "none"
        if mode == "off":
            return tr("state_dark"), "none"
        if self.leds:
            return tr("state_on", leds=self.leds), "on"
        return tr("state_none"), "none"


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


def screen_targets(o, frame, args, shape, mode, t0):
    """LED colors from the screen: each LED its zone, or one average color (a list of one)."""
    (R, G, B), gw, gh = frame
    m = o.monitor
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
    if mode == "average":
        return [shape(*avg)]
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
    return targets


def describe(active):
    """What the LEDs show and why, for the log."""
    r, look = active["rule"], active["look"]["mode"]
    why = {"app": f"{(r or {}).get('app') or 'any app'} {(r or {}).get('when', '')}", "night": "night profile",
           "rest": "no app's condition holds", "base": "Ambient light settings"}[active["source"]]
    return f"{why}: {look}"


def run(args, stop, state=None):
    state = state or State(args)
    com_init()
    outputs, grabbers, dxgi_failed = {}, {}, set()
    period = 1.0 / max(1.0, args.fps)
    next_scan = next_keep = 0.0
    monitors = []
    frames, t_stat = 0, time.perf_counter()
    t_prev = time.perf_counter()
    warned, held, seen, shapes = False, None, -1, {}
    watch, sound_apps, rule_t, file_t, file_mtime = AppWatch(), SoundApps(), 0.0, 0.0, None
    rule_monitors, rule_monitors_t = [], -99.0
    led_screens = load_settings().get("led_screens") or []  # the screens the LEDs followed last time
    music, music_t, music_retry, music_err = None, 0.0, 0.0, None  # listening while a Music look shows
    last_look, fade_until, thumb_t = None, 0.0, 0.0

    def shaper(b):
        if b not in shapes:
            if len(shapes) > 8:
                shapes.clear()
            shapes[b] = make_shaper(args.saturation, args.gamma, b, args.boost)
        return shapes[b]

    def grabber(m):
        g = grabbers.get(m.rect)
        if g is None:
            g = grabbers[m.rect] = make_grabber(m, args, dxgi_failed)
            log(f"  capture: {g.kind}, {g.gw}x{g.gh} grid")
        return g

    def take_thumb(m=None):
        """The LED screen's picture for the app's preview (it asks while it shows it)."""
        nonlocal rule_monitors, rule_monitors_t
        if m is None:
            m = next((o.monitor for o in outputs.values() if o.monitor), None)
        if m is None:
            if not monitors and time.perf_counter() - rule_monitors_t > 5:
                rule_monitors, rule_monitors_t = list_monitors(), time.perf_counter()
            ms = monitors or rule_monitors
            m = (next((x for x in ms if (x.name or x.device) in led_screens), None)
                 or next((x for x in ms if x.primary), None))
        if m is None:
            return
        try:
            g = grabber(m)
            g.grab()
            state.thumb = g.thumbnail()
        except OSError as e:
            log(f"  capture restarted ({e})")
            grabbers.pop(m.rect).close()

    try:
        while True:
            t0 = time.perf_counter()
            dt, t_prev = t0 - t_prev, t0
            if state.version != seen:
                seen = state.version
                for o in outputs.values():
                    o.last = None

            # ---- profiles changed from the command line (glowback --sync-when): they land in settings.json
            if t0 >= file_t:
                file_t = t0 + 2
                try:
                    mtime = os.stat(SETTINGS_PATH).st_mtime
                except OSError:
                    mtime = None
                if mtime != file_mtime:
                    file_mtime = mtime
                    saved = load_settings()
                    state.set_rules(saved.get("sync_when"), save=False)
                    if saved.get("otherwise") != state.otherwise or clean_night(saved.get("night")) != state.night:
                        if "night" in saved or "otherwise" in saved:
                            state.set_profiles(clean_night(saved.get("night")), saved.get("otherwise"), save=False)

            # ---- profiles, 4 times a second: the night's hours, the apps' conditions, and what to show then
            if t0 >= rule_t:
                rule_t = t0 + 0.25
                hit = None
                if state.enabled and state.rules:
                    if t0 - rule_monitors_t > 5:
                        rule_monitors, rule_monitors_t = list_monitors(), t0
                    leds = {o.monitor.device for o in outputs.values() if o.monitor}
                    if not leds:  # not connected yet: the screens the LEDs followed last time, else the primary one
                        leds = {m.device for m in rule_monitors if (m.name or m.device) in led_screens}
                        leds = leds or {m.device for m in rule_monitors if m.primary}
                    hit = conditions_met(state.rules, leds, rule_monitors, watch, sound_apps)
                state.set_match(hit)
            act = state.active
            look = act["look"]
            mode = look["mode"]
            want_thumb = time.monotonic() - state.thumb_want < 1.5
            thumb_due = want_thumb and t0 >= thumb_t
            if thumb_due:
                thumb_t = t0 + 0.08  # about 12 pictures a second for the preview

            # ---- paused, or a profile hands the LEDs back to the device's own effect
            hold = "paused" if not state.enabled else "device" if mode == "device" else None
            if hold:
                if held != hold:
                    held = hold
                    for o in outputs.values():
                        try:
                            o.dev.set_autonomous(True)
                        except OSError:
                            pass
                    state.preview = []
                    log("Paused: LEDs handed back to the device." if hold == "paused" else
                        f"{describe(act)}: LEDs handed back to the device.")
                if thumb_due:
                    take_thumb()
                if stop.wait(0.08 if want_thumb else 0.25):
                    break
                continue
            if held:
                held = None
                next_keep = 0.0
                for o in outputs.values():
                    o.smooth = o.last = None
                log(f"Resumed: {describe(act)}.")

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
                    o.uv = lamp_uv(dev.lamps, args.mirror, args.flip) if dev.lamps else []
                    period = max(period, dev.min_interval)
                    state.leds = sum(len(x.dev.lamps) for x in outputs.values())
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
                    names = sorted({o.monitor.name or o.monitor.device for o in outputs.values() if o.monitor})
                    state.screens = names
                    if names and names != led_screens:  # remembered for the "LED screen" condition at next start
                        led_screens = names
                        save_settings({"led_screens": names})
                elif args.capture == "auto":
                    for rect, g in list(grabbers.items()):  # retry DXGI (e.g. it failed on the lock screen)
                        if g.kind == "GDI":
                            grabbers.pop(rect).close()
                if not outputs and not warned:
                    log("Waiting for a Dynamic Lighting (HID LampArray) device... (glowback --list to check)")
                    warned = True

            # ---- the Music look listens to what the PC plays; 10 seconds after it, Glowback stops listening
            an = None
            if mode == "music":
                music_t = t0
                if music is None and t0 >= music_retry:
                    try:
                        music = SoundCapture()
                        music.an, music.checked = MusicAnalyser(music.rate), t0
                        log(f"Music: listening to what the PC plays ({music.rate * music.dec:g} Hz)")
                    except OSError as e:
                        music, music_retry = None, t0 + 5
                        if str(e) != music_err:  # said once, not every 5 seconds
                            music_err = str(e)
                            log(f"Music: cannot listen to the sound ({e})")
                if music is not None:
                    try:
                        samples = music.read()
                        if t0 - music.checked > 3:  # the default output changed (headphones...): follow it
                            music.checked = t0
                            dev, ident = default_output()
                            _release(dev)
                            if ident != music.ident:
                                raise OSError("the default output changed")
                        music.an.update(samples, dt, state.sensitivity)
                        an = music.an
                    except OSError as e:
                        log(f"Music: listening again ({e})")
                        music.close()
                        music, music_retry = None, t0 + 1
                sound = "on" if an is not None and not an.silent else "silent"
                if sound != state.sound:
                    state.sound = sound
                    state.notify()
            elif music is not None and t0 - music_t > 10:
                music.close()
                music, state.sound = None, None

            # ---- one frame
            if look != last_look:  # another look (a profile, the app...): fade into it
                fade_until = t0 + 0.8 if last_look is not None and last_look["mode"] != look["mode"] else fade_until
                last_look = look
            b = act["brightness"] / 100.0
            need_screen = mode in SCREEN_MODES or (mode == "music" and look["palette"] == "screen")
            keep = t0 >= next_keep
            if keep:
                next_keep = t0 + 5
            frames_by_rect = {}
            for path, o in list(outputs.items()):
                m = o.monitor
                if m is None:
                    continue
                frame = None
                if need_screen or thumb_due:
                    if m.rect not in frames_by_rect:
                        g = grabber(m)
                        try:
                            px = g.grab()
                            if thumb_due:
                                state.thumb, thumb_due = g.thumbnail(), False
                        except OSError as e:
                            log(f"  capture restarted ({e})")
                            grabbers.pop(m.rect).close()
                            px = None
                        frames_by_rect[m.rect] = (px, g.gw, g.gh) if px else None
                    frame = frames_by_rect[m.rect]
                n = len(o.dev.lamps)
                if mode in SCREEN_MODES:
                    if frame is None:
                        continue
                    targets = screen_targets(o, frame, args, shaper(b), mode, t0)
                elif mode == "color":
                    targets = [tuple(c * b for c in rgb(look["color"]))]
                elif mode == "gradient":
                    targets = [(r * b, g_ * b, bb * b) for r, g_, bb in gradient_colors(o.uv, look["gradient"],
                                                                                      look["flow"], t0)]
                elif mode == "music":
                    if o.geo is None or len(o.geo) != len(o.uv):
                        o.geo = music_geometry(o.uv)
                    pal = look["palette"]
                    if pal == "screen":
                        colors = screen_targets(o, frame, args, shaper(1.0), "zones", t0) if frame else None
                    elif pal == "color":
                        colors = [rgb(look["color"])] * n
                    elif pal == "gradient":
                        colors = gradient_colors(o.uv, look["gradient"], look["flow"], t0)
                    else:
                        colors = rainbow_colors(o.geo, look["style"], t0)
                    if an is None or not colors:
                        targets = [(0.0, 0.0, 0.0)] * n
                    else:
                        targets = music_colors(o.geo, an, look["style"], colors, b, t0)
                else:  # off: the LEDs stay dark
                    targets = [(0.0, 0.0, 0.0)]
                now = time.monotonic()
                if state.identify_until > now:  # "Identify" from a phone's app: white blinks, twice a second
                    v = 255.0 if now % 0.5 < 0.25 else 0.0
                    targets = [(v, v, v)]

                tau = args.smoothing
                if state.identify_until > now:
                    tau = 0.0  # crisp blinks
                elif t0 < fade_until:
                    tau = max(tau, 0.3)
                elif mode == "music":
                    tau = min(tau, 0.03)
                a = 1.0 - math.exp(-dt / tau) if tau > 0 else 1.0
                if o.smooth is None or len(o.smooth) != len(targets):
                    if o.smooth and len(targets) == 1:  # many colors -> one: fade from their average
                        o.smooth = [[sum(s[i] for s in o.smooth) / len(o.smooth) for i in range(3)]]
                    elif o.smooth and len(o.smooth) == 1:  # one color -> many: fade from it
                        o.smooth = [list(o.smooth[0]) for _ in targets]
                    else:
                        o.smooth = [list(t) for t in targets]
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
                    state.leds = sum(len(x.dev.lamps) for x in outputs.values())
                    next_scan = min(next_scan, t0 + 2)
            if thumb_due:  # no LED device on a screen: still show the screen's picture
                take_thumb()

            # the app's live preview: each LED's color (one color for all is spread to every LED)
            state.preview = [(o.uv, o.last if len(o.last) == len(o.uv) else o.last[:1] * len(o.uv))
                             for o in outputs.values() if o.last and o.uv]
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
        if music is not None:
            music.close()
        sound_apps.close()
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
    if args.openrgb and args.openrgb != "off":
        print(f"\nOpenRGB devices ({'auto-detect' if args.openrgb == 'auto' else args.openrgb}):")
        devs, skipped = open_openrgb_devices(args, include_all=True)
        if not devs and not skipped:
            print("  none (to use OpenRGB devices, start OpenRGB and its SDK server)")
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
        print(tr("no_device"))
        return
    print(tr("test_intro"))
    try:
        for d in devs:
            d.uv = lamp_uv(d.lamps, args.mirror, args.flip)
            d.set_autonomous(False)
        steps = [
            (tr("test_white"), lambda u, v: (255, 255, 255)),
            (tr("test_lr"),
             lambda u, v: (255, 0, 0) if u < 0.5 else (0, 0, 255)),
            (tr("test_tb"),
             lambda u, v: (0, 255, 0) if v < 0.5 else (255, 180, 0)),
        ]
        for label, fn in steps:
            print(f"  {label}")
            for d in devs:
                d.send([fn(u, v) for u, v in d.uv])
            if stop.wait(5):
                return
        print("  " + tr("test_rainbow"))
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
        print(tr("test_done"))


# =============================================================================
# Languages: the UI follows the Windows display language (or --lang)
# =============================================================================
STRINGS = {
    'en': {
        'update_downloading': 'Downloading Glowback {version}…',
        'update_installing': 'Installing the update. Glowback will restart by itself.',
        'update_failed': 'The update could not be installed ({error}). Opening the download page.',
        'ambilight': 'Ambient light',
        'start_windows': 'Start with Windows',
        'mode': 'Mode',
        'zones': 'Each LED follows its zone',
        'average': 'One average color',
        'brightness': 'Brightness',
        'made_by': 'Made by {author}',
        'star': 'Star on GitHub',
        'open_log': 'Open log',
        'quit': 'Quit',
        'by': 'by {author}',
        'tip_on': 'Glowback: ambient light on',
        'tip_off': 'Glowback: paused',
        'balloon_title': 'Glowback is running',
        'balloon_text': 'Right-click this icon to pause it, change mode or brightness, or quit.',
        'already': 'Glowback is already running: look for its icon next to the clock.',
        'pausing': 'Pausing the running Glowback for a moment...',
        'restarted': 'Glowback restarted in the background.',
        'press_enter': 'Press Enter to close this window...',
        'test_intro': 'Look at the wall behind the screen:',
        'test_white': 'all LEDs WHITE',
        'test_lr': 'LEFT = RED, RIGHT = BLUE (seen from your seat; if reversed use --mirror)',
        'test_tb': 'TOP = GREEN, BOTTOM = YELLOW (if reversed use --flip)',
        'test_rainbow': 'rainbow sweep around the LEDs',
        'test_done': 'Done, LEDs handed back to the device.',
        'no_device': 'No Dynamic Lighting device found (glowback --list).',
        'cal_intro': 'White balance: adjust until the light on the wall looks neutral white.',
        'cal_keys1': '  r / R  less / more red     g / G  green     b / B  blue',
        'cal_keys2': '  1 2 3 4  test at 100 / 50 / 25 / 10 %     Enter  save     Esc  skip this device',
        'cal_state': '  red {r:.2f}   green {g:.2f}   blue {b:.2f}   (level {level:.0%})   ',
        'cal_saved': 'saved.',
        'cal_skipped': 'skipped.',
        'cal_restart': 'Restart Glowback (or it picks this up at its next start).',
        'state_on': 'Active · {leds} LEDs',
        'state_paused': 'Paused',
        'state_none': 'Looking for LEDs…',
        'about': 'About',
        'updates': 'Check for updates',
        'auto_check': 'Check automatically',
        'up_to_date': 'Up to date',
        'check_failed': 'Failed',
        'update_to': 'Update to {version}',
        'update_title': 'Glowback {version} is available',
        'update_text': 'Click here to download it.',
        'ha_setup': 'Set up',
        'ha_connected': 'Connected',
        'ha_connecting': 'Connecting…',
        'ha_error': 'Not connected',
        'ha_intro': 'Glowback appears in Home Assistant as a light you can switch from dashboards, automations and Google Assistant. It connects through MQTT: install the Mosquitto broker app in Home Assistant, then sign in here with a Home Assistant user.',
        'ha_guide': 'Step-by-step guide',
        'ha_address': 'Address',
        'ha_port': 'Port',
        'ha_user': 'User',
        'ha_password': 'Password',
        'ha_user_hint': 'Home Assistant user',
        'ha_password_saved': 'Saved',
        'ha_connect': 'Connect',
        'ha_cancel': 'Cancel',
        'ha_disconnect': 'Disconnect',
        'ha_testing': 'Connecting to Home Assistant…',
        'ha_need_address': 'Enter the address of Home Assistant.',
        'ha_err_address': 'This address was not found on your network.',
        'ha_err_broker': 'No MQTT broker answers at this address. Is the Mosquitto broker app started?',
        'ha_err_login': 'Wrong user or password.',
        'ha_err_refused': 'The MQTT broker refused the connection.',
        'ha_err_tls': 'The secure connection failed.',
        'ha_err_other': 'The connection failed ({error}).',
        'ha_done_title': 'Connected to Home Assistant',
        'ha_done_text': 'Glowback is in Settings › Devices & services › MQTT.',
        'open_app': 'Open Glowback',
        'nav_home': 'Home Assistant',
        'nav_light': 'Ambient light',
        'nav_settings': 'Settings',
        'nav_about': 'About',
        'app_quit': 'Quit Glowback',
        'app_background': 'Glowback keeps running in the background. Click its icon next to the clock to come back.',
        'mode_zones_desc': 'Each LED takes the colors of the picture right next to it.',
        'mode_average_desc': 'All the LEDs show the average color of the screen.',
        'sync_now_paused': 'The ambient light is paused.',
        'sync_app': 'App',
        'sync_when_label': 'When',
        'sync_screen': 'Screen',
        'sync_any_app': 'Any app',
        'sync_open_apps': 'Open apps',
        'sync_browse': 'Other program…',
        'sync_running': 'Is running',
        'sync_foreground': 'Is in front',
        'sync_fullscreen': 'Is full screen',
        'sync_any_screen': 'Any screen',
        'sync_led_screen': 'The LED screen',
        'sync_screen_n': 'Screen {n}',
        'sync_add': 'Add',
        'sync_remove': 'Remove',
        'sync_programs': 'Programs',
        'home_sub': 'Switch the ambient light from Home Assistant, its automations and your voice assistant.',
        'nav_matter': 'Apple & Google',
        'matter_apple_home': 'Apple Home',
        'matter_title': 'Apple Home, Google Home and Alexa',
        'matter_sub': 'Control the ambient light from your phone with Matter: Glowback shows up as a light in Apple Home, Google Home, Alexa or SmartThings, without Home Assistant.',
        'matter_toggle': 'Matter light',
        'matter_off_desc': "Off: phones don't see Glowback",
        'matter_failed': 'Could not start: see the log',
        'matter_on_count': 'On · paired apps: {n}',
        'matter_on_none': 'On · ready to pair',
        'matter_pair': 'Pair',
        'matter_scan_title': 'Scan with your phone',
        'matter_scan': 'In Apple Home, Google Home or Alexa, add an accessory or a Matter device, then scan this code. Or type it:',
        'matter_open_for': 'Pairing open for {min} min',
        'matter_stop': 'Stop',
        'matter_other_app': 'Another app is being added to Glowback: carry on in that app ({min} min left).',
        'matter_closed_desc': 'Open pairing for 15 minutes to add Glowback to Apple Home, Google Home, Alexa or another Matter app. Already paired? Add the next app the same way.',
        'matter_open': 'Pair a phone',
        'matter_paired': 'Paired apps',
        'matter_paired_desc': 'Can switch the light and change its brightness and color',
        'matter_none': 'No phone or app yet.',
        'matter_remove': 'Remove',
        'matter_remove_ask': 'Remove Glowback from {app}? That app will no longer control the light.',
        'matter_good_to_know': 'Good to know',
        'matter_notes': 'Glowback is an uncertified Matter light: Apple Home asks you to confirm (Add Anyway), Google Home needs a free test setup first. Your phone and this PC must be on the same network; if Windows asks, allow Glowback.',
        'matter_controller': 'Matter app',
        'home_connected': 'Connected to {host}',
        'home_not_set': 'Not set up',
        'home_not_set_desc': 'Install the Mosquitto broker app in Home Assistant, then connect Glowback to it.',
        'home_connected_desc': 'Glowback is in Settings › Devices & services › MQTT.',
        'home_setup': 'Set up',
        'home_change': 'Change',
        'home_entities': 'In Home Assistant',
        'home_voice': 'Voice assistants',
        'home_voice_text': 'Google Assistant and Alexa work through Home Assistant, Siri and the Home app through its HomeKit Bridge integration.',
        'settings_sub': 'Startup, updates and language.',
        'settings_sub_store': 'Startup and language.',
        'settings_start_desc': 'Glowback starts in the background when you sign in.',
        'startup_store_desc': "Turn Glowback on or off in Windows' startup apps.",
        'settings_updates': 'Updates',
        'settings_check_desc': 'Once a day, Glowback asks GitHub whether a new version is out.',
        'settings_check_now': 'Check now',
        'settings_new': 'Glowback {version} is available',
        'settings_lang': 'Language',
        'settings_lang_label': 'Interface language',
        'lang_auto': 'Windows language',
        'settings_help': 'Help',
        'settings_log_desc': 'What Glowback did, to understand a problem.',
        'settings_open': 'Open',
        'about_tagline': 'Ambient light for monitors with RGB LEDs on the back.',
        'about_version': 'Version {version}',
        'about_site': 'Website',
        'about_source': 'Source code and guide',
        'about_issue': 'Report a problem',
        'about_license': 'Free and open source, MIT license.',
        'nav_profiles': 'Profiles',
        'profiles_sub': 'Change the look with the time of day, the app in front or the sound that plays. The rest of the time, the Ambient light page applies.',
        'light_sub': 'What the LEDs behind your screen show: the picture, a color, a gradient or your music.',
        'mode_zones': 'Screen',
        'mode_average': 'Average',
        'mode_color': 'Color',
        'mode_gradient': 'Gradient',
        'mode_music': 'Music',
        'color_hue': 'Hue',
        'color_sat': 'Saturation',
        'color_red': 'Red',
        'color_orange': 'Orange',
        'color_yellow': 'Yellow',
        'color_green': 'Green',
        'color_cyan': 'Cyan',
        'color_blue': 'Blue',
        'color_purple': 'Purple',
        'color_pink': 'Pink',
        'color_warm': 'Warm white',
        'color_white': 'White',
        'gradient_sunset': 'Sunset',
        'gradient_ocean': 'Ocean',
        'gradient_aurora': 'Aurora',
        'gradient_neon': 'Neon',
        'gradient_ember': 'Ember',
        'gradient_forest': 'Forest',
        'gradient_presets': 'Presets',
        'gradient_flow': 'Flow',
        'gradient_flow_desc': 'The gradient slides slowly across the LEDs',
        'style_pulse': 'Pulse',
        'style_spectrum': 'Spectrum',
        'style_wave': 'Waves',
        'style_pulse_desc': 'All the LEDs beat with the music.',
        'style_spectrum_desc': 'Each LED follows its own notes: bass at the bottom, treble at the top.',
        'style_wave_desc': 'Each beat sends a wave of light up both sides of the screen.',
        'music_style': 'Style',
        'music_colors': 'Colors',
        'music_sensitivity': 'Sensitivity',
        'music_on': 'The LEDs follow what your PC plays. Nothing is recorded.',
        'music_silent': 'No sound right now: play some music.',
        'palette_rainbow': 'Rainbow',
        'palette_screen': "The screen's colors",
        'palette_color': 'My color',
        'palette_gradient': 'My gradient',
        'now_base': 'No profile right now: the Ambient light page applies.',
        'now_night': 'Night profile until {end}: {look}, brightness {brightness} %.',
        'now_app': '{rule}: {look}.',
        'now_rest': 'None of your apps: {look}.',
        'night_title': 'Day and night',
        'night_profile': 'Night profile',
        'night_desc': 'From {start} to {end}, a softer light',
        'night_hours': 'Hours',
        'night_brightness': 'Brightness at night',
        'night_look': 'Look at night',
        'night_same': 'Same as the day',
        'night_short': 'Night',
        'apps_title': 'By app',
        'apps_empty': 'No app yet: add one below.',
        'apps_add': 'Add an app',
        'apps_examples': 'For example: music while Spotify plays sound, the screen for games full screen, blue while Visual Studio Code is in front.',
        'rest_title': 'The rest of the time',
        'rest_desc': 'When none of these apps matches',
        'look_label': 'Look',
        'look_auto': 'Auto: the Ambient light page',
        'look_auto_short': 'Auto',
        'look_device': "LEDs' own effect",
        'look_off': 'LEDs off',
        'sync_playing': 'Plays sound',
        'profiles_none': 'None',
        'profiles_one': '1 profile',
        'profiles_many': '{n} profiles',
        'profiles_none_long': 'None: the settings above apply all the time',
        'profiles_apps_one': '1 app',
        'profiles_apps': '{n} apps',
        'profiles_now': 'now {name}',
        'state_device': "LEDs' own effect",
        'state_dark': 'LEDs off',
        'tip_device': 'Glowback: the LEDs show their own effect',
        'home_leds_title': 'Number of LEDs',
        'home_update_title': 'Updates',
        'home_light': 'Turn it on or off, set its brightness, color and mode',
        'home_leds': 'How many LEDs Glowback drives right now',
        'home_update': 'New versions of Glowback, installed from Home Assistant',
    },
    'fr': {
        'update_downloading': 'Téléchargement de Glowback {version}…',
        'update_installing': 'Installation de la mise à jour. Glowback va redémarrer tout seul.',
        'update_failed': "La mise à jour n'a pas pu être installée ({error}). Ouverture de la page de téléchargement.",
        'start_windows': 'Lancer au démarrage',
        'mode': 'Mode',
        'zones': 'Chaque LED suit sa zone',
        'average': 'Une seule couleur moyenne',
        'brightness': 'Luminosité',
        'made_by': 'Créé par {author}',
        'star': 'Mettre une étoile sur GitHub',
        'open_log': 'Ouvrir le journal',
        'quit': 'Quitter',
        'by': 'par {author}',
        'tip_on': "Glowback : lumière d'ambiance active",
        'tip_off': 'Glowback : en pause',
        'balloon_title': 'Glowback est lancé',
        'balloon_text': 'Clic droit sur cette icône pour le mettre en pause, changer le mode ou la luminosité, ou quitter.',
        'already': "Glowback est déjà lancé : son icône est à côté de l'horloge.",
        'pausing': "Mise en pause de Glowback le temps de l'opération...",
        'restarted': 'Glowback a redémarré en arrière-plan.',
        'press_enter': 'Appuyez sur Entrée pour fermer cette fenêtre...',
        'test_intro': "Regardez le mur derrière l'écran :",
        'test_white': 'toutes les LED en BLANC',
        'test_lr': "GAUCHE = ROUGE, DROITE = BLEU (vu de votre place ; si c'est inversé, utilisez --mirror)",
        'test_tb': "HAUT = VERT, BAS = JAUNE (si c'est inversé, utilisez --flip)",
        'test_rainbow': 'arc-en-ciel qui tourne autour des LED',
        'test_done': "Terminé, les LED sont rendues à l'appareil.",
        'no_device': 'Aucun appareil Éclairage dynamique trouvé (glowback --list).',
        'cal_intro': "Balance des blancs : ajustez jusqu'à ce que la lumière sur le mur paraisse d'un blanc neutre.",
        'cal_keys1': '  r / R  moins / plus de rouge     g / G  vert     b / B  bleu',
        'cal_keys2': '  1 2 3 4  test à 100 / 50 / 25 / 10 %     Entrée  enregistrer     Échap  passer cet appareil',
        'cal_state': '  rouge {r:.2f}   vert {g:.2f}   bleu {b:.2f}   (niveau {level:.0%})   ',
        'cal_saved': 'enregistré.',
        'cal_skipped': 'ignoré.',
        'cal_restart': 'Redémarrez Glowback (sinon il en tiendra compte au prochain lancement).',
        'ambilight': "Lumière d'ambiance",
        'state_on': 'Actif · {leds} LED',
        'state_paused': 'En pause',
        'state_none': 'Recherche des LED…',
        'about': 'À propos',
        'updates': 'Rechercher des mises à jour',
        'auto_check': 'Vérifier automatiquement',
        'up_to_date': 'À jour',
        'check_failed': 'Échec',
        'update_to': 'Mettre à jour vers la {version}',
        'update_title': 'Glowback {version} est disponible',
        'update_text': 'Cliquez ici pour le télécharger.',
        'ha_setup': 'Configurer',
        'ha_connected': 'Connecté',
        'ha_connecting': 'Connexion…',
        'ha_error': 'Non connecté',
        'ha_intro': "Glowback apparaît dans Home Assistant comme une lumière à piloter depuis vos tableaux de bord, vos automatisations et Google Assistant. La connexion passe par MQTT : installez l'application Mosquitto broker dans Home Assistant, puis connectez-vous ici avec un utilisateur Home Assistant.",
        'ha_guide': 'Guide pas à pas',
        'ha_address': 'Adresse',
        'ha_port': 'Port',
        'ha_user': 'Utilisateur',
        'ha_password': 'Mot de passe',
        'ha_user_hint': 'Utilisateur Home Assistant',
        'ha_password_saved': 'Enregistré',
        'ha_connect': 'Connecter',
        'ha_cancel': 'Annuler',
        'ha_disconnect': 'Déconnecter',
        'ha_testing': 'Connexion à Home Assistant…',
        'ha_need_address': "Indiquez l'adresse de Home Assistant.",
        'ha_err_address': 'Cette adresse est introuvable sur votre réseau.',
        'ha_err_broker': "Aucun broker MQTT ne répond à cette adresse. L'application Mosquitto broker est-elle démarrée ?",
        'ha_err_login': 'Utilisateur ou mot de passe incorrect.',
        'ha_err_refused': 'Le broker MQTT a refusé la connexion.',
        'ha_err_tls': 'La connexion sécurisée a échoué.',
        'ha_err_other': 'La connexion a échoué ({error}).',
        'ha_done_title': 'Connecté à Home Assistant',
        'ha_done_text': 'Glowback est dans Paramètres › Appareils et services › MQTT.',
        'open_app': 'Ouvrir Glowback',
        'nav_home': 'Home Assistant',
        'nav_light': "Lumière d'ambiance",
        'nav_settings': 'Paramètres',
        'nav_about': 'À propos',
        'app_quit': 'Quitter Glowback',
        'app_background': "Glowback continue en arrière-plan. Cliquez sur son icône près de l'horloge pour revenir.",
        'mode_zones_desc': "Chaque LED prend les couleurs de l'image juste à côté d'elle.",
        'mode_average_desc': "Toutes les LED affichent la couleur moyenne de l'écran.",
        'sync_now_paused': "La lumière d'ambiance est en pause.",
        'sync_app': 'App',
        'sync_when_label': 'Quand',
        'sync_screen': 'Écran',
        'sync_any_app': "N'importe quelle app",
        'sync_open_apps': 'Apps ouvertes',
        'sync_browse': 'Autre programme…',
        'sync_running': 'Est lancée',
        'sync_foreground': 'Est au premier plan',
        'sync_fullscreen': 'Est en plein écran',
        'sync_any_screen': "N'importe quel écran",
        'sync_led_screen': "L'écran des LED",
        'sync_screen_n': 'Écran {n}',
        'sync_add': 'Ajouter',
        'sync_remove': 'Retirer',
        'sync_programs': 'Programmes',
        'home_sub': "Pilotez la lumière d'ambiance depuis Home Assistant, ses automatisations et votre assistant vocal.",
        'nav_matter': 'Apple et Google',
        'matter_apple_home': 'Apple Maison',
        'matter_title': 'Apple Maison, Google Home et Alexa',
        'matter_sub': "Pilotez la lumière d'ambiance depuis votre téléphone avec Matter : Glowback apparaît comme une lampe dans Apple Maison, Google Home, Alexa ou SmartThings, sans Home Assistant.",
        'matter_toggle': 'Lampe Matter',
        'matter_off_desc': 'Désactivée : les téléphones ne voient pas Glowback',
        'matter_failed': 'Démarrage impossible : voir le journal',
        'matter_on_count': 'Activée · apps appairées : {n}',
        'matter_on_none': 'Activée · prête à être appairée',
        'matter_pair': 'Appairer',
        'matter_scan_title': 'Scannez avec votre téléphone',
        'matter_scan': 'Dans Apple Maison, Google Home ou Alexa, ajoutez un accessoire ou un appareil Matter, puis scannez ce code. Ou tapez-le :',
        'matter_open_for': 'Appairage ouvert encore {min} min',
        'matter_stop': 'Arrêter',
        'matter_other_app': "Une autre app est en train d'être ajoutée à Glowback : continuez dans cette app ({min} min restantes).",
        'matter_closed_desc': "Ouvrez l'appairage pendant 15 minutes pour ajouter Glowback à Apple Maison, Google Home, Alexa ou une autre app Matter. Déjà appairée ? Ajoutez l'app suivante de la même façon.",
        'matter_open': 'Appairer un téléphone',
        'matter_paired': 'Apps appairées',
        'matter_paired_desc': 'Peut allumer la lumière, régler sa luminosité et sa couleur',
        'matter_none': "Aucun téléphone ni aucune app pour l'instant.",
        'matter_remove': 'Retirer',
        'matter_remove_ask': 'Retirer Glowback de {app} ? Cette app ne pourra plus piloter la lumière.',
        'matter_good_to_know': 'Bon à savoir',
        'matter_notes': "Glowback est une lampe Matter non certifiée : Apple Maison vous demande de confirmer (Ajouter quand même), Google Home demande d'abord une configuration de test gratuite. Votre téléphone et ce PC doivent être sur le même réseau ; si Windows le demande, autorisez Glowback.",
        'matter_controller': 'App Matter',
        'home_connected': 'Connecté à {host}',
        'home_not_set': 'Pas encore configuré',
        'home_not_set_desc': "Installez l'application Mosquitto broker dans Home Assistant, puis connectez-y Glowback.",
        'home_connected_desc': 'Glowback est dans Paramètres › Appareils et services › MQTT.',
        'home_setup': 'Configurer',
        'home_change': 'Modifier',
        'home_entities': 'Dans Home Assistant',
        'home_voice': 'Assistants vocaux',
        'home_voice_text': "Google Assistant et Alexa passent par Home Assistant, Siri et l'app Maison par son intégration HomeKit Bridge.",
        'settings_sub': 'Démarrage, mises à jour et langue.',
        'settings_sub_store': 'Démarrage et langue.',
        'settings_start_desc': "Glowback démarre en arrière-plan à l'ouverture de session.",
        'startup_store_desc': 'Activez ou désactivez Glowback dans les applications de démarrage de Windows.',
        'settings_updates': 'Mises à jour',
        'settings_check_desc': 'Une fois par jour, Glowback demande à GitHub si une nouvelle version est sortie.',
        'settings_check_now': 'Rechercher',
        'settings_new': 'Glowback {version} est disponible',
        'settings_lang': 'Langue',
        'settings_lang_label': "Langue de l'interface",
        'lang_auto': 'Langue de Windows',
        'settings_help': 'Aide',
        'settings_log_desc': 'Ce que Glowback a fait, pour comprendre un problème.',
        'settings_open': 'Ouvrir',
        'about_tagline': "Lumière d'ambiance pour les écrans à LED RGB au dos.",
        'about_version': 'Version {version}',
        'about_site': 'Site web',
        'about_source': 'Code source et guide',
        'about_issue': 'Signaler un problème',
        'about_license': 'Libre et open source, licence MIT.',
        'nav_profiles': 'Profils',
        'profiles_sub': "Changez d'ambiance selon l'heure, l'app au premier plan ou le son qui joue. Le reste du temps, la page Lumière d'ambiance s'applique.",
        'light_sub': "Ce que montrent les LED derrière votre écran : l'image, une couleur, un dégradé ou votre musique.",
        'mode_zones': 'Écran',
        'mode_average': 'Moyenne',
        'mode_color': 'Couleur',
        'mode_gradient': 'Dégradé',
        'mode_music': 'Musique',
        'color_hue': 'Teinte',
        'color_sat': 'Saturation',
        'color_red': 'Rouge',
        'color_orange': 'Orange',
        'color_yellow': 'Jaune',
        'color_green': 'Vert',
        'color_cyan': 'Cyan',
        'color_blue': 'Bleu',
        'color_purple': 'Violet',
        'color_pink': 'Rose',
        'color_warm': 'Blanc chaud',
        'color_white': 'Blanc',
        'gradient_sunset': 'Coucher de soleil',
        'gradient_ocean': 'Océan',
        'gradient_aurora': 'Aurore',
        'gradient_neon': 'Néon',
        'gradient_ember': 'Braise',
        'gradient_forest': 'Forêt',
        'gradient_presets': 'Modèles',
        'gradient_flow': 'Défilement',
        'gradient_flow_desc': 'Le dégradé glisse lentement sur les LED',
        'style_pulse': 'Pulsation',
        'style_spectrum': 'Spectre',
        'style_wave': 'Vagues',
        'style_pulse_desc': 'Toutes les LED battent au rythme de la musique.',
        'style_spectrum_desc': 'Chaque LED suit ses notes : les basses en bas, les aigus en haut.',
        'style_wave_desc': "Chaque temps fort envoie une vague de lumière de chaque côté de l'écran.",
        'music_style': 'Style',
        'music_colors': 'Couleurs',
        'music_sensitivity': 'Sensibilité',
        'music_on': "Les LED suivent ce que joue votre PC. Rien n'est enregistré.",
        'music_silent': "Aucun son pour l'instant : lancez une musique.",
        'palette_rainbow': 'Arc-en-ciel',
        'palette_screen': "Couleurs de l'écran",
        'palette_color': 'Ma couleur',
        'palette_gradient': 'Mon dégradé',
        'now_base': "Aucun profil en ce moment : la page Lumière d'ambiance s'applique.",
        'now_night': "Profil de nuit jusqu'à {end} : {look}, luminosité {brightness} %.",
        'now_app': '{rule} : {look}.',
        'now_rest': 'Aucune de vos apps : {look}.',
        'night_title': 'Jour et nuit',
        'night_profile': 'Profil de nuit',
        'night_desc': 'De {start} à {end}, une lumière plus douce',
        'night_hours': 'Horaires',
        'night_brightness': 'Luminosité la nuit',
        'night_look': 'Ambiance la nuit',
        'night_same': 'Comme le jour',
        'night_short': 'Nuit',
        'apps_title': 'Par app',
        'apps_empty': "Aucune app pour l'instant : ajoutez-en une ci-dessous.",
        'apps_add': 'Ajouter une app',
        'apps_examples': "Par exemple : la musique quand Spotify joue du son, l'écran pour les jeux en plein écran, du bleu quand Visual Studio Code est au premier plan.",
        'rest_title': 'Le reste du temps',
        'rest_desc': 'Quand aucune de ces apps ne correspond',
        'look_label': 'Ambiance',
        'look_auto': "Auto : la page Lumière d'ambiance",
        'look_auto_short': 'Auto',
        'look_device': 'Effet des LED',
        'look_off': 'LED éteintes',
        'sync_playing': 'Joue du son',
        'profiles_none': 'Aucun',
        'profiles_one': '1 profil',
        'profiles_many': '{n} profils',
        'profiles_none_long': "Aucun : les réglages ci-dessus s'appliquent tout le temps",
        'profiles_apps_one': '1 app',
        'profiles_apps': '{n} apps',
        'profiles_now': 'maintenant {name}',
        'state_device': 'Effet des LED',
        'state_dark': 'LED éteintes',
        'tip_device': 'Glowback : les LED affichent leur propre effet',
        'home_leds_title': 'Nombre de LED',
        'home_update_title': 'Mises à jour',
        'home_light': 'Allumez-la, éteignez-la, réglez sa luminosité, sa couleur et son mode',
        'home_leds': 'Combien de LED Glowback pilote en ce moment',
        'home_update': 'Les nouvelles versions de Glowback, installées depuis Home Assistant',
    },
    'es': {
        'update_downloading': 'Descargando Glowback {version}…',
        'update_installing': 'Instalando la actualización. Glowback se reiniciará solo.',
        'update_failed': 'No se pudo instalar la actualización ({error}). Abriendo la página de descarga.',
        'start_windows': 'Iniciar con Windows',
        'mode': 'Modo',
        'zones': 'Cada LED sigue su zona',
        'average': 'Un solo color promedio',
        'brightness': 'Brillo',
        'made_by': 'Creado por {author}',
        'star': 'Dar una estrella en GitHub',
        'open_log': 'Abrir registro',
        'quit': 'Salir',
        'by': 'por {author}',
        'tip_on': 'Glowback: luz ambiental activa',
        'tip_off': 'Glowback: en pausa',
        'balloon_title': 'Glowback está en marcha',
        'balloon_text': 'Haz clic derecho en este icono para pausarlo, cambiar el modo o el brillo, o salir.',
        'already': 'Glowback ya está en marcha: busca su icono junto al reloj.',
        'pausing': 'Pausando Glowback un momento...',
        'restarted': 'Glowback se ha reiniciado en segundo plano.',
        'press_enter': 'Pulsa Intro para cerrar esta ventana...',
        'test_intro': 'Mira la pared detrás de la pantalla:',
        'test_white': 'todos los LED en BLANCO',
        'test_lr': 'IZQUIERDA = ROJO, DERECHA = AZUL (visto desde tu sitio; si está invertido, usa --mirror)',
        'test_tb': 'ARRIBA = VERDE, ABAJO = AMARILLO (si está invertido, usa --flip)',
        'test_rainbow': 'arcoíris girando por los LED',
        'test_done': 'Listo, los LED vuelven al dispositivo.',
        'no_device': 'No se encontró ningún dispositivo de Iluminación dinámica (glowback --list).',
        'cal_intro': 'Balance de blancos: ajusta hasta que la luz en la pared parezca de un blanco neutro.',
        'cal_keys1': '  r / R  menos / más rojo     g / G  verde     b / B  azul',
        'cal_keys2': '  1 2 3 4  prueba al 100 / 50 / 25 / 10 %     Intro  guardar     Esc  omitir este dispositivo',
        'cal_state': '  rojo {r:.2f}   verde {g:.2f}   azul {b:.2f}   (nivel {level:.0%})   ',
        'cal_saved': 'guardado.',
        'cal_skipped': 'omitido.',
        'cal_restart': 'Reinicia Glowback (o lo aplicará en su próximo inicio).',
        'ambilight': 'Luz ambiental',
        'state_on': 'Activo · {leds} LED',
        'state_paused': 'En pausa',
        'state_none': 'Buscando LED…',
        'about': 'Acerca de',
        'updates': 'Buscar actualizaciones',
        'auto_check': 'Buscar automáticamente',
        'up_to_date': 'Actualizado',
        'check_failed': 'Error',
        'update_to': 'Actualizar a {version}',
        'update_title': 'Glowback {version} está disponible',
        'update_text': 'Haz clic aquí para descargarlo.',
        'ha_setup': 'Configurar',
        'ha_connected': 'Conectado',
        'ha_connecting': 'Conectando…',
        'ha_error': 'Sin conexión',
        'ha_intro': 'Glowback aparece en Home Assistant como una luz que puedes controlar desde los paneles, las automatizaciones y Google Assistant. Se conecta por MQTT: instala la app Mosquitto broker en Home Assistant e inicia sesión aquí con un usuario de Home Assistant.',
        'ha_guide': 'Guía paso a paso',
        'ha_address': 'Dirección',
        'ha_port': 'Puerto',
        'ha_user': 'Usuario',
        'ha_password': 'Contraseña',
        'ha_user_hint': 'Usuario de Home Assistant',
        'ha_password_saved': 'Guardada',
        'ha_connect': 'Conectar',
        'ha_cancel': 'Cancelar',
        'ha_disconnect': 'Desconectar',
        'ha_testing': 'Conectando con Home Assistant…',
        'ha_need_address': 'Indica la dirección de Home Assistant.',
        'ha_err_address': 'No se encuentra esta dirección en tu red.',
        'ha_err_broker': 'Ningún broker MQTT responde en esta dirección. ¿Está iniciada la app Mosquitto broker?',
        'ha_err_login': 'Usuario o contraseña incorrectos.',
        'ha_err_refused': 'El broker MQTT rechazó la conexión.',
        'ha_err_tls': 'Falló la conexión segura.',
        'ha_err_other': 'Falló la conexión ({error}).',
        'ha_done_title': 'Conectado a Home Assistant',
        'ha_done_text': 'Glowback está en Configuración › Dispositivos y servicios › MQTT.',
        'open_app': 'Abrir Glowback',
        'nav_home': 'Home Assistant',
        'nav_light': 'Luz ambiental',
        'nav_settings': 'Configuración',
        'nav_about': 'Acerca de',
        'app_quit': 'Salir de Glowback',
        'app_background': 'Glowback sigue funcionando en segundo plano. Haz clic en su icono junto al reloj para volver.',
        'mode_zones_desc': 'Cada LED toma los colores de la imagen justo a su lado.',
        'mode_average_desc': 'Todos los LED muestran el color medio de la pantalla.',
        'sync_now_paused': 'La luz ambiental está en pausa.',
        'sync_app': 'App',
        'sync_when_label': 'Cuándo',
        'sync_screen': 'Pantalla',
        'sync_any_app': 'Cualquier app',
        'sync_open_apps': 'Apps abiertas',
        'sync_browse': 'Otro programa…',
        'sync_running': 'Está abierta',
        'sync_foreground': 'Está en primer plano',
        'sync_fullscreen': 'Está en pantalla completa',
        'sync_any_screen': 'Cualquier pantalla',
        'sync_led_screen': 'La pantalla de los LED',
        'sync_screen_n': 'Pantalla {n}',
        'sync_add': 'Añadir',
        'sync_remove': 'Quitar',
        'sync_programs': 'Programas',
        'home_sub': 'Controla la luz ambiental desde Home Assistant, sus automatizaciones y tu asistente de voz.',
        'nav_matter': 'Apple y Google',
        'matter_apple_home': 'Apple Casa',
        'matter_title': 'Apple Casa, Google Home y Alexa',
        'matter_sub': 'Controla la luz ambiental desde tu teléfono con Matter: Glowback aparece como una luz en Apple Casa, Google Home, Alexa o SmartThings, sin Home Assistant.',
        'matter_toggle': 'Luz Matter',
        'matter_off_desc': 'Desactivada: los teléfonos no ven Glowback',
        'matter_failed': 'No se pudo iniciar: mira el registro',
        'matter_on_count': 'Activada · apps vinculadas: {n}',
        'matter_on_none': 'Activada · lista para vincular',
        'matter_pair': 'Vincular',
        'matter_scan_title': 'Escanea con tu teléfono',
        'matter_scan': 'En Apple Casa, Google Home o Alexa, añade un accesorio o un dispositivo Matter y escanea este código. O escríbelo:',
        'matter_open_for': 'Vinculación abierta {min} min más',
        'matter_stop': 'Detener',
        'matter_other_app': 'Se está añadiendo otra app a Glowback: continúa en esa app (quedan {min} min).',
        'matter_closed_desc': 'Abre la vinculación durante 15 minutos para añadir Glowback a Apple Casa, Google Home, Alexa u otra app Matter. ¿Ya vinculada? Añade la siguiente app del mismo modo.',
        'matter_open': 'Vincular un teléfono',
        'matter_paired': 'Apps vinculadas',
        'matter_paired_desc': 'Puede encender la luz y cambiar su brillo y su color',
        'matter_none': 'Todavía ningún teléfono ni app.',
        'matter_remove': 'Quitar',
        'matter_remove_ask': '¿Quitar Glowback de {app}? Esa app ya no podrá controlar la luz.',
        'matter_good_to_know': 'Conviene saber',
        'matter_notes': 'Glowback es una luz Matter no certificada: Apple Casa te pide confirmar (Añadir de todos modos) y Google Home necesita antes una configuración de prueba gratuita. Tu teléfono y este PC deben estar en la misma red; si Windows lo pide, permite Glowback.',
        'matter_controller': 'App Matter',
        'home_connected': 'Conectado a {host}',
        'home_not_set': 'Sin configurar',
        'home_not_set_desc': 'Instala la app Mosquitto broker en Home Assistant y luego conecta Glowback a ella.',
        'home_connected_desc': 'Glowback está en Configuración › Dispositivos y servicios › MQTT.',
        'home_setup': 'Configurar',
        'home_change': 'Cambiar',
        'home_entities': 'En Home Assistant',
        'home_voice': 'Asistentes de voz',
        'home_voice_text': 'Google Assistant y Alexa funcionan a través de Home Assistant, Siri y la app Casa con su integración HomeKit Bridge.',
        'settings_sub': 'Inicio, actualizaciones e idioma.',
        'settings_sub_store': 'Inicio e idioma.',
        'settings_start_desc': 'Glowback se inicia en segundo plano al iniciar sesión.',
        'startup_store_desc': 'Activa o desactiva Glowback en las aplicaciones de inicio de Windows.',
        'settings_updates': 'Actualizaciones',
        'settings_check_desc': 'Una vez al día, Glowback pregunta a GitHub si hay una versión nueva.',
        'settings_check_now': 'Buscar',
        'settings_new': 'Glowback {version} está disponible',
        'settings_lang': 'Idioma',
        'settings_lang_label': 'Idioma de la interfaz',
        'lang_auto': 'Idioma de Windows',
        'settings_help': 'Ayuda',
        'settings_log_desc': 'Lo que ha hecho Glowback, para entender un problema.',
        'settings_open': 'Abrir',
        'about_tagline': 'Luz ambiental para monitores con LED RGB en la parte trasera.',
        'about_version': 'Versión {version}',
        'about_site': 'Sitio web',
        'about_source': 'Código fuente y guía',
        'about_issue': 'Informar de un problema',
        'about_license': 'Libre y de código abierto, licencia MIT.',
        'nav_profiles': 'Perfiles',
        'profiles_sub': 'Cambia el ambiente según la hora, la app en primer plano o el sonido que suena. El resto del tiempo se aplica la página Luz ambiental.',
        'light_sub': 'Lo que muestran los LED detrás de tu pantalla: la imagen, un color, un degradado o tu música.',
        'mode_zones': 'Pantalla',
        'mode_average': 'Promedio',
        'mode_color': 'Color',
        'mode_gradient': 'Degradado',
        'mode_music': 'Música',
        'color_hue': 'Tono',
        'color_sat': 'Saturación',
        'color_red': 'Rojo',
        'color_orange': 'Naranja',
        'color_yellow': 'Amarillo',
        'color_green': 'Verde',
        'color_cyan': 'Cian',
        'color_blue': 'Azul',
        'color_purple': 'Violeta',
        'color_pink': 'Rosa',
        'color_warm': 'Blanco cálido',
        'color_white': 'Blanco',
        'gradient_sunset': 'Atardecer',
        'gradient_ocean': 'Océano',
        'gradient_aurora': 'Aurora',
        'gradient_neon': 'Neón',
        'gradient_ember': 'Brasa',
        'gradient_forest': 'Bosque',
        'gradient_presets': 'Predefinidos',
        'gradient_flow': 'Movimiento',
        'gradient_flow_desc': 'El degradado se desliza despacio por los LED',
        'style_pulse': 'Pulso',
        'style_spectrum': 'Espectro',
        'style_wave': 'Ondas',
        'style_pulse_desc': 'Todos los LED laten al ritmo de la música.',
        'style_spectrum_desc': 'Cada LED sigue sus notas: graves abajo, agudos arriba.',
        'style_wave_desc': 'Cada golpe envía una ola de luz por ambos lados de la pantalla.',
        'music_style': 'Estilo',
        'music_colors': 'Colores',
        'music_sensitivity': 'Sensibilidad',
        'music_on': 'Los LED siguen lo que suena en tu PC. No se graba nada.',
        'music_silent': 'No hay sonido ahora: pon algo de música.',
        'palette_rainbow': 'Arcoíris',
        'palette_screen': 'Colores de la pantalla',
        'palette_color': 'Mi color',
        'palette_gradient': 'Mi degradado',
        'now_base': 'Ningún perfil ahora: se aplica la página Luz ambiental.',
        'now_night': 'Perfil nocturno hasta las {end}: {look}, brillo {brightness} %.',
        'now_app': '{rule}: {look}.',
        'now_rest': 'Ninguna de tus apps: {look}.',
        'night_title': 'Día y noche',
        'night_profile': 'Perfil nocturno',
        'night_desc': 'De {start} a {end}, una luz más suave',
        'night_hours': 'Horario',
        'night_brightness': 'Brillo de noche',
        'night_look': 'Ambiente de noche',
        'night_same': 'Como de día',
        'night_short': 'Noche',
        'apps_title': 'Por app',
        'apps_empty': 'Todavía no hay apps: añade una abajo.',
        'apps_add': 'Añadir una app',
        'apps_examples': 'Por ejemplo: la música cuando Spotify reproduce sonido, la pantalla para los juegos en pantalla completa, azul cuando Visual Studio Code está en primer plano.',
        'rest_title': 'El resto del tiempo',
        'rest_desc': 'Cuando ninguna de estas apps coincide',
        'look_label': 'Ambiente',
        'look_auto': 'Auto: la página Luz ambiental',
        'look_auto_short': 'Auto',
        'look_device': 'Efecto propio de los LED',
        'look_off': 'LED apagados',
        'sync_playing': 'Reproduce sonido',
        'profiles_none': 'Ninguno',
        'profiles_one': '1 perfil',
        'profiles_many': '{n} perfiles',
        'profiles_none_long': 'Ninguno: los ajustes de arriba se aplican siempre',
        'profiles_apps_one': '1 app',
        'profiles_apps': '{n} apps',
        'profiles_now': 'ahora {name}',
        'state_device': 'Efecto propio de los LED',
        'state_dark': 'LED apagados',
        'tip_device': 'Glowback: los LED muestran su propio efecto',
        'home_leds_title': 'Número de LED',
        'home_update_title': 'Actualizaciones',
        'home_light': 'Enciéndela o apágala, ajusta su brillo, su color y su modo',
        'home_leds': 'Cuántos LED controla Glowback ahora',
        'home_update': 'Las nuevas versiones de Glowback, instaladas desde Home Assistant',
    },
    'de': {
        'update_downloading': 'Glowback {version} wird heruntergeladen …',
        'update_installing': 'Das Update wird installiert. Glowback startet danach von selbst neu.',
        'update_failed': 'Das Update konnte nicht installiert werden ({error}). Die Download-Seite wird geöffnet.',
        'start_windows': 'Mit Windows starten',
        'mode': 'Modus',
        'zones': 'Jede LED folgt ihrer Zone',
        'average': 'Eine Durchschnittsfarbe',
        'brightness': 'Helligkeit',
        'made_by': 'Erstellt von {author}',
        'star': 'Auf GitHub einen Stern geben',
        'open_log': 'Protokoll öffnen',
        'quit': 'Beenden',
        'by': 'von {author}',
        'tip_on': 'Glowback: Umgebungslicht an',
        'tip_off': 'Glowback: pausiert',
        'balloon_title': 'Glowback läuft',
        'balloon_text': 'Rechtsklick auf dieses Symbol: pausieren, Modus oder Helligkeit ändern oder beenden.',
        'already': 'Glowback läuft bereits: Das Symbol befindet sich neben der Uhr.',
        'pausing': 'Glowback wird kurz pausiert...',
        'restarted': 'Glowback wurde im Hintergrund neu gestartet.',
        'press_enter': 'Eingabetaste drücken, um dieses Fenster zu schließen...',
        'test_intro': 'Schau auf die Wand hinter dem Bildschirm:',
        'test_white': 'alle LEDs WEISS',
        'test_lr': 'LINKS = ROT, RECHTS = BLAU (von deinem Platz aus; falls vertauscht: --mirror)',
        'test_tb': 'OBEN = GRÜN, UNTEN = GELB (falls vertauscht: --flip)',
        'test_rainbow': 'Regenbogen läuft um die LEDs',
        'test_done': 'Fertig, die LEDs gehören wieder dem Gerät.',
        'no_device': 'Kein Gerät mit dynamischer Beleuchtung gefunden (glowback --list).',
        'cal_intro': 'Weißabgleich: so lange anpassen, bis das Licht an der Wand neutral weiß wirkt.',
        'cal_keys1': '  r / R  weniger / mehr Rot     g / G  Grün     b / B  Blau',
        'cal_keys2': '  1 2 3 4  Test bei 100 / 50 / 25 / 10 %     Eingabe  speichern     Esc  Gerät überspringen',
        'cal_state': '  Rot {r:.2f}   Grün {g:.2f}   Blau {b:.2f}   (Stufe {level:.0%})   ',
        'cal_saved': 'gespeichert.',
        'cal_skipped': 'übersprungen.',
        'cal_restart': 'Glowback neu starten (sonst beim nächsten Start übernommen).',
        'ambilight': 'Umgebungslicht',
        'state_on': 'Aktiv · {leds} LEDs',
        'state_paused': 'Pausiert',
        'state_none': 'Suche nach LEDs …',
        'about': 'Info',
        'updates': 'Nach Updates suchen',
        'auto_check': 'Automatisch suchen',
        'up_to_date': 'Aktuell',
        'check_failed': 'Fehler',
        'update_to': 'Auf {version} aktualisieren',
        'update_title': 'Glowback {version} ist verfügbar',
        'update_text': 'Zum Herunterladen hier klicken.',
        'ha_setup': 'Einrichten',
        'ha_connected': 'Verbunden',
        'ha_connecting': 'Verbinde…',
        'ha_error': 'Nicht verbunden',
        'ha_intro': 'Glowback erscheint in Home Assistant als Licht, das du über Dashboards, Automationen und Google Assistant steuerst. Die Verbindung läuft über MQTT: Installiere in Home Assistant die App Mosquitto broker und melde dich hier mit einem Home-Assistant-Benutzer an.',
        'ha_guide': 'Schritt-für-Schritt-Anleitung',
        'ha_address': 'Adresse',
        'ha_port': 'Port',
        'ha_user': 'Benutzer',
        'ha_password': 'Passwort',
        'ha_user_hint': 'Home-Assistant-Benutzer',
        'ha_password_saved': 'Gespeichert',
        'ha_connect': 'Verbinden',
        'ha_cancel': 'Abbrechen',
        'ha_disconnect': 'Trennen',
        'ha_testing': 'Verbinde mit Home Assistant…',
        'ha_need_address': 'Gib die Adresse von Home Assistant ein.',
        'ha_err_address': 'Diese Adresse wurde in deinem Netzwerk nicht gefunden.',
        'ha_err_broker': 'Unter dieser Adresse antwortet kein MQTT-Broker. Läuft die App Mosquitto broker?',
        'ha_err_login': 'Benutzer oder Passwort falsch.',
        'ha_err_refused': 'Der MQTT-Broker hat die Verbindung abgelehnt.',
        'ha_err_tls': 'Die sichere Verbindung ist fehlgeschlagen.',
        'ha_err_other': 'Verbindung fehlgeschlagen ({error}).',
        'ha_done_title': 'Mit Home Assistant verbunden',
        'ha_done_text': 'Glowback findest du unter Einstellungen › Geräte & Dienste › MQTT.',
        'open_app': 'Glowback öffnen',
        'nav_home': 'Home Assistant',
        'nav_light': 'Umgebungslicht',
        'nav_settings': 'Einstellungen',
        'nav_about': 'Info',
        'app_quit': 'Glowback beenden',
        'app_background': 'Glowback läuft im Hintergrund weiter. Klicke auf das Symbol neben der Uhr, um zurückzukehren.',
        'mode_zones_desc': 'Jede LED übernimmt die Farben des Bildes direkt neben ihr.',
        'mode_average_desc': 'Alle LEDs zeigen die Durchschnittsfarbe des Bildschirms.',
        'sync_now_paused': 'Das Umgebungslicht ist pausiert.',
        'sync_app': 'App',
        'sync_when_label': 'Wann',
        'sync_screen': 'Bildschirm',
        'sync_any_app': 'Beliebige App',
        'sync_open_apps': 'Geöffnete Apps',
        'sync_browse': 'Anderes Programm …',
        'sync_running': 'Läuft',
        'sync_foreground': 'Ist im Vordergrund',
        'sync_fullscreen': 'Ist im Vollbild',
        'sync_any_screen': 'Beliebiger Bildschirm',
        'sync_led_screen': 'Der LED-Bildschirm',
        'sync_screen_n': 'Bildschirm {n}',
        'sync_add': 'Hinzufügen',
        'sync_remove': 'Entfernen',
        'sync_programs': 'Programme',
        'home_sub': 'Steuere das Umgebungslicht aus Home Assistant, seinen Automationen und deinem Sprachassistenten.',
        'nav_matter': 'Apple & Google',
        'matter_apple_home': 'Apple Home',
        'matter_title': 'Apple Home, Google Home und Alexa',
        'matter_sub': 'Steuere das Umgebungslicht mit Matter von deinem Handy: Glowback erscheint als Lampe in Apple Home, Google Home, Alexa oder SmartThings, ohne Home Assistant.',
        'matter_toggle': 'Matter-Lampe',
        'matter_off_desc': 'Aus: Handys sehen Glowback nicht',
        'matter_failed': 'Start nicht möglich: siehe Protokoll',
        'matter_on_count': 'An · gekoppelte Apps: {n}',
        'matter_on_none': 'An · bereit zum Koppeln',
        'matter_pair': 'Koppeln',
        'matter_scan_title': 'Mit dem Handy scannen',
        'matter_scan': 'Füge in Apple Home, Google Home oder Alexa ein Zubehör oder Matter-Gerät hinzu und scanne diesen Code. Oder tippe ihn ein:',
        'matter_open_for': 'Kopplung noch {min} Min. offen',
        'matter_stop': 'Beenden',
        'matter_other_app': 'Eine weitere App wird zu Glowback hinzugefügt: mach in dieser App weiter (noch {min} Min.).',
        'matter_closed_desc': 'Öffne die Kopplung für 15 Minuten, um Glowback zu Apple Home, Google Home, Alexa oder einer anderen Matter-App hinzuzufügen. Schon gekoppelt? Füge die nächste App genauso hinzu.',
        'matter_open': 'Handy koppeln',
        'matter_paired': 'Gekoppelte Apps',
        'matter_paired_desc': 'Kann das Licht schalten und Helligkeit und Farbe ändern',
        'matter_none': 'Noch kein Handy und keine App.',
        'matter_remove': 'Entfernen',
        'matter_remove_ask': 'Glowback aus {app} entfernen? Diese App kann das Licht dann nicht mehr steuern.',
        'matter_good_to_know': 'Gut zu wissen',
        'matter_notes': 'Glowback ist eine nicht zertifizierte Matter-Lampe: Apple Home bittet um Bestätigung (Trotzdem hinzufügen), Google Home braucht vorher eine kostenlose Test-Einrichtung. Handy und PC müssen im selben Netzwerk sein; wenn Windows fragt, lass Glowback zu.',
        'matter_controller': 'Matter-App',
        'home_connected': 'Verbunden mit {host}',
        'home_not_set': 'Nicht eingerichtet',
        'home_not_set_desc': 'Installiere in Home Assistant die App Mosquitto broker und verbinde Glowback damit.',
        'home_connected_desc': 'Glowback findest du unter Einstellungen › Geräte & Dienste › MQTT.',
        'home_setup': 'Einrichten',
        'home_change': 'Ändern',
        'home_entities': 'In Home Assistant',
        'home_voice': 'Sprachassistenten',
        'home_voice_text': 'Google Assistant und Alexa funktionieren über Home Assistant, Siri und die Home-App über seine Integration HomeKit Bridge.',
        'settings_sub': 'Start, Updates und Sprache.',
        'settings_sub_store': 'Start und Sprache.',
        'settings_start_desc': 'Glowback startet bei der Anmeldung im Hintergrund.',
        'startup_store_desc': 'Schalte Glowback in den Autostart-Apps von Windows ein oder aus.',
        'settings_updates': 'Updates',
        'settings_check_desc': 'Einmal am Tag fragt Glowback bei GitHub nach einer neuen Version.',
        'settings_check_now': 'Suchen',
        'settings_new': 'Glowback {version} ist verfügbar',
        'settings_lang': 'Sprache',
        'settings_lang_label': 'Sprache der Oberfläche',
        'lang_auto': 'Windows-Sprache',
        'settings_help': 'Hilfe',
        'settings_log_desc': 'Was Glowback getan hat, um ein Problem zu verstehen.',
        'settings_open': 'Öffnen',
        'about_tagline': 'Umgebungslicht für Monitore mit RGB-LEDs auf der Rückseite.',
        'about_version': 'Version {version}',
        'about_site': 'Website',
        'about_source': 'Quellcode und Anleitung',
        'about_issue': 'Problem melden',
        'about_license': 'Frei und quelloffen, MIT-Lizenz.',
        'nav_profiles': 'Profile',
        'profiles_sub': 'Wechsle das Licht je nach Uhrzeit, App im Vordergrund oder laufendem Ton. Sonst gilt die Seite Umgebungslicht.',
        'light_sub': 'Was die LEDs hinter deinem Bildschirm zeigen: das Bild, eine Farbe, einen Verlauf oder deine Musik.',
        'mode_zones': 'Bildschirm',
        'mode_average': 'Mittelwert',
        'mode_color': 'Farbe',
        'mode_gradient': 'Verlauf',
        'mode_music': 'Musik',
        'color_hue': 'Farbton',
        'color_sat': 'Sättigung',
        'color_red': 'Rot',
        'color_orange': 'Orange',
        'color_yellow': 'Gelb',
        'color_green': 'Grün',
        'color_cyan': 'Cyan',
        'color_blue': 'Blau',
        'color_purple': 'Violett',
        'color_pink': 'Pink',
        'color_warm': 'Warmweiß',
        'color_white': 'Weiß',
        'gradient_sunset': 'Sonnenuntergang',
        'gradient_ocean': 'Ozean',
        'gradient_aurora': 'Polarlicht',
        'gradient_neon': 'Neon',
        'gradient_ember': 'Glut',
        'gradient_forest': 'Wald',
        'gradient_presets': 'Vorlagen',
        'gradient_flow': 'Bewegung',
        'gradient_flow_desc': 'Der Verlauf gleitet langsam über die LEDs',
        'style_pulse': 'Puls',
        'style_spectrum': 'Spektrum',
        'style_wave': 'Wellen',
        'style_pulse_desc': 'Alle LEDs pulsieren im Takt der Musik.',
        'style_spectrum_desc': 'Jede LED folgt ihren Tönen: Bässe unten, Höhen oben.',
        'style_wave_desc': 'Jeder Beat schickt eine Lichtwelle an beiden Seiten des Bildschirms hoch.',
        'music_style': 'Stil',
        'music_colors': 'Farben',
        'music_sensitivity': 'Empfindlichkeit',
        'music_on': 'Die LEDs folgen dem, was dein PC abspielt. Nichts wird aufgenommen.',
        'music_silent': 'Gerade kein Ton: spiel etwas Musik ab.',
        'palette_rainbow': 'Regenbogen',
        'palette_screen': 'Farben des Bildschirms',
        'palette_color': 'Meine Farbe',
        'palette_gradient': 'Mein Verlauf',
        'now_base': 'Gerade kein Profil: Es gilt die Seite Umgebungslicht.',
        'now_night': 'Nachtprofil bis {end}: {look}, Helligkeit {brightness} %.',
        'now_app': '{rule}: {look}.',
        'now_rest': 'Keine deiner Apps: {look}.',
        'night_title': 'Tag und Nacht',
        'night_profile': 'Nachtprofil',
        'night_desc': 'Von {start} bis {end}, ein sanfteres Licht',
        'night_hours': 'Uhrzeit',
        'night_brightness': 'Helligkeit nachts',
        'night_look': 'Licht nachts',
        'night_same': 'Wie am Tag',
        'night_short': 'Nacht',
        'apps_title': 'Pro App',
        'apps_empty': 'Noch keine App: füge unten eine hinzu.',
        'apps_add': 'App hinzufügen',
        'apps_examples': 'Zum Beispiel: Musik, wenn Spotify Ton abspielt, der Bildschirm für Spiele im Vollbild, Blau, wenn Visual Studio Code im Vordergrund ist.',
        'rest_title': 'Die übrige Zeit',
        'rest_desc': 'Wenn keine dieser Apps passt',
        'look_label': 'Licht',
        'look_auto': 'Auto: die Seite Umgebungslicht',
        'look_auto_short': 'Auto',
        'look_device': 'Eigener Effekt der LEDs',
        'look_off': 'LEDs aus',
        'sync_playing': 'Spielt Ton ab',
        'profiles_none': 'Keins',
        'profiles_one': '1 Profil',
        'profiles_many': '{n} Profile',
        'profiles_none_long': 'Keins: die Einstellungen oben gelten immer',
        'profiles_apps_one': '1 App',
        'profiles_apps': '{n} Apps',
        'profiles_now': 'jetzt {name}',
        'state_device': 'Eigener Effekt der LEDs',
        'state_dark': 'LEDs aus',
        'tip_device': 'Glowback: die LEDs zeigen ihren eigenen Effekt',
        'home_leds_title': 'Anzahl der LEDs',
        'home_update_title': 'Updates',
        'home_light': 'Ein- und ausschalten, Helligkeit, Farbe und Modus einstellen',
        'home_leds': 'Wie viele LEDs Glowback gerade steuert',
        'home_update': 'Neue Glowback-Versionen, aus Home Assistant installiert',
    },
    'it': {
        'update_downloading': 'Download di Glowback {version}…',
        'update_installing': "Installazione dell'aggiornamento. Glowback si riavvierà da solo.",
        'update_failed': "Impossibile installare l'aggiornamento ({error}). Apro la pagina di download.",
        'start_windows': 'Avvia con Windows',
        'mode': 'Modalità',
        'zones': 'Ogni LED segue la sua zona',
        'average': 'Un solo colore medio',
        'brightness': 'Luminosità',
        'made_by': 'Creato da {author}',
        'star': 'Metti una stella su GitHub',
        'open_log': 'Apri il log',
        'quit': 'Esci',
        'by': 'di {author}',
        'tip_on': 'Glowback: luce ambientale attiva',
        'tip_off': 'Glowback: in pausa',
        'balloon_title': 'Glowback è in esecuzione',
        'balloon_text': 'Fai clic destro su questa icona per metterlo in pausa, cambiare modalità o luminosità, o uscire.',
        'already': "Glowback è già in esecuzione: cerca la sua icona accanto all'orologio.",
        'pausing': 'Metto in pausa Glowback per un momento...',
        'restarted': 'Glowback è stato riavviato in background.',
        'press_enter': 'Premi Invio per chiudere questa finestra...',
        'test_intro': 'Guarda il muro dietro lo schermo:',
        'test_white': 'tutti i LED BIANCHI',
        'test_lr': 'SINISTRA = ROSSO, DESTRA = BLU (visto dal tuo posto; se è invertito usa --mirror)',
        'test_tb': 'SOPRA = VERDE, SOTTO = GIALLO (se è invertito usa --flip)',
        'test_rainbow': 'arcobaleno che gira intorno ai LED',
        'test_done': 'Fatto, i LED tornano al dispositivo.',
        'no_device': 'Nessun dispositivo Illuminazione dinamica trovato (glowback --list).',
        'cal_intro': 'Bilanciamento del bianco: regola finché la luce sul muro non sembra di un bianco neutro.',
        'cal_keys1': '  r / R  meno / più rosso     g / G  verde     b / B  blu',
        'cal_keys2': '  1 2 3 4  test al 100 / 50 / 25 / 10 %     Invio  salva     Esc  salta questo dispositivo',
        'cal_state': '  rosso {r:.2f}   verde {g:.2f}   blu {b:.2f}   (livello {level:.0%})   ',
        'cal_saved': 'salvato.',
        'cal_skipped': 'saltato.',
        'cal_restart': 'Riavvia Glowback (o verrà applicato al prossimo avvio).',
        'ambilight': 'Luce ambientale',
        'state_on': 'Attivo · {leds} LED',
        'state_paused': 'In pausa',
        'state_none': 'Ricerca dei LED…',
        'about': 'Informazioni',
        'updates': 'Controlla aggiornamenti',
        'auto_check': 'Controlla automaticamente',
        'up_to_date': 'Aggiornato',
        'check_failed': 'Errore',
        'update_to': 'Aggiorna alla {version}',
        'update_title': 'Glowback {version} è disponibile',
        'update_text': 'Fai clic qui per scaricarlo.',
        'ha_setup': 'Configura',
        'ha_connected': 'Connesso',
        'ha_connecting': 'Connessione…',
        'ha_error': 'Non connesso',
        'ha_intro': "Glowback compare in Home Assistant come una luce da comandare dalle dashboard, dalle automazioni e da Google Assistant. Si collega tramite MQTT: installa l'app Mosquitto broker in Home Assistant, poi accedi qui con un utente di Home Assistant.",
        'ha_guide': 'Guida passo passo',
        'ha_address': 'Indirizzo',
        'ha_port': 'Porta',
        'ha_user': 'Utente',
        'ha_password': 'Password',
        'ha_user_hint': 'Utente di Home Assistant',
        'ha_password_saved': 'Salvata',
        'ha_connect': 'Connetti',
        'ha_cancel': 'Annulla',
        'ha_disconnect': 'Disconnetti',
        'ha_testing': 'Connessione a Home Assistant…',
        'ha_need_address': "Inserisci l'indirizzo di Home Assistant.",
        'ha_err_address': 'Questo indirizzo non è stato trovato nella tua rete.',
        'ha_err_broker': "Nessun broker MQTT risponde a questo indirizzo. L'app Mosquitto broker è avviata?",
        'ha_err_login': 'Utente o password errati.',
        'ha_err_refused': 'Il broker MQTT ha rifiutato la connessione.',
        'ha_err_tls': 'La connessione sicura non è riuscita.',
        'ha_err_other': 'Connessione non riuscita ({error}).',
        'ha_done_title': 'Connesso a Home Assistant',
        'ha_done_text': 'Glowback è in Impostazioni › Dispositivi e servizi › MQTT.',
        'open_app': 'Apri Glowback',
        'nav_home': 'Home Assistant',
        'nav_light': 'Luce ambientale',
        'nav_settings': 'Impostazioni',
        'nav_about': 'Informazioni',
        'app_quit': 'Esci da Glowback',
        'app_background': "Glowback continua in background. Fai clic sulla sua icona accanto all'orologio per tornare.",
        'mode_zones_desc': "Ogni LED prende i colori dell'immagine proprio accanto a sé.",
        'mode_average_desc': 'Tutti i LED mostrano il colore medio dello schermo.',
        'sync_now_paused': 'La luce ambientale è in pausa.',
        'sync_app': 'App',
        'sync_when_label': 'Quando',
        'sync_screen': 'Schermo',
        'sync_any_app': 'Qualsiasi app',
        'sync_open_apps': 'App aperte',
        'sync_browse': 'Altro programma…',
        'sync_running': 'È aperta',
        'sync_foreground': 'È in primo piano',
        'sync_fullscreen': 'È a schermo intero',
        'sync_any_screen': 'Qualsiasi schermo',
        'sync_led_screen': 'Lo schermo dei LED',
        'sync_screen_n': 'Schermo {n}',
        'sync_add': 'Aggiungi',
        'sync_remove': 'Rimuovi',
        'sync_programs': 'Programmi',
        'home_sub': 'Comanda la luce ambientale da Home Assistant, dalle sue automazioni e dal tuo assistente vocale.',
        'nav_matter': 'Apple e Google',
        'matter_apple_home': 'Apple Casa',
        'matter_title': 'Apple Casa, Google Home e Alexa',
        'matter_sub': 'Comanda la luce ambientale dal telefono con Matter: Glowback appare come una luce in Apple Casa, Google Home, Alexa o SmartThings, senza Home Assistant.',
        'matter_toggle': 'Luce Matter',
        'matter_off_desc': 'Spenta: i telefoni non vedono Glowback',
        'matter_failed': 'Avvio non riuscito: vedi il log',
        'matter_on_count': 'Attiva · app associate: {n}',
        'matter_on_none': "Attiva · pronta per l'associazione",
        'matter_pair': 'Associa',
        'matter_scan_title': 'Scansiona con il telefono',
        'matter_scan': 'In Apple Casa, Google Home o Alexa aggiungi un accessorio o un dispositivo Matter, poi scansiona questo codice. Oppure digitalo:',
        'matter_open_for': 'Associazione aperta ancora {min} min',
        'matter_stop': 'Interrompi',
        'matter_other_app': "Un'altra app viene aggiunta a Glowback: continua in quell'app (ancora {min} min).",
        'matter_closed_desc': "Apri l'associazione per 15 minuti per aggiungere Glowback ad Apple Casa, Google Home, Alexa o un'altra app Matter. Già associata? Aggiungi l'app successiva allo stesso modo.",
        'matter_open': 'Associa un telefono',
        'matter_paired': 'App associate',
        'matter_paired_desc': 'Può accendere la luce e cambiarne luminosità e colore',
        'matter_none': 'Ancora nessun telefono né app.',
        'matter_remove': 'Rimuovi',
        'matter_remove_ask': "Rimuovere Glowback da {app}? Quell'app non potrà più comandare la luce.",
        'matter_good_to_know': 'Da sapere',
        'matter_notes': 'Glowback è una luce Matter non certificata: Apple Casa chiede di confermare (Aggiungi comunque), Google Home richiede prima una configurazione di prova gratuita. Telefono e PC devono essere sulla stessa rete; se Windows lo chiede, consenti Glowback.',
        'matter_controller': 'App Matter',
        'home_connected': 'Connesso a {host}',
        'home_not_set': 'Non configurato',
        'home_not_set_desc': "Installa l'app Mosquitto broker in Home Assistant, poi collega Glowback.",
        'home_connected_desc': 'Glowback è in Impostazioni › Dispositivi e servizi › MQTT.',
        'home_setup': 'Configura',
        'home_change': 'Modifica',
        'home_entities': 'In Home Assistant',
        'home_voice': 'Assistenti vocali',
        'home_voice_text': "Google Assistant e Alexa funzionano tramite Home Assistant, Siri e l'app Casa con la sua integrazione HomeKit Bridge.",
        'settings_sub': 'Avvio, aggiornamenti e lingua.',
        'settings_sub_store': 'Avvio e lingua.',
        'settings_start_desc': "Glowback si avvia in background all'accesso.",
        'startup_store_desc': 'Attiva o disattiva Glowback nelle app di avvio di Windows.',
        'settings_updates': 'Aggiornamenti',
        'settings_check_desc': 'Una volta al giorno, Glowback chiede a GitHub se è uscita una nuova versione.',
        'settings_check_now': 'Controlla',
        'settings_new': 'Glowback {version} è disponibile',
        'settings_lang': 'Lingua',
        'settings_lang_label': "Lingua dell'interfaccia",
        'lang_auto': 'Lingua di Windows',
        'settings_help': 'Aiuto',
        'settings_log_desc': 'Cosa ha fatto Glowback, per capire un problema.',
        'settings_open': 'Apri',
        'about_tagline': 'Luce ambientale per monitor con LED RGB sul retro.',
        'about_version': 'Versione {version}',
        'about_site': 'Sito web',
        'about_source': 'Codice sorgente e guida',
        'about_issue': 'Segnala un problema',
        'about_license': 'Libero e open source, licenza MIT.',
        'nav_profiles': 'Profili',
        'profiles_sub': "Cambia atmosfera in base all'ora, all'app in primo piano o al suono che si sente. Il resto del tempo vale la pagina Luce ambientale.",
        'light_sub': "Cosa mostrano i LED dietro lo schermo: l'immagine, un colore, una sfumatura o la tua musica.",
        'mode_zones': 'Schermo',
        'mode_average': 'Media',
        'mode_color': 'Colore',
        'mode_gradient': 'Sfumatura',
        'mode_music': 'Musica',
        'color_hue': 'Tonalità',
        'color_sat': 'Saturazione',
        'color_red': 'Rosso',
        'color_orange': 'Arancione',
        'color_yellow': 'Giallo',
        'color_green': 'Verde',
        'color_cyan': 'Ciano',
        'color_blue': 'Blu',
        'color_purple': 'Viola',
        'color_pink': 'Rosa',
        'color_warm': 'Bianco caldo',
        'color_white': 'Bianco',
        'gradient_sunset': 'Tramonto',
        'gradient_ocean': 'Oceano',
        'gradient_aurora': 'Aurora',
        'gradient_neon': 'Neon',
        'gradient_ember': 'Brace',
        'gradient_forest': 'Foresta',
        'gradient_presets': 'Modelli',
        'gradient_flow': 'Scorrimento',
        'gradient_flow_desc': 'La sfumatura scorre lentamente sui LED',
        'style_pulse': 'Pulsazione',
        'style_spectrum': 'Spettro',
        'style_wave': 'Onde',
        'style_pulse_desc': 'Tutti i LED battono al ritmo della musica.',
        'style_spectrum_desc': 'Ogni LED segue le sue note: bassi in basso, acuti in alto.',
        'style_wave_desc': "Ogni colpo manda un'onda di luce su entrambi i lati dello schermo.",
        'music_style': 'Stile',
        'music_colors': 'Colori',
        'music_sensitivity': 'Sensibilità',
        'music_on': 'I LED seguono ciò che suona il PC. Non viene registrato nulla.',
        'music_silent': 'Nessun suono per ora: fai partire della musica.',
        'palette_rainbow': 'Arcobaleno',
        'palette_screen': 'Colori dello schermo',
        'palette_color': 'Il mio colore',
        'palette_gradient': 'La mia sfumatura',
        'now_base': 'Nessun profilo ora: vale la pagina Luce ambientale.',
        'now_night': 'Profilo notturno fino alle {end}: {look}, luminosità {brightness} %.',
        'now_app': '{rule}: {look}.',
        'now_rest': 'Nessuna delle tue app: {look}.',
        'night_title': 'Giorno e notte',
        'night_profile': 'Profilo notturno',
        'night_desc': 'Dalle {start} alle {end}, una luce più morbida',
        'night_hours': 'Orari',
        'night_brightness': 'Luminosità di notte',
        'night_look': 'Atmosfera di notte',
        'night_same': 'Come di giorno',
        'night_short': 'Notte',
        'apps_title': 'Per app',
        'apps_empty': 'Ancora nessuna app: aggiungine una qui sotto.',
        'apps_add': "Aggiungi un'app",
        'apps_examples': 'Per esempio: la musica quando Spotify riproduce suono, lo schermo per i giochi a schermo intero, il blu quando Visual Studio Code è in primo piano.',
        'rest_title': 'Il resto del tempo',
        'rest_desc': 'Quando nessuna di queste app corrisponde',
        'look_label': 'Atmosfera',
        'look_auto': 'Auto: la pagina Luce ambientale',
        'look_auto_short': 'Auto',
        'look_device': 'Effetto proprio dei LED',
        'look_off': 'LED spenti',
        'sync_playing': 'Riproduce suono',
        'profiles_none': 'Nessuno',
        'profiles_one': '1 profilo',
        'profiles_many': '{n} profili',
        'profiles_none_long': 'Nessuno: le impostazioni qui sopra valgono sempre',
        'profiles_apps_one': '1 app',
        'profiles_apps': '{n} app',
        'profiles_now': 'ora {name}',
        'state_device': 'Effetto proprio dei LED',
        'state_dark': 'LED spenti',
        'tip_device': 'Glowback: i LED mostrano il loro effetto',
        'home_leds_title': 'Numero di LED',
        'home_update_title': 'Aggiornamenti',
        'home_light': 'Accendila o spegnila, regola luminosità, colore e modalità',
        'home_leds': 'Quanti LED gestisce Glowback in questo momento',
        'home_update': 'Le nuove versioni di Glowback, installate da Home Assistant',
    },
    'pt': {
        'update_downloading': 'Baixando o Glowback {version}…',
        'update_installing': 'Instalando a atualização. O Glowback vai reiniciar sozinho.',
        'update_failed': 'Não foi possível instalar a atualização ({error}). Abrindo a página de download.',
        'start_windows': 'Iniciar com o Windows',
        'mode': 'Modo',
        'zones': 'Cada LED segue sua zona',
        'average': 'Uma única cor média',
        'brightness': 'Brilho',
        'made_by': 'Criado por {author}',
        'star': 'Dar uma estrela no GitHub',
        'open_log': 'Abrir log',
        'quit': 'Sair',
        'by': 'por {author}',
        'tip_on': 'Glowback: luz ambiente ativa',
        'tip_off': 'Glowback: pausado',
        'balloon_title': 'Glowback está em execução',
        'balloon_text': 'Clique com o botão direito neste ícone para pausar, mudar o modo ou o brilho, ou sair.',
        'already': 'Glowback já está em execução: procure o ícone ao lado do relógio.',
        'pausing': 'Pausando o Glowback por um momento...',
        'restarted': 'Glowback foi reiniciado em segundo plano.',
        'press_enter': 'Pressione Enter para fechar esta janela...',
        'test_intro': 'Olhe para a parede atrás da tela:',
        'test_white': 'todos os LEDs em BRANCO',
        'test_lr': 'ESQUERDA = VERMELHO, DIREITA = AZUL (visto do seu lugar; se estiver invertido, use --mirror)',
        'test_tb': 'EM CIMA = VERDE, EMBAIXO = AMARELO (se estiver invertido, use --flip)',
        'test_rainbow': 'arco-íris girando pelos LEDs',
        'test_done': 'Pronto, os LEDs voltaram ao dispositivo.',
        'no_device': 'Nenhum dispositivo de Iluminação dinâmica encontrado (glowback --list).',
        'cal_intro': 'Balanço de branco: ajuste até a luz na parede parecer de um branco neutro.',
        'cal_keys1': '  r / R  menos / mais vermelho     g / G  verde     b / B  azul',
        'cal_keys2': '  1 2 3 4  teste a 100 / 50 / 25 / 10 %     Enter  salvar     Esc  pular este dispositivo',
        'cal_state': '  vermelho {r:.2f}   verde {g:.2f}   azul {b:.2f}   (nível {level:.0%})   ',
        'cal_saved': 'salvo.',
        'cal_skipped': 'pulado.',
        'cal_restart': 'Reinicie o Glowback (ou ele aplicará na próxima inicialização).',
        'ambilight': 'Luz ambiente',
        'state_on': 'Ativo · {leds} LEDs',
        'state_paused': 'Pausado',
        'state_none': 'Procurando LEDs…',
        'about': 'Sobre',
        'updates': 'Verificar atualizações',
        'auto_check': 'Verificar automaticamente',
        'up_to_date': 'Atualizado',
        'check_failed': 'Falhou',
        'update_to': 'Atualizar para {version}',
        'update_title': 'Glowback {version} está disponível',
        'update_text': 'Clique aqui para baixar.',
        'ha_setup': 'Configurar',
        'ha_connected': 'Conectado',
        'ha_connecting': 'Conectando…',
        'ha_error': 'Desconectado',
        'ha_intro': 'O Glowback aparece no Home Assistant como uma luz que você controla pelos painéis, pelas automações e pelo Google Assistente. A conexão é feita por MQTT: instale o app Mosquitto broker no Home Assistant e entre aqui com um usuário do Home Assistant.',
        'ha_guide': 'Guia passo a passo',
        'ha_address': 'Endereço',
        'ha_port': 'Porta',
        'ha_user': 'Usuário',
        'ha_password': 'Senha',
        'ha_user_hint': 'Usuário do Home Assistant',
        'ha_password_saved': 'Salva',
        'ha_connect': 'Conectar',
        'ha_cancel': 'Cancelar',
        'ha_disconnect': 'Desconectar',
        'ha_testing': 'Conectando ao Home Assistant…',
        'ha_need_address': 'Informe o endereço do Home Assistant.',
        'ha_err_address': 'Este endereço não foi encontrado na sua rede.',
        'ha_err_broker': 'Nenhum broker MQTT responde neste endereço. O app Mosquitto broker está iniciado?',
        'ha_err_login': 'Usuário ou senha incorretos.',
        'ha_err_refused': 'O broker MQTT recusou a conexão.',
        'ha_err_tls': 'A conexão segura falhou.',
        'ha_err_other': 'A conexão falhou ({error}).',
        'ha_done_title': 'Conectado ao Home Assistant',
        'ha_done_text': 'O Glowback está em Configurações › Dispositivos e serviços › MQTT.',
        'open_app': 'Abrir o Glowback',
        'nav_home': 'Home Assistant',
        'nav_light': 'Luz ambiente',
        'nav_settings': 'Configurações',
        'nav_about': 'Sobre',
        'app_quit': 'Sair do Glowback',
        'app_background': 'O Glowback continua em segundo plano. Clique no ícone dele ao lado do relógio para voltar.',
        'mode_zones_desc': 'Cada LED pega as cores da imagem bem ao lado dele.',
        'mode_average_desc': 'Todos os LEDs mostram a cor média da tela.',
        'sync_now_paused': 'A luz ambiente está pausada.',
        'sync_app': 'App',
        'sync_when_label': 'Quando',
        'sync_screen': 'Tela',
        'sync_any_app': 'Qualquer app',
        'sync_open_apps': 'Apps abertos',
        'sync_browse': 'Outro programa…',
        'sync_running': 'Está aberto',
        'sync_foreground': 'Está em primeiro plano',
        'sync_fullscreen': 'Está em tela cheia',
        'sync_any_screen': 'Qualquer tela',
        'sync_led_screen': 'A tela dos LEDs',
        'sync_screen_n': 'Tela {n}',
        'sync_add': 'Adicionar',
        'sync_remove': 'Remover',
        'sync_programs': 'Programas',
        'home_sub': 'Controle a luz ambiente pelo Home Assistant, pelas automações dele e pelo seu assistente de voz.',
        'nav_matter': 'Apple e Google',
        'matter_apple_home': 'Apple Casa',
        'matter_title': 'Apple Casa, Google Home e Alexa',
        'matter_sub': 'Controle a luz ambiente pelo celular com Matter: o Glowback aparece como uma luz no app Casa, no Google Home, na Alexa ou no SmartThings, sem Home Assistant.',
        'matter_toggle': 'Luz Matter',
        'matter_off_desc': 'Desligada: os celulares não veem o Glowback',
        'matter_failed': 'Não foi possível iniciar: veja o log',
        'matter_on_count': 'Ligada · apps pareados: {n}',
        'matter_on_none': 'Ligada · pronta para parear',
        'matter_pair': 'Parear',
        'matter_scan_title': 'Escaneie com o celular',
        'matter_scan': 'No app Casa, no Google Home ou na Alexa, adicione um acessório ou dispositivo Matter e escaneie este código. Ou digite:',
        'matter_open_for': 'Pareamento aberto por mais {min} min',
        'matter_stop': 'Parar',
        'matter_other_app': 'Outro app está sendo adicionado ao Glowback: continue nesse app (faltam {min} min).',
        'matter_closed_desc': 'Abra o pareamento por 15 minutos para adicionar o Glowback ao app Casa, ao Google Home, à Alexa ou a outro app Matter. Já pareado? Adicione o próximo app do mesmo jeito.',
        'matter_open': 'Parear um celular',
        'matter_paired': 'Apps pareados',
        'matter_paired_desc': 'Pode ligar a luz e mudar o brilho e a cor',
        'matter_none': 'Nenhum celular ou app ainda.',
        'matter_remove': 'Remover',
        'matter_remove_ask': 'Remover o Glowback do {app}? Esse app não vai mais controlar a luz.',
        'matter_good_to_know': 'Bom saber',
        'matter_notes': 'O Glowback é uma luz Matter não certificada: o app Casa pede para confirmar (Adicionar Mesmo Assim) e o Google Home precisa antes de uma configuração de teste gratuita. O celular e este PC precisam estar na mesma rede; se o Windows perguntar, permita o Glowback.',
        'matter_controller': 'App Matter',
        'home_connected': 'Conectado a {host}',
        'home_not_set': 'Não configurado',
        'home_not_set_desc': 'Instale o app Mosquitto broker no Home Assistant e conecte o Glowback a ele.',
        'home_connected_desc': 'O Glowback está em Configurações › Dispositivos e serviços › MQTT.',
        'home_setup': 'Configurar',
        'home_change': 'Alterar',
        'home_entities': 'No Home Assistant',
        'home_voice': 'Assistentes de voz',
        'home_voice_text': 'O Google Assistente e a Alexa funcionam pelo Home Assistant, a Siri e o app Casa pela integração HomeKit Bridge dele.',
        'settings_sub': 'Inicialização, atualizações e idioma.',
        'settings_sub_store': 'Inicialização e idioma.',
        'settings_start_desc': 'O Glowback inicia em segundo plano quando você entra no Windows.',
        'startup_store_desc': 'Ative ou desative o Glowback nos aplicativos de inicialização do Windows.',
        'settings_updates': 'Atualizações',
        'settings_check_desc': 'Uma vez por dia, o Glowback pergunta ao GitHub se saiu uma nova versão.',
        'settings_check_now': 'Verificar',
        'settings_new': 'O Glowback {version} está disponível',
        'settings_lang': 'Idioma',
        'settings_lang_label': 'Idioma da interface',
        'lang_auto': 'Idioma do Windows',
        'settings_help': 'Ajuda',
        'settings_log_desc': 'O que o Glowback fez, para entender um problema.',
        'settings_open': 'Abrir',
        'about_tagline': 'Luz ambiente para monitores com LEDs RGB na traseira.',
        'about_version': 'Versão {version}',
        'about_site': 'Site',
        'about_source': 'Código-fonte e guia',
        'about_issue': 'Relatar um problema',
        'about_license': 'Livre e de código aberto, licença MIT.',
        'nav_profiles': 'Perfis',
        'profiles_sub': 'Mude o clima conforme a hora, o app em primeiro plano ou o som que toca. No resto do tempo, vale a página Luz ambiente.',
        'light_sub': 'O que os LEDs atrás da sua tela mostram: a imagem, uma cor, um degradê ou a sua música.',
        'mode_zones': 'Tela',
        'mode_average': 'Média',
        'mode_color': 'Cor',
        'mode_gradient': 'Degradê',
        'mode_music': 'Música',
        'color_hue': 'Matiz',
        'color_sat': 'Saturação',
        'color_red': 'Vermelho',
        'color_orange': 'Laranja',
        'color_yellow': 'Amarelo',
        'color_green': 'Verde',
        'color_cyan': 'Ciano',
        'color_blue': 'Azul',
        'color_purple': 'Roxo',
        'color_pink': 'Rosa',
        'color_warm': 'Branco quente',
        'color_white': 'Branco',
        'gradient_sunset': 'Pôr do sol',
        'gradient_ocean': 'Oceano',
        'gradient_aurora': 'Aurora',
        'gradient_neon': 'Neon',
        'gradient_ember': 'Brasa',
        'gradient_forest': 'Floresta',
        'gradient_presets': 'Modelos',
        'gradient_flow': 'Movimento',
        'gradient_flow_desc': 'O degradê desliza devagar pelos LEDs',
        'style_pulse': 'Pulso',
        'style_spectrum': 'Espectro',
        'style_wave': 'Ondas',
        'style_pulse_desc': 'Todos os LEDs pulsam no ritmo da música.',
        'style_spectrum_desc': 'Cada LED segue as suas notas: graves embaixo, agudos em cima.',
        'style_wave_desc': 'Cada batida manda uma onda de luz pelos dois lados da tela.',
        'music_style': 'Estilo',
        'music_colors': 'Cores',
        'music_sensitivity': 'Sensibilidade',
        'music_on': 'Os LEDs seguem o que o seu PC toca. Nada é gravado.',
        'music_silent': 'Nenhum som agora: coloque uma música.',
        'palette_rainbow': 'Arco-íris',
        'palette_screen': 'Cores da tela',
        'palette_color': 'Minha cor',
        'palette_gradient': 'Meu degradê',
        'now_base': 'Nenhum perfil agora: vale a página Luz ambiente.',
        'now_night': 'Perfil noturno até {end}: {look}, brilho {brightness} %.',
        'now_app': '{rule}: {look}.',
        'now_rest': 'Nenhum dos seus apps: {look}.',
        'night_title': 'Dia e noite',
        'night_profile': 'Perfil noturno',
        'night_desc': 'Das {start} às {end}, uma luz mais suave',
        'night_hours': 'Horário',
        'night_brightness': 'Brilho à noite',
        'night_look': 'Clima à noite',
        'night_same': 'Igual ao dia',
        'night_short': 'Noite',
        'apps_title': 'Por app',
        'apps_empty': 'Nenhum app ainda: adicione um abaixo.',
        'apps_add': 'Adicionar um app',
        'apps_examples': 'Por exemplo: a música quando o Spotify toca som, a tela para jogos em tela cheia, azul quando o Visual Studio Code está em primeiro plano.',
        'rest_title': 'O resto do tempo',
        'rest_desc': 'Quando nenhum desses apps corresponde',
        'look_label': 'Clima',
        'look_auto': 'Auto: a página Luz ambiente',
        'look_auto_short': 'Auto',
        'look_device': 'Efeito próprio dos LEDs',
        'look_off': 'LEDs apagados',
        'sync_playing': 'Toca som',
        'profiles_none': 'Nenhum',
        'profiles_one': '1 perfil',
        'profiles_many': '{n} perfis',
        'profiles_none_long': 'Nenhum: as configurações acima valem sempre',
        'profiles_apps_one': '1 app',
        'profiles_apps': '{n} apps',
        'profiles_now': 'agora {name}',
        'state_device': 'Efeito próprio dos LEDs',
        'state_dark': 'LEDs apagados',
        'tip_device': 'Glowback: os LEDs mostram o próprio efeito',
        'home_leds_title': 'Número de LEDs',
        'home_update_title': 'Atualizações',
        'home_light': 'Ligue ou desligue, ajuste o brilho, a cor e o modo',
        'home_leds': 'Quantos LEDs o Glowback controla agora',
        'home_update': 'As novas versões do Glowback, instaladas pelo Home Assistant',
    },
}
LANGS = tuple(STRINGS)
_lang = {"code": "en"}


def detect_lang():
    """Windows display language -> one of LANGS (English otherwise)."""
    try:
        primary = k32.GetUserDefaultUILanguage() & 0x3FF
    except (OSError, AttributeError):
        return "en"
    return {0x09: "en", 0x0C: "fr", 0x0A: "es", 0x07: "de", 0x10: "it", 0x16: "pt"}.get(primary, "en")


def set_lang(code):
    _lang["code"] = code if code in STRINGS else "en"


def tr(key, **kw):
    text = STRINGS[_lang["code"]].get(key) or STRINGS["en"][key]
    return text.format(**kw) if kw else text


# =============================================================================
# Windows integration: settings, icon, autostart, Start menu, tray icon
# =============================================================================
SETTINGS_PATH = os.path.join(LOG_DIR, "settings.json")
START_MENU_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs", "Glowback.lnk")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_SETTINGS = "ms-settings:startupapps"  # where the Store version's start with Windows is turned on or off
REPO_URL = "https://github.com/Ilyomix/glowback"
AUTHOR, AUTHOR_URL = "Ilyomix", "https://github.com/Ilyomix"


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


_settings_lock = threading.Lock()  # the panel and Home Assistant can both change settings


def save_settings(data):
    """Merge `data` into settings.json."""
    with _settings_lock:
        try:
            merged = load_settings()
            merged.update(data)
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=1)
        except OSError:
            pass


def store_first_run():
    """First start of the Store version: it keeps the settings and the Matter pairings of a Glowback installed before
    (GlowbackSetup.exe, portable, pip), so the light stays in the phone's Home app."""
    if not PACKAGE or os.path.exists(SETTINGS_PATH):
        return
    import shutil
    os.makedirs(LOG_DIR, exist_ok=True)
    for name in ("settings.json", "matter.json"):
        try:
            shutil.copyfile(os.path.join(LOCAL_APPDATA, "Glowback", name), os.path.join(LOG_DIR, name))
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
        here = os.path.dirname(sys.executable)
        for gui in ("Glowback.exe", "GlowbackTray.exe"):  # installer / portable tray app next to this exe
            if os.path.exists(os.path.join(here, gui)):
                return [os.path.join(here, gui), "--background", *extra]
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
              f"$s.IconLocation={q(icon)};$s.Description={q('Glowback - ambient light for your monitor RGB LEDs')};$s.Save()")
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
    try:
        ha_forget_now()  # remove Glowback from Home Assistant before its settings go
    except Exception as e:
        log(f"Home Assistant: not removed ({e!r})")
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


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", HANDLE), ("uCallbackMessage", wt.UINT), ("uEdge", wt.UINT),
                ("rc", wt.RECT), ("lParam", wt.LPARAM)]


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
_sig(user32.AppendMenuW, wt.BOOL, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_void_p)  # owner-drawn: item data
_sig(user32.TrackPopupMenu, ctypes.c_int, HANDLE, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, HANDLE, ctypes.c_void_p)
_sig(user32.DestroyMenu, wt.BOOL, HANDLE)
_sig(user32.GetCursorPos, wt.BOOL, ctypes.POINTER(wt.POINT))
_sig(user32.SetForegroundWindow, wt.BOOL, HANDLE)
_sig(user32.RegisterWindowMessageW, wt.UINT, wt.LPCWSTR)
_sig(user32.LoadImageW, HANDLE, HANDLE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT)
_sig(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
_sig(user32.DestroyIcon, wt.BOOL, HANDLE)
_sig(shell32.Shell_NotifyIconW, wt.BOOL, wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_sig(shell32.SHAppBarMessage, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(APPBARDATA))
_sig(user32.MonitorFromRect, HANDLE, ctypes.POINTER(wt.RECT), wt.DWORD)
_sig(k32.GetModuleHandleW, HANDLE, wt.LPCWSTR)
_sig(user32.LoadCursorW, HANDLE, HANDLE, ctypes.c_void_p)
_sig(user32.GetClientRect, wt.BOOL, HANDLE, ctypes.POINTER(wt.RECT))
_sig(user32.MessageBoxW, ctypes.c_int, HANDLE, wt.LPCWSTR, wt.LPCWSTR, wt.UINT)


# ---- custom-drawn tray menu: dark, Inter, toggle switches (owner-drawn Win32 menu + GDI+)
gdiplus = ctypes.WinDLL("gdiplus")
dwmapi = ctypes.WinDLL("dwmapi")


class MEASUREITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", wt.UINT), ("CtlID", wt.UINT), ("itemID", wt.UINT), ("itemWidth", wt.UINT),
                ("itemHeight", wt.UINT), ("itemData", ctypes.c_size_t)]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", wt.UINT), ("CtlID", wt.UINT), ("itemID", wt.UINT), ("itemAction", wt.UINT),
                ("itemState", wt.UINT), ("hwndItem", HANDLE), ("hDC", HANDLE), ("rcItem", wt.RECT),
                ("itemData", ctypes.c_size_t)]


class MENUINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("fMask", wt.DWORD), ("dwStyle", wt.DWORD), ("cyMax", wt.UINT),
                ("hbrBack", HANDLE), ("dwContextHelpID", wt.DWORD), ("dwMenuData", ctypes.c_size_t)]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wt.BOOL), ("SuppressExternalCodecs", wt.BOOL)]


F = ctypes.c_float
_sig(gdi32.AddFontMemResourceEx, HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, ctypes.POINTER(wt.DWORD))
_sig(gdi32.CreateFontW, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.DWORD,
     wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR)
_sig(gdi32.SetTextColor, wt.DWORD, HANDLE, wt.DWORD)
_sig(gdi32.SetBkMode, ctypes.c_int, HANDLE, ctypes.c_int)
_sig(gdi32.CreateSolidBrush, HANDLE, wt.DWORD)
_sig(gdi32.GetTextExtentPoint32W, wt.BOOL, HANDLE, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE))
_sig(gdi32.ExcludeClipRect, ctypes.c_int, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(user32.FillRect, ctypes.c_int, HANDLE, ctypes.POINTER(wt.RECT), HANDLE)
_sig(user32.DrawTextW, ctypes.c_int, HANDLE, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT)
_sig(user32.SetMenuInfo, wt.BOOL, HANDLE, ctypes.POINTER(MENUINFO))
_sig(user32.DrawIconEx, wt.BOOL, HANDLE, ctypes.c_int, ctypes.c_int, HANDLE, ctypes.c_int, ctypes.c_int, wt.UINT,
     HANDLE, wt.UINT)
_sig(dwmapi.DwmSetWindowAttribute, ctypes.c_long, HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD)
_sig(gdiplus.GdiplusStartup, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(GdiplusStartupInput),
     ctypes.c_void_p)
_sig(gdiplus.GdipCreateFromHDC, ctypes.c_int, HANDLE, PVP)
_sig(gdiplus.GdipSetSmoothingMode, ctypes.c_int, VP, ctypes.c_int)
_sig(gdiplus.GdipSetPixelOffsetMode, ctypes.c_int, VP, ctypes.c_int)
_sig(gdiplus.GdipDeleteGraphics, ctypes.c_int, VP)
_sig(gdiplus.GdipCreateSolidFill, ctypes.c_int, ctypes.c_uint32, PVP)
_sig(gdiplus.GdipDeleteBrush, ctypes.c_int, VP)
_sig(gdiplus.GdipFillEllipse, ctypes.c_int, VP, VP, F, F, F, F)
_sig(gdiplus.GdipCreatePath, ctypes.c_int, ctypes.c_int, PVP)
_sig(gdiplus.GdipAddPathArc, ctypes.c_int, VP, F, F, F, F, F, F)
_sig(gdiplus.GdipClosePathFigure, ctypes.c_int, VP)
_sig(gdiplus.GdipFillPath, ctypes.c_int, VP, VP, VP)
_sig(gdiplus.GdipDeletePath, ctypes.c_int, VP)
_sig(gdiplus.GdipCreatePen1, ctypes.c_int, ctypes.c_uint32, F, ctypes.c_int, PVP)
_sig(gdiplus.GdipSetPenStartCap, ctypes.c_int, VP, ctypes.c_int)
_sig(gdiplus.GdipSetPenEndCap, ctypes.c_int, VP, ctypes.c_int)
_sig(gdiplus.GdipDrawArc, ctypes.c_int, VP, VP, F, F, F, F, F, F)
_sig(gdiplus.GdipDeletePen, ctypes.c_int, VP)
try:
    _sig(user32.GetDpiForWindow, wt.UINT, HANDLE)
except AttributeError:
    pass

_ui = {"face": None, "fonts": [], "gdip": None}


def ui_font_face():
    """Register the embedded Inter (private to this process); fall back to Segoe UI."""
    if _ui["face"] is None:
        _ui["face"] = "Segoe UI"
        try:
            import base64
            import zlib
            for parts in INTER_FONTS:
                data = zlib.decompress(base64.b64decode("".join(parts)))
                buf = ctypes.create_string_buffer(data, len(data))
                n = wt.DWORD()
                if gdi32.AddFontMemResourceEx(buf, len(data), None, byref(n)):
                    _ui["fonts"].append(buf)
                    _ui["face"] = "Glowback Inter"
        except Exception:
            pass
    return _ui["face"]


def icon_font_face():
    """Windows' own icon font: Segoe Fluent Icons (Windows 11) or Segoe MDL2 Assets (Windows 10)."""
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return "Segoe Fluent Icons" if os.path.exists(os.path.join(fonts, "SegoeIcons.ttf")) else "Segoe MDL2 Assets"


def _gdip_start():
    if _ui["gdip"] is None:
        token, inp = ctypes.c_size_t(), GdiplusStartupInput(1, None, False, False)
        _ui["gdip"] = gdiplus.GdiplusStartup(byref(token), byref(inp), None) == 0
    return _ui["gdip"]


def _cref(rgb):  # 0xRRGGBB -> Win32 COLORREF (0x00BBGGRR)
    return ((rgb >> 16) & 0xFF) | (rgb & 0xFF00) | ((rgb & 0xFF) << 16)


class MenuPainter:
    """Draws the tray menu: header with live status, icons, radio buttons, switches, sections."""
    BG, HOVER, TEXT, MUTED, ICON = 0x141519, 0x23252E, 0xECEEF3, 0x8C91A1, 0xC5C9D4
    ACCENT, LINE, OFF, RING, LABEL = 0x8B6CFF, 0x2B2D38, 0x3A3D49, 0x5B5F6E, 0x9D86FF
    GREEN, AMBER = 0x3DDC97, 0xF5B83D
    HEIGHTS = {"header": 64, "sep": 13, "label": 30}
    ICONS = {"light": "", "power": "", "sync": "", "monitor": "", "palette": "",
             "sun": "", "person": "", "star": "", "doc": "", "close": "",
             "link": ""}
    ICONS.update(dismiss="", quit="", check="", warning="", clock="")
    ICONS.update(home="")
    ICONS.update(phone="", qr="")  # CellPhone, QRCode
    ICONS.update(filter="", settings="", info="", chev_down="", chev_right="",
                 delete="", globe="", code="", bug="", window="", add="",
                 lang="", mic="", apps="", pause="", search="")

    ICONS.update(moon="", drop="", gradient="", music="", pulse="",
                 spectrum="", wave="", layers="", minus="", chev_left="",
                 volume="", sparkle="", bulb="", flow="", arrow="")

    def __init__(self, scale, icon):
        self.k, self.icon = scale, icon
        face = ui_font_face()
        mk = lambda px, weight, f=face: gdi32.CreateFontW(-round(px * scale), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, f)
        self.f_text, self.f_title, self.f_small, self.f_label = mk(13.5, 400), mk(15, 600), mk(12, 400), mk(11, 600)
        self.f_icon, self.f_link = mk(16, 400, icon_font_face()), mk(12, 400, icon_font_face())
        self.f_chev = mk(17, 400)
        self.f_close = mk(10, 400, icon_font_face())
        self.bg_brush = gdi32.CreateSolidBrush(_cref(self.BG))
        self.line_brush = gdi32.CreateSolidBrush(_cref(self.LINE))
        self.mdc = gdi32.CreateCompatibleDC(None)  # for measuring text
        self.gdip = _gdip_start()
        self.styled = set()

    def close(self):
        for h in (self.f_text, self.f_title, self.f_small, self.f_label, self.f_icon, self.f_link, self.f_chev,
                  self.f_close, self.bg_brush, self.line_brush):
            gdi32.DeleteObject(h)
        gdi32.DeleteDC(self.mdc)

    def px(self, v):
        return round(v * self.k)

    def text_width(self, text, font):
        gdi32.SelectObject(self.mdc, font)
        size = wt.SIZE()
        gdi32.GetTextExtentPoint32W(self.mdc, text, len(text), byref(size))
        return size.cx

    def measure(self, mis, it):
        p, kind = self.px, it["kind"]
        mis.itemHeight = p(self.HEIGHTS.get(kind, 34))
        if kind == "sep":
            w = 0
        elif kind == "header":  # icon, name + version over the status, close button
            title = self.text_width("Glowback", self.f_title) + p(7) + self.text_width(f"v{__version__}", self.f_small)
            w = p(56) + max(title, p(14) + self.text_width(it["status"], self.f_small)) + p(16 + 32 + 8)
        elif kind == "label":
            w = p(18 + 16) + self.text_width(it["text"].upper(), self.f_label)
        else:
            left = p(46) if it.get("icon") or "swatch" in it or "stops" in it else p(18)
            w = left + self.text_width(it["text"], self.f_text) + self.right_space(it) + p(8)
        mis.itemWidth = max(w, p(it.get("min", 232)))

    def right_space(self, it):
        """Room kept on the right of the label for the item's control (switch, radio, value, link)."""
        p, kind = self.px, it["kind"]
        if kind == "toggle":
            return p(16 + 34 + 14)
        if kind == "radio":
            return p(16 + 16 + 14)
        if kind == "submenu":
            return p(16 + 16 + 12) + self.text_width(it.get("value", ""), self.f_small)
        if kind == "segments":
            return p(16 + 12) + len(it["values"]) * p(it.get("seg_w", 44)) + (len(it["values"]) - 1) * p(3)
        if it.get("statuses"):  # room for the loader, or the widest result with its glyph
            return p(16 + 12) + max([p(16)] + [p(17) + self.text_width(t, self.f_small) for t in it["statuses"]])
        return p(16 + 14 + 12) if it.get("link") else p(16)

    def close_rect(self, l, t, r, b):
        """The close button, on the right of the header."""
        size = self.px(32)
        x1, y0 = r - self.px(8), t + (b - t - size) // 2
        return x1 - size, y0, x1, y0 + size

    def segment_rects(self, it, l, t, r, b):
        """(x0, y0, x1, y1) of each choice of a "segments" item, right-aligned in the row."""
        p, n = self.px, len(it["values"])
        w, gap = p(it.get("seg_w", 44)), p(3)
        x = r - p(16) - n * w - (n - 1) * gap
        return [(x + i * (w + gap), t + p(6), x + i * (w + gap) + w, b - p(6)) for i in range(n)]

    def style_window(self, hwnd):
        """Windows 11: dark border and rounded corners on the menu window."""
        if hwnd and hwnd not in self.styled:
            self.styled.add(hwnd)
            border, corner = wt.DWORD(_cref(0x2C2E38)), wt.DWORD(2)
            dwmapi.DwmSetWindowAttribute(hwnd, 34, byref(border), 4)  # DWMWA_BORDER_COLOR
            dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(corner), 4)  # DWMWA_WINDOW_CORNER_PREFERENCE

    def _text(self, hdc, text, font, color, l, t, r, b, flags=0):
        gdi32.SelectObject(hdc, font)
        gdi32.SetTextColor(hdc, _cref(color))
        rc = wt.RECT(int(l), int(t), int(r), int(b))
        user32.DrawTextW(hdc, text, -1, byref(rc), 0x20 | 0x04 | 0x800 | flags)  # SINGLELINE|VCENTER|NOPREFIX

    def _shapes(self, hdc, shapes):
        """Antialiased shapes with GDI+: ("round", color, x, y, w, h, radius) or ("circle", color, x, y, d)."""
        if not self.gdip or not shapes:
            return
        g = VP()
        if gdiplus.GdipCreateFromHDC(hdc, byref(g)):
            return
        gdiplus.GdipSetSmoothingMode(g, 4)
        gdiplus.GdipSetPixelOffsetMode(g, 4)
        for shape in shapes:
            if shape[0] == "hgrad":  # ("hgrad", colors, x, y, w, h, radius): a gradient (look menus)
                gdip_hgrad(g, *shape[1:])
                continue
            if shape[0] == "arc":  # ("arc", color, x, y, d, start, sweep, width): the update loader
                _, color, x, y, d, start, sweep, width = shape
                pen = VP()
                gdiplus.GdipCreatePen1(0xFF000000 | color, width, 2, byref(pen))  # UnitPixel
                gdiplus.GdipSetPenStartCap(pen, 2)  # LineCapRound
                gdiplus.GdipSetPenEndCap(pen, 2)
                gdiplus.GdipDrawArc(g, pen, x, y, d, d, start, sweep)
                gdiplus.GdipDeletePen(pen)
                continue
            brush = VP()
            gdiplus.GdipCreateSolidFill(0xFF000000 | shape[1], byref(brush))
            if shape[0] == "circle":
                _, _, x, y, d = shape
                gdiplus.GdipFillEllipse(g, brush, x, y, d, d)
            else:
                _, _, x, y, w, h, r = shape
                d = max(1.0, min(2 * r, w, h))
                path = VP()
                gdiplus.GdipCreatePath(0, byref(path))
                gdiplus.GdipAddPathArc(path, x, y, d, d, 180, 90)
                gdiplus.GdipAddPathArc(path, x + w - d, y, d, d, 270, 90)
                gdiplus.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0, 90)
                gdiplus.GdipAddPathArc(path, x, y + h - d, d, d, 90, 90)
                gdiplus.GdipClosePathFigure(path)
                gdiplus.GdipFillPath(g, brush, path)
                gdiplus.GdipDeletePath(path)
            gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeleteGraphics(g)

    def draw(self, dis, it):
        hdc, rc, p = dis.hDC, dis.rcItem, self.px
        kind = it["kind"]
        l, t, r, b = rc.left, rc.top, rc.right, rc.bottom
        h = b - t
        user32.FillRect(hdc, byref(rc), self.bg_brush)
        gdi32.SetBkMode(hdc, 1)  # transparent
        hovered = bool(dis.itemState & 0x1) and kind not in ("header", "sep", "label", "segments")
        under = self.HOVER if hovered else self.BG
        shapes = []
        if hovered:
            shapes.append(("round", self.HOVER, l + p(6), t + p(2), r - l - p(12), h - p(4), p(7)))
        if kind == "sep":
            line = wt.RECT(l + p(10), t + h // 2, r - p(10), t + h // 2 + max(1, p(1)))
            user32.FillRect(hdc, byref(line), self.line_brush)
        elif kind == "header":
            d = p(8)
            color = {"on": self.GREEN, "off": self.OFF + 0x202020, "none": self.AMBER}[it["state"]]
            shapes.append(("circle", color, l + p(56), t + h * 0.68 - d / 2, d))
            if it.get("hover_seg") == "close":
                x0, y0, x1, y1 = self.close_rect(l, t, r, b)
                shapes.append(("round", self.HOVER, x0, y0, x1 - x0, y1 - y0, p(6)))
        elif kind == "action" and it.get("busy"):  # loader: an accent arc running around a faint ring
            d, width = p(14), max(1.5, self.k * 1.8)
            x_, y_, now = r - p(16) - d, t + (h - d) / 2, time.monotonic()
            sweep = 40 + 230 * (0.5 - 0.5 * math.cos(now * 2 * math.pi / 1.6))
            shapes += [("arc", self.LINE, x_, y_, d, 0, 360, width),
                       ("arc", self.ACCENT, x_, y_, d, (now * 320) % 360, sweep, width)]
        elif kind == "toggle":
            w_, h_ = p(34), p(19)
            x_, y_ = r - p(16) - w_, t + (h - h_) / 2
            knob = h_ - p(6)
            shapes.append(("round", self.ACCENT if it["on"] else self.OFF, x_, y_, w_, h_, h_ / 2))
            kx = x_ + w_ - knob - p(3) if it["on"] else x_ + p(3)
            shapes.append(("circle", 0xFFFFFF if it["on"] else 0xC8CBD4, kx, y_ + p(3), knob))
        elif kind == "segments":
            segs = self.segment_rects(it, l, t, r, b)
            shapes.append(("round", 0x1E2028, segs[0][0] - p(2), segs[0][1] - p(2), segs[-1][2] - segs[0][0] + p(4),
                           segs[0][3] - segs[0][1] + p(4), p(8)))
            for i, (x0, y0, x1, y1) in enumerate(segs):
                if it["values"][i] == it["value"]:
                    shapes.append(("round", self.ACCENT, x0, y0, x1 - x0, y1 - y0, p(6)))
                elif it.get("hover_seg") == i:
                    shapes.append(("round", self.HOVER, x0, y0, x1 - x0, y1 - y0, p(6)))
        if "swatch" in it:  # a color, before the text
            d = p(16)
            shapes.append(("circle", it["swatch"], l + p(18), t + (h - d) / 2, d))
        elif "stops" in it:  # a gradient
            shapes.append(("hgrad", it["stops"], l + p(14), t + (h - p(12)) / 2, p(24), p(12), p(6)))
        if kind == "radio":
            d = p(16)
            x_, y_ = r - p(16) - d, t + (h - d) / 2
            if it.get("checked"):
                shapes += [("circle", self.ACCENT, x_, y_, d), ("circle", 0xFFFFFF, x_ + d / 2 - p(3), y_ + d / 2 - p(3), p(6))]
            else:
                ring = max(1.5, p(1.5))
                shapes += [("circle", self.RING, x_, y_, d), ("circle", under, x_ + ring, y_ + ring, d - 2 * ring)]
        self._shapes(hdc, shapes)

        if kind == "header":
            size = p(28)
            user32.DrawIconEx(hdc, l + p(16), t + (h - size) // 2, self.icon, size, size, 0, None, 3)
            x, (cx0, cy0, cx1, cy1) = l + p(56), self.close_rect(l, t, r, b)
            self._text(hdc, "Glowback", self.f_title, self.TEXT, x, t + p(8), cx0, t + h * 0.46)
            vx = x + self.text_width("Glowback", self.f_title) + p(7)
            self._text(hdc, f"v{__version__}", self.f_small, self.MUTED, vx, t + p(9), cx0, t + h * 0.46 + p(1))
            self._text(hdc, it["status"], self.f_small, self.MUTED, x + p(14), t + h * 0.46, cx0, b - p(6))
            self._text(hdc, self.ICONS["dismiss"], self.f_close, self.TEXT if it.get("hover_seg") == "close" else self.ICON,
                       cx0, cy0, cx1, cy1, 0x1)
        elif kind == "label":
            self._text(hdc, it["text"].upper(), self.f_label, self.LABEL, l + p(18), t + p(8), r, b)
        elif kind != "sep":
            x = l + p(46) if "swatch" in it or "stops" in it else l + p(18)
            if it.get("icon"):
                color = self.ACCENT if it.get("accent") else self.ICON
                self._text(hdc, self.ICONS[it["icon"]], self.f_icon, color, l + p(10), t, l + p(42), b, 0x1)
                x = l + p(46)
            self._text(hdc, it["text"], self.f_text, self.ACCENT if it.get("highlight") else self.TEXT, x, t,
                       r - self.right_space(it), b, 0x8000)  # DT_END_ELLIPSIS as a last resort
            right = r - p(16)
            if kind == "submenu":
                self._text(hdc, "›", self.f_chev, self.MUTED, l, t - p(1), right, b, 0x2)
                self._text(hdc, it.get("value", ""), self.f_small, self.MUTED, l, t, right - p(16), b, 0x2)
                gdi32.ExcludeClipRect(hdc, r - p(28), t, r, b)  # hide the system's own submenu arrow
            elif kind == "action" and it.get("link"):
                self._text(hdc, self.ICONS["link"], self.f_link, self.MUTED, l, t, right, b, 0x2)
            elif kind == "action" and it.get("status") and not it.get("busy"):
                text, color, glyph = it["status"]
                self._text(hdc, text, self.f_small, color, l, t, right, b, 0x2)
                if glyph:
                    gx = right - self.text_width(text, self.f_small) - p(5)
                    self._text(hdc, self.ICONS[glyph], self.f_link, color, l, t, gx, b, 0x2)
            elif kind == "segments":
                for i, (x0, y0, x1, y1) in enumerate(self.segment_rects(it, l, t, r, b)):
                    on = it["values"][i] == it["value"]
                    color = 0xFFFFFF if on else (self.TEXT if it.get("hover_seg") == i else self.MUTED)
                    if it.get("glyphs"):
                        self._text(hdc, it["glyphs"][i], self.f_icon, color, x0, y0, x1, y1, 0x1)
                    else:
                        self._text(hdc, f"{it['values'][i]}%", self.f_small, color, x0, y0, x1, y1, 0x1)


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", HANDLE), ("fErase", wt.BOOL), ("rcPaint", wt.RECT), ("fRestore", wt.BOOL),
                ("fIncUpdate", wt.BOOL), ("rgbReserved", ctypes.c_ubyte * 32)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD), ("hwndTrack", HANDLE), ("dwHoverTime", wt.DWORD)]


_sig(user32.BeginPaint, HANDLE, HANDLE, ctypes.POINTER(PAINTSTRUCT))
_sig(user32.EndPaint, wt.BOOL, HANDLE, ctypes.POINTER(PAINTSTRUCT))
_sig(user32.InvalidateRect, wt.BOOL, HANDLE, ctypes.c_void_p, wt.BOOL)
_sig(user32.ShowWindow, wt.BOOL, HANDLE, ctypes.c_int)
_sig(user32.IsWindow, wt.BOOL, HANDLE)
_sig(user32.TrackMouseEvent, wt.BOOL, ctypes.POINTER(TRACKMOUSEEVENT))
_sig(user32.MonitorFromPoint, HANDLE, wt.POINT, wt.DWORD)
_sig(user32.SetTimer, ctypes.c_size_t, HANDLE, ctypes.c_size_t, wt.UINT, ctypes.c_void_p)
_sig(user32.KillTimer, wt.BOOL, HANDLE, ctypes.c_size_t)
_sig(user32.SetWindowPos, wt.BOOL, HANDLE, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT)
_sig(gdi32.CreateCompatibleBitmap, HANDLE, HANDLE, ctypes.c_int, ctypes.c_int)
_sig(gdi32.BitBlt, wt.BOOL, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, HANDLE, ctypes.c_int,
     ctypes.c_int, wt.DWORD)
try:
    shcore = ctypes.WinDLL("shcore")
    _sig(shcore.GetDpiForMonitor, ctypes.c_long, HANDLE, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT))
except (OSError, AttributeError):
    shcore = None


def taskbar():
    """The taskbar that holds the notification area: (edge, rect), edge 0 left, 1 top, 2 right, 3 bottom."""
    abd = APPBARDATA()
    abd.cbSize = sizeof(abd)
    if shell32.SHAppBarMessage(5, byref(abd)):  # ABM_GETTASKBARPOS
        return abd.uEdge, abd.rc
    return None


def dock_flyout(pt, w, h, gap, work, screen, bar):
    """Top-left corner of the w x h panel opened from the tray icon clicked at pt: against the taskbar, like
    Windows' own flyouts. (Placed from the cursor, it was left floating mid-screen whenever the icon sat in the
    hidden-icons overflow, which closes as soon as the panel opens.)"""
    def clamp(v, lo, hi):
        return max(lo, min(v, hi))
    edge, rc = bar or (3, wt.RECT(work.left, work.bottom, work.right, work.bottom))
    if edge in (1, 3):  # taskbar on top or at the bottom: centred on the icon, along the taskbar
        x = clamp(pt.x - w // 2, work.left + gap, work.right - w - gap)
        y = max(rc.bottom, work.top) + gap if edge == 1 else min(rc.top, work.bottom) - h - gap
    else:  # on the left or the right (Windows 10)
        y = clamp(pt.y - h // 2, work.top + gap, work.bottom - h - gap)
        x = max(rc.right, work.left) + gap if edge == 0 else min(rc.left, work.right) - w - gap
    return clamp(x, screen.left, screen.right - w), clamp(y, screen.top, screen.bottom - h)


# =============================================================================
# Apps' profiles: while an app runs, is in front, is full screen (on a given screen) or plays sound, the LEDs
# show the profile's look (or the Ambient light page's); the rest of the time, what the user chose
# =============================================================================
WHEN = ("running", "foreground", "fullscreen", "playing")
DESKTOP_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd")
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, HANDLE, wt.LPARAM)
version_dll = ctypes.WinDLL("version")


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


_sig(user32.GetForegroundWindow, HANDLE)
_sig(user32.GetGuiResources, wt.DWORD, HANDLE, wt.DWORD)
_sig(k32.GetCurrentProcess, HANDLE)
_sig(user32.GetWindowThreadProcessId, wt.DWORD, HANDLE, ctypes.POINTER(wt.DWORD))
_sig(user32.EnumWindows, wt.BOOL, WNDENUMPROC, wt.LPARAM)
_sig(user32.EnumChildWindows, wt.BOOL, HANDLE, WNDENUMPROC, wt.LPARAM)
_sig(user32.IsWindowVisible, wt.BOOL, HANDLE)
_sig(user32.IsIconic, wt.BOOL, HANDLE)
_sig(user32.GetWindowRect, wt.BOOL, HANDLE, ctypes.POINTER(wt.RECT))
_sig(user32.GetWindowLongW, ctypes.c_long, HANDLE, ctypes.c_int)
_sig(user32.GetClassNameW, ctypes.c_int, HANDLE, wt.LPWSTR, ctypes.c_int)
_sig(user32.MonitorFromWindow, HANDLE, HANDLE, wt.DWORD)
_sig(k32.OpenProcess, HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
_sig(k32.QueryFullProcessImageNameW, wt.BOOL, HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))
_sig(k32.CreateToolhelp32Snapshot, HANDLE, wt.DWORD, wt.DWORD)
_sig(k32.Process32FirstW, wt.BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_sig(k32.Process32NextW, wt.BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_sig(dwmapi.DwmGetWindowAttribute, ctypes.c_long, HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD)
_sig(shell32.SHQueryUserNotificationState, ctypes.c_long, ctypes.POINTER(ctypes.c_int))
_sig(version_dll.GetFileVersionInfoSizeW, wt.DWORD, wt.LPCWSTR, ctypes.POINTER(wt.DWORD))
_sig(version_dll.GetFileVersionInfoW, wt.BOOL, wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p)
_sig(version_dll.VerQueryValueW, wt.BOOL, ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
     ctypes.POINTER(wt.UINT))


def gui_objects():
    """This process's window and drawing resources, against Windows' limit of 10000 each (for the log)."""
    me = k32.GetCurrentProcess()
    return f"GDI objects {user32.GetGuiResources(me, 0)}, USER objects {user32.GetGuiResources(me, 1)}"


def app_window_shown(pid):
    """True if process pid shows Glowback's window."""
    found = []

    def cb(hwnd, _):
        p, name = wt.DWORD(), ctypes.create_unicode_buffer(64)
        user32.GetWindowThreadProcessId(hwnd, byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd) and user32.GetClassNameW(hwnd, name, 64) \
                and name.value.startswith("GlowbackApp"):  # AppWindow's class
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return bool(found)


def app_key(name):
    r"""'C:\Program Files\VLC\VLC.EXE' or 'vlc' -> 'vlc.exe'; '', '*' or 'any' -> '' (any app)."""
    name = os.path.basename((name or "").strip().strip('"')).lower()
    if name in ("", "*", "any"):
        return ""
    return name if name.endswith(".exe") else name + ".exe"


def clean_rules(rules):
    """Valid apps' profiles only: {"app": "vlc.exe" ("" = any app), "when": one of WHEN,
    "screen": "" (any), "leds" (the screen the LEDs follow) or a screen name, "name": what the app is called,
    "look": what the LEDs show then (see clean_look; none: the Ambient light page)}."""
    out = []
    for r in rules if isinstance(rules, list) else []:
        if not isinstance(r, dict):
            continue
        rule = {"app": app_key(r.get("app", "")), "when": r.get("when") if r.get("when") in WHEN else "foreground",
                "screen": str(r.get("screen") or "")[:80]}
        if rule["when"] == "playing":
            rule["screen"] = ""  # sound has no screen
        if rule["app"] and r.get("name"):
            rule["name"] = str(r["name"])[:80]
        if rule["app"] and r.get("path"):  # for the app's icon
            rule["path"] = str(r["path"])[:400]
        if clean_look(r.get("look")):
            rule["look"] = clean_look(r["look"])
        if rule["when"] == "running" and not rule["app"] and not rule["screen"]:
            continue  # "any app is running": always true, says nothing
        key = lambda d: (d["app"], d["when"], d["screen"])
        if all(key(o) != key(rule) for o in out):
            out.append(rule)
    return out[:32]


def process_path(pid):
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION: works for most apps, elevated too
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
        return buf.value if k32.QueryFullProcessImageNameW(h, 0, buf, byref(size)) else ""
    finally:
        k32.CloseHandle(h)


def running_processes():
    """pid -> exe name (lower case) of every running process."""
    out = {}
    snap = k32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == INVALID_HANDLE:
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = sizeof(e)
        ok = k32.Process32FirstW(snap, byref(e))
        while ok:
            out[e.th32ProcessID] = e.szExeFile.lower()
            ok = k32.Process32NextW(snap, byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


def app_description(path):
    """An app's own name ("VLC media player") from its version information, else its file name without .exe."""
    fallback = os.path.splitext(os.path.basename(path))[0]
    try:
        size = version_dll.GetFileVersionInfoSizeW(path, None)
        if not size:
            return fallback
        data = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(path, 0, size, data):
            return fallback
        ptr, n = ctypes.c_void_p(), wt.UINT()
        langs = []
        if version_dll.VerQueryValueW(data, "\\VarFileInfo\\Translation", byref(ptr), byref(n)) and n.value >= 4:
            pairs = (ctypes.c_uint16 * (n.value // 2)).from_address(ptr.value)
            langs = [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs) - 1, 2)]
        for lang, cp in langs + [(0x0409, 0x04B0), (0x0409, 0x04E4), (0x0000, 0x04B0)]:
            key = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\FileDescription"
            if version_dll.VerQueryValueW(data, key, byref(ptr), byref(n)) and n.value > 1 and ptr.value:
                text = ctypes.wstring_at(ptr.value).strip()
                if text:
                    return text[:60]
    except (OSError, ValueError):
        pass
    return fallback


def cloaked(hwnd):
    """Windows hidden by DWM (other virtual desktops, suspended Store apps) count as not shown."""
    v = wt.DWORD(0)
    return dwmapi.DwmGetWindowAttribute(hwnd, 14, byref(v), 4) == 0 and v.value != 0  # DWMWA_CLOAKED


class Foreground:
    __slots__ = ("hwnd", "pid", "exe", "device", "fullscreen")


class AppWatch:
    """What sync conditions look at: the window in front, the running apps, the screens their windows are on.
    Everything is cached briefly, so checking four times a second costs next to nothing."""

    def __init__(self):
        self._exe = {}  # pid -> (exe, when)
        self._procs, self._procs_t = {}, -99.0
        self._wins, self._wins_t = {}, -99.0

    def exe_of(self, pid):
        now = time.monotonic()
        hit = self._exe.get(pid)
        if hit and now - hit[1] < 10:
            return hit[0]
        exe = os.path.basename(process_path(pid)).lower() or self.processes().get(pid, "")
        if len(self._exe) > 512:
            self._exe.clear()
        self._exe[pid] = (exe, now)
        return exe

    def processes(self):
        """pid -> exe of every running process, refreshed every 2 seconds at most."""
        now = time.monotonic()
        if now - self._procs_t >= 2:
            self._procs, self._procs_t = running_processes(), now
        return self._procs

    @staticmethod
    def window_pid(hwnd):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, byref(pid))
        return pid.value

    def owner(self, hwnd):
        """(pid, exe) of the app a window belongs to. Store apps live inside ApplicationFrameHost: look past it."""
        pid = self.window_pid(hwnd)
        exe = self.exe_of(pid)
        if exe == "applicationframehost.exe":
            inner = []

            def cb(child, _):
                p = self.window_pid(child)
                if p != pid:
                    inner.append(p)
                    return False
                return True

            user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
            if inner:
                pid, exe = inner[0], self.exe_of(inner[0]) or exe
        return pid, exe

    @staticmethod
    def screen_of(hwnd):
        """(device name, monitor rectangle) of the screen a window is on."""
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        hmon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not hmon or not user32.GetMonitorInfoW(hmon, byref(mi)):
            return "", None
        return mi.szDevice, mi.rcMonitor

    @staticmethod
    def class_of(hwnd):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        return buf.value

    def foreground(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        f = Foreground()
        f.hwnd = hwnd
        f.pid, f.exe = self.owner(hwnd)
        f.device, mrc = self.screen_of(hwnd)
        f.fullscreen = False
        if mrc and self.class_of(hwnd) not in DESKTOP_CLASSES:
            rc = wt.RECT()
            user32.GetWindowRect(hwnd, byref(rc))
            if rc.left <= mrc.left and rc.top <= mrc.top and rc.right >= mrc.right and rc.bottom >= mrc.bottom:
                captioned = user32.GetWindowLongW(hwnd, -16) & 0x00C00000 == 0x00C00000  # WS_CAPTION
                quns = ctypes.c_int(0)  # what Windows itself calls full screen (games, videos, presentations)
                busy = shell32.SHQueryUserNotificationState(byref(quns)) == 0 and quns.value in (2, 3, 4)
                f.fullscreen = not captioned or busy
        return f

    def windows(self):
        """exe -> screens (device names) where the app shows a window, refreshed every second at most."""
        now = time.monotonic()
        if now - self._wins_t < 1:
            return self._wins
        found = {}

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd) and not cloaked(hwnd) \
                    and self.class_of(hwnd) not in DESKTOP_CLASSES:
                _, exe = self.owner(hwnd)
                device, _ = self.screen_of(hwnd)
                if exe and device:
                    found.setdefault(exe, set()).add(device)
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        self._wins, self._wins_t = found, now
        return found

    def open_apps(self):
        """Apps with a window open now, for the app picker: [(exe, name, path)], sorted by name."""
        own, seen, apps = os.getpid(), set(), []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd) and not cloaked(hwnd) \
                    and not user32.GetWindow(hwnd, 4) and user32.GetWindowTextLengthW(hwnd) > 0 \
                    and self.class_of(hwnd) not in DESKTOP_CLASSES:  # GW_OWNER: top windows only, with a title
                pid, exe = self.owner(hwnd)
                if exe and exe not in seen and pid != own and exe not in ("applicationframehost.exe", "textinputhost.exe"):
                    seen.add(exe)
                    path = process_path(pid)
                    apps.append((exe, app_description(path) if path else exe[:-4], path))
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return sorted(apps, key=lambda a: a[1].lower())


_sig(user32.GetWindow, HANDLE, HANDLE, wt.UINT)


def screen_devices(screen, leds, monitors):
    r"""Device names (\\.\DISPLAYn) a condition's screen stands for; None = any screen."""
    if not screen:
        return None
    if screen == "leds":
        return set(leds)
    c = _norm(screen)
    return {m.device for m in monitors if c and (c == _norm(m.device) or c == _norm(m.name) or c in _norm(m.name + m.pnp))}


def conditions_met(rules, leds, monitors, watch, sound=None):
    """The first app's condition that holds now, or None."""
    fg = playing = None
    for r in rules:
        app, screens = r["app"], screen_devices(r["screen"], leds, monitors)
        if r["when"] == "playing":
            if playing is None:
                playing = {watch.exe_of(pid) for pid in sound.pids()} - {""} if sound else set()
            ok = app in playing if app else bool(playing)
        elif r["when"] == "running":
            if screens is None:
                ok = app in watch.processes().values()
            else:
                ok = any(devices & screens for exe, devices in watch.windows().items() if not app or exe == app)
        else:
            fg = fg or watch.foreground()
            ok = (fg is not None and (not app or fg.exe == app) and (screens is None or fg.device in screens)
                  and (r["when"] == "foreground" or fg.fullscreen))
        if ok:
            return r
    return None


def parse_rule(text, monitors=()):
    """Command line form WHEN:APP[@SCREEN] -> a condition, e.g. foreground:vlc.exe, fullscreen:*@leds, running:steam,
    playing:spotify."""
    when, _, rest = text.partition(":")
    when = {"front": "foreground", "full": "fullscreen", "run": "running", "sound": "playing", "play": "playing",
            "audio": "playing"}.get(when.strip().lower(), when.strip().lower())
    if when not in WHEN or not rest.strip():
        raise ValueError(text)
    app, _, screen = rest.partition("@")
    screen = screen.strip()
    if screen.lower() in ("leds", "led", "glowback"):
        screen = "leds"
    elif screen.isdigit():  # a number from glowback --list: kept as the screen's name, which survives reboots
        m = next((m for m in monitors if m.index == int(screen)), None)
        if m is None:
            raise ValueError(text)
        screen = m.name or m.device
    rules = clean_rules([{"app": app, "when": when, "screen": screen}])
    if not rules:
        raise ValueError(text)
    return rules[0]


def cmd_sync_when(values):
    """glowback --sync-when WHEN:APP[@SCREEN] ... (or always): saved; a running Glowback follows within 2 seconds."""
    usage = ("usage: glowback --sync-when WHEN:APP[@SCREEN] [--sync-when ...]   or   --sync-when always\n"
             "  WHEN: running, foreground, fullscreen or playing (plays sound); APP: an .exe name or * for any app;\n"
             "  SCREEN: leds (the screen the LEDs follow), a number from --list, or a screen name")
    if any(v.strip().lower() in ("always", "off", "none") for v in values):
        save_settings({"sync_when": [], "otherwise": "auto"})
        print("Glowback follows the screen all the time.")
        return
    monitors = list_monitors()
    try:
        rules = clean_rules([parse_rule(v, monitors) for v in values])
    except ValueError as e:
        sys.exit(f"Not understood: {e}\n{usage}")
    save_settings({"sync_when": rules, "otherwise": "device"})
    print("Glowback follows the screen only while one of these holds (the rest of the time, the LEDs show their own effect):")
    whens = dict(running="is running", foreground="is in front", fullscreen="is full screen", playing="plays sound")
    for r in rules:
        where = {"": "", "leds": " on the LED screen"}.get(r["screen"], f" on screen {r['screen']}")
        print(f"  {r['app'] or 'any app'} {whens[r['when']]}{where}")


class Tray:
    """Notification-area icon: pause/resume, mode, brightness, start with Windows, quit."""
    WM_TRAY, WM_CLOSE_APP, WM_UPDATE, WM_CHECKED = 0x8001, 0x8002, 0x8003, 0x8004
    WM_HA, WM_HA_INSTALL = 0x8005, 0x8006  # posted by the Home Assistant thread
    WM_OPEN_APP, WM_SYNC = 0x8007, 0x8008  # Glowback launched again; something shown changed (any thread)

    def __init__(self, state, stop, argv):
        self.state, self.stop, self.argv = state, stop, argv
        self.worker = None
        self.app = None  # the app window, made the first time it opens
        self.started, self.restarting = time.monotonic(), False  # see open_app()
        on, off = ensure_icons()
        self.icon_path = on
        self.painter, self.items = None, []
        self.balloon = None
        cx, cy = user32.GetSystemMetrics(49), user32.GetSystemMetrics(50)  # SM_CXSMICON, SM_CYSMICON
        self.icons = (user32.LoadImageW(None, on, 1, cx, cy, 0x10), user32.LoadImageW(None, off, 1, cx, cy, 0x10))
        self._proc_ref = WNDPROC(self._proc)
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._proc_ref, hinst, "GlowbackTray"
        user32.RegisterClassExW(byref(wc))
        self.flyout, self.flyout_closed, self.autostart, self.fly_place = None, 0.0, False, None
        self.checking, self.check_result, self.check_time = False, None, 0.0  # "check for updates" button
        self.hover = self.hover_seg = None
        self.ha, self.ha_dialog = None, None  # Home Assistant connection and its window
        self.matter = None  # the Matter light (Apple Home, Google Home...), when it is on
        self._fly_ref = WNDPROC(self._fly_proc)
        fc = WNDCLASSEXW()
        fc.cbSize, fc.lpfnWndProc, fc.hInstance, fc.lpszClassName = sizeof(fc), self._fly_ref, hinst, "GlowbackFlyout"
        fc.style = 0x00020000  # CS_DROPSHADOW
        fc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW
        user32.RegisterClassExW(byref(fc))
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
        s = self.state
        n.hIcon = self.icons[0 if s.lit() and not s.waiting else 1]
        n.szTip = tr("tip_off") if not s.lit() else tr("tip_device") if s.waiting else tr("tip_on")
        if info:
            n.uFlags |= 0x10  # NIF_INFO
            n.szInfoTitle, n.szInfo = info
        return n

    def refresh(self, info=None):
        shell32.Shell_NotifyIconW(1, byref(self._nid(info)))  # NIM_MODIFY

    def start_update(self):
        """Download, verify and install the new version in the background, then quit (it restarts itself)."""
        info, s = getattr(self.state, "update_info", None), self.state
        if not info or getattr(self, "updating", False):
            return
        self.updating, self.balloon = True, None
        self.refresh(("Glowback", tr("update_downloading", version=s.new_version)))

        def work():
            try:
                apply_update(info)
                log(f"Updating to {s.new_version}")
                self.refresh(("Glowback", tr("update_installing")))
                time.sleep(1.5)
                k32.SetEvent(self.stop.h)  # quit: the new version starts on its own
            except Exception as e:
                log(f"Update failed: {e!r}")
                self.updating = False
                self.refresh(("Glowback", tr("update_failed", error=str(e) or e.__class__.__name__)))
                os.startfile(update_url(s))

        threading.Thread(target=work, name="glowback-updating", daemon=True).start()

    def close_from_thread(self):
        user32.PostMessageW(self.hwnd, self.WM_CLOSE_APP, 0, 0)

    def loop(self):
        msg = wt.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            dialog = self.ha_dialog
            if dialog and dialog.hwnd and user32.IsDialogMessageW(dialog.hwnd, byref(msg)):  # Tab, Enter, Esc
                continue
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    def ha_window(self):
        """The Home Assistant row of the panel: its connection window."""
        if not self.ha_dialog:
            self.ha_dialog = HomeAssistantDialog(self)
        self.ha_dialog.open()

    def ha_changed(self):
        if self.ha:
            self.ha.reconfigure()

    def matter_toggle(self):
        """The Matter light on or off (its phones and apps stay paired)."""
        on = not matter_settings().get("on")
        save_settings({"matter": dict(matter_settings(), on=on)})
        if on and not self.matter:
            self.matter = matter_start(self.state, self.matter_notify)
        elif not on and self.matter:
            self.matter.stop()
            self.matter = None
            log("Matter: off")

    def matter_notify(self):
        """Pairing opened or closed, a phone added or removed (Matter's thread): redraw."""
        user32.PostMessageW(self.hwnd, self.WM_SYNC, 0, 0)

    def open_app(self, page=None):
        """Glowback's window, on a page; the panel closes."""
        if self.flyout and user32.IsWindow(self.flyout):
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)  # WM_CLOSE
        try:
            if not self.app:
                self.app = AppWindow(self)
            self.app.open(page)
        except Exception as e:
            log(f"App window: {e!r}")
        if self.app and self.app.hwnd:
            return
        # Windows refused the window (a long-running process can run out of window or drawing resources): a fresh
        # Glowback takes over and opens it, see main(). Not right after starting: the new one would fail the same way.
        if time.monotonic() - self.started > 60 and not self.restarting:
            self.restarting = True
            log("The window could not open: restarting Glowback.")
            subprocess.Popen(launch_command(self.argv), creationflags=0x00000008 | 0x00000200, close_fds=True)

    def app_closed(self):
        """The window closed: Glowback keeps running. Said once, the first time."""
        if not load_settings().get("told_background"):
            save_settings({"told_background": True})
            self.refresh(("Glowback", tr("app_background")))

    def _changed(self):
        """Something the panel or the window shows changed: redraw them."""
        if self.flyout and self.painter:
            user32.InvalidateRect(self.flyout, None, False)
        if self.app:
            self.app.invalidate()

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            return self._on(hwnd, msg, wparam, lparam)
        except Exception as e:  # without a console the error would vanish: log it, keep the tray running
            log(f"Tray: {e!r}")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            event = lparam & 0xFFFF
            if event in (0x0202, 0x0205, 0x007B):  # left/right click, context menu
                self._menu()
            elif event == 0x0203:  # double click: the app
                self.open_app()
            elif event == 0x0405 and self.balloon == "update":  # NIN_BALLOONUSERCLICK
                self.start_update()
            return 0
        if msg == self.WM_OPEN_APP:  # Glowback launched again (Start menu...): show this one's window
            self.open_app()
            return 0
        if msg == self.WM_SYNC:  # paused, resumed, waiting for a condition...: icon, panel, window
            self.refresh()
            self._changed()
            return 0
        if msg == self.WM_UPDATE:  # posted by the update checker thread
            self.balloon = "update"
            self.refresh((tr("update_title", version=self.state.new_version), tr("update_text")))
            if self.flyout and self.painter:
                self._fit_flyout()
            if self.app:
                self.app.invalidate()
            return 0
        if msg == self.WM_CHECKED:  # posted by check_now() once GitHub answered
            self.checking, self.check_time = False, time.monotonic()
            if self.flyout and self.painter:
                user32.KillTimer(self.flyout, 1)
                self._fit_flyout()  # a new version adds the "Update to" row
            elif self.check_result == "found" and not (self.app and self.app.hwnd):
                self.balloon = "update"
                self.refresh((tr("update_title", version=self.state.new_version), tr("update_text")))
            if self.app:
                self.app.invalidate()
            return 0
        if msg == self.WM_HA:  # Home Assistant changed a setting, or its connection status changed
            self.refresh()
            self._changed()
            return 0
        if msg == self.WM_HA_INSTALL:  # "Install" on Glowback's update entity in Home Assistant
            if getattr(self.state, "update_info", None):
                self.start_update()
            return 0
        if msg == 0x002C and self.painter:  # WM_MEASUREITEM (menu)
            mis = MEASUREITEMSTRUCT.from_address(lparam)
            if mis.CtlType == 1 and mis.itemData < len(self.items):
                self.painter.measure(mis, self.items[mis.itemData])
                return 1
        if msg == 0x002B and self.painter:  # WM_DRAWITEM (menu)
            dis = DRAWITEMSTRUCT.from_address(lparam)
            if dis.CtlType == 1 and dis.itemData < len(self.items):
                self.painter.draw(dis, self.items[dis.itemData])
                return 1
        if msg == 0x0121 and wparam == 2 and self.painter:  # WM_ENTERIDLE from a menu window
            self.painter.style_window(lparam)
        if msg == self.WM_CLOSE_APP:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            shell32.Shell_NotifyIconW(2, byref(self._nid()))  # NIM_DELETE
            user32.PostQuitMessage(0)
            return 0
        if msg == 0x0016 and wparam:  # WM_ENDSESSION: shutdown, sign-out, or an installer closing us
            k32.SetEvent(self.stop.h)
            if self.worker:
                self.worker.join(3)  # hand the LEDs back before the process is ended
            shell32.Shell_NotifyIconW(2, byref(self._nid()))
            return 0
        if self.taskbar_created and msg == self.taskbar_created:  # Explorer restarted
            shell32.Shell_NotifyIconW(0, byref(self._nid()))
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self):
        """Left or right click on the icon: open the panel, or close it if it is open."""
        if self.flyout and user32.IsWindow(self.flyout):
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)  # WM_CLOSE
        elif time.monotonic() - self.flyout_closed > 0.3:  # the click that closed it (focus lost) must not reopen it
            self._open_flyout()

    def _items(self):
        """The panel's content, rebuilt on every paint so it always shows the current state."""
        s = self.state
        status, dot = s.status()
        items = [dict(kind="header", status=status, state=dot)]
        if s.new_version:  # the "check for updates" row becomes the one that downloads and installs it
            update = dict(kind="action", id=26, icon="sync", text=tr("update_to", version=s.new_version), accent=True,
                          highlight=True, busy=getattr(self, "updating", False))
        else:
            update = dict(kind="action", id=26, icon="sync", text=tr("updates"), busy=self.checking,
                          status=self._check_status(), statuses=(tr("up_to_date"), tr("check_failed"), "v00.00.00"))
        items += [dict(kind="action", id=29, icon="window", text=tr("open_app")),
                  dict(kind="sep"),
                  dict(kind="toggle", id=1, icon="light", text=tr("ambilight"), on=s.lit()),
                  dict(kind="action", id=28, icon="layers", text=tr("nav_profiles"), status=self._profile_status(),
                       statuses=(tr("profiles_none"), tr("profiles_many", n=12), tr("night_short"), "Spotify Premium")),
                  dict(kind="action", id=20, icon="power", text=tr("start_windows"), link=True) if PACKAGE else
                  dict(kind="toggle", id=20, icon="power", text=tr("start_windows"), on=self.autostart),
                  dict(kind="action", id=27, icon="home", text="Home Assistant", status=Tray._ha_status(self),
                       statuses=(tr("ha_setup"), tr("ha_connected"), tr("ha_connecting"), tr("ha_error"))),
                  dict(kind="sep"), dict(kind="label", text=tr("mode")),
                  dict(kind="segments", id=11, icon=AppWindow.MODE_ICONS[s.mode], text=tr("mode_" + s.mode),
                       values=MODES, value=s.mode, seg_w=34, glyphs=[MenuPainter.ICONS[AppWindow.MODE_ICONS[m]]
                                                                     for m in MODES]),
                  dict(kind="segments", id=10, icon="sun", text=tr("brightness"), values=(25, 50, 75, 100),
                       value=round(s.brightness)),
                  dict(kind="sep"), dict(kind="label", text=tr("about")),
                  update,
                  dict(kind="toggle", id=24, icon="clock", text=tr("auto_check"), on=s.check_updates),
                  dict(kind="action", id=23, icon="person", text=tr("made_by", author=AUTHOR), link=True),
                  dict(kind="action", id=22, icon="star", text=tr("star"), accent=True, link=True),
                  dict(kind="action", id=21, icon="doc", text=tr("open_log")),
                  dict(kind="sep"),
                  dict(kind="action", id=99, icon="quit", text=tr("quit"))]
        if PACKAGE:  # the Store updates the Store version
            items = [it for it in items if it.get("id") not in (24, 26)]
        for i, it in enumerate(items):
            if i == self.hover:
                it["hover_seg"] = self.hover_seg
        return items

    def _profile_status(self):
        """Right side of the Profiles row: (text, colour, glyph)."""
        s = self.state
        count = len(s.rules) + (1 if s.night["on"] else 0)
        if not count:
            return tr("profiles_none"), MenuPainter.MUTED, None
        a = s.active
        if s.enabled and a["source"] == "app":
            name = (a["rule"].get("name") or a["rule"]["app"][:-4]) if a["rule"]["app"] else tr("sync_any_app")
            return (name[:15] + "…" if len(name) > 16 else name), MenuPainter.GREEN, "check"
        if s.enabled and a["source"] == "night":
            return tr("night_short"), MenuPainter.LABEL, "moon"
        if s.enabled and a["source"] == "rest" and a["look"]["mode"] in ("device", "off"):
            return tr("look_device" if a["look"]["mode"] == "device" else "look_off"), MenuPainter.AMBER, "clock"
        return (tr("profiles_one") if count == 1 else tr("profiles_many", n=count)), MenuPainter.MUTED, None

    def _ha_status(self):
        """Right side of the Home Assistant row: (text, colour, glyph)."""
        ha = getattr(self, "ha", None)
        status = ha.status if ha else "off"
        if status == "connected":
            return tr("ha_connected"), MenuPainter.GREEN, "check"
        if status == "connecting":
            return tr("ha_connecting"), MenuPainter.MUTED, None
        if status == "error":
            return tr("ha_error"), MenuPainter.AMBER, "warning"
        return tr("ha_setup"), MenuPainter.MUTED, None

    def _check_status(self):
        """Result of the last "check for updates" click, kept 10 minutes: (text, colour, glyph) or None."""
        if self.checking or not self.check_result or time.monotonic() - self.check_time > 600:
            return None
        if self.check_result == "found" and self.state.new_version:
            return f"v{self.state.new_version}", MenuPainter.ACCENT, None
        if self.check_result == "latest":
            return tr("up_to_date"), MenuPainter.GREEN, "check"
        return tr("check_failed"), MenuPainter.AMBER, "warning"

    def check_now(self):
        """The "check for updates" button: asks GitHub in the background while the row shows a loader."""
        if self.checking:
            return
        self.checking, self.check_result = True, None
        if self.flyout:
            user32.SetTimer(self.flyout, 1, 33, None)
        s, started = self.state, time.monotonic()

        def work():
            try:
                info = latest_release()
                tag = info["version"]
                if tag and _version_tuple(tag) > _version_tuple(__version__):
                    s.new_version, s.update_page, s.update_info = tag, info["page"], info
                    log(f"Update available: {tag}")
                    result = "found"
                else:
                    result = "latest"
            except Exception as e:  # offline, rate limited...
                log(f"Update check failed ({e.__class__.__name__}: {e})")
                result = "error"
            time.sleep(max(0.0, 0.8 - (time.monotonic() - started)))  # long enough to see the loader
            self.check_result = result
            user32.PostMessageW(self.hwnd, self.WM_CHECKED, 0, 0)

        threading.Thread(target=work, name="glowback-check", daemon=True).start()

    def _fit_flyout(self):
        """Resizes the open panel to its content (a row appears when a new version is found), still docked."""
        _, w, h = self._layout()
        pt, work, screen, bar = self.fly_place
        x, y = dock_flyout(pt, w, h, self.painter.px(12), work, screen, bar)
        user32.SetWindowPos(self.flyout, None, x, y, w, h, 0x0014)  # SWP_NOZORDER | SWP_NOACTIVATE
        user32.InvalidateRect(self.flyout, None, False)

    def _layout(self):
        """Rows (top, bottom) and the panel size, from the painter's measurements."""
        p = self.painter.px
        rows, y, width = [], p(6), 0
        for it in self._items():
            m = MEASUREITEMSTRUCT()
            self.painter.measure(m, it)
            rows.append((y, y + m.itemHeight))
            y += m.itemHeight
            width = max(width, m.itemWidth)
        return rows, width + p(12), y + p(6)

    def _open_flyout(self, pt=None):
        if pt is None:
            pt = wt.POINT()
            user32.GetCursorPos(byref(pt))
        mon, bar = user32.MonitorFromPoint(pt, 2), taskbar()  # MONITOR_DEFAULTTONEAREST
        if bar and user32.MonitorFromRect(byref(bar[1]), 2) != mon:  # opened from the keyboard, cursor elsewhere:
            mon = user32.MonitorFromRect(byref(bar[1]), 2)  # open at the notification-area end of the taskbar
            pt = wt.POINT(bar[1].right - 1, bar[1].bottom - 1)
        dpi_x, dpi_y = wt.UINT(96), wt.UINT(96)
        if shcore:
            shcore.GetDpiForMonitor(mon, 0, byref(dpi_x), byref(dpi_y))
        scale = dpi_x.value / 96.0
        size = round(28 * scale)
        self.flyout_icon = user32.LoadImageW(None, self.icon_path, 1, size, size, 0x10)
        self.painter = MenuPainter(scale, self.flyout_icon)
        self.autostart = autostart_enabled()
        self.hover, self.hover_seg, self.tracking = None, None, False
        rows, w, h = self._layout()
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        user32.GetMonitorInfoW(mon, byref(mi))
        self.fly_place = (pt, mi.rcWork, mi.rcMonitor, bar)
        x, y = dock_flyout(pt, w, h, self.painter.px(12), mi.rcWork, mi.rcMonitor, bar)
        hinst = k32.GetModuleHandleW(None)
        self.flyout = user32.CreateWindowExW(0x00000080 | 0x00000008, "GlowbackFlyout", "Glowback", 0x80000000,
                                             x, y, w, h, None, None, hinst, None)  # TOOLWINDOW|TOPMOST, POPUP
        if not self.flyout:
            self.painter.close()
            self.painter = None
            return
        for attr, value in ((20, 1), (33, 2), (34, _cref(0x2C2E38))):  # dark mode, rounded corners, border colour
            v = wt.DWORD(value)
            dwmapi.DwmSetWindowAttribute(self.flyout, attr, byref(v), 4)
        user32.ShowWindow(self.flyout, 5)  # SW_SHOW
        user32.SetForegroundWindow(self.flyout)
        if self.checking:  # reopened while a check is running: keep the loader turning
            user32.SetTimer(self.flyout, 1, 33, None)

    def _hit(self, x, y):
        """(row, part) under the mouse: part is a brightness choice, or "close" for the header's button."""
        rows, _, _ = self._layout()
        items = self._items()
        rc = wt.RECT()
        user32.GetClientRect(self.flyout, byref(rc))
        l, r = self.painter.px(6), rc.right - self.painter.px(6)
        for i, (t, b) in enumerate(rows):
            if t <= y < b:
                seg = None
                if items[i]["kind"] == "segments":
                    for k, (x0, y0, x1, y1) in enumerate(self.painter.segment_rects(items[i], l, t, r, b)):
                        if x0 <= x < x1:
                            seg = k
                elif items[i]["kind"] == "header":
                    x0, y0, x1, y1 = self.painter.close_rect(l, t, r, b)
                    if x0 <= x < x1 and y0 <= y < y1:
                        seg = "close"
                return i, seg
        return None, None

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        rc = wt.RECT()
        user32.GetClientRect(hwnd, byref(rc))
        mem = gdi32.CreateCompatibleDC(hdc)  # double buffered: no flicker while hovering
        bmp = gdi32.CreateCompatibleBitmap(hdc, rc.right, rc.bottom)
        old = gdi32.SelectObject(mem, bmp)
        user32.FillRect(mem, byref(rc), self.painter.bg_brush)
        rows, _, _ = self._layout()
        pad = self.painter.px(6)
        for i, (it, (t, b)) in enumerate(zip(self._items(), rows)):
            d = DRAWITEMSTRUCT()
            d.CtlType, d.hDC, d.rcItem = 1, mem, wt.RECT(pad, t, rc.right - pad, b)
            d.itemState = 1 if i == self.hover else 0
            self.painter.draw(d, it)
        gdi32.BitBlt(hdc, 0, 0, rc.right, rc.bottom, mem, 0, 0, 0x00CC0020)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.EndPaint(hwnd, byref(ps))

    def _click(self, i, seg):
        items = self._items()
        if i is not None and items[i]["kind"] == "header" and seg == "close":
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)  # WM_CLOSE: the panel only, Glowback keeps running
            return
        if i is None or "id" not in items[i]:
            return
        s, cid = self.state, items[i]["id"]
        if cid == 1:  # settings change in place: the panel stays open
            s.switch()
            self.refresh()
        elif cid == 20 and not PACKAGE:
            set_autostart(not self.autostart, self.argv)
            self.autostart = autostart_enabled()
        elif cid == 24:
            s.update(check_updates=not s.check_updates)
        elif cid == 11:
            if seg is not None:
                s.update(mode=MODES[seg])
        elif cid == 10:
            if seg is not None:
                s.update(brightness=items[i]["values"][seg])
        elif cid == 26 and not s.new_version:
            self.check_now()
        else:  # links, update, quit: close the panel first
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)
            if cid == 21:
                os.startfile(LOG_PATH)
            elif cid == 22:
                os.startfile(REPO_URL)
            elif cid == 23:
                os.startfile(AUTHOR_URL)
            elif cid in (25, 26):  # a new version is out: download and install it
                self.start_update()
            elif cid == 20:  # the Store version: Windows' startup apps
                os.startfile(STARTUP_SETTINGS)
            elif cid == 27:
                self.open_app("home")
            elif cid == 28:
                self.open_app("profiles")
            elif cid == 29:
                self.open_app()
            elif cid == 99:
                k32.SetEvent(self.stop.h)
            return
        user32.InvalidateRect(self.flyout, None, False)

    def _fly_proc(self, hwnd, msg, wparam, lparam):
        if msg == 0x000F and self.painter:  # WM_PAINT
            self._paint(hwnd)
            return 0
        if msg == 0x0014:  # WM_ERASEBKGND: painted in WM_PAINT
            return 1
        if msg == 0x0113:  # WM_TIMER: the update loader turns
            if self.checking:
                user32.InvalidateRect(hwnd, None, False)
            else:
                user32.KillTimer(hwnd, 1)
            return 0
        if msg == 0x0200 and self.painter:  # WM_MOUSEMOVE
            x, y = ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value
            hit = self._hit(x, y)
            if hit != (self.hover, self.hover_seg):
                self.hover, self.hover_seg = hit
                user32.InvalidateRect(hwnd, None, False)
            if not self.tracking:
                tme = TRACKMOUSEEVENT(sizeof(TRACKMOUSEEVENT), 0x2, hwnd, 0)  # TME_LEAVE
                self.tracking = bool(user32.TrackMouseEvent(byref(tme)))
            return 0
        if msg == 0x02A3:  # WM_MOUSELEAVE
            self.tracking, self.hover, self.hover_seg = False, None, None
            user32.InvalidateRect(hwnd, None, False)
            return 0
        if msg == 0x0202 and self.painter:  # WM_LBUTTONUP
            x, y = ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._click(*self._hit(x, y))
            return 0
        if msg == 0x0100 and wparam == 0x1B:  # Esc
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            return 0
        if msg == 0x0006 and (wparam & 0xFFFF) == 0:  # WM_ACTIVATE, WA_INACTIVE: a click elsewhere closes it
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            self.flyout, self.flyout_closed = None, time.monotonic()
            if self.painter:
                self.painter.close()
                self.painter = None
            user32.DestroyIcon(self.flyout_icon)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def latest_release():
    """Latest GitHub release: version, page, {asset name: download URL}. Sends only a 'Glowback/<version>' user agent."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO_URL.split('github.com/')[1]}/releases/latest",
                                 headers={"User-Agent": f"Glowback/{__version__}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    return dict(version=data.get("tag_name", "").lstrip("vV"), page=data.get("html_url") or REPO_URL + "/releases/latest",
                assets=assets)


def install_kind():
    if PACKAGE:
        return "store"  # updated by the Microsoft Store
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        return "installer" if os.path.exists(os.path.join(here, "unins000.exe")) else "portable"
    return "pip" if "site-packages" in os.path.abspath(__file__).lower() else "script"


def _fetch(url, dest=None):
    """HTTPS download from GitHub only. Returns bytes, or the SHA-256 of the file written to `dest`."""
    import hashlib
    import urllib.request
    if not url.startswith(("https://github.com/", "https://objects.githubusercontent.com/")):
        raise OSError("unexpected download location")
    req = urllib.request.Request(url, headers={"User-Agent": f"Glowback/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if dest is None:
            return r.read()
        h = hashlib.sha256()
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
        return h.hexdigest()


def apply_update(info):
    """Downloads the release asset matching this install, checks it against SHA256SUMS.txt, installs it and
    starts the new version (after this process exits). Returns once the new version is on its way."""
    import shutil
    import tempfile
    kind = install_kind()
    if kind == "store":
        raise OSError("the Microsoft Store updates this Glowback")
    assets = info["assets"]
    if kind == "installer":
        name = "GlowbackSetup.exe"
    elif kind == "portable":
        name = os.path.basename(sys.executable) if os.path.basename(sys.executable) in assets else "GlowbackTray.exe"
    elif kind == "pip":
        name = next((n for n in assets if n.endswith(".whl")), "")
    else:
        name = "glowback.py"
    if name not in assets or "SHA256SUMS.txt" not in assets:
        raise OSError("no download for this kind of install")
    sums = _fetch(assets["SHA256SUMS.txt"]).decode("utf-8", "replace")
    expected = next((ln.split()[0].lower() for ln in sums.splitlines()
                     if len(ln.split()) == 2 and ln.split()[1].lstrip("*") == name), None)
    tmp = tempfile.mkdtemp(prefix="glowback-update-")
    dest = os.path.join(tmp, name)
    if not expected or _fetch(assets[name], dest) != expected:
        raise OSError("checksum mismatch")
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    if kind == "installer":  # silent install; the installer stops us and relaunches the new version
        subprocess.Popen([dest, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"],
                         creationflags=flags, close_fds=True)
        return
    if kind == "pip":
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-deps", "--disable-pip-version-check",
                        dest], check=True, creationflags=0x08000000, capture_output=True)  # CREATE_NO_WINDOW
    else:  # portable exe or single file: a running file can be renamed, then replaced
        current = sys.executable if kind == "portable" else os.path.abspath(__file__)
        old = current + ".old"
        if os.path.exists(old):
            os.remove(old)
        os.rename(current, old)
        shutil.copyfile(dest, current)
    subprocess.Popen(launch_command(["--after-update"]), creationflags=flags, close_fds=True)


def _version_tuple(v):
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def update_url(state):
    """Installed with GlowbackSetup.exe: download the new installer. Otherwise: the release page."""
    if getattr(sys, "frozen", False) and os.path.exists(os.path.join(os.path.dirname(sys.executable), "unins000.exe")):
        return REPO_URL + "/releases/latest/download/GlowbackSetup.exe"
    return getattr(state, "update_page", None) or REPO_URL + "/releases/latest"


def update_checker(state, stop, notify):
    """Checks GitHub for a newer release shortly after start, then once a day (tray toggle, on by default)."""
    if stop.wait(30):
        return
    while True:
        if state.check_updates:
            try:
                info = latest_release()
                tag = info["version"]
                if tag and _version_tuple(tag) > _version_tuple(__version__) and state.new_version != tag:
                    state.new_version, state.update_page, state.update_info = tag, info["page"], info
                    log(f"Update available: {tag}")
                    notify()
            except Exception as e:  # offline, rate limited...: try again tomorrow
                log(f"Update check skipped ({e.__class__.__name__})")
        if stop.wait(24 * 3600):
            return


def run_with_tray(args, stop, state, argv):
    try:
        tray = Tray(state, stop, argv)
    except OSError as e:
        log(f"Tray icon unavailable ({e}), running without it.")
        HomeAssistant(state, stop).start()
        return run(args, stop, state)
    tray.ha = HomeAssistant(state, stop, notify=lambda: user32.PostMessageW(tray.hwnd, Tray.WM_HA, 0, 0),
                            install=lambda: user32.PostMessageW(tray.hwnd, Tray.WM_HA_INSTALL, 0, 0)).start()
    state.notify = lambda: user32.PostMessageW(tray.hwnd, Tray.WM_SYNC, 0, 0)
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
    tray.worker = t
    t.start()
    if not PACKAGE:  # the Store updates the Store version
        threading.Thread(target=update_checker, name="glowback-update", daemon=True,
                         args=(state, stop, lambda: user32.PostMessageW(tray.hwnd, Tray.WM_UPDATE, 0, 0))).start()
    if matter_settings().get("on"):
        tray.matter = matter_start(state, tray.matter_notify)
    if not (args.from_autostart or args.after_update):  # by hand (Start menu, installer): the window. At sign-in
        tray.open_app()  # or after an update (maybe started from Home Assistant): in the background
    tray.loop()
    k32.SetEvent(stop.h)
    if tray.matter:
        tray.matter.stop()  # phones' apps see Glowback leave the network
    t.join(5)
    for icon in tray.icons:
        user32.DestroyIcon(icon)
    if worker_error:
        raise worker_error[0]


# =============================================================================
# Home Assistant (MQTT discovery), and through it Google Assistant and Alexa
# =============================================================================
HA_PREFIX = "homeassistant"  # Home Assistant's MQTT discovery prefix
HA_EFFECTS = {"Zones": "zones", "Average": "average", "Color": "color", "Gradient": "gradient",
              "Music": "music"}  # light effects <-> Glowback modes
HA_PICTURE = "https://raw.githubusercontent.com/Ilyomix/glowback/main/docs/img/icon-192.png"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data, protect):
    """Encrypts (or decrypts) bytes for the current Windows user: how the MQTT password is kept in settings.json."""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    _sig(fn, wt.BOOL, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
         wt.DWORD, ctypes.POINTER(DATA_BLOB))
    _sig(k32.LocalFree, ctypes.c_void_p, ctypes.c_void_p)
    buf = (ctypes.c_ubyte * max(1, len(data))).from_buffer_copy(data or b"\0")
    blob, out = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))), DATA_BLOB()
    if not fn(byref(blob), None, None, None, None, 0x1, byref(out)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        k32.LocalFree(out.pbData)


def machine_id():
    """Short anonymous id of this PC (a hash of Windows' MachineGuid): MQTT topics and Home Assistant unique ids."""
    import hashlib
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            seed = winreg.QueryValueEx(key, "MachineGuid")[0]
    except OSError:
        seed = os.environ.get("COMPUTERNAME", "windows")
    return hashlib.sha256(f"glowback:{seed}".encode()).hexdigest()[:10]


def ha_settings():
    """The saved Home Assistant connection: dict(host, port, user, password, tls), or None when it isn't set up."""
    import base64
    saved = load_settings().get("home_assistant")
    if not isinstance(saved, dict) or not saved.get("host"):
        return None
    tls = bool(saved.get("tls"))
    cfg = dict(host=str(saved["host"]), port=int(saved.get("port") or (8883 if tls else 1883)),
               user=str(saved.get("user") or ""), password="", tls=tls)
    if saved.get("password"):
        try:
            cfg["password"] = _dpapi(base64.b64decode(saved["password"]), False).decode("utf-8")
        except (OSError, ValueError):  # saved by another Windows account
            log("Home Assistant: the saved password can't be read here, enter it again")
    return cfg


def save_ha_settings(host, port, user, password, tls=False):
    import base64
    secret = base64.b64encode(_dpapi(password.encode("utf-8"), True)).decode("ascii") if password else ""
    save_settings({"home_assistant": dict(host=host, port=port, user=user, password=secret, tls=tls)})


class MqttRefused(OSError):
    """The broker answered CONNECT with an error code (4: bad user name or password, 5: not authorized)."""

    def __init__(self, code):
        super().__init__(f"MQTT connection refused (code {code})")
        self.code = code


class Mqtt:
    """Minimal MQTT 3.1.1 client (QoS 0, keep-alive, last will): all Home Assistant needs, without dependencies."""

    def __init__(self, host, port, user="", password="", tls=False, client_id="glowback", will=None, keepalive=60):
        self.host, self.port, self.user, self.password, self.tls = host, port, user, password, tls
        self.client_id, self.will, self.keepalive = client_id, will, keepalive
        self.sock, self.packet_id, self.last_out, self.ping_sent = None, 0, 0.0, None

    @staticmethod
    def _str(s):
        b = s.encode("utf-8") if isinstance(s, str) else s
        return struct.pack(">H", len(b)) + b

    def _send(self, kind, body=b""):
        n, size = len(body), b""
        while True:  # "remaining length": 7 bits per byte
            n, digit = n >> 7, n & 0x7F
            size += bytes([digit | (0x80 if n else 0)])
            if not n:
                break
        self.sock.sendall(bytes([kind]) + size + body)
        self.last_out = time.monotonic()

    def _recv(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionResetError("the MQTT broker closed the connection")
            data += chunk
        return data

    def _read(self, timeout):
        """Next packet as (first byte, body), or None if nothing arrives within `timeout` seconds."""
        self.sock.settimeout(timeout)
        try:
            first = self.sock.recv(1)
        except (socket.timeout, TimeoutError):
            return None
        if not first:
            raise ConnectionResetError("the MQTT broker closed the connection")
        self.sock.settimeout(10)
        size, shift = 0, 0
        while True:
            byte = self._recv(1)[0]
            size |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
            if shift > 21:
                raise ConnectionResetError("malformed MQTT packet")
        return first[0], self._recv(size)

    def connect(self, timeout=8):
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        if self.tls:
            import ssl
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
        self.sock = sock
        flags, payload = 0x02, self._str(self.client_id)  # clean session
        if self.will:
            flags |= 0x04 | 0x20  # will message, retained
            payload += self._str(self.will[0]) + self._str(self.will[1])
        if self.user:
            flags |= 0x80
            payload += self._str(self.user)
            if self.password:
                flags |= 0x40
                payload += self._str(self.password)
        self._send(0x10, self._str("MQTT") + bytes([4, flags]) + struct.pack(">H", self.keepalive) + payload)
        packet = self._read(timeout)
        if not packet or packet[0] >> 4 != 2 or len(packet[1]) < 2:
            raise ConnectionResetError("no MQTT answer")
        if packet[1][1]:
            raise MqttRefused(packet[1][1])

    def publish(self, topic, payload, retain=False):
        if isinstance(payload, dict):
            payload = json.dumps(payload, separators=(",", ":"))
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self._send(0x30 | (1 if retain else 0), self._str(topic) + payload)

    def subscribe(self, *topics):
        self.packet_id = self.packet_id % 0xFFFF + 1
        self._send(0x82, struct.pack(">H", self.packet_id) + b"".join(self._str(t) + b"\0" for t in topics))

    def poll(self, timeout=0.5):
        """Waits up to `timeout` s for a message: (topic, payload bytes) or None. Keeps the connection alive."""
        now = time.monotonic()
        if self.ping_sent and now - self.ping_sent > self.keepalive:
            raise TimeoutError("the MQTT broker stopped answering")
        if not self.ping_sent and now - self.last_out > self.keepalive / 2:
            self._send(0xC0)  # PINGREQ
            self.ping_sent = now
        packet = self._read(timeout)
        if not packet:
            return None
        kind, body = packet
        if kind >> 4 == 13:  # PINGRESP
            self.ping_sent = None
        elif kind >> 4 == 3 and len(body) >= 2:  # PUBLISH
            n = struct.unpack(">H", body[:2])[0]
            topic, payload = body[2:2 + n].decode("utf-8", "replace"), body[2 + n:]
            if (kind >> 1) & 3:  # QoS 1 or 2 (we subscribe with QoS 0, so only from odd brokers)
                if (kind >> 1) & 3 == 1:
                    self._send(0x40, payload[:2])  # PUBACK
                payload = payload[2:]
            return topic, payload
        return None

    def close(self):
        if self.sock:
            try:
                self._send(0xE0)  # DISCONNECT: no last will
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


def ha_check(cfg, timeout=6):
    """Connects to the broker once with these settings: raises if it fails."""
    client = Mqtt(cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["tls"], f"glowback-{machine_id()}-check")
    try:
        client.connect(timeout)
    finally:
        client.close()


def ha_error_text(e):
    import ssl
    if isinstance(e, MqttRefused):
        return tr("ha_err_login") if e.code in (4, 5) else tr("ha_err_refused")
    if isinstance(e, socket.gaierror):
        return tr("ha_err_address")
    if isinstance(e, ssl.SSLError):
        return tr("ha_err_tls")
    if isinstance(e, (ConnectionRefusedError, socket.timeout, TimeoutError, ConnectionResetError)):
        return tr("ha_err_broker")
    return tr("ha_err_other", error=str(e) or e.__class__.__name__)


class HomeAssistant:
    """Glowback as a device in Home Assistant, through MQTT discovery: a light (ambient light on/off, brightness,
    color, mode as an effect), the number of LEDs and an update entity. Own thread; reconnects and follows the
    settings."""

    def __init__(self, state, stop, notify=lambda: None, install=lambda: None):
        self.state, self.stop, self.notify, self.install = state, stop, notify, install
        self.status, self.error = "off", ""  # off, connecting, connected, error
        self.wake = threading.Event()
        self.node = machine_id()
        self.base = f"glowback/{self.node}"
        self._saved = None

    def start(self):
        threading.Thread(target=self._run, name="glowback-home-assistant", daemon=True).start()
        return self

    def reconfigure(self):
        """The settings changed (panel window, --home-assistant): reconnect now."""
        self.wake.set()

    def _set_status(self, status, error=""):
        if (status, error) != (self.status, self.error):
            self.status, self.error = status, error
            self.notify()

    def _changed(self):
        return json.dumps(load_settings().get("home_assistant"), sort_keys=True) != self._saved

    def _sleep(self, seconds):
        """Waits, but wakes up when Glowback quits or the Home Assistant settings change."""
        end, next_look = time.monotonic() + seconds, time.monotonic() + 2
        while time.monotonic() < end and not self.wake.is_set():
            if self.stop.wait(0.25):
                return
            if time.monotonic() > next_look:
                next_look = time.monotonic() + 2
                if self._changed():
                    return

    def _run(self):
        delay = 2
        while not self.stop.wait(0):
            self.wake.clear()
            self._saved = json.dumps(load_settings().get("home_assistant"), sort_keys=True)
            cfg = ha_settings()
            if not cfg:
                self._set_status("off")
                self._sleep(3600)
                continue
            if self.status != "error":  # retries keep showing the last error until they succeed
                self._set_status("connecting")
            try:
                self._session(cfg)
                delay = 2
            except (OSError, ValueError) as e:
                if self.status != "error" or self.error != ha_error_text(e):
                    log(f"Home Assistant: {cfg['host']}:{cfg['port']} {e.__class__.__name__}: {e}")
                self._set_status("error", ha_error_text(e))
            if not self.wake.is_set() and not self.stop.wait(0):
                self._sleep(delay)
                delay = min(delay * 2, 60)

    def _session(self, cfg):
        available = self.base + "/availability"
        client = Mqtt(cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["tls"], f"glowback-{self.node}",
                      will=(available, "offline"))
        client.connect()
        try:
            client.subscribe(self.base + "/set", self.base + "/update/install", HA_PREFIX + "/status")
            self._announce(client)
            self._set_status("connected")
            log(f"Home Assistant: connected to {cfg['host']}:{cfg['port']}")
            seen, next_look = None, time.monotonic() + 2
            while not self.stop.wait(0) and not self.wake.is_set():
                message = client.poll(0.5)
                if message:
                    self._handle(client, *message)
                s = self.state
                now = (s.version, s.leds, s.new_version)
                if now != seen:  # changed in the panel, by a new device, or a new version is out
                    seen = now
                    self._publish_state(client)
                if time.monotonic() > next_look:
                    next_look = time.monotonic() + 2
                    if self._changed():
                        break
            if not ha_settings():  # disconnected from the panel: remove Glowback from Home Assistant
                self._forget(client)
            else:
                client.publish(available, "offline", retain=True)
        finally:
            client.close()

    def _device(self):
        return {"identifiers": [f"glowback_{self.node}"], "name": "Glowback", "manufacturer": AUTHOR,
                "model": f"Glowback ({os.environ.get('COMPUTERNAME', 'Windows')})", "sw_version": __version__,
                "configuration_url": REPO_URL}

    def _configs(self):
        """Discovery config of each entity, by component."""
        common = dict(availability_topic=self.base + "/availability", device=self._device(),
                      origin={"name": "Glowback", "sw_version": __version__, "support_url": REPO_URL})
        return {
            "light": dict(name=None, unique_id=f"glowback_{self.node}", icon="mdi:television-ambient-light",
                          schema="json", command_topic=self.base + "/set", state_topic=self.base + "/state",
                          brightness=True, brightness_scale=100, supported_color_modes=["rgb"],
                          effect=True, effect_list=list(HA_EFFECTS), **common),
            "sensor": dict(name="LEDs", unique_id=f"glowback_{self.node}_leds", icon="mdi:led-strip-variant",
                           state_topic=self.base + "/state", value_template="{{ value_json.leds }}",
                           state_class="measurement", entity_category="diagnostic", **common),
            "update": dict(name=None, unique_id=f"glowback_{self.node}_update", state_topic=self.base + "/update",
                           command_topic=self.base + "/update/install", payload_install="install",
                           entity_picture=HA_PICTURE, **common),
        }

    def _announce(self, client):
        for component, config in self._configs().items():
            client.publish(f"{HA_PREFIX}/{component}/glowback_{self.node}/config", config, retain=True)
        client.publish(self.base + "/availability", "online", retain=True)
        self._publish_state(client)

    def _forget(self, client):
        for component in self._configs():
            client.publish(f"{HA_PREFIX}/{component}/glowback_{self.node}/config", b"", retain=True)
        for topic in ("/state", "/update", "/availability"):
            client.publish(self.base + topic, b"", retain=True)
        log("Home Assistant: Glowback removed")

    def _publish_state(self, client):
        s = self.state
        effect = next((k for k, v in HA_EFFECTS.items() if v == s.mode), "Zones")
        client.publish(self.base + "/state", {"state": "ON" if s.lit() else "OFF", "brightness": round(s.brightness),
                                              "effect": effect, "color_mode": "rgb",
                                              "color": dict(zip("rgb", rgb(s.color))), "leds": s.leds}, retain=True)
        client.publish(self.base + "/update", {"installed_version": __version__,
                                               "latest_version": s.new_version or __version__, "title": "Glowback",
                                               "release_url": REPO_URL + "/releases/latest"}, retain=True)

    def _handle(self, client, topic, payload):
        if topic == self.base + "/set":
            try:
                command = json.loads(payload or b"{}")
            except ValueError:
                return
            change = {}
            if command.get("state") in ("ON", "OFF"):  # off: the LEDs go dark (Glowback's pause gives them back)
                change["enabled"], change["dark"] = True, command["state"] == "OFF"
            if isinstance(command.get("brightness"), (int, float)):
                change["brightness"] = max(1.0, min(100.0, float(command["brightness"])))
            color = command.get("color")
            if isinstance(color, dict) and all(isinstance(color.get(c), (int, float)) for c in "rgb"):
                r, g, b = (max(0, min(255, int(color[c]))) for c in "rgb")
                change["color"], change["mode"] = (r << 16) | (g << 8) | b, "color"  # a color chosen: the color mode
            if command.get("effect") in HA_EFFECTS:
                change["mode"] = HA_EFFECTS[command["effect"]]
            if change:
                log("Home Assistant: " + ", ".join(f"{k} {color_hex(v) if k == 'color' else v}" for k, v in change.items()))
                self.state.update(**change)
                self.notify()
            self._publish_state(client)
        elif topic == self.base + "/update/install" and payload.strip() == b"install":
            self.install()
        elif topic == HA_PREFIX + "/status" and payload.strip() == b"online":  # Home Assistant restarted
            self._announce(client)


def ha_forget_now():
    """Uninstall: remove Glowback from Home Assistant if it was connected (best effort, a few seconds at most)."""
    cfg = ha_settings()
    if not cfg:
        return
    ha = HomeAssistant(types_state(), None)
    client = Mqtt(cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["tls"], f"glowback-{ha.node}")
    try:
        client.connect(4)
        ha._forget(client)
    except OSError:
        pass
    finally:
        client.close()


def types_state():
    """A stand-in State for code that only needs its attributes."""
    import types
    return types.SimpleNamespace(enabled=False, brightness=100, mode="zones", leds=0, new_version=None, version=0)


def cmd_home_assistant(value):
    """glowback --home-assistant mqtt://user:password@host[:port] (mqtts:// for TLS), or off."""
    from urllib.parse import unquote, urlsplit
    if value.strip().lower() in ("off", "none", "no"):
        save_settings({"home_assistant": None})
        print("Home Assistant: off. A running Glowback removes itself from Home Assistant within a few seconds.")
        return
    usage = "usage: glowback --home-assistant mqtt://USER:PASSWORD@HOST[:PORT]   (or off)"
    url = urlsplit(value if "://" in value else "mqtt://" + value)
    try:
        port = url.port
    except ValueError:  # not a number
        sys.exit(usage)
    if url.scheme not in ("mqtt", "mqtts") or not url.hostname:
        sys.exit(usage)
    tls = url.scheme == "mqtts"
    cfg = dict(host=url.hostname, port=port or (8883 if tls else 1883), user=unquote(url.username or ""),
               password=unquote(url.password or ""), tls=tls)
    try:
        ha_check(cfg)
    except Exception as e:
        sys.exit(f"Home Assistant: {ha_error_text(e)}")
    save_ha_settings(cfg["host"], cfg["port"], cfg["user"], cfg["password"], tls)
    print(f"Home Assistant: connected to {cfg['host']}:{cfg['port']} and saved. "
          "Glowback appears in Settings > Devices & services > MQTT while it runs.")


def ha_guide_url():
    if _lang["code"] == "fr":
        return REPO_URL + "/blob/main/README.fr.md#-home-assistant-et-google-assistant"
    return REPO_URL + "#-home-assistant--google-assistant"


_sig(user32.SendMessageW, LRESULT, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
_sig(user32.GetWindowTextLengthW, ctypes.c_int, HANDLE)
_sig(user32.GetWindowTextW, ctypes.c_int, HANDLE, wt.LPWSTR, ctypes.c_int)
_sig(user32.SetWindowTextW, wt.BOOL, HANDLE, wt.LPCWSTR)
_sig(user32.EnableWindow, wt.BOOL, HANDLE, wt.BOOL)
_sig(user32.SetFocus, HANDLE, HANDLE)
_sig(user32.GetFocus, HANDLE)
_sig(user32.IsDialogMessageW, wt.BOOL, HANDLE, ctypes.POINTER(wt.MSG))
_sig(user32.SetCursor, HANDLE, HANDLE)
_sig(user32.ScreenToClient, wt.BOOL, HANDLE, ctypes.POINTER(wt.POINT))
_sig(gdi32.SetBkColor, wt.DWORD, HANDLE, wt.DWORD)


# =============================================================================
# Matter: Glowback as a light in Apple Home, Google Home, Alexa and other Matter apps, from a phone,
# without Home Assistant. Pure Python: P-256, SPAKE2+ and AES-CCM; PASE and CASE sessions; the Interaction Model;
# the clusters of an extended color light; DNS-SD. Glowback answers on UDP port 5540 of this PC's network.
# =============================================================================
MATTER_VID, MATTER_PID = 0xFFF1, 0x8000  # the test vendor and product IDs of uncertified Matter devices
MATTER_PATH = os.path.join(LOG_DIR, "matter.json")
MATTER_VENDORS = {0x1349: "matter_apple_home", 0x1384: "Apple (iOS)", 0x6006: "Google Home", 0x1217: "Amazon Alexa",
                  0x134B: "Home Assistant"}  # who pairs: Matter vendor IDs (matter_*: a translated name)
# The Matter SDK's test attestation credentials (github.com/project-chip/connectedhomeip, Apache License 2.0), which
# uncertified Matter devices use: Apple Home calls Glowback an "uncertified accessory", and Google Home needs a test
# setup in its developer console (see the README).
MATTER_DAC = ("MIIB6TCCAY6gAwIBAgIII4pke7xMMN0wCgYIKoZIzj0EAwIwPTElMCMGA1UEAwwcTWF0dGVyIERldiBQQUkgMHhGRkYxIG5vIFBJRDEUMBIGCisG"
    "AQQBgqJ8AgEMBEZGRjEwIBcNMjIwMjA1MDAwMDAwWhgPOTk5OTEyMzEyMzU5NTlaMFMxJTAjBgNVBAMMHE1hdHRlciBEZXYgREFDIDB4RkZGMS8w"
    "eDgwMDAxFDASBgorBgEEAYKifAIBDARGRkYxMRQwEgYKKwYBBAGConwCAgwEODAwMDBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABGLbFrreoyam"
    "24SBSgY/xsfp4rEBtyFkjrpOWshA9dowHuYYEk60GA4vw6IEelZLqbz6C/cfYM6JMPHn9m7I1yijYDBeMAwGA1UdEwEB/wQCMAAwDgYDVR0PAQH/"
    "BAQDAgeAMB0GA1UdDgQWBBS897AHSXBjYGomvk4IfFlWh3RaWjAfBgNVHSMEGDAWgBRjVA5H9kscONE4hKRi0WwZXY/7PDAKBggqhkjOPQQDAgNJ"
    "ADBGAiEAl5cR7J52GM5BgBEywlDbcHZ0YwzVjBLG4jFfCNAe4XgCIQDs/BMGvSoTPRIqJ4YQ6j3KR/BceouAX6ccb/QVOKhkyA==")
MATTER_DAC_KEY = ("MHcCAQEEIMzPnccFDvXZC+RXB7kOH4ddWb4fqULo7S5CcgP2wu49oAoGCCqGSM49AwEHoUQDQgAEYtsWut6jJqbbhIFKBj/Gx+nisQG3IWSOuk5a"
    "yED12jAe5hgSTrQYDi/DogR6VkupvPoL9x9gzokw8ef2bsjXKA==")
MATTER_PAI = ("MIIByzCCAXGgAwIBAgIIVq2CIq2UW2QwCgYIKoZIzj0EAwIwMDEYMBYGA1UEAwwPTWF0dGVyIFRlc3QgUEFBMRQwEgYKKwYBBAGConwCAQwERkZG"
    "MTAgFw0yMjAyMDUwMDAwMDBaGA85OTk5MTIzMTIzNTk1OVowPTElMCMGA1UEAwwcTWF0dGVyIERldiBQQUkgMHhGRkYxIG5vIFBJRDEUMBIGCisG"
    "AQQBgqJ8AgEMBEZGRjEwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAARBmpMVwhc+DIyHbQPM/JRIUmR/f+xeUIL0BZko7KiUxZQVEwmsYx5MsDOS"
    "r2hLC6+35ls7gWLC9Sv5MbjneqqCo2YwZDASBgNVHRMBAf8ECDAGAQH/AgEAMA4GA1UdDwEB/wQEAwIBBjAdBgNVHQ4EFgQUY1QOR/ZLHDjROISk"
    "YtFsGV2P+zwwHwYDVR0jBBgwFoAUav0idx9RH+y/FkGXZxDc3DGhcX4wCgYIKoZIzj0EAwIDSAAwRQIhALLvJ/Sa6bUPuR7qyUxNC9u415KcbLiP"
    "rOUpNo0SBUwMAiBlXckrhr2QmIKmxiF3uCXX0F7b58Ivn+pxIg5+pwP4kQ==")
MATTER_CD = ("MIICFwYJKoZIhvcNAQcCoIICCDCCAgQCAQMxDTALBglghkgBZQMEAgEwggFwBgkqhkiG9w0BBwGgggFhBIIBXRUkAAElAfH/NgIFAIAFAYAFAoAF"
    "A4AFBIAFBYAFBoAFB4AFCIAFCYAFCoAFC4AFDIAFDYAFDoAFD4AFEIAFEYAFEoAFE4AFFIAFFYAFFoAFF4AFGIAFGYAFGoAFG4AFHIAFHYAFHoAF"
    "H4AFIIAFIYAFIoAFI4AFJIAFJYAFJoAFJ4AFKIAFKYAFKoAFK4AFLIAFLYAFLoAFL4AFMIAFMYAFMoAFM4AFNIAFNYAFNoAFN4AFOIAFOYAFOoAF"
    "O4AFPIAFPYAFPoAFP4AFQIAFQYAFQoAFQ4AFRIAFRYAFRoAFR4AFSIAFSYAFSoAFS4AFTIAFTYAFToAFT4AFUIAFUYAFUoAFU4AFVIAFVYAFVoAF"
    "V4AFWIAFWYAFWoAFW4AFXIAFXYAFXoAFX4AFYIAFYYAFYoAFY4AYJAMWLAQTQ1NBMDAwMDBTV0MwMDAwMC0wMCQFACQGACQHASQIABgxfDB6AgED"
    "gBT+ND+VmUd2O2HuRTkTEzhJT+Z9jjALBglghkgBZQMEAgEwCgYIKoZIzj0EAwIERjBEAiBKEvjUL5AjXAWncSHL664V1ZAUZVjpybR6Gjj3o2p9"
    "xQIgIKR0KJfDCu2gpWs24U67yFu9t0ST+ZNYHrBETtbKlAs=")


# Matter cryptography, pure Python: P-256 (ECDSA, ECDH), SPAKE2+ (verifier side), AES-128-CCM, HKDF-SHA256.
# Slow next to C, fast enough for a light: a few handshakes and small messages.

# ---- P-256 (secp256r1)
P256_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
P256_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
P256_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
          0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _jdouble(pt):
    x, y, z = pt
    if not y:
        return (0, 1, 0)
    p = P256_P
    delta, gamma = z * z % p, y * y % p
    beta, alpha = x * gamma % p, 3 * (x - delta) * (x + delta) % p
    x3 = (alpha * alpha - 8 * beta) % p
    z3 = ((y + z) * (y + z) - gamma - delta) % p
    y3 = (alpha * (4 * beta - x3) - 8 * gamma * gamma) % p
    return (x3, y3, z3)


def _jadd(a, b):
    if not a[2]:
        return b
    if not b[2]:
        return a
    p = P256_P
    x1, y1, z1 = a
    x2, y2, z2 = b
    z1z1, z2z2 = z1 * z1 % p, z2 * z2 % p
    u1, u2 = x1 * z2z2 % p, x2 * z1z1 % p
    s1, s2 = y1 * z2 * z2z2 % p, y2 * z1 * z1z1 % p
    h, r = (u2 - u1) % p, (s2 - s1) % p
    if not h:
        return _jdouble(a) if not r else (0, 1, 0)
    hh = h * h % p
    hhh, v = h * hh % p, u1 * hh % p
    x3 = (r * r - hhh - 2 * v) % p
    y3 = (r * (v - x3) - s1 * hhh) % p
    return (x3, y3, z1 * z2 * h % p)


def _affine(pt):
    if not pt[2]:
        raise ValueError("point at infinity")
    zi = pow(pt[2], -1, P256_P)
    zi2 = zi * zi % P256_P
    return (pt[0] * zi2 % P256_P, pt[1] * zi2 * zi % P256_P)


def ec_mul(k, point=P256_G):
    """k * point (affine in and out)."""
    k %= P256_N
    if not k:
        raise ValueError("zero scalar")
    acc, add = (0, 1, 0), (point[0], point[1], 1)
    while k:
        if k & 1:
            acc = _jadd(acc, add)
        add = _jdouble(add)
        k >>= 1
    return _affine(acc)


def ec_add(a, b):
    return _affine(_jadd((a[0], a[1], 1), (b[0], b[1], 1)))


def ec_neg(a):
    return (a[0], (-a[1]) % P256_P)


def on_curve(pt):
    x, y = pt
    return 0 <= x < P256_P and 0 <= y < P256_P and (y * y - x * x * x + 3 * x - P256_B) % P256_P == 0


def ec_encode(pt):
    return b"\x04" + pt[0].to_bytes(32, "big") + pt[1].to_bytes(32, "big")


def ec_decode(data):
    """Uncompressed (04) or compressed (02/03) P-256 point, checked to be on the curve."""
    if len(data) == 65 and data[0] == 4:
        pt = (int.from_bytes(data[1:33], "big"), int.from_bytes(data[33:], "big"))
    elif len(data) == 33 and data[0] in (2, 3):
        x = int.from_bytes(data[1:], "big")
        y = pow((x * x * x - 3 * x + P256_B) % P256_P, (P256_P + 1) // 4, P256_P)
        if (y & 1) != (data[0] & 1):
            y = P256_P - y
        pt = (x, y)
    else:
        raise ValueError("bad P-256 point")
    if not on_curve(pt):
        raise ValueError("point not on P-256")
    return pt


def ec_keypair():
    d = int.from_bytes(os.urandom(40), "big") % (P256_N - 1) + 1
    return d, ec_mul(d)


def ecdh(d, peer_pub):
    """Shared secret: the x coordinate of d * peer (32 bytes)."""
    return ec_mul(d, ec_decode(peer_pub) if isinstance(peer_pub, (bytes, bytearray)) else peer_pub)[0].to_bytes(32, "big")


def ecdsa_sign(d, msg):
    """ECDSA-SHA256 with the private key d: r || s, 64 bytes."""
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    while True:
        k = int.from_bytes(os.urandom(40), "big") % (P256_N - 1) + 1
        r = ec_mul(k)[0] % P256_N
        s = pow(k, -1, P256_N) * (e + r * d) % P256_N
        if r and s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def ecdsa_verify(pub, msg, sig):
    """pub: point or encoded; sig: r || s (64 bytes)."""
    if len(sig) != 64:
        return False
    pt = ec_decode(pub) if isinstance(pub, (bytes, bytearray)) else pub
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if not (0 < r < P256_N and 0 < s < P256_N):
        return False
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    w = pow(s, -1, P256_N)
    acc = _jadd(_jmul(e * w % P256_N, P256_G), _jmul(r * w % P256_N, pt))
    if not acc[2]:
        return False
    return _affine(acc)[0] % P256_N == r


def _jmul(k, point):
    acc, add = (0, 1, 0), (point[0], point[1], 1)
    while k:
        if k & 1:
            acc = _jadd(acc, add)
        add = _jdouble(add)
        k >>= 1
    return acc


def der_sig(rs):
    """r || s -> DER ECDSA-Sig-Value."""
    def integer(v):
        v = v.lstrip(b"\x00") or b"\x00"
        if v[0] & 0x80:
            v = b"\x00" + v
        return b"\x02" + bytes([len(v)]) + v
    body = integer(rs[:32]) + integer(rs[32:])
    return b"\x30" + bytes([len(body)]) + body


def raw_sig(der):
    """DER ECDSA-Sig-Value -> r || s."""
    if der[0] != 0x30:
        raise ValueError("bad signature")
    i, out = 2, b""
    for _ in range(2):
        if der[i] != 2:
            raise ValueError("bad signature")
        n = der[i + 1]
        out += int.from_bytes(der[i + 2:i + 2 + n], "big").to_bytes(32, "big")
        i += 2 + n
    return out


# ---- HKDF-SHA256, HMAC
def hmac256(key, msg):
    return hmac.new(key, msg, hashlib.sha256).digest()


def hkdf(ikm, salt, info, length):
    prk = hmac256(salt or b"\x00" * 32, ikm)
    out, t, i = b"", b"", 1
    while len(out) < length:
        t = hmac256(prk, t + info + bytes([i]))
        out += t
        i += 1
    return out[:length]


# ---- SPAKE2+ (P-256, SHA-256, HKDF, HMAC), as Matter uses it: the device is the verifier
SPAKE_M = bytes.fromhex("02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f")
SPAKE_N = bytes.fromhex("03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49")


def pase_verifier(passcode, salt, iterations):
    """(w0, L) from the setup passcode: what the device keeps instead of the passcode."""
    ws = hashlib.pbkdf2_hmac("sha256", passcode.to_bytes(4, "little"), salt, iterations, 80)
    w0, w1 = int.from_bytes(ws[:40], "big") % P256_N, int.from_bytes(ws[40:], "big") % P256_N
    return w0, ec_encode(ec_mul(w1))


class Spake2pVerifier:
    """One SPAKE2+ exchange: X (from the commissioner) -> Y and cB; then cA is checked; Ke is the shared key."""

    def __init__(self, context, w0, L, prover_id=b"", verifier_id=b"", y=None):
        self.context, self.w0, self.L = context, w0, ec_decode(L)
        self.ids = prover_id, verifier_id
        self.y = y or int.from_bytes(os.urandom(40), "big") % (P256_N - 1) + 1

    def respond(self, X):
        Xp = ec_decode(X)
        M, N = ec_decode(SPAKE_M), ec_decode(SPAKE_N)
        Y = ec_encode(ec_add(ec_mul(self.y), ec_mul(self.w0, N)))
        Z = ec_encode(ec_mul(self.y, ec_add(Xp, ec_neg(ec_mul(self.w0, M)))))
        V = ec_encode(ec_mul(self.y, self.L))
        tt = b""
        for part in (self.context, self.ids[0], self.ids[1], ec_encode(M), ec_encode(N), X, Y, Z, V,
                     self.w0.to_bytes(32, "big")):
            tt += len(part).to_bytes(8, "little") + part
        k = hashlib.sha256(tt).digest()
        self.Ka, self.Ke = k[:16], k[16:]
        kc = hkdf(self.Ka, b"", b"ConfirmationKeys", 32)
        self.KcA, self.KcB = kc[:16], kc[16:]
        self.Y, self.Z, self.V = Y, Z, V
        self.expected_cA = hmac256(self.KcA, Y)
        return Y, hmac256(self.KcB, X)

    def check(self, cA):
        return hmac.compare_digest(cA, self.expected_cA)


# ---- AES-128 (encryption only: CTR and CBC-MAC need nothing else) and AES-CCM
_AES_SBOX = bytearray(256)
_aes_p = _aes_q = 1
while True:  # the S-box from GF(2^8) inverses and the affine map
    _aes_p = _aes_p ^ ((_aes_p << 1) & 0xFF) ^ (0x1B if _aes_p & 0x80 else 0)
    _aes_q ^= _aes_q << 1
    _aes_q ^= _aes_q << 2
    _aes_q ^= _aes_q << 4
    _aes_q &= 0xFF
    if _aes_q & 0x80:
        _aes_q ^= 0x09
    _aes_x = _aes_q ^ ((_aes_q << 1) | (_aes_q >> 7)) & 0xFF ^ ((_aes_q << 2) | (_aes_q >> 6)) & 0xFF ^ ((_aes_q << 3) | (_aes_q >> 5)) & 0xFF \
        ^ ((_aes_q << 4) | (_aes_q >> 4)) & 0xFF
    _AES_SBOX[_aes_p] = (_aes_x ^ 0x63) & 0xFF
    if _aes_p == 1:
        break
_AES_SBOX[0] = 0x63


def _aes_xt(b):
    return ((b << 1) ^ 0x1B) & 0xFF if b & 0x80 else b << 1


_AES_T0 = [0] * 256  # round tables: SubBytes + ShiftRows + MixColumns as lookups
for _aes_i in range(256):
    _aes_s = _AES_SBOX[_aes_i]
    _aes_s2 = _aes_xt(_aes_s)
    _AES_T0[_aes_i] = (_aes_s2 << 24) | (_aes_s << 16) | (_aes_s << 8) | (_aes_s2 ^ _aes_s)
_AES_T1 = [((t >> 8) | (t << 24)) & 0xFFFFFFFF for t in _AES_T0]
_AES_T2 = [((t >> 16) | (t << 16)) & 0xFFFFFFFF for t in _AES_T0]
_AES_T3 = [((t >> 24) | (t << 8)) & 0xFFFFFFFF for t in _AES_T0]


class AES128:
    def __init__(self, key):
        w = [int.from_bytes(key[i:i + 4], "big") for i in range(0, 16, 4)]
        rcon = 1
        for i in range(4, 44):
            t = w[i - 1]
            if i % 4 == 0:
                t = ((_AES_SBOX[(t >> 16) & 0xFF] << 24) | (_AES_SBOX[(t >> 8) & 0xFF] << 16) | (_AES_SBOX[t & 0xFF] << 8)
                     | _AES_SBOX[t >> 24]) ^ (rcon << 24)
                rcon = _aes_xt(rcon)
            w.append(w[i - 4] ^ t)
        self.rk = w

    def encrypt_block(self, block):
        rk = self.rk
        s0, s1, s2, s3 = (int.from_bytes(block[i:i + 4], "big") ^ rk[i // 4] for i in range(0, 16, 4))
        T0, T1, T2, T3 = _AES_T0, _AES_T1, _AES_T2, _AES_T3
        for r in range(1, 10):
            k = 4 * r
            s0, s1, s2, s3 = (
                T0[s0 >> 24] ^ T1[(s1 >> 16) & 0xFF] ^ T2[(s2 >> 8) & 0xFF] ^ T3[s3 & 0xFF] ^ rk[k],
                T0[s1 >> 24] ^ T1[(s2 >> 16) & 0xFF] ^ T2[(s3 >> 8) & 0xFF] ^ T3[s0 & 0xFF] ^ rk[k + 1],
                T0[s2 >> 24] ^ T1[(s3 >> 16) & 0xFF] ^ T2[(s0 >> 8) & 0xFF] ^ T3[s1 & 0xFF] ^ rk[k + 2],
                T0[s3 >> 24] ^ T1[(s0 >> 16) & 0xFF] ^ T2[(s1 >> 8) & 0xFF] ^ T3[s2 & 0xFF] ^ rk[k + 3])
        S = _AES_SBOX
        out = b""
        for i, (a, b, c, d) in enumerate(((s0, s1, s2, s3), (s1, s2, s3, s0), (s2, s3, s0, s1), (s3, s0, s1, s2))):
            v = (S[a >> 24] << 24) | (S[(b >> 16) & 0xFF] << 16) | (S[(c >> 8) & 0xFF] << 8) | S[d & 0xFF]
            out += (v ^ rk[40 + i]).to_bytes(4, "big")
        return out


def _xor_bytes(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")


def _ccm_mac(aes, nonce, data, aad, mic_len):
    """(tag before encryption, keystream for data) for AES-CCM with a 13-byte nonce (L = 2)."""
    q = 15 - len(nonce)
    b0 = bytes([(0x40 if aad else 0) | ((mic_len - 2) // 2) << 3 | (q - 1)]) + nonce + len(data).to_bytes(q, "big")
    mac = aes.encrypt_block(b0)
    if aad:
        a = len(aad).to_bytes(2, "big") + aad
        a += b"\x00" * (-len(a) % 16)
        for i in range(0, len(a), 16):
            mac = aes.encrypt_block(_xor_bytes(mac, a[i:i + 16]))
    return mac, q


def ccm_encrypt(key, nonce, plaintext, aad=b"", mic_len=16):
    aes = AES128(key)
    mac, q = _ccm_mac(aes, nonce, plaintext, aad, mic_len)
    padded = plaintext + b"\x00" * (-len(plaintext) % 16)
    for i in range(0, len(padded), 16):
        mac = aes.encrypt_block(_xor_bytes(mac, padded[i:i + 16]))
    out = bytearray()
    for i in range(0, len(plaintext), 16):
        ks = aes.encrypt_block(bytes([q - 1]) + nonce + (i // 16 + 1).to_bytes(q, "big"))
        chunk = plaintext[i:i + 16]
        out += _xor_bytes(chunk, ks[:len(chunk)])
    s0 = aes.encrypt_block(bytes([q - 1]) + nonce + b"\x00" * q)
    return bytes(out) + _xor_bytes(mac[:mic_len], s0[:mic_len])


def ccm_decrypt(key, nonce, data, aad=b"", mic_len=16):
    """The plaintext, or None if the message was altered."""
    if len(data) < mic_len:
        return None
    aes = AES128(key)
    q = 15 - len(nonce)
    ct, tag = data[:-mic_len], data[-mic_len:]
    out = bytearray()
    for i in range(0, len(ct), 16):
        ks = aes.encrypt_block(bytes([q - 1]) + nonce + (i // 16 + 1).to_bytes(q, "big"))
        chunk = ct[i:i + 16]
        out += _xor_bytes(chunk, ks[:len(chunk)])
    pt = bytes(out)
    mac, _ = _ccm_mac(aes, nonce, pt, aad, mic_len)
    padded = pt + b"\x00" * (-len(pt) % 16)
    for i in range(0, len(padded), 16):
        mac = aes.encrypt_block(_xor_bytes(mac, padded[i:i + 16]))
    s0 = aes.encrypt_block(bytes([q - 1]) + nonce + b"\x00" * q)
    return pt if hmac.compare_digest(_xor_bytes(mac[:mic_len], s0[:mic_len]), tag) else None


# Matter TLV (Core spec, appendix A) and Matter operational certificates (chapter 6.5): TLV <-> X.509 for checking
# signatures, the CSR a device sends, the DAC key.



class TlvSigned(int):
    """A signed TLV integer (plain non-negative ints are encoded unsigned)."""


class TlvFloat32(float):
    """A 4-byte TLV float (plain floats are 8 bytes)."""


class TList(list):
    """A TLV list: ordered (tag, value) pairs, tags may repeat (paths, certificate names)."""

    def get(self, tag, default=None):
        for t, v in self:
            if t == tag:
                return v
        return default


class TlvArray(list):
    """A TLV array: anonymous elements (a plain Python list is also encoded as an array)."""


def _tlv_int(v, signed):
    for n, code in ((1, 0), (2, 1), (4, 2), (8, 3)):
        lo, hi = (-(1 << (8 * n - 1)), (1 << (8 * n - 1)) - 1) if signed else (0, (1 << (8 * n)) - 1)
        if lo <= v <= hi:
            return code, v.to_bytes(n, "little", signed=signed)
    raise ValueError(f"integer too large for TLV: {v}")


def _tlv_tag(tag):
    if tag is None:
        return 0x00, b""
    if isinstance(tag, int) and 0 <= tag <= 255:
        return 0x20, bytes([tag])
    if isinstance(tag, tuple):  # (vendor, profile, number): fully qualified
        vendor, profile, number = tag
        if number <= 0xFFFF:
            return 0xC0, struct.pack("<HHH", vendor, profile, number)
        return 0xE0, struct.pack("<HHI", vendor, profile, number)
    raise ValueError(f"unsupported TLV tag {tag!r}")


def tlv_encode(value, tag=None):
    tc, tb = _tlv_tag(tag)
    if value is None:
        return bytes([tc | 0x14]) + tb
    if value is True or value is False:
        return bytes([tc | (0x09 if value else 0x08)]) + tb
    if isinstance(value, int):
        signed = isinstance(value, TlvSigned) or value < 0
        code, b = _tlv_int(int(value), signed)
        return bytes([tc | (code if signed else 4 + code)]) + tb + b
    if isinstance(value, TlvFloat32):
        return bytes([tc | 0x0A]) + tb + struct.pack("<f", value)
    if isinstance(value, float):
        return bytes([tc | 0x0B]) + tb + struct.pack("<d", value)
    if isinstance(value, (bytes, bytearray, str)):
        data = value.encode() if isinstance(value, str) else bytes(value)
        base = 0x0C if isinstance(value, str) else 0x10
        code, ln = _tlv_int(len(data), False)
        return bytes([tc | (base + code)]) + tb + ln + data
    if isinstance(value, dict):
        return bytes([tc | 0x15]) + tb + b"".join(tlv_encode(v, k) for k, v in value.items()) + b"\x18"
    if isinstance(value, TList):
        return bytes([tc | 0x17]) + tb + b"".join(tlv_encode(v, k) for k, v in value) + b"\x18"
    if isinstance(value, (list, tuple)):
        return bytes([tc | 0x16]) + tb + b"".join(tlv_encode(v) for v in value) + b"\x18"
    if isinstance(value, TlvRaw):
        return value.with_tag(tc, tb)
    raise TypeError(f"cannot encode {type(value).__name__} as TLV")


class TlvRaw:
    """Already-encoded TLV (anonymous): inserted as is, under the tag it is given."""

    def __init__(self, data):
        self.data = data

    def with_tag(self, tc, tb):
        return bytes([self.data[0] | tc]) + tb + self.data[1:]


class _TlvReader:
    def __init__(self, data, pos=0):
        self.d, self.i = data, pos

    def take(self, n):
        if self.i + n > len(self.d):
            raise ValueError("truncated TLV")
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def element(self):
        """(tag, value), or (END, None) at the end of a container."""
        ctrl = self.take(1)[0]
        typ, tcode = ctrl & 0x1F, ctrl >> 5
        if typ == 0x18:
            return _TLV_END, None
        if tcode == 0:
            tag = None
        elif tcode == 1:
            tag = self.take(1)[0]
        elif tcode in (2, 4):
            tag = ("common" if tcode == 2 else "implicit", struct.unpack("<H", self.take(2))[0])
        elif tcode in (3, 5):
            tag = ("common" if tcode == 3 else "implicit", struct.unpack("<I", self.take(4))[0])
        elif tcode == 6:
            tag = struct.unpack("<HHH", self.take(6))
        else:
            tag = struct.unpack("<HHI", self.take(8))
        if typ <= 0x07:
            n = 1 << (typ & 3)
            return tag, int.from_bytes(self.take(n), "little", signed=typ < 4)
        if typ in (0x08, 0x09):
            return tag, typ == 0x09
        if typ == 0x0A:
            return tag, struct.unpack("<f", self.take(4))[0]
        if typ == 0x0B:
            return tag, struct.unpack("<d", self.take(8))[0]
        if 0x0C <= typ <= 0x13:
            n = int.from_bytes(self.take(1 << (typ & 3)), "little")
            raw = self.take(n)
            return tag, (raw.decode("utf-8", "replace") if typ < 0x10 else bytes(raw))
        if typ == 0x14:
            return tag, None
        if typ == 0x15:
            out = {}
            while True:
                t, v = self.element()
                if t is _TLV_END:
                    return tag, out
                out[t] = v
        if typ == 0x16:
            out = TlvArray()
            while True:
                t, v = self.element()
                if t is _TLV_END:
                    return tag, out
                out.append(v)
        if typ == 0x17:
            out = TList()
            while True:
                t, v = self.element()
                if t is _TLV_END:
                    return tag, out
                out.append((t, v))
        raise ValueError(f"bad TLV element type {typ:#x}")


_TLV_END = object()


def tlv_decode(data):
    """The first (anonymous) element of data."""
    return _TlvReader(data).element()[1]


def tlv_decode_all(data):
    r, out = _TlvReader(data), []
    while r.i < len(data):
        out.append(r.element())
    return out


# ---- DER (just what certificates and CSRs need)
def _der_len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def der(tag, *parts):
    body = b"".join(parts)
    return bytes([tag]) + _der_len(len(body)) + body


def der_oid(dotted):
    nums = [int(x) for x in dotted.split(".")]
    out = bytes([40 * nums[0] + nums[1]])
    for n in nums[2:]:
        chunk = [n & 0x7F]
        n >>= 7
        while n:
            chunk.append(0x80 | (n & 0x7F))
            n >>= 7
        out += bytes(reversed(chunk))
    return der(0x06, out)


def der_int(value_bytes):
    """INTEGER from big-endian content bytes, normalized."""
    v = value_bytes.lstrip(b"\x00") or b"\x00"
    if v[0] & 0x80:
        v = b"\x00" + v
    return der(0x02, v)


def der_parse(data, pos=0):
    """(tag, content, next position)."""
    tag, n = data[pos], data[pos + 1]
    pos += 2
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(data[pos:pos + k], "big")
        pos += k
    return tag, data[pos:pos + n], pos + n


def der_items(content):
    out, pos = [], 0
    while pos < len(content):
        tag, body, nxt = der_parse(content, pos)
        out.append((tag, body, content[pos:nxt]))
        pos = nxt
    return out


OID_ECDSA_SHA256 = "1.2.840.10045.4.3.2"
OID_EC_PUBKEY = "1.2.840.10045.2.1"
OID_P256 = "1.2.840.10045.3.1.7"
_DN_OIDS = {1: "2.5.4.3", 2: "2.5.4.4", 3: "2.5.4.5", 4: "2.5.4.6", 5: "2.5.4.7", 6: "2.5.4.8", 7: "2.5.4.10",
            8: "2.5.4.11", 9: "2.5.4.12", 10: "2.5.4.41", 11: "2.5.4.42", 12: "2.5.4.43", 13: "2.5.4.44",
            14: "2.5.4.46", 15: "2.5.4.65", 16: "0.9.2342.19200300.100.1.25", 17: "1.3.6.1.4.1.37244.1.1",
            18: "1.3.6.1.4.1.37244.1.2", 19: "1.3.6.1.4.1.37244.1.3", 20: "1.3.6.1.4.1.37244.1.4",
            21: "1.3.6.1.4.1.37244.1.5", 22: "1.3.6.1.4.1.37244.1.6"}
_EKU_OIDS = {1: "1.3.6.1.5.5.7.3.1", 2: "1.3.6.1.5.5.7.3.2", 3: "1.3.6.1.5.5.7.3.3", 4: "1.3.6.1.5.5.7.3.4",
             5: "1.3.6.1.5.5.7.3.8", 6: "1.3.6.1.5.5.7.3.9"}
MATTER_EPOCH = 946684800  # 2000-01-01T00:00:00Z


def _cert_dn(name):
    rdns = b""
    for tag, value in name:
        base = tag & 0x7F
        oid = _DN_OIDS.get(base)
        if oid is None:
            raise ValueError(f"unknown DN attribute {tag}")
        if 17 <= base <= 22:  # Matter identifiers: upper-case hex in a UTF8String
            text = f"{value:08X}" if base == 22 else f"{value:016X}"
            val = der(0x0C, text.encode())
        elif base == 16:
            val = der(0x16, value.encode())  # IA5String
        else:
            val = der(0x13 if tag & 0x80 else 0x0C, value.encode())  # PrintableString / UTF8String
        rdns += der(0x31, der(0x30, der_oid(oid), val))
    return der(0x30, rdns)


def _cert_time(t):
    if t == 0:
        return der(0x18, b"99991231235959Z")
    tm = time.gmtime(MATTER_EPOCH + t)
    if 1950 <= tm.tm_year < 2050:
        return der(0x17, time.strftime("%y%m%d%H%M%SZ", tm).encode())
    return der(0x18, time.strftime("%Y%m%d%H%M%SZ", tm).encode())


def _der_bits(flags, count):
    bits = [(flags >> i) & 1 for i in range(count)]
    while bits and not bits[-1]:
        bits.pop()
    nbytes = (len(bits) + 7) // 8
    out = bytearray(nbytes)
    for i, b in enumerate(bits):
        if b:
            out[i // 8] |= 0x80 >> (i % 8)
    return der(0x03, bytes([nbytes * 8 - len(bits)]) + bytes(out))


def _cert_extension(oid, critical, value):
    return der(0x30, der_oid(oid), der(0x01, b"\xff") if critical else b"", der(0x04, value))


def cert_tbs(cert):
    """The X.509 TBSCertificate (DER) a Matter TLV certificate was signed as."""
    exts = b""
    for tag, v in cert.get(10, TList()):
        if tag == 1:
            body = (der(0x01, b"\xff") if v.get(1) else b"") + (der_int(v[2].to_bytes(8, "big")) if 2 in v else b"")
            exts += _cert_extension("2.5.29.19", True, der(0x30, body))
        elif tag == 2:
            exts += _cert_extension("2.5.29.15", True, _der_bits(v, 9))
        elif tag == 3:
            exts += _cert_extension("2.5.29.37", True, der(0x30, *(der_oid(_EKU_OIDS[k]) for k in v)))
        elif tag == 4:
            exts += _cert_extension("2.5.29.14", False, der(0x04, v))
        elif tag == 5:
            exts += _cert_extension("2.5.29.35", False, der(0x30, der(0x80, v)))
        elif tag == 6:
            exts += v  # already a DER Extension
    spki = der(0x30, der(0x30, der_oid(OID_EC_PUBKEY), der_oid(OID_P256)), der(0x03, b"\x00" + cert[9]))
    return der(0x30,
               der(0xA0, der(0x02, b"\x02")),
               der(0x02, cert[1]),  # the serial number's bytes are the INTEGER's content, as is
               der(0x30, der_oid(OID_ECDSA_SHA256)),
               _cert_dn(cert[3]),
               der(0x30, _cert_time(cert[4]), _cert_time(cert[5])),
               _cert_dn(cert[6]),
               spki,
               der(0xA3, der(0x30, exts)))


def cert_parse(data):
    cert = tlv_decode(data)
    if not isinstance(cert, dict) or 9 not in cert or 11 not in cert:
        raise ValueError("not a Matter certificate")
    return cert


def cert_signed_by(cert, issuer_pub):
    return ecdsa_verify(issuer_pub, cert_tbs(cert), cert[11])


def cert_dn_value(name, tag):
    for t, v in name:
        if t == tag:
            return v
    return None


def cert_verify_chain(noc, icac, rcac):
    """Checks a node's operational certificate chain; returns (fabric_id, node_id, cats) of the NOC."""
    root = cert_parse(rcac)
    if not cert_signed_by(root, root[9]):
        raise ValueError("root certificate signature")
    issuer = root
    if icac:
        ica = cert_parse(icac)
        if not cert_signed_by(ica, root[9]):
            raise ValueError("ICAC signature")
        issuer = ica
    node = cert_parse(noc)
    if not cert_signed_by(node, issuer[9]):
        raise ValueError("NOC signature")
    fabric_id, node_id = cert_dn_value(node[6], 21), cert_dn_value(node[6], 17)
    if node_id is None or fabric_id is None:
        raise ValueError("NOC without node or fabric ID")
    for c in (root, issuer):
        f = cert_dn_value(c[6], 21)
        if f is not None and f != fabric_id:
            raise ValueError("fabric ID mismatch")
    cats = [v for t, v in node[6] if t == 22]
    return fabric_id, node_id, cats


# ---- device side: CSR and keys
def matter_csr(d, pub):
    """PKCS#10 certificate request for the operational key (subject O=CSR, as the Matter SDK does)."""
    spki = der(0x30, der(0x30, der_oid(OID_EC_PUBKEY), der_oid(OID_P256)), der(0x03, b"\x00" + ec_encode(pub)))
    subject = der(0x30, der(0x31, der(0x30, der_oid("2.5.4.10"), der(0x0C, b"CSR"))))
    info = der(0x30, der(0x02, b"\x00"), subject, spki, der(0xA0))
    sig = der_sig(ecdsa_sign(d, info))
    return der(0x30, info, der(0x30, der_oid(OID_ECDSA_SHA256)), der(0x03, b"\x00" + sig))


def ec_private_key(der_key):
    """The private scalar of a SEC1 ECPrivateKey (DER)."""
    _, body, _ = der_parse(der_key)
    for tag, content, _ in der_items(body):
        if tag == 0x04 and len(content) == 32:
            return int.from_bytes(content, "big")
    raise ValueError("no private key")


def compressed_fabric_id(root_pub, fabric_id):
    """Key: the root public key without its 04 prefix; salt: the fabric ID (Matter Core 4.3.2.2)."""
    return hkdf(root_pub[1:], fabric_id.to_bytes(8, "big"), b"CompressedFabric", 8)


def operational_ipk(epoch_key, cfid):
    return hkdf(epoch_key, cfid, b"GroupKey v1.0", 16)


def sha256(data):
    return hashlib.sha256(data).digest()


# Matter onboarding payload: the QR code text (MT:...), the 11-digit manual pairing code, and a QR code matrix.

_QR_B38 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-."
MATTER_INVALID_PASSCODES = {0, 11111111, 22222222, 33333333, 44444444, 55555555, 66666666, 77777777, 88888888,
                     99999999, 12345678, 87654321}


def matter_qr_payload(vid, pid, discriminator, passcode, flow=0, discovery=0x04):
    """'MT:' + base-38 of the 88-bit payload (discovery 0x04: already on the IP network)."""
    bits = 0
    pos = 0
    for value, width in ((0, 3), (vid, 16), (pid, 16), (flow, 2), (discovery, 8), (discriminator, 12),
                         (passcode, 27), (0, 4)):
        bits |= (value & ((1 << width) - 1)) << pos
        pos += width
    data = bits.to_bytes(11, "little")
    out = ""
    for i in range(0, len(data), 3):
        chunk = data[i:i + 3]
        v = int.from_bytes(chunk, "little")
        for _ in range({1: 2, 2: 4, 3: 5}[len(chunk)]):
            out += _QR_B38[v % 38]
            v //= 38
    return "MT:" + out


_VERHOEFF_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VERHOEFF_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def _verhoeff(digits):
    c = 0
    for i, d in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(d)]]
    return str(_VERHOEFF_INV[c])


def matter_manual_code(discriminator, passcode):
    """The 11-digit code people can type in Apple Home / Google Home ("XXXX-XXX-XXXX")."""
    short = discriminator >> 8  # the 4 upper bits
    chunk1 = short >> 2
    chunk2 = ((short & 0x3) << 14) | (passcode & 0x3FFF)
    chunk3 = passcode >> 14
    digits = f"{chunk1}{chunk2:05d}{chunk3:04d}"
    return digits + _verhoeff(digits)


# ---- QR code (alphanumeric mode, error correction M, versions 1-5)
_QR_ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
_QR_BLOCKS = {1: (16, 10, 1), 2: (28, 16, 1), 3: (44, 26, 1), 4: (32, 18, 2), 5: (43, 24, 2)}  # data/block, ec/block
_QR_ALIGN = {2: 18, 3: 22, 4: 26, 5: 30}
_QR_EXP = [0] * 512
_QR_LOG = [0] * 256
_qr_x = 1
for _qr_i in range(255):
    _QR_EXP[_qr_i] = _qr_x
    _QR_LOG[_qr_x] = _qr_i
    _qr_x <<= 1
    if _qr_x & 0x100:
        _qr_x ^= 0x11D
for _qr_i in range(255, 512):
    _QR_EXP[_qr_i] = _QR_EXP[_qr_i - 255]


def _qr_rs(data, n):
    gen = [1]
    for i in range(n):
        nxt = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            nxt[j] ^= g
            nxt[j + 1] ^= _QR_EXP[_QR_LOG[g] + i] if g else 0
        gen = nxt
    rem = list(data) + [0] * n
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j in range(1, len(gen)):
                if gen[j]:
                    rem[i + j] ^= _QR_EXP[_QR_LOG[gen[j]] + _QR_LOG[c]]
    return rem[len(data):]


def qr_matrix(text):
    """Rows of booleans (True = dark), quiet zone not included."""
    text = text.upper()
    for version in range(1, 6):
        per, ec, blocks = _QR_BLOCKS[version]
        cap = per * blocks
        bits = 4 + (9 if version < 10 else 11) + 11 * (len(text) // 2) + 6 * (len(text) % 2)
        if bits <= cap * 8:
            break
    else:
        raise ValueError("text too long for this QR encoder")
    buf = [(0b0010, 4), (len(text), 9)]
    for i in range(0, len(text) - 1, 2):
        buf.append((_QR_ALNUM.index(text[i]) * 45 + _QR_ALNUM.index(text[i + 1]), 11))
    if len(text) % 2:
        buf.append((_QR_ALNUM.index(text[-1]), 6))
    s = "".join(format(v, f"0{w}b") for v, w in buf)
    s += "0" * min(4, cap * 8 - len(s))
    s += "0" * (-len(s) % 8)
    data = [int(s[i:i + 8], 2) for i in range(0, len(s), 8)]
    pad = (0xEC, 0x11)
    while len(data) < cap:
        data.append(pad[(len(data) - len(s) // 8) % 2])
    groups = [data[i * per:(i + 1) * per] for i in range(blocks)]
    ecs = [_qr_rs(g, ec) for g in groups]
    final = [g[i] for i in range(per) for g in groups] + [e[i] for i in range(ec) for e in ecs]
    size = 17 + 4 * version
    m = [[None] * size for _ in range(size)]

    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < size and 0 <= cc < size:
                    m[rr][cc] = (0 <= dr <= 6 and dc in (0, 6)) or (0 <= dc <= 6 and dr in (0, 6)) or \
                                (2 <= dr <= 4 and 2 <= dc <= 4)
    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(8, size - 8):
        m[6][i] = m[i][6] = i % 2 == 0
    if version in _QR_ALIGN:
        a = _QR_ALIGN[version]
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                m[a + dr][a + dc] = max(abs(dr), abs(dc)) != 1
    m[size - 8][8] = True  # dark module
    reserved = [[v is not None for v in row] for row in m]
    for i in range(9):  # format areas
        for r, c in ((8, i), (i, 8)):
            reserved[r][c] = True
    for i in range(8):
        reserved[8][size - 1 - i] = reserved[size - 1 - i][8] = True
    bits_out = "".join(format(b, "08b") for b in final)
    idx, up = 0, True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        for k in range(size):
            row = size - 1 - k if up else k
            for c in (col, col - 1):
                if not reserved[row][c]:
                    m[row][c] = idx < len(bits_out) and bits_out[idx] == "1"
                    idx += 1
        up = not up
        col -= 2
    masks = [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0,
             lambda r, c: (r + c) % 3 == 0, lambda r, c: (r // 2 + c // 3) % 2 == 0,
             lambda r, c: (r * c) % 2 + (r * c) % 3 == 0, lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
             lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0]
    best = None
    for mi, mask in enumerate(masks):
        g = [[(not m[r][c]) if (not reserved[r][c] and mask(r, c)) else bool(m[r][c]) for c in range(size)]
             for r in range(size)]
        fmt = (0b00 << 3) | mi  # level M = 00
        rem = fmt << 10
        for i in range(14, 9, -1):
            if rem & (1 << i):
                rem ^= 0x537 << (i - 10)
        fbits = ((fmt << 10) | rem) ^ 0x5412
        bit = lambda i: bool((fbits >> i) & 1)  # noqa: E731
        for i in range(6):  # first copy, around the top-left finder
            g[i][8] = bit(i)
        g[7][8], g[8][8], g[8][7] = bit(6), bit(7), bit(8)
        for i in range(9, 15):
            g[8][14 - i] = bit(i)
        for i in range(8):  # second copy, split between the other two finders
            g[8][size - 1 - i] = bit(i)
        for i in range(8, 15):
            g[size - 15 + i][8] = bit(i)
        g[size - 8][8] = True
        score = _qr_penalty(g)
        if best is None or score < best[0]:
            best = (score, g)
    return best[1]


def _qr_penalty(g):
    n, score = len(g), 0
    for lines in (g, list(zip(*g))):
        for line in lines:
            run, prev = 0, None
            for v in line:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, prev = 1, v
            if run >= 5:
                score += run - 2
    for r in range(n - 1):
        for c in range(n - 1):
            if g[r][c] == g[r][c + 1] == g[r + 1][c] == g[r + 1][c + 1]:
                score += 3
    dark = sum(map(sum, g))
    score += abs(dark * 20 - n * n * 10) // (n * n) * 10
    return score


# A Matter "Extended Color Light" over IP (Ethernet / Wi-Fi), pure Python: MRP transport, PASE and CASE sessions,
# the Interaction Model (read, subscribe, write, invoke, timed), the clusters a light and its commissioning need,
# access control, fail-safe, multi-admin commissioning windows and a small DNS-SD (mDNS) responder.


MATTER_PORT = 5540
DEVICE_TYPE_LIGHT, DEVICE_TYPE_ROOT = 0x010D, 0x0016  # Extended Color Light, Root Node
MATTER_SPEC_VERSION, MATTER_DM_REVISION, IM_REVISION = 0x01030000, 17, 11
MATTER_MAX_FABRICS = 5
PRIV_VIEW, PRIV_OPERATE, PRIV_MANAGE, PRIV_ADMIN = 1, 3, 4, 5
PASE_AUTH, CASE_AUTH, GROUP_AUTH = 1, 2, 3

ST_OK, ST_FAILURE, ST_INVALID_SUBSCRIPTION, ST_UNSUPPORTED_ACCESS, ST_UNSUPPORTED_ENDPOINT = 0x00, 0x01, 0x7D, 0x7E, 0x7F
ST_INVALID_ACTION, ST_UNSUPPORTED_COMMAND, ST_INVALID_COMMAND, ST_UNSUPPORTED_ATTRIBUTE = 0x80, 0x81, 0x85, 0x86
ST_CONSTRAINT_ERROR, ST_UNSUPPORTED_WRITE, ST_RESOURCE_EXHAUSTED, ST_NOT_FOUND = 0x87, 0x88, 0x89, 0x8B
ST_DATA_VERSION_MISMATCH, ST_TIMEOUT, ST_BUSY, ST_UNSUPPORTED_CLUSTER = 0x92, 0x94, 0x9C, 0xC3
ST_NEEDS_TIMED_INTERACTION, ST_TIMED_REQUEST_MISMATCH, ST_FAILSAFE_REQUIRED, ST_INVALID_IN_STATE = 0xC6, 0xC9, 0xCA, 0xCB

PROTO_SC, PROTO_IM = 0x0000, 0x0001  # protocols: secure channel, interaction model
SC_ACK, PBKDF_REQ, PBKDF_RSP, PAKE1, PAKE2, PAKE3 = 0x10, 0x20, 0x21, 0x22, 0x23, 0x24
SIGMA1, SIGMA2, SIGMA3, SIGMA2_RESUME, STATUS_REPORT = 0x30, 0x31, 0x32, 0x33, 0x40
IM_STATUS, IM_READ, IM_SUBSCRIBE, IM_SUBSCRIBE_RSP, IM_REPORT = 0x01, 0x02, 0x03, 0x04, 0x05
IM_WRITE, IM_WRITE_RSP, IM_INVOKE, IM_INVOKE_RSP, IM_TIMED = 0x06, 0x07, 0x08, 0x09, 0x0A

MRP_BASE, MRP_TRIES, MRP_ACK_DELAY = 0.3, 5, 0.2  # retransmission interval (s), transmissions, standalone ack delay
IM_REPORT_BUDGET = 900  # bytes of attribute reports per message (IPv6 minimum MTU 1280)


def _u16(v):
    return struct.pack("<H", v)


def _u32(v):
    return struct.pack("<I", v)


def _u64(v):
    return struct.pack("<Q", v)


class MatterSession:
    def __init__(self, local_id, peer_id, kind, enc, dec, challenge, addr, local_node=0, peer_node=0, fabric=0,
                 cats=()):
        self.local_id, self.peer_id, self.kind = local_id, peer_id, kind
        self.enc, self.dec, self.challenge, self.addr = enc, dec, challenge, addr
        self.local_node, self.peer_node, self.fabric, self.cats = local_node, peer_node, fabric, list(cats)
        self.tx = random.randint(1, 1 << 28)
        self.rx_max, self.rx_bits = None, 0
        self.last = time.monotonic()

    def next_counter(self):
        self.tx = (self.tx + 1) & 0xFFFFFFFF
        return self.tx

    def duplicate(self, ctr):
        if self.rx_max is None or ctr > self.rx_max:
            if self.rx_max is not None:
                shift = ctr - self.rx_max
                self.rx_bits = ((self.rx_bits << shift) | (1 << (shift - 1))) & 0xFFFFFFFF if shift <= 32 else 0
            self.rx_max = ctr
            return False
        d = self.rx_max - ctr
        if d == 0 or d > 32 or self.rx_bits & (1 << (d - 1)):
            return True
        self.rx_bits |= 1 << (d - 1)
        return False


class MatterExchange:
    def __init__(self, key, xid, ours, session, addr, src_node=None):
        self.key, self.xid, self.ours, self.session, self.addr = key, xid, ours, session, addr
        self.src_node = src_node  # unsecured: the initiator's ephemeral node ID
        self.ack, self.ack_due = None, 0.0
        self.pending = None  # our reliable message waiting for its acknowledgement
        self.state = None
        self.timed_until, self.timed = None, False
        self.last = time.monotonic()


class MatterSub:
    def __init__(self, sid, session, paths, min_s, max_s, filtered, fabric, node):
        self.id, self.session, self.paths, self.min, self.max = sid, session, paths, min_s, max_s
        self.filtered, self.fabric, self.node = filtered, fabric, node
        self.dirty = set()
        self.sent = {}  # (endpoint, cluster, attribute): the value last reported
        self.last = time.monotonic()
        self.inflight = False
        self.active = False


class MatterCluster:
    def __init__(self, cid, rev, features=0):
        self.id, self.rev, self.features = cid, rev, features
        self.attrs, self.cmds = {}, {}
        self.version = random.randint(0, 0xFFFFFFFF)

    def attr(self, aid, get, set=None, write=PRIV_OPERATE, read=PRIV_VIEW, fabric=False, sensitive=False, timed=False):
        self.attrs[aid] = dict(get=get, set=set, write=write, read=read, fabric=fabric, sensitive=sensitive,
                               timed=timed)

    def cmd(self, cid, fn, priv=PRIV_OPERATE, timed=False, resp=None):
        self.cmds[cid] = dict(fn=fn, priv=priv, timed=timed, resp=resp)

    def global_value(self, aid):
        if aid == 0xFFF8:
            return sorted({c["resp"] for c in self.cmds.values() if c["resp"] is not None})
        if aid == 0xFFF9:
            return sorted(self.cmds)
        if aid == 0xFFFB:
            return sorted(list(self.attrs) + [0xFFF8, 0xFFF9, 0xFFFB, 0xFFFC, 0xFFFD])
        if aid == 0xFFFC:
            return self.features
        if aid == 0xFFFD:
            return self.rev
        return None


class MatterCtx:
    """Who is asking, over which session."""

    def __init__(self, node, session, filtered=True):
        self.node, self.session, self.filtered = node, session, filtered
        self.fabric = session.fabric if session else 0
        self.after = []  # actions once the response is sent

    @property
    def pase(self):
        return self.session.kind == "pase"


class MatterNode:
    """store: load() -> dict, save(dict), protect(bytes) -> str, unprotect(str) -> bytes.
    light: state() -> dict(on, level, hue, sat, x, y, ct, mode); apply(**changes); identify(seconds).
    info: dict(product, vendor, version, version_int, url)."""

    def __init__(self, store, light, info, attestation, log=print, watch=None, notify=None):
        """watch: returns something that changes when the light changes elsewhere (checked twice a second);
        notify: called when pairing opens or closes, or a controller is added or removed."""
        self.store, self.light, self.info, self.log = store, light, info, log
        self.debug = log if os.environ.get("GLOWBACK_MATTER_DEBUG") else (lambda m: None)
        self.watch, self.notify = watch, notify or (lambda: None)
        self.watched, self.next_watch = watch() if watch else None, 0.0
        self.dac, self.pai, self.cd = attestation["dac"], attestation["pai"], attestation["cd"]
        self.dac_key = ec_private_key(attestation["dac_key"])
        self.vid, self.pid = attestation["vid"], attestation["pid"]
        self.sock = None
        self.mdns = None
        self.sessions, self.exchanges, self.subs = {}, {}, {}
        self.unsec_counter = random.randint(1, 1 << 28)
        self.unsec_seen = {}
        self.next_xid = random.randint(0, 0xFFFF)
        self.failsafe = None
        self.window = None
        self.pase_failures = 0
        self.calls = queue.Queue()
        self.stopping = threading.Event()
        self.thread = None
        self.started = time.monotonic()
        self.identify_until = 0.0
        self.groups = {}
        self._load()
        self._build_model()

    # ---- storage
    def _load(self):
        d = self.store.load() or {}
        self.setup = d.get("setup")
        if not self.setup:
            pin = 0
            while pin in MATTER_INVALID_PASSCODES:
                pin = random.SystemRandom().randint(1, 99999998)
            self.setup = dict(passcode=pin, discriminator=random.SystemRandom().randint(0, 4095),
                              salt=os.urandom(32).hex(), iterations=2000, serial=os.urandom(8).hex().upper(),
                              unique=os.urandom(16).hex().upper(), host=os.urandom(6).hex().upper())
        self.w0, self.L = pase_verifier(self.setup["passcode"], bytes.fromhex(self.setup["salt"]),
                                           self.setup["iterations"])
        self.fabrics = {}
        for f in d.get("fabrics", []):
            fab = dict(index=f["index"], rcac=bytes.fromhex(f["rcac"]), icac=bytes.fromhex(f["icac"]) if f.get("icac")
                       else None, noc=bytes.fromhex(f["noc"]), epoch=bytes.fromhex(f["epoch"]), vendor=f["vendor"],
                       label=f.get("label", ""), key=int.from_bytes(self.store.unprotect(f["key"]), "big"),
                       committed=True)
            self._fabric_ids(fab)
            self.fabrics[fab["index"]] = fab
        self.acl = d.get("acl", [])
        self.node_label = d.get("label", self.info.get("product", "Glowback"))
        self.location = d.get("location", "XX")
        self.regulatory = d.get("regulatory", 0)
        self.reboots = d.get("reboots", 0) + 1
        self._save()

    def _save(self):
        fabrics = [dict(index=f["index"], rcac=f["rcac"].hex(), icac=f["icac"].hex() if f["icac"] else None,
                        noc=f["noc"].hex(), epoch=f["epoch"].hex(), vendor=f["vendor"], label=f["label"],
                        key=self.store.protect(f["key"].to_bytes(32, "big")))
                   for f in self.fabrics.values() if f["committed"]]
        committed = {f["index"] for f in self.fabrics.values() if f["committed"]}
        self.store.save(dict(setup=self.setup, fabrics=fabrics, acl=[a for a in self.acl if a["fabric"] in committed],
                             label=self.node_label, location=self.location, regulatory=self.regulatory,
                             reboots=self.reboots))

    def _fabric_ids(self, fab):
        root = cert_parse(fab["rcac"])
        noc = cert_parse(fab["noc"])
        fab["root_pub"] = root[9]
        fab["fabric_id"] = cert_dn_value(noc[6], 21)
        fab["node_id"] = cert_dn_value(noc[6], 17)
        fab["cfid"] = compressed_fabric_id(fab["root_pub"], fab["fabric_id"])
        fab["ipk"] = operational_ipk(fab["epoch"], fab["cfid"])

    # ---- public API (any thread)
    def start(self):
        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (AttributeError, OSError):
            pass
        self.sock.bind(("::", MATTER_PORT))
        self.mdns = Mdns(self.setup["host"], self.log, self.debug)
        self.thread = threading.Thread(target=self._run, name="glowback-matter", daemon=True)
        self.thread.start()
        self.call(self._advertise)
        if not self.fabrics:
            self.call(lambda: self.open_window(900))

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(3)
        if self.mdns:
            self.mdns.close()
        if self.sock:
            self.sock.close()

    def call(self, fn):
        self.calls.put(fn)

    def light_changed(self):
        """The light changed on the PC: tell the controllers that subscribed."""
        self.call(lambda: [self._changed(1, c) for c in (0x0006, 0x0008, 0x0300)])

    def pairing(self):
        """What the app shows to pair a phone."""
        s = self.setup
        disc = self.window["discriminator"] if self.window and self.window["kind"] == "enhanced" else s["discriminator"]
        return dict(qr=matter_qr_payload(self.vid, self.pid, s["discriminator"], s["passcode"]),
                    code=matter_manual_code(s["discriminator"], s["passcode"]),
                    open=bool(self.window), until=self.window["until"] if self.window else 0,
                    enhanced=bool(self.window and self.window["kind"] == "enhanced"), discriminator=disc,
                    fabrics=[dict(index=f["index"], label=f["label"], vendor=f["vendor"])
                             for f in self.fabrics.values() if f["committed"]])

    def open_window(self, seconds=900):
        if self.failsafe:
            return
        self.window = dict(kind="basic", until=time.monotonic() + seconds, w0=self.w0, L=self.L,
                           salt=bytes.fromhex(self.setup["salt"]), iterations=self.setup["iterations"],
                           discriminator=self.setup["discriminator"], admin_fabric=None, admin_vendor=None,
                           instance=os.urandom(8).hex().upper())
        self.pase_failures = 0
        self.log(f"Matter: ready to pair for {seconds // 60} min")
        self._advertise()
        self._changed(0, 0x003C)

    def close_window(self):
        if self.window:
            self.window = None
            self._advertise()
            self._changed(0, 0x003C)

    def remove_fabric(self, index):
        if index in self.fabrics:
            self._drop_fabric(index)

    # ---- network thread
    def _run(self):
        while not self.stopping.is_set():
            socks = [self.sock] + self.mdns.sockets()
            try:
                ready, _, _ = select.select(socks, [], [], 0.05)
            except OSError:
                ready = []
            for s in ready:
                try:
                    data, addr = s.recvfrom(4096)
                except OSError:
                    continue
                try:
                    if s is self.sock:
                        self._received(data, addr)
                    else:
                        self.mdns.received(s, data, addr)
                except Exception as e:  # one bad message must not stop the device
                    self.log(f"Matter: {e!r}")
            while not self.calls.empty():
                try:
                    self.calls.get_nowait()()
                except Exception as e:
                    self.log(f"Matter: {e!r}")
            try:
                self._timers()
            except Exception as e:
                self.log(f"Matter: {e!r}")

    def _timers(self):
        now = time.monotonic()
        for x in list(self.exchanges.values()):
            if x.ack is not None and now >= x.ack_due:
                self._send(x, PROTO_SC, SC_ACK, b"", reliable=False)
            p = x.pending
            if p and now >= p["next"]:
                if p["tries"] >= MRP_TRIES:
                    x.pending = None
                    self._exchange_failed(x)
                else:
                    self._sendto(p["data"], x.addr)
                    p["tries"] += 1
                    p["next"] = now + self._backoff(p["tries"])
            if not x.pending and x.ack is None and now - x.last > 60:
                self.exchanges.pop(x.key, None)
        if self.failsafe and now >= self.failsafe["until"]:
            self.log("Matter: pairing timed out")
            self._expire_failsafe()
        if self.window and now >= self.window["until"]:
            self.close_window()
        if self.identify_until and now >= self.identify_until:
            self.identify_until = 0
            self._changed(1, 0x0003)
        if self.watch and now >= self.next_watch:
            self.next_watch = now + 0.5
            seen = self.watch()
            if seen != self.watched:
                self.watched = seen
                for cid in (0x0006, 0x0008, 0x0300):
                    self._changed(1, cid)
        for sub in list(self.subs.values()):
            if not sub.active or sub.inflight:
                continue
            if (sub.dirty and now - sub.last >= sub.min) or now - sub.last >= sub.max:
                self._report(sub)
        self.mdns.tick()

    @staticmethod
    def _backoff(tries):
        return MRP_BASE * 1.1 * 1.6 ** max(0, tries - 1) * (1 + random.random() * 0.25)

    def _sendto(self, data, addr):
        try:
            self.sock.sendto(data, addr)
        except OSError as e:
            self.log(f"Matter: send to {addr[0]} failed ({e})")

    # ---- messages
    def _received(self, data, addr):
        if len(data) < 8 or data[0] >> 4:
            return
        flags, sid, secf, ctr = data[0], struct.unpack_from("<H", data, 1)[0], data[3], struct.unpack_from("<I", data, 4)[0]
        pos, src = 8, None
        if flags & 0x04:
            src = struct.unpack_from("<Q", data, pos)[0]
            pos += 8
        if flags & 3 == 1:
            pos += 8
        elif flags & 3 == 2:
            return  # group messages: not supported
        if secf & 0x20:
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if secf & 0x03:
            return
        header, body = data[:pos], data[pos:]
        if sid == 0:
            session = None
            key = ("u", addr[0], src)
            seen = self.unsec_seen.setdefault(key, set())
            dup = ctr in seen
            seen.add(ctr)
            if len(seen) > 64:
                seen.discard(min(seen))
            payload = body
        else:
            session = self.sessions.get(sid)
            if not session:
                self.debug(f"Matter < {addr[0]} for unknown session {sid}")
                return
            nonce = bytes([secf]) + _u32(ctr) + _u64(session.peer_node if session.kind == "case" else 0)
            payload = ccm_decrypt(session.dec, nonce, body, header)
            if payload is None:
                self.debug(f"Matter < {addr[0]} {session.kind} message that does not decrypt")
                return
            dup = session.duplicate(ctr)
            session.addr, session.last = addr, time.monotonic()
        if len(payload) < 6:
            return
        xf, op, xid = payload[0], payload[1], struct.unpack_from("<H", payload, 2)[0]
        p = 4
        if xf & 0x10:
            p += 2
        proto = struct.unpack_from("<H", payload, p)[0]
        p += 2
        acked = None
        if xf & 0x02:
            acked = struct.unpack_from("<I", payload, p)[0]
            p += 4
        if xf & 0x08:
            p += 2 + struct.unpack_from("<H", payload, p)[0]
        app = payload[p:]
        skey = session.local_id if session else ("u", addr[0], src)
        ours = not (xf & 0x01)  # the peer did not initiate: an exchange we started
        key = (skey, xid, ours)
        x = self.exchanges.get(key)
        if acked is not None and x and x.pending and x.pending["ctr"] == acked:
            x.pending = None
            if x.state and x.state[0] == "close-after-ack":
                self.exchanges.pop(key, None)
        if dup:
            if xf & 0x04:
                tmp = x or MatterExchange(key, xid, ours, session, addr, src)
                tmp.ack = ctr
                self._send(tmp, PROTO_SC, SC_ACK, b"", reliable=False)
            return
        if x is None:
            if ours:
                return  # reply on an exchange we no longer track
            x = self.exchanges[key] = MatterExchange(key, xid, False, session, addr, src)
        x.addr, x.last = addr, time.monotonic()
        if xf & 0x04:
            x.ack, x.ack_due = ctr, time.monotonic() + MRP_ACK_DELAY
        if proto == PROTO_SC and op == SC_ACK:
            return
        self.debug(f"Matter < {addr[0]} {session.kind if session else 'unsecured'} proto {proto} op {op:#04x} "
                   f"x{xid}{' (ours)' if ours else ''} {len(app)} B")
        if proto == PROTO_SC:
            self._secure_channel(x, op, app)
        elif proto == PROTO_IM and session:
            self._interaction(x, op, app)

    def _send(self, x, proto, op, payload, reliable=True):
        xf = (0x01 if x.ours else 0) | (0x02 if x.ack is not None else 0) | (0x04 if reliable else 0)
        ph = bytes([xf, op]) + _u16(x.xid) + _u16(proto) + (_u32(x.ack) if x.ack is not None else b"") + payload
        x.ack = None
        s = x.session
        if op != SC_ACK:
            self.debug(f"Matter > {x.addr[0]} {s.kind if s else 'unsecured'} proto {proto} op {op:#04x} x{x.xid} "
                       f"{len(payload)} B")
        if s:
            ctr = s.next_counter()
            header = b"\x00" + _u16(s.peer_id) + b"\x00" + _u32(ctr)
            nonce = b"\x00" + _u32(ctr) + _u64(s.local_node if s.kind == "case" else 0)
            data = header + ccm_encrypt(s.enc, nonce, ph, header)
        else:
            self.unsec_counter = (self.unsec_counter + 1) & 0xFFFFFFFF
            ctr = self.unsec_counter
            if x.src_node is not None:
                header = b"\x01" + _u16(0) + b"\x00" + _u32(ctr) + _u64(x.src_node)
            else:
                header = b"\x00" + _u16(0) + b"\x00" + _u32(ctr)
            data = header + ph
        self._sendto(data, x.addr)
        x.last = time.monotonic()
        if reliable:
            x.pending = dict(ctr=ctr, data=data, tries=1, next=time.monotonic() + self._backoff(1))

    def _new_exchange(self, session):
        self.next_xid = (self.next_xid + 1) & 0xFFFF
        key = (session.local_id, self.next_xid, True)
        x = self.exchanges[key] = MatterExchange(key, self.next_xid, True, session, session.addr)
        return x

    def _exchange_failed(self, x):
        if x.state and x.state[0] == "sub":
            sub = x.state[1]
            self.log("Matter: a controller stopped answering; its subscription ends")
            self.subs.pop(sub.id, None)
        self.exchanges.pop(x.key, None)

    def _status_report(self, x, general, code, proto=PROTO_SC):
        self._send(x, PROTO_SC, STATUS_REPORT, _u16(general) + _u32(proto) + _u16(code))

    # ---- secure channel: PASE (commissioning) and CASE (operational)
    def _secure_channel(self, x, op, app):
        if op == STATUS_REPORT:
            if len(app) >= 8 and x.session and struct.unpack_from("<H", app, 6)[0] == 3:  # CloseSession
                self._close_session(x.session.local_id)
            return
        if x.session:
            return
        try:
            msg = tlv_decode(app)
        except Exception:
            return self._status_report(x, 1, 2)
        if op == PBKDF_REQ:
            self._pbkdf(x, msg, app)
        elif op == PAKE1 and x.state and x.state[0] == "pase":
            self._pake1(x, msg)
        elif op == PAKE3 and x.state and x.state[0] == "pase2":
            self._pake3(x, msg)
        elif op == SIGMA1:
            self._sigma1(x, msg, app)
        elif op == SIGMA3 and x.state and x.state[0] == "case":
            self._sigma3(x, msg, app)
        else:
            self._status_report(x, 1, 2)

    def _local_session_id(self):
        while True:
            sid = random.randint(1, 0xFFFF)
            if sid not in self.sessions:
                return sid

    @staticmethod
    def _session_params():
        return {1: 500, 2: 300, 3: 4000, 4: MATTER_DM_REVISION, 5: IM_REVISION, 6: MATTER_SPEC_VERSION, 7: 1}

    def _pbkdf(self, x, msg, raw):
        w = self.window
        if not w or self.failsafe and self.failsafe.get("pase_busy"):
            return self._status_report(x, 1, 4)  # busy: not pairing now
        resp = {1: msg[1], 2: os.urandom(32), 3: self._local_session_id()}
        if not msg.get(4):
            resp[4] = {1: w["iterations"], 2: w["salt"]}
        resp[5] = self._session_params()
        out = tlv_encode(resp)
        context = sha256(b"CHIP PAKE V1 Commissioning" + raw + out)
        x.state = ("pase", dict(context=context, peer_sid=msg[2], local_sid=resp[3],
                                verifier=Spake2pVerifier(context, w["w0"], w["L"])))
        self._send(x, PROTO_SC, PBKDF_RSP, out)

    def _pake1(self, x, msg):
        st = x.state[1]
        try:
            Y, cB = st["verifier"].respond(msg[1])
        except (ValueError, KeyError):
            return self._status_report(x, 1, 2)
        x.state = ("pase2", st)
        self._send(x, PROTO_SC, PAKE2, tlv_encode({1: Y, 2: cB}))

    def _pake3(self, x, msg):
        st = x.state[1]
        x.state = None
        if not st["verifier"].check(msg.get(1, b"")):
            self.pase_failures += 1
            self.log("Matter: wrong setup code")
            if self.pase_failures >= 20:
                self.close_window()
            return self._status_report(x, 1, 2)
        keys = hkdf(st["verifier"].Ke, b"", b"SessionKeys", 48)
        s = MatterSession(st["local_sid"], st["peer_sid"], "pase", enc=keys[16:32], dec=keys[:16], challenge=keys[32:],
                    addr=x.addr)
        self.sessions[s.local_id] = s
        self._status_report(x, 0, 0)
        self.log("Matter: a phone is pairing")

    def _sigma1(self, x, msg, raw):
        if msg.get(6) is not None:
            pass  # resumption is declined: a full handshake follows
        fab = None
        for f in self.fabrics.values():
            dest = hmac256(f["ipk"], msg[1] + f["root_pub"] + _u64(f["fabric_id"]) + _u64(f["node_id"]))
            if dest == msg[3]:
                fab = f
                break
        if not fab:
            self.debug(f"Matter   Sigma1 for no fabric of ours ({len(self.fabrics)} fabrics)")
            return self._status_report(x, 1, 1)  # no shared trust roots
        d, Q = ec_keypair()
        eph = ec_encode(Q)
        shared = ecdh(d, msg[4])
        rnd = os.urandom(32)
        sid = self._local_session_id()
        tbs = {1: fab["noc"]}
        if fab["icac"]:
            tbs[2] = fab["icac"]
        tbs.update({3: eph, 4: msg[4]})
        sig = ecdsa_sign(fab["key"], tlv_encode(tbs))
        tbe = {1: fab["noc"]}
        if fab["icac"]:
            tbe[2] = fab["icac"]
        tbe.update({3: sig, 4: os.urandom(16)})
        s2k = hkdf(shared, fab["ipk"] + rnd + eph + sha256(raw), b"Sigma2", 16)
        enc = ccm_encrypt(s2k, b"NCASE_Sigma2N", tlv_encode(tbe))
        out = tlv_encode({1: rnd, 2: sid, 3: eph, 4: enc, 5: self._session_params()})
        x.state = ("case", dict(fab=fab, shared=shared, msg1=raw, msg2=out, eph=eph, peer_eph=msg[4],
                                peer_sid=msg[2], local_sid=sid))
        self._send(x, PROTO_SC, SIGMA2, out)

    def _sigma3(self, x, msg, raw):
        st = x.state[1]
        x.state = None
        fab = st["fab"]
        s3k = hkdf(st["shared"], fab["ipk"] + sha256(st["msg1"] + st["msg2"]), b"Sigma3", 16)
        plain = ccm_decrypt(s3k, b"NCASE_Sigma3N", msg.get(1, b""))
        if plain is None:
            return self._status_report(x, 1, 2)
        try:
            tbe = tlv_decode(plain)
            fabric_id, node_id, cats = cert_verify_chain(tbe[1], tbe.get(2), fab["rcac"])
            if fabric_id != fab["fabric_id"]:
                raise ValueError("other fabric")
            tbs = {1: tbe[1]}
            if tbe.get(2):
                tbs[2] = tbe[2]
            tbs.update({3: st["peer_eph"], 4: st["eph"]})
            if not ecdsa_verify(cert_parse(tbe[1])[9], tlv_encode(tbs), tbe[3]):
                raise ValueError("signature")
        except Exception as e:
            self.log(f"Matter: refused a controller ({e})")
            return self._status_report(x, 1, 2)
        keys = hkdf(st["shared"], fab["ipk"] + sha256(st["msg1"] + st["msg2"] + raw), b"SessionKeys", 48)
        s = MatterSession(st["local_sid"], st["peer_sid"], "case", enc=keys[16:32], dec=keys[:16], challenge=keys[32:],
                    addr=x.addr, local_node=fab["node_id"], peer_node=node_id, fabric=fab["index"], cats=cats)
        self.sessions[s.local_id] = s
        self._status_report(x, 0, 0)

    def _close_session(self, sid):
        self.sessions.pop(sid, None)
        for sub in [s for s in self.subs.values() if s.session == sid]:
            self.subs.pop(sub.id, None)
        for key in [k for k, x in self.exchanges.items() if x.session and x.session.local_id == sid]:
            self.exchanges.pop(key, None)

    # ---- access control
    def privilege(self, ctx, endpoint, cluster):
        s = ctx.session
        if s.kind == "pase":
            return PRIV_ADMIN
        best = 0
        for e in self.acl:
            if e["fabric"] != s.fabric or e["auth"] != CASE_AUTH:
                continue
            subjects = e.get("subjects")
            if subjects:
                hit = s.peer_node in subjects
                for sub in subjects:
                    if sub >> 32 == 0xFFFFFFFD and any((c >> 16) == ((sub >> 16) & 0xFFFF) and
                                                       (c & 0xFFFF) >= (sub & 0xFFFF) for c in s.cats):
                        hit = True
                if not hit:
                    continue
            targets = e.get("targets")
            if targets:
                ok = False
                for t in targets:
                    if (t.get("cluster") in (None, cluster)) and (t.get("endpoint") in (None, endpoint)) and \
                            (t.get("device") is None or t.get("device") == self._device_type(endpoint)):
                        ok = True
                if not ok:
                    continue
            best = max(best, e["privilege"])
        return best

    @staticmethod
    def _device_type(endpoint):
        return DEVICE_TYPE_ROOT if endpoint == 0 else DEVICE_TYPE_LIGHT

    # ---- interaction model
    def _interaction(self, x, op, app):
        try:
            msg = tlv_decode(app) if app else {}
        except Exception:
            return self._im_status(x, ST_INVALID_ACTION)
        if op == IM_STATUS:
            return self._im_status_received(x, msg)
        if op == IM_TIMED:
            x.timed_until = time.monotonic() + msg.get(0, 0) / 1000
            return self._im_status(x, ST_OK, close=False)  # the write or invoke follows on this exchange
        timed = x.timed_until
        x.timed_until = None
        x.timed = timed is not None
        if op in (IM_WRITE, IM_INVOKE):
            flag = bool(msg.get(1, False))
            if flag != (timed is not None):
                return self._im_status(x, ST_TIMED_REQUEST_MISMATCH)
            if timed is not None and time.monotonic() > timed:
                return self._im_status(x, ST_TIMEOUT)
        if op == IM_READ:
            self._read(x, msg)
        elif op == IM_SUBSCRIBE:
            self._subscribe(x, msg)
        elif op == IM_WRITE:
            self._write(x, msg)
        elif op == IM_INVOKE:
            self._invoke(x, msg)
        else:
            self._im_status(x, ST_INVALID_ACTION)

    def _im_status(self, x, status, close=True):
        self._send(x, PROTO_IM, IM_STATUS, tlv_encode({0: status, 0xFF: IM_REVISION}))
        if close:
            x.state = ("close-after-ack",)

    def _im_status_received(self, x, msg):
        st = x.state
        self.debug(f"Matter   status {msg.get(0)} on {st[0] if st else None}")
        if not st:
            return
        if msg.get(0, ST_OK) != ST_OK:
            if st[0] in ("sub", "prime"):
                self.subs.pop(st[1].id, None)
            x.state = None
            self.exchanges.pop(x.key, None)
            return
        if st[0] in ("chunks", "prime", "sub") and st[2]:
            self._send_chunk(x)
        elif st[0] == "prime":
            sub = st[1]
            sub.active, sub.last = True, time.monotonic()
            self._send(x, PROTO_IM, IM_SUBSCRIBE_RSP, tlv_encode({0: sub.id, 2: sub.max, 0xFF: IM_REVISION}))
            x.state = ("close-after-ack",)
        elif st[0] == "sub":
            sub = st[1]
            sub.inflight, sub.last = False, time.monotonic()
            self._send(x, PROTO_SC, SC_ACK, b"", reliable=False)
            x.state = None
            self.exchanges.pop(x.key, None)

    # paths and values
    def _endpoints(self):
        return self.model

    def _expand(self, ctx, path):
        """[(endpoint, cluster, attribute)] for a path, and the error for a concrete path that does not exist."""
        ep, cid, aid = path.get(2), path.get(3), path.get(4)
        if ep is not None and ep not in self.model:
            return [], ST_UNSUPPORTED_ENDPOINT
        out = []
        for e in ([ep] if ep is not None else sorted(self.model)):
            clusters = self.model[e]
            if cid is not None and cid not in clusters:
                if ep is not None:
                    return [], ST_UNSUPPORTED_CLUSTER
                continue
            for c in ([cid] if cid is not None else sorted(clusters)):
                cl = clusters[c]
                ids = sorted(list(cl.attrs) + [0xFFF8, 0xFFF9, 0xFFFB, 0xFFFC, 0xFFFD])
                if aid is not None and aid not in ids:
                    if ep is not None and cid is not None:
                        return [], ST_UNSUPPORTED_ATTRIBUTE
                    continue
                for a in ([aid] if aid is not None else ids):
                    out.append((e, c, a))
        return out, None

    def _value(self, ctx, ep, cid, aid):
        cl = self.model[ep][cid]
        if aid >= 0xFFF8:
            return cl.global_value(aid)
        a = cl.attrs[aid]
        v = a["get"](ctx)
        if a["fabric"]:
            out = []
            for item in v:
                if item.get(0xFE) == ctx.fabric:
                    out.append(item)
                elif not ctx.filtered:
                    out.append({0xFE: item[0xFE]} if a["sensitive"] else item)
            v = out
        return v

    def _collect(self, ctx, paths, dv_filters=None, only=None, sub=None):
        """Attribute reports (each one TLV-encoded) for paths; only: restrict to these (endpoint, cluster, attr);
        sub: a subscription's report, which leaves out the values it already sent."""
        skip = set()
        for f in dv_filters or []:
            p = f.get(0)
            if p is not None:
                ep, cid = p.get(1), p.get(2)
                if ep in self.model and cid in self.model[ep] and self.model[ep][cid].version == f.get(1):
                    skip.add((ep, cid))
        reports, done = [], set()
        for path in paths:
            items, err = self._expand(ctx, path)
            concrete = path.get(2) is not None and path.get(3) is not None and path.get(4) is not None
            if err is not None:
                reports.append(tlv_encode(self._status_ib(path.get(2), path.get(3), path.get(4), err)))
                continue
            for ep, cid, aid in items:
                if (ep, cid, aid) in done or (ep, cid) in skip or (only is not None and (ep, cid, aid) not in only):
                    continue
                done.add((ep, cid, aid))
                cl = self.model[ep][cid]
                need = cl.attrs[aid]["read"] if aid in cl.attrs else PRIV_VIEW
                if self.privilege(ctx, ep, cid) < need:
                    if concrete:
                        reports.append(tlv_encode(self._status_ib(ep, cid, aid, ST_UNSUPPORTED_ACCESS)))
                    continue
                value = self._value(ctx, ep, cid, aid)
                if sub is not None:
                    if only is not None and (ep, cid, aid) in sub.sent and sub.sent[(ep, cid, aid)] == value:
                        continue
                    sub.sent[(ep, cid, aid)] = value
                reports.extend(self._data_ibs(ep, cid, aid, value, cl.version))
        return reports

    @staticmethod
    def _path(ep, cid, aid, append=False):
        p = TList([(2, ep), (3, cid), (4, aid)])
        if append:
            p.append((5, None))
        return p

    def _status_ib(self, ep, cid, aid, status):
        return {0: {0: self._path(ep, cid, aid), 1: {0: status}}}

    def _data_ibs(self, ep, cid, aid, value, version):
        whole = tlv_encode({1: {0: version, 1: self._path(ep, cid, aid), 2: value}})
        if len(whole) <= IM_REPORT_BUDGET or not isinstance(value, list):
            return [whole]
        out = [tlv_encode({1: {0: version, 1: self._path(ep, cid, aid), 2: []}})]  # a long list goes item by item
        for item in value:
            out.append(tlv_encode({1: {0: version, 1: self._path(ep, cid, aid, True), 2: item}}))
        return out

    @staticmethod
    def _chunks(reports):
        chunks, cur, size = [], [], 0
        for r in reports:
            if cur and size + len(r) > IM_REPORT_BUDGET:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(r)
            size += len(r)
        chunks.append(cur)
        return chunks

    def _report_msg(self, reports, sub_id=None, more=False, suppress=False):
        body = b""
        if sub_id is not None:
            body += tlv_encode(sub_id, 0)
        if reports:
            body += b"\x36\x01" + b"".join(reports) + b"\x18"  # AttributeReports: array, context tag 1
        if more:
            body += tlv_encode(True, 3)
        if suppress:
            body += tlv_encode(True, 4)
        body += tlv_encode(IM_REVISION, 0xFF)
        return b"\x15" + body + b"\x18"

    def _send_chunk(self, x):
        kind, obj, chunks = x.state
        chunk = chunks.pop(0)
        sub_id = obj.id if obj is not None else None
        last = not chunks
        if kind == "chunks":  # a read: the last chunk needs no answer
            self._send(x, PROTO_IM, IM_REPORT, self._report_msg(chunk, None, more=not last, suppress=last))
            if last:
                x.state = ("close-after-ack",)
        else:
            self._send(x, PROTO_IM, IM_REPORT, self._report_msg(chunk, sub_id, more=not last))

    def _read(self, x, msg):
        ctx = MatterCtx(self, x.session, bool(msg.get(3, True)))
        reports = self._collect(ctx, msg.get(0, []), msg.get(4))
        self.debug("Matter   read " + " ".join(f"{p.get(2)}/{p.get(3)}/{p.get(4)}" for p in msg.get(0, [])) +
                   f" events={len(msg.get(1) or [])} -> {len(reports)} reports")
        x.state = ("chunks", None, self._chunks(reports))
        self._send_chunk(x)

    def _subscribe(self, x, msg):
        s = x.session
        if not msg.get(0, False):
            for sub in [v for v in self.subs.values() if v.fabric == s.fabric and v.node == s.peer_node]:
                self.subs.pop(sub.id, None)
        floor, ceiling = msg.get(1, 0), msg.get(2, 60)
        sub = MatterSub(random.randint(1, 0xFFFFFFFF), s.local_id, msg.get(3, []), floor, max(floor, ceiling, 1),
                  bool(msg.get(7, True)), s.fabric, s.peer_node)
        self.subs[sub.id] = sub
        ctx = MatterCtx(self, s, sub.filtered)
        reports = self._collect(ctx, sub.paths, msg.get(8), sub=sub)
        x.state = ("prime", sub, self._chunks(reports))
        self._send_chunk(x)

    def _report(self, sub):
        s = self.sessions.get(sub.session)
        if not s:
            self.subs.pop(sub.id, None)
            return
        dirty, sub.dirty = sub.dirty, set()
        reports = self._collect(MatterCtx(self, s, sub.filtered), sub.paths, only=dirty, sub=sub) if dirty else []
        x = self._new_exchange(s)
        sub.inflight = True
        x.state = ("sub", sub, self._chunks(reports))
        self._send_chunk(x)

    def _changed(self, ep, cid, aid=None):
        """An attribute changed: new data version, and pending reports for the subscriptions that cover it."""
        if ep not in self.model or cid not in self.model[ep]:
            return
        cl = self.model[ep][cid]
        cl.version = (cl.version + 1) & 0xFFFFFFFF
        aids = [aid] if aid is not None else list(cl.attrs)
        for sub in self.subs.values():
            for path in sub.paths:
                pe, pc, pa = path.get(2), path.get(3), path.get(4)
                if pe in (None, ep) and pc in (None, cid):
                    for a in aids:
                        if pa in (None, a):
                            sub.dirty.add((ep, cid, a))

    def _write(self, x, msg):
        ctx = MatterCtx(self, x.session)
        ctx.privileges = {}  # checked against the ACL as it was before this write (an admin rewriting the ACL)
        for item in msg.get(2, []):
            p = item.get(1, TList())
            if p.get(2) in self.model and p.get(3) in self.model[p.get(2)]:
                ctx.privileges[(p.get(2), p.get(3))] = self.privilege(ctx, p.get(2), p.get(3))
        results = []
        for item in msg.get(2, []):
            path = item.get(1, TList())
            ep, cid, aid = path.get(2), path.get(3), path.get(4)
            append = any(t == 5 for t, _ in path)
            status = self._write_one(ctx, ep, cid, aid, item.get(2), item.get(0), append, x)
            results.append({0: self._path(ep, cid, aid), 1: {0: status}})
        self._send(x, PROTO_IM, IM_WRITE_RSP, tlv_encode({0: results, 0xFF: IM_REVISION}))
        if not msg.get(3):
            x.state = ("close-after-ack",)
        for fn in ctx.after:
            fn()

    def _write_one(self, ctx, ep, cid, aid, value, version, append, x):
        if ep is None or cid is None or aid is None:
            return ST_UNSUPPORTED_ATTRIBUTE
        if ep not in self.model:
            return ST_UNSUPPORTED_ENDPOINT
        if cid not in self.model[ep]:
            return ST_UNSUPPORTED_CLUSTER
        cl = self.model[ep][cid]
        a = cl.attrs.get(aid)
        if a is None:
            return ST_UNSUPPORTED_ATTRIBUTE if aid < 0xFFF8 else ST_UNSUPPORTED_WRITE
        if a["set"] is None:
            return ST_UNSUPPORTED_WRITE
        if ctx.privileges.get((ep, cid), 0) < a["write"]:
            return ST_UNSUPPORTED_ACCESS
        if a["timed"] and not getattr(x, "timed", False):
            return ST_NEEDS_TIMED_INTERACTION
        if version is not None and version != cl.version:
            return ST_DATA_VERSION_MISMATCH
        try:
            status = a["set"](ctx, value, append)
        except (KeyError, TypeError, ValueError, AttributeError):
            return ST_CONSTRAINT_ERROR
        if status in (None, ST_OK):
            self._changed(ep, cid, aid)
            return ST_OK
        return status

    def _invoke(self, x, msg):
        reqs = msg.get(2, [])
        if len(reqs) != 1:
            return self._im_status(x, ST_INVALID_ACTION)
        cd = reqs[0]
        path = cd.get(0, TList())
        ep, cid, cmd_id = path.get(0), path.get(1), path.get(2)
        ref = cd.get(2)
        ctx = MatterCtx(self, x.session)
        result = self._invoke_one(ctx, ep, cid, cmd_id, cd.get(1, {}), bool(msg.get(1, False)))
        self.debug(f"Matter   invoke {ep}/{cid:#06x}/{cmd_id:#04x} -> "
                   f"{result if not isinstance(result, tuple) else (result[0], str(result[1])[:120])}")
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
            resp_id, fields = result
            ib = {0: {0: TList([(0, ep), (1, cid), (2, resp_id)]), 1: fields}}
            if ref is not None:
                ib[0][2] = ref
        else:
            status, cluster_status = (result if isinstance(result, tuple) else (result, None))
            st = {0: status}
            if cluster_status is not None:
                st[1] = cluster_status
            ib = {1: {0: TList([(0, ep), (1, cid), (2, cmd_id)]), 1: st}}
            if ref is not None:
                ib[1][2] = ref
        self._send(x, PROTO_IM, IM_INVOKE_RSP, tlv_encode({0: False, 1: [ib], 0xFF: IM_REVISION}))
        x.state = ("close-after-ack",)
        for fn in ctx.after:
            fn()

    def _invoke_one(self, ctx, ep, cid, cmd_id, fields, timed):
        if ep not in self.model:
            return ST_UNSUPPORTED_ENDPOINT
        if cid not in self.model[ep]:
            return ST_UNSUPPORTED_CLUSTER
        c = self.model[ep][cid].cmds.get(cmd_id)
        if c is None:
            return ST_UNSUPPORTED_COMMAND
        if self.privilege(ctx, ep, cid) < c["priv"]:
            return ST_UNSUPPORTED_ACCESS
        if c["timed"] and not timed:
            return ST_NEEDS_TIMED_INTERACTION
        try:
            r = c["fn"](ctx, fields if isinstance(fields, dict) else {})
        except (KeyError, TypeError, ValueError):
            return ST_INVALID_COMMAND
        return ST_OK if r is None else r

    # ---- fabrics and commissioning
    def _expire_failsafe(self):
        fs, self.failsafe = self.failsafe, None
        if not fs:
            return
        idx = fs.get("new_fabric")
        if idx in self.fabrics and not self.fabrics[idx]["committed"]:
            self._drop_fabric(idx, save=False)
        for s in [s for s in self.sessions.values() if s.kind == "pase"]:
            self._close_session(s.local_id)
        self.breadcrumb = 0
        self._changed(0, 0x0030)

    def _drop_fabric(self, index, save=True):
        self.fabrics.pop(index, None)
        self.acl = [a for a in self.acl if a["fabric"] != index]
        for s in [s for s in self.sessions.values() if s.fabric == index]:
            self._close_session(s.local_id)
        self._advertise()
        for cid in (0x003E, 0x001F):
            self._changed(0, cid)
        if save:
            self._save()
            self.log(f"Matter: removed a controller ({len(self.committed())} left)")

    def committed(self):
        return [f for f in self.fabrics.values() if f["committed"]]

    def _advertise(self):
        if not self.mdns:
            return
        services = []
        w = self.window
        if w:
            disc = w["discriminator"]
            txt = {"D": str(disc), "CM": "2" if w["kind"] == "enhanced" else "1", "VP": f"{self.vid}+{self.pid}",
                   "DT": str(DEVICE_TYPE_LIGHT), "DN": self.node_label[:32], "SII": "500", "SAI": "300", "T": "0"}
            subs = [f"_L{disc}", f"_S{disc >> 8}", f"_V{self.vid}", f"_T{DEVICE_TYPE_LIGHT}", "_CM"]
            services.append(("_matterc._udp", w["instance"], subs, txt))
        for f in self.fabrics.values():
            cf = f["cfid"].hex().upper()
            services.append(("_matter._tcp", f"{cf}-{f['node_id']:016X}", [f"_I{cf}"],
                             {"SII": "500", "SAI": "300", "T": "0"}))
        self.mdns.publish(services, MATTER_PORT)
        try:
            self.notify()
        except Exception as e:
            self.log(f"Matter: {e!r}")

    def identify(self, seconds):
        self.identify_until = time.monotonic() + seconds if seconds else 0
        try:
            self.light.identify(seconds)
        except Exception as e:
            self.log(f"Matter: identify: {e!r}")
        self._changed(1, 0x0003)

    # ---- the data model
    def _build_model(self):
        self.breadcrumb = 0
        light = self.light
        st = lambda: light.state()  # noqa: E731

        def apply(**kw):
            light.apply(**kw)
            if self.watch:
                self.watched = self.watch()  # reported below: not twice
            for cid in (0x0006, 0x0008, 0x0300):
                self._changed(1, cid)

        # endpoint 0: the node
        desc0 = MatterCluster(0x001D, 2)
        acl = MatterCluster(0x001F, 1)
        basic = MatterCluster(0x0028, 3)
        gcom = MatterCluster(0x0030, 1)
        net = MatterCluster(0x0031, 1, features=0x04)  # Ethernet
        diag = MatterCluster(0x0033, 2)
        admin = MatterCluster(0x003C, 1)
        opc = MatterCluster(0x003E, 1)
        gkm = MatterCluster(0x003F, 1)
        ep0 = [desc0, acl, basic, gcom, net, diag, admin, opc, gkm]
        # endpoint 1: the light
        desc1 = MatterCluster(0x001D, 2)
        ident = MatterCluster(0x0003, 4)
        groups = MatterCluster(0x0004, 4)
        onoff = MatterCluster(0x0006, 6, features=0x01)  # Lighting
        level = MatterCluster(0x0008, 5, features=0x03)  # OnOff, Lighting
        color = MatterCluster(0x0300, 6, features=0x19)  # HueSaturation, XY, ColorTemperature
        ep1 = [desc1, ident, groups, onoff, level, color]
        self.model = {0: {c.id: c for c in ep0}, 1: {c.id: c for c in ep1}}

        desc0.attr(0, lambda c: [{0: DEVICE_TYPE_ROOT, 1: 2}])
        desc0.attr(1, lambda c: sorted(self.model[0]))
        desc0.attr(2, lambda c: [])
        desc0.attr(3, lambda c: [1])
        desc1.attr(0, lambda c: [{0: DEVICE_TYPE_LIGHT, 1: 4}])
        desc1.attr(1, lambda c: sorted(self.model[1]))
        desc1.attr(2, lambda c: [])
        desc1.attr(3, lambda c: [])

        # Access Control
        def acl_get(c):
            out = []
            for e in self.acl:
                out.append({1: e["privilege"], 2: e["auth"],
                            3: e["subjects"] if e.get("subjects") else None,
                            4: [{0: t.get("cluster"), 1: t.get("endpoint"), 2: t.get("device")}
                                for t in e["targets"]] if e.get("targets") else None,
                            0xFE: e["fabric"]})
            return out

        def acl_entry(c, v):
            if not isinstance(v, dict) or v.get(1) not in (1, 2, 3, 4, 5) or v.get(2) not in (CASE_AUTH, GROUP_AUTH):
                raise ValueError("bad ACL entry")
            subjects = list(v.get(3) or [])
            targets = [dict(cluster=t.get(0), endpoint=t.get(1), device=t.get(2)) for t in (v.get(4) or [])]
            if len(subjects) > 4 or len(targets) > 3:
                raise ValueError("too many subjects or targets")
            return dict(fabric=c.fabric, privilege=v[1], auth=v[2], subjects=subjects or None,
                        targets=targets or None)

        def acl_set(c, value, append):
            if append:
                if len([a for a in self.acl if a["fabric"] == c.fabric]) >= 4:
                    return ST_RESOURCE_EXHAUSTED
                self.acl.append(acl_entry(c, value))
            else:
                entries = [acl_entry(c, v) for v in value]
                if len(entries) > 4:
                    return ST_RESOURCE_EXHAUSTED
                self.acl = [a for a in self.acl if a["fabric"] != c.fabric] + entries
            if self.fabrics.get(c.fabric, {}).get("committed"):
                self._save()
            return ST_OK

        acl.attr(0, acl_get, acl_set, write=PRIV_ADMIN, read=PRIV_ADMIN, fabric=True, sensitive=True)
        acl.attr(2, lambda c: 4)
        acl.attr(3, lambda c: 3)
        acl.attr(4, lambda c: 4)

        # Basic Information
        version_int, version_str = self.info.get("version_int", 1), self.info.get("version", "1.0")

        def set_label(c, v, append):
            if not isinstance(v, str) or len(v) > 32:
                return ST_CONSTRAINT_ERROR
            self.node_label = v
            self._save()

        def set_location(c, v, append):
            if not isinstance(v, str) or len(v) != 2:
                return ST_CONSTRAINT_ERROR
            self.location = v
            self._save()

        for aid, fn in ((0, lambda c: MATTER_DM_REVISION), (1, lambda c: self.info.get("vendor", "Glowback")),
                        (2, lambda c: self.vid), (3, lambda c: self.info.get("product", "Glowback")),
                        (4, lambda c: self.pid), (7, lambda c: 1), (8, lambda c: "1"),
                        (9, lambda c: version_int), (10, lambda c: version_str),
                        (13, lambda c: self.info.get("url", "")), (14, lambda c: self.info.get("label", "Glowback")),
                        (15, lambda c: self.setup["serial"]), (18, lambda c: self.setup["unique"]),
                        (19, lambda c: {0: 3, 1: 3}), (21, lambda c: MATTER_SPEC_VERSION), (22, lambda c: 1)):
            basic.attr(aid, fn)
        basic.attr(5, lambda c: self.node_label, set_label, write=PRIV_MANAGE)
        basic.attr(6, lambda c: self.location, set_location, write=PRIV_ADMIN)

        # General Commissioning
        def set_breadcrumb(c, v, append):
            self.breadcrumb = int(v)

        gcom.attr(0, lambda c: self.breadcrumb, set_breadcrumb, write=PRIV_ADMIN)
        gcom.attr(1, lambda c: {0: 60, 1: 900})
        gcom.attr(2, lambda c: self.regulatory)
        gcom.attr(3, lambda c: 2)
        gcom.attr(4, lambda c: True)

        def arm(c, f):
            secs = f.get(0, 0)
            fs = self.failsafe
            if fs and fs["fabric"] != c.fabric:
                return 0x01, {0: 4, 1: ""}  # busy with another admin
            if secs == 0:
                if fs:
                    self._expire_failsafe()
                return 0x01, {0: 0, 1: ""}
            if not fs:
                self.failsafe = fs = dict(fabric=c.fabric, start=time.monotonic(), session=c.session.local_id)
            fs["until"] = min(time.monotonic() + secs, fs["start"] + 900)
            self.breadcrumb = f.get(1, 0)
            return 0x01, {0: 0, 1: ""}

        def regulatory(c, f):
            if f.get(0) not in (0, 1, 2):
                return 0x03, {0: 1, 1: ""}
            self.regulatory = f[0]
            self.breadcrumb = f.get(2, self.breadcrumb)
            return 0x03, {0: 0, 1: ""}

        def complete(c, f):
            fs = self.failsafe
            if not fs:
                return 0x05, {0: 3, 1: ""}
            if c.pase or c.fabric != fs.get("new_fabric", fs["fabric"]):
                return 0x05, {0: 2, 1: ""}
            fab = self.fabrics.get(c.fabric)
            if fab:
                fab["committed"] = True
            self.failsafe = None
            self.breadcrumb = 0
            self.window = None
            self._advertise()
            self._save()
            for s in [s for s in self.sessions.values() if s.kind == "pase"]:
                c.after.append(lambda sid=s.local_id: self._close_session(sid))
            self.log(f"Matter: paired with a controller ({len(self.committed())} in all)")
            return 0x05, {0: 0, 1: ""}

        gcom.cmd(0, arm, PRIV_ADMIN, resp=0x01)
        gcom.cmd(2, regulatory, PRIV_ADMIN, resp=0x03)
        gcom.cmd(4, complete, PRIV_ADMIN, resp=0x05)

        # Network Commissioning (Ethernet: nothing to configure)
        net.attr(0, lambda c: 1)
        net.attr(1, lambda c: [{0: b"eth", 1: True}])
        net.attr(4, lambda c: True, lambda c, v, a: ST_OK, write=PRIV_ADMIN)
        net.attr(5, lambda c: None)
        net.attr(6, lambda c: None)
        net.attr(7, lambda c: None)

        # General Diagnostics
        def interfaces(c):
            v4, v6 = local_addresses()
            return [{0: "Ethernet", 1: True, 2: None, 3: None, 4: bytes.fromhex(self.setup["host"]),
                     5: [socket.inet_aton(a) for a in v4[:4]],
                     6: [socket.inet_pton(socket.AF_INET6, a.split("%")[0]) for a, _ in v6[:8]], 7: 2}]

        diag.attr(0, interfaces)
        diag.attr(1, lambda c: self.reboots & 0xFFFF)
        diag.attr(2, lambda c: int(time.monotonic() - self.started))
        diag.attr(8, lambda c: False)
        diag.cmd(0, lambda c, f: ST_CONSTRAINT_ERROR, PRIV_MANAGE)
        diag.cmd(1, lambda c, f: (0x02, {0: int((time.monotonic() - self.started) * 1000),
                                         1: int(time.time() * 1000)}), PRIV_OPERATE, resp=0x02)

        # Administrator Commissioning
        admin.attr(0, lambda c: 0 if not self.window else (1 if self.window["kind"] == "enhanced" else 2))
        admin.attr(1, lambda c: self.window["admin_fabric"] if self.window else None)
        admin.attr(2, lambda c: self.window["admin_vendor"] if self.window else None)

        def open_ecw(c, f):
            if self.window or self.failsafe:
                return ST_FAILURE, 2  # busy
            timeout, verifier, disc, iters, salt = f.get(0), f.get(1), f.get(2), f.get(3), f.get(4)
            if not (180 <= (timeout or 0) <= 900) or not isinstance(verifier, bytes) or len(verifier) != 97 or \
                    not (0 <= (disc if disc is not None else -1) <= 4095) or not (1000 <= (iters or 0) <= 100000) or \
                    not isinstance(salt, bytes) or not 16 <= len(salt) <= 32:
                return ST_FAILURE, 3  # PAKE parameter error
            try:
                ec_decode(verifier[32:])
            except ValueError:
                return ST_FAILURE, 3
            fab = self.fabrics.get(c.fabric, {})
            self.window = dict(kind="enhanced", until=time.monotonic() + timeout,
                               w0=int.from_bytes(verifier[:32], "big"), L=verifier[32:], salt=salt, iterations=iters,
                               discriminator=disc, admin_fabric=c.fabric, admin_vendor=fab.get("vendor"),
                               instance=os.urandom(8).hex().upper())
            self.pase_failures = 0
            self.log("Matter: another app is being added")
            self._advertise()
            self._changed(0, 0x003C)

        def revoke(c, f):
            if not self.window:
                return ST_FAILURE, 4  # window not open
            self.close_window()
            if self.failsafe:
                self._expire_failsafe()

        admin.cmd(0, open_ecw, PRIV_ADMIN, timed=True)
        admin.cmd(2, revoke, PRIV_ADMIN, timed=True)

        # Operational Credentials
        def nocs(c):
            return [{1: f["noc"], 2: f["icac"], 0xFE: f["index"]} for f in self.fabrics.values()]

        def fabrics_attr(c):
            return [{1: f["root_pub"], 2: f["vendor"], 3: f["fabric_id"], 4: f["node_id"], 5: f["label"],
                     0xFE: f["index"]} for f in self.fabrics.values()]

        opc.attr(0, nocs, read=PRIV_ADMIN, fabric=True, sensitive=True)
        opc.attr(1, fabrics_attr, fabric=True)
        opc.attr(2, lambda c: MATTER_MAX_FABRICS)
        opc.attr(3, lambda c: len(self.committed()))
        opc.attr(4, lambda c: [f["rcac"] for f in self.fabrics.values()] +
                 ([self.failsafe["root"]] if self.failsafe and self.failsafe.get("root") else []))
        opc.attr(5, lambda c: c.fabric)

        def attestation(c, f):
            nonce = f.get(0)
            if not isinstance(nonce, bytes) or len(nonce) != 32:
                return ST_INVALID_COMMAND
            elements = tlv_encode({1: self.cd, 2: nonce, 3: 0})
            return 0x01, {0: elements, 1: ecdsa_sign(self.dac_key, elements + c.session.challenge)}

        def chain(c, f):
            kind = f.get(0)
            if kind not in (1, 2):
                return ST_INVALID_COMMAND
            return 0x03, {0: self.dac if kind == 1 else self.pai}

        def csr(c, f):
            nonce = f.get(0)
            if not isinstance(nonce, bytes) or len(nonce) != 32:
                return ST_INVALID_COMMAND
            fs = self.failsafe
            if not fs:
                return ST_FAILSAFE_REQUIRED
            d, Q = ec_keypair()
            fs["key"], fs["pub"], fs["update"] = d, ec_encode(Q), bool(f.get(1, False))
            elements = tlv_encode({1: matter_csr(d, Q), 2: nonce})
            return 0x05, {0: elements, 1: ecdsa_sign(self.dac_key, elements + c.session.challenge)}

        def add_root(c, f):
            fs = self.failsafe
            if not fs:
                return ST_FAILSAFE_REQUIRED
            try:
                root = cert_parse(f[0])
                if not cert_signed_by(root, root[9]):
                    return ST_INVALID_COMMAND
            except Exception:
                return ST_INVALID_COMMAND
            fs["root"] = f[0]
            self._changed(0, 0x003E, 4)

        def noc_response(code, index=None):
            r = {0: code}
            if index is not None:
                r[1] = index
            return 0x08, r

        def add_noc(c, f):
            fs = self.failsafe
            if not fs:
                return ST_FAILSAFE_REQUIRED
            if "key" not in fs or fs.get("update"):
                return noc_response(4)  # missing CSR
            if not fs.get("root"):
                return noc_response(3)
            if fs.get("new_fabric"):
                return ST_CONSTRAINT_ERROR
            if len(self.fabrics) >= MATTER_MAX_FABRICS:
                return noc_response(5)
            noc, icac, epoch = f.get(0), f.get(1), f.get(2)
            try:
                fabric_id, node_id, _ = cert_verify_chain(noc, icac, fs["root"])
            except Exception:
                return noc_response(3)
            if cert_parse(noc)[9] != fs["pub"]:
                return noc_response(1)
            if not isinstance(epoch, bytes) or len(epoch) != 16:
                return ST_INVALID_COMMAND
            root_pub = cert_parse(fs["root"])[9]
            if any(x["root_pub"] == root_pub and x["fabric_id"] == fabric_id for x in self.fabrics.values()):
                return noc_response(9)
            index = 1
            while index in self.fabrics:
                index += 1
            fab = dict(index=index, rcac=fs["root"], icac=icac, noc=noc, epoch=epoch, vendor=f.get(4, 0), label="",
                       key=fs["key"], committed=False)
            self._fabric_ids(fab)
            self.fabrics[index] = fab
            self.acl.append(dict(fabric=index, privilege=PRIV_ADMIN, auth=CASE_AUTH, subjects=[f.get(3)], targets=None))
            fs["new_fabric"] = index
            fs["fabric"] = index  # CommissioningComplete comes over CASE on the new fabric
            if c.pase:
                c.session.fabric = index  # the commissioning session now belongs to the new fabric
            del fs["key"]
            self._advertise()
            for cid in (0x003E, 0x001F):
                self._changed(0, cid)
            return noc_response(0, index)

        def update_noc(c, f):
            fs = self.failsafe
            if not fs or c.pase:
                return ST_FAILSAFE_REQUIRED
            fab = self.fabrics.get(c.fabric)
            if not fab or "key" not in fs or not fs.get("update"):
                return noc_response(4)
            try:
                fabric_id, node_id, _ = cert_verify_chain(f[0], f.get(1), fab["rcac"])
            except Exception:
                return noc_response(3)
            if cert_parse(f[0])[9] != fs["pub"]:
                return noc_response(1)
            fab.update(noc=f[0], icac=f.get(1), key=fs["key"])
            self._fabric_ids(fab)
            self._advertise()
            self._save()
            return noc_response(0, fab["index"])

        def label(c, f):
            text = f.get(0)
            fab = self.fabrics.get(c.fabric)
            if not isinstance(text, str) or len(text) > 32 or not fab:
                return ST_INVALID_COMMAND
            if any(x["label"] == text and x["index"] != fab["index"] and text for x in self.fabrics.values()):
                return noc_response(10)
            fab["label"] = text
            self._save()
            return noc_response(0, fab["index"])

        def remove(c, f):
            index = f.get(0)
            if index not in self.fabrics:
                return noc_response(11)
            c.after.append(lambda: self._drop_fabric(index))
            return noc_response(0, index)

        opc.cmd(0, attestation, PRIV_ADMIN, resp=0x01)
        opc.cmd(2, chain, PRIV_ADMIN, resp=0x03)
        opc.cmd(4, csr, PRIV_ADMIN, resp=0x05)
        opc.cmd(6, add_noc, PRIV_ADMIN, resp=0x08)
        opc.cmd(7, update_noc, PRIV_ADMIN, resp=0x08)
        opc.cmd(9, label, PRIV_ADMIN, resp=0x08)
        opc.cmd(10, remove, PRIV_ADMIN, resp=0x08)
        opc.cmd(11, add_root, PRIV_ADMIN)

        # Group Key Management: the IPK only
        gkm.attr(0, lambda c: [], lambda c, v, a: ST_OK, write=PRIV_MANAGE, fabric=True)
        gkm.attr(1, lambda c: [], fabric=True)
        gkm.attr(2, lambda c: 1)
        gkm.attr(3, lambda c: 1)
        gkm.cmd(0, lambda c, f: ST_RESOURCE_EXHAUSTED, PRIV_ADMIN)
        gkm.cmd(1, lambda c, f: ST_NOT_FOUND, PRIV_ADMIN, resp=0x02)
        gkm.cmd(3, lambda c, f: ST_NOT_FOUND if f.get(0) else ST_INVALID_COMMAND, PRIV_ADMIN)
        gkm.cmd(4, lambda c, f: (0x05, {0: [0]}), PRIV_ADMIN, resp=0x05)

        # Identify
        def set_identify(c, v, append):
            self.identify(int(v))

        ident.attr(0, lambda c: max(0, int(self.identify_until - time.monotonic() + 0.999)) if self.identify_until
                   else 0, set_identify, write=PRIV_MANAGE)
        ident.attr(1, lambda c: 1)  # light output
        ident.cmd(0, lambda c, f: self.identify(int(f.get(0, 0))), PRIV_MANAGE)
        ident.cmd(0x40, lambda c, f: self.identify(0 if f.get(0) in (0xFE, 0xFF) else 2), PRIV_MANAGE)

        # Groups: a table without group messages (not supported over this transport)
        def gtable(c):
            return self.groups.setdefault(c.fabric, {})

        def add_group(c, f):
            g = f.get(0, 0)
            if not 1 <= g <= 0xFFFF:
                return 0x00, {0: ST_CONSTRAINT_ERROR, 1: g}
            gtable(c)[g] = f.get(1, "")
            return 0x00, {0: ST_OK, 1: g}

        groups.attr(0, lambda c: 0)
        groups.cmd(0, add_group, PRIV_MANAGE, resp=0x00)
        groups.cmd(1, lambda c, f: (0x01, {0: ST_OK if f.get(0) in gtable(c) else ST_NOT_FOUND, 1: f.get(0, 0),
                                           2: gtable(c).get(f.get(0), "")}), PRIV_OPERATE, resp=0x01)
        groups.cmd(2, lambda c, f: (0x02, {0: None, 1: [g for g in gtable(c) if not f.get(0) or g in f.get(0)]}),
                   PRIV_OPERATE, resp=0x02)
        groups.cmd(3, lambda c, f: (0x03, {0: ST_OK if gtable(c).pop(f.get(0), None) is not None else ST_NOT_FOUND,
                                           1: f.get(0, 0)}), PRIV_MANAGE, resp=0x03)
        def add_if_identifying(c, f):
            if self.identify_until:
                add_group(c, f)

        groups.cmd(4, lambda c, f: gtable(c).clear(), PRIV_MANAGE)
        groups.cmd(5, add_if_identifying, PRIV_MANAGE)

        # On/Off
        onoff.attr(0, lambda c: bool(st()["on"]))
        onoff.attr(0x4000, lambda c: True)
        onoff.attr(0x4001, lambda c: 0, lambda c, v, a: ST_OK)
        onoff.attr(0x4002, lambda c: 0, lambda c, v, a: ST_OK)
        onoff.attr(0x4003, lambda c: None, lambda c, v, a: ST_OK)
        onoff.cmd(0, lambda c, f: apply(on=False))
        onoff.cmd(1, lambda c, f: apply(on=True))
        onoff.cmd(2, lambda c, f: apply(on=not st()["on"]))
        onoff.cmd(0x40, lambda c, f: apply(on=False))
        onoff.cmd(0x41, lambda c, f: apply(on=True))
        onoff.cmd(0x42, lambda c, f: apply(on=True))

        # Level Control (1..254)
        def to_level(c, f, with_onoff):
            lv = max(1, min(254, int(f[0])))
            if with_onoff:
                apply(level=lv, on=lv > 1)
            else:
                apply(level=lv)

        def step(c, f, with_onoff):
            cur = st()["level"]
            lv = max(1, min(254, cur + (int(f.get(1, 0)) if f.get(0, 0) == 0 else -int(f.get(1, 0)))))
            apply(level=lv, **({"on": lv > 1} if with_onoff else {}))

        def move(c, f, with_onoff):
            lv = 254 if f.get(0, 0) == 0 else 1
            apply(level=lv, **({"on": lv > 1} if with_onoff else {}))

        level.attr(0, lambda c: st()["level"])
        level.attr(1, lambda c: 0)
        level.attr(2, lambda c: 1)
        level.attr(3, lambda c: 254)
        level.attr(0x0F, lambda c: 0, lambda c, v, a: ST_OK)
        level.attr(0x11, lambda c: None, lambda c, v, a: ST_OK)
        level.attr(0x4000, lambda c: None, lambda c, v, a: ST_OK)
        level.cmd(0, lambda c, f: to_level(c, f, False))
        level.cmd(1, lambda c, f: move(c, f, False))
        level.cmd(2, lambda c, f: step(c, f, False))
        level.cmd(3, lambda c, f: None)
        level.cmd(4, lambda c, f: to_level(c, f, True))
        level.cmd(5, lambda c, f: move(c, f, True))
        level.cmd(6, lambda c, f: step(c, f, True))
        level.cmd(7, lambda c, f: None)

        # Color Control: hue/saturation, CIE xy, color temperature
        color.attr(0, lambda c: st()["hue"])
        color.attr(1, lambda c: st()["sat"])
        color.attr(2, lambda c: 0)
        color.attr(3, lambda c: st()["x"])
        color.attr(4, lambda c: st()["y"])
        color.attr(7, lambda c: st()["ct"])
        color.attr(8, lambda c: st()["mode"])
        color.attr(0x0F, lambda c: 0, lambda c, v, a: ST_OK)
        color.attr(0x10, lambda c: 0)
        color.attr(0x4001, lambda c: st()["mode"])
        color.attr(0x400A, lambda c: 0x19)
        color.attr(0x400B, lambda c: 153)
        color.attr(0x400C, lambda c: 500)
        color.attr(0x400D, lambda c: 153)
        color.attr(0x4010, lambda c: None, lambda c, v, a: ST_OK)

        def hs(h=None, s=None):
            cur = st()
            apply(hue=cur["hue"] if h is None else int(h) % 255, sat=cur["sat"] if s is None else min(254, int(s)),
                  mode=0)

        def step_hue(f):
            cur = st()["hue"]
            hs(h=(cur + (int(f.get(1, 0)) if f.get(0) == 1 else -int(f.get(1, 0)))) % 255)

        def step_sat(f):
            cur = st()["sat"]
            hs(s=max(0, min(254, cur + (int(f.get(1, 0)) if f.get(0) == 1 else -int(f.get(1, 0))))))

        def xy(x, y):
            apply(x=max(0, min(65279, int(x))), y=max(0, min(65279, int(y))), mode=1)

        def ct(m):
            apply(ct=max(153, min(500, int(m))), mode=2)

        color.cmd(0x00, lambda c, f: hs(h=f[0]))
        color.cmd(0x01, lambda c, f: None)
        color.cmd(0x02, lambda c, f: step_hue(f))
        color.cmd(0x03, lambda c, f: hs(s=f[0]))
        color.cmd(0x04, lambda c, f: None)
        color.cmd(0x05, lambda c, f: step_sat(f))
        color.cmd(0x06, lambda c, f: hs(h=f[0], s=f[1]))
        color.cmd(0x07, lambda c, f: xy(f[0], f[1]))
        color.cmd(0x08, lambda c, f: None)
        color.cmd(0x09, lambda c, f: xy(st()["x"] + int(f.get(0, 0)), st()["y"] + int(f.get(1, 0))))
        color.cmd(0x0A, lambda c, f: ct(f[0]))
        color.cmd(0x47, lambda c, f: None)
        color.cmd(0x4B, lambda c, f: None)
        color.cmd(0x4C, lambda c, f: ct(st()["ct"] + (int(f.get(1, 0)) if f.get(0) == 1 else -int(f.get(1, 0)))))


# ---- local addresses
MATTER_ADDRESSES = None  # a function giving the addresses of the networks phones are on (virtual adapters left out)


def local_addresses():
    """([IPv4], [(IPv6 with %scope, interface index)]) of this computer, loopback excluded."""
    if MATTER_ADDRESSES:
        try:
            return MATTER_ADDRESSES()
        except OSError:
            pass
    v4, v6 = [], []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
    except OSError:
        infos = []
    for fam, _, _, _, sa in infos:
        if fam == socket.AF_INET and not sa[0].startswith("127.") and sa[0] not in v4:
            v4.append(sa[0])
        elif fam == socket.AF_INET6 and sa[0] != "::1":
            entry = (sa[0] if "%" in sa[0] or not sa[3] else f"{sa[0]}%{sa[3]}", sa[3])
            if entry not in v6:
                v6.append(entry)
    if sys.platform.startswith("linux"):
        try:
            for line in open("/proc/net/if_inet6"):
                hexaddr, idx, _, scope, _, name = line.split()
                if name == "lo":
                    continue
                addr = socket.inet_ntop(socket.AF_INET6, bytes.fromhex(hexaddr))
                entry = (f"{addr}%{int(idx, 16)}" if int(scope, 16) == 0x20 else addr, int(idx, 16))
                if entry not in v6:
                    v6.append(entry)
        except OSError:
            pass
    if not v4:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("192.0.2.1", 9))
            v4.append(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    return v4, v6


# ---- DNS-SD over mDNS (RFC 6762/6763): just enough to be found and resolved
class Mdns:
    GROUP4, GROUP6 = "224.0.0.251", "ff02::fb"

    def __init__(self, host, log, debug=lambda m: None):
        self.host, self.log, self.debug = f"{host}.local", log, debug
        self.records, self.services, self.port = [], [], 0
        self.announce_at = []
        self.s4 = self.s6 = None
        self.ifaces6 = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            s.bind(("", 5353))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            v4, _ = local_addresses()
            joined = False
            for a in v4:
                try:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                 socket.inet_aton(self.GROUP4) + socket.inet_aton(a))
                    joined = True
                except OSError:
                    pass
            if not joined:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                             socket.inet_aton(self.GROUP4) + socket.inet_aton("0.0.0.0"))
            self.s4 = s
        except OSError as e:
            log(f"Matter: mDNS (IPv4) unavailable ({e})")
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            try:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            except (AttributeError, OSError):
                pass
            s.bind(("::", 5353))
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
            _, v6 = local_addresses()
            for idx in sorted({i for _, i in v6 if i}):
                try:
                    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                                 socket.inet_pton(socket.AF_INET6, self.GROUP6) + struct.pack("@I", idx))
                    self.ifaces6.append(idx)
                except OSError:
                    pass
            self.s6 = s
        except OSError as e:
            log(f"Matter: mDNS (IPv6) unavailable ({e})")
        v4, v6 = local_addresses()
        debug(f"Matter   mDNS: IPv4 {'on' if self.s4 else 'off'} {v4}, IPv6 {'on' if self.s6 else 'off'} interfaces "
              f"{self.ifaces6} {[a for a, _ in v6]}")

    def sockets(self):
        return [s for s in (self.s4, self.s6) if s]

    def close(self):
        if self.records:
            self._send_all(self._packet([(r[0], r[1], 0, r[3], r[4]) for r in self.records], []))
        for s in self.sockets():
            s.close()

    def publish(self, services, port):
        """services: [(type, instance, subtypes, txt dict)]."""
        old = {(r[0], r[1], r[4]) for r in self.records}
        self.services, self.port = services, port
        recs = []
        v4, v6 = local_addresses()
        for typ, inst, subs, txt in services:
            full = f"{inst}.{typ}.local"
            recs.append(("_services._dns-sd._udp.local", 12, 4500, False, _dns_name(f"{typ}.local")))
            recs.append((f"{typ}.local", 12, 4500, False, _dns_name(full)))
            for sub in subs:
                recs.append((f"{sub}._sub.{typ}.local", 12, 4500, False, _dns_name(full)))
            recs.append((full, 33, 120, True, struct.pack(">HHH", 0, 0, port) + _dns_name(self.host)))
            recs.append((full, 16, 4500, True, b"".join(bytes([len(e)]) + e for e in
                                                         (f"{k}={v}".encode() for k, v in txt.items()))))
        for a in v4:
            recs.append((self.host, 1, 120, True, socket.inet_aton(a)))
        for a, _ in v6:
            recs.append((self.host, 28, 120, True, socket.inet_pton(socket.AF_INET6, a.split("%")[0])))
        gone = [r for r in self.records if (r[0], r[1], r[4]) not in {(x[0], x[1], x[4]) for x in recs}]
        if gone:
            self._send_all(self._packet([(r[0], r[1], 0, r[3], r[4]) for r in gone], []))
        self.records = recs
        if {(r[0], r[1], r[4]) for r in recs} != old:
            now = time.monotonic()
            self.announce_at = [now, now + 1, now + 3]

    def tick(self):
        now = time.monotonic()
        if self.announce_at and now >= self.announce_at[0]:
            self.announce_at.pop(0)
            if self.records:
                answers = [r for r in self.records if r[1] in (12, 33, 16)]
                extra = [r for r in self.records if r[1] in (1, 28)]
                self._send_all(self._packet(answers, extra))

    def received(self, sock, data, addr):
        if len(data) < 12:
            return
        qid, flags, qd = struct.unpack(">HHH", data[:6])
        if flags & 0x8000:
            return  # a response, not a question
        pos, questions = 12, []
        for _ in range(qd):
            name, pos = _dns_read_name(data, pos)
            qtype, qclass = struct.unpack(">HH", data[pos:pos + 4])
            pos += 4
            questions.append((name.lower(), qtype, bool(qclass & 0x8000)))
        answers, unicast = [], False
        for name, qtype, qu in questions:
            for r in self.records:
                if r[0].lower() == name and (qtype in (r[1], 255)) and r not in answers:
                    answers.append(r)
                    unicast |= qu
        if any("matter" in q[0] or q[0] == self.host.lower() for q in questions):
            self.debug(f"Matter   mDNS from {addr[0]}: {[(q[0], q[1]) for q in questions]} -> {len(answers)} answers")
        if not answers:
            return
        extra = []
        for r in answers:
            if r[1] == 12:
                target = _dns_plain(r[4])
                extra += [x for x in self.records if x[0].lower() == target.lower() and x[1] in (33, 16)]
        for r in answers + extra:
            if r[1] == 33:
                extra += [x for x in self.records if x[0] == self.host and x[1] in (1, 28)]
        extra = [x for i, x in enumerate(extra) if x not in answers and x not in extra[:i]]
        legacy = addr[1] != 5353
        pkt = self._packet(answers, extra, qid if legacy else 0, questions if legacy else None)
        if legacy or unicast:
            try:
                sock.sendto(pkt, addr)
            except OSError:
                pass
        else:
            self._send_all(pkt)

    @staticmethod
    def _packet(answers, extra, qid=0, questions=None):
        out = struct.pack(">HHHHHH", qid, 0x8400, len(questions) if questions else 0, len(answers), 0, len(extra))
        for name, qtype, _ in questions or []:
            out += _dns_name(name) + struct.pack(">HH", qtype, 1)
        for name, rtype, ttl, unique, rdata in answers + extra:
            out += _dns_name(name) + struct.pack(">HHIH", rtype, 0x8001 if unique else 1, ttl, len(rdata)) + rdata
        return out

    def _send_all(self, pkt):
        if self.s4:
            for a in local_addresses()[0] or [None]:
                try:
                    if a:
                        self.s4.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(a))
                    self.s4.sendto(pkt, (self.GROUP4, 5353))
                except OSError:
                    pass
        if self.s6:
            for idx in self.ifaces6 or [0]:
                try:
                    self.s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, idx)
                    self.s6.sendto(pkt, (self.GROUP6, 5353, 0, idx))
                except OSError:
                    pass


def _dns_name(dotted):
    out = b""
    for label in dotted.rstrip(".").split("."):
        b = label.encode()
        out += bytes([len(b)]) + b
    return out + b"\x00"


def _dns_plain(encoded):
    return _dns_read_name(encoded, 0)[0]


def _dns_read_name(data, pos):
    labels, jumped, end = [], False, pos
    for _ in range(64):
        n = data[pos]
        if n == 0:
            pos += 1
            break
        if n & 0xC0 == 0xC0:
            ptr = ((n & 0x3F) << 8) | data[pos + 1]
            if not jumped:
                end = pos + 2
            jumped = True
            pos = ptr
            continue
        labels.append(data[pos + 1:pos + 1 + n].decode("utf-8", "replace"))
        pos += 1 + n
    return ".".join(labels), (end if jumped else pos)


class SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]


class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
    pass


IP_ADAPTER_UNICAST_ADDRESS._fields_ = [("Length", wt.ULONG), ("Flags", wt.DWORD),
                                       ("Next", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
                                       ("Address", SOCKET_ADDRESS)]


class IP_ADAPTER_ADDRESSES(ctypes.Structure):
    pass


IP_ADAPTER_ADDRESSES._fields_ = [
    ("Length", wt.ULONG), ("IfIndex", wt.DWORD), ("Next", ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p), ("FirstUnicastAddress", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
    ("FirstAnycastAddress", ctypes.c_void_p), ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p), ("DnsSuffix", wt.LPWSTR), ("Description", wt.LPWSTR),
    ("FriendlyName", wt.LPWSTR), ("PhysicalAddress", ctypes.c_ubyte * 8), ("PhysicalAddressLength", wt.ULONG),
    ("Flags", wt.ULONG), ("Mtu", wt.ULONG), ("IfType", wt.DWORD), ("OperStatus", ctypes.c_int),
    ("Ipv6IfIndex", wt.DWORD), ("ZoneIndices", wt.DWORD * 16), ("FirstPrefix", ctypes.c_void_p),
    ("TransmitLinkSpeed", ctypes.c_uint64), ("ReceiveLinkSpeed", ctypes.c_uint64),
    ("FirstWinsServerAddress", ctypes.c_void_p), ("FirstGatewayAddress", ctypes.c_void_p)]


def lan_addresses():
    """The addresses of the adapters that lead to the home network (up, with a gateway, not Hyper-V, WSL, Docker or
    VPN virtual adapters): what phones on the network can reach. ([IPv4], [(IPv6%scope, index)])."""
    iphlpapi = ctypes.WinDLL("iphlpapi")
    size = wt.ULONG(16384)
    for _ in range(3):
        buf = ctypes.create_string_buffer(size.value)
        err = iphlpapi.GetAdaptersAddresses(0, 0x0080 | 0x0002 | 0x0004, None, buf, byref(size))  # GATEWAYS, no
        if err != 111:  # ERROR_BUFFER_OVERFLOW                                                      # anycast/multicast
            break
    if err:
        raise OSError(f"GetAdaptersAddresses error {err}")
    v4, v6 = [], []
    a = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES))
    while a:
        ad = a.contents
        virtual = any(w in (ad.Description or "") for w in ("Hyper-V", "Virtual", "VMware", "VirtualBox", "TAP-",
                                                            "WireGuard", "Tailscale", "ZeroTier"))
        if ad.OperStatus == 1 and ad.IfType in (6, 71) and ad.FirstGatewayAddress and not virtual:
            u = ad.FirstUnicastAddress
            while u:
                sa = ctypes.string_at(u.contents.Address.lpSockaddr, u.contents.Address.iSockaddrLength)
                family = struct.unpack_from("<H", sa)[0]
                if family == socket.AF_INET:
                    v4.append(socket.inet_ntoa(sa[4:8]))
                elif family == 23:  # AF_INET6
                    addr, scope = socket.inet_ntop(socket.AF_INET6, sa[8:24]), struct.unpack_from("<I", sa, 24)[0]
                    if addr.startswith("fe80"):
                        v6.append((f"{addr}%{scope or ad.Ipv6IfIndex}", scope or ad.Ipv6IfIndex))
                    else:
                        v6.append((addr, ad.Ipv6IfIndex))
                u = u.contents.Next
        a = ad.Next
    if not v4 and not v6:
        raise OSError("no network adapter with a gateway")
    return v4, v6


MATTER_ADDRESSES = lan_addresses


def matter_settings():
    m = load_settings().get("matter")
    return m if isinstance(m, dict) else {}


class MatterStore:
    """matter.json, next to settings.json; the fabrics' private keys are encrypted for this Windows user."""

    def load(self):
        try:
            with open(MATTER_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def save(self, data):
        tmp = MATTER_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, MATTER_PATH)

    @staticmethod
    def protect(data):
        return base64.b64encode(_dpapi(data, True)).decode()

    @staticmethod
    def unprotect(text):
        return _dpapi(base64.b64decode(text), False)


def _srgb_linear(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _srgb_encode(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def rgb_xy(color):
    """0xRRGGBB -> CIE 1931 (x, y)."""
    r, g, b = (_srgb_linear(c) for c in rgb(color))
    X, Y, Z = (0.4124 * r + 0.3576 * g + 0.1805 * b, 0.2126 * r + 0.7152 * g + 0.0722 * b,
               0.0193 * r + 0.1192 * g + 0.9505 * b)
    total = X + Y + Z
    return (X / total, Y / total) if total else (0.3127, 0.3290)


def xy_rgb(x, y):
    """CIE 1931 (x, y) -> 0xRRGGBB, as bright as it gets."""
    y = max(y, 1e-4)
    X, Z = x / y, (1 - x - y) / y
    lin = [max(0.0, v) for v in (3.2406 * X - 1.5372 - 0.4986 * Z, -0.9689 * X + 1.8758 + 0.0415 * Z,
                                 0.0557 * X - 0.2040 + 1.0570 * Z)]
    top = max(lin) or 1.0
    r, g, b = (round(255 * _srgb_encode(v / top)) for v in lin)
    return (r << 16) | (g << 8) | b


def kelvin_rgb(kelvin):
    """A white of that color temperature -> 0xRRGGBB (Tanner Helland's fit of the black body)."""
    t = max(1000.0, min(40000.0, kelvin)) / 100
    r = 255 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255 if t >= 66 else 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    r, g, b = (max(0, min(255, round(v))) for v in (r, g, b))
    return (r << 16) | (g << 8) | b


class MatterLight:
    """Glowback's ambient light as Matter sees it: on/off, brightness, and a color (hue and saturation, CIE xy or a
    white's temperature) that switches Glowback to its Color look."""

    def __init__(self, state):
        self.s = state
        self.chosen = None  # (color, the Matter values it came from): reported as they were while the color stays

    def state(self):
        s = self.s
        if self.chosen and self.chosen[0] == s.color:
            fields = dict(self.chosen[1])
        else:
            h, sat, _ = color_hsv(s.color)
            x, y = rgb_xy(s.color)
            fields = dict(hue=round(h / 360 * 254) % 255, sat=round(sat * 254), x=min(65279, round(x * 65536)),
                          y=min(65279, round(y * 65536)), ct=250, mode=0)
        return dict(on=s.lit(), level=max(1, min(254, round(s.brightness * 254 / 100))), **fields)

    def apply(self, **kw):
        change = {}
        if "on" in kw:  # off: the LEDs go dark (Glowback's pause would give them back to the device's own effect)
            change["enabled"], change["dark"] = True, not kw["on"]
        if "level" in kw:
            change["brightness"] = float(max(1, min(100, round(kw["level"] * 100 / 254))))
        if kw.keys() & {"hue", "sat", "x", "y", "ct"}:
            cur = self.state()
            f = {k: kw.get(k, cur[k]) for k in ("hue", "sat", "x", "y", "ct", "mode")}
            if f["mode"] == 2:
                color = kelvin_rgb(1e6 / max(1, f["ct"]))
            elif f["mode"] == 1:
                color = xy_rgb(f["x"] / 65536, f["y"] / 65536)
            else:
                color = hsv_color(f["hue"] / 254 * 360, f["sat"] / 254)
            change["color"], change["mode"] = color, "color"  # a color chosen on the phone: the Color look
            self.chosen = (color, f)
        if change:
            log("Matter: " + ", ".join(f"{k} {color_hex(v) if k == 'color' else v}" for k, v in change.items()))
            self.s.update(**change)

    def identify(self, seconds):
        """"Identify" in the phone's app: the LEDs blink white."""
        self.s.identify_until = time.monotonic() + seconds if seconds else 0.0


def matter_start(state, notify=lambda: None):
    """Glowback's Matter light, started; None (and a line in the log) if this PC cannot run it."""
    nums = [int(n) for n in re.findall(r"\d+", __version__)[:3]] + [0, 0, 0]
    info = dict(product="Glowback", vendor="Glowback", label="Glowback ambient light", url=REPO_URL,
                version=__version__, version_int=nums[0] * 10000 + nums[1] * 100 + nums[2])
    att = dict(dac=base64.b64decode(MATTER_DAC), dac_key=base64.b64decode(MATTER_DAC_KEY),
               pai=base64.b64decode(MATTER_PAI), cd=base64.b64decode(MATTER_CD), vid=MATTER_VID, pid=MATTER_PID)
    try:
        node = MatterNode(MatterStore(), MatterLight(state), info, att, log=log, watch=lambda: state.version,
                          notify=notify)
        node.start()
    except (OSError, ValueError) as e:
        log(f"Matter: could not start ({e})")
        return None
    log("Matter: on")
    return node


def matter_guide_url():
    if _lang["code"] == "fr":
        return REPO_URL + "/blob/main/README.fr.md#-apple-maison-google-home-et-alexa"
    return REPO_URL + "#-apple-home-google-home-and-alexa"


def matter_app_name(fabric):
    """Which app a fabric is (from its maker), else the name it gave itself."""
    name = MATTER_VENDORS.get(fabric["vendor"])
    if name and name.startswith("matter_"):
        name = tr(name)
    return name or fabric["label"] or tr("matter_controller")
# (end of Matter)


class HomeAssistantDialog:
    """The window that connects Glowback to Home Assistant: broker address and port, user and password."""
    WM_RESULT = 0x8010
    FIELD, BORDER = 0x1B1C22, 0x2E3140
    FIELDS = ("host", "port", "user", "password")
    WIDTH = 452  # client width at 100 %

    def __init__(self, tray):
        self.tray, self.hwnd, self.painter = tray, None, None
        self.edits, self.boxes, self.labels, self.buttons = {}, {}, [], {}
        self.status, self.busy, self.result, self.pending = None, False, None, None
        self._ref = WNDPROC(self._proc)
        hinst = k32.GetModuleHandleW(None)
        self.cls = f"GlowbackHomeAssistant{id(self)}"  # a class per object: each keeps its own window procedure
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._ref, hinst, self.cls
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW
        icon = ensure_icons()[0]
        wc.hIcon = user32.LoadImageW(None, icon, 1, 32, 32, 0x10)
        wc.hIconSm = user32.LoadImageW(None, icon, 1, 16, 16, 0x10)
        user32.RegisterClassExW(byref(wc))

    # ---- layout and creation
    def _layout(self, w):
        """Positions of everything, in pixels; returns the client height."""
        pt, p = self.painter, self.painter.px
        pad, inner = p(26), w - 2 * p(26)
        y = p(24)
        self.head = (pad, y, w - pad, y + p(34))
        y += p(34) + p(14)
        rc = wt.RECT(0, 0, inner, 0)
        gdi32.SelectObject(pt.mdc, pt.f_text)
        user32.DrawTextW(pt.mdc, tr("ha_intro"), -1, byref(rc), 0x10 | 0x400 | 0x800)  # WORDBREAK|CALCRECT|NOPREFIX
        self.intro = (pad, y, w - pad, y + rc.bottom)
        y += rc.bottom + p(8)
        self.link = (pad, y, pad + pt.text_width(tr("ha_guide"), pt.f_text) + p(18), y + p(22))
        y += p(22) + p(20)
        gap, port_w, half = p(12), p(96), (inner - p(12)) // 2
        rows = ((("host", pad, inner - gap - port_w), ("port", w - pad - port_w, port_w)),
                (("user", pad, half), ("password", w - pad - half, half)))
        self.boxes, self.labels = {}, []
        for row in rows:
            for key, x, width in row:
                self.labels.append((tr("ha_" + ("address" if key == "host" else key)), x, y))
                self.boxes[key] = (x, y + p(22), x + width, y + p(22) + p(40))
            y += p(22) + p(40) + p(16)
        self.status_rc = (pad, y, w - pad, y + p(38))
        y += p(38) + p(14)
        self.button_y = (y, y + p(38))
        return y + p(38) + p(24)

    def open(self):
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(self.hwnd)
            return
        pt_ = wt.POINT()
        user32.GetCursorPos(byref(pt_))
        mon = user32.MonitorFromPoint(pt_, 2)
        dpi_x, dpi_y = wt.UINT(96), wt.UINT(96)
        if shcore:
            shcore.GetDpiForMonitor(mon, 0, byref(dpi_x), byref(dpi_y))
        scale = dpi_x.value / 96.0
        self.painter = MenuPainter(scale, None)
        p = self.painter.px
        mk = lambda px, weight, face: gdi32.CreateFontW(-round(px * scale), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, face)
        self.f_head, self.f_glyph = mk(20, 600, ui_font_face()), mk(18, 400, icon_font_face())
        self.f_button = mk(13.5, 600, ui_font_face())
        self.field_brush = gdi32.CreateSolidBrush(_cref(self.FIELD))
        w = p(self.WIDTH)
        h = self._layout(w)
        style = 0x00C00000 | 0x00080000 | 0x02000000  # CAPTION | SYSMENU | CLIPCHILDREN: a close button only
        rc = wt.RECT(0, 0, w, h)
        try:
            user32.AdjustWindowRectExForDpi(byref(rc), style, False, 0, dpi_x.value)
        except AttributeError:
            user32.AdjustWindowRectEx(byref(rc), style, False, 0)
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        user32.GetMonitorInfoW(mon, byref(mi))
        work, ww, wh = mi.rcWork, rc.right - rc.left, rc.bottom - rc.top
        x, y = work.left + (work.right - work.left - ww) // 2, work.top + (work.bottom - work.top - wh) // 2
        hinst = k32.GetModuleHandleW(None)
        self.hwnd = user32.CreateWindowExW(0, self.cls, "Glowback · Home Assistant", style,
                                           x, y, ww, wh, None, None, hinst, None)
        if not self.hwnd:
            self._free()
            return
        for attr, value in ((20, 1), (35, _cref(MenuPainter.BG)), (34, _cref(0x2C2E38))):  # dark, caption, border
            v = wt.DWORD(value)
            dwmapi.DwmSetWindowAttribute(self.hwnd, attr, byref(v), 4)
        saved = ha_settings()
        values = dict(host=("mqtts://" if saved and saved["tls"] else "") + (saved["host"] if saved else "homeassistant.local"),
                      port=str(saved["port"]) if saved else "1883", user=saved["user"] if saved else "", password="")
        for i, key in enumerate(self.FIELDS):
            l, t, r, b = self.boxes[key]
            eh = p(22)
            style = 0x50010080 | (0x20 if key == "password" else 0) | (0x2000 if key == "port" else 0)
            # WS_CHILD|VISIBLE|TABSTOP|ES_AUTOHSCROLL, ES_PASSWORD, ES_NUMBER
            e = user32.CreateWindowExW(0, "EDIT", values[key], style, l + p(13), t + (b - t - eh) // 2, r - l - p(26),
                                       eh, self.hwnd, ctypes.c_void_p(100 + i), hinst, None)
            user32.SendMessageW(e, 0x0030, self.painter.f_text, 0)  # WM_SETFONT
            self.edits[key] = e
        cues = dict(user=tr("ha_user_hint"), password=tr("ha_password_saved") if saved and saved["password"] else "")
        for key, cue in cues.items():
            if cue:
                text = ctypes.create_unicode_buffer(cue)  # EM_SETCUEBANNER copies it
                user32.SendMessageW(self.edits[key], 0x1501, 1, ctypes.addressof(text))
        user32.SendMessageW(self.edits["port"], 0x00C5, 5, 0)  # EM_LIMITTEXT
        self.buttons = {}
        top, bottom = self.button_y
        right = w - p(26)
        for cid, text in ((1, tr("ha_connect")), (2, tr("ha_cancel"))):
            bw = max(p(104), self.painter.text_width(text, self.f_button) + p(44))
            self.buttons[cid] = self._button(cid, text, right - bw, top, bw, bottom - top)
            right -= bw + p(10)
        if saved:
            text = tr("ha_disconnect")
            bw = self.painter.text_width(text, self.f_button) + p(28)
            self.buttons[3] = self._button(3, text, p(26) - p(14), top, bw, bottom - top)
        ha = getattr(self.tray, "ha", None)
        if ha and ha.status == "connected":
            self.status = (tr("ha_connected"), MenuPainter.GREEN)
        elif ha and ha.status == "error" and saved:
            self.status = (ha.error, MenuPainter.AMBER)
        user32.ShowWindow(self.hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(self.hwnd)
        user32.SetFocus(self.edits["user" if values["host"] and not values["user"] else "host"])

    def _button(self, cid, text, x, y, w, h):
        b = user32.CreateWindowExW(0, "BUTTON", text, 0x5001000B, x, y, w, h, self.hwnd, ctypes.c_void_p(cid),
                                   k32.GetModuleHandleW(None), None)  # WS_CHILD|VISIBLE|TABSTOP|BS_OWNERDRAW
        user32.SendMessageW(b, 0x0030, self.f_button, 0)
        return b

    def _free(self):
        if self.painter:
            self.painter.close()
            self.painter = None
        for h in (getattr(self, "f_head", None), getattr(self, "f_glyph", None), getattr(self, "f_button", None),
                  getattr(self, "field_brush", None)):
            if h:
                gdi32.DeleteObject(h)
        self.f_head = self.f_glyph = self.f_button = self.field_brush = None
        self.edits, self.buttons = {}, {}

    # ---- actions
    def _get(self, key):
        e = self.edits[key]
        buf = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(e) + 1)
        user32.GetWindowTextW(e, buf, len(buf))
        return buf.value

    def _show(self, text, color):
        self.status = (text, color) if text else None
        user32.InvalidateRect(self.hwnd, None, False)

    def _enable(self, on):
        for h in list(self.edits.values()) + list(self.buttons.values()):
            user32.EnableWindow(h, on)

    def connect(self):
        host, tls = self._get("host").strip(), False
        if "://" in host:
            scheme, host = host.split("://", 1)
            tls = scheme.lower() == "mqtts"
        host = host.strip().strip("/")
        port = self._get("port").strip()
        port = int(port) if port.isdigit() and 0 < int(port) < 65536 else (8883 if tls else 1883)
        user, password = self._get("user").strip(), self._get("password")
        if not host:
            self._show(tr("ha_need_address"), MenuPainter.AMBER)
            user32.SetFocus(self.edits["host"])
            return
        saved = ha_settings()
        if not password and saved and (saved["host"], saved["user"]) == (host, user):
            password = saved["password"]  # left empty: keep the saved one
        self.pending = dict(host=host, port=port, user=user, password=password, tls=tls)
        self.busy, self.result = True, None
        self._enable(False)
        self._show(tr("ha_testing"), MenuPainter.MUTED)
        hwnd, pending = self.hwnd, self.pending

        def work():
            try:
                ha_check(pending)
            except Exception as e:
                self.result = ha_error_text(e)
                log(f"Home Assistant: {pending['host']}:{pending['port']} {e.__class__.__name__}: {e}")
            user32.PostMessageW(hwnd, self.WM_RESULT, 0, 0)

        threading.Thread(target=work, name="glowback-ha-check", daemon=True).start()

    def _checked(self):
        self.busy = False
        self._enable(True)
        if self.result:
            self._show(self.result, MenuPainter.AMBER)
            return
        c = self.pending
        save_ha_settings(c["host"], c["port"], c["user"], c["password"], c["tls"])
        self.tray.ha_changed()
        user32.DestroyWindow(self.hwnd)
        self.tray.refresh((tr("ha_done_title"), tr("ha_done_text")))

    def disconnect(self):
        save_settings({"home_assistant": None})
        self.tray.ha_changed()
        user32.DestroyWindow(self.hwnd)

    # ---- drawing
    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        rc = wt.RECT()
        user32.GetClientRect(hwnd, byref(rc))
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, rc.right, rc.bottom)
        old = gdi32.SelectObject(mem, bmp)
        pt, p = self.painter, self.painter.px
        user32.FillRect(mem, byref(rc), pt.bg_brush)
        gdi32.SetBkMode(mem, 1)
        l, t, r, b = self.head
        tile = p(34)
        shapes = [("round", 0x2A2448, l, t, tile, tile, p(9))]
        focus = user32.GetFocus()
        for key, (x0, y0, x1, y1) in self.boxes.items():
            on = focus == self.edits.get(key)
            edge = max(1.0, p(2) if on else p(1))
            shapes += [("round", MenuPainter.ACCENT if on else self.BORDER, x0, y0, x1 - x0, y1 - y0, p(9)),
                       ("round", self.FIELD, x0 + edge, y0 + edge, x1 - x0 - 2 * edge, y1 - y0 - 2 * edge, p(9) - edge)]
        if self.status:
            sx, sy = self.status_rc[0], self.status_rc[1]
            shapes.append(("circle", self.status[1], sx, sy + p(6), p(8)))
        pt._shapes(mem, shapes)
        pt._text(mem, MenuPainter.ICONS["home"], self.f_glyph, MenuPainter.LABEL, l, t, l + tile, t + tile, 0x1)
        pt._text(mem, "Home Assistant", self.f_head, MenuPainter.TEXT, l + tile + p(12), t, r, t + tile)
        gdi32.SelectObject(mem, pt.f_text)
        gdi32.SetTextColor(mem, _cref(MenuPainter.MUTED))
        box = wt.RECT(*self.intro)
        user32.DrawTextW(mem, tr("ha_intro"), -1, byref(box), 0x10 | 0x800)  # WORDBREAK | NOPREFIX
        x0, y0, x1, y1 = self.link
        pt._text(mem, tr("ha_guide"), pt.f_text, MenuPainter.LABEL, x0, y0, x1, y1)
        gx = x0 + pt.text_width(tr("ha_guide"), pt.f_text) + p(5)
        pt._text(mem, MenuPainter.ICONS["link"], pt.f_link, MenuPainter.LABEL, gx, y0 + p(1), x1 + p(10), y1)
        for text, x, y in self.labels:
            pt._text(mem, text.upper(), pt.f_label, MenuPainter.MUTED, x, y, x + p(300), y + p(18))
        if self.status:
            sx, sy, sr, sb = self.status_rc
            gdi32.SelectObject(mem, pt.f_small)
            gdi32.SetTextColor(mem, _cref(self.status[1] if self.status[1] != MenuPainter.MUTED else MenuPainter.ICON))
            box = wt.RECT(sx + p(16), sy + p(1), sr, sb)
            user32.DrawTextW(mem, self.status[0], -1, byref(box), 0x10 | 0x800)
        gdi32.BitBlt(hdc, 0, 0, rc.right, rc.bottom, mem, 0, 0, 0x00CC0020)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.EndPaint(hwnd, byref(ps))

    def _draw_button(self, dis):
        pt, p = self.painter, self.painter.px
        hdc, rc, cid = dis.hDC, dis.rcItem, dis.CtlID
        l, t, r, b = rc.left, rc.top, rc.right, rc.bottom
        user32.FillRect(hdc, byref(rc), pt.bg_brush)
        pressed, disabled, focused = dis.itemState & 0x1, dis.itemState & 0x4, dis.itemState & 0x10
        shapes = []
        if cid == 1:  # Connect: the accent button
            fill, color = (0x4B3F86, 0xB8B3D6) if disabled else (0x7558F0 if pressed else MenuPainter.ACCENT, 0xFFFFFF)
            shapes.append(("round", fill, l, t, r - l, b - t, p(9)))
        elif cid == 2:
            fill, color = (0x2B2D38 if pressed else 0x23252E), (MenuPainter.MUTED if disabled else MenuPainter.TEXT)
            if focused and not disabled:
                shapes.append(("round", MenuPainter.RING, l, t, r - l, b - t, p(9)))
                shapes.append(("round", fill, l + 1, t + 1, r - l - 2, b - t - 2, p(9) - 1))
            else:
                shapes.append(("round", fill, l, t, r - l, b - t, p(9)))
        else:  # Disconnect: quiet, text only
            color = MenuPainter.TEXT if pressed or focused else MenuPainter.MUTED
            if pressed:
                shapes.append(("round", 0x23252E, l, t, r - l, b - t, p(9)))
        pt._shapes(hdc, shapes)
        gdi32.SetBkMode(hdc, 1)
        buf = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(dis.hwndItem, buf, 64)
        pt._text(hdc, buf.value, self.f_button, color, l, t, r, b, 0x1)

    def _over_link(self):
        pt_ = wt.POINT()
        user32.GetCursorPos(byref(pt_))
        user32.ScreenToClient(self.hwnd, byref(pt_))
        x0, y0, x1, y1 = self.link
        return x0 <= pt_.x < x1 and y0 <= pt_.y < y1

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            return self._on(hwnd, msg, wparam, lparam)
        except Exception as e:  # never let a drawing error take the tray down
            log(f"Home Assistant window: {e!r}")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on(self, hwnd, msg, wparam, lparam):
        if msg == 0x000F and self.painter:  # WM_PAINT
            self._paint(hwnd)
            return 0
        if msg == 0x0014:  # WM_ERASEBKGND
            return 1
        if msg in (0x0133, 0x0138) and self.painter:  # WM_CTLCOLOREDIT, WM_CTLCOLORSTATIC: the fields' colours
            gdi32.SetTextColor(wparam, _cref(MenuPainter.TEXT))
            gdi32.SetBkColor(wparam, _cref(self.FIELD))
            return self.field_brush
        if msg == 0x002B and self.painter:  # WM_DRAWITEM: buttons
            self._draw_button(DRAWITEMSTRUCT.from_address(lparam))
            return 1
        if msg == 0x0111:  # WM_COMMAND
            cid, code = wparam & 0xFFFF, (wparam >> 16) & 0xFFFF
            if code in (0x0100, 0x0200):  # EN_SETFOCUS, EN_KILLFOCUS: the focused field gets the accent border
                user32.InvalidateRect(hwnd, None, False)
            elif cid == 1 and not self.busy:  # Connect, or Enter
                self.connect()
            elif cid == 2:  # Cancel, or Esc
                user32.DestroyWindow(hwnd)
            elif cid == 3 and not self.busy:
                self.disconnect()
            return 0
        if msg == 0x0020 and (lparam & 0xFFFF) == 1 and self._over_link():  # WM_SETCURSOR over the guide link
            user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(32649)))  # IDC_HAND
            return 1
        if msg == 0x0202 and self._over_link():  # WM_LBUTTONUP
            os.startfile(ha_guide_url())
            return 0
        if msg == self.WM_RESULT:
            self._checked()
            return 0
        if msg == 0x0010:  # WM_CLOSE
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            self.hwnd = None
            self._free()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


# =============================================================================
# The app: Glowback's window. Ambient light (with a live preview of the LEDs), When to sync, Home Assistant,
# Settings, About. Closing it leaves Glowback running in the background, behind its icon next to the clock.
# =============================================================================
class MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wt.POINT), ("ptMaxSize", wt.POINT), ("ptMaxPosition", wt.POINT),
                ("ptMinTrackSize", wt.POINT), ("ptMaxTrackSize", wt.POINT)]


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [("lStructSize", wt.DWORD), ("hwndOwner", HANDLE), ("hInstance", HANDLE), ("lpstrFilter", wt.LPCWSTR),
                ("lpstrCustomFilter", wt.LPWSTR), ("nMaxCustFilter", wt.DWORD), ("nFilterIndex", wt.DWORD),
                ("lpstrFile", wt.LPWSTR), ("nMaxFile", wt.DWORD), ("lpstrFileTitle", wt.LPWSTR),
                ("nMaxFileTitle", wt.DWORD), ("lpstrInitialDir", wt.LPCWSTR), ("lpstrTitle", wt.LPCWSTR),
                ("Flags", wt.DWORD), ("nFileOffset", wt.WORD), ("nFileExtension", wt.WORD), ("lpstrDefExt", wt.LPCWSTR),
                ("lCustData", wt.LPARAM), ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wt.LPCWSTR),
                ("pvReserved", ctypes.c_void_p), ("dwReserved", wt.DWORD), ("FlagsEx", wt.DWORD)]


comdlg32 = ctypes.WinDLL("comdlg32")
_sig(comdlg32.GetOpenFileNameW, wt.BOOL, ctypes.POINTER(OPENFILENAMEW))
_sig(user32.SetCapture, HANDLE, HANDLE)
_sig(user32.ReleaseCapture, wt.BOOL)
_sig(user32.GetKeyState, ctypes.c_short, ctypes.c_int)
_sig(user32.FindWindowW, HANDLE, wt.LPCWSTR, wt.LPCWSTR)
_sig(user32.ClientToScreen, wt.BOOL, HANDLE, ctypes.POINTER(wt.POINT))
_sig(user32.AllowSetForegroundWindow, wt.BOOL, wt.DWORD)
_sig(user32.PrivateExtractIconsW, wt.UINT, wt.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(HANDLE),
     ctypes.POINTER(wt.UINT), wt.UINT, wt.UINT)
_sig(gdiplus.GdipAddPathEllipse, ctypes.c_int, VP, F, F, F, F)
_sig(gdiplus.GdipCreatePathGradientFromPath, ctypes.c_int, VP, PVP)
_sig(gdiplus.GdipSetPathGradientCenterColor, ctypes.c_int, VP, ctypes.c_uint32)
_sig(gdiplus.GdipSetPathGradientSurroundColorsWithCount, ctypes.c_int, VP, ctypes.POINTER(ctypes.c_uint32),
     ctypes.POINTER(ctypes.c_int))
_sig(gdiplus.GdipSetPathGradientSigmaBlend, ctypes.c_int, VP, F, F)
_sig(gdiplus.GdipDrawPath, ctypes.c_int, VP, VP, VP)
_sig(gdiplus.GdipSetClipPath, ctypes.c_int, VP, VP, ctypes.c_int)
_sig(gdiplus.GdipResetClip, ctypes.c_int, VP)


class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("fMask", wt.UINT), ("fType", wt.UINT), ("fState", wt.UINT), ("wID", wt.UINT),
                ("hSubMenu", HANDLE), ("hbmpChecked", HANDLE), ("hbmpUnchecked", HANDLE),
                ("dwItemData", ctypes.c_size_t), ("dwTypeData", wt.LPWSTR), ("cch", wt.UINT), ("hbmpItem", HANDLE)]


_sig(user32.InsertMenuItemW, wt.BOOL, HANDLE, wt.UINT, wt.BOOL, ctypes.POINTER(MENUITEMINFOW))


def pick_program(owner):
    """The Windows "Open" dialog, for a program that is not running now: its full path, or ''."""
    buf = ctypes.create_unicode_buffer(1024)
    filt = ctypes.create_unicode_buffer(f"{tr('sync_programs')} (*.exe)\0*.exe\0\0")
    o = OPENFILENAMEW()
    o.lStructSize, o.hwndOwner = sizeof(o), owner
    o.lpstrFilter = ctypes.cast(filt, wt.LPCWSTR)
    o.lpstrFile, o.nMaxFile = ctypes.cast(buf, wt.LPWSTR), len(buf)
    o.lpstrInitialDir = os.environ.get("ProgramFiles", "C:\\")
    o.Flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x00000008  # EXPLORER, FILEMUSTEXIST, PATHMUSTEXIST, NOCHANGEDIR
    return buf.value if comdlg32.GetOpenFileNameW(byref(o)) else ""


class POINTF(ctypes.Structure):
    _fields_ = [("X", F), ("Y", F)]


_sig(gdiplus.GdipCreateLineBrush, ctypes.c_int, ctypes.POINTER(POINTF), ctypes.POINTER(POINTF), ctypes.c_uint32,
     ctypes.c_uint32, ctypes.c_int, PVP)
_sig(gdiplus.GdipSetLinePresetBlend, ctypes.c_int, VP, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(F), ctypes.c_int)
_sig(gdiplus.GdipCreateBitmapFromScan0, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
     ctypes.c_void_p, PVP)
_sig(gdiplus.GdipDrawImageRect, ctypes.c_int, VP, VP, F, F, F, F)
_sig(gdiplus.GdipSetInterpolationMode, ctypes.c_int, VP, ctypes.c_int)
_sig(gdiplus.GdipDisposeImage, ctypes.c_int, VP)
_sig(gdiplus.GdipCreateRegion, ctypes.c_int, PVP)
_sig(gdiplus.GdipGetClip, ctypes.c_int, VP, VP)
_sig(gdiplus.GdipSetClipRegion, ctypes.c_int, VP, VP, ctypes.c_int)
_sig(gdiplus.GdipDeleteRegion, ctypes.c_int, VP)
_sig(gdiplus.GdipGetImageGraphicsContext, ctypes.c_int, VP, PVP)
_sig(gdiplus.GdipSetClipRectI, ctypes.c_int, VP, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(gdi32.IntersectClipRect, ctypes.c_int, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(gdi32.SelectClipRgn, ctypes.c_int, HANDLE, HANDLE)


def gdip_hgrad(g, colors, x, y, w, h, r, alpha=255):
    """Fills a rounded rectangle with a left-to-right gradient through `colors`, evenly spaced."""
    if w <= 0 or h <= 0 or not colors:
        return
    colors = list(colors) if len(colors) > 1 else [colors[0], colors[0]]
    n, brush = len(colors), VP()
    p1, p2 = POINTF(x - 1, y), POINTF(x + w + 1, y)  # a pixel beyond each end: no wrapped colour at the edges
    if gdiplus.GdipCreateLineBrush(byref(p1), byref(p2), Gfx.argb(colors[0], alpha), Gfx.argb(colors[-1], alpha), 0,
                                   byref(brush)):
        return
    blend = (ctypes.c_uint32 * n)(*(Gfx.argb(c, alpha) for c in colors))
    pos = (F * n)(*(i / (n - 1) for i in range(n)))
    gdiplus.GdipSetLinePresetBlend(brush, blend, pos, n)
    path = Gfx.round_path(x, y, w, h, r)
    gdiplus.GdipFillPath(g, brush, path)
    gdiplus.GdipDeletePath(path)
    gdiplus.GdipDeleteBrush(brush)


class Gfx:
    """GDI+ with alpha on a device context: rounded fills and outlines, circles, soft glows, gradients, pictures,
    clipping."""

    def __init__(self, hdc, clip=None):
        self.g, self.base = VP(), clip  # clip (l, t, r, b): only that part is painted
        self.ok = bool(_gdip_start()) and gdiplus.GdipCreateFromHDC(hdc, byref(self.g)) == 0
        if self.ok:
            gdiplus.GdipSetSmoothingMode(self.g, 4)  # antialiased
            gdiplus.GdipSetPixelOffsetMode(self.g, 4)
            self._base(0)

    def _base(self, mode):
        """Back to (mode 0), or within (mode 1), the part being painted."""
        if self.base:
            l, t, r, b = self.base
            gdiplus.GdipSetClipRectI(self.g, l, t, r - l, b - t, mode)
        elif mode == 0:
            gdiplus.GdipResetClip(self.g)

    def close(self):
        if self.ok:
            gdiplus.GdipDeleteGraphics(self.g)
            self.ok = False

    @staticmethod
    def argb(color, alpha=255):
        return ((int(alpha) & 0xFF) << 24) | (color & 0xFFFFFF)

    @staticmethod
    def round_path(x, y, w, h, r):
        path = VP()
        gdiplus.GdipCreatePath(0, byref(path))
        d = max(0.5, min(2.0 * r, w, h))
        gdiplus.GdipAddPathArc(path, x, y, d, d, 180, 90)
        gdiplus.GdipAddPathArc(path, x + w - d, y, d, d, 270, 90)
        gdiplus.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0, 90)
        gdiplus.GdipAddPathArc(path, x, y + h - d, d, d, 90, 90)
        gdiplus.GdipClosePathFigure(path)
        return path

    def _glow(self, g, color, cx, cy, rx, ry, alpha):
        path, brush = VP(), VP()
        gdiplus.GdipCreatePath(0, byref(path))
        gdiplus.GdipAddPathEllipse(path, cx - rx, cy - ry, 2 * rx, 2 * ry)
        if gdiplus.GdipCreatePathGradientFromPath(path, byref(brush)) == 0:
            gdiplus.GdipSetPathGradientCenterColor(brush, self.argb(color, alpha))
            edge, n = ctypes.c_uint32(self.argb(color, 0)), ctypes.c_int(1)
            gdiplus.GdipSetPathGradientSurroundColorsWithCount(brush, byref(edge), byref(n))
            gdiplus.GdipSetPathGradientSigmaBlend(brush, 1.0, 1.0)
            gdiplus.GdipFillPath(g, brush, path)
            gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeletePath(path)

    def draw(self, shape):
        if not self.ok:
            return
        kind = shape[0]
        if kind in ("round", "circle"):  # ("round", color, x, y, w, h, radius[, alpha]) / ("circle", color, x, y, d[, alpha])
            if kind == "round":
                _, color, x, y, w, h, r, *a = shape
            else:
                _, color, x, y, w, *a = shape
                h, r = w, w / 2
            if w <= 0 or h <= 0:
                return
            brush = VP()
            gdiplus.GdipCreateSolidFill(self.argb(color, a[0] if a else 255), byref(brush))
            if kind == "circle":
                gdiplus.GdipFillEllipse(self.g, brush, x, y, w, h)
            else:
                path = self.round_path(x, y, w, h, r)
                gdiplus.GdipFillPath(self.g, brush, path)
                gdiplus.GdipDeletePath(path)
            gdiplus.GdipDeleteBrush(brush)
        elif kind == "outline":  # ("outline", color, x, y, w, h, radius, width[, alpha])
            _, color, x, y, w, h, r, width, *a = shape
            pen = VP()
            gdiplus.GdipCreatePen1(self.argb(color, a[0] if a else 255), width, 2, byref(pen))  # UnitPixel
            half = width / 2
            path = self.round_path(x + half, y + half, w - width, h - width, max(0.5, r - half))
            gdiplus.GdipDrawPath(self.g, pen, path)
            gdiplus.GdipDeletePath(path)
            gdiplus.GdipDeletePen(pen)
        elif kind == "glow":  # ("glow", color, cx, cy, rx, ry, alpha): light that fades out, like on a wall
            self._glow(self.g, *shape[1:])
        elif kind == "glows":  # ("glows", [(color, cx, cy, rx, ry, alpha)], x0, y0, x1, y1): glows, drawn at a
            _, items, x0, y0, x1, y1 = shape  # quarter of the size then stretched (it is all blur): much faster
            if not items:
                return
            x = max(x0, min(cx - rx for _, cx, cy, rx, ry, _ in items))  # only where there is light
            y = max(y0, min(cy - ry for _, cx, cy, rx, ry, _ in items))
            w = min(x1, max(cx + rx for _, cx, cy, rx, ry, _ in items)) - x
            h = min(y1, max(cy + ry for _, cx, cy, rx, ry, _ in items)) - y
            k, bmp, g2 = 4.0, VP(), VP()
            bw, bh = max(1, int(w / k) + 2), max(1, int(h / k) + 2)
            if gdiplus.GdipCreateBitmapFromScan0(bw, bh, 0, 0xE200B, None, byref(bmp)) == 0:  # 32bppPARGB
                if gdiplus.GdipGetImageGraphicsContext(bmp, byref(g2)) == 0:
                    for color, cx, cy, rx, ry, alpha in items:
                        self._glow(g2, color, (cx - x) / k, (cy - y) / k, rx / k, ry / k, alpha)
                    gdiplus.GdipDeleteGraphics(g2)
                    gdiplus.GdipSetInterpolationMode(self.g, 6)  # high quality bilinear: here the fastest smooth one
                    gdiplus.GdipDrawImageRect(self.g, bmp, x, y, bw * k, bh * k)
                gdiplus.GdipDisposeImage(bmp)
        elif kind == "arc":  # ("arc", color, x, y, d, start, sweep, width): loaders
            _, color, x, y, d, start, sweep, width = shape
            pen = VP()
            gdiplus.GdipCreatePen1(self.argb(color), width, 2, byref(pen))
            gdiplus.GdipSetPenStartCap(pen, 2)
            gdiplus.GdipSetPenEndCap(pen, 2)
            gdiplus.GdipDrawArc(self.g, pen, x, y, d, d, start, sweep)
            gdiplus.GdipDeletePen(pen)
        elif kind == "hgrad":  # ("hgrad", colors, x, y, w, h, radius[, alpha]): a gradient, left to right
            gdip_hgrad(self.g, *shape[1:])
        elif kind == "image":  # ("image", (width, height, BGRA rows), x, y, w, h, radius): the screen's picture
            _, (tw, th, data), x, y, w, h, r = shape
            bmp, saved = VP(), VP()
            if gdiplus.GdipCreateBitmapFromScan0(tw, th, tw * 4, 0x22009, data, byref(bmp)) == 0:  # 32bppRGB
                gdiplus.GdipCreateRegion(byref(saved))
                gdiplus.GdipGetClip(self.g, saved)
                path = self.round_path(x, y, w, h, r)
                gdiplus.GdipSetClipPath(self.g, path, 1)  # CombineModeIntersect: inside the card too
                gdiplus.GdipDeletePath(path)
                gdiplus.GdipSetInterpolationMode(self.g, 7)  # high quality bicubic
                gdiplus.GdipDrawImageRect(self.g, bmp, x, y, w, h)
                gdiplus.GdipSetClipRegion(self.g, saved, 0)
                gdiplus.GdipDeleteRegion(saved)
                gdiplus.GdipDisposeImage(bmp)
        elif kind == "clip":  # ("clip", x, y, w, h, radius): what follows stays inside
            _, x, y, w, h, r = shape
            path = self.round_path(x, y, w, h, r)
            gdiplus.GdipSetClipPath(self.g, path, 0)  # CombineModeReplace
            gdiplus.GdipDeletePath(path)
            self._base(1)
        elif kind == "unclip":
            self._base(0)


class AppWindow:
    """Glowback's window: a sidebar of pages, drawn from display lists rebuilt on every paint, so it always shows
    the current state. Widgets registered while composing a page serve the mouse, the keyboard and focus.
    Pages: Ambient light (live preview, the look, brightness), Profiles (night, apps), Home Assistant, Settings,
    About."""
    PAGES = (("light", "light", "nav_light"), ("profiles", "layers", "nav_profiles"), ("home", "home", "nav_home"),
             ("matter", "phone", "nav_matter"), ("settings", "settings", "nav_settings"), ("about", "info", "nav_about"))
    MODE_ICONS = {"zones": "monitor", "average": "palette", "color": "drop", "gradient": "gradient", "music": "music"}
    STYLE_ICONS = {"pulse": "pulse", "spectrum": "spectrum", "wave": "wave"}
    SLIDERS = ("brightness", "hue", "sat", "sens", "night_bright")
    BG, CARD, LINE, HOVER, SELECT = 0x121317, 0x1A1B21, 0x24262E, 0x212329, 0x1F2129
    FIELD, FIELD_LINE = 0x0F1013, 0x2E3140
    SIZE, MIN = (1040, 790), (820, 560)  # at 100 %
    LANG_NAMES = (("", None), ("en", "English"), ("fr", "Français"), ("es", "Español"), ("de", "Deutsch"),
                  ("it", "Italiano"), ("pt", "Português (Brasil)"))
    SITE_URL = "https://ilyomix.github.io/glowback/"

    def __init__(self, tray):
        self.tray, self.state = tray, tray.state
        self.hwnd = self.painter = self.icon = self.icon_big = None
        self.k, self.fonts, self.size = 1.0, {}, (0, 0)
        self.page, self.scroll, self.max_scroll = "light", 0, 0
        self.widgets, self.side, self.content = [], ([], []), ([], [])
        self.hover = self.pressed = self.focus = self.drag = None
        self.focus_visible = self.tracking = False
        self.app_icons, self.menu_items, self.mons, self.mons_t = {}, [], [], -99.0
        self.draft = dict(app="", name="", path="", when="foreground", screen="", look=None)  # the app being added
        self.stop_sel, self.hue_memo = 0, None  # the gradient's color being edited; the hue of a white
        self.bufs, self.preview_rect = None, None  # paint buffers; where the live preview is
        self.sw = self.cx0 = self.cx1 = 0
        self._ref = WNDPROC(self._proc)
        self.cls = f"GlowbackApp{id(self)}"  # a class per object: each keeps its own window procedure
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._ref, k32.GetModuleHandleW(None), self.cls
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW
        icon = ensure_icons()[0]
        wc.hIcon = user32.LoadImageW(None, icon, 1, 48, 48, 0x10)
        wc.hIconSm = user32.LoadImageW(None, icon, 1, 16, 16, 0x10)
        user32.RegisterClassExW(byref(wc))

    # ---- scale, fonts, opening and closing
    def px(self, v):
        return round(v * self.k)

    def set_scale(self, k):
        self._free_gdi()
        self.k = k
        self.painter = MenuPainter(k, None)
        face, glyphs = ui_font_face(), icon_font_face()
        mk = lambda size, weight, f=face: gdi32.CreateFontW(-round(size * k), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, f)
        self.fonts = dict(page=mk(26, 600), h2=mk(15, 600), nav=mk(14, 400), body=mk(14, 400), button=mk(13.5, 600),
                          name=mk(17, 600), hero=mk(30, 600), icon=mk(18, 400, glyphs), icon_s=mk(14, 400, glyphs),
                          icon_l=mk(22, 400, glyphs))
        path = ensure_icons()[0]
        self.icon = user32.LoadImageW(None, path, 1, self.px(32), self.px(32), 0x10)
        self.icon_big = user32.LoadImageW(None, path, 1, self.px(72), self.px(72), 0x10)

    def _free_gdi(self):
        for f in self.fonts.values():
            gdi32.DeleteObject(f)
        self.fonts = {}
        if self.painter:
            self.painter.close()
            self.painter = None
        for h in [self.icon, self.icon_big] + list(self.app_icons.values()):
            if h:
                user32.DestroyIcon(h)
        self.icon = self.icon_big = None
        self.app_icons = {}

    def open(self, page=None):
        if page:
            self.page, self.scroll = page, 0
        if page == "settings" or not self.hwnd:
            self.tray.autostart = autostart_enabled()
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.ShowWindow(self.hwnd, 9 if user32.IsIconic(self.hwnd) else 5)  # SW_RESTORE, SW_SHOW
            user32.SetForegroundWindow(self.hwnd)
            self._timers()
            self.invalidate()
            return
        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        mon = user32.MonitorFromPoint(pt, 2)
        dpi_x, dpi_y = wt.UINT(96), wt.UINT(96)
        if shcore:
            shcore.GetDpiForMonitor(mon, 0, byref(dpi_x), byref(dpi_y))
        self.set_scale(dpi_x.value / 96.0)
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        user32.GetMonitorInfoW(mon, byref(mi))
        work = mi.rcWork
        w = min(self.px(self.SIZE[0]), work.right - work.left - self.px(32))
        h = min(self.px(self.SIZE[1]), work.bottom - work.top - self.px(32))
        x, y = work.left + (work.right - work.left - w) // 2, work.top + (work.bottom - work.top - h) // 2
        self.hwnd = user32.CreateWindowExW(0, self.cls, "Glowback", 0x00CF0000, x, y, w, h, None, None,
                                           k32.GetModuleHandleW(None), None)  # WS_OVERLAPPEDWINDOW
        if not self.hwnd:
            err = ctypes.get_last_error()
            self._free_gdi()
            log(f"App window: Windows refused it ({ctypes.FormatError(err).strip()} [{err}]); {gui_objects()}")
            return
        for attr, value in ((20, 1), (35, _cref(self.BG)), (34, _cref(0x2C2E38))):  # dark, caption, border colours
            v = wt.DWORD(value)
            dwmapi.DwmSetWindowAttribute(self.hwnd, attr, byref(v), 4)
        user32.ShowWindow(self.hwnd, 5)
        user32.SetForegroundWindow(self.hwnd)
        self._timers()

    def invalidate(self):
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, False)

    def _timers(self):
        if not self.hwnd:
            return
        if self.page == "light" and not user32.IsIconic(self.hwnd):
            user32.SetTimer(self.hwnd, 1, 40, None)  # live preview, 25 frames a second
        else:
            user32.KillTimer(self.hwnd, 1)
        user32.SetTimer(self.hwnd, 2, 1000, None)  # LED count, Home Assistant status...
        if self.tray.checking:
            user32.SetTimer(self.hwnd, 3, 33, None)  # the update check's loader

    # ---- display lists
    def S(self, *shape, side=False):
        (self.side if side else self.content)[0].append(shape)

    def T(self, text, font, color, l, t, r, b, flags=0, side=False):
        (self.side if side else self.content)[1].append(("text", text, font, color, l, t, r, b, flags))

    def W(self, text, font, color, l, t, r, b):
        self.content[1].append(("wrap", text, font, color, l, t, r, b))

    def I(self, hicon, x, y, size, side=False):
        (self.side if side else self.content)[1].append(("icon", hicon, x, y, size))

    def add(self, wid, kind, rect, side=False, focus=True, **kw):
        self.widgets.append(dict(id=wid, kind=kind, rect=tuple(int(v) for v in rect), side=side, focus=focus, **kw))

    def tw(self, text, font):
        return self.painter.text_width(text, font)

    def wrap_h(self, text, font, width):
        rc = wt.RECT(0, 0, int(width), 0)
        gdi32.SelectObject(self.painter.mdc, font)
        user32.DrawTextW(self.painter.mdc, text, -1, byref(rc), 0x10 | 0x400 | 0x800)  # WORDBREAK|CALCRECT|NOPREFIX
        return rc.bottom

    # ---- building blocks
    def _status(self):
        text, dot = self.state.status()
        return text, {"on": MenuPainter.GREEN, "off": MenuPainter.OFF + 0x202020, "none": MenuPainter.AMBER}[dot]

    def _nav(self, wid, x, y, w, icon, text, selected, quiet=False):
        p, h, ic = self.px, self.px(38), MenuPainter.ICONS
        hov = self.hover == wid
        if selected:
            self.S("round", self.SELECT, x, y, w, h, p(7), side=True)
            self.S("round", MenuPainter.ACCENT, x + p(1), y + h / 2 - p(8), p(3), p(16), p(1.5), side=True)
        elif hov:
            self.S("round", 0x1B1C22, x, y, w, h, p(7), side=True)
        color = MenuPainter.MUTED if quiet and not hov else MenuPainter.TEXT
        glyph = MenuPainter.LABEL if selected else (color if quiet else MenuPainter.ICON)
        self.T(ic[icon], self.fonts["icon"], glyph, x + p(10), y, x + p(40), y + h, 0x1, side=True)
        self.T(text, self.fonts["nav"], color, x + p(48), y, x + w - p(8), y + h, 0x8000, side=True)
        self.add(wid, "nav", (x, y, x + w, y + h), side=True, radius=p(7))

    def _card(self, y, h, x0=None, x1=None):
        p = self.px
        x0 = self.cx0 if x0 is None else x0
        x1 = self.cx1 if x1 is None else x1
        self.S("round", self.CARD, x0, y, x1 - x0, h, p(10))
        self.S("outline", self.LINE, x0, y, x1 - x0, h, p(10), max(1.0, self.k))

    def _sep(self, y):
        self.S("round", self.LINE, self.cx0 + self.px(16), y, self.cx1 - self.cx0 - self.px(32), max(1, self.px(1)), 0)

    def _row_hover(self, wid, y, h):
        if self.hover == wid:
            p = self.px
            self.S("round", self.HOVER, self.cx0 + p(4), y + p(4), self.cx1 - self.cx0 - p(8), h - p(8), p(7))

    def _header(self, y, title, sub=None):
        p = self.px
        self.T(title, self.fonts["page"], MenuPainter.TEXT, self.cx0, y, self.cx1, y + p(40))
        y += p(44)
        if sub:
            h = self.wrap_h(sub, self.fonts["body"], self.cx1 - self.cx0)
            self.W(sub, self.fonts["body"], MenuPainter.MUTED, self.cx0, y, self.cx1, y + h)
            y += h
        return y + p(24)

    def _label(self, y, text):
        p = self.px
        self.T(text.upper(), self.painter.f_label, MenuPainter.LABEL, self.cx0 + p(4), y, self.cx1, y + p(18))
        return y + p(26)

    def _row_text(self, y, h, icon, title, desc=None, right=None, icon_color=None, hicon=None, desc_color=None):
        p, ic = self.px, MenuPainter.ICONS
        x = self.cx0 + p(20)
        if hicon:
            self.I(hicon, x, y + (h - p(28)) / 2, p(28))
            x += p(44)
        elif icon:
            self.T(ic[icon], self.fonts["icon"], icon_color or MenuPainter.ICON, x, y, x + p(24), y + h, 0x1)
            x += p(42)
        r = self.cx1 - p(20) if right is None else right
        if desc:
            self.T(title, self.fonts["body"], MenuPainter.TEXT, x, y + p(10), r, y + h / 2 + p(2), 0x8000)
            self.T(desc, self.painter.f_small, desc_color or MenuPainter.MUTED, x, y + h / 2 + p(1), r, y + h - p(9), 0x8000)
        else:
            self.T(title, self.fonts["body"], MenuPainter.TEXT, x, y, r, y + h, 0x8000)

    def _toggle(self, wid, x, y, on, row=None):
        p = self.px
        w, h = p(42), p(22)
        hov = self.hover == wid
        if on:
            self.S("round", 0x9A80FF if hov else MenuPainter.ACCENT, x, y, w, h, h / 2)
            d = h - p(8)
            self.S("circle", 0xFFFFFF, x + w - d - p(4), y + p(4), d)
        else:
            edge = 0xC5C9D4 if hov else 0x8C91A1
            self.S("outline", edge, x, y, w, h, h / 2, max(1.0, self.k * 1.2))
            d = h - p(10)
            self.S("circle", edge, x + p(5), y + p(5), d)
        self.add(wid, "toggle", (x, y, x + w, y + h), radius=h / 2)
        if row:  # the whole row switches it too
            self.add(wid, "toggle", row, focus=False)

    def _button(self, wid, right, y, text, style="secondary", icon=None, busy=False, h=None):
        """A button right-aligned on `right`; returns its left edge."""
        p, ic = self.px, MenuPainter.ICONS
        h = h or p(34)
        f = self.fonts["button"]
        w = self.tw(text, f) + p(30) + (p(24) if icon or busy else 0)
        x = right - w
        hov, prs = self.hover == wid, self.pressed == wid
        if style == "primary":
            fill, color = (0x7558F0 if prs else 0x9A80FF if hov else MenuPainter.ACCENT), 0xFFFFFF
        elif style == "quiet":
            fill, color = (0x25272F if prs else 0x202229 if hov else None), (MenuPainter.TEXT if hov else MenuPainter.ICON)
        else:
            fill, color = (0x23252D if prs else 0x2E303A if hov else 0x272932), MenuPainter.TEXT
        if fill is not None:
            self.S("round", fill, x, y, w, h, p(7))
        if style == "secondary":
            self.S("outline", 0x363843, x, y, w, h, p(7), max(1.0, self.k))
        tx = x + p(15)
        if busy:
            d, width, now = p(14), max(1.5, self.k * 1.8), time.monotonic()
            sweep = 40 + 230 * (0.5 - 0.5 * math.cos(now * 2 * math.pi / 1.6))
            self.S("arc", MenuPainter.LINE, tx, y + (h - d) / 2, d, 0, 360, width)
            self.S("arc", MenuPainter.ACCENT, tx, y + (h - d) / 2, d, (now * 320) % 360, sweep, width)
            tx += p(24)
        elif icon:
            self.T(ic[icon], self.fonts["icon_s"], color, tx, y, tx + p(16), y + h, 0x1)
            tx += p(24)
        self.T(text, f, color, tx, y, x + w - p(12), y + h)
        self.add(wid, "button", (x, y, x + w, y + h), radius=p(7))
        return x

    def _picker(self, wid, x, y, w, text, hicon=None, glyph=None, swatch=None, stops=None, disabled=False):
        p, h, ic = self.px, self.px(36), MenuPainter.ICONS
        hov = self.hover == wid and not disabled
        self.S("round", self.FIELD, x, y, w, h, p(7))
        self.S("outline", 0x4A4E5E if hov else self.FIELD_LINE, x, y, w, h, p(7), max(1.0, self.k))
        tx = x + p(12)
        if hicon:
            self.I(hicon, tx, y + (h - p(20)) / 2, p(20))
            tx += p(28)
        elif swatch is not None:
            d = p(16)
            self.S("circle", swatch, tx + p(1), y + (h - d) / 2, d)
            tx += p(26)
        elif stops:
            self.S("hgrad", stops, tx, y + (h - p(12)) / 2, p(24), p(12), p(6))
            tx += p(32)
        elif glyph:
            self.T(ic[glyph], self.fonts["icon_s"], MenuPainter.MUTED if disabled else MenuPainter.ICON, tx, y,
                   tx + p(18), y + h, 0x1)
            tx += p(26)
        self.T(text, self.fonts["body"], MenuPainter.MUTED if disabled else MenuPainter.TEXT, tx, y, x + w - p(34),
               y + h, 0x8000)
        if not disabled:
            self.T(ic["chev_down"], self.fonts["icon_s"], MenuPainter.MUTED, x + w - p(32), y, x + w - p(10), y + h, 0x1)
            self.add(wid, "picker", (x, y, x + w, y + h), radius=p(7))

    def _slider(self, wid, x0, x1, cy, value, track=None, knob=None):
        """A 0-100 slider; `track`: colors of a gradient track (hue...), `knob`: the knob's color."""
        p = self.px
        fx = x0 + (x1 - x0) * max(0.0, min(100.0, value)) / 100
        if track is None:
            th = p(4)
            self.S("round", 0x3A3D49, x0, cy - th / 2, x1 - x0, th, th / 2)
            if fx > x0:
                self.S("round", MenuPainter.ACCENT, x0, cy - th / 2, fx - x0, th, th / 2)
        else:
            th = p(10)
            self.S("hgrad", track, x0, cy - th / 2, x1 - x0, th, th / 2)
        d = p(22)
        if knob is None:
            inner = p(12) if self.hover == wid or self.drag == wid else p(10)
            self.S("circle", 0x2B2D38, fx - d / 2, cy - d / 2, d)
            self.S("outline", 0x45485A, fx - d / 2, cy - d / 2, d, d, d / 2, max(1.0, self.k))
            self.S("circle", MenuPainter.ACCENT, fx - inner / 2, cy - inner / 2, inner)
        else:
            ring = p(4) if self.hover == wid or self.drag == wid else p(3)
            self.S("circle", 0xFFFFFF, fx - d / 2, cy - d / 2, d)
            self.S("circle", knob, fx - d / 2 + ring, cy - d / 2 + ring, d - 2 * ring)
        self.add(wid, "slider", (x0 - p(12), cy - p(16), x1 + p(12), cy + p(16)), x0=x0, x1=x1, radius=p(16))

    def _mode_tile(self, wid, x, y, w, h, icon, title, selected):
        """A compact choice: its icon over its name."""
        p, ic = self.px, MenuPainter.ICONS
        hov = self.hover == wid
        self.S("round", 0x1D1A30 if selected else (self.HOVER if hov else self.CARD), x, y, w, h, p(10))
        self.S("outline", MenuPainter.ACCENT if selected else self.LINE, x, y, w, h, p(10),
               max(1.5, p(2)) if selected else max(1.0, self.k))
        self.T(ic[icon], self.fonts["icon_l"], MenuPainter.LABEL if selected else MenuPainter.ICON, x, y + p(12), x + w,
               y + p(44), 0x1)
        self.T(title, self.fonts["body"], MenuPainter.TEXT, x + p(6), y + p(46), x + w - p(6), y + h - p(12), 0x1 | 0x8000)
        self.add(wid, "tile", (x, y, x + w, y + h), radius=p(10))

    def _swatch(self, wid, x, y, d, color=None, selected=False, stops=None, w=None):
        """A color (a disc) or a gradient (a pill) to pick; a ring shows the chosen one."""
        p = self.px
        w = w or d
        hov = self.hover == wid
        if selected or hov:
            g = p(4)
            self.S("outline", 0xFFFFFF if selected else 0x6B6F80, x - g, y - g, w + 2 * g, d + 2 * g, (d + 2 * g) / 2,
                   max(1.5, p(2)))
        if stops:
            self.S("hgrad", stops, x, y, w, d, d / 2)
        else:
            self.S("circle", color, x, y, d)
        self.add(wid, "swatch", (x - p(5), y - p(5), x + w + p(5), y + d + p(5)), radius=(d + p(10)) / 2)

    def _segmented(self, prefix, x0, x1, y, options, current):
        """Choices side by side, one of them on: options are (value, glyph, text)."""
        p, ic, h = self.px, MenuPainter.ICONS, self.px(40)
        self.S("round", self.FIELD, x0, y, x1 - x0, h, p(9))
        self.S("outline", self.FIELD_LINE, x0, y, x1 - x0, h, p(9), max(1.0, self.k))
        w = (x1 - x0 - p(8)) / len(options)
        for i, (value, glyph, text) in enumerate(options):
            sx, wid = x0 + p(4) + i * w, f"{prefix}:{value}"
            on = value == current
            if on:
                self.S("round", MenuPainter.ACCENT, sx, y + p(4), w, h - p(8), p(6))
            elif self.hover == wid:
                self.S("round", self.HOVER, sx, y + p(4), w, h - p(8), p(6))
            color = 0xFFFFFF if on else MenuPainter.ICON
            f = self.fonts["button"]
            full = self.tw(text, f) + (p(24) if glyph else 0)
            tx = sx + max(p(6), (w - full) / 2)
            if glyph and full < w - p(8):
                self.T(ic[glyph], self.fonts["icon_s"], color, tx, y, tx + p(18), y + h, 0x1)
                tx += p(24)
            self.T(text, f, color, tx, y, sx + w - p(4), y + h, 0x8000)
            self.add(wid, "tile", (sx, y + p(4), sx + w, y + h - p(4)), radius=p(6))

    def _stepper(self, wid, right, y, text):
        """[<] text [>], right-aligned on `right`: returns its left edge."""
        p, ic = self.px, MenuPainter.ICONS
        h, bw = p(36), p(34)
        w = 2 * bw + max(self.tw("00:00", self.fonts["body"]), self.tw(text, self.fonts["body"])) + p(14)
        x = right - w
        self.S("round", self.FIELD, x, y, w, h, p(7))
        self.S("outline", self.FIELD_LINE, x, y, w, h, p(7), max(1.0, self.k))
        for key, gx, glyph in (("-", x, "chev_left"), ("+", x + w - bw, "chev_right")):
            if self.hover == f"{wid}:{key}":
                self.S("round", self.HOVER, gx + p(3), y + p(3), bw - p(6), h - p(6), p(5))
            self.T(ic[glyph], self.fonts["icon_s"], MenuPainter.ICON, gx, y, gx + bw, y + h, 0x1)
            self.add(f"{wid}:{key}", "button", (gx, y, gx + bw, y + h), radius=p(7))
        self.T(text, self.fonts["body"], MenuPainter.TEXT, x + bw, y, x + w - bw, y + h, 0x1)
        return x

    def _icon_button(self, wid, x, y, size, glyph, enabled=True):
        p, ic = self.px, MenuPainter.ICONS
        hov = self.hover == wid and enabled
        self.S("round", 0x2E303A if hov else 0x272932, x, y, size, size, p(7))
        self.S("outline", 0x363843, x, y, size, size, p(7), max(1.0, self.k))
        self.T(ic[glyph], self.fonts["icon_s"], MenuPainter.TEXT if enabled else 0x4A4E5C, x, y, x + size, y + size, 0x1)
        if enabled:
            self.add(wid, "button", (x, y, x + size, y + size), radius=p(7))

    def _tile(self, wid, x, y, w, h, icon, title, desc, selected):
        p, ic = self.px, MenuPainter.ICONS
        hov = self.hover == wid
        self.S("round", 0x1D1A30 if selected else (self.HOVER if hov else self.CARD), x, y, w, h, p(10))
        self.S("outline", MenuPainter.ACCENT if selected else self.LINE, x, y, w, h, p(10),
               max(1.5, p(2)) if selected else max(1.0, self.k))
        self.S("round", 0x2A2448 if selected else 0x25272F, x + p(18), y + p(18), p(36), p(36), p(9))
        self.T(ic[icon], self.fonts["icon"], MenuPainter.LABEL if selected else MenuPainter.ICON,
               x + p(18), y + p(18), x + p(54), y + p(54), 0x1)
        tx = x + p(70)
        self.T(title, self.fonts["h2"], MenuPainter.TEXT, tx, y + p(16), x + w - p(48), y + p(40), 0x8000)
        dh = self.wrap_h(desc, self.painter.f_small, x + w - p(20) - tx)
        self.content[1].append(("wrap", desc, self.painter.f_small, MenuPainter.MUTED, tx, y + p(42), x + w - p(20),
                                y + p(42) + dh))
        d = p(18)
        rx, ry = x + w - p(18) - d, y + p(18)
        if selected:
            self.S("circle", MenuPainter.ACCENT, rx, ry, d)
            self.S("circle", 0xFFFFFF, rx + d / 2 - p(3.5), ry + d / 2 - p(3.5), p(7))
        else:
            self.S("outline", MenuPainter.RING, rx, ry, d, d, d / 2, max(1.2, self.k * 1.5))
        self.add(wid, "tile", (x, y, x + w, y + h), radius=p(10))

    # ---- conditions, as words
    def _monitors(self, fresh=False):
        if fresh or time.monotonic() - self.mons_t > 5:
            self.mons, self.mons_t = list_monitors(), time.monotonic()
        return self.mons

    def _app_name(self, r):
        if not r.get("app"):
            return tr("sync_any_app")
        return r.get("name") or r["app"][:-4]

    def _screen_text(self, screen, short=False):
        if not screen:
            return tr("sync_any_screen")
        if screen == "leds":
            names = self.state.screens
            return tr("sync_led_screen") + (f" · {names[0]}" if names and not short else "")
        m = next((m for m in self._monitors() if screen in (m.name, m.device)), None)
        return (tr("sync_screen_n", n=m.index) + ("" if short else f" · {screen}")) if m else screen

    def _rule_desc(self, r):
        when = tr("sync_" + r["when"])
        return when if r["when"] == "playing" else f"{when} · {self._screen_text(r['screen'])}"

    def _rule_text(self, r):
        if not r:
            return ""
        when = tr("sync_" + r["when"])
        text = f"{self._app_name(r)} {when[:1].lower()}{when[1:]}"
        return text + (f" · {self._screen_text(r['screen'], short=True)}" if r["screen"] else "")

    def _look_label(self, look, auto_text):
        """A profile's look for a picker: (text, picker options: its glyph, color or gradient)."""
        s = self.state
        if look is None:
            return auto_text, dict(glyph="sparkle")
        m = look["mode"]
        if m == "color":
            c = hex_color(look.get("color"))
            name = next((n for n, v in SWATCHES if v == c), None)
            text = tr("color_" + name) if name else (color_hex(c) if c is not None else tr("palette_color"))
            return text, dict(swatch=s.color if c is None else c)
        if m == "gradient":
            st = clean_stops(look.get("gradient"))
            name = next((n for n, v in GRADIENTS if v == st), None)
            text = tr("gradient_" + name) if name else (tr("mode_gradient") if st else tr("palette_gradient"))
            return text, dict(stops=st or s.gradient)
        if m == "music":
            return f"{tr('mode_music')} · {tr('style_' + look.get('style', s.music_style))}", dict(glyph="music")
        if m in ("device", "off"):
            return tr("look_" + m), dict(glyph="bulb" if m == "device" else "power")
        return tr("mode_" + m), dict(glyph=self.MODE_ICONS[m])

    def _look_name(self, look):
        """A full look (what the LEDs show now) in a few words."""
        m = look["mode"]
        if m == "color":
            name = next((n for n, v in SWATCHES if v == look["color"]), None)
            return f"{tr('mode_color')} · " + (tr("color_" + name) if name else color_hex(look["color"]))
        if m == "gradient":
            name = next((n for n, v in GRADIENTS if v == tuple(look["gradient"])), None)
            return tr("mode_gradient") + (f" · {tr('gradient_' + name)}" if name else "")
        if m == "music":
            return f"{tr('mode_music')} · {tr('style_' + look['style'])}"
        if m in ("device", "off"):
            return tr("look_" + m)
        return tr("zones" if m == "zones" else "average")

    def _look_items(self, current, auto_text):
        """Menu entries for a profile's look; each leaf's value is ("look", the new look or None for auto)."""
        s, cur = self.state, current or {}
        mode = cur.get("mode")

        def radio(text, look, checked, **kw):
            return dict(kind="radio", text=text, value=("look", look), checked=checked, **kw)

        screen = [radio(tr("zones"), {"mode": "zones"}, mode == "zones", icon="monitor"),
                  radio(tr("average"), {"mode": "average"}, mode == "average", icon="palette")]
        colors = [radio(tr("palette_color"), {"mode": "color"}, mode == "color" and "color" not in cur, swatch=s.color),
                  dict(kind="sep")]
        colors += [radio(tr("color_" + name), {"mode": "color", "color": color_hex(c)},
                         mode == "color" and hex_color(cur.get("color")) == c, swatch=c) for name, c in SWATCHES]
        grads = [radio(tr("palette_gradient"), {"mode": "gradient"}, mode == "gradient" and "gradient" not in cur,
                       stops=s.gradient), dict(kind="sep")]
        grads += [radio(tr("gradient_" + name), {"mode": "gradient", "gradient": [color_hex(c) for c in st]},
                        mode == "gradient" and clean_stops(cur.get("gradient")) == st, stops=st) for name, st in GRADIENTS]
        music = [radio(tr("style_" + st), {"mode": "music", "style": st},
                       mode == "music" and cur.get("style", s.music_style) == st, icon=self.STYLE_ICONS[st])
                 for st in MUSIC_STYLES]
        text = self._look_label(current, auto_text)[0] if current else ""
        sub = lambda glyph, title, entries, on: dict(kind="submenu", icon=glyph, text=title, items=entries,
                                                     value=text if on else "")
        return [radio(auto_text, None, current is None, icon="sparkle"), dict(kind="sep"),
                sub("monitor", tr("mode_zones"), screen, mode in SCREEN_MODES),
                sub("drop", tr("mode_color"), colors, mode == "color"),
                sub("gradient", tr("mode_gradient"), grads, mode == "gradient"),
                sub("music", tr("mode_music"), music, mode == "music"), dict(kind="sep"),
                radio(tr("look_device"), {"mode": "device"}, mode == "device", icon="bulb"),
                radio(tr("look_off"), {"mode": "off"}, mode == "off", icon="power")]

    def _profile_summary(self):
        """The Profiles row of the Ambient light page: (text, colour or None)."""
        s = self.state
        parts = ([f"{tr('night_short')} {hhmm(s.night['from'])}–{hhmm(s.night['to'])}"] if s.night["on"] else [])
        if s.rules:
            parts.append(tr("profiles_apps_one") if len(s.rules) == 1 else tr("profiles_apps", n=len(s.rules)))
        if not parts:
            return tr("profiles_none_long"), None
        a = s.active
        if s.enabled and a["source"] != "base":
            return " · ".join(parts) + " · " + tr("profiles_now", name=self._look_name(a["look"])), MenuPainter.LABEL
        return " · ".join(parts), None

    def _profile_now(self):
        """The Profiles page's first card: (glyph, colour, text)."""
        s = self.state
        a = s.active
        look = self._look_name(a["look"])
        if not s.enabled:
            return "info", MenuPainter.MUTED, tr("sync_now_paused")
        if a["source"] == "app":
            return "apps", MenuPainter.GREEN, tr("now_app", rule=self._rule_text(a["rule"]), look=look)
        if a["source"] == "night":
            return "moon", MenuPainter.LABEL, tr("now_night", end=hhmm(s.night["to"]), look=look,
                                                 brightness=a["brightness"])
        if a["source"] == "rest":
            dark = a["look"]["mode"] in ("device", "off")
            return "clock", MenuPainter.AMBER if dark else MenuPainter.GREEN, tr("now_rest", look=look)
        return "check", MenuPainter.GREEN, tr("now_base")

    def _app_icon(self, path):
        if not path:
            return None
        if path not in self.app_icons:
            h, size = HANDLE(), self.px(28)
            try:
                n = user32.PrivateExtractIconsW(path, 0, size, size, byref(h), None, 1, 0)
            except OSError:
                n = 0
            self.app_icons[path] = h.value if n and h.value else None
        return self.app_icons[path]

    def _glows(self, n=28):
        """The LED colours as up to n glows around the screen: (x, y on the screen's border 0..1, colour)."""
        out = []
        for uv, colors in list(self.state.preview or []):
            pts = []
            for (u, v), c in zip(uv, colors):
                e = edge_point(u, v)
                if e is not None:
                    pts.append((math.atan2(e[1] - 0.5, e[0] - 0.5), e, c))
            if not pts:
                continue
            pts.sort(key=lambda t: t[0])
            k = min(n, len(pts))
            for i in range(k):
                grp = pts[i * len(pts) // k:(i + 1) * len(pts) // k]
                m = len(grp)
                ex, ey = sum(g[1][0] for g in grp) / m, sum(g[1][1] for g in grp) / m
                r, g_, b = (int(sum(g[2][j] for g in grp) / m) for j in range(3))
                out.append((ex, ey, (r << 16) | (g_ << 8) | b))
        return out

    # ---- layout of everything
    def compose(self):
        """Display lists for the sidebar and the current page, and the widgets under them."""
        p, (W, H) = self.px, self.size
        self.widgets, self.side, self.content, self.preview_rect = [], ([], []), ([], []), None
        self.sw = p(264)
        room = W - self.sw - p(8) - p(36)  # right of the sidebar
        width = max(p(380), min(room, p(1200)))
        self.cx0 = self.sw + p(8) + max(0, (room - width) // 2)  # a wide or maximized window: the page in the middle
        self.cx1 = self.cx0 + width
        self._sidebar()
        y = getattr(self, "_page_" + self.page)(p(18) - self.scroll)  # the page title centred on the logo beside it
        self._nav("quit", p(14), H - p(18) - p(38), self.sw - p(28), "quit", tr("app_quit"), False, quiet=True)
        self.max_scroll = max(0, y + self.scroll + p(36) - H)
        if self.scroll > self.max_scroll:  # taller window, or a shorter page: show its end
            self.scroll = self.max_scroll
            return self.compose()
        if self.focus_visible:  # keyboard focus ring
            w = next((w for w in self.widgets if w["id"] == self.focus), None)
            if w:
                x0, y0, x1, y1 = w["rect"]
                r = w.get("radius", p(8)) + p(3)
                self.S("outline", 0xFFFFFF, x0 - p(3), y0 - p(3), x1 - x0 + p(6), y1 - y0 + p(6), r, max(1.5, p(2)), 225,
                       side=w["side"])

    def _sidebar(self):
        p, s = self.px, self.state
        x, w = p(14), self.sw - p(28)
        y = p(22)
        self.I(self.icon, x + p(8), y, p(32), side=True)
        self.T("Glowback", self.fonts["name"], MenuPainter.TEXT, x + p(52), y - p(3), x + w, y + p(19), side=True)
        self.T(f"v{__version__}", self.painter.f_small, MenuPainter.MUTED, x + p(52), y + p(18), x + w, y + p(36),
               side=True)
        y += p(58)
        text, color = self._status()
        self.S("round", 0x1A1B21, x + p(2), y, w - p(4), p(34), p(17), side=True)
        self.S("outline", 0x24262E, x + p(2), y, w - p(4), p(34), p(17), max(1.0, self.k), side=True)
        self.S("circle", color, x + p(16), y + p(13), p(8), side=True)
        self.T(text, self.painter.f_small, MenuPainter.ICON, x + p(32), y, x + w - p(10), y + p(34), 0x8000, side=True)
        y += p(52)
        for page, icon, key in self.PAGES:
            self._nav("nav:" + page, x, y, w, icon, tr(key), self.page == page)
            y += p(42)

    def _page_light(self, y):
        p, s = self.px, self.state
        x0, x1 = self.cx0, self.cx1
        y = self._header(y, tr("nav_light"), tr("light_sub"))
        h = p(256)
        self._card(y, h)
        self._preview(x0, y, x1 - x0, h)
        tx = x1 - p(24) - p(42)
        self._toggle("enabled", tx, y + p(24), s.lit())
        label = tr("ambilight")
        lw = self.tw(label, self.fonts["body"])
        self.T(label, self.fonts["body"], MenuPainter.TEXT, tx - p(12) - lw, y + p(24), tx - p(12), y + p(46))
        y += h + p(22)
        y = self._label(y, tr("mode"))
        gap, th = p(10), p(84)
        w = (x1 - x0 - gap * (len(MODES) - 1)) / len(MODES)
        for i, mode in enumerate(MODES):
            self._mode_tile("mode:" + mode, x0 + i * (w + gap), y, w, th, self.MODE_ICONS[mode], tr("mode_" + mode),
                            s.mode == mode)
        y += th + p(12)
        y = {"color": self._opts_color, "gradient": self._opts_gradient, "music": self._opts_music}.get(
            s.mode, self._opts_screen)(y)
        y += p(28)
        y = self._label(y, tr("brightness"))
        h = p(64)
        self._card(y, h)
        self.T(MenuPainter.ICONS["sun"], self.fonts["icon"], MenuPainter.ICON, x0 + p(20), y, x0 + p(44), y + h, 0x1)
        self._slider("brightness", x0 + p(66), x1 - p(88), y + h / 2, s.brightness)
        self.T(f"{round(s.brightness)} %", self.fonts["body"], MenuPainter.TEXT, x1 - p(76), y, x1 - p(20), y + h, 0x2)
        y += h + p(12)
        h = p(64)
        self._card(y, h)
        self._row_hover("goto:profiles", y, h)
        text, color = self._profile_summary()
        self._row_text(y, h, "layers", tr("nav_profiles"), text, right=x1 - p(60), desc_color=color)
        self.T(MenuPainter.ICONS["chev_right"], self.fonts["icon_s"], MenuPainter.MUTED, x1 - p(44), y, x1 - p(20),
               y + h, 0x1)
        self.add("goto:profiles", "row", (x0, y, x1, y + h), radius=p(10))
        return y + h

    def _card_behind(self, at, y, h):
        """A card under what was drawn since display list index `at` (its height known only afterwards)."""
        p, x0, x1 = self.px, self.cx0, self.cx1
        self.content[0][at:at] = [("round", self.CARD, x0, y, x1 - x0, h, p(10)),
                                  ("outline", self.LINE, x0, y, x1 - x0, h, p(10), max(1.0, self.k))]

    def _opts_screen(self, y):
        p, x0, x1 = self.px, self.cx0, self.cx1
        text = tr("mode_zones_desc" if self.state.mode == "zones" else "mode_average_desc")
        th = self.wrap_h(text, self.fonts["body"], x1 - x0 - p(82))
        h = max(p(56), th + p(30))
        self._card(y, h)
        self.T(MenuPainter.ICONS["info"], self.fonts["icon"], MenuPainter.ICON, x0 + p(20), y, x0 + p(44), y + h, 0x1)
        self.W(text, self.fonts["body"], MenuPainter.ICON, x0 + p(62), y + (h - th) / 2, x1 - p(20), y + (h + th) / 2)
        return y + h

    def _hsv(self, color):
        """Hue and saturation of the color being edited (a white keeps the hue it had)."""
        h, sat, _ = color_hsv(color)
        if self.hue_memo and self.hue_memo[0] == color:
            h = self.hue_memo[1]
        return h, sat

    def _color_rows(self, y, color, pad):
        """Swatches, then hue and saturation, for the color being edited; returns the bottom."""
        p, x0, x1 = self.px, self.cx0, self.cx1
        d = p(28)
        n = len(SWATCHES)
        gap = min(p(14), max(p(6), (x1 - x0 - 2 * pad - n * d) / (n - 1)))
        for i, (name, c) in enumerate(SWATCHES):
            self._swatch("swatch:" + name, x0 + pad + i * (d + gap), y, d, c, c == color)
        y += d + p(22)
        h, sat = self._hsv(color)
        lw = max(self.tw(tr("color_hue"), self.fonts["body"]), self.tw(tr("color_sat"), self.fonts["body"])) + p(20)
        for wid, label, value, track, knob in (
                ("hue", tr("color_hue"), h / 3.6, [hsv_color(a * 60, 1) for a in range(7)], hsv_color(h, 1)),
                ("sat", tr("color_sat"), sat * 100, [0xFFFFFF, hsv_color(h, 1)], color)):
            self.T(label, self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x0 + pad + lw, y + p(28), 0x8000)
            self._slider(wid, x0 + pad + lw + p(12), x1 - pad - p(12), y + p(14), value, track=track, knob=knob)
            y += p(42)
        return y - p(14)

    def _opts_color(self, y):
        p = self.px
        pad, at, top = p(20), len(self.content[0]), y
        y = self._color_rows(y + pad, self.state.color, pad) + pad
        self._card_behind(at, top, y - top)
        return y

    def _opts_gradient(self, y):
        p, s, x0, x1 = self.px, self.state, self.cx0, self.cx1
        pad, at, top = p(20), len(self.content[0]), y
        stops = s.gradient
        self.stop_sel = min(self.stop_sel, len(stops) - 1)
        y += pad
        bs, bh = p(36), p(36)
        bx = x1 - pad - bs
        self._icon_button("stop:del", bx, y, bs, "minus", enabled=len(stops) > 2)
        self._icon_button("stop:add", bx - p(8) - bs, y, bs, "add", enabled=len(stops) < 4)
        gx0, gx1 = x0 + pad, bx - p(8) - bs - p(16)
        self.S("hgrad", list(stops), gx0, y, gx1 - gx0, bh, p(9))
        d = p(22)
        for i, c in enumerate(stops):
            cx = gx0 + p(18) + (gx1 - gx0 - p(36)) * i / (len(stops) - 1)
            on, wid = i == self.stop_sel, f"stop:{i}"
            ring = p(4) if on else (p(3) if self.hover == wid else p(2))
            self.S("circle", 0xFFFFFF if on or self.hover == wid else 0x15161A, cx - d / 2, y + (bh - d) / 2, d)
            self.S("circle", c, cx - d / 2 + ring, y + (bh - d) / 2 + ring, d - 2 * ring)
            self.add(wid, "swatch", (cx - d / 2 - p(4), y, cx + d / 2 + p(4), y + bh), radius=d / 2 + p(4))
        y += bh + p(22)
        y = self._color_rows(y, stops[self.stop_sel], pad) + p(20)
        self._sep(y)
        y += p(18)
        label = tr("gradient_presets")
        self.T(label, self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x1, y + p(28), 0x8000)
        ph, gap, n = p(28), p(12), len(GRADIENTS)
        px_ = x0 + pad + self.tw(label, self.fonts["body"]) + p(24)
        pw = max(p(34), min(p(56), (x1 - pad - p(4) - px_ - gap * (n - 1)) / n))  # all of them, narrower if need be
        for name, st in GRADIENTS:
            if px_ + pw > x1 - pad:
                break
            self._swatch("preset:" + name, px_, y, ph, selected=st == tuple(stops), stops=st, w=pw)
            px_ += pw + gap
        y += ph + p(18)
        self._sep(y)
        rh = p(64)
        tx = x1 - p(20) - p(42)
        self._toggle("flow", tx, y + (rh - p(22)) / 2, s.flow, row=(x0, y, x1, y + rh))
        self._row_text(y, rh, "flow", tr("gradient_flow"), tr("gradient_flow_desc"), right=tx - p(16))
        y += rh
        self._card_behind(at, top, y - top)
        return y

    def _opts_music(self, y):
        p, s, ic, x0, x1 = self.px, self.state, MenuPainter.ICONS, self.cx0, self.cx1
        pad, at, top = p(20), len(self.content[0]), y
        silent = s.sound == "silent" and s.enabled and not s.waiting
        glyph, color = ("volume", MenuPainter.AMBER) if silent else ("music", MenuPainter.LABEL)
        text = tr("music_silent" if silent else "music_on")
        th = self.wrap_h(text, self.fonts["body"], x1 - pad - x0 - p(62))
        rh = max(p(60), th + p(30))
        self.T(ic[glyph], self.fonts["icon"], color, x0 + p(20), y, x0 + p(44), y + rh, 0x1)
        self.W(text, self.fonts["body"], MenuPainter.TEXT, x0 + p(62), y + (rh - th) / 2, x1 - pad, y + (rh + th) / 2)
        y += rh
        self._sep(y)
        lw = max(self.tw(tr(k), self.fonts["body"]) for k in ("music_style", "music_colors", "music_sensitivity")) + p(24)
        cx = x0 + pad + lw
        y += p(16)
        self.T(tr("music_style"), self.fonts["body"], MenuPainter.ICON, x0 + pad, y, cx, y + p(40), 0x8000)
        self._segmented("style", cx, x1 - pad, y, [(st, self.STYLE_ICONS[st], tr("style_" + st)) for st in MUSIC_STYLES],
                        s.music_style)
        y += p(40) + p(8)
        desc = tr(f"style_{s.music_style}_desc")
        dh = self.wrap_h(desc, self.painter.f_small, x1 - pad - cx)
        self.W(desc, self.painter.f_small, MenuPainter.MUTED, cx + p(2), y, x1 - pad, y + dh)
        y += dh + p(16)
        pal = s.music_palette
        kw = {"rainbow": dict(stops=[hsv_color(a * 60, 1) for a in range(6)]), "screen": dict(glyph="monitor"),
              "color": dict(swatch=s.color), "gradient": dict(stops=s.gradient)}[pal]
        self.T(tr("music_colors"), self.fonts["body"], MenuPainter.ICON, x0 + pad, y, cx, y + p(36), 0x8000)
        self._picker("pick:palette", cx, y, min(p(300), x1 - pad - cx), tr("palette_" + pal), **kw)
        y += p(36) + p(18)
        self.T(tr("music_sensitivity"), self.fonts["body"], MenuPainter.ICON, x0 + pad, y, cx, y + p(28), 0x8000)
        self._slider("sens", cx + p(12), x1 - pad - p(12), y + p(14), s.sensitivity)
        y += p(28) + pad
        self._card_behind(at, top, y - top)
        return y

    def _preview(self, x, y, w, h):
        """The screen with its picture, its stand, and the light the LEDs throw on the wall, live."""
        p, s = self.px, self.state
        s.thumb_want = time.monotonic()  # the capture loop sends the screen's picture while this shows
        self.preview_rect = (int(max(x, self.sw)), int(max(0, y)), int(x + w) + 1, int(min(self.size[1], y + h)) + 1)
        live = s.enabled and not s.waiting
        glows = self._glows() if live else []
        self.S("clip", x + 1, y + 1, w - 2, h - 2, p(10))
        mh = min((h / 2 - p(12)) / 0.93, w * 0.40 * 9 / 16)  # the halo (0.43 of the height) stays in the card
        mw = mh * 16 / 9
        mx, my = x + (w - mw) / 2, y + (h - mh) / 2 - p(8)
        layer = []
        for ex, ey, color in glows:
            r_, g_, b_ = rgb(color)
            v = max(r_, g_, b_)
            if v < 6:
                continue  # a dark LED throws no light (and no shadow)
            k = 255.0 / v
            pure = (min(255, round(r_ * k)) << 16) | (min(255, round(g_ * k)) << 8) | min(255, round(b_ * k))
            dx, dy = ex - 0.5, ey - 0.5
            n = max(abs(dx), abs(dy)) or 1.0
            layer.append((pure, mx + ex * mw + dx / n * mw * 0.07, my + ey * mh + dy / n * mh * 0.09,
                          mw * 0.24, mh * 0.34, 200 * (v / 255.0) ** 0.75))
        if not live:
            idle = 0x4B3F86 if s.enabled else 0x34363F
            for ex, ey in ((0.5, 0.0), (0.5, 1.0), (0.0, 0.5), (1.0, 0.5)):
                layer.append((idle, mx + ex * mw, my + ey * mh, mw * 0.42, mh * 0.42, 60))
        self.S("glows", layer, x, y, x + w, y + h)
        nw, nh = mw * 0.08, mh * 0.2
        self.S("round", 0x1C1E25, mx + mw / 2 - nw / 2, my + mh, nw, nh, p(2))
        bw, bh = mw * 0.34, max(p(6), mh * 0.05)
        self.S("round", 0x262830, mx + mw / 2 - bw / 2, my + mh + nh - p(2), bw, bh, bh / 2)
        bez = max(p(3), mw * 0.012)
        self.S("round", 0x2B2D35, mx - bez, my - bez, mw + 2 * bez, mh + 2 * bez, p(6))
        self.S("round", 0x08090B, mx, my, mw, mh, p(4))
        thumb = s.thumb
        if thumb:
            self.S("image", thumb, mx, my, mw, mh, p(4))
        mode = s.active["look"]["mode"]
        glyph = ("pause" if not s.enabled else "bulb" if mode == "device" else "power" if mode == "off"
                 else None if s.leds else "search")
        if glyph:  # a quiet sign of why the screen throws no light
            if thumb:
                self.S("round", 0x000000, mx, my, mw, mh, p(4), 150)
                d = p(52)
                self.S("circle", 0x000000, mx + (mw - d) / 2, my + (mh - d) / 2, d, 140)
            self.T(MenuPainter.ICONS[glyph], self.fonts["icon_l"], 0x8A8FA0 if thumb else 0x4A4E5C, mx, my, mx + mw,
                   my + mh, 0x1)
        self.S("unclip")
        text, color = self._status()
        d = p(9)
        self.S("circle", color, x + p(24), y + p(34) - d / 2, d)  # centred on the text beside it
        self.T(text, self.fonts["h2"], MenuPainter.TEXT, x + p(42), y + p(22), x + w / 2, y + p(46), 0x8000)
        if s.screens and s.leds:
            self.T(" · ".join(s.screens), self.painter.f_small, MenuPainter.MUTED, x + p(42), y + p(46), x + w / 2,
                   y + p(64), 0x8000)

    def _page_profiles(self, y):
        p, s, ic = self.px, self.state, MenuPainter.ICONS
        x0, x1 = self.cx0, self.cx1
        y = self._header(y, tr("nav_profiles"), tr("profiles_sub"))
        glyph, color, text = self._profile_now()
        th = self.wrap_h(text, self.fonts["body"], x1 - x0 - p(82))
        h = max(p(56), th + p(30))
        self._card(y, h)
        self.T(ic[glyph], self.fonts["icon"], color, x0 + p(20), y, x0 + p(44), y + h, 0x1)
        self.W(text, self.fonts["body"], MenuPainter.TEXT, x0 + p(62), y + (h - th) / 2, x1 - p(20), y + (h + th) / 2)
        y += h + p(28)

        # day and night
        y = self._label(y, tr("night_title"))
        n, rh = s.night, p(68)
        rows = 4 if n["on"] else 1
        self._card(y, rh * rows)
        tx = x1 - p(20) - p(42)
        self._toggle("night", tx, y + (rh - p(22)) / 2, n["on"], row=(x0, y, x1, y + rh))
        self._row_text(y, rh, "moon", tr("night_profile"), tr("night_desc", start=hhmm(n["from"]), end=hhmm(n["to"])),
                       right=tx - p(16))
        if n["on"]:
            ry = y + rh
            self._sep(ry)
            sy = ry + (rh - p(36)) / 2
            left = self._stepper("night_to", x1 - p(20), sy, hhmm(n["to"]))
            self.T(ic["arrow"], self.fonts["icon_s"], MenuPainter.MUTED, left - p(34), ry, left - p(8), ry + rh, 0x1)
            left = self._stepper("night_from", left - p(42), sy, hhmm(n["from"]))
            self._row_text(ry, rh, "clock", tr("night_hours"), None, right=left - p(12))
            ry += rh
            self._sep(ry)
            sx = x0 + p(62) + max(p(150), self.tw(tr("night_brightness"), self.fonts["body"]) + p(28))
            self._row_text(ry, rh, "sun", tr("night_brightness"), None, right=sx - p(12))
            self._slider("night_bright", sx, x1 - p(88), ry + rh / 2, n["brightness"])
            self.T(f"{n['brightness']} %", self.fonts["body"], MenuPainter.TEXT, x1 - p(76), ry, x1 - p(20), ry + rh, 0x2)
            ry += rh
            self._sep(ry)
            text, kw = self._look_label(n["look"], tr("night_same"))
            pw = min(p(280), (x1 - x0) * 0.45)
            self._picker("pick:night_look", x1 - p(20) - pw, ry + (rh - p(36)) / 2, pw, text, **kw)
            self._row_text(ry, rh, "palette", tr("night_look"), None, right=x1 - p(36) - pw)
        y += rh * rows + p(28)

        # by app
        y = self._label(y, tr("apps_title"))
        if s.rules:
            rh = p(64)
            self._card(y, rh * len(s.rules))
            narrow = x1 - x0 < p(700)  # Remove becomes an icon: room for the look
            for i, r in enumerate(s.rules):
                ry = y + i * rh
                if i:
                    self._sep(ry)
                if narrow:
                    bx = x1 - p(16) - p(34)
                    self._icon_button(f"remove:{i}", bx, ry + (rh - p(34)) / 2, p(34), "delete")
                else:
                    bx = self._button(f"remove:{i}", x1 - p(14), ry + (rh - p(32)) / 2, tr("sync_remove"), "quiet",
                                      icon="delete", h=p(32))
                text, kw = self._look_label(r.get("look"), tr("look_auto_short"))
                pw = min(p(230), (x1 - x0) * (0.38 if narrow else 0.3))
                self._picker(f"pick:look:{i}", bx - p(8) - pw, ry + (rh - p(36)) / 2, pw, text, **kw)
                hicon = self._app_icon(r.get("path"))
                self._row_text(ry, rh, None if hicon else ("apps" if r["app"] else "filter"), self._app_name(r),
                               self._rule_desc(r), right=bx - p(20) - pw, hicon=hicon)
            y += rh * len(s.rules) + p(12)
            rh = p(68)
            self._card(y, rh)
            text, kw = self._look_label(None if s.otherwise == "auto" else {"mode": s.otherwise}, tr("look_auto_short"))
            pw = min(p(260), (x1 - x0) * 0.4)
            self._picker("pick:rest", x1 - p(20) - pw, y + (rh - p(36)) / 2, pw, text, **kw)
            self._row_text(y, rh, "clock", tr("rest_title"), tr("rest_desc"), right=x1 - p(36) - pw)
            y += rh
        else:
            h = p(56)
            self._card(y, h)
            self.T(tr("apps_empty"), self.fonts["body"], MenuPainter.MUTED, x0 + p(20), y, x1 - p(20), y + h, 0x8000)
            y += h
        y += p(28)

        # add an app
        y = self._label(y, tr("apps_add"))
        pad, gap = p(20), p(14)
        d = self.draft
        half = (x1 - x0 - 2 * pad - gap) / 2
        help_text = tr("apps_examples")
        bw = self.tw(tr("sync_add"), self.fonts["button"]) + p(54)
        help_h = self.wrap_h(help_text, self.painter.f_small, x1 - x0 - 2 * pad - bw - p(24))
        ch = pad + 2 * (p(22) + p(36)) + p(16) + p(18) + max(p(34), help_h) + pad
        self._card(y, ch)
        playing = d["when"] == "playing"
        look_text, look_kw = self._look_label(d["look"], tr("look_auto_short"))
        fields = (("sync_app", "pick:app", x0 + pad, y + pad),
                  ("sync_when_label", "pick:when", x0 + pad + half + gap, y + pad),
                  ("sync_screen", "pick:screen", x0 + pad, y + pad + p(58) + p(16)),
                  ("look_label", "pick:draft_look", x0 + pad + half + gap, y + pad + p(58) + p(16)))
        for key, wid, xx, yy in fields:
            self.T(tr(key).upper(), self.painter.f_label, MenuPainter.MUTED, xx + p(2), yy, xx + half, yy + p(16))
            if wid == "pick:app":
                hicon = self._app_icon(d["path"])
                text = d["name"] or (d["app"][:-4] if d["app"] else tr("sync_any_app"))
                self._picker(wid, xx, yy + p(22), half, text, hicon=hicon, glyph=None if hicon else "apps")
            elif wid == "pick:when":
                self._picker(wid, xx, yy + p(22), half, tr("sync_" + d["when"]), glyph="volume" if playing else "filter")
            elif wid == "pick:screen":
                self._picker(wid, xx, yy + p(22), half, self._screen_text("" if playing else d["screen"]),
                             glyph="monitor", disabled=playing)
            else:
                self._picker(wid, xx, yy + p(22), half, look_text, **look_kw)
        by = y + pad + 2 * (p(22) + p(36)) + p(16) + p(18)
        self._button("add", x1 - pad, by, tr("sync_add"), "primary", icon="add")
        self.W(help_text, self.painter.f_small, MenuPainter.MUTED, x0 + pad, by, x1 - pad - bw - p(24), by + help_h)
        return y + ch

    def _page_home(self, y):
        p, ic = self.px, MenuPainter.ICONS
        x0, x1 = self.cx0, self.cx1
        ha, cfg = getattr(self.tray, "ha", None), ha_settings()
        y = self._header(y, "Home Assistant", tr("home_sub"))
        status = ha.status if ha else "off"
        if cfg and status == "connected":
            title, desc, color = tr("home_connected", host=cfg["host"]), tr("home_connected_desc"), MenuPainter.GREEN
        elif cfg and status == "connecting":
            title, desc, color = tr("ha_connecting"), cfg["host"], MenuPainter.MUTED
        elif cfg:
            title, desc, color = tr("ha_error"), (ha.error if ha and ha.error else cfg["host"]), MenuPainter.AMBER
        else:
            title, desc, color = tr("home_not_set"), tr("home_not_set_desc"), MenuPainter.MUTED
        h = p(84)
        self._card(y, h)
        ty = y + (h - p(44)) / 2
        self.S("round", 0x2A2448, x0 + p(20), ty, p(44), p(44), p(11))
        self.T(ic["home"], self.fonts["icon_l"], MenuPainter.LABEL, x0 + p(20), ty, x0 + p(64), ty + p(44), 0x1)
        by = y + (h - p(34)) / 2
        if cfg:
            bx = self._button("ha:disconnect", x1 - p(20), by, tr("ha_disconnect"), "quiet")
            bx = self._button("ha:setup", bx - p(8), by, tr("home_change"), "secondary")
        else:
            bx = self._button("ha:setup", x1 - p(20), by, tr("home_setup"), "primary")
        tx = x0 + p(80)
        self.S("circle", color, tx, y + p(30) - p(4), p(8))  # centred on the title beside it
        self.T(title, self.fonts["h2"], MenuPainter.TEXT, tx + p(16), y + p(18), bx - p(16), y + p(42), 0x8000)
        self.T(desc, self.painter.f_small, MenuPainter.MUTED, tx, y + p(44), bx - p(16), y + p(66), 0x8000)
        y += h + p(28)
        y = self._label(y, tr("home_entities"))
        rows = (("light", tr("ambilight"), tr("home_light"), "light.glowback"),
                ("monitor", tr("home_leds_title"), tr("home_leds"), "sensor.glowback_leds"),
                ("sync", tr("home_update_title"), tr("home_update"), "update.glowback"))
        rh = p(64)
        self._card(y, rh * len(rows))
        f = self.painter.f_small
        for i, (icon, title, text, entity) in enumerate(rows):
            ry = y + i * rh
            if i:
                self._sep(ry)
            right = x1 - p(20)
            tag = self.tw(entity, f) + p(20)
            if x1 - x0 > p(560):  # its ID, for automations: small, on the right
                th = p(26)
                self.S("round", self.FIELD, right - tag, ry + (rh - th) / 2, tag, th, p(6))
                self.S("outline", self.FIELD_LINE, right - tag, ry + (rh - th) / 2, tag, th, p(6), max(1.0, self.k))
                self.T(entity, f, MenuPainter.MUTED, right - tag, ry, right, ry + rh, 0x1)
                right -= tag + p(16)
            self._row_text(ry, rh, icon, title, text, right=right)
        y += rh * len(rows) + p(28)
        y = self._label(y, tr("home_voice"))
        guide = tr("ha_guide")
        bw = self.tw(guide, self.fonts["button"]) + p(54)
        text = tr("home_voice_text")
        th = self.wrap_h(text, self.fonts["body"], x1 - x0 - p(62) - bw - p(40))
        h = max(p(76), th + p(36))
        self._card(y, h)
        bx = self._button("link:guide", x1 - p(20), y + (h - p(34)) / 2, guide, "secondary", icon="link")
        self.T(ic["mic"], self.fonts["icon"], MenuPainter.ICON, x0 + p(20), y, x0 + p(44), y + h, 0x1)
        self.W(text, self.fonts["body"], MenuPainter.TEXT, x0 + p(62), y + (h - th) / 2, bx - p(20), y + (h + th) / 2)
        return y + h

    def _text_card(self, y, icon, text, button=None):
        """A card of wrapped text with an icon, and maybe a button (wid, label, style) on the right."""
        p, x0, x1 = self.px, self.cx0, self.cx1
        bw = self.tw(button[1], self.fonts["button"]) + p(54) if button else 0
        th = self.wrap_h(text, self.fonts["body"], x1 - x0 - p(62) - bw - p(40))
        h = max(p(76), th + p(36))
        self._card(y, h)
        right = x1 - p(20)
        if button:
            right = self._button(button[0], right, y + (h - p(34)) / 2, button[1], button[2]) - p(20)
        self.T(MenuPainter.ICONS[icon], self.fonts["icon"], MenuPainter.ICON, x0 + p(20), y, x0 + p(44), y + h, 0x1)
        self.W(text, self.fonts["body"], MenuPainter.TEXT, x0 + p(62), y + (h - th) / 2, right, y + (h + th) / 2)
        return y + h

    def _page_matter(self, y):
        p, x0, x1 = self.px, self.cx0, self.cx1
        node, on = self.tray.matter, bool(matter_settings().get("on"))
        info = node.pairing() if node else None
        y = self._header(y, tr("matter_title"), tr("matter_sub"))
        rh = p(68)
        self._card(y, rh)
        tx = x1 - p(20) - p(42)
        self._toggle("matter:on", tx, y + (rh - p(22)) / 2, on, row=(x0, y, x1, y + rh))
        if not on:
            desc, color = tr("matter_off_desc"), None
        elif not node:
            desc, color = tr("matter_failed"), MenuPainter.AMBER
        elif info["fabrics"]:
            desc, color = tr("matter_on_count", n=len(info["fabrics"])), MenuPainter.GREEN
        else:
            desc, color = tr("matter_on_none"), MenuPainter.GREEN
        self._row_text(y, rh, "phone", tr("matter_toggle"), desc, right=tx - p(16), desc_color=color)
        y += rh + p(28)
        if node:
            y = self._label(y, tr("matter_pair"))
            left = max(0, round((info["until"] - time.monotonic()) / 60 + 0.49)) if info["open"] else 0
            if info["open"] and not info["enhanced"]:
                y = self._matter_qr(y, info, left) + p(28)
            elif info["open"]:  # another app (Apple Home's "Turn On Pairing Mode"...) adds one more
                y = self._text_card(y, "phone", tr("matter_other_app", min=left),
                                    ("matter:stop", tr("matter_stop"), "secondary")) + p(28)
            else:
                y = self._text_card(y, "qr", tr("matter_closed_desc"),
                                    ("matter:pair", tr("matter_open"), "primary")) + p(28)
            y = self._label(y, tr("matter_paired"))
            fabrics = info["fabrics"]
            if not fabrics:
                y = self._text_card(y, "phone", tr("matter_none")) + p(28)
            else:
                self._card(y, rh * len(fabrics))
                for i, f in enumerate(fabrics):
                    ry = y + i * rh
                    if i:
                        self._sep(ry)
                    bx = self._button(f"matter:remove:{f['index']}", x1 - p(20), ry + (rh - p(34)) / 2,
                                      tr("matter_remove"), "quiet")
                    name = matter_app_name(f)
                    desc = f["label"] if f["label"] and f["label"] != name else tr("matter_paired_desc")  # its home
                    self._row_text(ry, rh, "home", name, desc, right=bx - p(16))
                y += rh * len(fabrics) + p(28)
        y = self._label(y, tr("matter_good_to_know"))
        return self._text_card(y, "info", tr("matter_notes"), ("link:matter", tr("ha_guide"), "secondary"))

    def _matter_qr(self, y, info, minutes):
        """The pairing card: the QR code to scan, the code to type, the time left."""
        p, x0, x1 = self.px, self.cx0, self.cx1
        cached = getattr(self, "_qr", None)
        if not cached or cached[0] != info["qr"]:
            cached = self._qr = (info["qr"], qr_matrix(info["qr"]))
        m = cached[1]
        mod, quiet = max(4, round(6 * self.k)), 3  # whole pixels: sharp modules a phone reads at a glance
        size = (len(m) + 2 * quiet) * mod
        tx = round(x0 + p(24)) + size + p(32)
        text = tr("matter_scan")
        th = self.wrap_h(text, self.fonts["body"], x1 - p(20) - tx)
        h = max(size + p(48), p(30) + p(32) + th + p(14) + p(40) + p(16) + p(34) + p(24))
        self._card(y, h)
        qx, qy = round(x0 + p(24)), round(y + p(24))
        self.S("round", 0xFFFFFF, qx, qy, size, size, p(8))
        for r, row in enumerate(m):
            start = None
            for c, dark in enumerate(list(row) + [False]):  # dark runs of each row: few shapes
                if dark and start is None:
                    start = c
                elif not dark and start is not None:
                    self.S("round", 0x000000, qx + (quiet + start) * mod, qy + (quiet + r) * mod, (c - start) * mod,
                           mod, 0)
                    start = None
        ty = y + p(30)
        self.T(tr("matter_scan_title"), self.fonts["h2"], MenuPainter.TEXT, tx, ty, x1 - p(20), ty + p(24), 0x8000)
        ty += p(32)
        self.W(text, self.fonts["body"], MenuPainter.MUTED, tx, ty, x1 - p(20), ty + th)
        ty += th + p(14)
        c = info["code"]
        self.T(f"{c[:4]}-{c[4:7]}-{c[7:]}", self.fonts["hero"], MenuPainter.TEXT, tx, ty, x1 - p(20), ty + p(40),
               0x8000)
        by = y + h - p(24) - p(34)
        self._button("matter:stop", x1 - p(20), by, tr("matter_stop"), "quiet")
        self.T(tr("matter_open_for", min=minutes), self.painter.f_small, MenuPainter.GREEN, tx, by, x1 - p(140),
               by + p(34), 0x8000)
        return y + h

    def _page_settings(self, y):
        p, s, t = self.px, self.state, self.tray
        x0, x1 = self.cx0, self.cx1
        y = self._header(y, tr("nav_settings"), tr("settings_sub_store" if PACKAGE else "settings_sub"))
        rh = p(68)
        self._card(y, rh)
        tx = x1 - p(20) - p(42)
        if PACKAGE:  # the Store version: Windows starts it (Settings > Apps > Startup), the Store updates it
            bx = self._button("autostart", x1 - p(20), y + (rh - p(34)) / 2, tr("settings_open"), "secondary")
            self._row_text(y, rh, "power", tr("start_windows"), tr("startup_store_desc"), right=bx - p(16))
            y += rh + p(28)
        else:
            self._toggle("autostart", tx, y + (rh - p(22)) / 2, t.autostart, row=(x0, y, x1, y + rh))
            self._row_text(y, rh, "power", tr("start_windows"), tr("settings_start_desc"), right=tx - p(16))
            y += rh + p(28)
            y = self._label(y, tr("settings_updates"))
            rows = 2
            self._card(y, rh * rows)
            ry = y
            if s.new_version:  # the check button becomes the one that downloads and installs it
                bx = self._button("update", x1 - p(20), ry + (rh - p(34)) / 2, tr("update_to", version=s.new_version),
                                  "primary", icon="sync", busy=getattr(t, "updating", False))
                self._row_text(ry, rh, "sync", tr("settings_new", version=s.new_version), f"Glowback {__version__}",
                               right=bx - p(16), icon_color=MenuPainter.ACCENT)
            else:
                result = t._check_status()
                bx = self._button("check", x1 - p(20), ry + (rh - p(34)) / 2, tr("settings_check_now"), "secondary",
                                  busy=t.checking)
                self._row_text(ry, rh, "sync", tr("updates"), result[0] if result else f"Glowback {__version__}",
                               right=bx - p(16), desc_color=result[1] if result else None)
            ry += rh
            self._sep(ry)
            self._toggle("auto_check", tx, ry + (rh - p(22)) / 2, s.check_updates, row=(x0, ry, x1, ry + rh))
            self._row_text(ry, rh, "clock", tr("auto_check"), tr("settings_check_desc"), right=tx - p(16))
            y += rh * rows + p(28)
        y = self._label(y, tr("settings_lang"))
        self._card(y, rh)
        pw = p(230)
        code = load_settings().get("lang") or ""
        name = next((n for c, n in self.LANG_NAMES if c == code), None) or tr("lang_auto")
        self._picker("pick:lang", x1 - p(20) - pw, y + (rh - p(36)) / 2, pw, name, glyph="lang")
        self._row_text(y, rh, "lang", tr("settings_lang_label"), None, right=x1 - p(36) - pw)
        y += rh + p(28)
        y = self._label(y, tr("settings_help"))
        self._card(y, rh)
        bx = self._button("open:log", x1 - p(20), y + (rh - p(34)) / 2, tr("settings_open"), "secondary")
        self._row_text(y, rh, "doc", tr("open_log"), tr("settings_log_desc"), right=bx - p(16))
        return y + rh

    def _page_about(self, y):
        p, ic = self.px, MenuPainter.ICONS
        x0, x1 = self.cx0, self.cx1
        y += p(6)
        self.I(self.icon_big, x0, y, p(72))
        self.T("Glowback", self.fonts["hero"], MenuPainter.TEXT, x0 + p(92), y + p(4), x1, y + p(44))
        self.T(tr("about_version", version=__version__), self.painter.f_small, MenuPainter.MUTED, x0 + p(92),
               y + p(44), x1, y + p(64))
        y += p(72) + p(20)
        th = self.wrap_h(tr("about_tagline"), self.fonts["body"], x1 - x0)
        self.W(tr("about_tagline"), self.fonts["body"], MenuPainter.ICON, x0, y, x1, y + th)
        y += th + p(24)
        rows = (("link:star", "star", tr("star"), True), ("link:site", "globe", tr("about_site"), False),
                ("link:repo", "code", tr("about_source"), False), ("link:issues", "bug", tr("about_issue"), False),
                ("link:author", "person", tr("made_by", author=AUTHOR), False))
        rh = p(56)
        self._card(y, rh * len(rows))
        for i, (wid, icon, text, accent) in enumerate(rows):
            ry = y + i * rh
            if i:
                self._sep(ry)
            self._row_hover(wid, ry, rh)
            self._row_text(ry, rh, icon, text, None, right=x1 - p(52), icon_color=MenuPainter.ACCENT if accent else None)
            self.T(ic["link"], self.fonts["icon_s"], MenuPainter.MUTED, x1 - p(44), ry, x1 - p(20), ry + rh, 0x1)
            self.add(wid, "row", (x0, ry, x1, ry + rh), radius=p(10))
        y += rh * len(rows) + p(18)
        self.T(tr("about_license"), self.painter.f_small, MenuPainter.MUTED, x0 + p(4), y, x1, y + p(20))
        return y + p(20)

    # ---- painting
    def draw(self, hdc, W, H, clip=None):
        """Composes and paints into hdc, W x H pixels (double-buffered; the page scrolls under the sidebar, clipped
        by painting it into its own buffer). clip (l, t, r, b): only that part changed (the live preview)."""
        self.size = (W, H)
        self.compose()
        if not self.bufs or self.bufs[0] != (W, H):  # kept from one paint to the next
            self._free_bufs()
            bufs = []
            for _ in range(2):
                mem = gdi32.CreateCompatibleDC(hdc)
                bmp = gdi32.CreateCompatibleBitmap(hdc, W, H)
                bufs.append((mem, bmp, gdi32.SelectObject(mem, bmp)))
            self.bufs, clip = ((W, H), bufs), None
        (side, _, _), (page, _, _) = self.bufs[1]
        l, t, r, b = clip or (0, 0, W, H)
        brush = gdi32.CreateSolidBrush(_cref(self.BG))
        for mem in (side, page):
            user32.FillRect(mem, byref(wt.RECT(l, t, r, b)), brush)
        gdi32.DeleteObject(brush)
        self._render(page, *self.content, clip=clip)
        x0 = max(l, self.sw)
        if r > x0:
            gdi32.BitBlt(side, x0, t, r - x0, b - t, page, x0, t, 0x00CC0020)
        self._render(side, *self.side, clip=clip)
        gdi32.BitBlt(hdc, l, t, r - l, b - t, side, l, t, 0x00CC0020)

    def _free_bufs(self):
        for mem, bmp, old in self.bufs[1] if self.bufs else ():
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
        self.bufs = None

    def _render(self, hdc, shapes, texts, clip=None):
        gfx = Gfx(hdc, clip)
        for shape in shapes:
            gfx.draw(shape)
        gfx.close()
        if clip:
            gdi32.IntersectClipRect(hdc, *clip)
        self._texts(hdc, texts)
        if clip:
            gdi32.SelectClipRgn(hdc, None)

    def _texts(self, hdc, texts):
        gdi32.SetBkMode(hdc, 1)
        for item in texts:
            if item[0] == "text":
                _, text, font, color, l, t, r, b, flags = item
                self.painter._text(hdc, text, font, color, l, t, r, b, flags)
            elif item[0] == "wrap":
                _, text, font, color, l, t, r, b = item
                gdi32.SelectObject(hdc, font)
                gdi32.SetTextColor(hdc, _cref(color))
                rc = wt.RECT(int(l), int(t), int(r), int(b))
                user32.DrawTextW(hdc, text, -1, byref(rc), 0x10 | 0x800)  # WORDBREAK | NOPREFIX
            elif item[0] == "icon" and item[1]:
                _, hicon, x, y, size = item
                user32.DrawIconEx(hdc, int(x), int(y), hicon, int(size), int(size), 0, None, 3)

    # ---- actions
    def _widget(self, wid):
        return next((w for w in self.widgets if w["id"] == wid), None)

    def _hit(self, x, y):
        for w in self.widgets:
            x0, y0, x1, y1 = w["rect"]
            if (w["side"] or x >= self.sw) and x0 <= x < x1 and y0 <= y < y1:
                return w
        return None

    def activate(self, wid):
        s, t = self.state, self.tray
        if wid.startswith("nav:") or wid == "goto:profiles":
            self.page, self.scroll = wid.split(":")[1], 0
            if self.page == "settings":
                t.autostart = autostart_enabled()
            self._timers()
        elif wid == "enabled":
            s.switch()
            t.refresh()
        elif wid.startswith("mode:"):
            s.update(mode=wid[5:])
        elif wid.startswith("swatch:"):
            self._set_color(dict(SWATCHES)[wid[7:]])
        elif wid.startswith("stop:"):
            stops, i = list(s.gradient), self.stop_sel
            if wid == "stop:add" and len(stops) < 4:
                j = min(i + 1, len(stops) - 1)
                mid = gradient_at((stops[i], stops[j]), 0.5) if j != i else rgb(stops[i])
                h, sat, _ = color_hsv((round(mid[0]) << 16) | (round(mid[1]) << 8) | round(mid[2]))
                stops.insert(i + 1, hsv_color(h, sat))
                self.stop_sel = i + 1
                s.update(gradient=tuple(stops))
            elif wid == "stop:del" and len(stops) > 2:
                del stops[i]
                self.stop_sel = max(0, i - 1)
                s.update(gradient=tuple(stops))
            elif wid[5:].isdigit():
                self.stop_sel = int(wid[5:])
        elif wid.startswith("preset:"):
            s.update(gradient=dict(GRADIENTS)[wid[7:]])
            self.stop_sel = 0
        elif wid == "flow":
            s.update(flow=not s.flow)
        elif wid.startswith("style:"):
            s.update(music_style=wid[6:])
        elif wid == "night":
            s.set_profiles(night=dict(s.night, on=not s.night["on"]))
        elif wid.startswith(("night_from:", "night_to:")):
            key, step = wid.split(":")
            key = "from" if key == "night_from" else "to"
            value = (s.night[key] // 30 * 30 + (30 if step == "+" else -30)) % 1440
            other = s.night["to" if key == "from" else "from"]
            if value == other:  # from and to never meet
                value = (value + (30 if step == "+" else -30)) % 1440
            s.set_profiles(night=dict(s.night, **{key: value}))
        elif wid == "autostart":
            if PACKAGE:
                os.startfile(STARTUP_SETTINGS)
            else:
                set_autostart(not t.autostart, t.argv)
                t.autostart = autostart_enabled()
        elif wid == "auto_check":
            s.update(check_updates=not s.check_updates)
        elif wid == "check":
            t.check_now()
            self._timers()
        elif wid == "update":
            t.start_update()
        elif wid == "ha:setup":
            t.ha_window()
        elif wid == "ha:disconnect":
            save_settings({"home_assistant": None})
            t.ha_changed()
        elif wid == "link:guide":
            os.startfile(ha_guide_url())
        elif wid == "matter:on":
            t.matter_toggle()
        elif wid == "matter:pair" and t.matter:
            node = t.matter
            node.call(lambda: node.open_window(900))
        elif wid == "matter:stop" and t.matter:
            t.matter.call(t.matter.close_window)
        elif wid.startswith("matter:remove:") and t.matter:
            node, index = t.matter, int(wid.rsplit(":", 1)[1])
            name = next((matter_app_name(f) for f in node.pairing()["fabrics"] if f["index"] == index), "")
            if user32.MessageBoxW(self.hwnd, tr("matter_remove_ask", app=name), "Glowback", 0x24) == 6:  # Yes
                node.call(lambda: node.remove_fabric(index))
        elif wid == "link:matter":
            os.startfile(matter_guide_url())
        elif wid == "open:log":
            os.startfile(LOG_PATH)
        elif wid.startswith("link:"):
            os.startfile({"star": REPO_URL, "repo": REPO_URL, "site": self.SITE_URL, "issues": REPO_URL + "/issues",
                          "author": AUTHOR_URL}[wid[5:]])
        elif wid == "quit":
            k32.SetEvent(t.stop.h)
        elif wid.startswith("pick:"):
            self._pick(wid[5:])
        elif wid == "add":
            d = self.draft
            rule = dict(app=d["app"], when=d["when"], screen=d["screen"], name=d["name"], path=d["path"], look=d["look"])
            s.set_rules(s.rules + [rule])
        elif wid.startswith("remove:"):
            rules = list(s.rules)
            i = int(wid[7:])
            if i < len(rules):
                del rules[i]
                s.set_rules(rules)
            if self.focus == wid:
                self.focus = None
        self.invalidate()

    def _set_color(self, color, live=False):
        """The color being edited: the color mode's, or the gradient's chosen stop. Live: while dragging."""
        s = self.state
        if s.mode == "gradient":
            stops = list(s.gradient)
            stops[min(self.stop_sel, len(stops) - 1)] = color
            kw = dict(gradient=tuple(stops))
        else:
            kw = dict(color=color)
        if live:
            for k, v in kw.items():
                setattr(s, k, v)
            s.version += 1
            s._activate(s.rule_hit)
        else:
            s.update(**kw)

    def _edited_color(self):
        s = self.state
        return s.gradient[min(self.stop_sel, len(s.gradient) - 1)] if s.mode == "gradient" else s.color

    def _slide(self, x, save=False):
        """A slider follows the mouse at x (None: just save where it is)."""
        wid = self.drag or self.focus
        w = self._widget(wid)
        if not w or w["kind"] != "slider":
            return
        f = self._slider_value(w, x) if x is not None else None
        self._slider_set(wid, f, save)
        self.invalidate()

    def _slider_value(self, w, x):
        return max(0.0, min(1.0, (x - w["x0"]) / max(1, w["x1"] - w["x0"])))

    def _slider_set(self, wid, f, save, step=None):
        """Sets slider `wid` to f (0..1; None: unchanged), live while dragging, saved when `save`. `step`: keys."""
        s = self.state
        if wid in ("brightness", "sens", "night_bright"):
            cur = {"brightness": s.brightness, "sens": s.sensitivity, "night_bright": s.night["brightness"]}[wid]
            v = round(cur) if f is None else round(f * 20) * 5
            if step:
                v = max(0, min(100, round(cur / 5) * 5 + step * 5))
            if wid == "night_bright":
                if save or v != s.night["brightness"]:
                    s.set_profiles(night=dict(s.night, brightness=v), save=save)
                return
            attr = "brightness" if wid == "brightness" else "sensitivity"
            if save:
                s.update(**{attr: v})
            elif v != round(cur):
                setattr(s, attr, v)  # live while dragging; saved once released
                s.version += 1
                s._activate(s.rule_hit)
        elif wid in ("hue", "sat"):
            color = self._edited_color()
            h, sat = self._hsv(color)
            if wid == "hue":
                h = h if f is None else f * 360.0
                if step:
                    h = (h + step * 5) % 360
                sat = sat if sat > 0.05 else 1.0  # a white takes colour when the hue moves
            else:
                sat = sat if f is None else f
                if step:
                    sat = max(0.0, min(1.0, sat + step * 0.05))
            new = hsv_color(h, sat)
            self.hue_memo = (new, h)
            self._set_color(new, live=not save)

    def _pick(self, which):
        w = self._widget("pick:" + which)
        if not w:
            return
        s, d = self.state, self.draft
        items = []

        def radio(text, value, checked, **kw):
            items.append(dict(kind="radio", text=text, value=value, checked=checked, **kw))

        def other(kind, text="", value=None):
            items.append(dict(kind=kind, text=text, icon="add" if kind == "action" else None, value=value))

        if which == "app":
            radio(tr("sync_any_app"), ("", "", ""), not d["app"])
            apps = AppWatch().open_apps()
            if d["app"] and all(a[0] != d["app"] for a in apps):
                radio(d["name"] or d["app"][:-4], (d["app"], d["name"], d["path"]), True)
            if apps:
                other("sep")
                other("label", tr("sync_open_apps"))
                for exe, name, path in apps[:24]:
                    radio(name, (exe, name, path), exe == d["app"])
            other("sep")
            other("action", tr("sync_browse"), "browse")
        elif which == "when":
            for when in WHEN:
                if when != "running" or d["app"]:
                    radio(tr("sync_" + when), when, d["when"] == when, icon="volume" if when == "playing" else None)
        elif which == "screen":
            radio(tr("sync_any_screen"), "", not d["screen"])
            radio(self._screen_text("leds"), "leds", d["screen"] == "leds")
            other("sep")
            for m in self._monitors(fresh=True):
                key = m.name or m.device
                radio(f"{tr('sync_screen_n', n=m.index)} · {key}", key, d["screen"] == key)
        elif which == "lang":
            saved = load_settings().get("lang") or ""
            for code, name in self.LANG_NAMES:
                radio(name or tr("lang_auto"), code, saved == code)
        elif which == "palette":
            for pal in MUSIC_PALETTES:
                kw = {"rainbow": dict(stops=[hsv_color(a * 60, 1) for a in range(6)]), "screen": dict(icon="monitor"),
                      "color": dict(swatch=s.color), "gradient": dict(stops=s.gradient)}[pal]
                radio(tr("palette_" + pal), pal, s.music_palette == pal, **kw)
        elif which == "rest":
            for value, glyph in (("auto", "sparkle"), ("device", "bulb"), ("off", "power")):
                radio(tr("look_auto" if value == "auto" else "look_" + value), value, s.otherwise == value, icon=glyph)
        elif which == "night_look":
            items = self._look_items(s.night["look"], tr("night_same"))
        elif which == "draft_look":
            items = self._look_items(d["look"], tr("look_auto"))
        elif which.startswith("look:"):
            i = int(which[5:])
            if i >= len(s.rules):
                return
            items = self._look_items(s.rules[i].get("look"), tr("look_auto"))
        for it in items:
            it["min"] = (w["rect"][2] - w["rect"][0]) / self.k
        chosen = self._menu(items, w["rect"])
        if chosen is None or chosen.get("value") is None:
            return
        value = chosen["value"]
        if which == "app":
            if value == "browse":
                path = pick_program(self.hwnd)
                if not path:
                    return
                value = (app_key(path), app_description(path), path)
            d["app"], d["name"], d["path"] = value
            if not d["app"] and d["when"] == "running":
                d["when"] = "foreground"
        elif which == "when":
            d["when"] = value
        elif which == "screen":
            d["screen"] = value
        elif which == "lang":
            save_settings({"lang": value or None})
            set_lang(value or detect_lang())
            self.tray.refresh()
        elif which == "palette":
            s.update(music_palette=value)
        elif which == "rest":
            s.set_profiles(otherwise=value)
        elif which == "night_look":
            s.set_profiles(night=dict(s.night, look=value[1]))
        elif which == "draft_look":
            d["look"] = value[1]
        elif which.startswith("look:"):
            rules = [dict(r) for r in s.rules]
            rules[int(which[5:])]["look"] = value[1]
            s.set_rules(rules)
        self.invalidate()

    def _menu(self, items, rect):
        """An owner-drawn popup menu in the panel's style, under a picker (entries with "items" open a submenu):
        the entry chosen, or None."""
        flat = []

        def build(entries):
            menu = user32.CreatePopupMenu()
            info = MENUINFO()
            info.cbSize, info.fMask, info.hbrBack = sizeof(info), 0x2, self.painter.bg_brush  # MIM_BACKGROUND
            user32.SetMenuInfo(menu, byref(info))
            for pos, it in enumerate(entries):
                i = len(flat)
                flat.append(it)
                if it.get("items"):
                    sub = build(it["items"])
                    user32.AppendMenuW(menu, 0x10 | 0x100, sub, ctypes.c_void_p(i))  # MF_POPUP | MF_OWNERDRAW
                elif it["kind"] in ("sep", "label"):  # a separator the keyboard skips, drawn like the rest
                    mii = MENUITEMINFOW()
                    mii.cbSize, mii.fMask = sizeof(mii), 0x100 | 0x20  # MIIM_FTYPE | MIIM_DATA
                    mii.fType, mii.dwItemData = 0x800 | 0x100, i  # MFT_SEPARATOR | MFT_OWNERDRAW
                    user32.InsertMenuItemW(menu, pos, True, byref(mii))
                else:
                    user32.AppendMenuW(menu, 0x100, i + 1, ctypes.c_void_p(i))  # MF_OWNERDRAW
            return menu

        menu = build(items)
        self.menu_items = flat
        pt = wt.POINT(int(rect[0]), int(rect[3]) + self.px(4))
        user32.ClientToScreen(self.hwnd, byref(pt))
        cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0080, pt.x, pt.y, 0, self.hwnd, None)  # RETURNCMD, NONOTIFY
        user32.DestroyMenu(menu)  # and its submenus
        self.menu_items = []
        return flat[cmd - 1] if cmd and cmd - 1 < len(flat) else None

    def _key(self, vk):
        order = []
        for w in self.widgets:
            if w["focus"] and w["id"] not in order:
                order.append(w["id"])
        if vk == 0x09:  # Tab, Shift+Tab
            self.focus_visible = True
            if order:
                i = order.index(self.focus) if self.focus in order else -1
                back = user32.GetKeyState(0x10) & 0x8000
                self.focus = order[(i + (-1 if back else 1)) % len(order)]
                self._reveal(self.focus)
            self.invalidate()
            return 0
        if vk in (0x0D, 0x20) and self.focus in order:  # Enter, Space
            self.activate(self.focus)
            return 0
        if vk in (0x25, 0x26, 0x27, 0x28) and self.focus in self.SLIDERS:  # arrows
            self._slider_set(self.focus, None, True, step=1 if vk in (0x26, 0x27) else -1)
            self.invalidate()
            return 0
        if vk in (0x21, 0x22, 0x24, 0x23):  # Page up/down, Home, End
            H = self.size[1]
            self.scroll_by({0x21: -H * 0.8, 0x22: H * 0.8, 0x24: -1e9, 0x23: 1e9}[vk])
            return 0
        return None

    def _reveal(self, wid):
        w = self._widget(wid)
        if not w or w["side"]:
            return
        p, H = self.px, self.size[1]
        if w["rect"][1] < p(16):
            self.scroll_by(w["rect"][1] - p(16))
        elif w["rect"][3] > H - p(16):
            self.scroll_by(w["rect"][3] - (H - p(16)))

    def scroll_by(self, dy):
        new = int(max(0, min(self.max_scroll, self.scroll + dy)))
        if new != self.scroll:
            self.scroll = new
            self.invalidate()

    # ---- window procedure
    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            r = self._on(hwnd, msg, wparam, lparam)
            if r is not None:
                return r
        except Exception as e:  # never let a drawing error take the tray down
            log(f"App window: {e!r}")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on(self, hwnd, msg, wparam, lparam):
        xy = lambda: (ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        if msg == 0x000F and self.painter:  # WM_PAINT
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, byref(ps))
            rc, pr = wt.RECT(), ps.rcPaint
            user32.GetClientRect(hwnd, byref(rc))
            if rc.right > 0 and rc.bottom > 0:
                part = (pr.left, pr.top, pr.right, pr.bottom)
                self.draw(hdc, rc.right, rc.bottom, None if part == (0, 0, rc.right, rc.bottom) else part)
            user32.EndPaint(hwnd, byref(ps))
            return 0
        if msg == 0x0014:  # WM_ERASEBKGND: painted in WM_PAINT
            return 1
        if msg == 0x0005:  # WM_SIZE
            self._timers()
            self.invalidate()
            return 0
        if msg == 0x0024 and self.painter:  # WM_GETMINMAXINFO
            mmi = MINMAXINFO.from_address(lparam)
            mmi.ptMinTrackSize.x, mmi.ptMinTrackSize.y = self.px(self.MIN[0]), self.px(self.MIN[1])
            return 0
        if msg == 0x02E0:  # WM_DPICHANGED: another screen, or its scale changed
            self.set_scale((wparam & 0xFFFF) / 96.0)
            rc = wt.RECT.from_address(lparam)
            user32.SetWindowPos(hwnd, None, rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top, 0x0014)
            self.invalidate()
            return 0
        if msg == 0x0113:  # WM_TIMER
            if wparam == 1:
                r = self.preview_rect
                if (self.state.preview or self.state.thumb) and r and r[3] > r[1]:
                    user32.InvalidateRect(hwnd, byref(wt.RECT(*r)), False)  # only the preview moves
                return 0
            if wparam == 3 and not self.tray.checking:
                user32.KillTimer(hwnd, 3)
            self.invalidate()
            return 0
        if msg == 0x0200:  # WM_MOUSEMOVE
            x, y = xy()
            if self.drag:
                self._slide(x)
                return 0
            w = self._hit(x, y)
            wid = w["id"] if w else None
            if wid != self.hover:
                self.hover = wid
                self.invalidate()
            if not self.tracking:
                tme = TRACKMOUSEEVENT(sizeof(TRACKMOUSEEVENT), 0x2, hwnd, 0)  # TME_LEAVE
                self.tracking = bool(user32.TrackMouseEvent(byref(tme)))
            return 0
        if msg == 0x02A3:  # WM_MOUSELEAVE
            self.tracking = False
            if self.hover:
                self.hover = None
                self.invalidate()
            return 0
        if msg == 0x0201:  # WM_LBUTTONDOWN
            x, y = xy()
            w = self._hit(x, y)
            self.pressed, self.focus_visible = (w["id"] if w else None), False
            if w and w["kind"] == "slider":
                self.drag = w["id"]
                self.focus = w["id"]
                user32.SetCapture(hwnd)
                self._slide(x)
            self.invalidate()
            return 0
        if msg == 0x0202:  # WM_LBUTTONUP
            x, y = xy()
            if self.drag:
                self._slide(x, save=True)
                self.drag = self.pressed = None
                user32.ReleaseCapture()
                return 0
            w, pressed = self._hit(x, y), self.pressed
            self.pressed = None
            if w and w["id"] == pressed:
                if w["focus"]:
                    self.focus = w["id"]
                self.activate(w["id"])
            self.invalidate()
            return 0
        if msg == 0x0215 and self.drag:  # WM_CAPTURECHANGED: dragging ended elsewhere
            wid, self.drag = self.drag, None
            self._slider_set(wid, None, True)
            return 0
        if msg == 0x020A:  # WM_MOUSEWHEEL
            self.scroll_by(-ctypes.c_short((wparam >> 16) & 0xFFFF).value / 120 * self.px(72))
            return 0
        if msg == 0x0100:  # WM_KEYDOWN
            return self._key(wparam)
        if msg == 0x002C and self.painter:  # WM_MEASUREITEM: a picker's menu
            mis = MEASUREITEMSTRUCT.from_address(lparam)
            if mis.CtlType == 1 and mis.itemData < len(self.menu_items):
                self.painter.measure(mis, self.menu_items[mis.itemData])
                return 1
        if msg == 0x002B and self.painter:  # WM_DRAWITEM
            dis = DRAWITEMSTRUCT.from_address(lparam)
            if dis.CtlType == 1 and dis.itemData < len(self.menu_items):
                self.painter.draw(dis, self.menu_items[dis.itemData])
                return 1
        if msg == 0x0121 and wparam == 2 and self.painter:  # WM_ENTERIDLE from the menu: dark rounded border
            self.painter.style_window(lparam)
        if msg == 0x0010:  # WM_CLOSE: the window goes, Glowback stays
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            for timer in (1, 2, 3):
                user32.KillTimer(hwnd, timer)
            self.hwnd, self.hover, self.pressed, self.drag = None, None, None, None
            self._free_bufs()
            self._free_gdi()
            self.tray.app_closed()
            return 0
        return None


# =============================================================================
# Command line
# =============================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="glowback",
        description="Ambient light for monitors with RGB LEDs on the back (Windows Dynamic Lighting / HID LampArray).",
        epilog="Example: glowback --brightness 70 --smoothing 0.2")
    p.add_argument("--mode", choices=list(MODES), default=None,
                   help="zones: each LED follows the part of the image it sits behind (default); average: one color "
                        "for all, the screen's average; color: --color; gradient: --gradient; music: the LEDs follow "
                        "the sound the PC plays")
    p.add_argument("--color", metavar="#RRGGBB", help="the color of the color mode (default: the app's)")
    p.add_argument("--gradient", metavar="#RRGGBB,#RRGGBB[,...]",
                   help="2 to 4 colors of the gradient mode, from left to right (default: the app's)")
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
    p.add_argument("--openrgb", nargs="?", const="127.0.0.1:6742", default="auto", metavar="HOST:PORT|off",
                   help="OpenRGB SDK server whose devices are driven too (default: auto-detect on this PC; off to disable)")
    p.add_argument("--home-assistant", metavar="mqtt://USER:PASSWORD@HOST[:PORT]|off",
                   help="show Glowback in Home Assistant through its MQTT broker (saved; off to remove it)")
    p.add_argument("--sync-when", action="append", metavar="WHEN:APP[@SCREEN]|always",
                   help="follow the screen only while one of these holds (repeatable, saved): WHEN is running, "
                        "foreground, fullscreen or playing (plays sound); APP an .exe name or * for any app; SCREEN "
                        "leds (the screen the LEDs follow), a number from --list or a name. 'always' removes the "
                        "conditions. The app's Profiles page sets a look for each app")
    p.add_argument("--strip-start", default="bottom-left",
                   choices=["bottom-left", "bottom-center", "bottom-right", "top-left", "top-right"],
                   help="OpenRGB LED strips: where the first LED is (strip runs around the screen)")
    p.add_argument("--strip-ccw", action="store_true", help="OpenRGB LED strips run counter-clockwise (seen from the front)")
    p.add_argument("--white-balance", type=lambda v: tuple(float(x) for x in v.split(",")), metavar="R,G,B",
                   help="color multipliers 0-1 for all devices, e.g. 1,0.9,0.8 (default: from --calibrate)")
    p.add_argument("--calibrate", action="store_true", help="interactive per-device white balance, then exit")
    p.add_argument("--diy-layout", metavar="WxH:L,T,R,B",
                   help="print LED positions for a DIY RP2040 strip (see docs/DIY-LED-strip.md), then exit")
    p.add_argument("--lang", choices=LANGS, help="interface language (default: the Windows display language)")
    p.add_argument("--no-tray", action="store_true", help="no notification-area icon")
    p.add_argument("--list", action="store_true", help="list LED devices and screens, then exit")
    p.add_argument("--test", action="store_true", help="play an orientation test pattern, then exit")
    p.add_argument("--stop", action="store_true", help="stop the running Glowback instance")
    p.add_argument("--install", action="store_true", help="start with Windows + Start menu entry (keeps the other options)")
    p.add_argument("--uninstall", action="store_true", help="stop Glowback and remove it from startup, Start menu and app data")
    p.add_argument("--autostart", choices=["on", "off"], help="start Glowback with Windows (with the other options given)")
    p.add_argument("--check-updates", choices=["on", "off"],
                   help="look for a new version on GitHub once a day (saved, default on; applies from the next start)")
    p.add_argument("--background", action="store_true", help="detach from the console (log in %%LOCALAPPDATA%%\\Glowback)")
    p.add_argument("--from-autostart", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--pause-at-end", action="store_true", help=argparse.SUPPRESS)  # Start menu tools
    p.add_argument("--after-update", action="store_true", help=argparse.SUPPRESS)
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
        if a in ("--autostart", "--check-updates"):
            skip = True
            continue
        if a.startswith(("--autostart=", "--check-updates=")):
            continue
        out.append(a)
    return out


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw)
    if PACKAGE and os.path.basename(sys.executable).lower().startswith("glowbackbackground"):
        args.background = args.from_autostart = True  # the Store package's startup task: no window
    store_first_run()
    if args.color is not None and hex_color(args.color) is None:
        sys.exit("--color: a color like #FF8800")
    if args.gradient is not None and clean_stops(args.gradient) is None:
        sys.exit("--gradient: 2 to 4 colors like #FF0080,#7928CA")
    set_lang(args.lang or load_settings().get("lang") or detect_lang())  # the app's Settings page can choose it
    try:  # leftover of a previous in-place update
        os.remove((sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)) + ".old")
    except OSError:
        pass
    keep = _passthrough(raw)
    if args.stop:
        request_stop()
        return
    if args.home_assistant:
        cmd_home_assistant(args.home_assistant)
        return
    if args.sync_when:
        cmd_sync_when(args.sync_when)
        return
    if args.diy_layout:
        cmd_diy_layout(args.diy_layout)
        return
    if args.uninstall:
        cmd_uninstall()
        return
    if args.check_updates:  # the installer runs this to save its "check for a new version" box
        save_settings({"check_updates": args.check_updates == "on"})
        print("Update checks on." if args.check_updates == "on" else "Update checks off.")
        if not (args.install or args.autostart):
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
    relaunch = replaced = False
    if stop.already_running:
        if args.after_update:
            stop = _other_quit(stop, 100)  # the previous version is quitting
        if stop.already_running and (args.test or args.calibrate):
            print(tr("pausing"))
            request_stop(quiet=True)
            stop = _other_quit(stop)  # once the other instance has handed the LEDs back and exited
            relaunch = not stop.already_running
        tray_hwnd = user32.FindWindowW("GlowbackTray", None) if stop.already_running else None
        if tray_hwnd and not (args.test or args.calibrate):  # launched again: the running one shows its window
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(tray_hwnd, byref(pid))
            user32.AllowSetForegroundWindow(pid.value)
            user32.PostMessageW(tray_hwnd, Tray.WM_OPEN_APP, 0, 0)
            for _ in range(50):
                if app_window_shown(pid.value):
                    k32.CloseHandle(stop.h)
                    return
                time.sleep(0.1)
            # No window: an older Glowback that has none (the pip version's tray icon), or one that can no longer
            # open it. This one replaces it.
            request_stop(quiet=True)
            stop = _other_quit(stop)
            replaced = not stop.already_running
        if stop.already_running:
            msg = tr("already")
            if sys.stdout is None:
                user32.MessageBoxW(None, msg, "Glowback", 0x40)
            else:
                print(msg + " (glowback --stop to quit it)")
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
            try:  # a new log each start; the previous one is kept (what went wrong before a restart)
                os.replace(LOG_PATH, LOG_PREVIOUS)
            except OSError:
                pass
            log(f"Glowback {__version__} - mode {args.mode}, {args.fps:g} fps. Ctrl+C or 'glowback --stop' to quit.")
            if replaced:
                log("Replaced a running Glowback that did not open its window (its log: glowback.previous.log).")
            sys.unraisablehook = _log_unraisable
            state = State(args, enabled)
            if args.no_tray:
                HomeAssistant(state, stop).start()
                run(args, stop, state)
            else:
                run_with_tray(args, stop, state, keep)
    except KeyboardInterrupt:
        pass
    finally:
        stop.done.set()
        if relaunch:
            k32.CloseHandle(stop.h)  # free the single-instance slot for the relaunched app
            subprocess.Popen(launch_command(), creationflags=0x00000008 | 0x00000200, close_fds=True)
            print(tr("restarted"))
        if args.pause_at_end and sys.stdout is not None:
            input("\n" + tr("press_enter"))


# =============================================================================
# Embedded UI font: Inter (https://rsms.me/inter), SIL Open Font License 1.1,
# subset and renamed "Glowback Inter". License: licenses/Inter-OFL.txt
# =============================================================================
INTER_FONTS = (
    (
        "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"
        "f2Vh/zL/LTGGqFfeUfNmoqk/nfBLYr4PBQsAMcqx9rRU+vXcCPBiB5ou7e0jXa02/I2Z/ecx+6s+f9KZxv9ZwzodkRkdLN8nf6vl"
        "Kmony9taE+du1fM8Li3nTq+GtC/TLn5peOm1xP98t4L2rYG+L7xK03a077OoLdYascdRYumEfnfiFx920mexb8qt7VbVM54f4b5g"
        "pGo7tPzkb8igUC2H1Hb4eo01WyHVXoI52raOI79gFj+RL2yhLXY5qqb8ot4koP9Ln85nxL8fZbffaVGt1f4nPexkh0bcPW9frt0O"
        "zZ+tyn/hM/i/0t9aYufJWlR5teN6+K/Gns6qvL8fOajWZsqPlOX8fWRF9wkQnKf+Lc7/eZ9b/rNZxNf+xzr2D3Yf/42Z+881U7Pm"
        "3+NMiCjaWd+/tQ7gm/+Fnv/jnfX/YN374J9rmKa0/m6r//dtyv9rn39l3dk55VzlMiFWVi4jV8J3pyWXqb7bl2iLsju/7/I8Sn+K"
        "ADvoaTtL8vC/0PMS9P+7T8e9n//hKrb9fnJA29pfvUvVIO4CNPyt9cP/l6Tf+Z5GmzVP+5d2Z56Qu2gqOwpWXGP3X/nTX9Sf9Q8b"
        "9n/OvkOkxtrBv9N1mX8HOpEUQ2xJ3Z/WGHadrjk678n/YH8b1s9VdH9VvYZ7yQiy/j/1kmL9q/9vWD9y5/u/PHkY8BOY/mfApWgN"
        "nMlz6RWoBp1Ee9Fp9BAdR9+jx+g++gU9Qd+h39Dv6BF6hhToB2yMjdFP2BSbop+xOTZHv9Dnf59gJ9wb/Yrd8RCkwMPgkOERcGhh"
        "P+yPtcmTv1gXh+BQrI/D8UTcBU/CiVBzKk7FNjgdZ0H9HDwX98bz4ZDjDXgT9sLV+AAeTJ72xcNxPW7A5B3Ly+kzz+R3mLpIhvTg"
        "MEL6AJbIGKI6DplCz2T0WejeyAY5ICvkCocFpPrBtzvyQFrIE8mhnBdEO93QSBQCtULhkKExcDiiMDg4FI6igF40Go8M0QQUC21M"
        "QtOgbgocDvSXBHZoBhzmKA3NBC4y0WxoORvNBR7nweGM5qMlwOtSOHzQMvHp/7XA1zo4vNF6tAn1QJvRVii/DW1H2mgH2omc0C60"
        "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"
        "Yd2EdRPWTVg3Yd2EdH9PYye7D81emX1k9rHZZ+V1r1eI5Bb7fQY040hbhD2/EtbiWNuGnFtv+rqeYyHHlImFnBtybsi5inMV5yqT"
        "G3LJIZcccskhlxxyySGXHHLJIZcccsmKS1ZcsuKSFZesuGTFJSsuWXHJisKvqUfqzT40+2x6aNJDkx6adGXSlUnPliPpSGJcSCm7"
        "yVLZT1bKauRvvWyQT8mZcq5cKJfKVXK93CJ3y33ykHxfHpen5Tl5UV6zXLyClVnl1mCrxhpjRdZEa6o1x2q1FuMVdY210dpu7bHe"
        "sY5YH1gnrTPWeeuyLezALrb72APsofYoe5w9wZ5sz7CfsxfYS+yV9jp7s73L3msftN+zj9mn7E/sC/ZVx3YyTk+nvzPIGe7UOcpp"
        "dKY4s5wWZ5GzzFntbHC2Oe3O285h56hzwvnY+dS55Fx3fbfI7eVWuFVurTvWTdxJ7jS32Z3vtrkr3LXuJneH+6Z7wH3X/dD9yD3r"
        "fuZe8aTXzSv1+nmVXrU32qv3GrynvJneXG+ht9Rb5a33tni7vX3eIe9977h32jvnXfSu+a5f6Jf55f5gv8Yf40f+RH+qP8dv9Rf7"
        "y/01/kZ/u7/Hf8c/4n/gn/TP+Of9y3hzD1LFqT6pAamhqVGpcakJqcmpGannUgtSS1IrU+tSm1O7UntTB1PvpY6lTqU+SV1IXQ3s"
        "IBP0DPoHg4LhQV2ggsZgSjAraAkWBkuCFcGaYEOwJdgVvBm8ExwO3g+OBR8FZ4JPg4vB1bRMB+midFm6f7oyPTRdmx6TVumG9OT0"
        "tPScdEt6YXpJekV6TXp9elN6G+xgju1gju1gjuViEcdijiUmFrJuyLoh64asG7JuyLqKdRXrKtZVrKtYV7FuxLoR60asG7FuxLoR"
        "68asG7NuzLox68asG7NuwroJ6yasm7BuwrqJ0Q0Z55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcQ4Z"
        "55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcVaMs2KcFeOsGGfFOCvGWTHOinFWjLNinBXjrBhnxTgr"
        "xlkxzopxVoyzYpwV46wYZ8U4K8ZZMc6KcVaMs2KcFeOsGGfFOCvGWTHOinFWjLNinBXjrBjniHGOGOeIcY4Y54hxjhjniHGOGOeI"
        "cY4Y54hxjhjniHGOGOeIcY4Y54hxjhjniHGOGOeIcY4Y54hxjhjniHGOGOeIcY4Y54hxjhjniHGOGOeIcY4Y54hxjhjnmHGOGeeY"
        "cY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeY"
        "cY4Z55hxjhnnhHFOGOeEcU4Y54RxThjnhHFOGOeEcU4Y54RxThjnhHFOGOeEcU4Y54RxThjnhHFOGOeEcU4Y54RxThjnhHFOGOeE"
        "cU4Y54RxThjnhHFOGOeEcU4Y54RxTii8bmaxr5tZ7OtmFpvdR2Yfm31WPjTyoZEPjXxo5EMjHxp5ZeSVkVdGXhl5ZeSVkY+MfGTk"
        "IyMfGfnIyEdGPjbysZGPjXxs5GMjHxv5xMgnRj4x8omRT4x8Fh9JUpJkJOVISPRKiZlXZa8pT8NsWmOyRUb0EYNFHa0tSfGUPC8g"
        "qBbCHDeLajwu5+NR8qjIffE0m6JofQlIAg0C3QudazP0y+i1IHhar+fAOi3xlfmz9TdURTfYTmXobV45sJjWeCIxEwbAOJgAk6FZ"
        "eKJQlIn+ohJcUYU24VYsfzqGafrbxbT/De2nw2YsbQP8Drevkc/PWaG/53IJNhm539KKRhHan1WiVozNs0IXi2VilViHduh20S72"
        "iQPwJteSi80xsSZOazJpTSzXxHJNLNdEcn80bcjus8dN5ljn7zTnkN030b7JHOsS9PP7XbAHt2hLI0qF2e81U1ntpow/kHWt8d9M"
        "Z6pjv6NYFnNdxjTazjEpeyhlj9HzcbxMh9lY1jr4NWzHMeWSV+1qsUscEafRJi+DOrTDZ6IFvhb2wrvwEVyQvhwga2UiZ8hFciPa"
        "gQflMXlWXkL7r8yqsuqtJdZaa4d10DphXbBtuwxtu3p7qr3QXmPvtq+htdbqrHS2o4V23pVumVvtTnAXuqvRBjvsnvaqvLHeZLSz"
        "lnvt3rvexzQWAftUYk8todHo0qh6kkblKsoDMSsvp55yWk1OkpcTUs5kk1Odl6Mop87klOXlPEZjfxiMIg+aYu1XaueY4upVUH01"
        "yq50wpMwGaUs54BzQDyHctm3+ixhO7t0EE9h2lqT5jjrskHUY2qbSXWdtlwQQzF9jkn30MLloNtnN+RWY6Ga6qx36qnOQ1zncB2o"
        "znaus382UJ0buM5uuUB1Ls3VaV/qDFRnM9dZo+u0j9vHdZ2OzNVpH9aB6ryQq9Nuzwaq81SuTnt9LlCd73KdbZ2B6mznOvX32EEO"
        "wt8GPD6YvS7JXvhbIaTTQO+S6pQAfwsQkTqnTmzMpsFlTJvBvab7ej6mNGDOWZKQcoyYiSljMOU4pViySlaJRkyrwrTD2fOTvXTQ"
        "40TXC9kaHelmg6jEdBw1sN5cM/X3rD/DcfEZtNEV1RUt4lWMaW/kfmKH+AuOQf1l7BnkY7eA/LT+PTviYS/+xnF7dcoWLGkLVHdJ"
        "W4XXgVUY+nVJXYBXgQUUgi7pU4Wjn9rQk5uLeVicNHWdzEs7gmlDhbSu6hintmNqL2FZZ62zOm7SpXUUr6QA+qnDurzUfaKN/Adz"
        "sVz6JuLrCSxnk4lncyxrqbWUGHsgj7k6vdlqFsPxeBtqZ2O5nAarQX+LU6zIi2eZqe9AL2BcezG+IP4HPNECQ+AB8St6Jraanju9"
        "Cv8By8Ua+pb4ulyf0VtiuVJcGAkP42EE44WHd6fJIo3Xy7l4JdXPs4rxmvmWKCG5av3/xvFq8BjK6Sdnaby2zkK5VmhFuXV4FyvR"
        "LYZNkL2SLc8bjzYs1wHvTCBa8tId7TFLXrONdOXqzHFhYi5ge/W1qzPP088Ec4E84cs5VzNpJG2HUWsKofDm1pAn59WbWyPOmHBT"
        "a8R7HG5qjdidF25uzUO0HaFbgy1ZQv+JZk+X1jRT0N6yG7q0ptGERZi2pEtrajlMo7tDfmv65AU96qP83sZYjqGvih3wivgvHCG/"
        "hF/Ar5BlS/AeuB+WUXt/SNsHaczgNRDPW49oHuPiMAYQyGLa51K34RwE8E4GiERn6iqcp+kekDQj6WRbqf4vl5g6n3yHsy2U4nPx"
        "pX7AhuM5RZhNwDnNJPLpBNobZoga7IU68mmWFO+srwIDiJ70lkRFZ0/g7EnfxdbCf9LTvUvgGWSAPEcTUQ7PIhtG6e/yw0M4L3jY"
        "zDnHIy9m42ykCZpR4jl4HkfsPD2bgB2wE+cwv4fd8Adoh7fgDdgDf8Q5ksR+0P7GglgDxBqfWNONWNOdWFNCrCnNa8Mscb+4LvT/"
        "aAeQYIENDrjgQXfI6P8fAAU4nm+DYv1fBKAESuEOnL/4kIIA0jiPvBN6QW/oA32hH9wF/aEcfgAVcA/OPO+FShgId8MguA/0f1wN"
        "xCWNMrZuhAjwnOtEIfkLl5Kn8O3amxVnY9oLuAzbO1f0xvbOE/cRdkPMU1KfrrrFtB0k5PNzX1yI903x0jOzWvX/O5jd+nQzlqvH"
        "XBHOdWnmjbVlcvNtPFqNSQey9yc8erjz+fP/AZ4S7RE="
    ),
    (
        "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"
        "tnpa/awhlmeNtSZaM6zZ1kIaUVda66zN1g5rl7Xfes86Yp2wTlsXbbCTdq7dxe5m97YH2sPt0fZ4e4r9hD3PXmQvs1fbG+xt9pv2"
        "Hvsd+6B91P6Nfda+HLEjWZEOkaJIj0jfSEXEjYyJTIhMi1RHFkReiKyIrI1sitRGfhzZFzkQORw5Hvkocj5yNRqP5uiv2UdLo+XR"
        "odEgOi46KVoVnRutiS6Nroquj26Jvh59K/p29P3oB9GT0TPRSzEVaxXLjxXGSmJlsUGxEbHK2KOxqbFZsfmxxbHlsTWxjbHtsZ2x"
        "vbF3Y4dix2KnYudiV+LReJt4Qbw43jPeLz4k7sXHxifGZ8RnxxfGl8RXxtfFN8d3xHfF98ffix+Jn4ifjl+ki3sykZvokuiW6J0Y"
        "mBieGJ0Yn5iSeCIxL7EosSyxOrEhsS3xZmJP4p3EwcTRxG8SZxOXk3YyK9khWZTskeybrEi6yTHJCclpyerk/OSi5NLkyuTa5Mbk"
        "tuTryV3Jfcl3kweTHyRPJD9KnkteTqlUMpWTKkgVpUpSvVPlqSEpN1WZGp+alJqRqk7NTy1KLU2tTK1JrU9twi3CsS3CsS3CsTqf"
        "Jz5ffIHxOSLriKwjso7IOiLriKwrsq7IuiLriqwrsq7IeiLriawnsp7IeiLriawvsr7I+iLri6wvsr7IBiIbiGwgsoHIBiIbGFlH"
        "cHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdH"
        "cHYEZ0dwdgRnR3B2BGdXcHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdX"
        "cHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdPcPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdP"
        "cPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdfcPYFZ19w9gVnX3D2BWdfcPYFZ19w9gVnX3D2BWdf"
        "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"
        "+OD6e8//B6IgfJ0="
    ),
)


if __name__ == "__main__":
    main()
