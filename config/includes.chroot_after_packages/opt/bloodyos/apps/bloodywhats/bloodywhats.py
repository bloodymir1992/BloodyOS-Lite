#!/usr/bin/env python3
"""BloodyWhats Lite — GTK3 front-end for one local Go process."""
import json
import os
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / 'bloodywhats-engine'
ICON = ROOT / 'bloodywhats-cat-yellow.png'

class BloodyWhats(Gtk.Window):
    def __init__(self):
        super().__init__(title='BloodyWhats Lite — BloodyCat')
        self.set_default_size(850, 550)
        self.set_border_width(8)
        if ICON.is_file():
            try:
                self.set_icon_from_file(str(ICON))
            except Exception:
                pass
        self.hidden_path = (
            Path.home() / '.local/share/bloodywhats-lite/hidden-chats.json'
        )
        try:
            self.hidden_chats = set(
                json.loads(self.hidden_path.read_text(encoding='utf-8'))
            )
        except (OSError, ValueError, TypeError):
            self.hidden_chats = set()
        self.show_hidden = False
        # BLOODYWHATS_FAVORITES_V1
        self.favorites_path = (
            Path.home() / '.local/share/bloodywhats-lite/favorites.json'
        )
        try:
            saved = json.loads(
                self.favorites_path.read_text(encoding='utf-8')
            )
            self.favorites = set(saved) if isinstance(saved, list) else set()
        except (OSError, ValueError, TypeError):
            self.favorites = set()
        self.favorites_only = False
        self.contacts = []
        self.messages = []
        self.active = None
        self.online = False
        self.linked = False
        self.proc = None

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(main)
        top = Gtk.Box(spacing=8)
        main.pack_start(top, False, False, 0)
        title = Gtk.Label(label='🐈 BloodyWhats Lite')
        top.pack_start(title, False, False, 5)
        self.link = Gtk.Button(label='Vincular / Conectar')
        self.link.connect('clicked', self.connect)
        top.pack_end(self.link, False, False, 0)
        self.reload_button = Gtk.Button(label='Actualizar')
        self.reload_button.connect('clicked', lambda *_: self.send_cmd('list'))
        top.pack_end(self.reload_button, False, False, 0)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_position(250)
        main.pack_start(split, True, True, 0)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        split.pack1(left, resize=False, shrink=False)
        tabs = Gtk.Box(spacing=4)
        left.pack_start(tabs, False, False, 0)

        self.all_tab = Gtk.ToggleButton(label='Todos los chats')
        self.fav_tab = Gtk.ToggleButton(label='⭐ Favoritos')

        # BLOODYWHATS_GROUPS_V1
        self.groups_tab = Gtk.ToggleButton(label='👥 Grupos')

        tabs.pack_start(self.all_tab, True, True, 0)
        tabs.pack_start(self.fav_tab, True, True, 0)
        tabs.pack_start(self.groups_tab, True, True, 0)

        self.all_tab.connect('toggled', self.change_chat_tab, 'all')
        self.fav_tab.connect('toggled', self.change_chat_tab, 'favorites')
        self.groups_tab.connect('toggled', self.change_chat_tab, 'groups')
        self.all_tab.set_active(True)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Buscar contactos...')
        self.search.connect('search-changed', lambda *_: self.draw_contacts())
        left.pack_start(self.search, False, False, 0)
        leftscroll = Gtk.ScrolledWindow()
        left.pack_start(leftscroll, True, True, 0)
        self.contact_list = Gtk.ListBox()
        self.contact_list.connect('row-selected', self.select_chat)
        Gtk.Window.connect(self, 'key-press-event', self.hidden_shortcut)
        leftscroll.add(self.contact_list)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        split.pack2(right, resize=True, shrink=False)
        self.header = Gtk.Label(label='Selecciona una conversación')
        right.pack_start(self.header, False, False, 8)
        scroll = Gtk.ScrolledWindow()
        right.pack_start(scroll, True, True, 0)
        self.text = Gtk.TextView()
        self.text.set_editable(False)
        self.text.set_cursor_visible(False)
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text.set_left_margin(10)
        self.text.set_right_margin(10)
        scroll.add(self.text)
        self.scroll = scroll
        entry_line = Gtk.Box(spacing=5)
        right.pack_start(entry_line, False, False, 0)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text('Mensaje de texto...')
        self.entry.connect('activate', self.send_message)
        entry_line.pack_start(self.entry, True, True, 0)
        emojis = Gtk.Button(label='😀')
        emojis.connect('clicked', self.emoji_menu)
        entry_line.pack_start(emojis, False, False, 0)
        self.send_button = Gtk.Button(label='Enviar')
        self.send_button.connect('clicked', self.send_message)
        entry_line.pack_start(self.send_button, False, False, 0)
        self.status = Gtk.Label(label='Sin conexión — mensajes reales desactivados', xalign=0)
        main.pack_start(self.status, False, False, 2)
        self.qr_win = None
        if ICON.is_file():
            self.tray_icon = Gtk.StatusIcon.new_from_file(str(ICON))
        else:
            self.tray_icon = Gtk.StatusIcon.new_from_icon_name(
                'mail-message-new'
            )
        self.tray_icon.set_tooltip_text('BloodyWhats Lite')
        self.tray_icon.set_visible(True)
        self.tray_icon.connect('activate', self.on_tray_activate)
        self.tray_icon.connect('popup-menu', self.on_tray_menu)

        Gtk.Window.connect(self, 'delete-event', self.on_window_close)
        Gtk.Window.connect(self, 'destroy', self.shutdown)
        self.update_send_enabled()
        self.start_engine()

    def start_engine(self):
        (Path.home() / '.local/share/bloodywhats-lite').mkdir(
            parents=True, exist_ok=True
        )
        if not ENGINE.is_file():
            self.status.set_text('Falta el motor Go: ' + str(ENGINE))
            return
        try:
            self.proc = subprocess.Popen(
                [str(ENGINE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
                cwd=str(Path.home() / '.local/share/bloodywhats-lite'),
            )
        except OSError as exc:
            self.status.set_text('Error iniciando motor: ' + str(exc))
            return
        threading.Thread(target=self.read_engine, daemon=True).start()
        self.send_cmd('list')
        self.send_cmd('connect')

    def read_engine(self):
        for line in self.proc.stdout:
            try:
                data = json.loads(line)
            except (ValueError, TypeError):
                continue
            GLib.idle_add(self.on_event, data)
        GLib.idle_add(self.engine_closed)

    def engine_closed(self):
        self.online = False
        self.update_send_enabled()
        self.status.set_text('Motor cerrado')
        return False

    def send_cmd(self, action, **kwargs):
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            self.proc.stdin.write(json.dumps({'action': action, **kwargs}, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            self.status.set_text('No se pudo comunicar con el motor')

    def connect(self, *_):
        if self.online:
            self.send_cmd('list')
            return
        self.status.set_text('Conectando...')
        self.send_cmd('connect')

    def on_event(self, data):
        kind = data.get('event')
        if kind == 'ready':
            self.linked = bool(data.get('linked'))
            self.status.set_text('Sesión guardada: pulsa Conectar' if self.linked else 'Sin vincular: pulsa Vincular / Conectar')
        elif kind == 'snapshot':
            self.linked = bool(data.get('linked'))
            self.online = bool(data.get('online'))
            self.contacts = data.get('contacts') or []
            self.messages = data.get('messages') or []
            self.draw_contacts()
            self.render_messages()
            self.status.set_text('WhatsApp conectado' if self.online else 'Sin conexión — no se enviarán mensajes')
        elif kind == 'message':
            msg = data.get('message')
            if isinstance(msg, dict):
                if not any(x.get('id') == msg.get('id') and x.get('chat') == msg.get('chat') for x in self.messages):
                    self.messages.append(msg)
                    if msg.get('mine') is False and self.online:
                        try:
                            subprocess.Popen(
                                ['paplay',
                                 '/usr/share/sounds/freedesktop/stereo/message-new-instant.oga'],
                                env={**__import__('os').environ,
                                     'PULSE_SERVER': 'unix:/run/user/1000/pulse/native'},
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                        except OSError:
                            pass
                if not any(x.get('id') == msg.get('chat') for x in self.contacts):
                    ident = msg.get('chat', '')
                    self.contacts.append({'id': ident, 'name': ident.split('@')[0]})
                    self.draw_contacts()
                self.render_messages()
        elif kind == 'qr':
            self.show_qr(data.get('path'))
            self.status.set_text('Escanea el QR en WhatsApp > Dispositivos vinculados')
        elif kind == 'connection':
            self.online = bool(data.get('online'))
            self.linked = bool(data.get('linked'))
            if self.online and self.qr_win is not None:
                self.qr_win.destroy()
                self.qr_win = None
            self.status.set_text('WhatsApp conectado' if self.online else 'WhatsApp desconectado')
            if self.online:
                self.send_cmd('list')
        elif kind == 'error':
            self.status.set_text('Error: ' + str(data.get('message', 'Desconocido')))
        self.update_send_enabled()
        return False

    def show_qr(self, path):
        expected = Path.home() / '.local/share/bloodywhats-lite/login-qr.png'
        if path != str(expected):
            return
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file(str(expected))
        except (GLib.Error, OSError):
            return
        if self.qr_win is None:
            self.qr_win = Gtk.Window(title='Vincular BloodyWhats Lite')
            self.qr_win.set_transient_for(self)
            self.qr_win.set_default_size(380, 420)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            outer.set_border_width(15)
            self.qr_win.add(outer)
            outer.pack_start(Gtk.Label(label='WhatsApp > Dispositivos vinculados > Vincular'), False, False, 5)
            self.qr_img = Gtk.Image()
            outer.pack_start(self.qr_img, True, True, 0)
            outer.pack_start(Gtk.Label(label='No compartas este QR con nadie'), False, False, 4)
            self.qr_win.connect('destroy', lambda *_: setattr(self, 'qr_win', None))
        self.qr_img.set_from_pixbuf(pix)
        self.qr_win.show_all()

    def change_chat_tab(self, button, tab):
        if not button.get_active():
            return

        self.chat_tab = tab
        self.favorites_only = (tab == 'favorites')

        for name, widget in (
            ('all', self.all_tab),
            ('favorites', self.fav_tab),
            ('groups', self.groups_tab),
        ):
            if name != tab and widget.get_active():
                widget.set_active(False)

        self.draw_contacts()

    def save_favorites(self):
        self.favorites_path.parent.mkdir(
            parents=True, exist_ok=True, mode=0o700
        )
        temporary = self.favorites_path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(sorted(self.favorites)),
            encoding='utf-8'
        )
        temporary.chmod(0o600)
        temporary.replace(self.favorites_path)

    def toggle_favorite(self, widget, chat_id):
        previous = set(self.favorites)
        if chat_id in self.favorites:
            self.favorites.remove(chat_id)
        else:
            self.favorites.add(chat_id)

        try:
            self.save_favorites()
        except OSError as exc:
            self.favorites = previous
            self.status.set_text(
                'Error guardando favoritos: ' + str(exc)
            )
            return

        self.draw_contacts()

    def save_hidden_chats(self):
        self.hidden_path.parent.mkdir(
            parents=True, exist_ok=True, mode=0o700
        )
        temporary = self.hidden_path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(sorted(self.hidden_chats)), encoding='utf-8'
        )
        temporary.chmod(0o600)
        temporary.replace(self.hidden_path)

    def hidden_shortcut(self, widget, event):
        from gi.repository import Gdk
        if (event.state & Gdk.ModifierType.CONTROL_MASK
                and event.keyval in (Gdk.KEY_h, Gdk.KEY_H)):
            self.show_hidden = not self.show_hidden
            self.draw_contacts()
            self.status.set_text(
                'Mostrando conversaciones ocultas'
                if self.show_hidden else 'Conversaciones ocultas'
            )
            return True
        return False

    def chat_context_menu(self, row, event):
        if event.button != 3:
            return False

        menu = Gtk.Menu()

        favorite = row.chat_id in self.favorites
        fav_item = Gtk.MenuItem(
            label='Quitar de favoritos' if favorite
            else '⭐ Agregar a favoritos'
        )
        fav_item.connect(
            'activate', self.toggle_favorite, row.chat_id
        )
        menu.append(fav_item)
        menu.append(Gtk.SeparatorMenuItem())

        hidden = row.chat_id in self.hidden_chats
        item = Gtk.MenuItem(
            label='Restaurar conversación' if hidden
            else 'Ocultar conversación'
        )
        item.connect(
            'activate', self.toggle_hidden_chat, row.chat_id
        )
        menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def toggle_hidden_chat(self, widget, chat_id):
        previous = set(self.hidden_chats)
        if chat_id in self.hidden_chats:
            self.hidden_chats.remove(chat_id)
        else:
            self.hidden_chats.add(chat_id)

        try:
            self.save_hidden_chats()
        except OSError as exc:
            self.hidden_chats = previous
            self.status.set_text('Error guardando cambio: ' + str(exc))
            return

        if chat_id == self.active and chat_id in self.hidden_chats:
            self.active = None
            self.update_send_enabled()

        self.draw_contacts()

    def draw_contacts(self):
        wanted = self.active
        for child in self.contact_list.get_children():
            self.contact_list.remove(child)
        query = self.search.get_text().casefold()
        latest = {}
        for message in self.messages:
            chat = message.get('chat')
            stamp = message.get('time') or 0
            if chat:
                latest[chat] = max(latest.get(chat, 0), stamp)

        ordered_contacts = sorted(
            self.contacts,
            key=lambda contact: latest.get(contact.get('id'), 0),
            reverse=True
        )

        for contact in ordered_contacts:
            chat_id = contact.get('id', '')

            if self.favorites_only and chat_id not in self.favorites:
                continue

            if getattr(self, 'chat_tab', 'all') == 'groups':
                if not chat_id.endswith('@g.us'):
                    continue
            if chat_id in self.hidden_chats and not self.show_hidden:
                continue
            if chat_id not in self.hidden_chats and self.show_hidden:
                continue
            label = contact.get('name') or chat_id
            if query and query not in label.casefold():
                continue
            row = Gtk.ListBoxRow()
            row.chat_id = contact.get('id')
            row.connect('button-press-event', self.chat_context_menu)
            line = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=4
            )

            lbl = Gtk.Label(label=label, xalign=0)
            lbl.set_ellipsize(3)
            lbl.set_margin_top(8)
            lbl.set_margin_bottom(8)
            lbl.set_margin_start(8)
            line.pack_start(lbl, True, True, 0)

            star = Gtk.Button(
                label='★' if chat_id in self.favorites else '☆'
            )
            star.set_tooltip_text(
                'Quitar de favoritos'
                if chat_id in self.favorites
                else 'Agregar a favoritos'
            )
            star.set_relief(Gtk.ReliefStyle.NONE)
            star.connect('clicked', self.toggle_favorite, chat_id)
            line.pack_end(star, False, False, 4)

            row.add(line)
            self.contact_list.add(row)
            if row.chat_id == wanted:
                self.contact_list.select_row(row)
        self.contact_list.show_all()

    def select_chat(self, widget, row):
        if row is None:
            return
        self.active = row.chat_id
        self.render_messages()
        self.update_send_enabled()

    def render_messages(self):
        if not self.active:
            return
        name = next((c.get('name') for c in self.contacts if c.get('id') == self.active), self.active)
        self.header.set_text('💬 ' + str(name))
        msgs = sorted((m for m in self.messages if m.get('chat') == self.active), key=lambda m: m.get('time', 0))
        def sender_label(m):
            if m.get('mine'):
                return 'Tú'

            sender = m.get('sender') or ''
            saved_name = next(
                (c.get('name') for c in self.contacts
                 if c.get('id') == sender and c.get('name')),
                None
            )

            return (
                saved_name
                or m.get('sender_name')
                or sender.split('@')[0]
                or ('Remitente desconocido'
                    if '@g.us' in self.active else str(name))
            )

        lines = [
            sender_label(m) + ': ' + (m.get('text') or '')
            for m in msgs[-150:]
        ]
        self.text.get_buffer().set_text('\n\n'.join(lines) if lines else 'Sin mensajes de texto disponibles')
        GLib.idle_add(self.scroll_bottom)

    def scroll_bottom(self):
        adj = self.scroll.get_vadjustment()
        adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))
        return False

    def update_send_enabled(self):
        self.send_button.set_sensitive(self.online and bool(self.active))
        self.entry.set_sensitive(self.online and bool(self.active))

    def send_message(self, *_):
        message = self.entry.get_text().strip()
        if not message or not self.active or not self.online:
            return
        self.send_cmd('send', to=self.active, text=message)
        self.entry.set_text('')
        self.status.set_text('Enviando...')

    def emoji_menu(self, button):
        emojis = ['😀','😁','😂','🤣','😊','😍','🥰','😘','😎','🤔','😭','😡','👍','👏','🙏','💪','👋','❤️','💕','🔥','🎉','💀','🐈','🚀','💯','😴','🤯','😅','😉','🤩']
        pop = Gtk.Popover.new(button)
        grid = Gtk.Grid(column_spacing=3, row_spacing=3, margin=8)
        for i, symbol in enumerate(emojis):
            b = Gtk.Button(label=symbol)
            b.set_relief(Gtk.ReliefStyle.NONE)
            def chosen(_, value=symbol):
                self.entry.insert_text(value, self.entry.get_position())
                self.entry.grab_focus()
                pop.popdown()
            b.connect('clicked', chosen)
            grid.attach(b, i % 6, i // 6, 1, 1)
        pop.add(grid)
        grid.show_all()
        pop.popup()

    def on_window_close(self, *_):
        if self.tray_icon and self.tray_icon.is_embedded():
            self.hide()
            return True
        return False

    def on_tray_activate(self, *_):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()
            self.present()

    def on_tray_menu(self, icon, button, activate_time):
        menu = Gtk.Menu()

        show_item = Gtk.MenuItem(label='Mostrar BloodyWhats')
        show_item.connect('activate', lambda *_: self.show_window())
        menu.append(show_item)

        quit_item = Gtk.MenuItem(label='Salir completamente')
        quit_item.connect('activate', lambda *_: self.destroy())
        menu.append(quit_item)

        menu.show_all()
        menu.popup(
            None, None, Gtk.StatusIcon.position_menu,
            icon, button, activate_time
        )

    def show_window(self):
        self.show_all()
        self.present()

    def shutdown(self, *_):
        self.send_cmd('quit')
        if self.proc and self.proc.poll() is None:
            GLib.timeout_add(1000, self.force_stop)
        Gtk.main_quit()

    def force_stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        return False

if __name__ == '__main__':
    if not ENGINE.exists():
        raise SystemExit('No se encontró bloodywhats-engine junto al archivo Python')
    w = BloodyWhats()
    w.show_all()
    Gtk.main()
