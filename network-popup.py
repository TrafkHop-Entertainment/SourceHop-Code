#!/usr/bin/env python3
"""TrafkHop Netzwerk Popup  —  gtk-layer-shell edition"""

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, os, cairo

ROFI_DIR      = os.path.expanduser("~/.config/rofi")
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
    padding: 5px 12px;
    font-family: "Noto Sans Serif";
    font-size: 11px;
    font-weight: bold;
    min-height: 30px;
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
.btn-danger       {{ color: #f07a7a; }}
.btn-danger:hover {{ background-image: none; background-color: rgba(90,16,32,0.8); color: #ffffff; }}
.btn-scan         {{ font-size: 12px; padding: 4px 12px; }}
.btn-scan.tile    {{ padding: 4px 12px; }}
.btn-sm           {{ font-size: 10px; padding: 3px 8px; min-height: 24px; }}
.btn-sm.tile      {{ padding: 3px 8px; }}

list {{ background-color: transparent; }}
row  {{ background-color: transparent; }}
row:hover {{ background-color: rgba(132,86,221,0.2); border-radius: 10px; }}

separator {{ background-color: rgba(132,86,221,0.4); min-height: 1px; margin: 3px 0; }}

/* Inline password entry */
.pw-revealer {{
    background-image: url("{BUBBLE_URI}");
    background-size: 100% 100%;
    padding: 6px 10px;
    margin: 2px 4px;
    border-radius: 10px;
}}
entry {{
    background-color: rgba(30,18,60,0.85);
    color: #fff495;
    border-radius: 8px;
    border: 1px solid rgba(132,86,221,0.6);
    padding: 4px 8px;
    font-family: "Noto Sans Serif";
    font-size: 11px;
    caret-color: #fff495;
    min-height: 26px;
}}
entry:focus {{
    border-color: #8456dd;
    box-shadow: none;
}}
entry selection {{
    background-color: #8456dd;
    color: #ffffff;
}}

label {{
    color: #fff495;
    font-family: "Noto Sans Serif", "JetBrainsMono Nerd Font";
    font-weight: bold;
    background-color: transparent;
}}
.lbl-title  {{ font-size: 14px; color: #fff495; }}
.lbl-sub    {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-ok     {{ font-size: 11px; color: #7af0a0; font-weight: normal; }}
.lbl-err    {{ font-size: 11px; color: #f07a7a; font-weight: normal; }}
.lbl-bars   {{ font-size: 11px; color: #cdc477; min-width: 38px; }}
.lbl-pw     {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
"""


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""

def run_bg(cmd):
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)

def signal_to_bars(signal):
    try:
        s = int(signal)
        if s >= 75: return "▂▄▆█"
        if s >= 50: return "▂▄▆░"
        if s >= 25: return "▂▄░░"
        return "▂░░░"
    except Exception:
        return "░░░░"

def get_connections():
    out = run("nmcli -t -f SSID,BSSID,SIGNAL,SECURITY,IN-USE dev wifi list")
    networks = []
    seen = set()
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 5:
            continue
        ssid     = parts[0].strip()
        signal   = parts[-3] if len(parts) >= 5 else "0"
        security = parts[-2] if len(parts) >= 5 else ""
        in_use   = parts[-1].strip() == "*"
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({"ssid": ssid, "signal": signal,
                         "security": security, "active": in_use, "type": "wifi"})
    networks.sort(key=lambda x: (not x["active"], -int(x["signal"] or 0)))

    eth_out = run("nmcli -t -f DEVICE,TYPE,STATE dev")
    for line in eth_out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] == "ethernet":
            networks.insert(0, {
                "ssid": f"LAN ({parts[0]})", "signal": "100",
                "security": "", "active": parts[2] == "connected",
                "type": "ethernet", "device": parts[0]})
    return networks

def get_saved_connections():
    out = run("nmcli -t -f NAME,TYPE con show")
    saved = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            saved[parts[0]] = parts[1]
    return saved

def try_connect(ssid, password=None):
    """Returns True on likely success (exit code 0), False otherwise."""
    if password:
        result = subprocess.run(
            f"nmcli dev wifi connect '{ssid}' password '{password}'",
            shell=True, capture_output=True, text=True)
    else:
        result = subprocess.run(
            f"nmcli con up '{ssid}'",
            shell=True, capture_output=True, text=True)
    return result.returncode == 0


class NetworkPopup(Gtk.Window):
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

        self.set_size_request(360, -1)
        self.connect("key-press-event",
            lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        self.connect("focus-out-event", self._on_focus_out)

        # Track which SSID currently has the password revealer open
        self._open_revealer_ssid = None

        self._build()
        self.show_all()
        if not HAS_LAYER_SHELL:
            self._fallback_position()
        threading.Thread(target=self._load_networks, daemon=True).start()

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

        # Title row
        title_box = self._bubble()
        outer.pack_start(title_box, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.pack_start(row, False, False, 0)

        title = Gtk.Label(label="🌐 Netzwerk")
        title.get_style_context().add_class("lbl-title")
        title.get_style_context().add_class("tile")
        title.set_halign(Gtk.Align.START)
        row.pack_start(title, True, True, 0)

        scan_btn = Gtk.Button(label="🔄 Scannen")
        scan_btn.get_style_context().add_class("btn-scan")
        scan_btn.get_style_context().add_class("tile")
        scan_btn.connect("clicked", self._on_scan)
        row.pack_end(scan_btn, False, False, 0)

        # Network list
        self._net_bubble = self._bubble()
        self._net_bubble.set_margin_bottom(0)
        outer.pack_start(self._net_bubble, False, False, 0)

        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(28, 28)
        self._spinner.start()
        self._net_bubble.pack_start(self._spinner, False, False, 4)

        loading = Gtk.Label(label="Suche nach Netzwerken…")
        loading.get_style_context().add_class("lbl-sub")
        loading.get_style_context().add_class("tile")
        self._net_bubble.pack_start(loading, False, False, 4)

    def _load_networks(self):
        nets = get_connections()
        GLib.idle_add(self._render_networks, nets)

    def _render_networks(self, networks):
        for child in self._net_bubble.get_children():
            self._net_bubble.remove(child)
        self._open_revealer_ssid = None

        if not networks:
            lbl = Gtk.Label(label="Keine Netzwerke gefunden")
            lbl.get_style_context().add_class("lbl-sub")
            lbl.get_style_context().add_class("tile")
            self._net_bubble.pack_start(lbl, False, False, 8)
            self._net_bubble.show_all()
            return

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        self._net_bubble.pack_start(lb, False, False, 0)

        for net in networks:
            # Each network gets a wrapper box: the visible row + a hidden revealer
            wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

            row_widget = self._make_row(net, wrapper)
            wrapper.pack_start(row_widget, False, False, 0)

            # Password revealer (hidden by default)
            revealer = Gtk.Revealer()
            revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
            revealer.set_transition_duration(180)
            revealer.set_reveal_child(False)
            wrapper.pack_start(revealer, False, False, 0)

            pw_box = self._make_pw_box(net["ssid"], revealer)
            revealer.add(pw_box)

            lb_row = Gtk.ListBoxRow()
            lb_row.set_activatable(False)
            lb_row.add(wrapper)
            lb.add(lb_row)

        self._net_bubble.show_all()

    def _make_row(self, net, wrapper):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class("tile")
        box.set_margin_top(4); box.set_margin_bottom(4)
        box.set_margin_start(4); box.set_margin_end(4)

        icon = Gtk.Label(label=(
            "🔌" if net["type"] == "ethernet"
            else "🔒" if net.get("security") else "📶"))
        box.pack_start(icon, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.pack_start(info, True, True, 0)

        name = Gtk.Label(label=net["ssid"])
        name.set_halign(Gtk.Align.START)
        name.set_ellipsize(3)
        info.pack_start(name, False, False, 0)

        if net["active"]:
            st = Gtk.Label(label="✓ Verbunden")
            st.get_style_context().add_class("lbl-ok")
        else:
            st = Gtk.Label(label=net.get("security") or "Offen")
            st.get_style_context().add_class("lbl-sub")
        st.set_halign(Gtk.Align.START)
        info.pack_start(st, False, False, 0)

        if net["type"] == "wifi":
            sig = Gtk.Label(label=signal_to_bars(net["signal"]))
            sig.get_style_context().add_class("lbl-bars")
            box.pack_start(sig, False, False, 0)

        ssid = net["ssid"]
        if net["active"]:
            btn = Gtk.Button(label="Trennen")
            btn.get_style_context().add_class("btn-danger")
            btn.connect("clicked", lambda _b, s=ssid: self._disconnect(s))
        else:
            saved = get_saved_connections()
            if ssid in saved:
                # Known network → connect directly, no password needed
                btn = Gtk.Button(label="Verbinden")
                btn.connect("clicked", lambda _b, s=ssid: self._connect_saved(s))
            else:
                # Unknown → show password revealer on click
                btn = Gtk.Button(label="Verbinden")
                btn.connect("clicked", lambda _b, s=ssid, w=wrapper: self._toggle_pw_revealer(s, w))
        box.pack_end(btn, False, False, 0)

        return box

    def _make_pw_box(self, ssid, revealer):
        """The inline password entry that slides in under a network row."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.get_style_context().add_class("pw-revealer")

        hint = Gtk.Label(label=f"Passwort für »{ssid}«")
        hint.get_style_context().add_class("lbl-pw")
        hint.set_halign(Gtk.Align.START)
        outer.pack_start(hint, False, False, 0)

        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(entry_row, False, False, 0)

        entry = Gtk.Entry()
        entry.set_visibility(False)          # password dots
        entry.set_placeholder_text("Passwort eingeben…")
        entry.set_activates_default(True)
        entry_row.pack_start(entry, True, True, 0)

        # Toggle show/hide password
        show_btn = Gtk.Button(label="👁")
        show_btn.get_style_context().add_class("btn-sm")
        show_btn.get_style_context().add_class("tile")
        show_btn.connect("clicked", lambda _b, e=entry: e.set_visibility(not e.get_visibility()))
        entry_row.pack_start(show_btn, False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(btn_row, False, False, 0)

        # Status label (shown on error)
        status_lbl = Gtk.Label(label="")
        status_lbl.get_style_context().add_class("lbl-err")
        status_lbl.set_halign(Gtk.Align.START)
        outer.pack_start(status_lbl, False, False, 0)

        cancel_btn = Gtk.Button(label="Abbrechen")
        cancel_btn.get_style_context().add_class("btn-sm")
        cancel_btn.get_style_context().add_class("tile")
        cancel_btn.connect("clicked", lambda _b, r=revealer, s=ssid: self._close_revealer(r, s))
        btn_row.pack_start(cancel_btn, True, True, 0)

        connect_btn = Gtk.Button(label="✓ Verbinden")
        connect_btn.get_style_context().add_class("btn-sm")
        connect_btn.get_style_context().add_class("tile")
        connect_btn.connect("clicked",
            lambda _b, e=entry, s=ssid, r=revealer, sl=status_lbl:
                self._connect_with_pw(s, e, r, sl))
        btn_row.pack_start(connect_btn, True, True, 0)

        # Enter key in entry triggers connect
        entry.connect("activate",
            lambda _e, e=entry, s=ssid, r=revealer, sl=status_lbl:
                self._connect_with_pw(s, e, r, sl))

        return outer

    # ── Revealer logic ────────────────────────────────────────────────────────
    def _toggle_pw_revealer(self, ssid, wrapper):
        # Find the revealer inside wrapper (second child)
        children = wrapper.get_children()
        if len(children) < 2:
            return
        revealer = children[1]

        currently_open = (self._open_revealer_ssid == ssid)

        # Close any other open revealer first
        if self._open_revealer_ssid and self._open_revealer_ssid != ssid:
            # Walk all rows to close old one — simpler to just re-render
            # but instead we track via re-render on close
            pass

        if currently_open:
            self._close_revealer(revealer, ssid)
        else:
            revealer.set_reveal_child(True)
            self._open_revealer_ssid = ssid
            # Focus the entry inside revealer → pw_box → entry_row → entry
            pw_box = revealer.get_child()
            if pw_box:
                for row_child in pw_box.get_children():
                    if isinstance(row_child, Gtk.Box):
                        for widget in row_child.get_children():
                            if isinstance(widget, Gtk.Entry):
                                GLib.timeout_add(200, widget.grab_focus)
                                break

    def _close_revealer(self, revealer, ssid):
        revealer.set_reveal_child(False)
        if self._open_revealer_ssid == ssid:
            self._open_revealer_ssid = None

    # ── Connect / disconnect ──────────────────────────────────────────────────
    def _connect_saved(self, ssid):
        def do():
            run_bg(f"nmcli con up '{ssid}'")
            GLib.timeout_add(2000, self._refresh)
        threading.Thread(target=do, daemon=True).start()

    def _connect_with_pw(self, ssid, entry, revealer, status_lbl):
        pwd = entry.get_text().strip()
        if not pwd:
            status_lbl.set_text("Bitte Passwort eingeben")
            return

        status_lbl.set_text("Verbinde…")
        entry.set_sensitive(False)

        def do():
            ok = try_connect(ssid, pwd)
            def upd():
                if ok:
                    revealer.set_reveal_child(False)
                    self._open_revealer_ssid = None
                    GLib.timeout_add(1500, self._refresh)
                else:
                    status_lbl.set_text("Verbindung fehlgeschlagen – Passwort prüfen")
                    entry.set_sensitive(True)
                    entry.grab_focus()
            GLib.idle_add(upd)
        threading.Thread(target=do, daemon=True).start()

    def _disconnect(self, ssid):
        run_bg(f"nmcli con down '{ssid}'")
        GLib.timeout_add(1500, self._refresh)

    def _on_scan(self, *_):
        run_bg("nmcli dev wifi rescan")
        GLib.timeout_add(2000,
            lambda: (threading.Thread(target=self._load_networks, daemon=True).start(), False)[1])

    def _refresh(self):
        threading.Thread(target=self._load_networks, daemon=True).start()
        return False

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
    win = NetworkPopup()
    Gtk.main()
