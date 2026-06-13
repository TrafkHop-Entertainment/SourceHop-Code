#!/usr/bin/env python3
"""TrafkHop Kalender + Wetter Popup  —  gtk-layer-shell edition"""

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

from gi.repository import Gtk, Gdk, GLib
import calendar, datetime, urllib.request, json, threading, os, cairo

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
    padding: 4px 6px;
    margin: 2px;
}}
button {{
    background-image: none;
    background-color: transparent;
    color: #fff495;
    border-radius: 10px;
    padding: 4px 10px;
    font-family: "Noto Sans Serif";
    font-size: 12px;
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
.btn-nav {{
    font-size: 18px;
    min-width: 36px; min-height: 36px;
    padding: 2px;
}}
.btn-nav.tile {{
    padding: 2px;
}}
.btn-day {{
    border-radius: 50%;
    font-size: 13px;
    min-width: 34px; min-height: 34px;
    padding: 2px;
    font-weight: bold;
}}
.btn-day.tile {{
    padding: 2px;
}}
.btn-day.tile {{
    background-size: 100% 100%;
}}
.btn-day:hover {{
    background-image: url("{BUBBLE_LT_URI}");
    background-size: 100% 100%;
}}
.btn-today {{
    background-image: none;
    background-color: #8456dd;
    color: #ffffff;
    border-radius: 50%;
}}
.btn-today:hover {{
    background-color: #9a70ee;
    background-image: none;
}}
.btn-weekend {{ color: #b08af0; }}

label {{
    color: #fff495;
    font-family: "Noto Sans Serif", "JetBrainsMono Nerd Font";
    font-weight: bold;
    background-color: transparent;
}}
.lbl-title   {{ font-size: 14px; color: #fff495; }}
.lbl-sub     {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-month   {{ font-size: 15px; color: #fff495; font-weight: bold; }}
.lbl-dayhead {{ font-size: 11px; color: #cdc477; font-weight: bold; min-width: 34px; }}
.lbl-wtemp   {{ font-size: 20px; color: #fff495; font-weight: bold; }}
.lbl-wdesc   {{ font-size: 11px; color: #cdc477; font-weight: normal; }}
.lbl-wicon   {{ font-size: 26px; }}
.lbl-ficon   {{ font-size: 16px; }}
.lbl-fday    {{ font-size: 10px; color: #cdc477; font-weight: normal; }}
.lbl-ftemp   {{ font-size: 10px; color: #fff495; }}
"""

WMO_ICONS = {0:"☀️",1:"🌤",2:"⛅",3:"☁️",45:"🌫",48:"🌫",
             51:"🌦",53:"🌦",55:"🌧",61:"🌧",63:"🌧",65:"🌧",
             71:"❄️",73:"❄️",75:"❄️",80:"🌦",81:"🌧",82:"⛈",
             95:"⛈",96:"⛈",99:"⛈"}
WMO_DESC  = {0:"Klar",1:"Überwiegend klar",2:"Teilbewölkt",3:"Bewölkt",
             45:"Neblig",48:"Eisnebel",51:"Leichter Nieselregen",53:"Nieselregen",
             55:"Starker Nieselregen",61:"Leichter Regen",63:"Regen",65:"Starker Regen",
             71:"Leichter Schnee",73:"Schnee",75:"Starker Schnee",
             80:"Leichte Schauer",81:"Schauer",82:"Starke Schauer",
             95:"Gewitter",96:"Gewitter+Hagel",99:"Starkes Gewitter"}

MONTHS_DE = ["Januar","Februar","März","April","Mai","Juni",
             "Juli","August","September","Oktober","November","Dezember"]
DAYS_DE   = ["Mo","Di","Mi","Do","Fr","Sa","So"]


def fetch_weather():
    lat, lon = 48.0533, 14.1291
    url = (f"https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           f"&current=temperature_2m,weathercode"
           f"&daily=temperature_2m_max,temperature_2m_min,weathercode"
           f"&timezone=Europe%2FVienna&forecast_days=3")
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


class CalendarPopup(Gtk.Window):
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

        today = datetime.date.today()
        self._year  = today.year
        self._month = today.month
        self._today = today

        self.connect("key-press-event",
            lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        self.connect("focus-out-event", self._on_focus_out)

        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._outer.set_margin_top(6); self._outer.set_margin_bottom(6)
        self._outer.set_margin_start(6); self._outer.set_margin_end(6)
        self.add(self._outer)

        self._build_weather()
        self._build_calendar()

        self.show_all()
        if not HAS_LAYER_SHELL:
            self._fallback_position()
        threading.Thread(target=self._load_weather, daemon=True).start()

    def _clear_bg(self, _w, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

    def _bubble(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b.get_style_context().add_class("bubble")
        return b

    # ── Weather ───────────────────────────────────────────────────────────────
    def _build_weather(self):
        box = self._bubble()
        self._outer.pack_start(box, False, False, 0)

        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.pack_start(main_row, False, False, 0)

        # Left: icon + temp/desc
        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        left.get_style_context().add_class("tile")
        main_row.pack_start(left, True, True, 0)

        self._w_icon = Gtk.Label(label="⌛")
        self._w_icon.get_style_context().add_class("lbl-wicon")
        left.pack_start(self._w_icon, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.pack_start(info, False, False, 0)

        self._w_temp = Gtk.Label(label="Lade…")
        self._w_temp.get_style_context().add_class("lbl-wtemp")
        self._w_temp.set_halign(Gtk.Align.START)
        info.pack_start(self._w_temp, False, False, 0)

        self._w_desc = Gtk.Label(label="Kremsmünster")
        self._w_desc.get_style_context().add_class("lbl-wdesc")
        self._w_desc.set_halign(Gtk.Align.START)
        info.pack_start(self._w_desc, False, False, 0)

        # Right: 3-day forecast
        self._forecast = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._forecast.set_halign(Gtk.Align.END)
        main_row.pack_end(self._forecast, False, False, 0)

    def _load_weather(self):
        data = fetch_weather()
        GLib.idle_add(self._update_weather, data)

    def _update_weather(self, data):
        if not data:
            self._w_temp.set_text("Offline")
            self._w_desc.set_text("Kein Wetter")
            return
        cur  = data["current"]
        code = cur["weathercode"]
        self._w_icon.set_text(WMO_ICONS.get(code, "❓"))
        self._w_temp.set_text(f"{cur['temperature_2m']:.0f}°C")
        self._w_desc.set_text(WMO_DESC.get(code, "Unbekannt"))

        daily   = data["daily"]
        days_de = ["Mo","Di","Mi","Do","Fr","Sa","So"]
        for i in range(min(3, len(daily["time"]))):
            d     = datetime.date.fromisoformat(daily["time"][i])
            d_cod = daily["weathercode"][i]
            d_max = daily["temperature_2m_max"][i]
            d_min = daily["temperature_2m_min"][i]

            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            col.get_style_context().add_class("tile")
            col.set_halign(Gtk.Align.CENTER)

            ld = Gtk.Label(label=days_de[d.weekday()])
            ld.get_style_context().add_class("lbl-fday")
            col.pack_start(ld, False, False, 0)

            li = Gtk.Label(label=WMO_ICONS.get(d_cod, "❓"))
            li.get_style_context().add_class("lbl-ficon")
            col.pack_start(li, False, False, 0)

            lt = Gtk.Label(label=f"{d_max:.0f}/{d_min:.0f}°")
            lt.get_style_context().add_class("lbl-ftemp")
            col.pack_start(lt, False, False, 0)

            self._forecast.pack_start(col, False, False, 0)
        self._forecast.show_all()

    # ── Calendar ──────────────────────────────────────────────────────────────
    def _build_calendar(self):
        self._cal_bubble = self._bubble()
        self._cal_bubble.set_margin_bottom(0)
        self._outer.pack_start(self._cal_bubble, False, False, 0)
        self._render_calendar()

    def _render_calendar(self):
        for child in self._cal_bubble.get_children():
            self._cal_bubble.remove(child)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_halign(Gtk.Align.CENTER)
        self._cal_bubble.pack_start(header, False, False, 0)

        pb = Gtk.Button(label="‹")
        pb.get_style_context().add_class("btn-nav")
        pb.get_style_context().add_class("tile")
        pb.connect("clicked", self._prev_month)
        header.pack_start(pb, False, False, 0)

        ml = Gtk.Label(label=f"{MONTHS_DE[self._month-1]} {self._year}")
        ml.get_style_context().add_class("lbl-month")
        ml.get_style_context().add_class("tile")
        ml.set_size_request(190, -1)
        ml.set_halign(Gtk.Align.CENTER)
        header.pack_start(ml, True, True, 0)

        nb = Gtk.Button(label="›")
        nb.get_style_context().add_class("btn-nav")
        nb.get_style_context().add_class("tile")
        nb.connect("clicked", self._next_month)
        header.pack_start(nb, False, False, 0)

        # Grid
        grid = Gtk.Grid()
        grid.set_column_spacing(2)
        grid.set_row_spacing(2)
        grid.set_halign(Gtk.Align.CENTER)
        self._cal_bubble.pack_start(grid, False, False, 0)

        for col, d in enumerate(DAYS_DE):
            lbl = Gtk.Label(label=d)
            lbl.get_style_context().add_class("lbl-dayhead")
            lbl.get_style_context().add_class("tile-small")
            lbl.set_halign(Gtk.Align.CENTER)
            grid.attach(lbl, col, 0, 1, 1)

        for row_idx, week in enumerate(calendar.monthcalendar(self._year, self._month)):
            for col_idx, day in enumerate(week):
                if day == 0:
                    lbl = Gtk.Label(label="")
                    lbl.set_size_request(34, 34)
                    grid.attach(lbl, col_idx, row_idx + 1, 1, 1)
                else:
                    btn = Gtk.Button(label=str(day))
                    btn.get_style_context().add_class("btn-day")
                    btn.get_style_context().add_class("tile")
                    if col_idx >= 5:
                        btn.get_style_context().add_class("btn-weekend")
                    is_today = (day == self._today.day
                                and self._month == self._today.month
                                and self._year == self._today.year)
                    if is_today:
                        btn.get_style_context().add_class("btn-today")
                    grid.attach(btn, col_idx, row_idx + 1, 1, 1)

        self._cal_bubble.show_all()

    def _prev_month(self, *_):
        self._month = 12 if self._month == 1 else self._month - 1
        if self._month == 12:
            self._year -= 1
        self._render_calendar()

    def _next_month(self, *_):
        self._month = 1 if self._month == 12 else self._month + 1
        if self._month == 1:
            self._year += 1
        self._render_calendar()

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
    win = CalendarPopup()
    Gtk.main()
