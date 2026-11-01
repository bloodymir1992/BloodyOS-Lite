#!/usr/bin/env python3
"""BloodyDisk Lite 1.1: read-only GTK3 storage overview."""
import os
import subprocess
import threading
from pathlib import Path
import gi
import cairo

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

PALETTE = {'used': '#ef4444', 'free': '#22c55e', 'reserved': '#a78bfa',
           'books': '#a78bfa', 'music': '#22c55e', 'video': '#f59e0b',
           'documents': '#60a5fa', 'images': '#f472b6', 'other': '#9ca3af'}
EXTENSIONS = {
    'books': {'.pdf', '.epub', '.mobi', '.azw', '.azw3', '.cbz', '.cbr', '.djvu'},
    'music': {'.mp3', '.flac', '.ogg', '.opus', '.m4a', '.wav', '.aac'},
    'video': {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.mpeg', '.mpg'},
    'documents': {'.txt', '.odt', '.doc', '.docx', '.rtf', '.md', '.csv', '.ods', '.xlsx', '.pptx'},
    'images': {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.heic'},
}
NAMES = {'books': 'Libros y mangas', 'music': 'Música', 'video': 'Videos',
         'documents': 'Documentos', 'images': 'Imágenes', 'other': 'Otros archivos'}


def fmt(n):
    n = float(n)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if n < 1024 or unit == 'TiB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n:.0f} B'
        n /= 1024


def rgb(hexcode):
    return tuple(int(hexcode[i:i + 2], 16) / 255 for i in (1, 3, 5))


def mounts():
    """List existing mounted local filesystems; no privileged disk operations."""
    excluded = {'proc', 'sysfs', 'tmpfs', 'devtmpfs', 'devpts', 'cgroup', 'cgroup2',
                'overlay', 'squashfs', 'tracefs', 'securityfs', 'debugfs', 'pstore',
                'configfs', 'fusectl', 'mqueue', 'hugetlbfs', 'autofs', 'rpc_pipefs'}
    result, seen = [], set()
    with open('/proc/self/mounts', encoding='utf-8') as f:
        for line in f:
            fields = line.split()
            if len(fields) < 3:
                continue
            dev, dest, fstype = fields[:3]
            dest = dest.replace('\\040', ' ')
            if not dest.startswith('/') or fstype in excluded or dest in seen:
                continue
            if not (dev.startswith('/dev/') or fstype in {'fuseblk', 'exfat', 'vfat'}):
                continue
            try:
                if os.statvfs(dest).f_blocks == 0:
                    continue
            except OSError:
                continue
            result.append((dest, dev))
            seen.add(dest)
    return sorted(result, key=lambda x: (x[0] != '/', x[0]))


def scan_home(root):
    """Read-only walk of home on same filesystem. Sizes are logical, not allocated blocks."""
    totals = {key: 0 for key in NAMES}
    count, errors = 0, 0
    rootdev = os.stat(root).st_dev
    seen_inodes = set()
    def onerror(_):
        nonlocal errors
        errors += 1
    for folder, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
        keep = []
        for dirname in dirs:
            path = os.path.join(folder, dirname)
            try:
                st = os.lstat(path)
                if not os.path.islink(path) and st.st_dev == rootdev:
                    keep.append(dirname)
            except OSError:
                errors += 1
        dirs[:] = keep
        for filename in files:
            path = os.path.join(folder, filename)
            try:
                if os.path.islink(path):
                    continue
                st = os.stat(path, follow_symlinks=False)
                if st.st_dev != rootdev or (st.st_dev, st.st_ino) in seen_inodes:
                    continue
                seen_inodes.add((st.st_dev, st.st_ino))
                suffix = Path(filename).suffix.lower()
                category = next((k for k, extensions in EXTENSIONS.items() if suffix in extensions), 'other')
                totals[category] += st.st_size
                count += 1
            except OSError:
                errors += 1
    return totals, count, errors


class ColorBar(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.set_size_request(220, 22)
        self.connect('draw', self.paint)

    def paint(self, _widget, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        cr.set_source_rgb(0.16, 0.16, 0.16)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        total = sum(v for v, _ in self.parts)
        if total <= 0:
            return False
        offset = 0.0
        for amount, color in self.parts:
            width = w * amount / total
            cr.set_source_rgb(*rgb(color))
            cr.rectangle(offset, 0, width, h)
            cr.fill()
            offset += width
        return False


class Window(Gtk.Window):
    def __init__(self):
        super().__init__(title='BloodyDisk Lite')
        self.set_default_size(470, 510)
        self.set_size_request(320, 350)
        self.set_border_width(16)
        self.generation = 0
        self.scanning = False
        css = Gtk.CssProvider()
        css.load_from_data(b'''window {background: #000000;} label {color: #f5f5f5;}
          button, combobox button {background: #202020; color: #ffffff; border-radius: 6px; padding: 7px;}
          button:disabled {color: #777777;} .muted {color: #a3a3a3;} .warning {color: #fbbf24;}''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(outer)
        title = Gtk.Label()
        title.set_markup('<span size="x-large" weight="bold">BloodyDisk Lite</span>  <span foreground="#888888">v1.1</span>')
        title.set_xalign(0)
        outer.pack_start(title, False, False, 0)
        selector = Gtk.Box(spacing=8)
        selector.pack_start(Gtk.Label(label='Unidad:'), False, False, 0)
        self.combo = Gtk.ComboBoxText()
        self.combo.set_hexpand(True)
        self.combo.connect('changed', self.refresh)
        selector.pack_start(self.combo, True, True, 0)
        outer.pack_start(selector, False, False, 0)
        self.space = Gtk.Label(xalign=0)
        outer.pack_start(self.space, False, False, 0)
        self.bar = ColorBar()
        outer.pack_start(self.bar, False, False, 0)
        self.disk_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.pack_start(self.disk_rows, False, False, 0)
        self.warning = Gtk.Label(xalign=0)
        self.warning.set_line_wrap(True)
        outer.pack_start(self.warning, False, False, 0)
        sep = Gtk.Separator()
        outer.pack_start(sep, False, False, 0)
        subtitle = Gtk.Label(label='Archivos de mi carpeta personal', xalign=0)
        outer.pack_start(subtitle, False, False, 0)
        self.status = Gtk.Label(label='Pulsa Analizar para clasificar archivos (no modifica nada).', xalign=0)
        self.status.get_style_context().add_class('muted')
        self.status.set_line_wrap(True)
        outer.pack_start(self.status, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(100)
        outer.pack_start(scroll, True, True, 0)
        self.categories = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        scroll.add(self.categories)
        buttons = Gtk.Box(spacing=8)
        self.update_btn = Gtk.Button(label='Actualizar')
        self.update_btn.connect('clicked', self.reload_mounts)
        buttons.pack_start(self.update_btn, True, True, 0)
        self.scan_btn = Gtk.Button(label='Analizar')
        self.scan_btn.connect('clicked', self.start_scan)
        buttons.pack_start(self.scan_btn, True, True, 0)
        self.open_btn = Gtk.Button(label='Abrir carpeta')
        self.open_btn.connect('clicked', self.open_home)
        buttons.pack_start(self.open_btn, True, True, 0)
        outer.pack_start(buttons, False, False, 0)
        footer = Gtk.Label(label='Solo lectura · Sin servicios en segundo plano', xalign=0)
        footer.get_style_context().add_class('muted')
        outer.pack_start(footer, False, False, 0)
        self.reload_mounts()

    def row(self, parent, color, label, value):
        line = Gtk.Box(spacing=9)
        dot = Gtk.DrawingArea()
        dot.set_size_request(12, 12)
        def paint(widget, cr):
            cr.set_source_rgb(*rgb(color))
            cr.arc(6, 6, 5.5, 0, 2 * 3.141592653589793)
            cr.fill()
            return False
        dot.connect('draw', paint)
        line.pack_start(dot, False, False, 0)
        name = Gtk.Label(label=label, xalign=0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        line.pack_start(name, True, True, 0)
        value_label = Gtk.Label(label=value, xalign=1)
        line.pack_end(value_label, False, False, 0)
        parent.pack_start(line, False, False, 0)

    def reload_mounts(self, *_args):
        selected = self.combo.get_active_id()
        self.combo.handler_block_by_func(self.refresh)
        self.combo.remove_all()
        try:
            devices = mounts()
        except OSError:
            devices = [('/', 'Sistema')]
        for mount, device in devices:
            self.combo.append(mount, f'{mount}   ({device})')
        if devices:
            self.combo.set_active_id(selected if selected in dict(devices) else devices[0][0])
        self.combo.handler_unblock_by_func(self.refresh)
        self.refresh()

    def refresh(self, *_args):
        target = self.combo.get_active_id()
        if not target:
            return
        try:
            info = os.statvfs(target)
            total = info.f_blocks * info.f_frsize
            used = (info.f_blocks - info.f_bfree) * info.f_frsize
            free = info.f_bavail * info.f_frsize
            reserved = (info.f_bfree - info.f_bavail) * info.f_frsize
            self.space.set_text(f'Capacidad: {fmt(total)}   ·   Disponible: {fmt(free)}')
            self.bar.parts = [(used, PALETTE['used']), (free, PALETTE['free']),
                              (reserved, PALETTE['reserved'])]
            for item in self.disk_rows.get_children():
                self.disk_rows.remove(item)
            for label, amount, col in [('Ocupado', used, PALETTE['used']),
                                       ('Disponible', free, PALETTE['free']),
                                       ('Reservado / no disponible', reserved, PALETTE['reserved'])]:
                self.row(self.disk_rows, col, label, fmt(amount))
            self.disk_rows.show_all()
            self.bar.queue_draw()
            frac = free / total if total else 0
            self.warning.set_text('⚠ Menos del 10% disponible' if total and frac < .1 else '')
        except OSError as err:
            self.space.set_text(f'No se pudo consultar la unidad: {err}')

    def start_scan(self, *_args):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.set_sensitive(False)
        self.status.set_text('Analizando archivos personales… (solo lectura)')
        self.generation += 1
        gen = self.generation
        def worker():
            try:
                data = scan_home(os.path.expanduser('~'))
                GLib.idle_add(self.finish_scan, gen, data, None)
            except Exception as err:
                GLib.idle_add(self.finish_scan, gen, None, str(err))
        threading.Thread(target=worker, daemon=True).start()

    def finish_scan(self, gen, data, error):
        if gen != self.generation:
            return False
        self.scanning = False
        self.scan_btn.set_sensitive(True)
        if error:
            self.status.set_text('Error de análisis: ' + error)
            return False
        totals, count, errors = data
        for item in self.categories.get_children():
            self.categories.remove(item)
        for key in ('books', 'music', 'video', 'documents', 'images', 'other'):
            self.row(self.categories, PALETTE[key], NAMES[key], fmt(totals[key]))
        self.categories.show_all()
        suffix = f' · {errors} errores de acceso' if errors else ''
        self.status.set_text(f'{count} archivos analizados en Home{suffix}. Los tamaños son lógicos; no equivalen al espacio físico ocupado.')
        return False

    def open_home(self, *_args):
        try:
            subprocess.Popen(['xdg-open', os.path.expanduser('~')],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as err:
            self.status.set_text('No se pudo abrir la carpeta: ' + str(err))


if __name__ == '__main__':
    win = Window()
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
