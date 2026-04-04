# TextHunter - Advanced Text Monitoring Tool
import time
import mss
from PIL import Image, ImageTk
import pytesseract
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import pygetwindow as gw
import sys
import os
import json
import requests
from datetime import datetime, timedelta
import uuid
import tempfile
import atexit

# ────────────────────── SINGLE INSTANCE CHECK ──────────────────────
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'texthunter.lock')

def check_single_instance():
    """Ensure only one instance of TextHunter is running"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process is still running
            import psutil
            if psutil.pid_exists(pid):
                return False
        except:
            pass
    
    # Create lock file
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    # Register cleanup
    atexit.register(cleanup_lock)
    return True

def cleanup_lock():
    """Remove lock file on exit"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass

# Try to import pygame for volume control, fall back to playsound
try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except ImportError:
    from playsound import playsound
    PYGAME_AVAILABLE = False

# --- TESSERACT PATH (keep if needed) ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ────────────────────── CONFIG ──────────────────────
CONFIG_FILE = 'texthunter_config.json'
DEBUG_IMG = 'debug.png'

# Default target keys - fallback if no config file exists
DEFAULT_TARGET_KEYS = ['Griffon Egg', 'King of Greed']

def get_config_file_path():
    """Get the correct path to the config file when running as exe or script"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        return os.path.join(exe_dir, CONFIG_FILE)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, CONFIG_FILE)

def get_sounds_dir():
    """Get the sounds directory path"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'sounds')
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')

def get_available_sounds():
    """Get list of available sound files from ./sounds folder"""
    sounds_dir = get_sounds_dir()
    if not os.path.exists(sounds_dir):
        return []
    sound_files = []
    for file in os.listdir(sounds_dir):
        if file.lower().endswith(('.mp3', '.wav', '.ogg')):
            sound_files.append(file)
    return sorted(sound_files)

def play_sound_with_volume(sound_file, volume=1.0):
    """Play a sound file with volume control"""
    sounds_dir = get_sounds_dir()
    sound_path = os.path.join(sounds_dir, sound_file)
    
    if not os.path.exists(sound_path):
        print(f"Sound file not found: {sound_path}")
        try:
            import winsound
            winsound.Beep(1000, 500)
        except:
            pass
        return
    
    try:
        if PYGAME_AVAILABLE:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play()
        else:
            playsound(sound_path)
    except Exception as e:
        print(f"Error playing sound: {e}")
        try:
            import winsound
            winsound.Beep(1000, 500)
        except:
            pass

# ────────────────────── MONITORED REGION CLASS ──────────────────────
class MonitoredRegion:
    """Represents a single monitored region with its own settings"""
    def __init__(self, region_id=None):
        self.id = region_id or str(uuid.uuid4())[:8]
        self.name = f"Region {self.id}"
        self.enabled = True
        self.region_type = None  # 'screen_region', 'window_region', 'full_window'
        self.region_data = None  # Coordinates or window info
        
        # Per-region settings
        self.monitoring_interval = 5
        
        # Detection rules - each rule has its own keywords, sound, and notification settings
        self.detection_rules = [
            {
                'name': 'Default Rule',
                'keywords': DEFAULT_TARGET_KEYS.copy(),
                'sound_enabled': True,
                'sound_file': 'level_up.mp3',
                'volume': 0.8,
                'discord_enabled': False,
                'discord_webhook_url': '',
                'discord_cooldown': 30,
                'last_discord_notification': None
            }
        ]
        
        # Runtime state
        self.running = False
        self.paused = False
        self.last_status = "Stopped"
        self.thread = None
        
        # Debug/preview state
        self.last_capture = None
        self.last_ocr_text = ""
        self.preview_window = None
    
    def to_dict(self):
        """Serialize region to dictionary"""
        # Serialize rules without runtime state
        rules_serialized = []
        for rule in self.detection_rules:
            rules_serialized.append({
                'name': rule.get('name', 'Rule'),
                'keywords': rule.get('keywords', []),
                'sound_enabled': rule.get('sound_enabled', True),
                'sound_file': rule.get('sound_file', 'level_up.mp3'),
                'volume': rule.get('volume', 0.8),
                'discord_enabled': rule.get('discord_enabled', False),
                'discord_webhook_url': rule.get('discord_webhook_url', ''),
                'discord_cooldown': rule.get('discord_cooldown', 30)
            })
        
        return {
            'id': self.id,
            'name': self.name,
            'enabled': self.enabled,
            'region_type': self.region_type,
            'region_data': self.region_data,
            'monitoring_interval': self.monitoring_interval,
            'detection_rules': rules_serialized
        }
    
    @classmethod
    def from_dict(cls, data):
        """Deserialize region from dictionary"""
        region = cls(data.get('id'))
        region.name = data.get('name', region.name)
        region.enabled = data.get('enabled', True)
        region.region_type = data.get('region_type')
        region.region_data = data.get('region_data')
        region.monitoring_interval = data.get('monitoring_interval', 5)
        
        # Load detection rules or migrate from old format
        if 'detection_rules' in data:
            region.detection_rules = []
            for rule_data in data['detection_rules']:
                region.detection_rules.append({
                    'name': rule_data.get('name', 'Rule'),
                    'keywords': rule_data.get('keywords', []),
                    'sound_enabled': rule_data.get('sound_enabled', True),
                    'sound_file': rule_data.get('sound_file', 'level_up.mp3'),
                    'volume': rule_data.get('volume', 0.8),
                    'discord_enabled': rule_data.get('discord_enabled', False),
                    'discord_webhook_url': rule_data.get('discord_webhook_url', ''),
                    'discord_cooldown': rule_data.get('discord_cooldown', 30),
                    'last_discord_notification': None
                })
        else:
            # Migrate from old single-rule format
            region.detection_rules = [{
                'name': 'Default Rule',
                'keywords': data.get('target_keys', DEFAULT_TARGET_KEYS.copy()),
                'sound_enabled': data.get('sound_enabled', True),
                'sound_file': data.get('sound_file', 'level_up.mp3'),
                'volume': data.get('volume', 0.8),
                'discord_enabled': data.get('discord_enabled', False),
                'discord_webhook_url': data.get('discord_webhook_url', ''),
                'discord_cooldown': data.get('discord_cooldown', 30),
                'last_discord_notification': None
            }]
        
        return region
    
    def play_alert_for_rule(self, rule):
        """Play alert sound for a specific rule"""
        if rule.get('sound_enabled', True):
            threading.Thread(
                target=play_sound_with_volume,
                args=(rule.get('sound_file', 'level_up.mp3'), rule.get('volume', 0.8)),
                daemon=True
            ).start()
    
    def send_discord_for_rule(self, rule, found_text):
        """Send Discord notification for a specific rule"""
        if not rule.get('discord_enabled') or not rule.get('discord_webhook_url', '').strip():
            return
        
        now = datetime.now()
        last_notif = rule.get('last_discord_notification')
        cooldown = rule.get('discord_cooldown', 30)
        
        if last_notif and now - last_notif < timedelta(seconds=cooldown):
            return
        
        try:
            rule_name = rule.get('name', 'Rule')
            message = f'@everyone [{self.name} - {rule_name}] TextHunter found: "{found_text}"!'
            payload = {"content": message, "username": "TextHunter Bot"}
            response = requests.post(rule['discord_webhook_url'], json=payload, timeout=10)
            if response.status_code == 204:
                rule['last_discord_notification'] = now
                print(f"Discord notification sent for {self.name} - {rule_name}")
        except Exception as e:
            print(f"Discord error for {self.name}: {e}")
    
    def notify_rule(self, rule, found_keywords):
        """Send all notifications for a rule"""
        found_text = ", ".join(found_keywords)
        self.play_alert_for_rule(rule)
        if rule.get('discord_enabled'):
            threading.Thread(
                target=self.send_discord_for_rule,
                args=(rule, found_text),
                daemon=True
            ).start()
    
    def check_rules(self, text):
        """Check all detection rules against OCR text, notify for matches"""
        all_found = []
        for rule in self.detection_rules:
            found_keywords = []
            for keyword in rule.get('keywords', []):
                if keyword.lower() in text.lower():
                    found_keywords.append(keyword)
            
            if found_keywords:
                all_found.extend(found_keywords)
                self.notify_rule(rule, found_keywords)
        
        return all_found
    
    def play_alert(self):
        """Play alert sound from first rule (for test button)"""
        if self.detection_rules:
            self.play_alert_for_rule(self.detection_rules[0])
    
    def show_preview_window(self, parent, refresh_callback=None):
        """Show/update preview window with capture and OCR text"""
        if self.preview_window and self.preview_window.winfo_exists():
            self.update_preview_content()
            self.preview_window.lift()
            return
        
        self.preview_window = tk.Toplevel(parent)
        self.preview_window.title(f"Preview - {self.name}")
        self.preview_window.geometry("520x450")
        self.preview_window.configure(bg='#0f0f23')
        self.preview_window.attributes('-topmost', True)
        
        # Header
        header = tk.Frame(self.preview_window, bg='#1a1a2e', height=45)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text=f"👁 {self.name}",
            bg='#1a1a2e',
            fg='#ffffff',
            font=('Segoe UI', 12, 'bold')
        ).pack(side='left', padx=15, pady=10)
        
        # Refresh button in header — triggers a fresh capture + OCR
        refresh_btn = tk.Button(
            header,
            text="🔄 Refresh",
            command=refresh_callback or self.update_preview_content,
            bg='#3498db',
            fg='white',
            font=('Segoe UI', 9),
            relief='flat',
            padx=12,
            cursor='hand2'
        )
        refresh_btn.pack(side='right', padx=15, pady=8)
        
        tk.Frame(self.preview_window, bg='#e94560', height=2).pack(fill='x')
        
        # Image preview section
        img_section = tk.Frame(self.preview_window, bg='#0f0f23')
        img_section.pack(fill='x', padx=15, pady=(15, 5))
        
        tk.Label(
            img_section,
            text="🖼️ Captured Region",
            bg='#0f0f23',
            fg='#e94560',
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor='w')
        
        self.preview_image_label = tk.Label(
            self.preview_window,
            bg='#1a1a2e',
            text="Click 'Refresh' to capture...",
            fg='#444466',
            font=('Segoe UI', 10)
        )
        self.preview_image_label.pack(fill='x', padx=15, pady=8, ipady=25)
        
        # OCR text section
        text_section = tk.Frame(self.preview_window, bg='#0f0f23')
        text_section.pack(fill='x', padx=15, pady=(5, 0))
        
        tk.Label(
            text_section,
            text="📝 Detected Text (OCR)",
            bg='#0f0f23',
            fg='#e94560',
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor='w')
        
        text_frame = tk.Frame(self.preview_window, bg='#1a1a2e')
        text_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame, bg='#1a1a2e')
        scrollbar.pack(side='right', fill='y')
        
        self.preview_text = tk.Text(
            text_frame,
            bg='#1a1a2e',
            fg='#00ff88',
            font=('Consolas', 10),
            height=8,
            yscrollcommand=scrollbar.set,
            wrap='word',
            relief='flat',
            padx=10,
            pady=10
        )
        self.preview_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.preview_text.yview)
        
        self.update_preview_content()
    
    def update_preview_content(self):
        """Update the preview window with latest capture and OCR"""
        if not self.preview_window or not self.preview_window.winfo_exists():
            return
        
        try:
            if self.last_capture:
                # Resize for display
                display_img = self.last_capture.copy()
                display_img.thumbnail((490, 150), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(display_img)
                self.preview_image_label.config(image=photo, text="", bg='#1a1a2e')
                self.preview_image_label.image = photo
            else:
                self.preview_image_label.config(image="", text="Click 'Refresh' to capture...", bg='#1a1a2e')
            
            # Update OCR text
            self.preview_text.delete('1.0', 'end')
            if self.last_ocr_text:
                self.preview_text.insert('1.0', self.last_ocr_text)
            else:
                self.preview_text.insert('1.0', "(No text detected)")
                
        except Exception as e:
            print(f"Preview update error: {e}")


# ────────────────────── MAIN APPLICATION ──────────────────────
class TextHunterApp:
    """Main application window managing multiple monitored regions"""
    
    def __init__(self):
        self.regions = []
        self.root = None
        self.region_frames = {}
        self.load_config()
    
    def load_config(self):
        """Load all regions from config file"""
        try:
            config_path = get_config_file_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    regions_data = config.get('regions', [])
                    for rd in regions_data:
                        region = MonitoredRegion.from_dict(rd)
                        self.regions.append(region)
                    print(f"Loaded {len(self.regions)} regions from config")
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save_config(self):
        """Save all regions to config file"""
        try:
            config = {
                'regions': [r.to_dict() for r in self.regions],
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            config_path = get_config_file_path()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"Config saved: {len(self.regions)} regions")
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def run(self):
        """Start the main application"""
        self.root = tk.Tk()
        self.root.title("TextHunter")
        self.root.geometry("680x480")
        self.root.minsize(620, 580)
        self.root.configure(bg='#0f0f23')
        self.root.attributes('-topmost', True)
        
        # Set window icon if available
        try:
            self.root.iconbitmap('icon.ico')
        except:
            pass
        
        self.create_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()
    
    def create_ui(self):
        """Create the main UI"""
        # Title bar with gradient-like effect
        title_frame = tk.Frame(self.root, bg='#1a1a2e', height=60)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        # App icon and title
        title_container = tk.Frame(title_frame, bg='#1a1a2e')
        title_container.pack(side='left', padx=20, pady=12)
        
        tk.Label(
            title_container,
            text="🔍",
            bg='#1a1a2e',
            fg='#e94560',
            font=('Segoe UI Emoji', 20)
        ).pack(side='left')
        
        tk.Label(
            title_container,
            text="TextHunter",
            bg='#1a1a2e',
            fg='#ffffff',
            font=('Segoe UI', 18, 'bold')
        ).pack(side='left', padx=(8, 0))
        
        tk.Label(
            title_container,
            text="Multi-Region Monitor",
            bg='#1a1a2e',
            fg='#888899',
            font=('Segoe UI', 10)
        ).pack(side='left', padx=(12, 0), pady=(6, 0))
        
        # Separator line
        tk.Frame(self.root, bg='#e94560', height=2).pack(fill='x')
        
        # Top button bar
        btn_frame = tk.Frame(self.root, bg='#16213e')
        btn_frame.pack(fill='x', padx=0, pady=0)
        
        btn_inner = tk.Frame(btn_frame, bg='#16213e')
        btn_inner.pack(fill='x', padx=15, pady=12)
        
        self._create_styled_button(
            btn_inner,
            text="➕ Add Region",
            command=self.add_region_dialog,
            bg='#9b59b6',
            hover='#8e44ad'
        ).pack(side='left', padx=(0, 8))
        
        self._create_styled_button(
            btn_inner,
            text="▶ Start All",
            command=self.start_all,
            bg='#27ae60',
            hover='#219a52'
        ).pack(side='left', padx=8)
        
        self._create_styled_button(
            btn_inner,
            text="⏹ Stop All",
            command=self.stop_all,
            bg='#e74c3c',
            hover='#c0392b'
        ).pack(side='left', padx=8)
        
        self._create_styled_button(
            btn_inner,
            text="💾 Save Config",
            command=self.save_config,
            bg='#3498db',
            hover='#2980b9'
        ).pack(side='right', padx=0)
        
        # Scrollable region list
        container = tk.Frame(self.root, bg='#0f0f23')
        container.pack(fill='both', expand=True, padx=0, pady=0)
        
        # Custom styled scrollbar
        style = ttk.Style()
        style.configure('Custom.Vertical.TScrollbar', 
            background='#1a1a2e',
            troughcolor='#0f0f23',
            arrowcolor='#e94560'
        )
        
        canvas = tk.Canvas(container, bg='#0f0f23', highlightthickness=0)
        self.main_canvas = canvas
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        self.regions_frame = tk.Frame(canvas, bg='#0f0f23')
        
        self.regions_frame.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all'))
        )
        
        self.regions_window = canvas.create_window((0, 0), window=self.regions_frame, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(self.regions_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Bind mousewheel only to this canvas (avoid affecting dialogs)
        canvas.bind('<MouseWheel>', lambda e: self._scroll_canvas_if_needed(canvas, e))
        
        # Refresh region list
        self.refresh_region_list()
    
    def _create_styled_button(self, parent, text, command, bg, hover):
        """Create a styled button with hover effect"""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            padx=16,
            pady=8,
            cursor='hand2',
            activebackground=hover,
            activeforeground='white',
            bd=0
        )
        btn.bind('<Enter>', lambda e, b=btn, c=hover: b.config(bg=c))
        btn.bind('<Leave>', lambda e, b=btn, c=bg: b.config(bg=c))
        return btn

    def _scroll_canvas_if_needed(self, canvas, event):
        """Scroll only when content exceeds the visible canvas height."""
        bbox = canvas.bbox('all')
        if not bbox:
            return

        content_height = bbox[3] - bbox[1]
        visible_height = canvas.winfo_height()

        # Prevent "floating" movement when everything already fits on screen.
        if content_height <= visible_height:
            return

        delta = int(-1 * (event.delta / 120))
        if delta != 0:
            canvas.yview_scroll(delta, 'units')
    
    def refresh_region_list(self):
        """Refresh the displayed region list"""
        # Clear existing
        for widget in self.regions_frame.winfo_children():
            widget.destroy()
        self.region_frames.clear()
        
        if not self.regions:
            visible_height = 500
            if hasattr(self, 'main_canvas'):
                self.main_canvas.update_idletasks()
                visible_height = max(self.main_canvas.winfo_height(), 300)

            top_pad = max(40, (visible_height - 190) // 2)
            empty_frame = tk.Frame(self.regions_frame, bg='#0f0f23')
            empty_frame.pack(fill='x', pady=(top_pad, 0))
            
            tk.Label(
                empty_frame,
                text="📭",
                bg='#0f0f23',
                fg='#333355',
                font=('Segoe UI Emoji', 48)
            ).pack()
            
            tk.Label(
                empty_frame,
                text="No regions configured",
                bg='#0f0f23',
                fg='#666688',
                font=('Segoe UI', 14, 'bold')
            ).pack(pady=(10, 5))
            
            tk.Label(
                empty_frame,
                text="Click '➕ Add Region' to start monitoring",
                bg='#0f0f23',
                fg='#444466',
                font=('Segoe UI', 11)
            ).pack()
            return
        
        # Add some top padding
        tk.Frame(self.regions_frame, bg='#0f0f23', height=10).pack()

        # Reset to top after rebuilding the list to avoid stale offset.
        if hasattr(self, 'main_canvas'):
            self.main_canvas.yview_moveto(0)
        
        for region in self.regions:
            self.create_region_card(region)
    
    def create_region_card(self, region):
        """Create a card UI for a single region"""
        # Outer wrapper for border effect
        card_wrapper = tk.Frame(self.regions_frame, bg='#1a1a2e')
        card_wrapper.pack(fill='x', padx=15, pady=6)
        
        # Main card with left border color based on status
        # Check if region has a "Found" status
        if region.last_status and region.last_status.startswith("Found:"):
            status_color = '#27ae60'  # Keep green for found (same as running)
            status_text = region.last_status
        else:
            status_color = '#27ae60' if region.running and not region.paused else (
                '#f39c12' if region.paused else '#444466'
            )
            status_text = "Running" if region.running and not region.paused else (
                "Paused" if region.paused else "Stopped"
            )
        
        # Left accent border
        accent = tk.Frame(card_wrapper, bg=status_color, width=4)
        accent.pack(side='left', fill='y')
        
        card = tk.Frame(card_wrapper, bg='#1a1a2e')
        card.pack(side='left', fill='x', expand=True)
        self.region_frames[region.id] = card_wrapper
        
        # Header row
        header = tk.Frame(card, bg='#1a1a2e')
        header.pack(fill='x', padx=12, pady=(10, 5))
        
        # Status indicator with glow effect
        status_frame = tk.Frame(header, bg='#1a1a2e')
        status_frame.pack(side='left')
        
        status_dot = tk.Label(
            status_frame,
            text="●",
            bg='#1a1a2e',
            fg=status_color,
            font=('Arial', 16)
        )
        status_dot.pack(side='left')
        
        status_text_label = tk.Label(
            status_frame,
            text=status_text,
            bg='#1a1a2e',
            fg=status_color,
            font=('Segoe UI', 8)
        )
        status_text_label.pack(side='left', padx=(2, 0))
        
        # Store references for dynamic updates
        region.status_widgets = {
            'dot': status_dot,
            'text': status_text_label,
            'accent': accent
        }
        name_var = tk.StringVar(value=region.name)
        name_entry = tk.Entry(
            header,
            textvariable=name_var,
            bg='#0f0f23',
            fg='#ffffff',
            font=('Segoe UI', 12, 'bold'),
            relief='flat',
            width=22,
            insertbackground='#e94560'
        )
        name_entry.pack(side='left', padx=(15, 10))
        name_entry.bind('<FocusOut>', lambda e, r=region, v=name_var: setattr(r, 'name', v.get()))
        
        # Type badge
        type_info = {
            'screen_region': ('📺', 'Screen', '#3498db'),
            'window_region': ('🪟', 'Window Region', '#9b59b6'),
            'full_window': ('🖥️', 'Full Window', '#27ae60')
        }.get(region.region_type, ('❓', 'Not Set', '#666688'))
        
        type_badge = tk.Frame(header, bg=type_info[2], padx=8, pady=2)
        type_badge.pack(side='left')
        tk.Label(
            type_badge,
            text=f"{type_info[0]} {type_info[1]}",
            bg=type_info[2],
            fg='white',
            font=('Segoe UI', 8, 'bold')
        ).pack()
        
        # Control buttons
        btn_frame = tk.Frame(header, bg='#1a1a2e')
        btn_frame.pack(side='right')
        
        if region.running:
            if region.paused:
                self._create_icon_button(btn_frame, "▶", lambda r=region: self.resume_region(r), '#27ae60')
            else:
                self._create_icon_button(btn_frame, "⏸", lambda r=region: self.pause_region(r), '#f39c12')
            self._create_icon_button(btn_frame, "⏹", lambda r=region: self.stop_region(r), '#e74c3c')
        else:
            self._create_icon_button(btn_frame, "▶", lambda r=region: self.start_region(r), '#27ae60')
        
        self._create_icon_button(btn_frame, "⚙️", lambda r=region: self.edit_region_settings(r), '#5d6d7e')
        self._create_icon_button(btn_frame, "🗑", lambda r=region: self.delete_region(r), '#95a5a6')
        
        # Separator
        tk.Frame(card, bg='#0f0f23', height=1).pack(fill='x', padx=12, pady=5)
        
        # Settings row
        settings_frame = tk.Frame(card, bg='#1a1a2e')
        settings_frame.pack(fill='x', padx=12, pady=(0, 10))
        
        # Info badges container
        info_frame = tk.Frame(settings_frame, bg='#1a1a2e')
        info_frame.pack(side='left')
        
        # Targets preview badge - show rule count and total keywords
        total_keywords = sum(len(rule.get('keywords', [])) for rule in region.detection_rules)
        rule_count = len(region.detection_rules)
        targets_text = f"{rule_count} rule{'s' if rule_count != 1 else ''}, {total_keywords} keyword{'s' if total_keywords != 1 else ''}"
        self._create_info_badge(info_frame, "🎯", targets_text, '#e94560')
        
        # Sound info badge - show first rule's sound
        if region.detection_rules:
            first_rule = region.detection_rules[0]
            sound_name = first_rule.get('sound_file', 'level_up.mp3').replace('.mp3', '').replace('.wav', '')[:10]
            self._create_info_badge(info_frame, "🔊", f"{sound_name}", '#9b59b6')
        
        # Interval badge
        self._create_info_badge(info_frame, "⏱️", f"{region.monitoring_interval}s", '#3498db')
        
        # Discord indicator - check if any rule has discord enabled
        has_discord = any(rule.get('discord_enabled') for rule in region.detection_rules)
        if has_discord:
            self._create_info_badge(info_frame, "💬", "Discord", '#5865f2')
        
        # Action buttons
        btn_container = tk.Frame(settings_frame, bg='#1a1a2e')
        btn_container.pack(side='right')
        
        # Test sound button
        tk.Button(
            btn_container,
            text="🔔 Test",
            command=lambda r=region: r.play_alert(),
            bg='#9b59b6',
            fg='white',
            font=('Segoe UI', 8),
            relief='flat',
            padx=10,
            cursor='hand2'
        ).pack(side='right', padx=3)
        
        # Preview button (shows capture + OCR text)
        tk.Button(
            btn_container,
            text="👁 Preview",
            command=lambda r=region: self.do_capture_and_preview(r),
            bg='#3498db',
            fg='white',
            font=('Segoe UI', 8),
            relief='flat',
            padx=10,
            cursor='hand2'
        ).pack(side='right', padx=3)
    
    def highlight_region(self, region_id):
        """Create a pulsing highlight effect on a region's card border when it finds a match"""
        if region_id in self.region_frames:
            card_wrapper = self.region_frames[region_id]
            accent = card_wrapper.winfo_children()[0]  # The accent frame (left border)
            original_color = accent.cget('bg')
            highlight_color = '#00FF00'  # Bright pure green for more noticeable pulse
            
            def pulse(count=0):
                try:
                    if not accent.winfo_exists():
                        return
                    
                    if count >= 6:  # 3 pulses (6 changes)
                        accent.config(bg=original_color)
                        return
                    
                    # Alternate between highlight and original
                    new_color = highlight_color if count % 2 == 0 else original_color
                    accent.config(bg=new_color)
                    
                    # Schedule next pulse (150ms intervals for smooth effect)
                    self.root.after(150, lambda: pulse(count + 1))
                    
                except:
                    pass  # Widget was destroyed, ignore
            
            pulse()  # Start the pulsing effect
    
    def update_region_status(self, region):
        """Update the status display of a specific region without refreshing the whole list"""
        if hasattr(region, 'status_widgets'):
            # Determine status color and text
            if region.last_status and region.last_status.startswith("Found:"):
                status_color = '#27ae60'  # Keep green for found
                status_text = region.last_status
            else:
                status_color = '#27ae60' if region.running and not region.paused else (
                    '#f39c12' if region.paused else '#444466'
                )
                status_text = "Running" if region.running and not region.paused else (
                    "Paused" if region.paused else "Stopped"
                )
            
            # Update the widgets
            try:
                region.status_widgets['dot'].config(fg=status_color)
                region.status_widgets['text'].config(text=status_text, fg=status_color)
                region.status_widgets['accent'].config(bg=status_color)
            except:
                pass  # Widgets might be destroyed, ignore
    
    def _create_icon_button(self, parent, icon, command, bg):
        """Create a small icon button"""
        btn = tk.Button(
            parent,
            text=icon,
            command=command,
            bg=bg,
            fg='white',
            font=('Segoe UI', 10),
            relief='flat',
            padx=8,
            pady=3,
            cursor='hand2',
            activebackground='#0f0f23'
        )
        btn.pack(side='left', padx=2)
        return btn
    
    def _create_info_badge(self, parent, icon, text, color):
        """Create a small info badge"""
        badge = tk.Frame(parent, bg='#0f0f23', padx=6, pady=2)
        badge.pack(side='left', padx=(0, 6))
        tk.Label(
            badge,
            text=f"{icon} {text}",
            bg='#0f0f23',
            fg=color,
            font=('Segoe UI', 8)
        ).pack()
    
    def add_region_dialog(self):
        """Show dialog to add a new region"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Region")
        dialog.geometry("420x320")
        dialog.configure(bg='#0f0f23')
        dialog.attributes('-topmost', True)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Header
        header = tk.Frame(dialog, bg='#1a1a2e', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="➕ Add New Region",
            bg='#1a1a2e',
            fg='#ffffff',
            font=('Segoe UI', 14, 'bold')
        ).pack(side='left', padx=20, pady=12)
        
        tk.Frame(dialog, bg='#e94560', height=2).pack(fill='x')
        
        tk.Label(
            dialog,
            text="Select how you want to capture the region:",
            bg='#0f0f23',
            fg='#888899',
            font=('Segoe UI', 10)
        ).pack(pady=(20, 15))
        
        def select_screen_region():
            dialog.destroy()
            self.root.withdraw()
            selector = RegionSelector()
            region_data = selector.select_region()
            self.root.deiconify()
            
            if region_data:
                region = MonitoredRegion()
                region.region_type = 'screen_region'
                region.region_data = region_data
                self.regions.append(region)
                self.refresh_region_list()
                self.save_config()
        
        def select_window():
            dialog.destroy()
            window_selector = WindowSelector()
            result = window_selector.select_window()
            
            if result:
                if result['mode'] == 'full_window':
                    region = MonitoredRegion()
                    region.region_type = 'full_window'
                    region.region_data = {
                        'title': result['window']['title'],
                        'hwnd': result['window']['window']._hWnd if hasattr(result['window']['window'], '_hWnd') else None
                    }
                    self.regions.append(region)
                    self.refresh_region_list()
                    self.save_config()
                elif result['mode'] == 'window_region':
                    self.root.withdraw()
                    region_selector = WindowRegionSelector(result['window'])
                    region_data = region_selector.select_region_in_window()
                    self.root.deiconify()
                    
                    if region_data:
                        region = MonitoredRegion()
                        region.region_type = 'window_region'
                        region.region_data = {
                            'window_title': result['window']['title'],
                            'hwnd': result['window']['window']._hWnd if hasattr(result['window']['window'], '_hWnd') else None,
                            'relative_left': region_data['relative_left'],
                            'relative_top': region_data['relative_top'],
                            'width': region_data['width'],
                            'height': region_data['height']
                        }
                        self.regions.append(region)
                        self.refresh_region_list()
                        self.save_config()
        
        # styled option buttons
        def create_option_btn(parent, icon, title, subtitle, command, color):
            btn_frame = tk.Frame(parent, bg=color, cursor='hand2')
            btn_frame.pack(fill='x', padx=30, pady=8)
            
            inner = tk.Frame(btn_frame, bg=color)
            inner.pack(fill='x', padx=15, pady=12)
            
            tk.Label(inner, text=icon, bg=color, fg='white', font=('Segoe UI Emoji', 20)).pack(side='left')
            
            text_frame = tk.Frame(inner, bg=color)
            text_frame.pack(side='left', padx=15)
            tk.Label(text_frame, text=title, bg=color, fg='white', font=('Segoe UI', 11, 'bold'), anchor='w').pack(anchor='w')
            tk.Label(text_frame, text=subtitle, bg=color, fg='#e8f1ff', font=('Segoe UI', 9), anchor='w').pack(anchor='w')
            
            # Make entire frame clickable
            for widget in [btn_frame, inner, text_frame] + list(inner.winfo_children()) + list(text_frame.winfo_children()):
                widget.bind('<Button-1>', lambda e, cmd=command: cmd())
            
            # Hover effects on the outer frame only
            def on_enter(e, frame=btn_frame, orig=color):
                # Lighten the color for hover
                frame.config(bg='#4a6fa5' if orig == '#3498db' else '#2ecc71')
            def on_leave(e, frame=btn_frame, orig=color):
                frame.config(bg=orig)
            btn_frame.bind('<Enter>', on_enter)
            btn_frame.bind('<Leave>', on_leave)
        
        create_option_btn(dialog, "📺", "Screen Region", "Select any area on screen", select_screen_region, '#3498db')
        create_option_btn(dialog, "🪟", "Window / Window Region", "Monitor a window or part of it", select_window, '#27ae60')
        
        tk.Button(
            dialog,
            text="Cancel",
            command=dialog.destroy,
            bg='#1a1a2e',
            fg='#888899',
            font=('Segoe UI', 10),
            relief='flat',
            padx=20,
            pady=8,
            cursor='hand2'
        ).pack(pady=20)
    
    def edit_region_settings(self, region):
        """Show settings dialog for a region with multiple detection rules"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Settings - {region.name}")
        dialog.geometry("600x750")
        dialog.minsize(580, 600)
        dialog.resizable(True, True)
        dialog.configure(bg='#0f0f23')
        dialog.attributes('-topmost', True)
        dialog.transient(self.root)
        
        # Working copy of rules (so we can cancel changes)
        working_rules = [rule.copy() for rule in region.detection_rules]
        
        # Header
        header = tk.Frame(dialog, bg='#1a1a2e', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text=f"⚙️ {region.name}",
            bg='#1a1a2e',
            fg='#ffffff',
            font=('Segoe UI', 14, 'bold')
        ).pack(side='left', padx=20, pady=12)
        
        tk.Frame(dialog, bg='#e94560', height=2).pack(fill='x')
        
        # Scrollable content
        canvas = tk.Canvas(dialog, bg='#0f0f23', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient='vertical', command=canvas.yview)
        content = tk.Frame(canvas, bg='#0f0f23')
        
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        content_window = canvas.create_window((0, 0), window=content, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(content_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.bind('<MouseWheel>', lambda e: self._scroll_canvas_if_needed(canvas, e))
        dialog.bind('<MouseWheel>', lambda e: self._scroll_canvas_if_needed(canvas, e))
        
        canvas.pack(side='left', fill='both', expand=True, padx=20, pady=15)
        scrollbar.pack(side='right', fill='y')
        
        def section_label(parent, text, icon=""):
            tk.Label(parent, text=f"{icon} {text}".strip(), bg='#0f0f23', fg='#e94560', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(15, 6))
            tk.Frame(parent, bg='#1a1a2e', height=1).pack(fill='x', pady=(0, 8))
        
        def field_label(parent, text):
            tk.Label(parent, text=text, bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 3))
        
        # Region Name
        section_label(content, "General", "📝")
        field_label(content, "Region Name")
        name_var = tk.StringVar(value=region.name)
        tk.Entry(content, textvariable=name_var, bg='#1a1a2e', fg='#ffffff', font=('Segoe UI', 11), width=40, relief='flat', insertbackground='#e94560').pack(anchor='w', ipady=5)
        
        # Monitoring Interval
        interval_frame = tk.Frame(content, bg='#0f0f23')
        interval_frame.pack(anchor='w', pady=(10, 0))
        tk.Label(interval_frame, text="Monitoring Interval:", bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(side='left')
        interval_var = tk.IntVar(value=region.monitoring_interval)
        tk.Spinbox(interval_frame, from_=1, to=60, textvariable=interval_var, bg='#1a1a2e', fg='#ffffff', font=('Segoe UI', 10), width=5, relief='flat').pack(side='left', padx=8)
        tk.Label(interval_frame, text="seconds", bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(side='left')
        
        # Capture Region Section
        section_label(content, "Capture Region", "📍")
        
        # Show current region info
        region_info_frame = tk.Frame(content, bg='#1a1a2e', padx=12, pady=10)
        region_info_frame.pack(fill='x', pady=(0, 10))
        
        type_info = {
            'screen_region': ('📺', 'Screen Region', '#3498db'),
            'window_region': ('🪟', 'Window Region', '#9b59b6'),
            'full_window': ('🖥️', 'Full Window', '#27ae60')
        }.get(region.region_type, ('❓', 'Not Set', '#666688'))
        
        region_type_label = tk.Label(
            region_info_frame,
            text=f"{type_info[0]} {type_info[1]}",
            bg='#1a1a2e',
            fg=type_info[2],
            font=('Segoe UI', 10, 'bold')
        )
        region_type_label.pack(anchor='w')
        
        # Show region details
        if region.region_type == 'screen_region' and region.region_data:
            details = f"Position: ({region.region_data.get('left', 0)}, {region.region_data.get('top', 0)}) | Size: {region.region_data.get('width', 0)}x{region.region_data.get('height', 0)}"
        elif region.region_type == 'full_window' and region.region_data:
            details = f"Window: {region.region_data.get('title', 'Unknown')[:40]}"
        elif region.region_type == 'window_region' and region.region_data:
            details = f"Window: {region.region_data.get('window_title', 'Unknown')[:30]} | Offset: ({region.region_data.get('relative_left', 0)}, {region.region_data.get('relative_top', 0)})"
        else:
            details = "No region configured"
        
        region_details_label = tk.Label(
            region_info_frame,
            text=details,
            bg='#1a1a2e',
            fg='#888899',
            font=('Segoe UI', 9)
        )
        region_details_label.pack(anchor='w', pady=(4, 0))
        
        # Change region buttons
        change_btn_frame = tk.Frame(content, bg='#0f0f23')
        change_btn_frame.pack(anchor='w', pady=(0, 5))
        
        def change_to_screen_region():
            dialog.withdraw()
            self.root.withdraw()
            selector = RegionSelector()
            new_region_data = selector.select_region()
            self.root.deiconify()
            dialog.deiconify()
            
            if new_region_data:
                region.region_type = 'screen_region'
                region.region_data = new_region_data
                # Update the display
                region_type_label.config(text="📺 Screen Region", fg='#3498db')
                region_details_label.config(text=f"Position: ({new_region_data.get('left', 0)}, {new_region_data.get('top', 0)}) | Size: {new_region_data.get('width', 0)}x{new_region_data.get('height', 0)}")
        
        def change_to_window():
            dialog.withdraw()
            window_selector = WindowSelector()
            result = window_selector.select_window()
            
            if result:
                if result['mode'] == 'full_window':
                    region.region_type = 'full_window'
                    region.region_data = {
                        'title': result['window']['title'],
                        'hwnd': result['window']['window']._hWnd if hasattr(result['window']['window'], '_hWnd') else None
                    }
                    dialog.deiconify()
                    region_type_label.config(text="🖥️ Full Window", fg='#27ae60')
                    region_details_label.config(text=f"Window: {result['window']['title'][:40]}")
                elif result['mode'] == 'window_region':
                    self.root.withdraw()
                    region_selector = WindowRegionSelector(result['window'])
                    new_region_data = region_selector.select_region_in_window()
                    self.root.deiconify()
                    dialog.deiconify()
                    
                    if new_region_data:
                        region.region_type = 'window_region'
                        region.region_data = {
                            'window_title': result['window']['title'],
                            'hwnd': result['window']['window']._hWnd if hasattr(result['window']['window'], '_hWnd') else None,
                            'relative_left': new_region_data['relative_left'],
                            'relative_top': new_region_data['relative_top'],
                            'width': new_region_data['width'],
                            'height': new_region_data['height']
                        }
                        region_type_label.config(text="🪟 Window Region", fg='#9b59b6')
                        region_details_label.config(text=f"Window: {result['window']['title'][:30]} | Offset: ({new_region_data['relative_left']}, {new_region_data['relative_top']})")
            else:
                dialog.deiconify()
        
        tk.Button(
            change_btn_frame,
            text="📺 Screen Region",
            command=change_to_screen_region,
            bg='#3498db',
            fg='white',
            font=('Segoe UI', 9),
            relief='flat',
            padx=12,
            pady=6,
            cursor='hand2'
        ).pack(side='left', padx=(0, 8))
        
        tk.Button(
            change_btn_frame,
            text="🪟 Window / Region",
            command=change_to_window,
            bg='#27ae60',
            fg='white',
            font=('Segoe UI', 9),
            relief='flat',
            padx=12,
            pady=6,
            cursor='hand2'
        ).pack(side='left')
        
        # Detection Rules Section
        section_label(content, "Detection Rules", "🎯")
        tk.Label(content, text="Each rule can have its own keywords, sound, and notifications", bg='#0f0f23', fg='#666688', font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 10))
        
        # Container for rules list
        rules_container = tk.Frame(content, bg='#0f0f23')
        rules_container.pack(fill='x', pady=5)
        
        def refresh_rules_list():
            """Rebuild the rules list UI"""
            for widget in rules_container.winfo_children():
                widget.destroy()
            
            for i, rule in enumerate(working_rules):
                create_rule_card(i, rule)
            
            # Update scroll region
            content.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox('all'))
        
        def create_rule_card(idx, rule):
            """Create a card for a single detection rule"""
            card = tk.Frame(rules_container, bg='#1a1a2e')
            card.pack(fill='x', pady=4)
            
            # Left accent
            accent_color = '#27ae60' if rule.get('sound_enabled') else '#666688'
            tk.Frame(card, bg=accent_color, width=3).pack(side='left', fill='y')
            
            card_inner = tk.Frame(card, bg='#1a1a2e')
            card_inner.pack(side='left', fill='x', expand=True, padx=10, pady=8)
            
            # Rule header row
            header_row = tk.Frame(card_inner, bg='#1a1a2e')
            header_row.pack(fill='x')
            
            # Rule name
            tk.Label(
                header_row,
                text=rule.get('name', f'Rule {idx+1}'),
                bg='#1a1a2e',
                fg='#ffffff',
                font=('Segoe UI', 10, 'bold')
            ).pack(side='left')
            
            # Buttons
            btn_frame = tk.Frame(header_row, bg='#1a1a2e')
            btn_frame.pack(side='right')
            
            tk.Button(
                btn_frame,
                text="✏️",
                command=lambda r=rule, i=idx: edit_rule(i, r),
                bg='#3498db',
                fg='white',
                font=('Segoe UI', 8),
                relief='flat',
                width=3,
                cursor='hand2'
            ).pack(side='left', padx=2)
            
            tk.Button(
                btn_frame,
                text="🔔",
                command=lambda r=rule: test_rule_sound(r),
                bg='#9b59b6',
                fg='white',
                font=('Segoe UI', 8),
                relief='flat',
                width=3,
                cursor='hand2'
            ).pack(side='left', padx=2)
            
            if len(working_rules) > 1:
                tk.Button(
                    btn_frame,
                    text="🗑",
                    command=lambda i=idx: delete_rule(i),
                    bg='#e74c3c',
                    fg='white',
                    font=('Segoe UI', 8),
                    relief='flat',
                    width=3,
                    cursor='hand2'
                ).pack(side='left', padx=2)
            
            # Info row
            info_row = tk.Frame(card_inner, bg='#1a1a2e')
            info_row.pack(fill='x', pady=(5, 0))
            
            # Keywords preview
            keywords = rule.get('keywords', [])
            kw_text = ", ".join(keywords[:3])
            if len(keywords) > 3:
                kw_text += f" +{len(keywords)-3}"
            tk.Label(
                info_row,
                text=f"🎯 {kw_text}" if keywords else "🎯 (no keywords)",
                bg='#1a1a2e',
                fg='#e94560' if keywords else '#666688',
                font=('Segoe UI', 8)
            ).pack(side='left', padx=(0, 15))
            
            # Sound info
            sound = rule.get('sound_file', 'level_up.mp3').replace('.mp3', '').replace('.wav', '')[:10]
            vol = int(rule.get('volume', 0.8) * 100)
            sound_text = f"🔊 {sound} {vol}%" if rule.get('sound_enabled') else "🔇 Off"
            tk.Label(
                info_row,
                text=sound_text,
                bg='#1a1a2e',
                fg='#9b59b6' if rule.get('sound_enabled') else '#666688',
                font=('Segoe UI', 8)
            ).pack(side='left', padx=(0, 15))
            
            # Discord indicator
            if rule.get('discord_enabled'):
                tk.Label(
                    info_row,
                    text="💬 Discord",
                    bg='#1a1a2e',
                    fg='#5865f2',
                    font=('Segoe UI', 8)
                ).pack(side='left')
        
        def test_rule_sound(rule):
            """Test sound for a specific rule"""
            if rule.get('sound_enabled'):
                play_sound_with_volume(rule.get('sound_file', 'level_up.mp3'), rule.get('volume', 0.8))
        
        def delete_rule(idx):
            """Delete a rule"""
            if len(working_rules) > 1:
                working_rules.pop(idx)
                refresh_rules_list()
        
        def add_rule():
            """Add a new rule"""
            new_rule = {
                'name': f'Rule {len(working_rules) + 1}',
                'keywords': [],
                'sound_enabled': True,
                'sound_file': 'level_up.mp3',
                'volume': 0.8,
                'discord_enabled': False,
                'discord_webhook_url': '',
                'discord_cooldown': 30
            }
            working_rules.append(new_rule)
            refresh_rules_list()
            edit_rule(len(working_rules) - 1, new_rule)
        
        def edit_rule(idx, rule):
            """Open rule editor dialog"""
            rule_dialog = tk.Toplevel(dialog)
            rule_dialog.title(f"Edit Rule - {rule.get('name', 'Rule')}")
            rule_dialog.geometry("480x720")
            rule_dialog.configure(bg='#0f0f23')
            rule_dialog.attributes('-topmost', True)
            rule_dialog.transient(dialog)
            rule_dialog.grab_set()
            
            # Header
            rh = tk.Frame(rule_dialog, bg='#1a1a2e', height=45)
            rh.pack(fill='x')
            rh.pack_propagate(False)
            tk.Label(rh, text=f"✏️ Edit Detection Rule", bg='#1a1a2e', fg='#ffffff', font=('Segoe UI', 12, 'bold')).pack(side='left', padx=15, pady=10)
            tk.Frame(rule_dialog, bg='#e94560', height=2).pack(fill='x')
            
            # Content
            rc = tk.Frame(rule_dialog, bg='#0f0f23')
            rc.pack(fill='both', expand=True, padx=20, pady=15)
            
            # Rule name
            field_label(rc, "Rule Name")
            rule_name_var = tk.StringVar(value=rule.get('name', ''))
            tk.Entry(rc, textvariable=rule_name_var, bg='#1a1a2e', fg='#ffffff', font=('Segoe UI', 10), width=35, relief='flat', insertbackground='#e94560').pack(anchor='w', ipady=4)
            
            # Keywords
            field_label(rc, "Keywords (one per line)")
            kw_text = tk.Text(rc, bg='#1a1a2e', fg='#00ff88', font=('Consolas', 10), height=5, width=40, relief='flat', insertbackground='#e94560')
            kw_text.pack(anchor='w', pady=(0, 10))
            kw_text.insert('1.0', '\n'.join(rule.get('keywords', [])))
            
            # Sound settings
            section_label(rc, "Sound", "🔊")
            
            sound_en_var = tk.BooleanVar(value=rule.get('sound_enabled', True))
            tk.Checkbutton(rc, text="Enable Sound", variable=sound_en_var, bg='#0f0f23', fg='#ffffff', selectcolor='#9b59b6', activebackground='#0f0f23', font=('Segoe UI', 10), cursor='hand2').pack(anchor='w')
            
            sf = tk.Frame(rc, bg='#0f0f23')
            sf.pack(anchor='w', fill='x', pady=5)
            tk.Label(sf, text="Sound:", bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(side='left')
            sound_var = tk.StringVar(value=rule.get('sound_file', 'level_up.mp3'))
            sounds = get_available_sounds()
            if sounds:
                ttk.Combobox(sf, textvariable=sound_var, values=sounds, state='readonly', width=22).pack(side='left', padx=8)
            
            vf = tk.Frame(rc, bg='#0f0f23')
            vf.pack(anchor='w', fill='x', pady=5)
            tk.Label(vf, text="Volume:", bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(side='left')
            vol_var = tk.DoubleVar(value=rule.get('volume', 0.8))
            tk.Scale(vf, from_=0, to=1, resolution=0.05, orient='horizontal', variable=vol_var, bg='#1a1a2e', fg='#ffffff', highlightthickness=0, troughcolor='#0f0f23', activebackground='#e94560', length=150, sliderrelief='flat').pack(side='left', padx=8)
            vol_lbl = tk.Label(vf, text=f"{int(vol_var.get()*100)}%", bg='#0f0f23', fg='#e94560', font=('Segoe UI', 9, 'bold'), width=4)
            vol_lbl.pack(side='left')
            vol_var.trace_add('write', lambda *a: vol_lbl.config(text=f"{int(vol_var.get()*100)}%"))
            
            tk.Button(rc, text="🔔 Test", command=lambda: play_sound_with_volume(sound_var.get(), vol_var.get()) if sound_en_var.get() else None, bg='#9b59b6', fg='white', font=('Segoe UI', 8), relief='flat', padx=10, cursor='hand2').pack(anchor='w', pady=5)
            
            # Discord settings
            section_label(rc, "Discord", "💬")
            
            dc_en_var = tk.BooleanVar(value=rule.get('discord_enabled', False))
            tk.Checkbutton(rc, text="Enable Discord Notifications", variable=dc_en_var, bg='#0f0f23', fg='#ffffff', selectcolor='#5865f2', activebackground='#0f0f23', font=('Segoe UI', 10), cursor='hand2').pack(anchor='w')
            
            field_label(rc, "Webhook URL")
            wh_var = tk.StringVar(value=rule.get('discord_webhook_url', ''))
            tk.Entry(rc, textvariable=wh_var, bg='#1a1a2e', fg='#5865f2', font=('Consolas', 9), width=45, relief='flat', insertbackground='#e94560').pack(anchor='w', ipady=3)
            
            cdf = tk.Frame(rc, bg='#0f0f23')
            cdf.pack(anchor='w', pady=5)
            tk.Label(cdf, text="Cooldown:", bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(side='left')
            cd_var = tk.IntVar(value=rule.get('discord_cooldown', 30))
            tk.Spinbox(cdf, from_=5, to=300, textvariable=cd_var, bg='#1a1a2e', fg='#ffffff', font=('Segoe UI', 10), width=5, relief='flat').pack(side='left', padx=8)
            tk.Label(cdf, text="seconds", bg='#0f0f23', fg='#888899', font=('Segoe UI', 9)).pack(side='left')
            
            # Save/Cancel buttons
            btn_row = tk.Frame(rc, bg='#0f0f23')
            btn_row.pack(fill='x', pady=(20, 0))
            
            def save_rule():
                rule['name'] = rule_name_var.get() or f'Rule {idx+1}'
                rule['keywords'] = [k.strip() for k in kw_text.get('1.0', 'end').strip().split('\n') if k.strip()]
                rule['sound_enabled'] = sound_en_var.get()
                rule['sound_file'] = sound_var.get()
                rule['volume'] = vol_var.get()
                rule['discord_enabled'] = dc_en_var.get()
                rule['discord_webhook_url'] = wh_var.get()
                rule['discord_cooldown'] = cd_var.get()
                rule_dialog.destroy()
                refresh_rules_list()
            
            tk.Button(btn_row, text="💾 Save Rule", command=save_rule, bg='#27ae60', fg='white', font=('Segoe UI', 10, 'bold'), relief='flat', padx=20, pady=8, cursor='hand2').pack(side='left')
            tk.Button(btn_row, text="Cancel", command=rule_dialog.destroy, bg='#1a1a2e', fg='#888899', font=('Segoe UI', 10), relief='flat', padx=15, pady=8, cursor='hand2').pack(side='left', padx=10)
        
        # Add Rule button
        tk.Button(
            content,
            text="➕ Add Detection Rule",
            command=add_rule,
            bg='#9b59b6',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            padx=15,
            pady=8,
            cursor='hand2'
        ).pack(anchor='w', pady=(10, 0))
        
        # Build initial rules list
        refresh_rules_list()
        
        # Save button
        def save_settings():
            region.name = name_var.get()
            region.monitoring_interval = interval_var.get()
            region.detection_rules = working_rules
            
            self.save_config()
            self.refresh_region_list()
            dialog.destroy()
        
        tk.Frame(content, bg='#0f0f23', height=20).pack()
        
        tk.Button(
            content,
            text="💾 Save All Settings",
            command=save_settings,
            bg='#e94560',
            fg='white',
            font=('Segoe UI', 12, 'bold'),
            relief='flat',
            padx=30,
            pady=10,
            cursor='hand2'
        ).pack(pady=15)
    
    def delete_region(self, region):
        """Delete a region after confirmation"""
        if messagebox.askyesno("Delete Region", f"Delete '{region.name}'?"):
            region.running = False
            self.regions.remove(region)
            self.save_config()
            self.refresh_region_list()
    
    def start_region(self, region):
        """Start monitoring a region"""
        if not region.region_data:
            messagebox.showwarning("No Region", "This region has no area configured.")
            return
        
        region.running = True
        region.paused = False
        region.last_status = "Running"
        region.thread = threading.Thread(target=self.monitoring_loop, args=(region,), daemon=True)
        region.thread.start()
        self.update_region_status(region)
    
    def stop_region(self, region):
        """Stop monitoring a region"""
        region.running = False
        region.paused = False
        region.last_status = "Stopped"
        self.update_region_status(region)
    
    def pause_region(self, region):
        """Pause monitoring a region"""
        region.paused = True
        region.last_status = "Paused"
        self.update_region_status(region)
    
    def resume_region(self, region):
        """Resume monitoring a region"""
        region.paused = False
        region.last_status = "Running"
        self.update_region_status(region)
    
    def do_capture_and_preview(self, region):
        """Capture region and show preview window"""
        try:
            capture_coords = self.get_capture_region(region)
            if not capture_coords:
                messagebox.showerror("Capture Failed", 
                    f"Could not get capture region.\n\n"
                    f"Type: {region.region_type}\n"
                    f"Data: {region.region_data}")
                return
            
            with mss.mss() as sct:
                img = sct.grab(capture_coords)
                pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                
                # Store for preview
                region.last_capture = pil_img.copy()
                
                # OCR
                text = pytesseract.image_to_string(pil_img).strip()
                region.last_ocr_text = text
                
                # Show preview
                region.show_preview_window(self.root, refresh_callback=lambda: self.do_capture_and_preview(region))
                
        except Exception as e:
            messagebox.showerror("Capture Error", f"Error capturing region:\n{str(e)}")
    
    def start_all(self):
        """Start all regions"""
        for region in self.regions:
            if not region.running and region.region_data:
                self.start_region(region)
    
    def stop_all(self):
        """Stop all regions"""
        for region in self.regions:
            region.running = False
            region.paused = False
            region.last_status = "Stopped"
            self.update_region_status(region)
    
    def monitoring_loop(self, region):
        """Main monitoring loop for a region"""
        try:
            with mss.mss() as sct:
                while region.running:
                    if region.paused:
                        time.sleep(0.5)
                        continue
                    
                    try:
                        capture_region = self.get_capture_region(region)
                        if not capture_region:
                            region.last_status = "Region not available"
                            print(f"[{region.name}] Region not available")
                            time.sleep(region.monitoring_interval)
                            continue
                        
                        # Capture the region
                        img = sct.grab(capture_region)
                        pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                        
                        # Store for preview
                        region.last_capture = pil_img.copy()
                        
                        # OCR
                        text = pytesseract.image_to_string(pil_img).strip()
                        region.last_ocr_text = text
                        
                        # Auto-update preview window if open
                        if region.preview_window and region.preview_window.winfo_exists():
                            try:
                                region.preview_window.after(0, region.update_preview_content)
                            except:
                                pass
                        
                        # Check for targets using detection rules
                        found_targets = region.check_rules(text)
                        
                        if found_targets:
                            region.last_status = f"Found: {', '.join(found_targets)}"
                            print(f"[{region.name}] Found: {found_targets}")
                            # Update status and highlight the region
                            self.root.after(0, lambda: self.update_region_status(region))
                            self.root.after(0, lambda: self.highlight_region(region.id))
                        else:
                            region.last_status = "Monitoring"
                        
                    except Exception as e:
                        region.last_status = f"Error: {str(e)[:30]}"
                        print(f"[{region.name}] Error: {e}")
                    
                    time.sleep(region.monitoring_interval)
                    
        except Exception as e:
            print(f"[{region.name}] Monitoring error: {e}")
        finally:
            region.last_status = "Stopped"
            print(f"[{region.name}] Monitoring stopped")
    
    def get_capture_region(self, region):
        """Get the capture coordinates for a region"""
        try:
            if region.region_type == 'screen_region':
                return region.region_data
            
            elif region.region_type == 'full_window':
                window = self._find_window_by_hwnd_or_title(region.region_data)
                if window and window.visible and window.width > 0 and window.height > 0:
                    return {"left": window.left, "top": window.top, "width": window.width, "height": window.height}
                title = region.region_data.get('title', '')
                print(f"[{region.name}] Window '{title}' not found or not visible")
            
            elif region.region_type == 'window_region':
                window = self._find_window_by_hwnd_or_title(region.region_data)
                if window and window.visible and window.width > 0 and window.height > 0:
                    rel_left = region.region_data.get('relative_left', 0)
                    rel_top = region.region_data.get('relative_top', 0)
                    width = region.region_data.get('width', 100)
                    height = region.region_data.get('height', 100)
                    
                    result = {
                        "left": window.left + rel_left,
                        "top": window.top + rel_top,
                        "width": width,
                        "height": height
                    }
                    return result
                title = region.region_data.get('window_title', region.region_data.get('title', ''))
                print(f"[{region.name}] Window '{title}' not found or not visible")
                
        except Exception as e:
            print(f"Error getting capture region for {region.name}: {e}")
        return None
    
    def _find_window_by_hwnd_or_title(self, region_data):
        """Find a specific window by hwnd first, then fall back to title"""
        hwnd = region_data.get('hwnd')
        title = region_data.get('window_title', region_data.get('title', ''))
        
        try:
            all_windows = gw.getAllWindows()
            
            # First try to find by hwnd (exact match)
            if hwnd:
                for w in all_windows:
                    if hasattr(w, '_hWnd') and w._hWnd == hwnd:
                        if w.visible and w.width > 0 and w.height > 0:
                            return w
            
            # Fall back to title match (for config files without hwnd)
            if title:
                for w in all_windows:
                    if w.title == title and w.visible and w.width > 0 and w.height > 0:
                        return w
                        
        except Exception as e:
            print(f"Error finding window: {e}")
        
        return None
    
    def on_close(self):
        """Handle window close"""
        self.stop_all()
        self.save_config()
        self.root.destroy()

class WindowSelector:
    """Window selection dialog for choosing which window to monitor"""
    
    def __init__(self):
        self.selected_window = None
        
    def get_all_windows(self):
        """Get all visible windows with titles"""
        windows = []
        try:
            all_windows = gw.getAllWindows()
            for window in all_windows:
                if window.title.strip() and window.visible and window.width > 100 and window.height > 100:
                    windows.append({
                        'title': window.title,
                        'window': window
                    })
        except Exception as e:
            print(f"Error getting windows: {e}")
        return windows
    
    def select_window(self):
        """Show window selection dialog"""
        windows = self.get_all_windows()
        
        if not windows:
            messagebox.showerror("No Windows", "No suitable windows found")
            return None
        
        root = tk.Tk()
        root.title("Select Window")
        root.geometry("620x450")
        root.resizable(True, True)
        root.configure(bg='#0f0f23')
        root.attributes('-topmost', True)
        
        # Header
        header = tk.Frame(root, bg='#1a1a2e', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🪟 Select Window to Monitor",
            bg='#1a1a2e',
            fg='#ffffff',
            font=('Segoe UI', 14, 'bold')
        ).pack(side='left', padx=20, pady=12)
        
        tk.Frame(root, bg='#e94560', height=2).pack(fill='x')
        
        tk.Label(
            root,
            text="Choose a window from the list below:",
            bg='#0f0f23',
            fg='#888899',
            font=('Segoe UI', 10)
        ).pack(pady=(15, 10))
        
        # Listbox with custom style
        frame = tk.Frame(root, bg='#1a1a2e', padx=2, pady=2)
        frame.pack(fill='both', expand=True, padx=20, pady=5)
        
        scrollbar = tk.Scrollbar(frame, bg='#1a1a2e')
        scrollbar.pack(side='right', fill='y')
        
        listbox = tk.Listbox(
            frame,
            yscrollcommand=scrollbar.set,
            font=('Consolas', 10),
            bg='#0f0f23',
            fg='#ffffff',
            selectbackground='#e94560',
            selectforeground='white',
            highlightthickness=0,
            relief='flat',
            activestyle='none'
        )
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=listbox.yview)
        
        for i, window in enumerate(windows):
            title = window['title'][:65] + "..." if len(window['title']) > 65 else window['title']
            listbox.insert(tk.END, f"  {i+1}. {title}")
        
        selected_window = None
        selected_mode = None
        
        btn_frame = tk.Frame(root, bg='#0f0f23')
        btn_frame.pack(fill='x', padx=20, pady=15)
        
        def on_full_window():
            nonlocal selected_window, selected_mode
            selection = listbox.curselection()
            if selection:
                selected_window = windows[selection[0]]
                selected_mode = "full_window"
                root.quit()
                root.destroy()
            else:
                messagebox.showwarning("No Selection", "Please select a window first")
        
        def on_window_region():
            nonlocal selected_window, selected_mode
            selection = listbox.curselection()
            if selection:
                selected_window = windows[selection[0]]
                selected_mode = "window_region"
                root.quit()
                root.destroy()
            else:
                messagebox.showwarning("No Selection", "Please select a window first")
        
        def on_cancel():
            root.quit()
            root.destroy()
        
        tk.Button(
            btn_frame,
            text="🖥️ Monitor Full Window",
            command=on_full_window,
            bg='#27ae60',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            padx=15,
            pady=10,
            cursor='hand2'
        ).pack(side='left', padx=(0, 8))
        
        tk.Button(
            btn_frame,
            text="🪟 Select Region in Window",
            command=on_window_region,
            bg='#3498db',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            padx=15,
            pady=10,
            cursor='hand2'
        ).pack(side='left', padx=8)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            command=on_cancel,
            bg='#1a1a2e',
            fg='#888899',
            font=('Segoe UI', 10),
            relief='flat',
            padx=15,
            pady=10,
            cursor='hand2'
        ).pack(side='right')
        
        root.mainloop()
        
        if selected_mode:
            return {"mode": selected_mode, "window": selected_window}
        return None

class RegionSelector:
    def __init__(self):
        self.start_x = 0
        self.start_y = 0
        self.end_x = 0
        self.end_y = 0
        self.selecting = False
        self.selection_complete = False
        self.selected_region = None
        
    def get_virtual_screen_bounds(self):
        """Get the bounds of the entire virtual screen (all monitors)"""
        with mss.mss() as sct:
            # Monitor 0 is the virtual screen containing all monitors
            virtual_screen = sct.monitors[0]
            return virtual_screen
        
    def select_region(self):
        """Create a fullscreen overlay for region selection across all monitors"""
        print("Getting monitor information...")
        
        # Get virtual screen bounds
        virtual_bounds = self.get_virtual_screen_bounds()
        print(f"Virtual screen: {virtual_bounds}")
        
        # Create fullscreen window covering the entire virtual screen
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the window initially
        
        # Set window geometry to cover all monitors
        geometry = f"{virtual_bounds['width']}x{virtual_bounds['height']}+{virtual_bounds['left']}+{virtual_bounds['top']}"
        self.root.geometry(geometry)
        self.root.attributes('-alpha', 0.3)  # Semi-transparent
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.configure(bg='black')
        
        # Show the window
        self.root.deiconify()
        self.root.update()
        
        # Create canvas
        self.canvas = tk.Canvas(
            self.root, 
            highlightthickness=0, 
            bg='black',
            width=virtual_bounds['width'],
            height=virtual_bounds['height']
        )
        self.canvas.pack(fill='both', expand=True)
        
        # Bind events
        self.canvas.bind('<Button-1>', self.start_selection)
        self.canvas.bind('<B1-Motion>', self.update_selection)
        self.canvas.bind('<ButtonRelease-1>', self.end_selection)
        self.root.bind('<Escape>', self.cancel_selection)
        
        # Make sure the window can receive keyboard events
        self.root.focus_force()
        
        # Instructions - position them in the center of the primary monitor
        center_x = virtual_bounds['width'] // 2
        self.canvas.create_text(
            center_x, 50,
            text="Click and drag to select monitoring region across ANY monitor | ESC to cancel",
            fill='white', font=('Arial', 16), width=800
        )
        
        self.root.mainloop()
        return self.selected_region
    
    def start_selection(self, event):
        # Convert canvas coordinates to global screen coordinates
        virtual_bounds = self.get_virtual_screen_bounds()
        self.start_x = event.x + virtual_bounds['left']
        self.start_y = event.y + virtual_bounds['top']
        self.selecting = True
        
    def update_selection(self, event):
        if self.selecting:
            # Convert canvas coordinates to global screen coordinates
            virtual_bounds = self.get_virtual_screen_bounds()
            self.end_x = event.x + virtual_bounds['left']
            self.end_y = event.y + virtual_bounds['top']
            
            # Clear previous rectangle
            self.canvas.delete('selection_rect')
            
            # Draw selection rectangle in canvas coordinates
            x1 = min(self.start_x, self.end_x) - virtual_bounds['left']
            y1 = min(self.start_y, self.end_y) - virtual_bounds['top']
            x2 = max(self.start_x, self.end_x) - virtual_bounds['left']
            y2 = max(self.start_y, self.end_y) - virtual_bounds['top']
            
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline='red', width=3, tags='selection_rect'
            )
    
    def end_selection(self, event):
        if self.selecting:
            # Convert canvas coordinates to global screen coordinates
            virtual_bounds = self.get_virtual_screen_bounds()
            self.end_x = event.x + virtual_bounds['left']
            self.end_y = event.y + virtual_bounds['top']
            self.selecting = False
            
            # Calculate region
            left = min(self.start_x, self.end_x)
            top = min(self.start_y, self.end_y)
            width = abs(self.end_x - self.start_x)
            height = abs(self.end_y - self.start_y)
            
            if width > 10 and height > 10:  # Minimum size check
                self.selected_region = {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height
                }
                self.root.quit()
                self.root.destroy()
            else:
                messagebox.showwarning("Invalid Selection", "Please select a larger area")
    
    def cancel_selection(self, event):
        self.selected_region = None
        self.root.quit()
        self.root.destroy()

class WindowRegionSelector:
    def __init__(self, window_info):
        self.window_info = window_info
        self.window = window_info['window']
        self.start_x = 0
        self.start_y = 0
        self.end_x = 0
        self.end_y = 0
        self.selecting = False
        self.selected_region = None
        
    def test_coordinate_mapping(self):
        """Test and display coordinate mapping for debugging"""
        window = self.window
        print(f"=== COORDINATE MAPPING TEST ===")
        print(f"Window reported bounds: left={window.left}, top={window.top}, width={window.width}, height={window.height}")
        
        try:
            with mss.mss() as sct:
                test_region = {
                    "left": window.left,
                    "top": window.top,
                    "width": 100,
                    "height": 100
                }
                img = sct.grab(test_region)
                pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                pil_img.save("test_capture.png")
                print("Saved test_capture.png - check if this shows the top-left of your window")
        except Exception as e:
            print(f"Test capture failed: {e}")
        
        print(f"=== END TEST ===")
        
    def select_region_in_window(self):
        """Create an overlay specifically for the selected window"""
        try:
            window = self.window
            if not window.visible:
                messagebox.showerror("Window Not Visible", "The selected window is not visible")
                return None
            
            print(f"Click and drag to select a region within: {window.title}")
            self.test_coordinate_mapping()
            
            # Create overlay window positioned over the ENTIRE window
            self.root = tk.Tk()
            self.root.title(f"TextHunter - Select Region in: {window.title}")
            self.root.geometry(f"{window.width}x{window.height}+{window.left}+{window.top}")
            self.root.attributes('-alpha', 0.3)
            self.root.attributes('-topmost', True)
            self.root.overrideredirect(True)
            self.root.configure(bg='blue')
            
            # Create canvas
            self.canvas = tk.Canvas(
                self.root, 
                highlightthickness=0, 
                bg='blue',
                width=window.width,
                height=window.height
            )
            self.canvas.pack(fill='both', expand=True)
            
            # Bind events
            self.canvas.bind('<Button-1>', self.start_selection)
            self.canvas.bind('<B1-Motion>', self.update_selection)
            self.canvas.bind('<ButtonRelease-1>', self.end_selection)
            self.root.bind('<Escape>', self.cancel_selection)
            
            self.root.focus_force()
            
            # Instructions
            self.canvas.create_text(
                window.width // 2, 30,
                text=f"Select region within: {window.title[:50]}... | ESC to cancel",
                fill='white', font=('Arial', 12, 'bold'),
                width=window.width - 20
            )
            
            # Show coordinate reference points
            self.canvas.create_rectangle(5, 5, 15, 15, fill='red', outline='yellow', width=2)
            self.canvas.create_text(20, 10, text="(0,0)", fill='yellow', font=('Arial', 10), anchor='w')
            
            self.root.mainloop()
            return self.selected_region
            
        except Exception as e:
            print(f"Error creating window overlay: {e}")
            return None
    
    def start_selection(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.selecting = True
        
    def update_selection(self, event):
        if self.selecting:
            self.end_x = event.x
            self.end_y = event.y
            
            # Clear previous rectangle
            self.canvas.delete('selection_rect')
            
            # Draw selection rectangle
            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            x2 = max(self.start_x, self.end_x)
            y2 = max(self.start_y, self.end_y)
            
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline='red', width=3, tags='selection_rect'
            )
    
    def end_selection(self, event):
        if self.selecting:
            self.end_x = event.x
            self.end_y = event.y
            self.selecting = False
            
            left = min(self.start_x, self.end_x)
            top = min(self.start_y, self.end_y)
            width = abs(self.end_x - self.start_x)
            height = abs(self.end_y - self.start_y)
            
            if width > 10 and height > 10:
                self.selected_region = {
                    "relative_left": left,
                    "relative_top": top,
                    "width": width,
                    "height": height,
                    "window": self.window_info
                }
                self.root.quit()
                self.root.destroy()
            else:
                messagebox.showwarning("Invalid Selection", "Please select a larger area")

    def cancel_selection(self, event):
        self.selected_region = None
        self.root.quit()
        self.root.destroy()

class WindowMonitor:
    def __init__(self, window_info):
        self.window_info = window_info
        self.window = window_info['window']
        
    def get_window_region(self):
        """Get current window position and size"""
        try:
            self.window = gw.getWindowsWithTitle(self.window.title)[0] if gw.getWindowsWithTitle(self.window.title) else None
            
            if not self.window or not self.window.visible:
                return None
                
            return {
                "left": self.window.left,
                "top": self.window.top,
                "width": self.window.width,
                "height": self.window.height
            }
        except Exception as e:
            print(f"Error getting window region: {e}")
            return None


def main():
    """Main entry point - start the TextHunter application"""
    print("TextHunter - Advanced Text Monitoring Tool")
    print("=" * 50)
    
    # Check for single instance
    if not check_single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "TextHunter Already Running",
            "Another instance of TextHunter is already running.\n\n"
            "Only one instance can run at a time."
        )
        root.destroy()
        sys.exit(1)
    
    app = TextHunterApp()
    app.run()


if __name__ == "__main__":
    main()
