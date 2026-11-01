#!/usr/bin/env python3
import sqlite3
from pathlib import Path
import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Poppler", "0.18")
from gi.repository import Gtk, GLib, Gdk, Poppler

ROOT = Path(__file__).resolve().parent
DATA = Path.home() / ".local/share/bloodyreader-lite"
DATA.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(DATA / "library.db")
db.execute("""CREATE TABLE IF NOT EXISTS books
              (path TEXT PRIMARY KEY, page INTEGER DEFAULT 0)""")
db.commit()

class Reader(Gtk.Window):
    def __init__(self):
        super().__init__(title="BloodyReader Lite")
        self.set_default_size(850, 600)
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_reader_key)
        Gtk.Settings.get_default().set_property(
            "gtk-application-prefer-dark-theme", True)

        self.doc = None
        self.path = None
        self.page_num = 0
        self.spread_mode = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(root)

        bar = Gtk.Box(spacing=6)
        root.pack_start(bar, False, False, 5)

        for title, callback in [

        ]:
            btn = Gtk.Button(label=title)
            btn.connect("clicked", callback)
            bar.pack_start(btn, False, False, 2)


        self.spread_button = Gtk.ToggleButton(label="📖 Libro abierto")
        self.spread_button.connect("toggled", self.toggle_spread)
        bar.pack_start(self.spread_button, False, False, 2)

        self.counter = Gtk.Label(label="BloodyReader Lite")
        bar.pack_end(self.counter, False, False, 5)

        pane = Gtk.Paned()
        pane.set_position(220)
        root.pack_start(pane, True, True, 0)

        sidebar = Gtk.ScrolledWindow()
        self.books = Gtk.ListBox()
        self.books.connect("row-activated", self.open_row)
        sidebar.add(self.books)
        pane.pack1(sidebar, False, False)

        self.scroll = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        self.image.set_valign(Gtk.Align.START)
        self.image.set_halign(Gtk.Align.FILL)
        # BLOODYREADER_CENTERED_READING_V1
        # Centrado sin modificar escala ni resolución.
        self.image.set_halign(Gtk.Align.CENTER)
        self.image.set_valign(Gtk.Align.CENTER)

        self.page_align = Gtk.Alignment.new(0.5, 0.5, 0, 0)
        self.page_align.set_padding(18, 18, 18, 18)
        self.page_align.add(self.image)

        self.scroll.add(self.page_align)
        pane.pack2(self.scroll, True, False)
        self._resize_source = None
        self.scroll.connect('size-allocate', self.on_reader_resize)



        # Biblioteca visual y pantalla de lectura.
        root.remove(bar)
        pane.remove(self.scroll)
        root.remove(pane)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(
            Gtk.StackTransitionType.CROSSFADE
        )
        self.stack.set_transition_duration(150)
        root.pack_start(self.stack, True, True, 0)

        library = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8
        )

        library_header = Gtk.Box(spacing=12)
        library_header.set_margin_start(15)
        library_header.set_margin_end(15)
        library_header.set_margin_top(12)

        heading = Gtk.Label()
        heading.set_markup(
            "<span size='x-large' weight='bold'>"
            "Mi biblioteca</span>"
        )
        library_header.pack_start(heading, False, False, 0)

        add_button = Gtk.Button(label="+ Agregar PDF")
        add_button.connect("clicked", self.add_pdf)
        folder_button = Gtk.Button(label="+ Agregar carpeta")
        folder_button.connect("clicked", self.add_folder)
        library_header.pack_end(
            folder_button, False, False, 0
        )

        library_header.pack_end(add_button, False, False, 0)
        library.pack_start(library_header, False, False, 0)

        gallery_scroll = Gtk.ScrolledWindow()
        gallery_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC
        )

        self.gallery = Gtk.FlowBox()
        self.gallery.set_selection_mode(Gtk.SelectionMode.NONE)
        self.gallery.set_column_spacing(18)
        self.gallery.set_row_spacing(18)
        self.gallery.set_min_children_per_line(1)
        self.gallery.set_max_children_per_line(6)
        self.gallery.set_homogeneous(False)
        self.gallery.set_valign(Gtk.Align.START)
        self.gallery.set_margin_start(16)
        self.gallery.set_margin_end(16)
        self.gallery.set_margin_top(12)
        self.gallery.set_margin_bottom(16)
        self.gallery.connect(
            "child-activated", self.open_gallery_item
        )

        gallery_scroll.add(self.gallery)
        library.pack_start(gallery_scroll, True, True, 0)

        reader = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6
        )

        back = Gtk.Button()
        # BLOODYREADER_BOOKS_ICON_V1
        back.set_image(Gtk.Image.new_from_file(
            str(ROOT / "books-symbolic.svg")
        ))
        back.set_tooltip_text("Volver a Mi biblioteca")
        back.connect("clicked", self.go_library)


        reader.pack_start(bar, False, False, 0)
        reader.pack_start(self.scroll, True, True, 0)

        self.stack.add_named(library, "library")
        self.stack.add_named(reader, "reader")
        self.stack.set_visible_child_name("library")

        # BLOODYREADER SIDEBAR V0.3
        reader.remove(bar)
        root.remove(self.stack)

        layout = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0
        )
        root.pack_start(layout, True, True, 0)

        sidebar = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8
        )
        sidebar.set_size_request(220, -1)
        sidebar.set_margin_start(8)
        sidebar.set_margin_end(8)
        sidebar.set_margin_top(12)

        heading = Gtk.Label(label="BloodyReader Lite")
        sidebar.pack_start(heading, False, False, 0)

        separator = Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL
        )
        sidebar.pack_start(separator, False, False, 4)

        # BLOODYREADER_FOLIATE_NAV_V1
        self.library_indicator = Gtk.Button()
        indicator_box = Gtk.Box(spacing=9)
        indicator_box.pack_start(
            Gtk.Image.new_from_file(
                str(ROOT / "books-symbolic.svg")
            ),
            False, False, 0
        )
        indicator_box.pack_start(
            Gtk.Label(label="Mi biblioteca"),
            False, False, 0
        )
        self.library_indicator.add(indicator_box)

        self.library_indicator.set_sensitive(False)
        self.library_indicator.get_style_context().add_class(
            "suggested-action"
        )
        sidebar.pack_start(
            self.library_indicator, False, False, 0
        )

        back.set_halign(Gtk.Align.START)
        sidebar.pack_start(back, False, False, 0)
        self.library_back_button = back
        back.set_no_show_all(True)
        back.hide()


        bar.set_orientation(Gtk.Orientation.VERTICAL)
        bar.set_spacing(7)

        self.counter.set_line_wrap(True)
        # Ocultar el título y contador del panel lateral.
        # Se conserva el widget para que el código pueda actualizarlo.
        self.counter.set_no_show_all(True)
        self.counter.hide()
        sidebar.pack_start(bar, False, False, 0)

        layout.pack_start(sidebar, False, False, 0)
        layout.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
            False, False, 0
        )
        layout.pack_start(self.stack, True, True, 0)


        self.refresh_library()


    def get_cover(self, filename):
        import hashlib

        cache = DATA / "covers"
        cache.mkdir(parents=True, exist_ok=True)

        path = Path(filename)
        if not path.is_file():
            return None

        signature = (
            str(path.resolve()) + ":" +
            str(path.stat().st_mtime_ns) + ":" +
            str(path.stat().st_size)
        )
        key = hashlib.sha256(signature.encode()).hexdigest()
        target = cache / (key + ".png")

        if target.is_file():
            return str(target)

        try:
            uri = GLib.filename_to_uri(str(path.resolve()), None)
            doc = Poppler.Document.new_from_file(uri, None)

            if not doc or doc.get_n_pages() < 1:
                return None

            page = doc.get_page(0)
            width, height = page.get_size()

            scale = min(120 / width, 165 / height)
            w = max(1, round(width * scale))
            h = max(1, round(height * scale))

            surface = cairo.ImageSurface(
                cairo.FORMAT_ARGB32, w, h
            )
            ctx = cairo.Context(surface)
            ctx.set_source_rgb(1, 1, 1)
            ctx.paint()
            ctx.scale(scale, scale)
            page.render(ctx)
            surface.write_to_png(str(target))

            return str(target)

        except (GLib.Error, OSError, ValueError,
                RuntimeError, cairo.Error):
            return None



    def get_total_pages(self, path):
        # Guardamos el total para no abrir cada PDF
        # en cada actualización de la biblioteca.
        db.execute("""
            CREATE TABLE IF NOT EXISTS book_meta (
                path TEXT PRIMARY KEY,
                total INTEGER NOT NULL
            )
        """)
        db.commit()

        result = db.execute(
            "SELECT total FROM book_meta WHERE path=?",
            (path,)
        ).fetchone()

        if result:
            return result[0]

        try:
            uri = GLib.filename_to_uri(
                str(Path(path).resolve()), None
            )
            doc = Poppler.Document.new_from_file(uri, None)
            total = doc.get_n_pages()
            if total < 1:
                return 0

            db.execute(
                "INSERT OR REPLACE INTO book_meta VALUES (?,?)",
                (path, total)
            )
            db.commit()
            return total
        except (GLib.Error, OSError, ValueError):
            return 0

    def refresh_library(self):
        for child in self.gallery.get_children():
            self.gallery.remove(child)

        rows = db.execute(
            "SELECT path, page FROM books "
            "ORDER BY path COLLATE NOCASE"
        ).fetchall()

        for path, page in rows:
            child = Gtk.FlowBoxChild()
            child.path = path

            card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=7
            )
            card.set_size_request(145, -1)

            cover = self.get_cover(path)
            if cover:
                image = Gtk.Image.new_from_file(cover)
            else:
                image = Gtk.Image.new_from_icon_name(
                    "x-office-document",
                    Gtk.IconSize.DIALOG
                )

            image.set_halign(Gtk.Align.CENTER)
            card.pack_start(image, False, False, 0)

            title = Gtk.Label(label=Path(path).stem)
            title.set_line_wrap(True)
            title.set_line_wrap_mode(2)
            title.set_max_width_chars(19)
            title.set_lines(2)
            title.set_ellipsize(3)
            title.set_justify(Gtk.Justification.CENTER)
            title.set_halign(Gtk.Align.CENTER)
            card.pack_start(title, False, False, 0)

            # Progreso de lectura.
            total = self.get_total_pages(path)

            if total > 1:
                percent = round(
                    min(100, max(0, page * 100 / (total - 1)))
                )
            else:
                percent = 0

            footer = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=4
            )
            footer.set_size_request(120, -1)
            footer.set_halign(Gtk.Align.CENTER)

            progress = Gtk.Label(label=f"{percent}%")
            progress.get_style_context().add_class(
                "dim-label"
            )
            footer.pack_start(progress, False, False, 0)

            spacer = Gtk.Box()
            footer.pack_start(spacer, True, True, 0)

            # Menú de tres puntos.
            menu_button = Gtk.MenuButton(label="⋯")
            menu_button.set_relief(Gtk.ReliefStyle.NONE)
            menu_button.set_tooltip_text(
                "Opciones del libro"
            )

            popover = Gtk.Popover.new(menu_button)

            remove_button = Gtk.Button(
                label="Quitar de biblioteca"
            )
            remove_button.set_relief(Gtk.ReliefStyle.NONE)
            remove_button.set_margin_top(5)
            remove_button.set_margin_bottom(5)
            remove_button.set_margin_start(8)
            remove_button.set_margin_end(8)

            remove_button.connect(
                "clicked",
                self.remove_library_book,
                path
            )

            popover.add(remove_button)
            remove_button.show()
            menu_button.set_popover(popover)

            footer.pack_end(menu_button, False, False, 0)
            card.pack_start(footer, False, False, 0)

            child.add(card)
            self.gallery.add(child)

        self.gallery.show_all()

    def remove_library_book(self, button, path):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="¿Quitar este libro de la biblioteca?"
        )

        dialog.format_secondary_text(
            Path(path).name +
            "\n\nEl archivo PDF original NO será borrado."
        )

        dialog.add_button(
            "Cancelar", Gtk.ResponseType.CANCEL
        )
        dialog.add_button(
            "Quitar de biblioteca", Gtk.ResponseType.OK
        )

        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            return

        db.execute("DELETE FROM books WHERE path=?", (path,))
        db.execute(
            "DELETE FROM book_meta WHERE path=?", (path,)
        )
        db.commit()

        self.refresh_library()

    def open_gallery_item(self, flowbox, child):
        self.open_book(child.path)

    def go_library(self, *_):
        self.stack.set_visible_child_name("library")
        self.library_indicator.show()
        self.library_back_button.hide()


    def import_books(self, filenames):
        paths = sorted({
            str(Path(name).resolve())
            for name in filenames
            if Path(name).is_file()
            and Path(name).suffix.lower() == ".pdf"
        })

        if not paths:
            return

        # Inserción por lotes. Respeta el progreso existente.
        db.executemany(
            "INSERT OR IGNORE INTO books(path,page) VALUES (?,0)",
            [(name,) for name in paths]
        )
        db.commit()

        # Actualizar la biblioteca una sola vez.
        self.refresh_library()

    def add_pdf(self, *_):
        dialog = Gtk.FileChooserDialog(
            title="Agregar libros PDF",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            "Cancelar", Gtk.ResponseType.CANCEL,
            "Agregar", Gtk.ResponseType.OK
        )

        dialog.set_select_multiple(True)

        pdf_filter = Gtk.FileFilter()
        pdf_filter.set_name("Documentos PDF")
        pdf_filter.add_mime_type("application/pdf")
        dialog.add_filter(pdf_filter)

        filenames = []
        if dialog.run() == Gtk.ResponseType.OK:
            filenames = dialog.get_filenames()

        dialog.destroy()

        if filenames:
            self.import_books(filenames)

    def add_folder(self, *_):
        dialog = Gtk.FileChooserDialog(
            title="Seleccionar carpeta de libros",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            "Cancelar", Gtk.ResponseType.CANCEL,
            "Importar", Gtk.ResponseType.OK
        )

        folder = None
        if dialog.run() == Gtk.ResponseType.OK:
            folder = dialog.get_filename()

        dialog.destroy()

        if not folder:
            return

        base = Path(folder)
        try:
            filenames = [
                str(f)
                for f in base.rglob("*")
                if f.is_file()
                and f.suffix.lower() == ".pdf"
            ]
        except OSError as exc:
            self.show_import_error(str(exc))
            return

        self.import_books(filenames)

    def show_import_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Error importando libros"
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def open_row(self, widget, row):
        self.open_book(row.path)

    def open_book(self, filename):
        if not Path(filename).is_file():
            self.counter.set_text("Archivo no encontrado")
            return

        try:
            uri = GLib.filename_to_uri(filename, None)
            doc = Poppler.Document.new_from_file(uri, None)
        except GLib.Error as e:
            self.counter.set_text("Error PDF: " + str(e))
            return

        if doc is None or doc.get_n_pages() == 0:
            self.counter.set_text("PDF vacío o no compatible")
            return

        self.doc = doc
        self.path = filename
        result = db.execute(
            "SELECT page FROM books WHERE path=?", (filename,)
        ).fetchone()
        self.page_num = min(
            max(0, result[0] if result else 0),
            doc.get_n_pages() - 1
        )
        self.stack.set_visible_child_name("reader")
        self.library_indicator.hide()
        self.library_back_button.show()
        self.render_page()


    def toggle_spread(self, button):
        self.spread_mode = button.get_active()
        if self.doc:
            self.render_page()

    def on_reader_resize(self, widget, allocation):
        if not self.doc:
            return
        if self._resize_source is not None:
            GLib.source_remove(self._resize_source)
        self._resize_source = GLib.timeout_add(150, self._finish_resize)

    def _finish_resize(self):
        self._resize_source = None
        self.render_page()
        return False

    def render_page(self):
        if self.doc is None:
            return

        count = self.doc.get_n_pages()
        indices = [self.page_num]
        if self.spread_mode and self.page_num + 1 < count:
            indices.append(self.page_num + 1)

        pages = [self.doc.get_page(i) for i in indices]
        sizes = [page.get_size() for page in pages]

        gap = 12 if len(pages) == 2 else 0
        total_width = sum(w for w, h in sizes) + gap
        max_height = max(h for w, h in sizes)

        # Conservar los tamaños anteriores al diseño Foliate.
        # Compensamos el ancho del antiguo panel lateral.
        available = max(
            100,
            self.scroll.get_allocated_width() - 232
        )

        if self.spread_mode:
            scale = (available / total_width) * 1.15
        else:
            # Mismo tamaño que una página del modo libro abierto.
            scale = available / (sizes[0][0] * 2 + 12) * 1.20

        # BLOODYREADER_EXTRA_SCALE

        scale *= 1.10

        w = max(1, int(total_width * scale))
        h = max(1, int(max_height * scale))

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        context = cairo.Context(surface)
        context.set_source_rgb(0.18, 0.18, 0.18)
        context.paint()

        offset = 0
        for page, (pw, ph) in zip(pages, sizes):
            context.save()
            context.translate(offset * scale, 0)
            context.scale(scale, scale)
            context.set_source_rgb(1, 1, 1)
            context.rectangle(0, 0, pw, ph)
            context.fill()
            page.render(context)
            context.restore()
            offset += pw + gap

        surface.flush()
        pixbuf = Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
        self.image.set_from_pixbuf(pixbuf)

        visible = str(self.page_num + 1)
        if len(indices) == 2:
            visible += "-" + str(self.page_num + 2)

        self.counter.set_text(
            f"{Path(self.path).stem} — {visible}/{count}"
        )
        db.execute(
            "UPDATE books SET page=? WHERE path=?",
            (self.page_num, self.path)
        )
        db.commit()

    def on_reader_key(self, widget, event):
        # Solo navegar cuando un libro está abierto.
        if not self.doc:
            return False

        if self.stack.get_visible_child_name() != "reader":
            return False

        if event.keyval == Gdk.KEY_Right:
            self.next_page()
            return True

        if event.keyval == Gdk.KEY_Left:
            self.previous()
            return True

        return False

    def next_page(self, *_):
        if self.doc:
            step = 2 if self.spread_mode else 1
            new_page = self.page_num + step
            if new_page < self.doc.get_n_pages():
                self.page_num = new_page
                self.render_page()

    def previous(self, *_):
        if self.doc:
            step = 2 if self.spread_mode else 1
            if self.page_num > 0:
                self.page_num = max(0, self.page_num - step)
                self.render_page()

win = Reader()
win.show_all()
Gtk.main()
