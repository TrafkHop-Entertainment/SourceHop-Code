#!/usr/bin/env python3
"""TrafkHop Bluetooth Popup  —  gtk-layer-shell edition"""

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, re, os, cairo

SCRIPT_DIR    = os.path.dirname(os.path.realpath(__file__))
ROFI_DIR = os.path.expanduser("~/.config/rofi")
BUBBLE_URI    = f"file://{ROFI_DIR}/TrafkBubble.png"
BUBBLE_LT_URI = f"file://{ROFI_DIR}/TrafkBubble_lighter.png"
WAYBAR_OFFSET = 55

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
    padding: 5px 10px;
    font-family: "Noto Sans Serif";
    font-size: 11px;
    font-weight: bold;
    min-height: 28px;
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
.btn-sm {{ padding: 3px 8px; font-size: 10px; min-height: 24px; }}
.btn-sm.tile {{ padding: 2px 6px; }}
.btn-danger       {{ color: #f07a7a; }}
.btn-danger:hover {{ background-image: none; background-color: rgba(90,16,32,0.8); color: #ffffff; }}
.btn-ok           {{ color: #7af0a0; }}
.btn-power-off    {{ color: #f07a7a; }}

list {{ background-color: transparent; }}
row  {{ background-color: transparent; }}
row:hover {{ background-color: rgba(132,86,221,0.2); border-radius: 10px; }}

label {{
    color: #fff495;
    font-family: "Noto Sans Serif", "JetBrainsMono Nerd Font";
    font-weight: bold;
    background-color: transparent;
}}
.lbl-title  {{ font-size: 14px; color: #fff495; }}
.lbl-sub    {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-conn   {{ font-size: 11px; color: #7af0a0; font-weight: normal; }}
.lbl-paired {{ font-size: 11px; color: #7ab4f0; font-weight: normal; }}
.lbl-scan   {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
"""


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""

def btctl(cmd):
    try:
        p = subprocess.Popen(
            ["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
        out, _ = p.communicate(input=f"{cmd}\nquit\n", timeout=10)
        return out
    except Exception:
        return ""

def bt_is_powered():
    return "Powered: yes" in run("bluetoothctl show")

def get_paired_devices():
    out = run("bluetoothctl paired-devices")
    devices = []
    for line in out.splitlines():
        m = re.match(r"Device ([0-9A-F:]{17}) (.+)", line)
        if m:
            devices.append({"mac": m.group(1), "name": m.group(2), "paired": True})
    return devices

def get_connected_macs():
    connected = set()
    for dev in get_paired_devices():
        if "Connected: yes" in run(f"bluetoothctl info {dev['mac']}"):
            connected.add(dev["mac"])
    return connected

def get_scan_results():
    paired_macs = {d["mac"] for d in get_paired_devices()}
    import time
    run("bluetoothctl -- scan on &")
    time.sleep(4)
    run("bluetoothctl -- scan off")
    out = run("bluetoothctl devices")
    devices = []
    for line in out.splitlines():
        m = re.match(r"Device ([0-9A-F:]{17}) (.+)", line)
        if m and m.group(1) not in paired_macs:
            devices.append({"mac": m.group(1), "name": m.group(2), "paired": False})
    return devices

def _device_icon(name):
    n = name.lower()
    if any(k in n for k in ("head", "ear", "bud")):
        return "🎧"
    if "mouse" in n:
        return "🖱️"
    if any(k in n for k in ("keyboard", "tastatur")):
        return "⌨️"
    if "phone" in n:
        return "📱"
    return "🔵"


class BluetoothPopup(Gtk.Window):
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

        self.set_size_request(350, -1)
        self.connect("key-press-event",
            lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        self.connect("focus-out-event", self._on_focus_out)

        self._scanning = False
        self._build()
        self.show_all()
        if not HAS_LAYER_SHELL:
            self._fallback_position()
        threading.Thread(target=self._load_paired, daemon=True).start()

    def _clear_bg(self, _w, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

    def _bubble(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b.get_style_context().add_class("bubble")
        return b

    def _build(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(6); outer.set_margin_bottom(6)
        outer.set_margin_start(6); outer.set_margin_end(6)
        self.add(outer)

        # ── Header ─────────────────────────────────────────────────────
        hdr = self._bubble()
        outer.pack_start(hdr, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr.pack_start(row, False, False, 0)

        title = Gtk.Label(label="🎧 Bluetooth")
        title.get_style_context().add_class("lbl-title")
        title.get_style_context().add_class("tile")
        title.set_halign(Gtk.Align.START)
        row.pack_start(title, True, True, 0)

        self._powered = bt_is_powered()
        self._power_btn = Gtk.Button(label="AN" if self._powered else "AUS")
        self._power_btn.get_style_context().add_class("tile")
        if not self._powered:
            self._power_btn.get_style_context().add_class("btn-power-off")
        self._power_btn.connect("clicked", self._toggle_bt)
        row.pack_end(self._power_btn, False, False, 0)

        self._scan_btn = Gtk.Button(label="🔍 Scannen")
        self._scan_btn.get_style_context().add_class("tile")
        self._scan_btn.connect("clicked", self._start_scan)
        row.pack_end(self._scan_btn, False, False, 4)

        # ── Paired devices ─────────────────────────────────────────────
        self._paired_bubble = self._bubble()
        outer.pack_start(self._paired_bubble, False, False, 0)

        sec_lbl = Gtk.Label(label="Gekoppelte Geräte")
        sec_lbl.get_style_context().add_class("lbl-sub")
        sec_lbl.get_style_context().add_class("tile")
        sec_lbl.set_halign(Gtk.Align.START)
        self._paired_bubble.pack_start(sec_lbl, False, False, 0)

        sp = Gtk.Spinner()
        sp.set_size_request(26, 26)
        sp.start()
        self._paired_bubble.pack_start(sp, False, False, 4)

        # ── Scan results ───────────────────────────────────────────────
        self._scan_bubble = self._bubble()
        self._scan_bubble.set_margin_bottom(0)
        outer.pack_start(self._scan_bubble, False, False, 0)

        scan_hdr = Gtk.Label(label="Gefundene Geräte")
        scan_hdr.get_style_context().add_class("lbl-sub")
        scan_hdr.get_style_context().add_class("tile")
        scan_hdr.set_halign(Gtk.Align.START)
        self._scan_bubble.pack_start(scan_hdr, False, False, 0)

        self._scan_status = Gtk.Label(label="Noch kein Scan")
        self._scan_status.get_style_context().add_class("lbl-scan")
        self._scan_status.get_style_context().add_class("tile")
        self._scan_status.set_halign(Gtk.Align.START)
        self._scan_bubble.pack_start(self._scan_status, False, False, 0)

    # ── Device row (jetzt als Tile) ────────────────────────────────────────────
    def _make_device_row(self, dev, is_connected, paired=True):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.get_style_context().add_class("tile")
        box.set_margin_top(3); box.set_margin_bottom(3)
        box.set_margin_start(4); box.set_margin_end(4)

        icon = Gtk.Label(label=_device_icon(dev["name"]))
        box.pack_start(icon, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.pack_start(info, True, True, 0)

        name = Gtk.Label(label=dev["name"])
        name.set_halign(Gtk.Align.START)
        name.set_ellipsize(3)
        info.pack_start(name, False, False, 0)

        if is_connected:
            st = Gtk.Label(label="● Verbunden")
            st.get_style_context().add_class("lbl-conn")
        elif paired:
            st = Gtk.Label(label="○ Gekoppelt")
            st.get_style_context().add_class("lbl-paired")
        else:
            st = Gtk.Label(label="Neu")
            st.get_style_context().add_class("lbl-scan")
        st.set_halign(Gtk.Align.START)
        info.pack_start(st, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.pack_end(btn_box, False, False, 0)

        mac = dev["mac"]
        if paired:
            if is_connected:
                d_btn = Gtk.Button(label="Trennen")
                d_btn.get_style_context().add_class("btn-danger")
                d_btn.get_style_context().add_class("btn-sm")
                d_btn.connect("clicked", lambda _b, m=mac: self._bt_action("disconnect", m))
                btn_box.pack_start(d_btn, False, False, 0)
            else:
                c_btn = Gtk.Button(label="Verbinden")
                c_btn.get_style_context().add_class("btn-ok")
                c_btn.get_style_context().add_class("btn-sm")
                c_btn.connect("clicked", lambda _b, m=mac: self._bt_action("connect", m))
                btn_box.pack_start(c_btn, False, False, 0)

            f_btn = Gtk.Button(label="✕")
            f_btn.get_style_context().add_class("btn-danger")
            f_btn.get_style_context().add_class("btn-sm")
            f_btn.set_tooltip_text("Vergessen")
            f_btn.connect("clicked", lambda _b, m=mac: self._forget(m))
            btn_box.pack_start(f_btn, False, False, 0)
        else:
            p_btn = Gtk.Button(label="Koppeln")
            p_btn.get_style_context().add_class("btn-sm")
            p_btn.connect("clicked", lambda _b, m=mac: self._pair(m))
            btn_box.pack_start(p_btn, False, False, 0)

        return box

    # ── Paired device loading ─────────────────────────────────────────────────
    def _load_paired(self):
        paired    = get_paired_devices()
        connected = get_connected_macs()
        GLib.idle_add(self._render_paired, paired, connected)

    def _render_paired(self, devices, connected):
        for child in list(self._paired_bubble.get_children())[1:]:
            self._paired_bubble.remove(child)

        if not devices:
            lbl = Gtk.Label(label="Keine gekoppelten Geräte")
            lbl.get_style_context().add_class("lbl-scan")
            lbl.get_style_context().add_class("tile")
            lbl.set_halign(Gtk.Align.START)
            self._paired_bubble.pack_start(lbl, False, False, 4)
        else:
            for dev in devices:
                row = self._make_device_row(dev, dev["mac"] in connected, paired=True)
                self._paired_bubble.pack_start(row, False, False, 2)

        self._paired_bubble.show_all()

    # ── Scan ──────────────────────────────────────────────────────────────────
    def _start_scan(self, *_):
        if self._scanning:
            return
        self._scanning = True
        self._scan_status.set_text("Scanne… (4 Sekunden)")
        self._scan_btn.set_sensitive(False)
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        devices = get_scan_results()
        GLib.idle_add(self._render_scan, devices)

    def _render_scan(self, devices):
        self._scanning = False
        self._scan_btn.set_sensitive(True)

        for child in list(self._scan_bubble.get_children())[1:]:
            self._scan_bubble.remove(child)

        if not devices:
            self._scan_status = Gtk.Label(label="Keine neuen Geräte gefunden")
            self._scan_status.get_style_context().add_class("lbl-scan")
            self._scan_status.get_style_context().add_class("tile")
            self._scan_status.set_halign(Gtk.Align.START)
            self._scan_bubble.pack_start(self._scan_status, False, False, 4)
        else:
            for dev in devices:
                row = self._make_device_row(dev, False, paired=False)
                self._scan_bubble.pack_start(row, False, False, 2)

        self._scan_bubble.show_all()

    # ── BT actions ────────────────────────────────────────────────────────────
    def _bt_action(self, action, mac):
        def do():
            btctl(f"{action} {mac}")
            GLib.idle_add(lambda: threading.Thread(target=self._load_paired, daemon=True).start())
        threading.Thread(target=do, daemon=True).start()

    def _forget(self, mac):
        def do():
            btctl(f"remove {mac}")
            GLib.idle_add(lambda: threading.Thread(target=self._load_paired, daemon=True).start())
        threading.Thread(target=do, daemon=True).start()

    def _pair(self, mac):
        def do():
            btctl(f"pair {mac}")
            btctl(f"trust {mac}")
            btctl(f"connect {mac}")
            GLib.idle_add(lambda: threading.Thread(target=self._load_paired, daemon=True).start())
        threading.Thread(target=do, daemon=True).start()

    def _toggle_bt(self, *_):
        def do():
            if bt_is_powered():
                run("bluetoothctl power off")
            else:
                run("bluetoothctl power on")
            powered = bt_is_powered()
            def upd():
                self._power_btn.set_label("AN" if powered else "AUS")
                ctx = self._power_btn.get_style_context()
                if powered:
                    ctx.remove_class("btn-power-off")
                else:
                    ctx.add_class("btn-power-off")
            GLib.idle_add(upd)
        threading.Thread(target=do, daemon=True).start()

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
    win = BluetoothPopup()
    Gtk.main()
