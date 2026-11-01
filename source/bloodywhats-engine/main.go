package main

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"os/signal"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	_ "github.com/mattn/go-sqlite3"
	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow"
	waE2E "go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"google.golang.org/protobuf/proto"
)

type Command struct {
	Action string `json:"action"`
	To     string `json:"to"`
	Text   string `json:"text"`
}
type Message struct {
	Chat       string `json:"chat"`
	Text       string `json:"text"`
	Mine       bool   `json:"mine"`
	ID         string `json:"id"`
	Time       int64  `json:"time"`
	Sender     string `json:"sender,omitempty"`
	SenderName string `json:"sender_name,omitempty"`
}
type Contact struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}
type State struct {
	Messages []Message         `json:"messages"`
	Names    map[string]string `json:"names"`
}

type Engine struct {
	client    *whatsmeow.Client
	dir       string
	state     State
	mu        sync.Mutex
	outMu     sync.Mutex
	connected bool
}

func (e *Engine) emit(v any) {
	e.outMu.Lock()
	defer e.outMu.Unlock()
	_ = json.NewEncoder(os.Stdout).Encode(v)
}
func (e *Engine) err(msg string) { e.emit(map[string]any{"event": "error", "message": msg}) }
func (e *Engine) file() string   { return filepath.Join(e.dir, "history.json") }
func (e *Engine) load() {
	e.state = State{Messages: []Message{}, Names: map[string]string{}}
	b, err := os.ReadFile(e.file())
	if err == nil {
		_ = json.Unmarshal(b, &e.state)
	}
	if e.state.Names == nil {
		e.state.Names = map[string]string{}
	}
	if e.state.Messages == nil {
		e.state.Messages = []Message{}
	}
}
func (e *Engine) saveLocked() error {
	// Bound both number of text messages and actual data size. Never remove messages from WhatsApp itself.
	if len(e.state.Messages) > 300 {
		e.state.Messages = e.state.Messages[len(e.state.Messages)-300:]
	}
	var b []byte
	for {
		var err error
		b, err = json.Marshal(e.state)
		if err != nil {
			return err
		}
		if len(b) <= 4*1024*1024 || len(e.state.Messages) == 0 {
			break
		}
		e.state.Messages = e.state.Messages[1:]
	}
	tmp := e.file() + ".tmp"
	if err := os.WriteFile(tmp, b, 0600); err != nil {
		return err
	}
	return os.Rename(tmp, e.file())
}

// Unifica LID con PN solo cuando Whatsmeow conoce la relación.
func (e *Engine) canonicalChat(id string) string {
	jid, err := types.ParseJID(id)
	if err != nil || jid.Server != types.HiddenUserServer {
		return id
	}
	if e.client == nil || e.client.Store == nil ||
		e.client.Store.LIDs == nil {
		return id
	}

	ctx, cancel := context.WithTimeout(
		context.Background(), 3*time.Second)
	defer cancel()

	pn, err := e.client.Store.LIDs.GetPNForLID(ctx, jid)
	if err == nil && !pn.IsEmpty() {
		return pn.String()
	}
	return id
}

// Reorganiza el historial local conservando los mensajes.
func (e *Engine) reconcileChats() {
	e.mu.Lock()
	defer e.mu.Unlock()

	changed := false
	seen := make(map[string]bool)
	messages := make([]Message, 0, len(e.state.Messages))

	for _, m := range e.state.Messages {
		original := m.Chat
		m.Chat = e.canonicalChat(m.Chat)
		if m.Chat != original {
			changed = true
		}

		if m.ID != "" {
			key := m.Chat + "\x00" + m.ID
			if seen[key] {
				changed = true
				continue
			}
			seen[key] = true
		}
		messages = append(messages, m)
	}

	for id, name := range e.state.Names {
		canonical := e.canonicalChat(id)
		if canonical != id && name != "" {
			if e.state.Names[canonical] == "" {
				e.state.Names[canonical] = name
				changed = true
			}
		}
	}

	if changed {
		e.state.Messages = messages
		if err := e.saveLocked(); err != nil {
			e.err("Error guardando historial: " + err.Error())
		}
	}
}

func (e *Engine) addMessage(m Message) {
	if m.Text == "" || m.Chat == "" {
		return
	}
	m.Chat = e.canonicalChat(m.Chat)
	e.mu.Lock()
	for _, old := range e.state.Messages {
		if m.ID != "" && old.Chat == m.Chat && old.ID == m.ID {
			e.mu.Unlock()
			return
		}
	}
	e.state.Messages = append(e.state.Messages, m)
	err := e.saveLocked()
	e.mu.Unlock()
	if err != nil {
		e.err("No se pudo guardar el historial: " + err.Error())
	}
	e.emit(map[string]any{"event": "message", "message": m})
}
func (e *Engine) setName(id, name string) {
	if id == "" || name == "" {
		return
	}
	e.mu.Lock()
	if e.state.Names[id] != name {
		e.state.Names[id] = name
		_ = e.saveLocked()
	}
	e.mu.Unlock()
}
func (e *Engine) contacts() []Contact {
	if e.client != nil &&
		e.client.Store != nil &&
		e.client.Store.Contacts != nil {

		ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
		defer cancel()

		raw, err := e.client.Store.Contacts.GetAllContacts(ctx)
		if err != nil {
			e.err("Contactos: " + err.Error())
		}

		for jid, info := range raw {
			name := info.FullName
			if name == "" {
				name = info.FirstName
			}
			if name == "" {
				name = info.PushName
			}
			if name == "" {
				name = info.BusinessName
			}
			if name != "" {
				e.setName(jid.String(), name)
			}
		}
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	seen := map[string]bool{}
	for _, m := range e.state.Messages {
		seen[m.Chat] = true
	}
	for id := range e.state.Names {
		seen[id] = true
	}
	result := make([]Contact, 0, len(seen))
	for id := range seen {
		name := e.state.Names[id]
		if name == "" {
			name = strings.Split(id, "@")[0]
		}
		result = append(result, Contact{ID: id, Name: name})
	}
	sort.Slice(result, func(i, j int) bool { return strings.ToLower(result[i].Name) < strings.ToLower(result[j].Name) })
	return result
}
func (e *Engine) snapshot() {
	e.reconcileChats()
	cs := e.contacts()
	e.mu.Lock()
	msgs := append([]Message{}, e.state.Messages...)
	e.mu.Unlock()
	e.emit(map[string]any{"event": "snapshot", "contacts": cs, "messages": msgs, "linked": e.client.Store.ID != nil, "online": e.client.IsLoggedIn()})
}
func textOf(m *waE2E.Message) string {
	if m == nil {
		return ""
	}
	s := m.GetConversation()
	if s == "" {
		s = m.GetExtendedTextMessage().GetText()
	}
	return s
}
func (e *Engine) onEvent(evt any) {
	switch x := evt.(type) {
	case *events.Message:
		t := textOf(x.Message)
		if t == "" {
			return
		}
		chat := x.Info.Chat
		if x.Info.IsIncomingBroadcast() && !x.Info.Sender.IsEmpty() {
			chat = x.Info.Sender
		}
		e.addMessage(Message{Chat: chat.String(), Text: t, Mine: x.Info.IsFromMe, ID: x.Info.ID, Sender: x.Info.Sender.String(), SenderName: x.Info.PushName, Time: x.Info.Timestamp.Unix()})
	case *events.HistorySync:
		if x.Data == nil {
			return
		}
		for _, conv := range x.Data.GetConversations() {
			jid, err := types.ParseJID(conv.GetID())
			if err != nil {
				continue
			}
			e.setName(jid.String(), conv.GetName())
			for _, hm := range conv.GetMessages() {
				if hm.GetMessage() == nil {
					continue
				}
				parsed, err := e.client.ParseWebMessage(jid, hm.GetMessage())
				if err != nil || parsed == nil {
					continue
				}
				t := textOf(parsed.Message)
				if t == "" {
					continue
				}
				chat := parsed.Info.Chat
				if parsed.Info.IsIncomingBroadcast() && !parsed.Info.Sender.IsEmpty() {
					chat = parsed.Info.Sender
				}
				e.addMessage(Message{Chat: chat.String(), Text: t, Mine: parsed.Info.IsFromMe, ID: parsed.Info.ID, Sender: parsed.Info.Sender.String(), SenderName: parsed.Info.PushName, Time: parsed.Info.Timestamp.Unix()})
			}
		}
		e.snapshot()
	case *events.Connected:
		e.emit(map[string]any{"event": "connection", "online": true, "linked": true})
		_ = os.Remove(filepath.Join(e.dir, "login-qr.png"))
		e.snapshot()
	case *events.Disconnected:
		e.emit(map[string]any{"event": "connection", "online": false, "linked": e.client.Store.ID != nil})
	}
}
func (e *Engine) connect() {
	if e.client.IsLoggedIn() {
		e.snapshot()
		return
	}
	if e.client.Store.ID == nil {
		qr, err := e.client.GetQRChannel(context.Background())
		if err != nil {
			e.err("QR: " + err.Error())
			return
		}
		go func() {
			for event := range qr {
				switch event.Event {
				case "code":
					path := filepath.Join(e.dir, "login-qr.png")
					tmp := path + ".tmp"
					if err := qrcode.WriteFile(event.Code, qrcode.Medium, 320, tmp); err != nil {
						e.err("QR: " + err.Error())
						continue
					}
					_ = os.Chmod(tmp, 0600)
					if err := os.Rename(tmp, path); err == nil {
						e.emit(map[string]any{"event": "qr", "path": path})
					}
				case "success":
					e.emit(map[string]any{"event": "connection", "linked": true, "online": e.client.IsLoggedIn()})
					_ = os.Remove(filepath.Join(e.dir, "login-qr.png"))
				case "timeout", "error":
					e.err("Vinculación: " + event.Event)
					_ = os.Remove(filepath.Join(e.dir, "login-qr.png"))
				}
			}
		}()
	}
	if err := e.client.Connect(); err != nil {
		e.err("Conexión: " + err.Error())
	}
}
func (e *Engine) send(to, text string) {
	if !e.client.IsLoggedIn() {
		e.err("WhatsApp no está conectado")
		return
	}
	if strings.TrimSpace(text) == "" {
		return
	}
	jid, err := types.ParseJID(to)
	if err != nil {
		e.err("Destino inválido")
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	resp, err := e.client.SendMessage(ctx, jid, &waE2E.Message{Conversation: proto.String(text)})
	if err != nil {
		e.err("Envío fallido: " + err.Error())
		return
	}
	e.addMessage(Message{Chat: jid.String(), Text: text, Mine: true, ID: resp.ID, Time: time.Now().Unix()})
	e.emit(map[string]any{"event": "sent", "to": to})
}
func main() {
	home, err := os.UserHomeDir()
	if err != nil {
		panic(err)
	}
	dir := filepath.Join(home, ".local", "share", "bloodywhats-lite")
	if err := os.MkdirAll(dir, 0700); err != nil {
		panic(err)
	}
	if err := os.Chmod(dir, 0700); err != nil {
		panic(err)
	}
	path := filepath.Join(dir, "session.db")
	ctx := context.Background()
	db, err := sqlstore.New(ctx, "sqlite3", "file:"+path+"?_foreign_keys=on", nil)
	if err != nil {
		panic(err)
	}
	_ = os.Chmod(path, 0600)
	device, err := db.GetFirstDevice(ctx)
	if err != nil {
		panic(err)
	}
	cli := whatsmeow.NewClient(device, nil)
	e := &Engine{client: cli, dir: dir}
	e.load()
	e.reconcileChats()
	cli.AddEventHandler(e.onEvent)
	defer cli.Disconnect()
	e.emit(map[string]any{"event": "ready", "linked": cli.Store.ID != nil})
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	commands := make(chan Command, 32)
	go func() {
		defer close(commands)
		for scanner.Scan() {
			var c Command
			if json.Unmarshal(scanner.Bytes(), &c) == nil {
				commands <- c
			}
		}
	}()
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	for {
		select {
		case c, ok := <-commands:
			if !ok {
				return
			}
			switch c.Action {
			case "status", "list":
				e.snapshot()
			case "connect":
				go e.connect()
			case "send":
				go e.send(c.To, c.Text)
			case "quit":
				return
			default:
				e.err("Acción desconocida")
			}
		case <-sig:
			return
		}
	}
}
