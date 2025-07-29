import random
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk, colorchooser
import tkinter.font as tkfont
import threading
import json, os, sys, time, webbrowser, requests, base64
from websocket import WebSocketApp
from playsound import playsound
import re
from datetime import datetime

CURRENT_VERSION = "1.0.0"
CONFIG_FILE     = "chat_config.json"
SERVER_URL      = "http://45.79.137.244:8800".rstrip("/")
ICON_FILE       = "gg_fUv_icon.ico"
ALERT_FILENAME  = "alert.wav"
NOTIFY_FILENAME = "notify.mp3"

# UI Colors
BG_COLOR      = "#1e1e1e"
FG_COLOR      = "#ffffff"
ENTRY_BG      = "#2b2b2b"
BUTTON_BG     = "#3a3a3a"
BUTTON_ACTIVE = "#555555"

def _decode_jwt(token: str) -> dict:
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded)
    except:
        return {}

class ChatClient:
    def __init__(self, gui, token):
        self.gui   = gui
        self.token = token
        self.ws    = None

    def start(self):
        scheme = "wss" if SERVER_URL.startswith("https") else "ws"
        host   = SERVER_URL.split("://", 1)[1]
        ws_url = f"{scheme}://{host}/ws?token={self.token}"
        self.ws = WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def on_open(self, ws):
        self.gui.append_text("[System] Connected to chat server.")
        self.gui.connect_btn.config(text="Disconnect", command=self.gui.disconnect)

    def on_error(self, ws, error):
        self.gui.append_text(f"[System] WS Error: {error}")

    def on_close(self, ws, code, msg):
        if code == 4001 or (msg and "invalid" in msg.lower()):
            self.gui.config.pop("token", None)
            self.gui.save_config()
            self.gui.append_text("[System] Token expired or invalid. Please log in again.")
        else:
            self.gui.append_text(f"[System] Disconnected (code={code}, msg={msg}).")
        self.gui.on_disconnected()

    def send(self, msg):
        if self.ws:
            self.ws.send(msg)

    def on_message(self, ws, message):
        if self.gui.notify_var.get():
            notify_path = os.path.join(getattr(sys, '_MEIPASS', os.path.abspath('.')), NOTIFY_FILENAME)
            threading.Thread(target=playsound, args=(notify_path,), daemon=True).start()
        text = message.split("]", 1)[-1]
        if self.gui.alert_var.get() and re.search(r"\balert\b", text, re.IGNORECASE):
            alert_path = os.path.join(getattr(sys, '_MEIPASS', os.path.abspath('.')), ALERT_FILENAME)
            threading.Thread(target=playsound, args=(alert_path,), daemon=True).start()
        self.gui.append_text(message)

class ChatGui:
    def __init__(self, master):
        self.master = master
        self.client = None
        self.token = None
        self.state = None
        self.user_colors = {}
        self.is_officer = False
        self.username = None
        self.config = self.load_config()
        self.is_maximized = False

        self.custom_self_color = self.config.get("self_msg_color", "yellow")
        self.custom_others_color = self.config.get("others_msg_color", FG_COLOR)

        self.notify_var = tk.BooleanVar(value=self.config.get("sound_notify", False))
        self.alert_var  = tk.BooleanVar(value=self.config.get("sound_alerts", True))

        master.title("GG Chat")
        master.geometry("800x300")
        master.configure(bg=BG_COLOR)
        master.bind('<F1>', lambda e: self.on_send(custom="[!ALERT!]"))

        content = tk.Frame(master, bg=BG_COLOR)
        content.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(content, bg=BG_COLOR)
        top.pack(fill=tk.X, pady=(5, 0))

        self.users_button = tk.Button(top, text="Online: 0", bg=BUTTON_BG, fg=FG_COLOR,
                                      activebackground=BUTTON_ACTIVE, relief=tk.RAISED, bd=1)
        self.users_button.pack(side=tk.LEFT, padx=10)

        self.connect_btn = tk.Button(top, text="Login with Discord", command=self.start_oauth,
                                     bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE)
        self.connect_btn.pack(side=tk.RIGHT, padx=5)

        self.settings_btn = tk.Button(top, text="⚙ Settings", command=self.open_settings_window,
                                      bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE)
        self.settings_btn.pack(side=tk.RIGHT, padx=5)

        self.pin_btn = tk.Button(top, text="📌 Pin", command=self.toggle_pin,
                                 bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE)
        self.pin_btn.pack(side=tk.RIGHT, padx=5)

        tk.Button(top, text="Send Alert!", command=lambda: self.on_send(custom="[!ALERT!]"),
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE).pack(side=tk.RIGHT, padx=5)

        chat_wrapper = tk.Frame(content, bg=BG_COLOR)
        chat_wrapper.pack(fill=tk.BOTH, expand=True)
        chat_wrapper.grid_rowconfigure(0, weight=1)
        chat_wrapper.grid_columnconfigure(0, weight=1)

        self.text_frame = tk.Frame(chat_wrapper, bg=BG_COLOR)
        self.text_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(5, 0))
        self.text_frame.grid_rowconfigure(0, weight=1)
        self.text_frame.grid_columnconfigure(0, weight=1)

        font_size = self.config.get("font_size", 13)
        self.text_area = tk.Text(self.text_frame, state="disabled", wrap=tk.WORD,
                                 bg=ENTRY_BG, fg=FG_COLOR, font=("Segoe UI", font_size),
                                 insertbackground=FG_COLOR, relief=tk.FLAT)
        self.text_area.grid(row=0, column=0, sticky="nsew")

        self.text_area.tag_configure("mention", foreground="yellow", font=("Segoe UI", font_size, "bold"))
        self.text_area.tag_configure("self_msg", foreground=self.custom_self_color, font=("Segoe UI", font_size, "bold"))
        self.text_area.tag_configure("others_msg", foreground=self.custom_others_color, font=("Segoe UI", font_size))

        scrollbar = ttk.Scrollbar(self.text_frame, orient="vertical",
                                  command=self.text_area.yview, style="Vertical.TScrollbar")
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.text_area.config(yscrollcommand=scrollbar.set)

        entry_frame = tk.Frame(chat_wrapper, bg=BG_COLOR, height=35)
        entry_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        entry_frame.grid_propagate(False)

        self.entry = tk.Entry(entry_frame, bg=ENTRY_BG, fg=FG_COLOR, insertbackground=FG_COLOR)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind('<Return>', self.on_send)

        tk.Button(entry_frame, text="Send", command=self.on_send,
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE).pack(side=tk.RIGHT)

        cached_token = self.config.get("token")
        self.token = cached_token

        if cached_token:
            payload = _decode_jwt(cached_token)
            if payload.get("exp", 0) > time.time():
                self.config["token"] = cached_token
                self.save_config()
                self.username = payload.get("username")
                self.is_officer = payload.get("is_officer", False)
                self.append_text(f"[System] Resuming session as '{self.username}'")
                self.start_chat()
            else:
                self.config.pop("token", None)
                self.save_config()
                self.token = None

        self.poll_online_users()


    def append_text(self, text):
        ts = datetime.now().strftime("%H:%M")
        full_line = f"[{ts}] {text}\n"
        self.text_area.configure(state="normal")

        match = re.match(r"\[(.*?)\] \[(.*?)\](.*)", full_line)
        if match:
            timestamp = match.group(1)
            sender = match.group(2)
            message = match.group(3) + "\n"

            # Insert timestamp
            self.text_area.insert("end", f"[{timestamp}] ")

            # Insert name with random color tag
            name_tag = f"user_{sender}"
            if name_tag not in self.text_area.tag_names():
                rand_color = f"#{random.randint(0, 0xFFFFFF):06x}"
                self.text_area.tag_configure(name_tag, foreground=rand_color, font=("Segoe UI", 13, "bold"))
            self.text_area.insert("end", f"[{sender}]", name_tag)

            # Insert message with custom message color
            msg_tag = "self_msg" if sender.lower() == (self.username or '').lower() else "others_msg"
            self.text_area.insert("end", message, msg_tag)
        else:
            self.text_area.insert("end", full_line)

        self.text_area.configure(state="disabled")
        self.text_area.see("end")

    def get_user_color(self, username):
        return f"user_{username}"

    def open_settings_window(self):
        if hasattr(self, 'settings_win') and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return

        self.settings_win = tk.Toplevel(self.master)
        self.settings_win.title("Settings")
        self.settings_win.configure(bg=BG_COLOR)
        self.settings_win.geometry("300x300")
        self.settings_win.resizable(False, False)

        tk.Label(self.settings_win, text="Font Size:", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=10, pady=(10, 0))
        font_slider = tk.Scale(self.settings_win, from_=8, to=24, orient=tk.HORIZONTAL,
                               bg=BG_COLOR, fg=FG_COLOR, troughcolor=BUTTON_BG,
                               highlightthickness=0, relief=tk.FLAT)
        current_font_size = tkfont.Font(font=self.text_area.cget("font")).actual("size")
        font_slider.set(current_font_size)
        font_slider.pack(fill="x", padx=10)
        font_slider.bind("<ButtonRelease-1>", lambda e: self.set_font_size(font_slider.get()))

        tk.Checkbutton(self.settings_win, text="🔔 Sound on message", variable=self.notify_var,
                       bg=BG_COLOR, fg=FG_COLOR, selectcolor=BG_COLOR, activebackground=BG_COLOR
                       ).pack(anchor="w", padx=10, pady=(10, 0))

        tk.Checkbutton(self.settings_win, text="🔔 Sound on alert", variable=self.alert_var,
                       bg=BG_COLOR, fg=FG_COLOR, selectcolor=BG_COLOR, activebackground=BG_COLOR
                       ).pack(anchor="w", padx=10)

        def pick_color_self():
            color_code = colorchooser.askcolor(title="Choose your own text color")[1]
            if color_code:
                self.custom_self_color = color_code
                self.text_area.tag_configure("self_msg", foreground=color_code)
                self.config["self_msg_color"] = color_code
                self.save_config()

        def pick_color_others():
            color_code = colorchooser.askcolor(title="Choose others' message color")[1]
            if color_code:
                self.custom_others_color = color_code
                self.text_area.tag_configure("others_msg", foreground=color_code)
                self.config["others_msg_color"] = color_code
                self.save_config()

        tk.Button(self.settings_win, text="Pick Your Text Color", command=pick_color_self,
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE).pack(pady=5, padx=10)

        tk.Button(self.settings_win, text="Pick Others' Text Color", command=pick_color_others,
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE).pack(pady=5, padx=10)

    def set_font_size(self, size):
        new_font = ("Segoe UI", size)
        self.text_area.config(font=new_font)
        self.text_area.tag_configure("mention", font=new_font + ("bold",))
        self.text_area.tag_configure("self_msg", font=new_font + ("bold",))
        for tag in self.user_colors:
            self.text_area.tag_configure(f"user_{tag}", font=new_font + ("bold",))
        self.config["font_size"] = size
        self.save_config()

    def poll_online_users(self):
        def fetch():
            try:
                resp = requests.get("http://45.79.137.244:8801/online_count", timeout=5)
                if resp.ok:
                    count = resp.json().get("online", 0)
                    self.users_button.config(text=f"Online: {count}")
            except Exception as e:
                print(f"Failed to fetch online count: {e}")
            finally:
                self.master.after(15000, self.poll_online_users)
        threading.Thread(target=fetch, daemon=True).start()

    def load_config(self):
        try:
            return json.load(open(CONFIG_FILE))
        except:
            return {}

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def get_user_color(self, username):
        if username not in self.user_colors:
            self.user_colors[username] = self.custom_others_color
            self.text_area.tag_configure(f"user_{username}", foreground=self.custom_others_color, font=("Segoe UI", 13, "bold"))
        return f"user_{username}"

    def start_oauth(self):
        if self.token:
            payload = _decode_jwt(self.token)
            if payload.get("exp", 0) > time.time():
                self.username = payload.get("username")
                self.is_officer = payload.get("is_officer", False)
                self.append_text(f"[System] Already authenticated as '{self.username}'. Reconnecting...")
                self.start_chat()
                return

        resp = requests.get(f"{SERVER_URL}/start")
        data = resp.json()
        self.state = data['state']
        webbrowser.open(data['auth_url'])
        self.append_text("[System] Waiting for authentication...")
        threading.Thread(target=self.poll_token, daemon=True).start()

    def poll_token(self):
        while True:
            time.sleep(1)
            resp = requests.get(f"{SERVER_URL}/token", params={"state": self.state})
            info = resp.json()
            token = info.get('token')
            self.is_officer = info.get('is_officer', False)
            if token:
                self.token = token
                self.config["token"] = token
                self.save_config()
                payload = _decode_jwt(token)
                self.username = payload.get('username')
                self.append_text("[System] Authentication successful!")
                self.start_chat()
                break

    def start_chat(self):
        self.client = ChatClient(self, self.token)
        self.client.start()

    def disconnect(self):
        if self.client and self.client.ws:
            self.client.ws.close()

    def on_disconnected(self):
        self.client = None
        self.username = None
        self.connect_btn.config(text="Login with Discord", command=self.start_oauth)
        self.append_text("[System] Disconnected. Click login to reconnect.")

    def on_send(self, event=None, custom=None):
        msg = custom or self.entry.get().strip()
        if msg and self.client:
            self.client.send(msg)
            if not custom:
                self.entry.delete(0, tk.END)

    def toggle_pin(self):
        pinned = not self.master.attributes("-topmost")
        self.master.wm_attributes("-topmost", pinned)
        self.pin_btn.config(relief=tk.SUNKEN if pinned else tk.RAISED)

if __name__ == "__main__":
    root = tk.Tk()
    if getattr(sys, 'frozen', False):
        icon_path = os.path.join(sys._MEIPASS, 'gg_fUv_icon.ico')
    else:
        icon_path = os.path.abspath('gg_fUv_icon.ico')
    root.iconbitmap(default=icon_path)

    gui = ChatGui(root)
    root.mainloop()
