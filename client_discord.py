import random
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk, colorchooser
import tkinter.font as tkfont
import threading
import json, os, sys, time, webbrowser, requests, base64, subprocess, tempfile
from websocket import WebSocketApp
import re
from datetime import datetime
import queue
import concurrent.futures

# Import playsound with fallback
try:
    from playsound import playsound
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False
    def playsound(*args, **kwargs):
        pass  # No-op fallback

# Import winsound for Windows-native audio (more reliable)
try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False

try:
    # Check Python version first before importing CEF
    import sys
    if sys.version_info >= (3, 13):
        CEF_AVAILABLE = False
    else:
        from cefpython3 import cefpython as cef
        CEF_AVAILABLE = True
except ImportError:
    CEF_AVAILABLE = False
except Exception as e:
    CEF_AVAILABLE = False

CURRENT_VERSION = "2.0.3"
CONFIG_FILE     = "chat_config.json"
SERVER_URL      = "http://45.79.137.244:8800".rstrip("/")
ICON_FILE       = "gg_fUv_icon.ico"
ALERT_FILENAME  = "alert.wav"
NOTIFY_FILENAME = "notify.wav"

# Check if running from PyInstaller bundle
def is_frozen():
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

# UI Colors
BG_COLOR      = "#1e1e1e"
FG_COLOR      = "#ffffff"
ENTRY_BG      = "#2b2b2b"
BUTTON_BG     = "#3a3a3a"
BUTTON_ACTIVE = "#555555"

class SoundManager:
    """Robust sound manager with proper resource handling"""
    def __init__(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="SoundPlayer")
        self.sound_cache = {}
        self._prepare_sounds()
    
    def _prepare_sounds(self):
        """Pre-load and validate sound file paths"""
        try:
            base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
            self.sound_cache['notify'] = os.path.join(base_path, NOTIFY_FILENAME)
            self.sound_cache['alert'] = os.path.join(base_path, ALERT_FILENAME)
            
            # Validate files exist
            for sound_type, path in self.sound_cache.items():
                if not os.path.exists(path):
                    print(f"Warning: Sound file not found: {path}")
                    # Try alternative paths
                    alt_path = os.path.join(os.path.abspath('.'), os.path.basename(path))
                    if os.path.exists(alt_path):
                        self.sound_cache[sound_type] = alt_path
                        print(f"Using alternative path: {alt_path}")
                    
            # Debug: Print all sound paths
            print(f"Sound manager initialized with paths:")
            for sound_type, path in self.sound_cache.items():
                print(f"  {sound_type}: {path} (exists: {os.path.exists(path)})")
                    
        except Exception as e:
            print(f"Sound initialization error: {e}")
    
    def play_sound(self, sound_type):
        """Play sound with proper error handling and resource management"""
        print(f"Attempting to play {sound_type} sound...")
        
        if not PLAYSOUND_AVAILABLE and not WINSOUND_AVAILABLE:
            print("No sound libraries available")
            return
            
        if sound_type not in self.sound_cache:
            print(f"Sound type '{sound_type}' not found in cache")
            return
            
        sound_path = self.sound_cache[sound_type]
        if not os.path.exists(sound_path):
            print(f"Sound file not found: {sound_path}")
            return
        
        print(f"Playing {sound_type} from: {sound_path}")
        
        # Submit to thread pool instead of creating new threads
        try:
            future = self.executor.submit(self._play_sound_safe, sound_path)
            # Don't block, but handle result to prevent resource leaks
            future.add_done_callback(self._sound_complete)
        except Exception as e:
            print(f"Sound playback error: {e}")
    
    def _play_sound_safe(self, sound_path):
        """Thread-safe sound playback with error handling"""
        try:
            # Try Windows-native winsound first (more reliable)
            if WINSOUND_AVAILABLE:
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            elif PLAYSOUND_AVAILABLE:
                playsound(sound_path, block=True)
                return True
            else:
                print("No sound library available")
                return False
        except Exception as e:
            # Log error but don't crash
            print(f"Sound playback error: {e}")
            return False
    
    def _sound_complete(self, future):
        """Callback for completed sound playback"""
        try:
            result = future.result(timeout=1)  # Quick timeout
            if result:
                print("Sound played successfully")
            else:
                print("Sound failed to play")
        except Exception as e:
            print(f"Sound completion error: {e}")
    
    def cleanup(self):
        """Clean shutdown of sound manager"""
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass

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
        self.sound_manager = SoundManager()  # Initialize sound manager

    def start(self):
        scheme = "wss" if SERVER_URL.startswith("https") else "ws"
        host   = SERVER_URL.split("://", 1)[1]
        
        # Main chat WebSocket (requires authentication)
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
        # Play notification sound using robust sound manager
        if self.gui.notify_var.get():
            self.sound_manager.play_sound('notify')
            
        # Check for alert keywords and play alert sound
        text = message.split("]", 1)[-1]
        if self.gui.alert_var.get() and re.search(r"\balert\b", text, re.IGNORECASE):
            self.sound_manager.play_sound('alert')
            
        self.gui.append_text(message)
    
    def cleanup(self):
        """Clean shutdown of client resources"""
        try:
            if self.ws:
                self.ws.close()
                self.ws = None
        except Exception as e:
            print(f"WebSocket cleanup error: {e}")
        finally:
            # Don't cleanup sound manager here - let GUI handle it
            pass

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
        # Restore saved window geometry or use default
        saved_geometry = self.config.get("window_geometry", "800x300")
        master.geometry(saved_geometry)
        master.configure(bg=BG_COLOR)
        master.bind('<F1>', lambda e: self.on_send(custom="[!ALERT!]"))
        
        # Set up close handler to save config on exit
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

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

        tk.Button(top, text="GG Map", command=self.open_map_window,
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

            # Insert name with user color tag
            name_tag = f"user_{sender}"
            if name_tag not in self.text_area.tag_names():
                # Use the custom others color instead of random color
                self.text_area.tag_configure(name_tag, foreground=self.custom_others_color, font=("Segoe UI", 13, "bold"))
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

        # Test sound buttons
        test_frame = tk.Frame(self.settings_win, bg=BG_COLOR)
        test_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        tk.Label(test_frame, text="Test Sounds:", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w")
        
        test_buttons_frame = tk.Frame(test_frame, bg=BG_COLOR)
        test_buttons_frame.pack(fill="x", pady=(5, 0))
        
        tk.Button(test_buttons_frame, text="🔔 Test Notify", 
                  command=lambda: self.test_sound('notify'),
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE).pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Button(test_buttons_frame, text="🚨 Test Alert", 
                  command=lambda: self.test_sound('alert'),
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE).pack(side=tk.LEFT)

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
                
                # Update all existing user tags to use the new color
                for tag in self.text_area.tag_names():
                    if tag.startswith("user_"):
                        self.text_area.tag_configure(tag, foreground=color_code)
                
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
    
    def test_sound(self, sound_type):
        """Test sound playback for debugging"""
        try:
            if hasattr(self, 'client') and hasattr(self.client, 'sound_manager'):
                print(f"Testing {sound_type} sound...")
                self.client.sound_manager.play_sound(sound_type)
            else:
                print(f"Cannot test sound: client or sound manager not available")
                messagebox.showwarning("Sound Test", "Cannot test sound: client not connected")
        except Exception as e:
            print(f"Sound test error: {e}")
            messagebox.showerror("Sound Test Error", f"Failed to test sound: {str(e)}")

    def open_map_window(self):
        """Open the GG Map in an integrated window"""
        if not self.username:
            messagebox.showwarning("No Username", "Please login first before opening the map.")
            return
            
        # Check if map window already exists
        if hasattr(self, 'map_window') and self.map_window and hasattr(self.map_window, 'winfo_exists'):
            try:
                if self.map_window.winfo_exists():
                    self.map_window.lift()
                    self.map_window.focus_force()
                    return
            except:
                pass
        
        try:
            if CEF_AVAILABLE:
                try:
                    self.create_cef_window()
                    return
                except Exception as cef_error:
                    pass
            
            if WEBVIEW_AVAILABLE:
                # Use webview for integrated experience
                map_url = f"http://45.79.137.244:8888/map?username={self.username}"
                
                # Check if webview window is already open
                if hasattr(self, '_webview_process') and self._webview_process and self._webview_process.poll() is None:
                    messagebox.showinfo("Map Already Open", "The GG Map window is already open.")
                    return
                
                try:
                    # Handle differently if running from compiled .exe
                    if is_frozen():
                        # For compiled executable, use separate webview launcher process
                        # This mimics the development subprocess behavior
                        import subprocess
                        
                        # Path to the webview launcher executable (should be in same directory)
                        script_dir = os.path.dirname(sys.executable) if is_frozen() else os.path.dirname(os.path.abspath(__file__))
                        launcher_path = os.path.join(script_dir, "webview_launcher.exe")
                        
                        # Check if webview process is already running
                        if hasattr(self, '_webview_process') and self._webview_process and self._webview_process.poll() is None:
                            messagebox.showinfo("Map Already Open", "The GG Map window is already open.")
                            return
                        
                        # Check if launcher exists
                        if os.path.exists(launcher_path):
                            try:
                                # Start webview launcher in separate process (hidden, no console)
                                self._webview_process = subprocess.Popen([
                                    launcher_path,
                                    map_url,
                                    self.username
                                ], 
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                                )
                                
                                # No confirmation dialog - just open silently
                                return
                                
                            except Exception as launcher_error:
                                print(f"Launcher error: {launcher_error}")
                                # Fall through to threading approach
                        
                        # Fallback to threading if launcher not found
                        import threading
                        
                        def create_webview_window():
                            """Fallback webview in thread"""
                            try:
                                import webview
                                import os
                                
                                os.environ['WEBVIEW_ALLOW_HTTP'] = '1'
                                os.environ['WEBVIEW_DISABLE_SECURITY'] = '1'
                                
                                webview.create_window(
                                    title=f"GG Map - {self.username}",
                                    url=map_url,
                                    width=1200,
                                    height=800,
                                    resizable=True,
                                    on_top=False
                                )
                                webview.start(debug=False, private_mode=False)
                                        
                            except Exception as e:
                                print(f"Webview thread error: {e}")
                                import webbrowser
                                webbrowser.open(map_url)
                        
                        threading.Thread(target=create_webview_window, daemon=True).start()
                        
                    else:
                        # Original subprocess approach for development
                        import subprocess
                        import tempfile
                        
                        # Enhanced pywebview script with HTTP handling
                        webview_script = f'''
import webview
import sys
import os

def main():
    try:
        # Set aggressive environment variables before any imports
        os.environ['WEBVIEW_ALLOW_HTTP'] = '1'
        os.environ['WEBVIEW_DISABLE_SECURITY'] = '1'
        os.environ['WEBVIEW_PRIVATE_MODE'] = '0'
        os.environ['WEBVIEW_INCOGNITO'] = '0'
        os.environ['CHROME_ARGS'] = '--disable-web-security --allow-running-insecure-content --disable-features=VizDisplayCompositor --ignore-certificate-errors --allow-http'
        
        # Method 1: Try Edge WebView2 (usually better with HTTP)
        try:
            webview.create_window(
                title="GG Map - {self.username}",
                url="{map_url}",
                width=1200,
                height=800,
                resizable=True,
                on_top=False
            )
            webview.start(debug=False, gui="edgehtml", private_mode=False)
            
        except Exception as e1:
            # Method 2: Try with explicit Chromium args
            try:
                webview.create_window(
                    title="GG Map - {self.username}",
                    url="{map_url}",
                    width=1200,
                    height=800,
                    resizable=True
                )
                webview.start(debug=False, private_mode=False)
                
            except Exception as e2:
                # Method 3: Try basic start
                try:
                    webview.create_window(
                        title="GG Map - {self.username}",
                        url="{map_url}",
                        width=1200,
                        height=800
                    )
                    webview.start()
                    
                except Exception as e3:
                    import traceback
                    traceback.print_exc()
                    sys.exit(1)
            
    except Exception as e:
        print(f"Webview initialization failed: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
                        
                        # Write script to temporary file
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                            f.write(webview_script)
                            script_path = f.name
                        
                        # Get python executable path
                        python_exe = sys.executable
                        
                        # Start webview in separate process
                        self._webview_process = subprocess.Popen([python_exe, script_path])
                        
                        # Clean up temp file after a delay
                        def cleanup_temp_file():
                            try:
                                os.unlink(script_path)
                            except Exception as e:
                                pass
                        
                        self.master.after(5000, cleanup_temp_file)
                    
                except Exception as webview_error:
                    import traceback
                    traceback.print_exc()
                    self.create_enhanced_map_window()
            else:
                # Fallback to enhanced browser launcher
                self.create_enhanced_map_window()
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to open map: {str(e)}")
            # Fallback to browser
            try:
                import webbrowser
                map_url = f"http://45.79.137.244:8888/map?username={self.username}"
                webbrowser.open(map_url)
            except:
                pass

    def create_cef_window(self):
        """Create a CEF-based integrated browser window"""
        map_url = f"http://45.79.137.244:8888/map?username={self.username}"
        
        # Create CEF window in a separate process
        import subprocess
        import tempfile
        
        cef_script = f'''
import sys
import tkinter as tk
from cefpython3 import cefpython as cef
import threading
import os

def main():
    try:
        # Initialize CEF with settings that allow HTTP
        sys.excepthook = cef.ExceptHook  # To shutdown all CEF processes on error
        
        settings = {{
            "debug": False,
            "log_severity": cef.LOGSEVERITY_INFO,
            "log_file": "",
            "multi_threaded_message_loop": False,
            "auto_zooming": "system_dpi",
            "ignore_certificate_errors": True,
            "ignore_ssl_errors": True,
            "disable_web_security": True,
            "allow_running_insecure_content": True,
        }}
        
        cef.Initialize(settings)
        
        # Create window
        root = tk.Tk()
        root.title("GG Map - {self.username}")
        root.geometry("1200x800")
        root.configure(bg="#1e1e1e")
        
        # Add icon if available
        try:
            if os.path.exists(ICON_FILE):
                root.iconbitmap(ICON_FILE)
        except:
            pass
        
        # Create browser frame
        browser_frame = tk.Frame(root, bg="#1e1e1e")
        browser_frame.pack(fill=tk.BOTH, expand=tk.TRUE)
        
        window_info = cef.WindowInfo()
        window_info.SetAsChild(browser_frame.winfo_id(), [0, 0, 1200, 800])
        
        browser = cef.CreateBrowserSync(
            window_info,
            url="{map_url}"
        )
        
        # Message loop
        def message_loop():
            cef.MessageLoopWork()
            root.after(10, message_loop)
            
        def on_closing():
            browser.CloseBrowser(True)
            cef.Shutdown()
            root.destroy()
            
        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.after(10, message_loop)
        root.mainloop()
        
    except Exception as e:
        print(f"CEF Error: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(cef_script)
            script_path = f.name
        
        python_exe = sys.executable
        self._cef_process = subprocess.Popen([python_exe, script_path])
        
        # Clean up temp file after delay
        def cleanup_cef_file():
            try:
                os.unlink(script_path)
            except Exception as e:
                pass
        
        self.master.after(5000, cleanup_cef_file)

    def create_enhanced_map_window(self):
        """Create an enhanced map window that opens browser with better integration"""
        self.map_window = tk.Toplevel(self.master)
        self.map_window.title(f"GG Map - {self.username}")
        self.map_window.configure(bg=BG_COLOR)
        self.map_window.geometry("500x350")
        self.map_window.resizable(True, True)
        
        # Add icon if available
        try:
            if os.path.exists(ICON_FILE):
                self.map_window.iconbitmap(ICON_FILE)
        except:
            pass
        
        main_frame = tk.Frame(self.map_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title with map icon
        title_frame = tk.Frame(main_frame, bg=BG_COLOR)
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = tk.Label(title_frame, text="🗺️ GG Guild Map", 
                              font=("Segoe UI", 18, "bold"), 
                              bg=BG_COLOR, fg="#ffd700")
        title_label.pack()
        
        subtitle_label = tk.Label(title_frame, text="Guild Coordination & Ping System", 
                                 font=("Segoe UI", 11), 
                                 bg=BG_COLOR, fg="#cccccc")
        subtitle_label.pack(pady=(5, 0))
        
        # Status info
        info_frame = tk.Frame(main_frame, bg=ENTRY_BG, relief=tk.RAISED, bd=2)
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        status_text = f"✅ Connected as: {self.username}"
        status_label = tk.Label(info_frame, text=status_text,
                               font=("Segoe UI", 12, "bold"),
                               bg=ENTRY_BG, fg="#00ff00", pady=10)
        status_label.pack()
        
        # Quick launch button
        map_url = f"http://45.79.137.244:8888/map?username={self.username}"
        
        launch_btn = tk.Button(main_frame, text="🚀 Launch GG Map in Browser", 
                              command=lambda: self.launch_map_browser(map_url),
                              bg="#4CAF50", fg="white", 
                              activebackground="#45a049",
                              font=("Segoe UI", 14, "bold"),
                              relief=tk.RAISED, bd=3, pady=15)
        launch_btn.pack(fill=tk.X, pady=(0, 15))
        
        # Features list
        features_frame = tk.Frame(main_frame, bg=BG_COLOR)
        features_frame.pack(fill=tk.X, pady=(0, 15))
        
        features_title = tk.Label(features_frame, text="🎯 Map Features:",
                                 font=("Segoe UI", 12, "bold"),
                                 bg=BG_COLOR, fg=FG_COLOR)
        features_title.pack(anchor="w")
        
        features = [
            "• Click anywhere to place pings",
            "• See other guild members' pings in real-time", 
            "• Auto-zoom to new pings",
            "• Sound notifications for new pings",
            "• Username labels above each ping"
        ]
        
        for feature in features:
            feature_label = tk.Label(features_frame, text=feature,
                                   font=("Segoe UI", 10),
                                   bg=BG_COLOR, fg="#cccccc")
            feature_label.pack(anchor="w", padx=(10, 0))
        
        # Bottom buttons
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        copy_btn = tk.Button(button_frame, text="📋 Copy URL", 
                            command=lambda: self.copy_to_clipboard(map_url),
                            bg=BUTTON_BG, fg=FG_COLOR, 
                            activebackground=BUTTON_ACTIVE,
                            font=("Segoe UI", 10))
        copy_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        close_btn = tk.Button(button_frame, text="✖️ Close", 
                             command=self.map_window.destroy,
                             bg="#f44336", fg="white", 
                             activebackground="#d32f2f",
                             font=("Segoe UI", 10))
        close_btn.pack(side=tk.RIGHT)
        
        # Auto-focus and bring to front
        self.map_window.lift()
        self.map_window.focus_force()
        
    def launch_map_browser(self, url):
        """Launch map in browser and close the launcher window"""
        try:
            webbrowser.open(url)
            # Show success message
            success_label = tk.Label(self.map_window, text="✅ Map opened in browser!",
                                   font=("Segoe UI", 10, "bold"),
                                   bg=BG_COLOR, fg="#00ff00")
            success_label.pack(pady=5)
            
            # Auto-close after 2 seconds
            self.master.after(2000, self.map_window.destroy)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open browser: {str(e)}")

    def create_tkinter_map_window(self):
        """Create a Tkinter window with instructions to manually navigate to the map"""
        self.map_window = tk.Toplevel(self.master)
        self.map_window.title(f"GG Map - {self.username}")
        self.map_window.configure(bg=BG_COLOR)
        self.map_window.geometry("600x400")
        self.map_window.resizable(True, True)
        
        # Add icon if available
        try:
            if os.path.exists(ICON_FILE):
                self.map_window.iconbitmap(ICON_FILE)
        except:
            pass
        
        main_frame = tk.Frame(self.map_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = tk.Label(main_frame, text="GG Map Integration", 
                              font=("Segoe UI", 16, "bold"), 
                              bg=BG_COLOR, fg=FG_COLOR)
        title_label.pack(pady=(0, 20))
        
        # Map URL
        map_url = f"http://45.79.137.244:8888/map?username={self.username}"
        
        # Instructions
        instructions = tk.Label(main_frame, 
                               text="The integrated web view is not available.\nClick the button below to open the map in your browser:",
                               font=("Segoe UI", 11),
                               bg=BG_COLOR, fg=FG_COLOR,
                               justify=tk.CENTER)
        instructions.pack(pady=(0, 20))
        
        # URL display
        url_frame = tk.Frame(main_frame, bg=ENTRY_BG, relief=tk.SUNKEN, bd=1)
        url_frame.pack(fill=tk.X, pady=(0, 20))
        
        url_text = tk.Text(url_frame, height=2, wrap=tk.WORD, 
                          bg=ENTRY_BG, fg=FG_COLOR, 
                          font=("Consolas", 9),
                          relief=tk.FLAT, bd=5)
        url_text.pack(fill=tk.BOTH, expand=True)
        url_text.insert("1.0", map_url)
        url_text.config(state=tk.DISABLED)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        open_browser_btn = tk.Button(button_frame, text="Open in Browser", 
                                    command=lambda: webbrowser.open(map_url),
                                    bg=BUTTON_BG, fg=FG_COLOR, 
                                    activebackground=BUTTON_ACTIVE,
                                    font=("Segoe UI", 11, "bold"))
        open_browser_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        copy_url_btn = tk.Button(button_frame, text="Copy URL", 
                                command=lambda: self.copy_to_clipboard(map_url),
                                bg=BUTTON_BG, fg=FG_COLOR, 
                                activebackground=BUTTON_ACTIVE)
        copy_url_btn.pack(side=tk.LEFT)
        
        # Status
        status_label = tk.Label(main_frame, 
                               text=f"Connected as: {self.username}",
                               font=("Segoe UI", 10),
                               bg=BG_COLOR, fg="#00ff00")
        status_label.pack(pady=(20, 0))
        
        # Install instructions
        install_frame = tk.Frame(main_frame, bg=BG_COLOR)
        install_frame.pack(fill=tk.X, pady=(20, 0))
        
        install_label = tk.Label(install_frame, 
                                text="For better integration, install: pip install pywebview",
                                font=("Segoe UI", 9, "italic"),
                                bg=BG_COLOR, fg="#888888")
        install_label.pack()

    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(text)
            messagebox.showinfo("Copied", "URL copied to clipboard!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy to clipboard: {str(e)}")

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

    def on_closing(self):
        """Handle window closing - save config and clean up"""
        try:
            # Save current sound notification settings
            self.config["sound_notify"] = self.notify_var.get()
            self.config["sound_alerts"] = self.alert_var.get()
            
            # Save window geometry for next startup
            geometry = self.master.geometry()
            self.config["window_geometry"] = geometry
            
            # Save configuration before closing
            self.save_config()
            
            # Disconnect websocket if connected
            if hasattr(self, 'client') and self.client:
                try:
                    self.client.cleanup()  # Use the new cleanup method
                except:
                    pass
                    
            # Clean up sound manager if it exists
            if hasattr(self, 'client') and hasattr(self.client, 'sound_manager'):
                try:
                    self.client.sound_manager.cleanup()
                except Exception as e:
                    print(f"Sound manager cleanup error: {e}")
        except Exception as e:
            print(f"Error during shutdown: {e}")
        finally:
            # Close the window
            self.master.destroy()

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
