# Contributing to Glowback

Thanks for helping more monitors glow!

## Report a device (the most useful contribution)

Open a [device report](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) with:

- your monitor or LED device model,
- the output of `glowback --list`,
- whether `glowback --test` shows the right orientation (and whether you needed `--mirror` / `--flip`),
- a short video or GIF if you can. These make the README shine.

## Code

- Glowback is intentionally **one file with zero dependencies** (`glowback.py`, Python 3.9+, ctypes only). Keep it that way unless there is a strong reason.
- Run `python glowback.py --list` and `python glowback.py --test` on real hardware before opening a PR.
- Keep device-specific hacks out: device behaviour should come from the HID LampArray descriptor.
- Roadmap items in the README are great first contributions.
