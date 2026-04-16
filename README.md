# Sensel Morph Linux

A Linux-native Python toolchain for the [Sensel Morph](https://sensel.com/),
built on the vendored MIT `LibSensel` C source. No dependency on Sensel's
(now-defunct) SenselApp or cloud services.

## Setup

```sh
uv sync
uv run python build.py         # compiles lib/sensel-lib/libsensel.so
uv run python tools/morph_info.py
```

## Permissions

Install the udev rules and add your user to the required groups:

```sh
sudo cp udev/99-sensel.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG dialout $USER   # Morph serial device (/dev/ttyACM*)
sudo usermod -aG input $USER     # virtual input device (/dev/uinput) for tablet bridge
```

Log out and back in for the group changes to take effect.

## Tools

- `morph-info` — print device info.
- `morph-monitor` — live terminal view of contacts.
- `morph-visualizer` — pygame visualization of contacts.
- `morph-tablet` — uinput tablet bridge (pen or multi-touch).
- `morph-midi` — virtual MIDI port driven by touch, via YAML profiles.
- `morph-config` — read/write on-device overlay configuration.
