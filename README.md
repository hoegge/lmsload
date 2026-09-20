# lmsload — LM Studio Model Loader

A terminal UI to browse, load, and unload models from a local LM Studio server.

## Requirements

- Python 3.8+
- `pyyaml` (`pip install pyyaml`)
- An LM Studio instance running with the local server enabled (default: `http://localhost:1234`)

## Usage

```bash
python lmsload.py
```

```bash
# Connect to a custom server
python lmsload.py -h 192.168.1.100:1234
```

Use `--help` to display command-line help. `--host` remains available as the
long form of `-h`.

```bash
# Debug mode (print API responses before launching TUI)
python lmsload.py --debug
```

## Build standalone executable

Build a self-contained binary (no Python or PyYAML needed on the target machine) and install it to `~/.local/bin`:

```bash
./build.sh
```

The binary also lands in `dist/lmsload` (~15 MB). Rerun after code changes to rebuild. Requires [uv](https://docs.astral.sh/uv/).

## Controls

| Key              | Action                                       |
|------------------|----------------------------------------------|
| `Up` / `Down`    | Navigate the model list                       |
| `Enter`          | Load the selected model                       |
| Double-click     | Load or unload the clicked model              |
| `/`              | Enter live search mode                        |
| `s`              | Cycle sort mode (unsorted → name → size)      |
| `o`              | Open server options (switch/add/delete)       |
| `u`              | Unload the selected model                     |
| `q` / `Esc`      | Quit                                          |

## Server Options Screen

Press `o` to manage LM Studio server connections:

| Key              | Action                                       |
|------------------|----------------------------------------------|
| `Up` / `Down`    | Select a server                              |
| `Enter`          | Use the selected server and return            |
| `a`              | Add a new server (enter address and port)     |
| `d`              | Delete the selected server                    |
| `q` / `Esc`      | Go back without changing server               |

## Features

- **Model browsing** — lists all models available on the connected LM Studio server
- **Load/unload models** — load a model into memory or unload it to free resources
- **Live search** — filter models by name or key in real time
- **Sorting** — toggle between unsorted, alphabetical, and by size
- **Multi-server support** — manage multiple LM Studio servers and switch between them
- **Mouse support** — click to select, double-click to load/unload
- **Capability indicators** — color-coded badges for vision and tool-use capabilities
- **Auto-refresh** — polls the server every 5 seconds to detect external changes
- **Persistent config** — server list and current selection saved to `~/.config/lmsload/config.yaml`

## Config

Server settings are stored in `~/.config/lmsload/config.yaml`. The program will automatically migrate from the legacy `~/.config/lmsmc/config.yaml` location.
