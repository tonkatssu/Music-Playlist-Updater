# 🎵 YouTube Music Playlist Manager

## First-time setup (2 minutes)

**1. Make sure Python is installed**
Open PowerShell and run:
```
python --version
```
If you get an error, download Python from https://python.org (check "Add to PATH" during install).

---

**2. Put these files in a permanent folder**
Move the entire `youtube_music_manager` folder somewhere you won't accidentally delete it,
e.g. `C:\Users\YourName\Documents\youtube_music_manager`

---

**3. Run the manager**
Double-click **`Start Manager.bat`**

On first launch it will:
- Install `ytmusicapi` automatically
- Walk you through a one-time YouTube Music login (copy/paste browser headers — instructions shown on screen)
- Find or create your "Now" and "Washed Up" playlists
- Start watching your listening history

---

## Day-to-day use

Just double-click **`Start Manager.bat`** whenever your PC is on.
Leave the window in the background while you listen on any device (iPhone, PC, etc.)

---

## Optional: Run automatically on PC startup

1. Press `Win + R`, type `shell:startup`, press Enter
2. Copy a **shortcut** to `Start Manager.bat` into that folder
3. Done — it'll launch silently every time Windows starts

---

## Files created by the manager

| File | What it is |
|---|---|
| `headers_auth.json` | Your YouTube Music login (keep this safe) |
| `playlist_state.json` | Tracks miss counts, play history, etc. |

---

## How skip detection works

The manager polls your YouTube Music play history every 30 minutes.
It compares each snapshot to the previous one to see what was actually played.

- A song from "Now" appears in new plays → **heard**, miss streak resets
- Music was played but this song wasn't → **miss +1**
- No music played at all → **no penalty** (you weren't listening)
- After **15 consecutive misses** (~7.5 hours of active ignoring) → moved to **Washed Up**

New songs are added from your YouTube Music home feed and radio seeds
based on your most-played tracks.
