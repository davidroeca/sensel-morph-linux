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

Add your user to the `dialout` group so the Morph's `/dev/ttyACM*` node is
readable:

```sh
sudo usermod -aG dialout $USER
```

For the tablet bridge, add your user to the `input` group so `/dev/uinput` is
writable:

```sh
sudo usermod -aG input $USER
```

Log out and back in (or run `newgrp dialout` / `newgrp input`) for the group
changes to take effect.

## Tools

- `morph-info` — print device info.
- `morph-monitor` — live terminal view of contacts.
- `morph-visualizer` — pygame visualization of contacts.
- `morph-tablet` — uinput tablet bridge (pen or multi-touch).
- `morph-midi` — virtual MIDI port driven by touch, via YAML profiles.
- `morph-config` — read/write on-device overlay configuration.
