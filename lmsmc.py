#!/usr/bin/env python3
"""
LM Studio Model Switcher Console (lmsmc)

A terminal UI to browse, load, and unload models from a local LM Studio server.

Controls:
  Up/Down / k/j   Scroll model list
  Enter           Load the selected model
  Ctrl+U          Unload the current model
  q / Esc         Quit
"""

import argparse
import curses
import sys
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


def fetch_models(base_url):
    """Return list of model dicts from the server."""
    data = api_get(base_url, "/v1/models")
    models = data.get("data", [])
    return models


def fetch_loaded_model(base_url):
    """Return the currently loaded model info, or None."""
    try:
        data = api_get(base_url, "/v1/models/load")
        return data
    except ConnectionError:
        return None


def load_model(base_url, model_id):
    """Load a model by ID."""
    return api_post(base_url, "/v1/models/load", {"model": model_id})


def unload_model(base_url):
    """Unload the currently loaded model."""
    return api_post(base_url, "/v1/models/unload")


def format_model_name(model):
    """Extract a readable name from a model dict."""
    return model.get("id", model.get("object", "unknown"))


def format_status(model_info):
    """Format loaded model status line."""
    if not model_info:
        return "No model loaded"
    name = model_info.get("model", model_info.get("id", "unknown"))
    return f"Loaded: {name}"


def main(stdscr, host):
    curses.curs_set(0)
    stdscr.nodelay(False)

    height, width = stdscr.getmaxyx()

    header = " LM Studio Model Switcher "
    help_line = "[Up/Down] Scroll  [Enter] Load  [Ctrl+U] Unload  [q/Esc] Quit"

    models = []
    selected = 0
    status_msg = ""
    status_time = 0
    loaded_model = None
    loading = False
    last_refresh = 0

    def draw():
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addnstr(0, 0, header.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Loaded model status
        status = format_status(loaded_model)
        stdscr.attron(curses.color_pair(2))
        stdscr.addnstr(1, 0, f" {status}", w - 1)
        stdscr.attroff(curses.color_pair(2))

        # Loading indicator
        if loading:
            stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
            stdscr.addnstr(2, 0, " Loading... please wait. ", w - 1)
            stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)

        # Temporary status message (fade after 3s)
        if status_msg and (time.time() - status_time < 3):
            y = 3 if loading else 2
            stdscr.attron(curses.color_pair(4))
            stdscr.addnstr(y, 0, f" {status_msg}", w - 1)
            stdscr.attroff(curses.color_pair(4))

        # Model list
        list_start = 3 if (loading or status_msg and (time.time() - status_time < 3)) else 2
        list_height = h - list_start - 2

        if list_height > 0:
            stdscr.addnstr(list_start - 1, 0, f" Models ({len(models)}): ", w - 1)

            # Calculate visible window
            if models:
                if selected < list_start:
                    offset = 0
                elif selected >= list_start + list_height:
                    offset = selected - list_height + 1
                else:
                    offset = selected - list_start

                for i in range(list_height):
                    idx = offset + i
                    if idx >= len(models):
                        break
                    row = list_start + i
                    name = format_model_name(models[idx])
                    if idx == selected:
                        stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                        stdscr.addnstr(row, 1, f"> {name}", w - 3)
                        stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
                    else:
                        stdscr.addnstr(row, 1, f"  {name}", w - 3)

        # Help line
        stdscr.attron(curses.color_pair(1))
        stdscr.addnstr(h - 1, 0, help_line.center(w), w - 1)
        stdscr.attroff(curses.color_pair(1))

        stdscr.refresh()

    def refresh_state():
        nonlocal models, loaded_model
        try:
            models = fetch_models(host)
        except ConnectionError as e:
            status_msg = f"Error: {e}"
            status_time = time.time()
            models = []
        try:
            loaded_model = fetch_loaded_model(host)
        except ConnectionError:
            loaded_model = None

    # Initialize colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)

    refresh_state()
    draw()

    while True:
        stdscr.timeout(500)
        ch = stdscr.getch()

        if ch in (ord("q"), 27):
            break
        elif ch in (curses.KEY_UP, ord("k")):
            if models:
                selected = max(0, selected - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            if models:
                selected = min(len(models) - 1, selected + 1)
        elif ch == curses.KEY_RESIZE:
            pass
        elif ch == 10 or ch == 13:
            if models and not loading:
                target = models[selected]
                model_id = format_model_name(target)
                loading = True
                status_msg = f"Loading {model_id}..."
                status_time = time.time()
                draw()
                try:
                    load_model(host, model_id)
                    loaded_model = {"model": model_id}
                    status_msg = f"Loaded {model_id}"
                except ConnectionError as e:
                    status_msg = f"Load failed: {e}"
                finally:
                    loading = False
                    status_time = time.time()
        elif ch == 21:
            if not loading:
                loading = True
                status_msg = "Unloading model..."
                status_time = time.time()
                draw()
                try:
                    unload_model(host)
                    loaded_model = None
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
    args = parser.parse_args()
    curses.wrapper(main, args.host)
