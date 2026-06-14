"""
YouTube Music Playlist Manager
================================
Keeps your "Now" playlist fresh automatically.

  - Tracks songs you keep ignoring (15 missed polls → moved to "Washed Up")
  - Adds new recommended songs each cycle

Run:   python manager.py
Stop:  Ctrl+C
"""

import json
import os
import sys
import time
from datetime import datetime, timezone


# ============================================================
# SETTINGS  ← edit these to your preference
# ============================================================

NOW_PLAYLIST_NAME        = "Now"
WASHED_UP_PLAYLIST_NAME  = "Washed Up"
TARGET_PLAYLIST_SIZE     = 30   # songs to maintain in "Now"
SKIP_THRESHOLD           = 15   # missed polls in a row → Washed Up
POLL_INTERVAL_MINUTES    = 30   # how often to check (minutes)
SONGS_TO_ADD_PER_CYCLE   = 3    # fresh songs added each cycle

# ============================================================
# CONSTANTS  (don't change these)
# ============================================================

AUTH_FILE  = "headers_auth.json"
STATE_FILE = "playlist_state.json"


# ============================================================
# SETUP  (runs automatically on first launch)
# ============================================================

def run_setup():
    """One-time authentication setup."""
    print("=" * 60)
    print("  FIRST-TIME SETUP")
    print("=" * 60)
    print("""
To connect to your YouTube Music account:

  1. Open YouTube Music in Chrome or Firefox
     https://music.youtube.com

  2. Press F12 to open DevTools → click the Network tab

  3. Click on any song to play it

  4. Find any request to music.youtube.com (e.g. 'watchtime')

  5. Click it → Headers panel → scroll to Request Headers

  6. Select ALL the headers text and copy it

  7. Paste everything below, then press Enter, Ctrl-Z, Enter to finish
""")
    from ytmusicapi import setup
    from ytmusicapi.helpers import get_authorization, sapisid_from_cookie
    setup(filepath=AUTH_FILE)

    # ytmusicapi needs 'authorization' present in the file to detect
    # browser auth type. It regenerates the actual value on every
    # request from your cookies, so we just need the field to exist.
    with open(AUTH_FILE, encoding="utf-8") as f:
        headers = json.load(f)
    if "authorization" not in headers:
        try:
            sapisid = sapisid_from_cookie(headers["cookie"])
            origin  = headers.get("origin", headers.get("x-origin", "https://music.youtube.com"))
            headers["authorization"] = get_authorization(sapisid + " " + origin)
            with open(AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(headers, f, indent=4, sort_keys=True)
        except Exception as e:
            print(f"  \u26a0\ufe0f  Could not generate authorization header: {e}")

    print(f"\n\u2705  Saved to {AUTH_FILE} — don't delete this file!\n")


def ensure_authenticated():
    """Check for auth file; run setup if missing."""
    if not os.path.exists(AUTH_FILE):
        print(f"\n⚠️  No auth file found ({AUTH_FILE}).")
        print("Running first-time setup...\n")
        run_setup()


def ensure_dependencies():
    """Install ytmusicapi if not present."""
    try:
        import ytmusicapi  # noqa: F401
    except ImportError:
        print("📦 Installing ytmusicapi...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ytmusicapi", "-q"])
        print("✅ Installed!\n")


# ============================================================
# STATE
# ============================================================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "songs": {},
        "washed_up_ids": [],
        "last_history_snapshot": [],
        "now_playlist_id": None,
        "washed_up_playlist_id": None,
    }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


# ============================================================
# PLAYLISTS
# ============================================================

def find_or_create_playlist(ytm, name, description=""):
    try:
        for pl in ytm.get_library_playlists(limit=100):
            if pl["title"].lower() == name.lower():
                print(f"  ✅  Found '{name}'")
                return pl["playlistId"]
    except Exception as e:
        print(f"  ⚠️  Couldn't search playlists: {e}")
    pid = ytm.create_playlist(name, description)
    print(f"  🆕  Created '{name}'")
    return pid


def get_playlist_tracks(ytm, playlist_id):
    try:
        return ytm.get_playlist(playlist_id, limit=200).get("tracks", [])
    except Exception as e:
        print(f"  ⚠️  Error fetching playlist: {e}")
        return []


def sync_playlist_to_state(state, tracks):
    """Keep state in sync with the actual Now playlist."""
    playlist_ids = {t["videoId"] for t in tracks if t.get("videoId")}

    for track in tracks:
        vid = track.get("videoId")
        if vid and vid not in state["songs"]:
            state["songs"][vid] = {
                "title":       track.get("title", "Unknown"),
                "artist":      ", ".join(a["name"] for a in track.get("artists", [])),
                "miss_count":  0,
                "last_seen":   None,
                "date_added":  datetime.now(timezone.utc).isoformat(),
                "total_plays": 0,
            }

    for vid in list(state["songs"]):
        if vid not in playlist_ids:
            del state["songs"][vid]

    return state


# ============================================================
# HISTORY & SKIP DETECTION
# ============================================================

def get_history_ids(ytm, state):
    """
    Returns (new_ids, snapshot).
    new_ids = songs played since the last poll.
    Only songs that are new to the snapshot count — this is how we
    detect what was actually listened to between poll cycles.
    """
    try:
        history       = ytm.get_history()
        current_ids   = [h["videoId"] for h in history if h.get("videoId")]
        last_snapshot = set(state.get("last_history_snapshot", []))
        new_ids       = set(vid for vid in current_ids if vid not in last_snapshot)
        return new_ids, current_ids[:50]
    except Exception as e:
        print(f"  ⚠️  History error: {e}")
        return set(), state.get("last_history_snapshot", [])


def update_miss_counts(state, new_history_ids):
    """
    For each song in Now:
      - Appears in new history  → heard! reset miss streak
      - Not heard, but other music played → miss +1 (you played music but skipped it)
      - Not heard, no music played at all → no penalty (you weren't listening)
    """
    music_was_played = len(new_history_ids) > 0
    washed_out = []

    for vid, song in list(state["songs"].items()):
        if vid in new_history_ids:
            old_miss = song["miss_count"]
            song.update({
                "miss_count":  0,
                "last_seen":   datetime.now(timezone.utc).isoformat(),
                "total_plays": song.get("total_plays", 0) + 1,
            })
            if old_miss > 0:
                print(f"  🎵  Heard: {song['title']} — {song['artist']}  "
                      f"(miss streak reset from {old_miss})")
        elif music_was_played:
            song["miss_count"] = song.get("miss_count", 0) + 1
            if song["miss_count"] >= SKIP_THRESHOLD:
                print(f"  💀  Retiring: {song['title']} — {song['artist']}  "
                      f"(missed {SKIP_THRESHOLD} polls in a row)")
                washed_out.append(vid)

    return state, washed_out


def move_to_washed_up(ytm, state, video_ids, now_id, washed_id):
    if not video_ids:
        return state

    now_tracks = get_playlist_tracks(ytm, now_id)
    track_map  = {t["videoId"]: t for t in now_tracks if t.get("videoId")}

    for vid in video_ids:
        song  = state["songs"].get(vid, {})
        track = track_map.get(vid)
        try:
            ytm.add_playlist_items(washed_id, [vid])
            if track and track.get("setVideoId"):
                ytm.remove_playlist_items(now_id,
                    [{"videoId": vid, "setVideoId": track["setVideoId"]}])
            state["washed_up_ids"].append(vid)
            state["songs"].pop(vid, None)
            print(f"  ✅  Moved '{song.get('title', vid)}' to Washed Up")
        except Exception as e:
            print(f"  ⚠️  Couldn't move '{song.get('title', vid)}': {e}")

    return state


# ============================================================
# RECOMMENDATIONS
# ============================================================

def get_recommendations(ytm, state):
    already_have = set(state["songs"]) | set(state.get("washed_up_ids", []))
    recs = []

    # Source 1: YouTube Music home feed
    try:
        for section in ytm.get_home(limit=4):
            for item in section.get("contents", []):
                vid = item.get("videoId")
                if vid and vid not in already_have:
                    recs.append({
                        "videoId": vid,
                        "title":   item.get("title", "?"),
                        "artist":  ", ".join(a["name"] for a in item.get("artists", []))
                                   if item.get("artists") else "?",
                    })
    except Exception as e:
        print(f"  ⚠️  Home feed error: {e}")

    # Source 2: Radio seeded from your most-played songs
    top_seeds = sorted(
        state["songs"].items(),
        key=lambda x: x[1].get("total_plays", 0),
        reverse=True
    )[:3]

    for seed_vid, seed_song in top_seeds:
        try:
            radio = ytm.get_watch_playlist(videoId=seed_vid, radio=True, limit=8)
            for track in radio.get("tracks", []):
                vid = track.get("videoId")
                if vid and vid not in already_have:
                    recs.append({
                        "videoId": vid,
                        "title":   track.get("title", "?"),
                        "artist":  ", ".join(a["name"] for a in track.get("artists", []))
                                   if track.get("artists") else "?",
                    })
        except Exception:
            pass

    # Deduplicate
    seen, unique = set(), []
    for r in recs:
        if r["videoId"] not in seen:
            seen.add(r["videoId"])
            unique.append(r)
    return unique


def add_recommendations(ytm, state, recs, now_id):
    slots  = TARGET_PLAYLIST_SIZE - len(state["songs"])
    to_add = recs[:min(slots, SONGS_TO_ADD_PER_CYCLE)] if slots > 0 else []

    for song in to_add:
        try:
            ytm.add_playlist_items(now_id, [song["videoId"]])
            state["songs"][song["videoId"]] = {
                "title":       song["title"],
                "artist":      song["artist"],
                "miss_count":  0,
                "last_seen":   None,
                "date_added":  datetime.now(timezone.utc).isoformat(),
                "total_plays": 0,
            }
            print(f"  ➕  Added: {song['title']} — {song['artist']}")
        except Exception as e:
            print(f"  ⚠️  Couldn't add '{song['title']}': {e}")

    return state


# ============================================================
# ONE POLL CYCLE
# ============================================================

def run_cycle(ytm, state):
    now_id    = state["now_playlist_id"]
    washed_id = state["washed_up_playlist_id"]
    ts        = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    print(f"\n{'='*60}")
    print(f"  🔄  {ts}")
    print(f"  Tracking {len(state['songs'])} songs in '{NOW_PLAYLIST_NAME}'")
    print(f"{'='*60}")

    # 1. What's been played since last poll?
    new_ids, snapshot = get_history_ids(ytm, state)
    print(f"\n  📖  {len(new_ids)} new play(s) detected since last check")

    # 2. Update miss counts; find songs ready to retire
    state, washed_out = update_miss_counts(state, new_ids)

    # 3. Retire ignored songs
    if washed_out:
        print(f"\n  🚿  Retiring {len(washed_out)} song(s) to Washed Up...")
        state = move_to_washed_up(ytm, state, washed_out, now_id, washed_id)

    # 4. Add fresh picks
    print(f"\n  🎯  Fetching recommendations...")
    recs  = get_recommendations(ytm, state)
    state = add_recommendations(ytm, state, recs, now_id)

    # 5. Re-sync (picks up any manual playlist edits)
    state = sync_playlist_to_state(state, get_playlist_tracks(ytm, now_id))

    # 6. Persist
    state["last_history_snapshot"] = snapshot
    save_state(state)

    now_count    = len(state["songs"])
    washed_count = len(state["washed_up_ids"])
    print(f"\n  ✅  Done  |  Now: {now_count} songs  |  Washed Up: {washed_count} songs")
    print(f"  ⏰  Next check in {POLL_INTERVAL_MINUTES} min  (Ctrl+C to stop)\n")
    return state


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    print("\n🎵  YouTube Music Playlist Manager")
    print(f"    Now: '{NOW_PLAYLIST_NAME}'  →  target {TARGET_PLAYLIST_SIZE} songs")
    print(f"    Washed Up after {SKIP_THRESHOLD} missed polls "
          f"(~{SKIP_THRESHOLD * POLL_INTERVAL_MINUTES // 60}h of active ignoring)\n")

    ensure_dependencies()
    ensure_authenticated()

    from ytmusicapi import YTMusic
    ytm = YTMusic(AUTH_FILE)

    # Load or initialise state
    state = load_state()
    if not state["now_playlist_id"]:
        print("🔍  Finding/creating playlists...")
        state["now_playlist_id"]       = find_or_create_playlist(ytm, NOW_PLAYLIST_NAME,
                                                                  "Auto-refreshing playlist")
        state["washed_up_playlist_id"] = find_or_create_playlist(ytm, WASHED_UP_PLAYLIST_NAME,
                                                                  "Songs I used to love")
        print(f"\n📥  Syncing '{NOW_PLAYLIST_NAME}' into tracker...")
        tracks = get_playlist_tracks(ytm, state["now_playlist_id"])
        state  = sync_playlist_to_state(state, tracks)
        print(f"    → Tracking {len(state['songs'])} songs")
        save_state(state)
        print()

    # Main loop
    print(f"▶️   Manager running — polls every {POLL_INTERVAL_MINUTES} min.")
    print("    Leave this window open while you listen. Press Ctrl+C to stop.\n")

    while True:
        try:
            state = run_cycle(ytm, state)
            time.sleep(POLL_INTERVAL_MINUTES * 60)
        except KeyboardInterrupt:
            print("\n⏹️   Stopped. Run again to resume.")
            break
        except Exception as e:
            print(f"\n⚠️   Unexpected error: {e}")
            print("    Retrying in 5 minutes...")
            time.sleep(300)


if __name__ == "__main__":
    main()
