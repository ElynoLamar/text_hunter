# 🔍 TextHunter - Advanced Text Monitoring Tool

**TextHunter** is a powerful screen monitoring application that detects specific text patterns in real-time and alerts you when they appear. Originally designed for game monitoring, it's versatile enough for any text detection task across your screen.

## ✨ Features

- 🎯 **Multi-target monitoring** - Track multiple text patterns simultaneously
- 🖼️ **Flexible capture modes** - Monitor entire windows, specific regions, or screen areas
- 🔄 **Real-time tracking** - Follows moving windows automatically
- 🎮 **Gaming-friendly** - Works with games and applications in fullscreen
- 🔊 **Audio alerts** - Plays sound notifications when targets are found
- ⏸️ **Pause/Resume** - Control monitoring without losing your setup
- 🎨 **Modern UI** - Dark theme with purple accents
- 🔧 **Easy configuration** - Edit target words through intuitive interface

---

## 🚀 Quick Start

### 1. Download & Run
1. Download `TextHunter.exe` from the releases
2. Place `alert.mp3` in the same folder as the executable
3. Double-click `TextHunter.exe` to start

### 2. Basic Setup
1. **Select Monitoring Mode:**
   - **Monitor Region INSIDE Window** - Select a specific area within a window
   - **Monitor Entire Window** - Monitor the complete window content
   - **Monitor Screen Region** - Monitor a fixed screen area

2. **Choose Your Target Window** (for window modes)
3. **Select the Region** (if using region mode)
4. **Start Monitoring!**

---

## 🎮 How to Use the Interface

### Main Window Selection
![Window Selection](docs/window-selection.png)

1. **Window List** - Shows all available windows
2. **Monitoring Modes:**
   - 🟢 **Region INSIDE Window** - Best for specific UI elements (chat boxes, notifications)
   - 🟠 **Entire Window** - Monitor everything in the window
   - 🔵 **Screen Region** - Fixed area regardless of windows

### Region Selection (Blue Overlay)
When selecting a region inside a window:
- **Blue overlay** appears over your chosen window
- **Click and drag** to select the area you want to monitor
- **Red rectangle** shows your selection in real-time
- **ESC** to cancel selection

### Control Panel
The floating control panel appears near your monitored region:

```
🔍 TextHunter
● MONITORING
Targets: Griffon Egg, King of Greed...
🎯 Edit Targets
⏹ Stop    ⏸ Pause
```

**Status Indicators:**
- 🟢 **● MONITORING** - Actively scanning for targets
- 🟡 **⏸ PAUSED** - Monitoring paused
- 🔴 **● FOUND: [target]** - Target detected!
- 🟠 **Window not visible** - Target window is minimized/hidden

**Controls:**
- **🎯 Edit Targets** - Add, remove, or modify target words
- **⏹ Stop** - End monitoring session
- **⏸ Pause / ▶ Resume** - Temporarily pause/resume monitoring

---

## 🎯 Managing Target Words

### Adding New Targets
1. Click **🎯 Edit Targets** in the control panel
2. Type each target word on a separate line:
   ```
   Griffon Egg
   King of Greed
   Rare Item Found
   Quest Complete
   ```
3. Click **💾 Save**

### Target Examples
- **Game Items:** `Legendary Drop`, `Rare Material`, `Quest Reward`
- **Chat Monitoring:** `Your Name`, `Guild Message`, `Trade Offer`
- **System Messages:** `Error`, `Warning`, `Success`
- **Business Apps:** `New Email`, `Meeting Started`, `Task Complete`

### Tips for Better Detection
- Use **exact text** as it appears on screen
- **Case doesn't matter** - "RARE ITEM" matches "rare item"
- **Partial matches work** - "Griffon" will match "Griffon Egg Found!"
- **Avoid special characters** unless necessary

---

## 🔧 Advanced Configuration

### File Structure
```
📁 TextHunter/
├── TextHunter.exe        # Main application
├── sounds/               # Sound files for alerts
│   └── level_up.mp3     # Default alert sound
└── texthunter_config.json  # Auto-generated config
```

### Custom Alert Sound
Replace `alert.mp3` with your own sound file:
1. Convert your audio to MP3 format
2. Name it `alert.mp3`
3. Place in the same folder as `TextHunter.exe`

### Troubleshooting
- **Check `debug.png`** - Shows exactly what TextHunter is monitoring
- **Console output** - Run from command line to see detailed logs
- **Test with simple text** - Start with easy-to-detect words

---

## 🛠️ Development & Updates

### Building from Source
```bash
# Install dependencies
pip install -r requirements.txt

# Run from source
python text_hunter.py

# Build executable
pyinstaller --onefile --windowed --name "TextHunter" text_hunter.py
```

### Updating the Application

#### Method 1: Download New Release
1. Download the latest `TextHunter.exe`
2. Replace the old executable
3. Keep your existing `alert.mp3` file

#### Method 2: Build from Source
```bash
# Pull latest changes
git pull origin main

# Rebuild executable
pyinstaller --onefile --windowed --name "TextHunter" text_hunter.py

# New executable in dist/TextHunter.exe
```

### File Locations
- **Source Code:** `text_hunter.py`
- **Dependencies:** `requirements.txt`
- **Output:** `dist/TextHunter.exe`

---

## 📝 System Requirements

- **OS:** Windows 10/11 (64-bit)
- **RAM:** 50MB minimum
- **Storage:** 20MB for application + space for screenshots
- **Dependencies:** None (all bundled in executable)

### Optional Components
- **Tesseract OCR:** Pre-configured for text recognition
- **Audio System:** For alert sound playback

---

## 🐛 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| No sound alerts | Ensure `alert.mp3` is in the same folder |
| Text not detected | Check `debug.png` to verify capture area |
| Window not found | Restart TextHunter and reselect the window |
| High CPU usage | Increase monitoring interval (default: 5 seconds) |
| Antivirus blocks exe | Add TextHunter to antivirus whitelist |

### Debug Information
- **Screenshot:** `debug.png` shows the monitored area
- **Console output:** Run `TextHunter.exe` from command prompt for detailed logs
- **Test mode:** Use simple, clearly visible text for testing

### Getting Help
1. Check the `debug.png` file to see what's being captured
2. Run from command line to see error messages
3. Verify your target words appear exactly as typed in the monitored area

---

## 📜 License & Disclaimer

This software is provided "as-is" without warranty. Use responsibly and in accordance with the terms of service of applications you're monitoring.

**TextHunter** respects user privacy:
- No data is transmitted over the internet
- All processing happens locally on your machine
- Screenshots are only saved locally for debugging

---

## 🚀 Version History

- **v2.0** - Rebranded to TextHunter, improved UI, digital signing
- **v1.5** - Added pause/resume, better window tracking
- **v1.0** - Initial release as GriffonMonitor

---

**Made with ❤️ by StrataG Software**