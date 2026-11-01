#!/usr/bin/env python3
import os
import sys
import signal
import fcntl
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, Vte, GLib, Gdk

HOME = Path.home()
NCSPOT = str(HOME / ".local/bin/ncspot")
LOCK = HOME / ".cache/bloodymusic.lock"
PIDFILE = HOME / ".cache/bloodymusic.pid"

LOCK.parent.mkdir(parents=True, exist_ok=True)
lock = open(LOCK, "w")

try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    try:
        os.kill(int(PIDFILE.read_text()), signal.SIGUSR1)
    except (OSError, ValueError):
        pass
    sys.exit(0)

PIDFILE.write_text(str(os.getpid()))

class BloodyMusic:
    def __init__(self):
        self.child_pid = None

        self.window = Gtk.Window(title="BloodyMusic — BloodyCat Edition")
        self.window.set_default_size(760, 520)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.connect("delete-event", self.hide_window)

        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(200)
        self.terminal.set_color_background(
            Gdk.RGBA(0.06, 0.07, 0.09, 1)
        )
        self.terminal.set_color_foreground(
            Gdk.RGBA(0.94, 0.94, 0.94, 1)
        )
        self.terminal.connect("child-exited", self.child_exited)
        self.window.add(self.terminal)

        self.tray = Gtk.StatusIcon()
        self.tray.set_from_icon_name("multimedia-player")
        self.tray.set_tooltip_text("BloodyMusic — Spotify Premium")
        self.tray.set_visible(True)
        self.tray.connect("activate", self.show_window)
        self.tray.connect("popup-menu", self.tray_menu)

        signal.signal(
            signal.SIGUSR1,
            lambda *_: GLib.idle_add(self.show_window)
        )

        self.window.show_all()

        ok, pid = self.terminal.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            str(HOME),
            [NCSPOT],
            None,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            None
        )

        if not ok:
            raise RuntimeError("No se pudo iniciar ncspot")

        self.child_pid = pid

    def spawned(self, terminal, pid, error, *args):
        if error:
            print("Error iniciando ncspot:", error)
            self.tray.set_visible(False)
            Gtk.main_quit()
        else:
            self.child_pid = pid

    def hide_window(self, *args):
        self.window.hide()
        return True

    def show_window(self, *args):
        self.window.show_all()
        self.window.present()
        return False

    def tray_menu(self, icon, button, timestamp):
        menu = Gtk.Menu()

        open_item = Gtk.MenuItem(label="Mostrar BloodyMusic")
        open_item.connect("activate", self.show_window)
        menu.append(open_item)

        exit_item = Gtk.MenuItem(label="Salir completamente")
        exit_item.connect("activate", self.quit)
        menu.append(exit_item)

        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu,
                   icon, button, timestamp)

    def child_exited(self, *args):
        self.child_pid = None
        self.tray.set_visible(False)
        Gtk.main_quit()

    def quit(self, *args):
        if self.child_pid:
            try:
                os.kill(self.child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.tray.set_visible(False)
        Gtk.main_quit()

app = BloodyMusic()

try:
    Gtk.main()
finally:
    try:
        PIDFILE.unlink()
    except OSError:
        pass
