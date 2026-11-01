#!/usr/bin/env python3
import io
import json
import queue
import subprocess
import threading
import tkinter as tk
import urllib.request
from PIL import Image, ImageTk

BG = "#101115"
PANEL = "#202229"
RED = "#D92D48"
WHITE = "#F5F5F5"

root = tk.Tk()
root.title("BloodyTube v0.2 — BloodyCat Edition")
root.geometry("720x520")
root.minsize(480, 320)
root.configure(bg=BG)

messages = queue.Queue()
photos = []
generation = 0

tk.Label(
    root, text="▶ BloodyTube",
    font=("DejaVu Sans", 21, "bold"),
    bg=BG, fg=RED
).pack(pady=(14, 10))

bar = tk.Frame(root, bg=BG)
bar.pack(fill="x", padx=15)

query = tk.Entry(
    bar, bg=PANEL, fg=WHITE,
    insertbackground=WHITE,
    font=("DejaVu Sans", 11),
    relief="flat"
)
query.pack(side="left", fill="x", expand=True, ipady=7)

status = tk.StringVar(value="Busca tus videos favoritos")

area = tk.Frame(root, bg=BG)
area.pack(fill="both", expand=True, padx=15, pady=12)

canvas = tk.Canvas(area, bg=BG, highlightthickness=0)
scroll = tk.Scrollbar(area, command=canvas.yview)
canvas.configure(yscrollcommand=scroll.set)

scroll.pack(side="right", fill="y")
canvas.pack(side="left", fill="both", expand=True)

results_frame = tk.Frame(canvas, bg=BG)
frame_id = canvas.create_window(
    (0, 0), window=results_frame, anchor="nw"
)

results_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)
canvas.bind(
    "<Configure>",
    lambda e: canvas.itemconfigure(frame_id, width=e.width)
)

def play(video_id):
    if not isinstance(video_id, str) or len(video_id) != 11:
        status.set("Enlace de video no válido")
        return

    url = "https://www.youtube.com/watch?v=" + video_id

    subprocess.Popen([
        "mpv",
        "--hwdec=auto-safe",
        "--ytdl-format=134+140/"
        "bestvideo[height<=360][vcodec^=avc1]+"
        "bestaudio[ext=m4a]/best[height<=360]",
        url
    ], start_new_session=True)

    status.set("Reproduciendo en MPV...")

def clear_results():
    photos.clear()
    for widget in results_frame.winfo_children():
        widget.destroy()

def add_result(index, item):
    vid = str(item.get("id") or "")
    if len(vid) != 11:
        return

    row = tk.Frame(results_frame, bg=PANEL)
    row.pack(fill="x", pady=3)

    pic = tk.Label(
        row, text="▶", bg="#151820",
        fg=RED, width=17, height=5
    )
    pic.pack(side="left", padx=7, pady=6)

    title = str(item.get("title") or "Sin título")
    channel = str(
        item.get("channel") or item.get("uploader") or ""
    )

    info = tk.Frame(row, bg=PANEL)
    info.pack(side="left", fill="both", expand=True, padx=6)

    tk.Label(
        info, text=title, bg=PANEL, fg=WHITE,
        font=("DejaVu Sans", 10, "bold"),
        wraplength=380, justify="left",
        anchor="w"
    ).pack(fill="x", pady=(12, 4))

    tk.Label(
        info, text=channel, bg=PANEL,
        fg="#AAB0BA", anchor="w"
    ).pack(fill="x")

    btn = tk.Button(
        row, text="▶", bg=RED, fg="white",
        relief="flat", command=lambda: play(vid)
    )
    btn.pack(side="right", padx=9)

    for widget in (row, pic, info):
        widget.bind(
            "<Double-Button-1>",
            lambda e, v=vid: play(v)
        )

    return pic, vid

def search_worker(term, token):
    try:
        proc = subprocess.run(
            [
                "yt-dlp", "--flat-playlist",
                "--dump-single-json", "--no-warnings",
                f"ytsearch10:{term}"
            ],
            capture_output=True, text=True, timeout=65
        )
        if proc.returncode:
            raise RuntimeError(
                proc.stderr.strip() or "Error de búsqueda"
            )

        data = json.loads(proc.stdout)
        items = [
            x for x in data.get("entries", [])
            if x and len(str(x.get("id") or "")) == 11
        ]
        messages.put(("results", token, items))

    except Exception as exc:
        messages.put(("error", token, str(exc)))

def image_worker(index, vid, token):
    try:
        url = (
            "https://i.ytimg.com/vi/"
            + vid + "/mqdefault.jpg"
        )

        with urllib.request.urlopen(url, timeout=10) as response:
            data = response.read(250000)

        img = Image.open(io.BytesIO(data))
        img.load()
        img = img.convert("RGB")
        img.thumbnail((120, 68))

        messages.put(("image", token, index, img))

    except Exception:
        pass

image_labels = {}

def poll():
    global image_labels
    try:
        while True:
            msg = messages.get_nowait()
            kind, token = msg[:2]

            if token != generation:
                continue

            if kind == "results":
                items = msg[2]
                clear_results()
                image_labels = {}

                for i, item in enumerate(items):
                    result = add_result(i, item)
                    if result:
                        label, vid = result
                        image_labels[i] = label
                        threading.Thread(
                            target=image_worker,
                            args=(i, vid, token),
                            daemon=True
                        ).start()

                status.set(
                    f"{len(items)} videos encontrados"
                    if items else "Sin resultados"
                )

            elif kind == "image":
                index, img = msg[2], msg[3]
                label = image_labels.get(index)
                if label and label.winfo_exists():
                    photo = ImageTk.PhotoImage(img)
                    photos.append(photo)
                    label.config(image=photo, text="",
                                 width=120, height=68)

            elif kind == "error":
                status.set("Error: " + msg[2][:120])

    except queue.Empty:
        pass

    root.after(100, poll)

def search():
    global generation
    term = query.get().strip()
    if not term:
        return

    generation += 1
    token = generation
    clear_results()
    status.set("Buscando en YouTube...")

    threading.Thread(
        target=search_worker,
        args=(term, token),
        daemon=True
    ).start()

tk.Button(
    bar, text="BUSCAR", command=search,
    bg=RED, fg="white", relief="flat",
    font=("DejaVu Sans", 10, "bold"),
    padx=12
).pack(side="right", padx=(7, 0), ipady=6)

query.bind("<Return>", lambda e: search())

tk.Label(
    root, textvariable=status,
    bg=BG, fg="#AAB0BA"
).pack(pady=(0, 10))

root.after(100, poll)
query.focus_set()
root.mainloop()
