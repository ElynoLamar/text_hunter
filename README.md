# 🔍 TextHunter

TextHunter is a Windows desktop screen-monitoring utility that uses OCR (Tesseract) to watch selected screen/window regions, detect keywords, and trigger alerts in real time.

It supports multiple independent monitoring regions, per-region rules, sound notification (MP3/WAV/OGG), Discord webhook notifications, and live preview with OCR text output.

---

## 🚀 What’s New in This Version
- Multi-region architecture with independent monitor rules and intervals
- Window or screen region capture modes (screen region, full window, window subregion)
- Per-region detection rule sets (keywords, sound, volume, Discord, cooldown)
- Preview window showing the last capture frame + OCR text
- Rule-based matching with partial/case-insensitive matching
- Support for both `pygame` audio (preferred) and fallback `playsound`
- Single-instance prevention (lock file)
- JSON config persistence via `texthunter_config.json`

---

## 🧩 Dependencies
- Python 3.10+ (recommended)
- Tesseract OCR installed and accessible (default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- requirements from `requirements.txt`:
  - mss, Pillow, pytesseract, playsound, pygetwindow, requests, pygame, psutil

---

## ▶️ Quick Start
### Run from source
1. Install Python dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Ensure Tesseract is installed and working:
   ```powershell
   tesseract --version
   ```
3. Launch TextHunter:
   ```powershell
   python text_hunter.py
   ```

### Run as executable
1. Build or download `TextHunter.exe`.
2. Copy `sounds/` folder next to the exe.
3. Run the executable directly.

---

## 🖥️ Capture Modes
- `Screen Region` – select an arbitrary area on screen (multi-monitor support via mss)
- `Full Window` – track the bounding rectangle of a chosen window
- `Window Region` – track a sub-region inside a chosen window

Region data is saved to `texthunter_config.json`, so your setup persists across restarts.

---

## 🎯 Detection Rules
Each monitored region has an array of detection rules. Rules contain:
- `name`
- `keywords` (one per line)
- `sound_enabled` + `sound_file` + `volume`
- `discord_enabled` + `discord_webhook_url` + `discord_cooldown`

Matching is case-insensitive and supports substring matching (`Griffon` matches `Griffon Egg`).

---

## 🔔 Alerts
- Audio play from the `sounds` folder. Default sound is `level_up.mp3`.
- Discord notifications via webhook (per-rule cooldown to avoid spam).
- GUI status indicator (stopped/running/paused; found state updates).

---

## 🛠️ Main UI Controls
- Add Region
- Start All / Stop All
- Save Config
- Per-region Start/Pause/Resume/Stop
- Per-region Settings (name, interval, capture type, rules, Discord)
- Preview (live capture + OCR text)
- Test alert button

---

## ⚙️ Configuration
File: `texthunter_config.json` (auto-created).
Structure: top-level `regions` with each region containing: `id`, `name`, `region_type`, `region_data`, `monitoring_interval`, `detection_rules`.

### Example region stored by app
```json
{
  "id": "abcd1234",
  "name": "Game Chat",
  "region_type": "window_region",
  "region_data": { "window_title": "MyGame", "relative_left": 50, "relative_top": 300, "width": 600, "height": 140 },
  "monitoring_interval": 5,
  "detection_rules": [ ... ]
}
```

---

## 🐛 Troubleshooting
- If no text is found, open Preview and verify OCR text (`No text detected` means capture region or OCR failed).
- Run `python text_hunter.py` from console for log output.
- Ensure monitored windows are not minimized and have non-zero size.
- For sound: check `sounds/` contains a valid `.mp3/.wav/.ogg` file.
- Discord errors are printed in console; verify webhook is valid and not rate-limited.

---

## 🏗️ Build Release Binary
```powershell
pyinstaller --onefile --windowed --name "TextHunter" text_hunter.py
```
Output exe in `dist/TextHunter.exe`.

---

## 📜 License
Use this repository code as-is. No warranty. All OCR and capture is local to your machine.

## ♻️ Notes
- New regions are only valid after pressing `Save Config` in UI or on exit.
- Single-instance guard uses `texthunter.lock` in temp folder.
- If you want custom Tesseract path, edit `pytesseract.pytesseract.tesseract_cmd` in the script.
