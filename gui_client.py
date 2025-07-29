import asyncio
import irc3
import threading
import tkinter as tk
from tkinter import scrolledtext

class IRCGUI:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.bot = None
        self.channel = "#lobby"

        # --- GUI Setup ---
        self.root = tk.Tk()
        self.root.title("IRC3 + Tkinter Client")
        self.root.geometry("800x500")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.pinned = False

        top = tk.Frame(self.root)
        top.pack(fill=tk.X)

        self.server_entry = tk.Entry(top, width=25)
        self.server_entry.insert(0, "45.79.137.244")
        self.server_entry.pack(side=tk.LEFT, padx=5)

        self.nick_entry = tk.Entry(top, width=15)
        self.nick_entry.insert(0, "MyBot")
        self.nick_entry.pack(side=tk.LEFT, padx=5)

        self.channel_entry = tk.Entry(top, width=15)
        self.channel_entry.insert(0, self.channel)
        self.channel_entry.pack(side=tk.LEFT, padx=5)

        tk.Button(top, text="Connect", command=self.start_irc).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="📌 Pin", command=self.toggle_pin).pack(side=tk.LEFT)

        self.output = scrolledtext.ScrolledText(self.root, state='disabled')
        self.output.pack(expand=True, fill=tk.BOTH)

        self.input_box = tk.Entry(self.root)
        self.input_box.pack(fill=tk.X)
        self.input_box.bind("<Return>", self.send_msg)

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.root.wm_attributes("-topmost", self.pinned)

    def start_irc(self):
        server = self.server_entry.get()
        nick = self.nick_entry.get()
        self.channel = self.channel_entry.get()

        config = {
            'nick': nick,
            'autojoins': [self.channel],
            'host': server,
            'includes': [__name__],
            'loop': self.loop,
        }

        @irc3.plugin
        class GUIPlugin:
            def __init__(self, bot):
                self.bot = bot

            @irc3.event(irc3.rfc.PRIVMSG)
            def on_privmsg(self, mask, event, target, data):
                msg = f"<{mask.nick}> {data}"
                self.bot.gui.print_to_chat(msg)

            @irc3.event(irc3.rfc.JOIN)
            def on_join(self, mask, channel):
                self.bot.gui.print_to_chat(f"*** {mask.nick} joined {channel}")

            @irc3.event(irc3.rfc.PING)
            def on_ping(self, server):
                self.bot.send_line(f'PONG {server}')

        config['gui'] = self  # so plugin can access the GUI
        self.bot = irc3.IrcBot(**config)
        threading.Thread(target=self.loop.run_until_complete, args=(self.bot.run(),), daemon=True).start()

    def send_msg(self, event=None):
        msg = self.input_box.get()
        if self.bot and msg:
            self.bot.privmsg(self.channel, msg)
            self.print_to_chat(f"<You> {msg}")
            self.input_box.delete(0, tk.END)

    def print_to_chat(self, message):
        self.output.configure(state='normal')
        self.output.insert(tk.END, message + "\n")
        self.output.see(tk.END)
        self.output.configure(state='disabled')

    def quit(self):
        if self.bot:
            self.bot.quit("Bye")
        self.loop.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    client = IRCGUI()
    client.run()
