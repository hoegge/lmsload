#!/usr/bin/env python3
"""
LM Studio Model Switcher Console (lmsmc)

A terminal UI to browse, load, and unload models from a local LM Studio server.

Controls:
  Up/Down / k/j   Scroll model list
  Enter           Load the selected model
  /               Live search models
  s               Toggle sort (name/size)
  o               Server options (switch/add/delete servers)
  u               Unload the current model
  q / Esc         Quit

Server settings stored in ~/.config/lmsmc/config.yaml
"""

import argparse
import curses
import os
import time
import urllib.request
import urllib.error
import json
import yaml

from pathlib import Path


DEFAULT_HOST = "http://localhost:1234"
CONFIG_DIR = Path.home() / ".config" / "lmsmc"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def api_get(base_url, path, timeout=5):
    """GET request to the LM Studio API."""
    url = f"{base_url}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise ConnectionError(f"Cannot reach {url}: {e.reason}")


def api_post(base_url, path, body=None, timeout=30):
    """POST request to the LM Studio API."""
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            raise ConnectionError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Cannot reach {url}: {e.reason}")


SORT_MODES = [
    ("unsorted", None),
    ("name", lambda m: format_model_name(m).casefold()),
    ("size", lambda m: m.get("size_bytes") or 0),
]

DEFAULT_SORT_INDEX = 0


def fetch_models(base_url):
    """Return (model_list, loaded_instance_ids) from the v1 API."""
    data = api_get(base_url, "/api/v1/models")
    models = data.get("models", [])
    loaded_ids = set()
    for m in models:
        for inst in m.get("loaded_instances", []):
            loaded_ids.add(inst.get("id"))
    return models, loaded_ids


def load_model(base_url, model_id):
    """Load a model by ID."""
    return api_post(base_url, "/api/v1/models/load", {"model": model_id})


def unload_model(base_url, instance_id):
    """Unload a model by instance ID."""
    return api_post(base_url, "/api/v1/models/unload", {"instance_id": instance_id})


def format_model_name(model):
    """Extract a readable name from a model dict (v1 API)."""
    display = model.get("display_name") or model.get("key", "unknown")
    key = model.get("key")
    if key and key != display:
        return f"{display} ({key})"
    return display


def is_model_loaded(model, instance_ids):
    """Check if a model has any loaded instances."""
    for inst in model.get("loaded_instances", []):
        if inst.get("id") in instance_ids:
            return True
    return False


def format_capabilities(model):
    """Extract and format capability labels (vision, tool_use)."""
    caps = model.get("capabilities", {}) or {}
    vision = caps.get("vision", False)
    tools = caps.get("trained_for_tool_use", False)
    parts = []
    if vision:
        parts.append(("Vision", 7))   # pair 7 = yellow for vision
    if tools:
        parts.append(("Tools", 8))    # pair 8 = magenta for tools
    return parts


def format_loaded_status(instance_ids, models):
    """Format loaded model status line showing all loaded instances."""
    if not instance_ids:
        return "No model loaded"
    names = []
    for inst_id in sorted(instance_ids):
        for m in models:
            for inst in m.get("loaded_instances", []):
                if inst.get("id") == inst_id:
                    names.append(m.get("display_name") or m.get("key", "unknown"))
                    break
    return f"Loaded: {', '.join(names)}"


def format_size(model):

    """Format model size in GB with one decimal place."""
    size_bytes = model.get("size_bytes")
    if not size_bytes:
        return ""
    gb = size_bytes / (1024 ** 3)
    return f"[{gb:.1f}GB]"


def load_config():
    """Load server list from config file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    return {"servers": [DEFAULT_HOST], "current_index": 0}


def save_config(cfg):
    """Save server list to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)


def get_current_server(cfg):
    """Return the currently selected server URL."""
    idx = cfg.get("current_index", 0)
    servers = cfg.get("servers", [DEFAULT_HOST])
    if not servers:
        return DEFAULT_HOST
    return servers[min(idx, len(servers) - 1)]


def server_options_screen(stdscr, cfg):
    """Show server options screen: list servers, select, add new."""
    servers = cfg.get("servers", [DEFAULT_HOST])
    current_idx = cfg.get("current_index", 0)
    selected = current_idx
    status_msg = ""

    def draw():
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        header = " Server Options "
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addnstr(0, 0, header.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        help_line = "[Up/Down] Select  [Enter] Use server  [a] Add  [d] Delete  [q] Back"
        stdscr.attron(curses.color_pair(1))
        stdscr.addnstr(h - 1, 0, help_line.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1))

        if status_msg:
            stdscr.attron(curses.color_pair(4))
            stdscr.addnstr(h - 2, 0, f" {status_msg}", w - 1)
            stdscr.attroff(curses.color_pair(4))

        list_start = 2
        list_height = h - list_start - 2
        if status_msg:
            list_height -= 1

        if list_height > 0:
            stdscr.addnstr(list_start - 1, 0, f" Servers ({len(servers)}):", w - 1)
            for i in range(list_height):
                if i >= len(servers):
                    break
                row = list_start + i
                prefix = ">" if i == selected else " "
                marker = " *" if i == current_idx else ""
                line = f"{prefix} {servers[i]}{marker}"
                if i == selected:
                    stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                stdscr.addnstr(row, 1, line[:w - 3], w - 3)
                if i == selected:
                    stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)

        stdscr.refresh()

    def add_server():
        nonlocal status_msg
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        header = " Add Server "
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addnstr(0, 0, header.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        prompt = " Address (e.g. 192.168.1.1): "
        stdscr.addnstr(2, 1, prompt, w - 3)

        port_prompt = " Port (default 1234): "
        stdscr.addnstr(3, 1, port_prompt, w - 3)

        help_line = "[Enter] Confirm  [Esc] Cancel"
        stdscr.attron(curses.color_pair(1))
        stdscr.addnstr(h - 1, 0, help_line.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1))

        stdscr.refresh()

        address = ""
        port = ""
        field = 0  # 0=address, 1=port

        stdscr.nodelay(False)

        while True:
            # Redraw input fields
            row = 2 if field == 0 else 3
            col = len(prompt) if field == 0 else len(port_prompt)
            current_text = address if field == 0 else port
            stdscr.addnstr(row, col, current_text, w - col - 1)
            stdscr.move(row, col + len(current_text))
            stdscr.refresh()

            ch = stdscr.getch()

            if ch == 27:
                return
            elif ch in (10, 13):
                if field == 0:
                    field = 1
                else:
                    addr = address.strip()
                    prt = port.strip() or "1234"
                    if addr:
                        url = f"http://{addr}:{prt}"
                        if url not in servers:
                            servers.append(url)
                            cfg["current_index"] = len(servers) - 1
                            status_msg = f"Added {url}"
                        else:
                            status_msg = "Server already in list"
                    else:
                        status_msg = "Address required"
                    return
            elif ch in (9, curses.KEY_DOWN):
                if field == 0:
                    field = 1
            elif ch == curses.KEY_UP:
                field = 0
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if field == 0:
                    address = address[:-1]
                else:
                    port = port[:-1]
            elif 32 <= ch < 127:
                if field == 0:
                    address += chr(ch)
                else:
                    port += chr(ch)

    draw()

    while True:
        stdscr.timeout(200)
        ch = stdscr.getch()

        if ch == ord("q") or ch == 27:
            cfg["current_index"] = current_idx
            save_config(cfg)
            return
        elif ch == ord("a"):
            add_server()
            draw()
        elif ch == ord("d"):
            if len(servers) > 1 and selected < len(servers):
                removed = servers.pop(selected)
                if selected >= len(servers):
                    selected = len(servers) - 1
                if current_idx >= len(servers):
                    current_idx = len(servers) - 1
                elif current_idx > selected:
                    current_idx -= 1
                cfg["current_index"] = current_idx
                status_msg = f"Removed {removed}"
            elif len(servers) <= 1:
                status_msg = "Cannot remove last server"
            draw()
        elif ch == curses.KEY_UP:
            if servers:
                selected = max(0, selected - 1)
                draw()
        elif ch == curses.KEY_DOWN:
            if servers:
                selected = min(len(servers) - 1, selected + 1)
                draw()
        elif ch in (10, 13):
            if servers and selected < len(servers):
                current_idx = selected
                cfg["current_index"] = current_idx
                save_config(cfg)
                return


def main(stdscr, host):
    curses.curs_set(0)
    stdscr.nodelay(False)
    try:
        curses.set_escdelay(25)  # make a bare Esc register quickly
    except AttributeError:  # Python < 3.9
        pass

    help_line = "[/] Search  [s] Sort  [o] Servers  [Up/Down] Scroll  [Enter] Load  [u] Unload  [q/Esc] Quit"

    models = []
    selected = 0
    scroll_offset = 0
    search_mode = False
    search_query = ""
    sort_mode_index = DEFAULT_SORT_INDEX
    status_msg = ""
    status_time = 0
    loaded_instance_ids = set()
    loading = False

    # Load server config
    cfg = load_config()
    current_host = get_current_server(cfg)
    if host == DEFAULT_HOST:
        host = current_host

    def get_filtered():
        """Return filtered/sorted model list."""
        filtered = list(models)
        if search_query:
            q = search_query.casefold()
            filtered = [m for m in filtered if q in format_model_name(m).casefold() or q in m.get("key", "").casefold()]
        _, sort_key = SORT_MODES[sort_mode_index]
        if len(filtered) > 1 and sort_key is not None:
            filtered.sort(key=sort_key, reverse=sort_mode_index == 2)
        return filtered

    def refresh_state():
        nonlocal models, loaded_instance_ids, status_msg, status_time
        try:
            models, loaded_instance_ids = fetch_models(host)
        except ConnectionError as e:
            status_msg = f"Error: {e}"
            status_time = time.time()
            models = []

    def draw(filtered):
        nonlocal scroll_offset
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addnstr(0, 0, f" Server: {host} ", w - 1)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Loaded model status
        stdscr.attron(curses.color_pair(2))
        stdscr.addnstr(1, 0, f" {format_loaded_status(loaded_instance_ids, models)}", w - 1)
        stdscr.attroff(curses.color_pair(2))

        # Loading indicator
        loading_row = 2
        if loading:
            stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
            stdscr.addnstr(loading_row, 0, " Loading... please wait. ", w - 1)
            stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)

        # Model list
        list_start = loading_row + 1
        list_height = h - list_start - 2

        if list_height > 0 and not loading:
            sort_name_fn, _ = SORT_MODES[sort_mode_index]
            label = f" Models ({len(filtered)}): [{sort_name_fn}]"
            if search_mode:
                label += f" [/{search_query}]"
            stdscr.addnstr(list_start - 1, 0, label, w - 1)

            if filtered:
                # Keep the selected row inside the visible window
                if selected < scroll_offset:
                    scroll_offset = selected
                elif selected >= scroll_offset + list_height:
                    scroll_offset = selected - list_height + 1
                scroll_offset = max(0, min(scroll_offset, len(filtered) - 1))

                for i in range(list_height):
                    row = list_start + i
                    idx = scroll_offset + i
                    if row >= h - 1 or idx >= len(filtered):
                        break
                    m = filtered[idx]
                    name = format_model_name(m)
                    size = format_size(m)
                    is_loaded = is_model_loaded(m, loaded_instance_ids)
                    prefix = ">" if idx == selected else ("*" if is_loaded else " ")
                    line = f"{prefix} {name}  {size}"

                    if idx == selected:
                        stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                    elif is_loaded:
                        stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                    stdscr.addnstr(row, 1, line, w - 3)
                    if idx == selected or is_loaded:
                        stdscr.attroff(curses.color_pair(5 if idx == selected else 6) | curses.A_BOLD)

                    # Capability badges
                    caps = format_capabilities(m)
                    col = len(line) + 1
                    for cap_label, cp in caps:
                        if col < w - 2:
                            stdscr.attron(curses.color_pair(cp) | curses.A_BOLD)
                            stdscr.addnstr(row, col, f" {cap_label}", w - col)
                            stdscr.attroff(curses.color_pair(cp) | curses.A_BOLD)
                        col += len(cap_label) + 2

        # Status / help line
        if status_msg and (time.time() - status_time < 3):
            stdscr.attron(curses.color_pair(4))
            stdscr.addnstr(h - 1, 0, f" {status_msg}", w - 1)
            stdscr.attroff(curses.color_pair(4))
        elif search_mode:
            prompt = f" /{search_query} "
            stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addnstr(h - 1, 0, prompt.center(w), w - 1)
            stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
        else:
            stdscr.attron(curses.color_pair(1))
            stdscr.addnstr(h - 1, 0, help_line.center(w), w - 1)
            stdscr.attroff(curses.color_pair(1))

        stdscr.refresh()

    def do_load(target):
        """Load a model, showing progress, then refresh state from the server."""
        nonlocal loading, status_msg, status_time
        model_key = target.get("key", target.get("id", "unknown"))
        model_name = format_model_name(target)
        loading = True
        status_msg = f"Loading {model_name}..."
        status_time = time.time()
        draw(get_filtered())
        try:
            load_model(host, model_key)
            status_msg = f"Loaded {model_name}"
        except ConnectionError as e:
            status_msg = f"Load failed: {e}"
        finally:
            loading = False
            status_time = time.time()
        refresh_state()

    # Initialize colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(6, curses.COLOR_GREEN, -1)
    curses.init_pair(7, curses.COLOR_YELLOW, -1)
    curses.init_pair(8, curses.COLOR_MAGENTA, -1)

    refresh_state()
    last_refresh = time.time()

    while True:
        filtered = get_filtered()
        if filtered:
            selected = max(0, min(selected, len(filtered) - 1))

        draw(filtered)

        stdscr.timeout(500)
        ch = stdscr.getch()

        if ch == -1:
            # Idle tick: periodically pick up load/unload changes from the server
            if time.time() - last_refresh > 5:
                refresh_state()
                last_refresh = time.time()
            continue

        if search_mode:
            if ch in (10, 13):
                if filtered and not loading:
                    target = filtered[selected]
                    search_mode = False
                    search_query = ""
                    selected = 0
                    do_load(target)
            elif ch == 27:
                search_mode = False
                search_query = ""
                selected = 0
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                search_query = search_query[:-1]
                selected = 0
            elif ch == curses.KEY_UP or ch == ord("k"):
                selected = max(0, selected - 1)
            elif ch == curses.KEY_DOWN or ch == ord("j"):
                selected = min(len(filtered) - 1, selected + 1)
            elif 32 <= ch < 127:
                search_query += chr(ch)
                selected = 0

        elif ch == ord("q") or ch == 27:
            break
        elif ch == curses.KEY_UP or ch == ord("k"):
            selected = max(0, selected - 1)
        elif ch == curses.KEY_DOWN or ch == ord("j"):
            selected = min(len(filtered) - 1, selected + 1)
        elif ch == ord("/"):
            search_mode = True
            search_query = ""
        elif ch == ord("s"):
            sort_mode_index = (sort_mode_index + 1) % len(SORT_MODES)
            name_fn, _ = SORT_MODES[sort_mode_index]
            direction = "largest first" if name_fn == "size" else ""
            status_msg = f"Sort: {name_fn} ({direction})" if direction else f"Sort: {name_fn}"
            status_time = time.time()
        elif ch == ord("o"):
            server_options_screen(stdscr, cfg)
            new_host = get_current_server(cfg)
            if new_host != host:
                host = new_host
                selected = 0
                refresh_state()
        elif ch in (10, 13):
            if filtered and not loading:
                do_load(filtered[selected])
        elif ch == ord("u"):
            if not loading and loaded_instance_ids:
                loading = True
                status_msg = "Unloading model..."
                status_time = time.time()
                draw(filtered)
                try:
                    instance_id = next(iter(loaded_instance_ids))
                    unload_model(host, instance_id)
                    loaded_instance_ids.discard(instance_id)
                    status_msg = "Model unloaded"
                except ConnectionError as e:
                    status_msg = f"Unload failed: {e}"
                finally:
                    loading = False
                    status_time = time.time()
                refresh_state()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LM Studio Model Switcher Console")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"LM Studio server URL (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print API responses to stdout before launching TUI",
    )
    args = parser.parse_args()

    if args.debug:
        try:
            models, loaded_id = fetch_models(args.host)
            print(f"Models API returned {len(models)} models:")
            for m in models:
                print(f"  {m}")
            print(f"Loaded model: {loaded_id!r}")
        except Exception as e:
            print(f"Debug error: {e}")

    curses.wrapper(main, args.host)
