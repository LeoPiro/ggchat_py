import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText
from irc.client import SimpleIRCClient, Event
from playsound import playsound
import re, threading, json, os, sys
from datetime import datetime

CONFIG_FILE     = "irc_config.json"
ICON_FILENAME   = "gg_fUv_icon.ico"
ALERT_FILENAME  = "alert.wav"
NOTIFY_FILENAME = "notify.mp3"

class IRCBot(SimpleIRCClient):
    def __init__(self, gui):
        super().__init__()
        self.gui   = gui
        self.users = set()

    def on_welcome(self, connection, event: Event):
        self.gui.append_text("Connected. Joining " + self.gui.channel + "...")
        connection.join(self.gui.channel)
        self.gui.set_disconnect_mode()

    def on_namreply(self, connection, event: Event):
        if len(event.arguments) >= 3:
            names = event.arguments[2].split()
            clean = {n.lstrip("@+~&%") for n in names}
            self.users.update(clean)
            self.gui.update_user_count(len(self.users))

    def on_join(self, connection, event: Event):
        nick = event.source.nick
        self.users.add(nick)
        self.gui.update_user_count(len(self.users))
        if nick != self.gui.nickname:
            self.gui.append_text(f"{nick} joined.")

    def on_part(self, connection, event: Event):
        nick = event.source.nick
        self.users.discard(nick)
        self.gui.update_user_count(len(self.users))
        # self.gui.append_text(f"{nick} left.")

    def on_quit(self, connection, event: Event):
        nick = event.source.nick
        self.users.discard(nick)
        self.gui.update_user_count(len(self.users))
        # self.gui.append_text(f"{nick} quit.")

    def on_pubmsg(self, connection, event: Event):
        nick, msg = event.source.nick, event.arguments[0]
        # Display
        self.gui.append_text(f"<{nick}> {msg}")
        # Quiet notify tone on any message
        if self.gui.notify_var.get():
            notify_path = os.path.join(getattr(sys, '_MEIPASS', os.path.abspath('.')),
                                       NOTIFY_FILENAME)
            threading.Thread(target=playsound, args=(notify_path,), daemon=True).start()
        # Alert tone on keyword
        if self.gui.alert_var.get() and re.search(r"\b(alert)\b", msg, re.IGNORECASE):
            alert_path = os.path.join(getattr(sys, '_MEIPASS', os.path.abspath('.')),
                                      ALERT_FILENAME)
            threading.Thread(target=playsound, args=(alert_path,), daemon=True).start()

    def on_disconnect(self, connection, event: Event):
        self.gui.append_text("Disconnected from server.")
        self.users.clear()
        self.gui.update_user_count(0)
        self.gui.set_connect_mode()

    def on_nicknameinuse(self, connection, event: Event):
        self.gui.ignore_disconnect = True
        self.gui.master.after(0, lambda: messagebox.showerror(
            "Nickname Error", "Nickname already in use. Please choose another."
        ))
        self.gui.master.after(0, lambda: self.gui.append_text(
            "Nickname already in use. Please choose another."
        ))
        connection.disconnect()
        self.gui.master.after(0, self.gui.set_connect_mode)
        self.gui.master.after(100, lambda: self.gui.nick_entry.focus_set())

    def send_message(self, msg):
        if self.connection and self.connection.is_connected():
            self.connection.privmsg(self.gui.channel, msg)


class IRCGui:
    def __init__(self, master):
        self.master       = master
        self.bot          = None
        self.nickname     = None
        self.user_window  = None
        self.user_listbox = None
        self.ignore_disconnect = False

        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        self.icon_path = os.path.join(base, ICON_FILENAME)

        try:
            master.iconbitmap(self.icon_path)
        except:
            img = tk.PhotoImage(file=self.icon_path)
            master.tk.call('wm', 'iconphoto', master._w, img)

        master.title("GG Chat")
        master.geometry("800x250")
        master.eval('tk::PlaceWindow . center')
        master.resizable(True, True)

        self.config    = self.load_config()
        self.bg, self.fg   = "#1e1e1e", "#ffffff"
        self.entry_bg      = "#2b2b2b"
        self.button_bg     = "#3a3a3a"
        master.configure(bg=self.bg)
        master.grid_rowconfigure(1, weight=1)
        master.grid_columnconfigure(0, weight=1)

        # --- Top Controls ---
        top = tk.Frame(master, bg=self.bg)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(5,0))

        tk.Label(top, text="Nickname:", bg=self.bg, fg=self.fg)\
          .pack(side=tk.LEFT, padx=(10,0))
        self.nick_entry = tk.Entry(
            top, width=12,
            bg=self.entry_bg, fg=self.fg,
            insertbackground=self.fg
        )
        self.nick_entry.insert(0, self.config.get("nickname","LeoPyChat"))
        self.nick_entry.pack(side=tk.LEFT, padx=5)

        self.users_button = tk.Button(
            top, text="Users: 0", command=self.toggle_users_window,
            bg=self.button_bg, fg=self.fg, activebackground="#555555"
        )
        self.users_button.pack(side=tk.LEFT, padx=10)

        # new Notify-all checkbox
        self.notify_var = tk.BooleanVar(value=self.config.get("sound_notify", False))
        tk.Checkbutton(
            top, text="🔔 Notify", variable=self.notify_var,
            command=self.save_notify_setting,
            bg=self.bg, fg=self.fg,
            selectcolor=self.bg, activebackground=self.bg
        ).pack(side=tk.RIGHT, padx=5)

        # existing Alerts-on-keyword checkbox
        self.alert_var = tk.BooleanVar(value=self.config.get("sound_alerts", True))
        tk.Checkbutton(
            top, text="🔔 Alerts", variable=self.alert_var,
            command=self.save_alert_setting,
            bg=self.bg, fg=self.fg,
            selectcolor=self.bg, activebackground=self.bg
        ).pack(side=tk.RIGHT, padx=5)

        # manual “send alert!” button
        tk.Button(
            top, text="Send Alert!", command=lambda: self.send_message(custom_text="alert!"),
            bg=self.button_bg, fg=self.fg, activebackground="#555555"
        ).pack(side=tk.RIGHT, padx=5)

        self.pin_button = tk.Button(
            top, text="📌 Pin", command=self.toggle_pin,
            bg=self.button_bg, fg=self.fg, activebackground="#555555"
        )
        self.pin_button.pack(side=tk.RIGHT, padx=5)

        self.connect_button = tk.Button(
            top, text="Connect", command=self.connect_irc,
            bg=self.button_bg, fg=self.fg, activebackground="#555555"
        )
        self.connect_button.pack(side=tk.RIGHT, padx=5)


        # --- Chat Display (font +1, mention tag) ---
        self.text_area = ScrolledText(
            master, state="disabled",
            bg=self.entry_bg, fg=self.fg,
            font=("Segoe UI", 11),
            insertbackground=self.fg,
            selectbackground="#444"
        )
        self.text_area.tag_config("mention", foreground="yellow")
        self.text_area.grid(row=1, column=0, columnspan=2,
                            sticky="nsew", padx=10, pady=5)

        # --- Entry + Send ---
        entry = tk.Frame(master, bg=self.bg)
        entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0,5), padx=10)
        entry.grid_columnconfigure(0, weight=1)

        self.entry = tk.Entry(entry, bg=self.entry_bg, fg=self.fg, insertbackground=self.fg)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0,5))
        self.entry.bind("<Return>", self.send_message)

        tk.Button(
            entry, text="Send", command=self.send_message,
            bg=self.button_bg, fg=self.fg, activebackground="#555555"
        ).grid(row=0, column=1)

        master.bind("<F1>", lambda e: self.send_message(custom_text="alert!"))

        # keep top+entry visible when shrunken
        master.update_idletasks()
        h0 = top.winfo_height(); h2 = entry.winfo_height()
        master.minsize(200, h0 + h2 + 20)

        # IRC details
        self.channel = "#lobby"
        self.server  = "45.79.137.244"
        self.port    = 6667

    def connect_irc(self):
        self.nickname = self.nick_entry.get().strip() or "LeoPyChat"
        # merge into config
        self.config["nickname"]      = self.nickname
        self.config["sound_alerts"]  = self.alert_var.get()
        self.config["sound_notify"]  = self.notify_var.get()
        self.save_config(self.config)

        if self.bot:
            self.append_text("Already connected.")
            return

        self.bot = IRCBot(self)
        threading.Thread(target=self._start_irc_thread, daemon=True).start()

    def _start_irc_thread(self):
        try:
            self.bot.connect(self.server, self.port, self.nickname)
            self.bot.start()
        except Exception as e:
            self.append_text(f"Connection error: {e}")
            self.set_connect_mode()

    def disconnect_irc(self):
        if self.bot and self.bot.connection.is_connected():
            self.bot.connection.quit("User disconnected")

    def set_connect_mode(self):
        self.connect_button.config(text="Connect", command=self.connect_irc)
        self.bot = None

    def set_disconnect_mode(self):
        self.connect_button.config(text="Disconnect", command=self.disconnect_irc)

    def send_message(self, event=None, custom_text=None):
        msg = custom_text or self.entry.get()
        if msg and self.bot:
            self.bot.send_message(msg)
            self.append_text(f"<You> {msg}")
            if not custom_text:
                self.entry.delete(0, tk.END)

    def append_text(self, text):
        ts   = datetime.now().strftime("%H:%M")
        line = f"[{ts}] {text}\n"
        self.text_area.configure(state="normal")
        # if mention, apply tag
        if self.nickname and self.nickname.lower() in text.lower():
            self.text_area.insert(tk.END, line, "mention")
        else:
            self.text_area.insert(tk.END, line)
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)

    def update_user_count(self, cnt):
        self.users_button.config(text=f"Users: {cnt}")
        if self.user_listbox:
            self.user_listbox.delete(0, tk.END)
            for nick in sorted(self.bot.users):
                self.user_listbox.insert(tk.END, nick)

    def toggle_users_window(self):
        if self.user_window and self.user_window.winfo_exists():
            self.user_window.destroy()
            self.user_window = None
            self.user_listbox = None
            return
        if not self.bot:
            messagebox.showinfo("Users", "Not connected.")
            return
        self.user_window = tk.Toplevel(self.master)
        self.user_window.title("Users in Channel")
        self.user_window.geometry("200x300")
        self.user_window.protocol("WM_DELETE_WINDOW", self.toggle_users_window)
        self.user_listbox = tk.Listbox(self.user_window)
        self.user_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        for nick in sorted(self.bot.users):
            self.user_listbox.insert(tk.END, nick)

    def toggle_pin(self):
        pinned = not self.master.attributes("-topmost")
        self.master.wm_attributes("-topmost", pinned)
        self.pin_button.config(relief=tk.SUNKEN if pinned else tk.RAISED)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                return json.load(open(CONFIG_FILE))
            except:
                pass
        return {}

    def save_config(self, data):
        try:
            json.dump(data, open(CONFIG_FILE, "w"))
        except:
            pass

    def save_alert_setting(self):
        self.config["sound_alerts"] = self.alert_var.get()
        self.save_config(self.config)

    def save_notify_setting(self):
        self.config["sound_notify"] = self.notify_var.get()
        self.save_config(self.config)


if __name__ == "__main__":
    root = tk.Tk()
    gui = IRCGui(root)
    root.mainloop()
