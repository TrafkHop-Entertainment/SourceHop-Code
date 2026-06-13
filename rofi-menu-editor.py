#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib

import json
import os
import re
from pathlib import Path

# Pfade
MENU_JSON_PATH = Path.home() / ".config" / "rofi" / "menu.json"
WAYBAR_CONFIG_PATH = Path.home() / ".config" / "waybar" / "config.jsonc"
DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/usr/local/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
]
APP_ID = "de.trafkhop.MenuEditor"

# ─────────────────────────────────────────────────────────────
# JSON-HELPERS (Unterordner-Support)
# ─────────────────────────────────────────────────────────────
def flatten_dict(d: dict, parent_key: str = '') -> dict:
    items = {}
    if parent_key and parent_key not in items:
        items[parent_key] = {}
    if not isinstance(d, dict):
        return items
    for k, v in d.items():
        if isinstance(v, dict):
            new_key = f"{parent_key}/{k}" if parent_key else k
            if new_key not in items:
                items[new_key] = {}
            child_items = flatten_dict(v, new_key)
            for ck, cv in child_items.items():
                if ck not in items:
                    items[ck] = {}
                items[ck].update(cv)
        else:
            target_key = parent_key if parent_key else "(Root)"
            if target_key not in items:
                items[target_key] = {}
            items[target_key][k] = str(v)
    return items

def unflatten_dict(flat_dict: dict) -> dict:
    res = {}
    for path, apps in flat_dict.items():
        if path == "(Root)" or path == "⚠️ Waybar Schnellstart":
            continue  # Waybar wird separat gespeichert
        parts = path.split('/')
        current = res
        for part in parts:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        for app_name, app_cmd in apps.items():
            current[app_name] = str(app_cmd)
    return res

# ─────────────────────────────────────────────────────────────
# WAYBAR PARSER & WRITER (Unterstützt echte JSONC-Kommentare nicht ganz, nutzt Regex-Säuberung)
# ─────────────────────────────────────────────────────────────
def load_waybar_apps() -> dict:
    apps = {}
    if not WAYBAR_CONFIG_PATH.exists():
        return apps
    try:
        content = WAYBAR_CONFIG_PATH.read_text()
        # Entferne einzeilige Kommentare für den Parser
        content_clean = re.sub(r"//.*", "", content)
        data = json.loads(content_clean)

        modules_left = data.get("modules-left", [])
        for mod in modules_left:
            if mod.startswith("custom/") and mod not in ["custom/appmenu", "custom/power", "custom/hideAll", "custom/allworkspaces"]:
                mod_cfg = data.get(mod, {})
                # Name aus custom/xyz -> Xyz machen
                name = mod.replace("custom/", "").capitalize()
                apps[name] = mod_cfg.get("on-click", "")
    except Exception as e:
        print(f"Fehler beim Laden der Waybar: {e}")
    return apps

def save_waybar_apps(waybar_apps: dict):
    if not WAYBAR_CONFIG_PATH.exists():
        return
    try:
        content = WAYBAR_CONFIG_PATH.read_text()
        content_clean = re.sub(r"//.*", "", content)
        data = json.loads(content_clean)

        # 1. Entferne alte custom/ Einträge aus modules-left
        old_modules = data.get("modules-left", [])
        new_modules = []

        # Standard-Basismodule behalten
        for m in old_modules:
            if m in ["custom/appmenu", "custom/power", "custom/allworkspaces", "custom/hideAll"]:
                new_modules.append(m)

        # 2. Lösche alte Custom-Konfigurationen aus dem Root-Objekt
        for k in list(data.keys()):
            if k.startswith("custom/") and k not in ["custom/appmenu", "custom/power", "custom/hideAll", "custom/allworkspaces"]:
                del data[k]

        # 3. Neue Apps generieren und einsortieren
        # Icons erraten oder Standard setzen
        icon_mapping = {"kitty": "🖹", "thunar": "📁", "firefox": "🌐"}

        for name, cmd in waybar_apps.items():
            mod_id = f"custom/{name.lower()}"
            new_modules.append(mod_id)

            cmd_base = cmd.split()[0].lower()
            icon = icon_mapping.get(cmd_base, "🚀")

            data[mod_id] = {
                "format": icon,
                "on-click": cmd,
                "tooltip": f"open {name.lower()}"
            }

        data["modules-left"] = new_modules

        # Zurückspeichern
        WAYBAR_CONFIG_PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False))
        # Waybar neu laden signalisieren
        os.system("killall -SIGUSR2 waybar 2>/dev/null")
        # Autohide-Skript über den Reset informieren!
        os.system("pkill -USR2 -f autohide.sh 2>/dev/null")
    except Exception as e:
        print(f"Fehler beim Speichern der Waybar: {e}")

# ─────────────────────────────────────────────────────────────
# SCANNERS
# ─────────────────────────────────────────────────────────────
def parse_desktop_file(path: Path) -> dict | None:
    data = {}
    try:
        in_desktop = False
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if line == "[Desktop Entry]":
                in_desktop = True
                continue
            if line.startswith("[") and line != "[Desktop Entry]":
                in_desktop = False
                continue
            if in_desktop and "=" in line:
                key, _, val = line.partition("=")
                data[key.strip()] = val.strip()
    except Exception:
        return None

    if data.get("NoDisplay") == "true" or data.get("Hidden") == "true":
        return None
    name = data.get("Name", "").strip()
    exec_clean = re.sub(r"%[a-zA-Z]", "", data.get("Exec", "")).strip()
    if not name or not exec_clean: return None

    return {
        "name": name, "exec": exec_clean, "icon": data.get("Icon", "application-x-executable"),
        "comment": data.get("Comment", "Desktop App"), "type": "desktop"
    }

def get_desktop_entries() -> list[dict]:
    seen_execs = set()
    entries = []
    for d in DESKTOP_DIRS:
        if not d.exists(): continue
        for f in sorted(d.glob("*.desktop")):
            entry = parse_desktop_file(f)
            if entry and entry["exec"].split()[0] not in seen_execs:
                seen_execs.add(entry["exec"].split()[0])
                entries.append(entry)
    return sorted(entries, key=lambda e: e["name"].lower())

def get_binary_entries() -> list[dict]:
    seen_execs = set()
    entries = []
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(path_dir)
        if not p.is_dir(): continue
        try:
            for child in p.iterdir():
                if child.is_file() and os.access(child, os.X_OK):
                    if child.name not in seen_execs:
                        seen_execs.add(child.name)
                        entries.append({
                            "name": child.name, "exec": child.name,
                            "icon": "utilities-terminal", "comment": "System Paket / Binary", "type": "binary"
                        })
        except Exception:
            pass
    return sorted(entries, key=lambda e: e["name"].lower())

# ─────────────────────────────────────────────────────────────
# GTK APP WINDOW
# ─────────────────────────────────────────────────────────────
class CustomAppDialog(Adw.MessageDialog):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True)
        self.set_heading("Eigene App/Datei hinzufügen")
        self.add_response("cancel", "Abbrechen")
        self.add_response("ok", "Hinzufügen")
        self.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        self._name_row = Adw.EntryRow(title="Name")
        self._cmd_row = Adw.EntryRow(title="Befehl oder Pfad")
        box.append(self._name_row)
        box.append(self._cmd_row)

        file_btn = Gtk.Button(label="Datei/Skript wählen...")
        file_btn.add_css_class("flat")
        file_btn.connect("clicked", self._pick_file)
        box.append(file_btn)
        self.set_extra_child(box)

    def _pick_file(self, btn):
        dialog = Gtk.FileDialog(title="Wähle Datei")
        dialog.open(self.get_transient_for(), None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            f = dialog.open_finish(result)
            if f:
                path = f.get_path()
                if os.access(path, os.X_OK):
                    self._cmd_row.set_text(path)
                else:
                    self._cmd_row.set_text(f'xdg-open "{path}"')
        except Exception: pass

    @property
    def name(self): return self._name_row.get_text().strip()
    @property
    def cmd(self): return self._cmd_row.get_text().strip()


class FolderDialog(Adw.MessageDialog):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True)
        self.set_heading("Neuer Ordner")
        self.add_response("cancel", "Abbrechen")
        self.add_response("ok", "Erstellen")
        self.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        self._entry = Adw.EntryRow(title="Ordnername (z.B. Games/RSA)")
        self.set_extra_child(self._entry)

    @property
    def folder_name(self): return self._entry.get_text().strip()


class MenuEditorWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Rofi & Waybar Menu Editor")
        self.set_default_size(1050, 680)

        # Menü laden und Waybar injizieren
        raw_menu = {}
        if MENU_JSON_PATH.exists():
            try: raw_menu = json.loads(MENU_JSON_PATH.read_text())
            except Exception: pass
        self._menu = flatten_dict(raw_menu)
        self._menu["⚠️ Waybar Schnellstart"] = load_waybar_apps()

        self._deskt_entries = []
        self._bin_entries = []
        self._selected_folder = None
        self._search_query = ""

        self._build_ui()
        self._refresh_folder_list()
        self._load_data_async()

    def _build_ui(self):
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(outer)

        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        self._title_widget = Adw.WindowTitle(title="Rofi & Waybar Editor")
        header.set_title_widget(self._title_widget)

        save_btn = Gtk.Button(icon_name="document-save-symbolic")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)
        outer.append(header)

        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._paned.set_position(260)
        outer.append(self._paned)
        self._paned.set_vexpand(True)

        # LINKS: Ordnerliste
        s_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._folder_list = Gtk.ListBox()
        self._folder_list.connect("row-selected", self._on_folder_selected)
        scroll.set_child(self._folder_list)
        s_box.append(scroll)

        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_f = Gtk.Button(icon_name="folder-new-symbolic")
        add_f.connect("clicked", self._on_add_folder)
        del_f = Gtk.Button(icon_name="user-trash-symbolic")
        del_f.add_css_class("destructive-action")
        del_f.connect("clicked", self._on_delete_folder)
        tb.append(add_f)
        tb.append(del_f)
        s_box.append(tb)
        self._paned.set_start_child(s_box)

        # RECHTS: Content Splitter (Aktueller Inhalt vs Verfügbare Apps)
        c_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._search_entry = Gtk.SearchEntry(hexpand=True, placeholder_text="Suchen...")
        self._search_entry.connect("search-changed", self._on_search_changed)
        top_bar.append(self._search_entry)

        custom_btn = Gtk.Button(label="+ Eigene App/Datei")
        custom_btn.connect("clicked", lambda *_: self._on_add_custom_app())
        top_bar.append(custom_btn)
        c_box.append(top_bar)

        inner_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner_paned.set_position(360)
        c_box.append(inner_paned)

        # Linke Innenspalte: Apps im ausgewählten Ordner
        l_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._folder_label = Gtk.Label(label="Ordnerinhalt", xalign=0)
        self._folder_label.add_css_class("heading")
        l_box.append(self._folder_label)
        l_scroll = Gtk.ScrolledWindow(vexpand=True)
        self._menu_list = Gtk.ListBox()
        l_scroll.set_child(self._menu_list)
        l_box.append(l_scroll)
        inner_paned.set_start_child(l_box)

        # Rechte Innenspalte: Filter-Tabs & Quell-Apps
        r_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Die neuen Tabs für Option 1 und Option 2!
        self._view_stack = Gtk.Stack()
        stack_switcher = Gtk.StackSwitcher()
        stack_switcher.set_stack(self._view_stack)
        r_box.append(stack_switcher)

        self._loading_spinner = Gtk.Spinner()
        r_box.append(self._loading_spinner)

        # Tab 1: Desktop Einträge (.desktop)
        self._desktop_list = Gtk.ListBox()
        self._desktop_list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        d_scroll = Gtk.ScrolledWindow(vexpand=True)
        d_scroll.set_child(self._desktop_list)
        self._view_stack.add_titled(d_scroll, "desktop", "1. Desktop Apps")

        # Tab 2: Alle Pakete & Systembefehle (Alphabetisch)
        self._binary_list = Gtk.ListBox()
        self._binary_list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        b_scroll = Gtk.ScrolledWindow(vexpand=True)
        b_scroll.set_child(self._binary_list)
        self._view_stack.add_titled(b_scroll, "binary", "2. Alle Pakete (A-Z)")

        r_box.append(self._view_stack)

        add_sel_btn = Gtk.Button(label="← Ausgewählte Apps hinzufügen")
        add_sel_btn.add_css_class("suggested-action")
        add_sel_btn.connect("clicked", self._on_add_selected)
        r_box.append(add_sel_btn)

        inner_paned.set_end_child(r_box)
        self._paned.set_end_child(c_box)

    def _refresh_folder_list(self):
        selected = self._selected_folder
        while self._folder_list.get_first_child():
            self._folder_list.remove(self._folder_list.get_first_child())

        for folder in sorted(self._menu.keys()):
            row = Gtk.ListBoxRow()
            row.folder_name = folder
            hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = "preferences-system-windows-symbolic" if "Waybar" in folder else "folder-symbolic"
            hb.append(Gtk.Image.new_from_icon_name(icon))
            hb.append(Gtk.Label(label=folder, hexpand=True, xalign=0))
            row.set_child(hb)
            self._folder_list.append(row)

        if selected in self._menu:
            row = self._folder_list.get_first_child()
            while row:
                if row.folder_name == selected:
                    self._folder_list.select_row(row)
                    break
                row = row.get_next_sibling()

    def _on_folder_selected(self, lb, row):
        if row:
            self._selected_folder = row.folder_name
            self._folder_label.set_label(f"In „{self._selected_folder}“")
            self._refresh_menu_list()

    def _refresh_menu_list(self):
        while self._menu_list.get_first_child():
            self._menu_list.remove(self._menu_list.get_first_child())
        if not self._selected_folder: return

        q = self._search_query.lower()
        for name, cmd in list(self._menu[self._selected_folder].items()):
            if q and q not in name.lower() and q not in str(cmd).lower(): continue
            row = Gtk.ListBoxRow()
            hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hb.append(Gtk.Label(label=f"{name} → {cmd}", hexpand=True, xalign=0))
            rem = Gtk.Button(icon_name="list-remove-symbolic")
            rem.connect("clicked", lambda b, n=name: self._rem_entry(n))
            hb.append(rem)
            row.set_child(hb)
            self._menu_list.append(row)

    def _rem_entry(self, name):
        if self._selected_folder:
            del self._menu[self._selected_folder][name]
            self._refresh_menu_list()
            self._refresh_avail_lists()

    def _load_data_async(self):
        self._loading_spinner.start()
        def load():
            d_entries = get_desktop_entries()
            b_entries = get_binary_entries()
            GLib.idle_add(self._on_data_loaded, d_entries, b_entries)
        import threading
        threading.Thread(target=load, daemon=True).start()

    def _on_data_loaded(self, d_entries, b_entries):
        self._deskt_entries = d_entries
        self._bin_entries = b_entries
        self._loading_spinner.stop()
        self._refresh_avail_lists()

    def _refresh_avail_lists(self):
        # 1. Desktop-Liste leeren & befüllen
        while self._desktop_list.get_first_child(): self._desktop_list.remove(self._desktop_list.get_first_child())
        # 2. Binary-Liste leeren & befüllen
        while self._binary_list.get_first_child(): self._binary_list.remove(self._binary_list.get_first_child())

        q = self._search_query.lower()

        # Filterfunktion
        def is_already_added(name, cmd):
            if not self._selected_folder: return False
            return name in self._menu[self._selected_folder]

        # Befülle Desktop-Apps
        for e in self._deskt_entries:
            if is_already_added(e["name"], e["exec"]): continue
            if q and q not in e["name"].lower() and q not in e["exec"].lower(): continue
            self._desktop_list.append(self._create_app_row(e))

        # Befülle Binaries (A-Z) – Limitiert auf 300 Einträge ohne Suche, um UI-Lags zu vermeiden
        b_count = 0
        for e in self._bin_entries:
            if is_already_added(e["name"], e["exec"]): continue
            if q and q not in e["name"].lower() and q not in e["exec"].lower(): continue
            if not q and b_count > 300: break  # Bremse, falls keine Suche läuft
            self._binary_list.append(self._create_app_row(e))
            b_count += 1

    def _create_app_row(self, e):
        row = Gtk.ListBoxRow()
        row.entry_data = e
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hb.append(Gtk.Image.new_from_icon_name(e["icon"]))
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vb.append(Gtk.Label(label=e["name"], xalign=0))
        lbl = Gtk.Label(label=e["comment"], xalign=0)
        lbl.add_css_class("dim-label")
        vb.append(lbl)
        hb.append(vb)
        row.set_child(hb)
        return row

    def _on_add_selected(self, btn):
        if not self._selected_folder: return

        active_list = self._desktop_list if self._view_stack.get_visible_child_name() == "desktop" else self._binary_list
        for r in active_list.get_selected_rows():
            if hasattr(r, "entry_data"):
                self._menu[self._selected_folder][r.entry_data["name"]] = r.entry_data["exec"]

        self._refresh_menu_list()
        self._refresh_avail_lists()

    def _on_add_custom_app(self):
        if not self._selected_folder: return
        d = CustomAppDialog(self)
        d.connect("response", self._add_custom_cb)
        d.present()

    def _add_custom_cb(self, d, r):
        if r == "ok" and d.name and d.cmd:
            self._menu[self._selected_folder][d.name] = d.cmd
            self._refresh_menu_list()
            self._refresh_avail_lists()
        d.destroy()

    def _on_add_folder(self, btn):
        d = FolderDialog(self)
        d.connect("response", lambda d, r: self._add_f_cb(d, r))
        d.present()

    def _add_f_cb(self, d, r):
        if r == "ok" and d.folder_name:
            if d.folder_name not in self._menu and "Waybar" not in d.folder_name:
                self._menu[d.folder_name] = {}
                self._refresh_folder_list()
        d.destroy()

    def _on_delete_folder(self, btn):
        if self._selected_folder and "Waybar" not in self._selected_folder:
            del self._menu[self._selected_folder]
            self._selected_folder = None
            self._refresh_folder_list()
            self._refresh_avail_lists()

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text()
        self._refresh_menu_list()
        self._refresh_avail_lists()

    def _on_save(self, btn):
        # 1. Rofi-Menü sichern
        save_menu(self._menu)
        # 2. Waybar-Einträge separat sichern
        save_waybar_apps(self._menu.get("⚠️ Waybar Schnellstart", {}))

        self._title_widget.set_subtitle("Gespeichert & Waybar aktualisiert!")


def save_menu(menu: dict):
    MENU_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    nested_menu = unflatten_dict(menu)
    MENU_JSON_PATH.write_text(json.dumps(nested_menu, indent=2, ensure_ascii=False))


class MenuEditorApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", lambda app: MenuEditorWindow(app).present())

if __name__ == "__main__":
    import sys
    sys.exit(MenuEditorApp().run(sys.argv))
