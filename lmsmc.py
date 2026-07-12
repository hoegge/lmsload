#!/usr/bin/env python3
"""
LM Studio Model Switcher Console (lmsmc)

A terminal UI to browse, load, and unload models from a local LM Studio server.

Controls:
  Up/Down / k/j   Scroll model list
  Enter           Load the selected model
  /               Live search models
  s               Toggle sort (name/size)
  u               Unload the current model
  q / Esc         Quit
"""

import argparse
import curses
import time
import urllib.request
import urllib.error
import json


DEFAULT_HOST = "http://localhost:1234"


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


def format_status(loaded_id):
    """Format loaded model status line."""
    if not loaded_id:
        return "No model loaded"
    return f"Loaded: {loaded_id}"


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
    return model.get("display_name") or model.get("key", "unknown")


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


def main(stdscr, host):
    curses.curs_set(0)
    stdscr.nodelay(False)

    height, width = stdscr.getmaxyx()

    header = " LM Studio Model Switcher "
    help_line = "[/] Search  [s] Sort  [Up/Down] Scroll  [Enter] Load  [u] Unload  [q/Esc] Quit"

    models = []
    selected = 0
    search_mode = False
    search_query = ""
    sort_mode_index = DEFAULT_SORT_INDEX
    status_msg = ""
    status_time = 0
    loaded_instance_ids = set()
    loading = False

    def get_filtered_models():
        """Return (filtered_list, count) based on current search query and sort mode."""
        filtered = list(models)
        if search_query:
            q = search_query.casefold()
            filtered = [m for m in filtered if q in format_model_name(m).casefold() or q in m.get("key", "").casefold()]
        key_fn, sort_key = SORT_MODES[sort_mode_index]
        if len(filtered) > 1 and sort_key is not None:
            reverse = sort_mode_index == 2  # size index is 2: descending (largest first)
            filtered.sort(key=sort_key, reverse=reverse)
        return filtered, len(filtered)

    def cycle_sort():
        """Cycle to next sort mode and show status."""
        nonlocal sort_mode_index, status_msg, status_time
        sort_mode_index = (sort_mode_index + 1) % len(SORT_MODES)
        name_fn, _ = SORT_MODES[sort_mode_index]
        direction = "largest first" if name_fn == "size" else ""
        status_msg = f"Sort: {name_fn} ({direction})" if direction else f"Sort: {name_fn}"
        status_time = time.time()

    def draw():
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addnstr(0, 0, header.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Loaded model status
        status = format_loaded_status(loaded_instance_ids, models)
        stdscr.attron(curses.color_pair(2))
        stdscr.addnstr(1, 0, f" {status}", w - 1)
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
            filtered, count = get_filtered_models()
            label = f" Models ({count}): "
            if search_mode:
                label += f"[{search_query}] "
            sort_name_fn, _ = SORT_MODES[sort_mode_index]
            label += f"[{sort_name_fn}]"
            stdscr.addnstr(list_start - 1, 0, label, w - 1)

            # Calculate visible window
            if filtered:
                if selected < list_start:
                    offset = 0
                elif selected >= list_start + list_height:
                    offset = selected - list_height + 1
                else:
                    offset = selected - list_start

                for i in range(list_height):
                    idx = offset + i
                    if idx >= len(filtered):
                        break
                    row = list_start + i
                    name = format_model_name(filtered[idx])
                    size = format_size(filtered[idx])
                    is_loaded = is_model_loaded(filtered[idx], loaded_instance_ids)

                    # Build full line: prefix, name, size, capabilities
                    prefix = ">" if idx == selected else ("*" if is_loaded else "  ")
                    left_text = f"{prefix} {name}  {size}"

                    caps = format_capabilities(filtered[idx])
                    cap_strs = [f" {cap[0]}" for cap in caps]
                    full_line = left_text + "".join(cap_strs)

                    # Draw the whole line normally first
                    stdscr.addnstr(row, 1, full_line.strip()[:w-3], w - 3)

                    # Overlay highlight on name/size portion for selected/loading
                    if idx == selected:
                        stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                        try:
                            stdscr.addnstr(row, 1, left_text.strip()[:w-3], w - 3)
                        except curses.error:
                            pass
                        stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
                    elif is_loaded:
                        stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                        try:
                            stdscr.addnstr(row, 1, left_text.strip()[:w-3], w - 3)
                        except curses.error:
                            pass
                        stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)

                    # Overlay capability labels with their own colors
                    cap_start = len(left_text) + 1
                    for ci, (cap_label, color_pair) in enumerate(caps):
                        col = cap_start + ci * (len(cap_label) + 1)
                        if col < w - 3:
                            stdscr.attron(curses.color_pair(color_pair) | curses.A_BOLD)
                            try:
                                label_str = f" {cap_label}"
                                stdscr.addnstr(row, col + 1, label_str[:w-col-2], w - col - 2)
                            except curses.error:
                                pass
                            stdscr.attroff(curses.color_pair(color_pair) | curses.A_BOLD)


        # Status message or help line at bottom
        if status_msg and (time.time() - status_time < 3):
            stdscr.attron(curses.color_pair(4))
            stdscr.addnstr(h - 1, 0, f" {status_msg}", w - 1)
            stdscr.attroff(curses.color_pair(4))
        elif search_mode:
            prompt = f" /{search_query} "
            if len(prompt) > w - 2:
                prompt = "/" + search_query[-(w-4):]
            stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addnstr(h - 1, 0, prompt.center(w), w - 1)
            stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
        else:
            stdscr.attron(curses.color_pair(1))
            stdscr.addnstr(h - 1, 0, help_line.center(w), w - 1)
            stdscr.attroff(curses.color_pair(1))

        stdscr.refresh()

    def refresh_state():
        nonlocal models, loaded_instance_ids, status_msg, status_time
        try:
            models, loaded_instance_ids = fetch_models(host)
        except ConnectionError as e:
            status_msg = f"Error: {e}"
            status_time = time.time()
            models = []

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
    draw()

    while True:
        stdscr.timeout(500)
        ch = stdscr.getch()

        if search_mode:
            if ch in (10, 13):
                if models and not loading:
                    filtered, _ = get_filtered_models()
                    if filtered:
                        selected = max(0, min(selected, len(filtered) - 1))
                        target = filtered[selected]
                        model_key = target.get("key", target.get("id", "unknown"))
                        model_name = format_model_name(target)
                        search_mode = False
                        search_query = ""
                        loading = True
                        status_msg = f"Loading {model_name}..."
                        status_time = time.time()
                        draw()
                        try:
                            load_model(host, model_key)
                            loaded_instance_ids.add(model_key)
                            status_msg = f"Loaded {model_name}"
                        except ConnectionError as e:
                            status_msg = f"Load failed: {e}"
                        finally:
                            loading = False
                            status_time = time.time()
            elif ch == 27:
                search_mode = False
                search_query = ""
                selected = 0
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]
                    selected = 0
            elif ch == curses.KEY_UP or ch == ord("k"):
                filtered, _ = get_filtered_models()
                if filtered and len(filtered) > 1:
                    selected = max(0, selected - 1)
            elif ch == curses.KEY_DOWN or ch == ord("j"):
                filtered, _ = get_filtered_models()
                if filtered and len(filtered) > 1:
                    selected = min(len(filtered) - 1, selected + 1)
            elif 32 <= ch < 127:
                search_query += chr(ch)
                selected = 0

        elif ch == ord("q"):
            break
        elif ch in (curses.KEY_UP, ord("k")):
            if models:
                filtered, _ = get_filtered_models()
                if filtered:
                    selected = max(0, selected - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            if models:
                filtered, _ = get_filtered_models()
                if filtered:
                    selected = min(len(filtered) - 1, selected + 1)
        elif ch == curses.KEY_RESIZE:
            pass
        elif ch == ord("/"):
            search_mode = True
            search_query = ""
        elif ch == ord("s"):
            cycle_sort()
            draw()
        elif ch == 10 or ch == 13:
            if models and not loading:
                target = models[selected]
                model_key = target.get("key", target.get("id", "unknown"))
                model_name = format_model_name(target)
                loading = True
                status_msg = f"Loading {model_name}..."
                status_time = time.time()
                draw()
                try:
                    load_model(host, model_key)
                    loaded_instance_ids.add(model_key)
                    status_msg = f"Loaded {model_name}"
                except ConnectionError as e:
                    status_msg = f"Load failed: {e}"
                finally:
                    loading = False
                    status_time = time.time()
        elif ch == ord("u"):
            if not loading and loaded_instance_ids:
                loading = True
                status_msg = "Unloading model..."
                status_time = time.time()
                draw()
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
        else:
            pass

        refresh_state()
        draw()


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
