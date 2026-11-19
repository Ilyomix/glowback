# DIY: add ambient light to any monitor with a $5 RP2040 board and an LED strip

Your monitor has no RGB on the back? Stick an addressable LED strip behind it and drive it with a Raspberry Pi Pico (RP2040). The Pico shows up in Windows as a **Dynamic Lighting (HID LampArray) device**, so Glowback drives it like a built-in monitor LED. No serial protocol and no extra software are needed.

> **Status:** the firmware side is Microsoft's own [RP2040 LampArray sample](https://github.com/microsoft/RP2040MacropadHidSample), adapted below. This guide has not been tested end to end by the Glowback maintainers yet. If you build it, please [send a device report](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) with photos.

## What you need

| Part | Notes |
|---|---|
| Raspberry Pi Pico (or any RP2040 board) | about $4–5 |
| WS2812B LED strip, 5 V, 60 LEDs/m | measure your monitor's perimeter. A 27" monitor takes about 1.7 m, roughly 100 LEDs |
| 5 V power supply | up to 60 mA per LED at full white (100 LEDs → 6 A max, ambient use is far lower). A USB port (500 mA) cannot power the strip: use a separate supply |
| Wires, solder, double-sided tape | optional: a 330 Ω resistor on the data line and a 1000 µF capacitor across 5 V/GND |

**Wiring:** strip `DIN` → Pico `GP19` (physical pin 25). Strip `GND` → Pico `GND` **and** the power supply's GND. Strip `5V` → the power supply's 5 V. The Pico is powered by its USB cable, which also carries the lighting data.

Lay the strip on the back of the monitor starting at the **bottom-left corner (seen from the front)** and going **up the left side**, then clockwise around the screen. Count the LEDs on each side.

## 1. Generate the LED layout

```bash
glowback --diy-layout 600x340:17,30,17,30
```

The format is `WIDTHxHEIGHT:LEFT,TOP,RIGHT,BOTTOM`: the rectangle the strip follows, in millimeters, and the number of LEDs on each side in strip order. Glowback prints a block of C code (`NEOPIXEL_COUNT`, `LAMPARRAY_WIDTH`, `LampPositions`…) with the physical position of every LED. Windows and Glowback use those positions to map each LED to the right part of the screen.

## 2. Adapt Microsoft's RP2040 sample

Clone [microsoft/RP2040MacropadHidSample](https://github.com/microsoft/RP2040MacropadHidSample) and follow its README build setup (WSL, Pico SDK, latest TinyUSB). Then make these changes:

1. **`src/util.h`**: in the *Neopixel*, *LampArray Attributes* and *Lamp Attributes* sections, replace `NEOPIXEL`, `NEOPIXEL_COUNT`, `LAMPARRAY_LAMP_COUNT`, `LAMPARRAY_WIDTH`, `LAMPARRAY_HEIGHT`, `LAMPARRAY_DEPTH`, `LAMPARRAY_KIND` and `LampPositions` with the block printed by `glowback --diy-layout`. `LAMPARRAY_KIND 5` declares the device as ambient lighting. The sample says *keyboard*, which Glowback ignores by default.
2. **`src/Lighting/LampArray.c`**, in `GetLampAttributesReport`: replace the last field, `layers[0].macros[LampIdToKey(currentLampId)].keycode[0]`, with `0`. Your LEDs are not keys, and the key table only has 12 entries.
3. **`src/macropad.c`**, in `main()`: remove the `add_repeating_timer_ms(... keyboardTimerCallback ...)` call so the board never sends keystrokes.
4. Build for a plain Pico: `cmake -DPICO_BOARD=pico ..` then `make`.

Hold **BOOTSEL** while plugging the Pico in, then copy the `.uf2` file to the `RPI-RP2` drive. The board reboots and appears in *Settings → Personalization → Dynamic Lighting*.

## 3. Run Glowback

1. In *Dynamic Lighting*, turn **off** "Use Dynamic Lighting on my devices" for the new device.
2. Check that it is detected: `glowback --list`
3. Check the orientation: `glowback --test`. Use `--mirror` or `--flip` if needed.
4. Optionally, match the strip's white to your wall: `glowback --calibrate`
5. Start it with Windows: `glowback --install`

## Already using OpenRGB?

If your strip runs on a controller that [OpenRGB](https://openrgb.org) supports (motherboard ARGB header, Nollie, Prism, ESP/WLED…), you can skip the firmware entirely. Start OpenRGB's SDK server and run:

```bash
glowback --openrgb --strip-start bottom-left
```

`--strip-start` (`bottom-left`, `bottom-center`, `bottom-right`, `top-left`, `top-right`) and `--strip-ccw` tell Glowback where the strip begins and which way it runs.
