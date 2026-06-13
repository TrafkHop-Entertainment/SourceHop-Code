#!/usr/bin/env python3
"""TrafkHop Volume + Media Popup  —  gtk-layer-shell edition
Tabs: Ausgabe-Gerät | Lautstärke + Media | App-Lautstärken
"""

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

from gi.repository import Gtk, Gdk, GLib
import subprocess, re, os, cairo

# ── Paths ─────────────────────────────────────────────────────────────────────
ROFI_DIR      = os.path.expanduser("~/.config/rofi")
BUBBLE_URI    = f"file://{ROFI_DIR}/TrafkBubble.png"
BUBBLE_LT_URI = f"file://{ROFI_DIR}/TrafkBubble_lighter.png"
WAYBAR_OFFSET = 55

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = f"""
* {{ background-color: transparent; border: none; outline: none; }}
window {{ background-color: transparent; }}

.bubble {{
    background-color: transparent;
    padding: 0;
    margin: 0;
}}
.tile {{
    background-image: url("{BUBBLE_URI}");
    background-size: 100% 100%;
    padding: 8px 12px;
    margin: 4px 0;
}}
.tile-small {{
    background-image: url("{BUBBLE_URI}");
    background-size: 100% 100%;
    padding: 4px 8px;
    margin: 2px;
}}
button {{
    background-image: none;
    background-color: transparent;
    color: #fff495;
    border-radius: 10px;
    padding: 6px 14px;
    font-family: "Noto Sans Serif";
    font-size: 12px;
    font-weight: bold;
    min-height: 32px;
}}
button.tile {{
    background-image: url("{BUBBLE_URI}");
    background-size: 100% 100%;
}}
button:hover {{
    background-image: url("{BUBBLE_LT_URI}");
    background-size: 100% 100%;
    color: #ffffff;
}}
.btn-mute  {{ font-size: 11px; padding: 4px 12px; min-height: 28px; }}
.btn-mute.tile {{ padding: 4px 12px; }}
.btn-ctrl  {{ font-size: 20px; min-width: 48px; min-height: 48px; padding: 4px; }}
.btn-ctrl.tile {{ padding: 4px; }}
.btn-active {{ color: #8456dd; }}
.btn-active:hover {{ color: #ffffff; }}

/* Tab bar */
.tab-bar {{
    background-color: transparent;
    margin: 0 6px 0 6px;
}}
.tab-btn {{
    font-size: 11px;
    padding: 4px 10px;
    min-height: 26px;
    border-radius: 8px 8px 0 0;
    color: #cdc477;
    background-color: transparent;
    background-image: none;
}}
.tab-btn:hover {{
    color: #fff495;
    background-color: rgba(132,86,221,0.2);
    background-image: none;
}}
.tab-btn.active {{
    color: #fff495;
    background-image: url("{BUBBLE_URI}");
    background-size: 100% 100%;
}}

/* Sink row */
.sink-row {{
    background-image: url("{BUBBLE_URI}");
    background-size: 100% 100%;
    padding: 6px 10px;
    margin: 2px 0;
    border-radius: 10px;
}}
.sink-row.active-sink {{
    background-image: url("{BUBBLE_LT_URI}");
    background-size: 100% 100%;
}}

label {{
    color: #fff495;
    font-family: "Noto Sans Serif", "JetBrainsMono Nerd Font";
    font-weight: bold;
    background-color: transparent;
}}
.lbl-title   {{ font-size: 14px; color: #fff495; }}
.lbl-val     {{ font-size: 20px; color: #fff495; min-width: 62px; }}
.lbl-sub     {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-track   {{ font-size: 13px; color: #fff495; }}
.lbl-artist  {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-appname {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-appvol  {{ font-size: 11px; color: #fff495; min-width: 40px; }}
.lbl-sink-name {{ font-size: 12px; color: #fff495; }}
.lbl-sink-desc {{ font-size: 10px; color: #cdc477; font-weight: normal; }}

scale trough    {{ background-color: rgba(58,42,106,0.85); border-radius: 8px; min-height: 8px; }}
scale highlight {{ background-color: #fff495; border-radius: 8px; }}
scale slider    {{
    background-color: #ffffff;
    border-radius: 50%;
    min-width: 16px; min-height: 16px;
    border: 2px solid #8456dd;
    background-image: none;
}}
"""

# ── PulseAudio helpers ────────────────────────────────────────────────────────
def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""

def get_sinks():
    """Returns list of dicts: {index, name, description, active}"""
    out = run("pactl list sinks")
    sinks = []
    current = {}
    default = run("pactl get-default-sink").strip()
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^Sink #(\d+)", line)
        if m:
            if current:
                sinks.append(current)
            current = {"index": m.group(1), "name": "", "description": "", "active": False}
        elif line.startswith("Name:"):
            name = line.split(":", 1)[1].strip()
            current["name"] = name
            current["active"] = (name == default)
        elif line.startswith("Description:"):
            current["description"] = line.split(":", 1)[1].strip()
    if current:
        sinks.append(current)
    return sinks

def set_default_sink(name):
    run(f"pactl set-default-sink '{name}'")
    # Move all existing streams to new sink
    out = run("pactl list sink-inputs short")
    for line in out.splitlines():
        idx = line.split()[0]
        run(f"pactl move-sink-input {idx} '{name}'")

def get_volume():
    m = re.search(r"(\d+)%", run("pactl get-sink-volume @DEFAULT_SINK@"))
    return int(m.group(1)) if m else 50

def get_muted():
    return run("pactl get-sink-mute @DEFAULT_SINK@").endswith("yes")

def set_volume(v):
    run(f"pactl set-sink-volume @DEFAULT_SINK@ {max(0, min(150, int(v)))}%")

def toggle_mute():
    run("pactl set-sink-mute @DEFAULT_SINK@ toggle")

def get_sink_inputs():
    """Returns list: {index, name, volume, muted}"""
    out = run("pactl list sink-inputs")
    inputs = []
    current = {}
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^Sink Input #(\d+)", line)
        if m:
            if current.get("index"):
                inputs.append(current)
            current = {"index": m.group(1), "name": "Unbekannt", "volume": 100, "muted": False}
        elif "application.name" in line.lower():
            val = line.split("=", 1)[-1].strip().strip('"')
            current["name"] = val
        elif "application.process.binary" in line.lower() and current.get("name") == "Unbekannt":
            val = line.split("=", 1)[-1].strip().strip('"')
            current["name"] = val
        elif line.startswith("Volume:"):
            m2 = re.search(r"(\d+)%", line)
            if m2:
                current["volume"] = int(m2.group(1))
        elif line.startswith("Mute:"):
            current["muted"] = "yes" in line
    if current.get("index"):
        inputs.append(current)
    return inputs

def set_sink_input_volume(idx, v):
    run(f"pactl set-sink-input-volume {idx} {max(0, min(150, int(v)))}%")

def toggle_sink_input_mute(idx):
    run(f"pactl set-sink-input-mute {idx} toggle")

def playerctl(action):
    run(f"playerctl {action}")

def get_media():
    title  = run("playerctl metadata title 2>/dev/null")
    artist = run("playerctl metadata artist 2>/dev/null")
    status = run("playerctl status 2>/dev/null")
    return title, artist, status

def sink_icon(description):
    d = description.lower()
    if any(k in d for k in ("headphone", "kopfhörer", "headset", "earphone")):
        return "🎧"
    if any(k in d for k in ("hdmi", "displayport", "dp")):
        return "🖥"
    if any(k in d for k in ("usb",)):
        return "🔌"
    if any(k in d for k in ("bluetooth", "bt")):
        return "📶"
    return "🔊"

def app_icon(name):
    n = name.lower()
    if any(k in n for k in ("firefox", "chrome", "chromium", "browser")):
        return "🌐"
    if any(k in n for k in ("spotify", "music", "rhythmbox", "clementine", "vlc", "mpv", "mplayer")):
        return "🎵"
    if any(k in n for k in ("discord", "telegram", "signal", "teams", "zoom", "mumble")):
        return "💬"
    if any(k in n for k in ("steam", "game", "wine", "lutris")):
        return "🎮"
    return "🔉"


# ── Window ────────────────────────────────────────────────────────────────────
class VolumePopup(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.connect("draw", self._clear_bg)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        if HAS_LAYER_SHELL:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT,  True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, WAYBAR_OFFSET)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT,  16)
            try:
                GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
            except AttributeError:
                GtkLayerShell.set_keyboard_interactivity(self, True)
        else:
            self.set_decorated(False)
            self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
            self.set_keep_above(True)
            self.set_skip_taskbar_hint(True)
            self.set_skip_pager_hint(True)

        self.set_size_request(340, -1)
        self.connect("key-press-event",
            lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        self.connect("focus-out-event", self._on_focus_out)

        self._active_tab = 1  # 0=Geräte, 1=System, 2=Apps
        self._tab_btns   = []
        self._pages      = []
        self._vol_timer  = None
        self._app_timers = {}

        self._build()
        self.show_all()
        if not HAS_LAYER_SHELL:
            self._fallback_position()
        GLib.timeout_add(1500, self._refresh_media)

    def _clear_bg(self, _w, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

    def _bubble(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b.get_style_context().add_class("bubble")
        return b

    # ── Shell ─────────────────────────────────────────────────────────────────
    def _build(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(6)
        outer.set_margin_bottom(6)
        outer.set_margin_start(6)
        outer.set_margin_end(6)
        self.add(outer)

        # Tab bar
        tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        tab_bar.get_style_context().add_class("tab-bar")
        outer.pack_start(tab_bar, False, False, 0)

        tabs = [("🔊 Gerät", 0), ("🎚 System", 1), ("📊 Apps", 2)]
        for label, idx in tabs:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("tab-btn")
            if idx == self._active_tab:
                btn.get_style_context().add_class("active")
            btn.connect("clicked", self._switch_tab, idx)
            tab_bar.pack_start(btn, True, True, 0)
            self._tab_btns.append(btn)

        # Page stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)
        outer.pack_start(self._stack, False, False, 0)

        # Build all three pages
        self._page_devices = self._build_page_devices()
        self._page_system  = self._build_page_system()
        self._page_apps    = self._build_page_apps()

        self._stack.add_named(self._page_devices, "devices")
        self._stack.add_named(self._page_system,  "system")
        self._stack.add_named(self._page_apps,    "apps")

        self._stack.set_visible_child_name("system")

    def _switch_tab(self, _btn, idx):
        pages = ["devices", "system", "apps"]
        self._active_tab = idx
        for i, btn in enumerate(self._tab_btns):
            ctx = btn.get_style_context()
            if i == idx:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")
        self._stack.set_visible_child_name(pages[idx])
        # Lazy-refresh apps tab on switch
        if idx == 2:
            self._refresh_apps()
        elif idx == 0:
            self._refresh_devices()

    # ── Tab 0: Ausgabe-Geräte ─────────────────────────────────────────────────
    def _build_page_devices(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._devices_box = self._bubble()
        page.pack_start(self._devices_box, False, False, 0)

        loading = Gtk.Label(label="Lade Geräte…")
        loading.get_style_context().add_class("lbl-sub")
        loading.get_style_context().add_class("tile")
        self._devices_box.pack_start(loading, False, False, 4)

        return page

    def _refresh_devices(self):
        sinks = get_sinks()
        for child in self._devices_box.get_children():
            self._devices_box.remove(child)

        if not sinks:
            lbl = Gtk.Label(label="Keine Audio-Geräte gefunden")
            lbl.get_style_context().add_class("lbl-sub")
            lbl.get_style_context().add_class("tile")
            self._devices_box.pack_start(lbl, False, False, 8)
        else:
            for sink in sinks:
                row = self._make_sink_row(sink)
                self._devices_box.pack_start(row, False, False, 2)

        self._devices_box.show_all()

    def _make_sink_row(self, sink):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class("sink-row")
        if sink["active"]:
            box.get_style_context().add_class("active-sink")

        icon = Gtk.Label(label=sink_icon(sink["description"]))
        icon.set_size_request(24, -1)
        box.pack_start(icon, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.pack_start(info, True, True, 0)

        # Shorten long description
        desc = sink["description"]
        if len(desc) > 38:
            desc = desc[:36] + "…"
        name_lbl = Gtk.Label(label=desc)
        name_lbl.get_style_context().add_class("lbl-sink-name")
        name_lbl.set_halign(Gtk.Align.START)
        info.pack_start(name_lbl, False, False, 0)

        tech_lbl = Gtk.Label(label=sink["name"].split(".")[-1])
        tech_lbl.get_style_context().add_class("lbl-sink-desc")
        tech_lbl.set_halign(Gtk.Align.START)
        info.pack_start(tech_lbl, False, False, 0)

        if sink["active"]:
            badge = Gtk.Label(label="✓ Aktiv")
            badge.get_style_context().add_class("lbl-sub")
            badge.set_halign(Gtk.Align.END)
            box.pack_end(badge, False, False, 0)
        else:
            btn = Gtk.Button(label="Wählen")
            btn.get_style_context().add_class("btn-mute")
            btn.get_style_context().add_class("tile")
            name = sink["name"]
            btn.connect("clicked", lambda _b, n=name: self._select_sink(n))
            box.pack_end(btn, False, False, 0)

        return box

    def _select_sink(self, name):
        set_default_sink(name)
        GLib.timeout_add(300, self._refresh_devices)
        # Also sync system tab volume
        GLib.timeout_add(400, self._sync_vol)

    # ── Tab 1: System-Lautstärke + Media ─────────────────────────────────────
    def _build_page_system(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Volume section
        vol_box = self._bubble()
        page.pack_start(vol_box, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_box.pack_start(row, False, False, 0)

        lbl = Gtk.Label(label="🔊 Lautstärke")
        lbl.get_style_context().add_class("lbl-title")
        lbl.get_style_context().add_class("tile")
        lbl.set_halign(Gtk.Align.START)
        row.pack_start(lbl, True, True, 0)

        self._vol_lbl = Gtk.Label(label=f"{get_volume()}%")
        self._vol_lbl.get_style_context().add_class("lbl-val")
        self._vol_lbl.get_style_context().add_class("tile")
        self._vol_lbl.set_halign(Gtk.Align.END)
        row.pack_end(self._vol_lbl, False, False, 0)

        self._vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        self._vol_scale.set_value(get_volume())
        self._vol_scale.set_draw_value(False)
        self._vol_scale.connect("value-changed", self._on_vol_change)
        vol_box.pack_start(self._vol_scale, False, False, 0)

        # Add tick at 100%
        self._vol_scale.add_mark(100, Gtk.PositionType.BOTTOM, None)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vol_box.pack_start(btn_row, False, False, 0)

        mute = Gtk.Button(label="🔇 Stummschalten")
        mute.get_style_context().add_class("btn-mute")
        mute.get_style_context().add_class("tile")
        mute.connect("clicked", lambda *_: (toggle_mute(), self._sync_vol()))
        btn_row.pack_start(mute, True, True, 0)

        # Media section
        media_box = self._bubble()
        media_box.set_margin_bottom(0)
        page.pack_start(media_box, False, False, 0)

        hdr = Gtk.Label(label="🎵 Wiedergabe")
        hdr.get_style_context().add_class("lbl-title")
        hdr.get_style_context().add_class("tile")
        hdr.set_halign(Gtk.Align.START)
        media_box.pack_start(hdr, False, False, 0)

        self._track_lbl = Gtk.Label(label="—")
        self._track_lbl.get_style_context().add_class("lbl-track")
        self._track_lbl.get_style_context().add_class("tile")
        self._track_lbl.set_halign(Gtk.Align.START)
        self._track_lbl.set_ellipsize(3)
        media_box.pack_start(self._track_lbl, False, False, 0)

        self._artist_lbl = Gtk.Label(label="")
        self._artist_lbl.get_style_context().add_class("lbl-artist")
        self._artist_lbl.get_style_context().add_class("tile")
        self._artist_lbl.set_halign(Gtk.Align.START)
        media_box.pack_start(self._artist_lbl, False, False, 0)

        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ctrl.set_halign(Gtk.Align.CENTER)
        media_box.pack_start(ctrl, False, False, 0)

        for label, action in [("⏮", "previous"), ("▶", None), ("⏭", "next")]:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("btn-ctrl")
            btn.get_style_context().add_class("tile")
            if action:
                btn.connect("clicked", lambda _b, a=action: playerctl(a))
            else:
                self._play_btn = btn
                btn.connect("clicked", self._on_playpause)
            ctrl.pack_start(btn, False, False, 0)

        self._refresh_media()
        return page

    # ── Tab 2: App-Lautstärken ────────────────────────────────────────────────
    def _build_page_apps(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._apps_box = self._bubble()
        self._apps_box.set_margin_bottom(0)
        page.pack_start(self._apps_box, False, False, 0)

        loading = Gtk.Label(label="Lade Apps…")
        loading.get_style_context().add_class("lbl-sub")
        loading.get_style_context().add_class("tile")
        self._apps_box.pack_start(loading, False, False, 4)

        return page

    def _refresh_apps(self):
        inputs = get_sink_inputs()
        for child in self._apps_box.get_children():
            self._apps_box.remove(child)

        if not inputs:
            lbl = Gtk.Label(label="Keine aktiven Audio-Streams")
            lbl.get_style_context().add_class("lbl-sub")
            lbl.get_style_context().add_class("tile")
            self._apps_box.pack_start(lbl, False, False, 8)
        else:
            for inp in inputs:
                row = self._make_app_row(inp)
                self._apps_box.pack_start(row, False, False, 2)

        self._apps_box.show_all()

    def _make_app_row(self, inp):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("tile")
        box.set_margin_top(2)
        box.set_margin_bottom(2)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(top, False, False, 0)

        icon = Gtk.Label(label=app_icon(inp["name"]))
        icon.set_size_request(22, -1)
        top.pack_start(icon, False, False, 0)

        name_lbl = Gtk.Label(label=inp["name"])
        name_lbl.get_style_context().add_class("lbl-appname")
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_ellipsize(3)
        name_lbl.set_size_request(120, -1)
        top.pack_start(name_lbl, True, True, 0)

        # Mute toggle
        muted = inp["muted"]
        mute_btn = Gtk.Button(label="🔇" if muted else "🔊")
        mute_btn.get_style_context().add_class("btn-mute")
        mute_btn.get_style_context().add_class("tile")
        idx = inp["index"]
        mute_btn.connect("clicked", lambda _b, i=idx, b=mute_btn: self._toggle_app_mute(i, b))
        top.pack_end(mute_btn, False, False, 0)

        vol_lbl = Gtk.Label(label=f"{inp['volume']}%")
        vol_lbl.get_style_context().add_class("lbl-appvol")
        vol_lbl.set_halign(Gtk.Align.END)
        top.pack_end(vol_lbl, False, False, 0)

        # Volume slider
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        scale.set_value(inp["volume"])
        scale.set_draw_value(False)
        scale.add_mark(100, Gtk.PositionType.BOTTOM, None)
        scale.connect("value-changed", self._on_app_vol_change, idx, vol_lbl)
        box.pack_start(scale, False, False, 0)

        return box

    def _toggle_app_mute(self, idx, btn):
        toggle_sink_input_mute(idx)
        # Re-read state and update icon
        inputs = get_sink_inputs()
        for inp in inputs:
            if inp["index"] == idx:
                btn.set_label("🔇" if inp["muted"] else "🔊")
                break

    def _on_app_vol_change(self, scale, idx, vol_lbl):
        v = int(scale.get_value())
        vol_lbl.set_text(f"{v}%")
        # Debounce
        if idx in self._app_timers and self._app_timers[idx]:
            GLib.source_remove(self._app_timers[idx])
        self._app_timers[idx] = GLib.timeout_add(80, self._apply_app_vol, idx, v)

    def _apply_app_vol(self, idx, v):
        self._app_timers[idx] = None
        set_sink_input_volume(idx, v)
        return False

    # ── System volume events ──────────────────────────────────────────────────
    def _on_vol_change(self, scale):
        v = int(scale.get_value())
        self._vol_lbl.set_text(f"{v}%")
        if self._vol_timer:
            GLib.source_remove(self._vol_timer)
        self._vol_timer = GLib.timeout_add(60, self._apply_vol, v)

    def _apply_vol(self, v):
        self._vol_timer = None
        set_volume(v)
        return False

    def _sync_vol(self):
        v = get_volume()
        self._vol_scale.handler_block_by_func(self._on_vol_change)
        self._vol_scale.set_value(v)
        self._vol_scale.handler_unblock_by_func(self._on_vol_change)
        self._vol_lbl.set_text(f"{v}%")

    # ── Media events ──────────────────────────────────────────────────────────
    def _on_playpause(self, _btn):
        playerctl("play-pause")
        GLib.timeout_add(200, self._refresh_media)

    def _refresh_media(self):
        title, artist, status = get_media()
        self._track_lbl.set_text(title or "Kein Player aktiv")
        self._artist_lbl.set_text(artist or "")
        self._play_btn.set_label("⏸" if status == "Playing" else "▶")
        return True

    # ── Focus / position ──────────────────────────────────────────────────────
    def _on_focus_out(self, *_):
        GLib.timeout_add(150, self._check_focus)

    def _check_focus(self):
        if not self.has_toplevel_focus():
            Gtk.main_quit()
        return False

    def _fallback_position(self):
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() or display.get_monitor(0)
        if not mon:
            return
        g = mon.get_geometry()
        w, h = self.get_size()
        self.move(g.x + g.width - w - 16, g.y + g.height - h - WAYBAR_OFFSET)


if __name__ == "__main__":
    win = VolumePopup()
    Gtk.main()
