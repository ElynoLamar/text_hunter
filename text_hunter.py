# TextHunter - Advanced Text Monitoring Tool
import time
import mss
from PIL import Image, ImageTk
import pytesseract
from playsound import playsound
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import pygetwindow as gw
import sys
import os
import json
import requests
from datetime import datetime, timedelta

# --- TESSERACT PATH (keep if needed) ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ────────────────────── CONFIG ──────────────────────
CONFIG_FILE = 'texthunter_config.json'

# Default target keys - fallback if no config file exists
DEFAULT_TARGET_KEYS = ['Griffon Egg', 'King of Greed']

def load_config():
    """Load configuration from file"""
    try:
        config_path = get_config_file_path()
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                target_keys = config.get('target_keys', DEFAULT_TARGET_KEYS)
                print(f"Loaded {len(target_keys)} target keys from config: {target_keys}")
                
                # Load notification settings
                notification_settings = config.get('notification_settings', {})
                if notification_settings:
                    notification_manager.sound_enabled = notification_settings.get('sound_enabled', True)
                    notification_manager.discord_enabled = notification_settings.get('discord_enabled', False)
                    notification_manager.selected_sound = notification_settings.get('selected_sound', 'level_up.mp3')
                    notification_manager.discord_webhook_url = notification_settings.get('discord_webhook_url', '')
                    print(f"Loaded notification settings: Sound={notification_manager.sound_enabled}, Discord={notification_manager.discord_enabled}")
                
                # Load timing settings
                timing_settings = config.get('timing_settings', {})
                if timing_settings:
                    notification_manager.monitoring_interval = timing_settings.get('monitoring_interval', 5)
                    notification_manager.discord_cooldown = timing_settings.get('discord_cooldown', 30)
                    print(f"Loaded timing settings: Interval={notification_manager.monitoring_interval}s, Cooldown={notification_manager.discord_cooldown}s")
                
                return target_keys
        else:
            print("No config file found, using default targets")
            return DEFAULT_TARGET_KEYS.copy()
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_TARGET_KEYS.copy()

def save_config(target_keys):
    """Save configuration to file"""
    try:
        config = {
            'target_keys': target_keys,
            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        config_path = get_config_file_path()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Config saved successfully: {len(target_keys)} target keys")
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def get_config_file_path():
    """Get the correct path to the config file when running as exe or script"""
    if getattr(sys, 'frozen', False):
        # Running as exe - save config next to the exe
        exe_dir = os.path.dirname(sys.executable)
        return os.path.join(exe_dir, CONFIG_FILE)
    else:
        # Running as script - save in script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, CONFIG_FILE)

# Load target keys from config at startup
TARGET_KEYS = load_config()
DEBUG_IMG = 'debug.png'

# ────────────────────── NOTIFICATION SYSTEM ──────────────────────
class NotificationManager:
    def __init__(self):
        self.sound_enabled = True
        self.discord_enabled = False
        self.selected_sound = "level_up.mp3"
        self.discord_webhook_url = ""
        self.last_discord_notification = None
        self.discord_cooldown = 30  # 30 seconds cooldown
        self.monitoring_interval = 5  # 5 seconds monitoring interval
        
    def get_available_sounds(self):
        """Get list of available sound files from ./sounds folder"""
        sounds_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')
        if not os.path.exists(sounds_dir):
            return []
        
        sound_files = []
        for file in os.listdir(sounds_dir):
            if file.lower().endswith(('.mp3', '.wav', '.ogg')):
                sound_files.append(file)
        return sorted(sound_files)
    
    def play_selected_sound(self):
        """Play the currently selected sound"""
        if not self.sound_enabled:
            return
            
        try:
            sounds_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')
            sound_path = os.path.join(sounds_dir, self.selected_sound)
            
            if os.path.exists(sound_path):
                playsound(sound_path)
                print(f"Played sound: {self.selected_sound}")
            else:
                print(f"Sound file not found: {sound_path}")
                # Fallback to system beep
                import winsound
                winsound.Beep(1000, 500)
        except Exception as e:
            print(f"Error playing sound: {e}")
            try:
                import winsound
                winsound.Beep(1000, 500)
            except:
                pass
    
    def send_discord_notification(self, found_text):
        """Send notification to Discord webhook with cooldown"""
        if not self.discord_enabled or not self.discord_webhook_url.strip():
            return
        
        # Check cooldown
        now = datetime.now()
        if (self.last_discord_notification and 
            now - self.last_discord_notification < timedelta(seconds=self.discord_cooldown)):
            time_left = self.discord_cooldown - (now - self.last_discord_notification).seconds
            print(f"Discord notification on cooldown. {time_left}s remaining.")
            return
        
        try:
            message = f'@everyone TextHunter has found the text "{found_text}"!'
            
            payload = {
                "content": message,
                "username": "TextHunter Bot"
            }
            
            response = requests.post(self.discord_webhook_url, json=payload, timeout=10)
            
            if response.status_code == 204:
                print(f"Discord notification sent: {message}")
                self.last_discord_notification = now
            else:
                print(f"Discord notification failed: {response.status_code}")
                
        except Exception as e:
            print(f"Error sending Discord notification: {e}")
    
    def notify(self, found_targets):
        """Send notifications using enabled methods"""
        found_text = ", ".join(found_targets)
        
        # Play sound in separate thread
        if self.sound_enabled:
            threading.Thread(target=self.play_selected_sound, daemon=True).start()
        
        # Send Discord notification in separate thread
        if self.discord_enabled:
            threading.Thread(target=self.send_discord_notification, args=(found_text,), daemon=True).start()

# Global notification manager
notification_manager = NotificationManager()

class NotificationSettingsDialog:
    def __init__(self, parent):
        self.parent = parent
        self.result = {'saved': False}
        
    def show_settings(self):
        """Show notification settings dialog"""
        root = tk.Toplevel(self.parent)
        root.title("TextHunter - Notification Settings")
        root.geometry("500x800")  
        root.resizable(True, True)
        root.configure(bg='#2d2d30')
        root.attributes('-topmost', True)
        
        # Title
        title_label = tk.Label(
            root,
            text="🔔 Notification Settings",
            bg='#2d2d30',
            fg='#ffffff',
            font=('Arial', 14, 'bold')
        )
        title_label.pack(pady=15)
        
        # Main frame with scrollable area
        main_frame = tk.Frame(root, bg='#2d2d30')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Sound notification section
        sound_frame = tk.LabelFrame(
            main_frame,
            text="Sound Notifications",
            bg='#2d2d30',
            fg='#ffffff',
            font=('Arial', 11, 'bold'),
            padx=10,
            pady=10
        )
        sound_frame.pack(fill='x', pady=5)
        
        # Sound enabled checkbox
        self.sound_var = tk.BooleanVar(value=notification_manager.sound_enabled)
        sound_check = tk.Checkbutton(
            sound_frame,
            text="🔊 Enable sound notifications",
            variable=self.sound_var,
            bg='#2d2d30',
            fg='#ffffff',
            selectcolor='#8e44ad',
            font=('Arial', 10),
            command=self.toggle_sound_controls
        )
        sound_check.pack(anchor='w', pady=5)
        
        # Sound selection frame
        self.sound_select_frame = tk.Frame(sound_frame, bg='#2d2d30')
        self.sound_select_frame.pack(fill='x', pady=5)
        
        tk.Label(
            self.sound_select_frame,
            text="Select sound:",
            bg='#2d2d30',
            fg='#cccccc',
            font=('Arial', 9)
        ).pack(anchor='w')
        
        # Sound dropdown
        self.sound_var_dropdown = tk.StringVar(value=notification_manager.selected_sound)
        available_sounds = notification_manager.get_available_sounds()
        
        if available_sounds:
            self.sound_dropdown = ttk.Combobox(
                self.sound_select_frame,
                textvariable=self.sound_var_dropdown,
                values=available_sounds,
                state="readonly",
                width=30
            )
            self.sound_dropdown.pack(anchor='w', pady=2)
        else:
            tk.Label(
                self.sound_select_frame,
                text="No sound files found in ./sounds folder",
                bg='#2d2d30',
                fg='#e74c3c',
                font=('Arial', 9)
            ).pack(anchor='w')
        
        # Test sound button
        test_sound_btn = tk.Button(
            self.sound_select_frame,
            text="🎵 Test Sound",
            command=self.test_sound,
            bg='#3498db',
            fg='white',
            font=('Arial', 9),
            relief='flat',
            padx=10,
            pady=2
        )
        test_sound_btn.pack(anchor='w', pady=5)
        
        # Discord notification section
        discord_frame = tk.LabelFrame(
            main_frame,
            text="Discord Notifications",
            bg='#2d2d30',
            fg='#ffffff',
            font=('Arial', 11, 'bold'),
            padx=10,
            pady=10
        )
        discord_frame.pack(fill='x', pady=10)
        
        # Discord enabled checkbox
        self.discord_var = tk.BooleanVar(value=notification_manager.discord_enabled)
        discord_check = tk.Checkbutton(
            discord_frame,
            text="💬 Enable Discord webhook notifications",
            variable=self.discord_var,
            bg='#2d2d30',
            fg='#ffffff',
            selectcolor='#8e44ad',
            font=('Arial', 10),
            command=self.toggle_discord_controls
        )
        discord_check.pack(anchor='w', pady=5)
        
        # Discord webhook URL frame
        self.discord_url_frame = tk.Frame(discord_frame, bg='#2d2d30')
        self.discord_url_frame.pack(fill='x', pady=5)
        
        tk.Label(
            self.discord_url_frame,
            text="Webhook URL:",
            bg='#2d2d30',
            fg='#cccccc',
            font=('Arial', 9)
        ).pack(anchor='w')
        
        self.webhook_entry = tk.Entry(
            self.discord_url_frame,
            bg='#1e1e1e',
            fg='#ffffff',
            font=('Consolas', 9),
            insertbackground='#ffffff',
            width=50
        )
        self.webhook_entry.pack(fill='x', pady=2)
        self.webhook_entry.insert(0, notification_manager.discord_webhook_url)
        
        # Discord info
        info_text = "ⓘ 30-second cooldown between Discord notifications\nMessage format: 'TextHunter has found the text \"[target]\"!'"
        tk.Label(
            discord_frame,
            text=info_text,
            bg='#2d2d30',
            fg='#95a5a6',
            font=('Arial', 8),
            justify='left'
        ).pack(anchor='w', pady=2)
        
        # Test Discord button
        test_discord_btn = tk.Button(
            self.discord_url_frame,
            text="📤 Test Discord",
            command=self.test_discord,
            bg='#5865F2',
            fg='white',
            font=('Arial', 9),
            relief='flat',
            padx=10,
            pady=2
        )
        test_discord_btn.pack(anchor='w', pady=5)
        
        # Timing settings section
        timing_frame = tk.LabelFrame(
            main_frame,
            text="Timing Settings",
            bg='#2d2d30',
            fg='#ffffff',
            font=('Arial', 11, 'bold'),
            padx=10,
            pady=10
        )
        timing_frame.pack(fill='x', pady=10)
        
        # Monitoring interval setting
        interval_frame = tk.Frame(timing_frame, bg='#2d2d30')
        interval_frame.pack(fill='x', pady=5)
        
        tk.Label(
            interval_frame,
            text="Monitoring Interval (seconds):",
            bg='#2d2d30',
            fg='#cccccc',
            font=('Arial', 10)
        ).pack(anchor='w')
        
        self.interval_var = tk.StringVar(value=str(notification_manager.monitoring_interval))
        interval_spinbox = tk.Spinbox(
            interval_frame,
            from_=1,
            to=60,
            textvariable=self.interval_var,
            bg='#1e1e1e',
            fg='#ffffff',
            font=('Arial', 10),
            insertbackground='#ffffff',
            width=10
        )
        interval_spinbox.pack(anchor='w', pady=2)
        
        tk.Label(
            interval_frame,
            text="ⓘ How often to check for target text (1-60 seconds)",
            bg='#2d2d30',
            fg='#95a5a6',
            font=('Arial', 8)
        ).pack(anchor='w', pady=2)
        
        # Discord cooldown setting
        cooldown_frame = tk.Frame(timing_frame, bg='#2d2d30')
        cooldown_frame.pack(fill='x', pady=5)
        
        tk.Label(
            cooldown_frame,
            text="Discord Cooldown (seconds):",
            bg='#2d2d30',
            fg='#cccccc',
            font=('Arial', 10)
        ).pack(anchor='w')
        
        self.cooldown_var = tk.StringVar(value=str(notification_manager.discord_cooldown))
        cooldown_spinbox = tk.Spinbox(
            cooldown_frame,
            from_=5,
            to=300,
            textvariable=self.cooldown_var,
            bg='#1e1e1e',
            fg='#ffffff',
            font=('Arial', 10),
            insertbackground='#ffffff',
            width=10
        )
        cooldown_spinbox.pack(anchor='w', pady=2)
        
        tk.Label(
            cooldown_frame,
            text="ⓘ Minimum time between Discord notifications (5-300 seconds)",
            bg='#2d2d30',
            fg='#95a5a6',
            font=('Arial', 8)
        ).pack(anchor='w', pady=2)
        
        # Status label
        self.status_label = tk.Label(
            root,
            text="",
            bg='#2d2d30',
            fg='#e74c3c',
            font=('Arial', 9),
            height=2
        )
        self.status_label.pack(pady=5)
        
        # Button frame
        button_frame = tk.Frame(root, bg='#2d2d30')
        button_frame.pack(side='bottom', fill='x', padx=20, pady=15)
        
        # Save button
        save_btn = tk.Button(
            button_frame,
            text="💾 Save Settings",
            command=lambda: self.save_settings(root),
            bg='#8e44ad',
            fg='white',
            font=('Arial', 11, 'bold'),
            padx=20,
            pady=8,
            relief='flat',
            activebackground='#9b59b6'
        )
        save_btn.pack(side='left', padx=(0, 8))
        
        # Cancel button
        cancel_btn = tk.Button(
            button_frame,
            text="❌ Cancel",
            command=root.destroy,
            bg='#5d6d7e',
            fg='white',
            font=('Arial', 11, 'bold'),
            padx=20,
            pady=8,
            relief='flat'
        )
        cancel_btn.pack(side='right')
        
        # Initialize control states
        self.toggle_sound_controls()
        self.toggle_discord_controls()
        
        root.mainloop()
        return self.result['saved']
    
    def toggle_sound_controls(self):
        """Enable/disable sound controls based on checkbox"""
        state = 'normal' if self.sound_var.get() else 'disabled'
        for widget in self.sound_select_frame.winfo_children():
            if hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except:
                    pass
    
    def toggle_discord_controls(self):
        """Enable/disable Discord controls based on checkbox"""
        state = 'normal' if self.discord_var.get() else 'disabled'
        for widget in self.discord_url_frame.winfo_children():
            if hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except:
                    pass
    
    def test_sound(self):
        """Test the selected sound"""
        if hasattr(self, 'sound_dropdown'):
            selected = self.sound_dropdown.get()
            if selected:
                # Temporarily set the sound and test it
                old_sound = notification_manager.selected_sound
                old_enabled = notification_manager.sound_enabled
                
                notification_manager.selected_sound = selected
                notification_manager.sound_enabled = True
                
                threading.Thread(target=notification_manager.play_selected_sound, daemon=True).start()
                self.status_label.config(text=f"Playing: {selected}", fg='#3498db')
                
                # Restore settings
                notification_manager.selected_sound = old_sound
                notification_manager.sound_enabled = old_enabled
            else:
                self.status_label.config(text="Please select a sound first", fg='#e74c3c')
    
    def test_discord(self):
        """Test Discord webhook"""
        webhook_url = self.webhook_entry.get().strip()
        if not webhook_url:
            self.status_label.config(text="Please enter a webhook URL first", fg='#e74c3c')
            return
        
        # Temporarily set webhook and test
        old_url = notification_manager.discord_webhook_url
        old_enabled = notification_manager.discord_enabled
        
        notification_manager.discord_webhook_url = webhook_url
        notification_manager.discord_enabled = True
        
        def test_notification():
            notification_manager.send_discord_notification("Test Message")
            
        threading.Thread(target=test_notification, daemon=True).start()
        self.status_label.config(text="Sending test Discord message...", fg='#3498db')
        
        # Restore settings
        notification_manager.discord_webhook_url = old_url
        notification_manager.discord_enabled = old_enabled
    
    def save_settings(self, root):
        """Save notification settings"""
        try:
            # Update notification manager settings
            notification_manager.sound_enabled = self.sound_var.get()
            notification_manager.discord_enabled = self.discord_var.get()
            
            if hasattr(self, 'sound_dropdown'):
                notification_manager.selected_sound = self.sound_dropdown.get()
            
            notification_manager.discord_webhook_url = self.webhook_entry.get().strip()
            
            # Update timing settings
            notification_manager.monitoring_interval = int(self.interval_var.get())
            notification_manager.discord_cooldown = int(self.cooldown_var.get())
            
            # Save to config file (extend existing config)
            config_path = get_config_file_path()
            config = {}
            
            # Load existing config
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except:
                    pass
            
            # Add notification settings
            config.update({
                'notification_settings': {
                    'sound_enabled': notification_manager.sound_enabled,
                    'discord_enabled': notification_manager.discord_enabled,
                    'selected_sound': notification_manager.selected_sound,
                    'discord_webhook_url': notification_manager.discord_webhook_url
                },
                'timing_settings': {
                    'monitoring_interval': notification_manager.monitoring_interval,
                    'discord_cooldown': notification_manager.discord_cooldown
                }
            })
            
            # Save updated config
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.status_label.config(text="✓ Settings saved successfully!", fg='#27ae60')
            self.result['saved'] = True
            
            root.after(1500, root.destroy)
            
        except Exception as e:
            self.status_label.config(text=f"Error saving: {str(e)}", fg='#e74c3c')

class TargetKeyManager:
    def __init__(self):
        self.target_keys = TARGET_KEYS.copy()
        
    def show_target_editor(self):
        """Show dialog to edit target keys"""
        # Create a regular Tk window instead of Toplevel for better reliability
        root = tk.Tk()
        root.title("TextHunter - Edit Target Words")
        root.geometry("550x500")  # Made taller to accommodate buttons
        root.minsize(500, 450)  # Increased minimum height
        root.resizable(True, True)
        root.configure(bg='#2d2d30')
        
        # Make it always on top
        root.attributes('-topmost', True)
        
        # Title
        title_label = tk.Label(
            root, 
            text="🎯 Configure Target Words", 
            bg='#2d2d30', 
            fg='#ffffff', 
            font=('Arial', 14, 'bold')
        )
        title_label.pack(pady=15)
        
        # Instructions
        instruction_label = tk.Label(
            root, 
            text="Words to monitor for (one per line):", 
            bg='#2d2d30', 
            fg='#cccccc', 
            font=('Arial', 11)
        )
        instruction_label.pack(pady=(0, 8))
        
        # Current targets display
        current_label = tk.Label(
            root, 
            text=f"Current targets: {', '.join(self.target_keys)}", 
            bg='#2d2d30', 
            fg='#999999', 
            font=('Arial', 9),
            wraplength=500
        )
        current_label.pack(pady=(0, 8))
        
        # Text area for target keys
        text_frame = tk.Frame(root, bg='#2d2d30')
        text_frame.pack(fill='both', expand=True, padx=25, pady=(15, 0))  # Remove bottom padding
        
        # Scrollbar for text area
        scrollbar = tk.Scrollbar(text_frame, bg='#3d3d40')
        scrollbar.pack(side='right', fill='y')
        
        # Text widget
        text_widget = tk.Text(
            text_frame, 
            yscrollcommand=scrollbar.set,
            bg='#1e1e1e',
            fg='#ffffff',
            font=('Consolas', 12),
            insertbackground='#ffffff',
            wrap='word',
            height=10,  # Reduced height to make room for buttons
            selectbackground='#8e44ad'
        )
        text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Fill with current target keys
        text_widget.delete('1.0', 'end')  # Clear first
        for key in self.target_keys:
            text_widget.insert('end', key + '\n')
        
        # Status label for feedback
        status_label = tk.Label(
            root, 
            text="", 
            bg='#2d2d30', 
            fg='#e74c3c', 
            font=('Arial', 10),
            height=2
        )
        status_label.pack(pady=(8, 0))
        
        # Buttons frame - ensure it's always visible at bottom
        button_frame = tk.Frame(root, bg='#2d2d30')
        button_frame.pack(side='bottom', fill='x', padx=25, pady=15)  # Use side='bottom' to pin to bottom
        
        result = {'saved': False, 'targets': []}
        
        def save_targets():
            try:
                content = text_widget.get('1.0', 'end-1c').strip()
                print(f"Raw content: '{content}'")
                
                new_targets = []
                for line in content.split('\n'):
                    cleaned_line = line.strip()
                    if cleaned_line:
                        new_targets.append(cleaned_line)
                
                print(f"Processed targets: {new_targets}")
                
                if not new_targets:
                    status_label.config(text="⚠ Please enter at least one target word.", fg='#e74c3c')
                    return
                
                # Update the targets globally
                self.target_keys = new_targets
                global TARGET_KEYS
                TARGET_KEYS = new_targets.copy()
                result['saved'] = True
                result['targets'] = new_targets.copy()
                
                # Save to config file
                if save_config(TARGET_KEYS):
                    status_label.config(text="✓ Targets saved successfully!", fg='#27ae60')
                    print(f"Successfully saved targets: {TARGET_KEYS}")
                else:
                    status_label.config(text="✓ Targets updated (config save failed)", fg='#f39c12')
                    print(f"Targets updated but config save failed: {TARGET_KEYS}")
                
                root.after(1500, root.destroy)
                
            except Exception as e:
                print(f"Error saving targets: {e}")
                status_label.config(text=f"❌ Error saving: {str(e)}", fg='#e74c3c')
        
        def cancel():
            print("Target editing cancelled")
            root.destroy()
        
        def reset_defaults():
            text_widget.delete('1.0', 'end')
            for key in DEFAULT_TARGET_KEYS:
                text_widget.insert('end', key + '\n')
            status_label.config(text="Reset to default targets", fg='#f39c3c')
        
        # Buttons with proper sizing and spacing
        save_btn = tk.Button(
            button_frame, 
            text="💾 Save", 
            command=save_targets,
            bg='#8e44ad', 
            fg='white', 
            font=('Arial', 11, 'bold'),
            padx=20,  # Reduced padding to fit better
            pady=8,
            relief='flat',
            activebackground='#9b59b6',
            cursor='hand2'
        )
        save_btn.pack(side='left', padx=(0, 8))
        
        reset_btn = tk.Button(
            button_frame, 
            text="🔄 Reset", 
            command=reset_defaults,
            bg='#7d3c98', 
            fg='white', 
            font=('Arial', 11, 'bold'),
            padx=20,
            pady=8,
            relief='flat',
            activebackground='#8e44ad',
            cursor='hand2'
        )
        reset_btn.pack(side='left', padx=8)
        
        cancel_btn = tk.Button(
            button_frame, 
            text="❌ Cancel", 
            command=cancel,
            bg='#5d6d7e', 
            fg='white', 
            font=('Arial', 11, 'bold'),
            padx=20,
            pady=8,
            relief='flat',
            activebackground='#6c7b7f',
            cursor='hand2'
        )
        cancel_btn.pack(side='right')
        
        root.mainloop()
        
        return result['saved']

class MonitorControlPanel:
    def __init__(self, region_info, monitor_type="region"):
        self.region_info = region_info
        self.monitor_type = monitor_type
        self.running = True
        self.root = None
        self.target_manager = TargetKeyManager()
        self.preview_window = None
        self.always_on_preview = None
        self.show_always_on = False
        
    def create_control_panel(self):
        """Create a small floating control panel"""
        self.root = tk.Tk()
        self.root.title("TextHunter")
        self.root.geometry("280x280")  # Made wider and adjusted height for 2x2 grid
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.95)
        self.root.configure(bg='#2d2d30')
        
        # Title
        title_label = tk.Label(
            self.root, 
            text="🔍 TextHunter", 
            bg='#2d2d30', 
            fg='#ffffff', 
            font=('Arial', 12, 'bold')
        )
        title_label.pack(pady=8)
        
        # Status indicator
        self.status_label = tk.Label(
            self.root, 
            text="● MONITORING", 
            bg='#2d2d30', 
            fg='#2ecc71', 
            font=('Arial', 10, 'bold')
        )
        self.status_label.pack(pady=4)
        
        # Target info (clickable to edit)
        self.update_target_display()
        
        # Buttons frame with 2x2 grid layout
        button_frame = tk.Frame(self.root, bg='#2d2d30')
        button_frame.pack(pady=12, padx=10, fill='x')
        
        # Configure grid weights for equal spacing
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_rowconfigure(0, weight=1)
        button_frame.grid_rowconfigure(1, weight=1)
        
        # Row 1: Edit Targets and Pause
        edit_btn = tk.Button(
            button_frame, 
            text="🎯 Edit Targets", 
            command=self.edit_targets,
            bg='#8e44ad', 
            fg='white', 
            font=('Arial', 9, 'bold'),
            padx=8,
            pady=6,
            relief='flat',
            activebackground='#9b59b6',
            width=12
        )
        edit_btn.grid(row=0, column=0, padx=4, pady=4, sticky='ew')
        
        # Pause/Resume button
        self.pause_btn = tk.Button(
            button_frame, 
            text="⏸ Pause", 
            command=self.toggle_pause,
            bg='#6c3483', 
            fg='white', 
            font=('Arial', 9, 'bold'),
            padx=8,
            pady=6,
            relief='flat',
            activebackground='#7d3c98',
            width=12
        )
        self.pause_btn.grid(row=0, column=1, padx=4, pady=4, sticky='ew')
        
        # Row 2: Show Preview and Settings
        self.preview_btn = tk.Button(
            button_frame, 
            text="👁 Show Preview", 
            command=self.toggle_always_on,
            bg='#5d6d7e', 
            fg='white', 
            font=('Arial', 9, 'bold'),
            padx=8,
            pady=6,
            relief='flat',
            activebackground='#6c7b7f',
            width=12
        )
        self.preview_btn.grid(row=1, column=0, padx=4, pady=4, sticky='ew')
        
        # Settings button
        settings_btn = tk.Button(
            button_frame, 
            text="⚙️ Settings", 
            command=self.open_settings,
            bg='#34495e', 
            fg='white', 
            font=('Arial', 9, 'bold'),
            padx=8,
            pady=6,
            relief='flat',
            activebackground='#5d6d7e',
            width=12
        )
        settings_btn.grid(row=1, column=1, padx=4, pady=4, sticky='ew')
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.stop_monitoring)
        
        return self.root
    
    def update_target_display(self):
        """Update the target display label"""
        # Remove old target label if it exists
        for widget in self.root.winfo_children():
            if hasattr(widget, 'target_label_id'):
                widget.destroy()
        
        targets_text = ", ".join(TARGET_KEYS[:2])  # Show first 2 targets
        if len(TARGET_KEYS) > 2:
            targets_text += f"... (+{len(TARGET_KEYS) - 2} more)"
            
        self.target_label = tk.Label(
            self.root, 
            text=f"Targets: {targets_text}", 
            bg='#2d2d30', 
            fg='#cccccc', 
            font=('Arial', 9),
            wraplength=220,
            cursor='hand2'  # Show it's clickable
        )
        self.target_label.target_label_id = True  # Mark for identification
        self.target_label.pack(pady=4)
        
        # Make it clickable
        self.target_label.bind("<Button-1>", lambda e: self.edit_targets())
    
    def edit_targets(self):
        """Open target editor dialog"""
        # Update the target manager with current targets before opening
        self.target_manager.target_keys = TARGET_KEYS.copy()
        
        if self.target_manager.show_target_editor():
            # Force update the target display with the new targets
            self.update_target_display()
            
            # Show a brief confirmation
            original_text = self.status_label.cget('text')
            original_color = self.status_label.cget('fg')
            
            self.status_label.config(text="● TARGETS UPDATED", fg='#9b59b6')
            self.root.after(2500, lambda: self.status_label.config(text=original_text, fg=original_color))
    
    def stop_monitoring(self):
        """Stop the monitoring process"""
        self.running = False
        if self.root:
            self.root.quit()
            self.root.destroy()
    
    def toggle_pause(self):
        """Toggle pause/resume monitoring"""
        if hasattr(self, 'paused') and self.paused:
            self.paused = False
            self.pause_btn.config(text="⏸ Pause", bg='#6c3483')
            self.status_label.config(text="● MONITORING", fg='#2ecc71')
        else:
            self.paused = True
            self.pause_btn.config(text="▶ Resume", bg='#27ae60')
            self.status_label.config(text="⏸ PAUSED", fg='#f39c12')
    
    def update_status(self, message, color='#2ecc71'):
        """Update the status label"""
        if self.root and self.status_label.winfo_exists():
            self.status_label.config(text=f"● {message}", fg=color)
            self.root.update_idletasks()
    
    def is_running(self):
        """Check if monitoring should continue"""
        if self.root:
            try:
                self.root.update_idletasks()
                return self.running
            except tk.TclError:
                return False
        return self.running
    
    def is_paused(self):
        """Check if monitoring is paused"""
        return hasattr(self, 'paused') and self.paused

    def toggle_preview(self):
        """Toggle the preview window"""
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()
            self.preview_window = None
        else:
            self.create_preview_window()

    def create_preview_window(self):
        """Create a preview window showing the monitored region"""
        self.preview_window = tk.Toplevel(self.root)
        self.preview_window.title("Preview - Monitored Region")
        self.preview_window.geometry("320x240")
        self.preview_window.configure(bg='#2d2d30')
        self.preview_window.attributes('-topmost', True)
        self.preview_window.attributes('-alpha', 0.95)
        
        # Position the preview window to the right of the control panel
        if self.root:
            x = self.root.winfo_x() + self.root.winfo_width() + 10
            y = self.root.winfo_y()
            self.preview_window.geometry(f"320x240+{x}+{y}")
        
        # Title label
        title_label = tk.Label(
            self.preview_window,
            text="🔍 Live Preview",
            bg='#2d2d30',
            fg='#ffffff',
            font=('Arial', 10, 'bold')
        )
        title_label.pack(pady=5)
        
        # Image label for preview
        self.preview_image_label = tk.Label(
            self.preview_window,
            bg='#1e1e1e',
            text="Capturing preview...",
            fg='#ffffff'
        )
        self.preview_image_label.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Start updating preview
        self.update_preview()

    def toggle_always_on(self):
        """Toggle the always-on preview"""
        self.show_always_on = not self.show_always_on
        if self.show_always_on:
            self.preview_btn.config(text="👁 Show Preview", bg='#3498db')
            self.create_always_on_preview()
        else:
            self.preview_btn.config(text="👁 Show Preview", bg='#5d6d7e')
            if self.always_on_preview and self.always_on_preview.winfo_exists():
                self.always_on_preview.destroy()
                self.always_on_preview = None

    def create_always_on_preview(self):
        """Create an always-on preview window attached to the control panel"""
        if self.always_on_preview and self.always_on_preview.winfo_exists():
            self.always_on_preview.destroy()
            
        self.always_on_preview = tk.Toplevel(self.root)
        self.always_on_preview.title("Always On Preview")
        self.always_on_preview.geometry("200x150")
        self.always_on_preview.configure(bg='#1e1e1e')
        self.always_on_preview.attributes('-topmost', True)
        self.always_on_preview.attributes('-alpha', 0.9)
        self.always_on_preview.overrideredirect(True)  # No title bar
        
        # Position attached to the left side of the control panel
        if self.root:
            control_x = self.root.winfo_x()
            control_y = self.root.winfo_y()
            # Attach to the left side of the control panel
            attach_x = control_x - 210  # 200 width + 10 padding
            attach_y = control_y
            self.always_on_preview.geometry(f"200x150+{attach_x}+{attach_y}")
        
        # Image label for always-on preview
        self.always_on_image_label = tk.Label(
            self.always_on_preview,
            bg='#1e1e1e',
            text="Capturing...",
            fg='#ffffff',
            font=('Arial', 8)
        )
        self.always_on_image_label.pack(fill='both', expand=True)
        
        # Add a border to make it clear it belongs to the control panel
        border_frame = tk.Frame(
            self.always_on_preview,
            bg='#8e44ad',
            height=3
        )
        border_frame.pack(side='bottom', fill='x')
        
        # Bind the always-on preview to follow the main window
        self.root.bind('<Configure>', self.update_always_on_position)
        
        # Start updating always-on preview
        self.update_always_on_preview()

    def update_always_on_position(self, event=None):
        """Update the position of the always-on preview when the main window moves"""
        if self.always_on_preview and self.always_on_preview.winfo_exists() and self.show_always_on:
            try:
                control_x = self.root.winfo_x()
                control_y = self.root.winfo_y()
                # Keep it attached to the left side
                attach_x = control_x - 210
                attach_y = control_y
                self.always_on_preview.geometry(f"200x150+{attach_x}+{attach_y}")
            except:
                pass  # Ignore errors during window destruction

    def capture_current_region(self):
        """Capture the current monitored region"""
        try:
            import mss
            
            if self.monitor_type == "window_region" and self.region_info:
                # Get current window position
                window_info = self.region_info.get('window', {})
                if hasattr(window_info, 'get'):
                    window_title = window_info.get('title', '')
                    current_windows = gw.getWindowsWithTitle(window_title)
                    if current_windows:
                        current_window = current_windows[0]
                        if current_window.visible:
                            # Calculate absolute region coordinates
                            absolute_region = {
                                "left": current_window.left + self.region_info.get('relative_left', 0),
                                "top": current_window.top + self.region_info.get('relative_top', 0),
                                "width": self.region_info.get('width', 200),
                                "height": self.region_info.get('height', 200)
                            }
                            
                            with mss.mss() as sct:
                                img = sct.grab(absolute_region)
                                pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                                return pil_img
                                
            elif self.monitor_type == "full_window" and self.region_info:
                # Full window monitoring
                window_title = self.region_info.get('title', '')
                current_windows = gw.getWindowsWithTitle(window_title)
                if current_windows:
                    current_window = current_windows[0]
                    if current_window.visible:
                        region = {
                            "left": current_window.left,
                            "top": current_window.top,
                            "width": current_window.width,
                            "height": current_window.height
                        }
                        
                        with mss.mss() as sct:
                            img = sct.grab(region)
                            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                            return pil_img
                            
            elif self.monitor_type == "screen_region" and self.region_info:
                # Screen region monitoring
                with mss.mss() as sct:
                    img = sct.grab(self.region_info)
                    pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                    return pil_img
                    
        except Exception as e:
            print(f"Error capturing region: {e}")
            
        return None

    def update_preview(self):
        """Update the preview window with current region capture"""
        if not (self.preview_window and self.preview_window.winfo_exists()):
            return
            
        try:
            pil_img = self.capture_current_region()
            if pil_img:
                # Resize image to fit preview window
                pil_img.thumbnail((300, 200), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(pil_img)
                
                # Update label
                self.preview_image_label.config(image=photo, text="")
                self.preview_image_label.image = photo  # Keep a reference
            else:
                self.preview_image_label.config(image="", text="No capture available")
                
        except Exception as e:
            self.preview_image_label.config(image="", text=f"Error: {str(e)[:30]}")
        
        # Schedule next update
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.after(1000, self.update_preview)  # Update every second

    def update_always_on_preview(self):
        """Update the always-on preview with current region capture"""
        if not (self.always_on_preview and self.always_on_preview.winfo_exists()):
            return
            
        try:
            pil_img = self.capture_current_region()
            if pil_img:
                # Resize image to fit always-on window
                pil_img.thumbnail((180, 130), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(pil_img)
                
                # Update label
                self.always_on_image_label.config(image=photo, text="")
                self.always_on_image_label.image = photo  # Keep a reference
            else:
                self.always_on_image_label.config(image="", text="No capture")
                
        except Exception as e:
            self.always_on_image_label.config(image="", text="Error")
        
        # Schedule next update
        if self.show_always_on and self.always_on_preview and self.always_on_preview.winfo_exists():
            self.always_on_preview.after(1000, self.update_always_on_preview)  # Update every second

    def open_settings(self):
        """Open notification settings dialog"""
        settings_dialog = NotificationSettingsDialog(self.root)
        if settings_dialog.show_settings():
            # Show a brief confirmation only if the window still exists
            try:
                if self.root and self.status_label.winfo_exists():
                    original_text = self.status_label.cget('text')
                    original_color = self.status_label.cget('fg')
                    
                    self.status_label.config(text="● SETTINGS UPDATED", fg='#3498db')
                    self.root.after(2500, lambda: self.safe_restore_status(original_text, original_color))
            except (tk.TclError, AttributeError):
                # Window was destroyed, ignore
                pass
    
    def safe_restore_status(self, original_text, original_color):
        """Safely restore status label text"""
        try:
            if self.root and self.status_label.winfo_exists():
                self.status_label.config(text=original_text, fg=original_color)
        except (tk.TclError, AttributeError):
            # Window was destroyed, ignore
            pass

class WindowSelector:
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
        
        # Create selection window
        root = tk.Tk()
        root.title("Select Window to Monitor")
        root.geometry("600x450")
        root.resizable(True, True)
        
        # Instructions
        instruction_label = tk.Label(
            root, 
            text="Step 1: Select a window, then choose monitoring mode:",
            font=('Arial', 12, 'bold'),
            pady=10
        )
        instruction_label.pack()
        
        # Create listbox with scrollbar
        frame = tk.Frame(root)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side='right', fill='y')
        
        listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set, font=('Consolas', 10))
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Add windows to listbox
        for i, window in enumerate(windows):
            try:
                title = window['title'][:80] + "..." if len(window['title']) > 80 else window['title']
                listbox.insert(tk.END, f"{i+1}. {title}")
            except:
                listbox.insert(tk.END, f"{i+1}. <Unknown Window>")
        
        # Mode selection frame
        mode_frame = tk.LabelFrame(root, text="Step 2: Choose Monitoring Mode", font=('Arial', 10, 'bold'))
        mode_frame.pack(fill='x', padx=10, pady=5)
        
        # Button frame
        button_frame = tk.Frame(mode_frame)
        button_frame.pack(pady=10)
        
        selected_window = None
        selected_mode = None
        
        def on_window_region():
            nonlocal selected_window, selected_mode
            selection = listbox.curselection()
            if selection:
                selected_window = windows[selection[0]]
                selected_mode = "WINDOW_REGION"
                root.quit()
                root.destroy()
            else:
                messagebox.showwarning("No Selection", "Please select a window first")
        
        def on_full_window():
            nonlocal selected_window, selected_mode
            selection = listbox.curselection()
            if selection:
                selected_window = windows[selection[0]]
                selected_mode = "FULL_WINDOW"
                root.quit()
                root.destroy()
            else:
                messagebox.showwarning("No Selection", "Please select a window first")
        
        def on_screen_region():
            nonlocal selected_mode
            selected_mode = "SCREEN_REGION"
            root.quit()
            root.destroy()
        
        def on_cancel():
            root.quit()
            root.destroy()
        
        # Monitoring mode buttons
        window_region_btn = tk.Button(
            button_frame, 
            text="Monitor Region\nINSIDE Window", 
            command=on_window_region, 
            bg='green', 
            fg='white', 
            padx=15, 
            pady=5,
            font=('Arial', 9, 'bold')
        )
        window_region_btn.pack(side='left', padx=5)
        
        full_window_btn = tk.Button(
            button_frame, 
            text="Monitor Entire\nWindow", 
            command=on_full_window, 
            bg='orange', 
            fg='white', 
            padx=15, 
            pady=5,
            font=('Arial', 9, 'bold')
        )
        full_window_btn.pack(side='left', padx=5)
        
        screen_region_btn = tk.Button(
            button_frame, 
            text="Monitor Screen\nRegion Instead", 
            command=on_screen_region, 
            bg='blue', 
            fg='white', 
            padx=15, 
            pady=5,
            font=('Arial', 9, 'bold')
        )
        screen_region_btn.pack(side='left', padx=5)
        
        cancel_btn = tk.Button(
            button_frame, 
            text="Cancel", 
            command=on_cancel, 
            padx=15, 
            pady=5
        )
        cancel_btn.pack(side='left', padx=5)
        
        root.mainloop()
        
        if selected_mode == "WINDOW_REGION":
            return {"mode": "window_region", "window": selected_window}
        elif selected_mode == "FULL_WINDOW":
            return {"mode": "full_window", "window": selected_window}
        elif selected_mode == "SCREEN_REGION":
            return {"mode": "screen_region"}
        else:
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

def monitor_window_region(region_info):
    """Monitor a specific region within a window with UI control panel"""
    window_info = region_info['window']
    relative_left = region_info['relative_left']
    relative_top = region_info['relative_top']
    region_width = region_info['width']
    region_height = region_info['height']
    
    print(f"\nMonitoring region within window: {window_info['title']}")
    print(f"Region: ({relative_left}, {relative_top}) {region_width}x{region_height}")
    print("Region will follow the window wherever it moves!")
    
    # Create control panel
    control_panel = MonitorControlPanel(region_info, "window_region")
    panel_root = control_panel.create_control_panel()
    
    def monitoring_loop():
        """Main monitoring loop running in separate thread"""
        try:
            with mss.mss() as sct:
                while control_panel.is_running():
                    if control_panel.is_paused():
                        time.sleep(0.5)  # Check pause state more frequently
                        continue
                        
                    try:
                        current_windows = gw.getWindowsWithTitle(window_info['title'])
                        if not current_windows:
                            control_panel.update_status("Window not found", '#e74c3c')
                            time.sleep(notification_manager.monitoring_interval)
                            continue
                            
                        current_window = current_windows[0]
                        
                        if not current_window.visible:
                            control_panel.update_status("Window not visible", '#f39c12')
                            time.sleep(notification_manager.monitoring_interval)
                            continue
                        
                        control_panel.update_status("MONITORING", '#2ecc71')
                        
                        # Calculate absolute region coordinates
                        absolute_region = {
                            "left": current_window.left + relative_left,
                            "top": current_window.top + relative_top,
                            "width": region_width,
                            "height": region_height
                        }
                        
                        # Capture the region
                        img = sct.grab(absolute_region)
                        pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                        # Save debug
                        pil_img.save(DEBUG_IMG)

                        # OCR
                        text = pytesseract.image_to_string(pil_img).strip()
                        print(text)
                        # Alert
                        found_targets = []
                        for target in TARGET_KEYS:
                            if target.lower() in text.lower():
                                found_targets.append(target)
                        
                        if found_targets:
                            control_panel.update_status(f"FOUND: {', '.join(found_targets)}", '#e74c3c')
                            notification_manager.notify(found_targets)
                            time.sleep(2)  # Show the found message briefly
                            
                    except Exception as e:
                        control_panel.update_status(f"Error: {str(e)[:20]}...", '#e74c3c')

                    time.sleep(notification_manager.monitoring_interval)
                    
        except Exception as e:
            print(f"Monitoring error: {e}")
        finally:
            print("Monitoring stopped.")

    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Run the UI (blocking)
    panel_root.mainloop()

def monitor_window(window_info):
    """Monitor an entire window with UI control panel"""
    print(f"\nMonitoring window: {window_info['title']}")
    
    # Create control panel
    control_panel = MonitorControlPanel(window_info, "full_window")
    panel_root = control_panel.create_control_panel()
    
    monitor = WindowMonitor(window_info)
    
    def monitoring_loop():
        """Main monitoring loop running in separate thread"""
        try:
            with mss.mss() as sct:
                while control_panel.is_running():
                    if control_panel.is_paused():
                        time.sleep(0.5)
                        continue
                        
                    try:
                        region = monitor.get_window_region()
                        
                        if region and region['width'] > 0 and region['height'] > 0:
                            control_panel.update_status("MONITORING", '#2ecc71')
                            
                            img = sct.grab(region)
                            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                            pil_img.save(DEBUG_IMG)

                            text = pytesseract.image_to_string(pil_img).strip()

                            found_targets = []
                            for target in TARGET_KEYS:
                                if target.lower() in text.lower():
                                    found_targets.append(target)
                            
                            if found_targets:
                                control_panel.update_status(f"FOUND: {', '.join(found_targets)}", '#e74c3c')
                                notification_manager.notify(found_targets)
                                time.sleep(2)
                        else:
                            control_panel.update_status("Window not visible", '#f39c12')
                            
                    except Exception as e:
                        control_panel.update_status(f"Error: {str(e)[:20]}...", '#e74c3c')

                    time.sleep(notification_manager.monitoring_interval)
                    
        except Exception as e:
            print(f"Monitoring error: {e}")
        finally:
            print("Monitoring stopped.")

    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Run the UI (blocking)
    panel_root.mainloop()

def monitor_region(region):
    """Monitor a selected region with UI control panel"""
    print(f"\nMonitoring region: {region}")
    print(f"Size: {region['width']}x{region['height']}")
    
    # Create control panel
    control_panel = MonitorControlPanel(region, "screen_region")
    panel_root = control_panel.create_control_panel()
    
    def monitoring_loop():
        """Main monitoring loop running in separate thread"""
        try:
            with mss.mss() as sct:
                while control_panel.is_running():
                    if control_panel.is_paused():
                        time.sleep(0.5)
                        continue
                        
                    try:
                        control_panel.update_status("MONITORING", '#2ecc71')
                        
                        img = sct.grab(region)
                        pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                        pil_img.save(DEBUG_IMG)

                        text = pytesseract.image_to_string(pil_img).strip()

                        found_targets = []
                        for target in TARGET_KEYS:
                            if target.lower() in text.lower():
                                found_targets.append(target)
                        
                        if found_targets:
                            control_panel.update_status(f"FOUND: {', '.join(found_targets)}", '#e74c3c')
                            notification_manager.notify(found_targets)
                            time.sleep(2)
                            
                    except Exception as e:
                        control_panel.update_status(f"Error: {str(e)[:20]}...", '#e74c3c')

                    time.sleep(notification_manager.monitoring_interval)
                    
        except Exception as e:
            print(f"Monitoring error: {e}")
        finally:
            print("Monitoring stopped.")

    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Run the UI (blocking)
    panel_root.mainloop()

def main():
    print("TextHunter - Advanced Text Monitoring Tool")
    print("=" * 50)
    
    # Select window or region
    window_selector = WindowSelector()
    selected = window_selector.select_window()
    
    if selected:
        if selected['mode'] == "screen_region":
            # Select region
            selector = RegionSelector()
            region = selector.select_region()
            
            if region:
                # Start monitoring region
                monitor_region(region)
            else:
                print("No region selected. Exiting.")
        elif selected['mode'] == "full_window":
            # Start monitoring window
            monitor_window(selected['window'])
        elif selected['mode'] == "window_region":
            # Select region within window
            region_selector = WindowRegionSelector(selected['window'])
            region_info = region_selector.select_region_in_window()
            
            if region_info:
                # Start monitoring window region
                monitor_window_region(region_info)
            else:
                print("No region selected within window. Exiting.")
    else:
        print("No selection made. Exiting.")

if __name__ == "__main__":
    main()
