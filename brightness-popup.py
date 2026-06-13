#!/usr/bin/env python3
"""TrafkHop Brightness + Nachtlicht Popup  —  gtk-layer-shell edition"""

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, os, shutil, cairo

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
.btn-on {{ color: #7af0a0; }}

label {{
    color: #fff495;
    font-family: "Noto Sans Serif", "JetBrainsMono Nerd Font";
    font-weight: bold;
    background-color: transparent;
}}
.lbl-title  {{ font-size: 14px; color: #fff495; }}
.lbl-val    {{ font-size: 20px; color: #fff495; min-width: 72px; }}
.lbl-sub    {{ font-size: 10px; color: #f0b07a; font-weight: normal; }}
.lbl-hint   {{ font-size: 10px; color: #cdc477; font-weight: normal; }}

scale trough  {{ background-color: rgba(58,42,106,0.85); border-radius: 8px; min-height: 10px; }}
scale highlight {{ background-color: #fff495; border-radius: 8px; }}
scale slider  {{
    background-color: #ffffff; border-radius: 50%;
    min-width: 18px; min-height: 18px;
    border: 2px solid #8456dd; background-image: none;
}}
"""

NIGHT_TEMP_WARM = 2000
NIGHT_TEMP_DAY  = 6500
NIGHT_STATE     = "/tmp/trafkhop_night_temp"
BRIGHT_STATE    = "/tmp/trafkhop_brightness"


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


# ── Backend detection ─────────────────────────────────────────────────────────
def _has_brightnessctl():
    if not shutil.which("brightnessctl"):
        return False
    out = run("brightnessctl -m")
    return bool(out) and len(out.split(",")) >= 4

def _has_xrandr():
    if not shutil.which("xrandr"):
        return False
    out = run("xrandr --query")
    return " connected" in out

def _xrandr_output():
    out = run("xrandr --query | grep ' connected' | head -1 | cut -d' ' -f1")
    return out if out else None

def _has_gammastep():
    return bool(shutil.which("gammastep"))

# Backend‑Entscheidung:
# 1. brightnessctl (Hardware)
# 2. xrandr --brightness (VM / kein Backlight)
# 3. statefile (nur Speicherung, keine echte Änderung)
if _has_brightnessctl():
    BRIGHT_BACKEND = "brightnessctl"
elif _has_xrandr():
    BRIGHT_BACKEND = "xrandr"
else:
    BRIGHT_BACKEND = "statefile"

NIGHT_BACKEND  = "gammastep" if _has_gammastep() else "xrandr"


# ── Brightness API ────────────────────────────────────────────────────────────
def get_brightness():
    if BRIGHT_BACKEND == "brightnessctl":
        parts = run("brightnessctl -m").split(",")
        try:
            return int(parts[3].replace("%", ""))
        except Exception:
            pass
    # Für xrandr & statefile: aus Datei lesen
    try:
        return int(open(BRIGHT_STATE).read().strip())
    except Exception:
        return 100

def set_brightness(val):
    val = max(1, min(100, val))
    if BRIGHT_BACKEND == "brightnessctl":
        run(f"brightnessctl set {val}%")
    elif BRIGHT_BACKEND == "xrandr":
        out = _xrandr_output()
        if out:
            brightness = max(0.1, min(1.0, val / 100.0))
            run(f"xrandr --output {out} --brightness {brightness}")
    # In allen Fällen Wert speichern (für xrandr auch zum Wiederherstellen)
    try:
        open(BRIGHT_STATE, "w").write(str(val))
    except Exception:
        pass


# ── Night light API (unverändert, funktioniert auch in VM mit xrandr) ─────────
def _temp_to_gamma(temp):
    t = max(2000, min(6500, temp))
    n = (t - 2000) / 4500.0
    return round(1.0, 3), round(0.45 + 0.55 * n, 3), round(0.10 + 0.90 * n, 3)

def _save_night(temp):
    try:
        open(NIGHT_STATE, "w").write(str(temp))
    except Exception:
        pass

def get_night_temp():
    try:
        return int(open(NIGHT_STATE).read().strip())
    except Exception:
        return 3500

def night_is_active():
    try:
        return int(open(NIGHT_STATE).read().strip()) < NIGHT_TEMP_DAY - 100
    except Exception:
        return False

def apply_night_temp(temp):
    _save_night(temp)
    off = temp >= NIGHT_TEMP_DAY - 100
    if NIGHT_BACKEND == "gammastep":
        run("gammastep -x 2>/dev/null; true") if off else run(f"gammastep -P -O {temp}")
    else:
        out = _xrandr_output()
        if out:
            if off:
                run(f"xrandr --output {out} --gamma 1:1:1")
            else:
                r, g, b = _temp_to_gamma(temp)
                run(f"xrandr --output {out} --gamma {r}:{g}:{b}")

def toggle_night():
    if night_is_active():
        apply_night_temp(NIGHT_TEMP_DAY)
    else:
        temp = get_night_temp()
        if temp >= NIGHT_TEMP_DAY - 100:
            temp = 3500
        apply_night_temp(temp)


# ── Window ────────────────────────────────────────────────────────────────────
class BrightnessPopup(Gtk.Window):
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

        self.set_size_request(330, -1)
        self.connect("key-press-event",
            lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        self.connect("focus-out-event", self._on_focus_out)

        self._bright_timer = None
        self._night_timer  = None
        self._build()
        self.show_all()
        if not HAS_LAYER_SHELL:
            self._fallback_position()

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
        self._build_brightness(outer)
        self._build_night(outer)

    # ── Brightness section ────────────────────────────────────────────────────
    def _build_brightness(self, parent):
        box = self._bubble()
        parent.pack_start(box, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(row, False, False, 0)

        lbl = Gtk.Label(label="󰃠 Helligkeit")
        lbl.get_style_context().add_class("lbl-title")
        lbl.get_style_context().add_class("tile")
        lbl.set_halign(Gtk.Align.START)
        row.pack_start(lbl, True, True, 0)

        self._bright_lbl = Gtk.Label(label=f"{get_brightness()}%")
        self._bright_lbl.get_style_context().add_class("lbl-val")
        self._bright_lbl.get_style_context().add_class("tile")
        self._bright_lbl.set_halign(Gtk.Align.END)
        row.pack_end(self._bright_lbl, False, False, 0)

        if BRIGHT_BACKEND == "statefile":
            hint = Gtk.Label(label="⚠ Kein Backlight (VM) — Wert nur gespeichert")
            hint.get_style_context().add_class("lbl-sub")
            hint.get_style_context().add_class("tile-small")
            hint.set_halign(Gtk.Align.START)
            hint.set_line_wrap(True)
            box.pack_start(hint, False, False, 0)

        self._bright_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self._bright_scale.set_value(get_brightness())
        self._bright_scale.set_draw_value(False)
        self._bright_scale.connect("value-changed", self._on_bright_change)
        box.pack_start(self._bright_scale, False, False, 0)

    # ── Night light section ───────────────────────────────────────────────────
    def _build_night(self, parent):
        box = self._bubble()
        box.set_margin_bottom(0)
        parent.pack_start(box, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(row, False, False, 0)

        lbl = Gtk.Label(label="󰖔 Nachtlicht")
        lbl.get_style_context().add_class("lbl-title")
        lbl.get_style_context().add_class("tile")
        lbl.set_halign(Gtk.Align.START)
        row.pack_start(lbl, True, True, 0)

        active = night_is_active()
        temp   = get_night_temp()

        self._night_lbl = Gtk.Label(label=f"{temp}K" if active else "AUS")
        self._night_lbl.get_style_context().add_class("lbl-val")
        self._night_lbl.get_style_context().add_class("tile")
        self._night_lbl.set_halign(Gtk.Align.END)
        row.pack_end(self._night_lbl, False, False, 0)

        backend_txt = ("via gammastep" if NIGHT_BACKEND == "gammastep"
                       else "via xrandr --gamma (VM-Fallback)")
        hint = Gtk.Label(label=backend_txt)
        hint.get_style_context().add_class("lbl-hint")
        hint.get_style_context().add_class("tile-small")
        hint.set_halign(Gtk.Align.START)
        box.pack_start(hint, False, False, 0)

        self._night_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, NIGHT_TEMP_WARM, NIGHT_TEMP_DAY, 100)
        self._night_scale.set_value(temp if active else NIGHT_TEMP_DAY)
        self._night_scale.set_draw_value(False)
        self._night_scale.set_inverted(True)
        self._night_scale.connect("value-changed", self._on_night_change)
        box.pack_start(self._night_scale, False, False, 0)

        ends = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(ends, False, False, 0)
        wl = Gtk.Label(label="🌙 Warm"); wl.get_style_context().add_class("lbl-hint")
        cl = Gtk.Label(label="☀ Aus");  cl.get_style_context().add_class("lbl-hint")
        ends.pack_start(wl, False, False, 0)
        ends.pack_end(cl, False, False, 0)

        self._night_toggle = Gtk.Button()
        self._night_toggle.get_style_context().add_class("tile")
        self._update_night_btn(active)
        self._night_toggle.connect("clicked", self._on_night_toggle)
        box.pack_start(self._night_toggle, False, False, 2)

    # ── Events ────────────────────────────────────────────────────────────────
    def _on_bright_change(self, scale):
        v = int(scale.get_value())
        self._bright_lbl.set_text(f"{v}%")
        if self._bright_timer:
            GLib.source_remove(self._bright_timer)
        self._bright_timer = GLib.timeout_add(80, self._apply_bright, v)

    def _apply_bright(self, v):
        self._bright_timer = None
        threading.Thread(target=set_brightness, args=(v,), daemon=True).start()
        return False

    def _on_night_change(self, scale):
        temp = int(scale.get_value())
        active = temp < NIGHT_TEMP_DAY - 100
        self._night_lbl.set_text(f"{temp}K" if active else "AUS")
        self._update_night_btn(active)
        if self._night_timer:
            GLib.source_remove(self._night_timer)
        self._night_timer = GLib.timeout_add(120, self._apply_night, temp)

    def _apply_night(self, temp):
        self._night_timer = None
        threading.Thread(target=apply_night_temp, args=(temp,), daemon=True).start()
        return False

    def _on_night_toggle(self, _btn):
        def do():
            toggle_night()
            active = night_is_active()
            temp   = get_night_temp()
            GLib.idle_add(self._sync_night_ui, active, temp)
        threading.Thread(target=do, daemon=True).start()

    def _sync_night_ui(self, active, temp):
        self._update_night_btn(active)
        self._night_lbl.set_text(f"{temp}K" if active else "AUS")
        self._night_scale.handler_block_by_func(self._on_night_change)
        self._night_scale.set_value(temp if active else NIGHT_TEMP_DAY)
        self._night_scale.handler_unblock_by_func(self._on_night_change)

    def _update_night_btn(self, active):
        ctx = self._night_toggle.get_style_context()
        if active:
            self._night_toggle.set_label("🌙 Nachtlicht AN  – Ausschalten")
            ctx.add_class("btn-on")
        else:
            self._night_toggle.set_label("🌙 Nachtlicht EIN – Einschalten")
            ctx.remove_class("btn-on")

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
    win = BrightnessPopup()
    Gtk.main()
