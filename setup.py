"""
Run this once to authenticate with YouTube Music.
After it finishes, run manager.py normally.
"""
import json
from ytmusicapi import setup
from ytmusicapi.helpers import get_authorization, sapisid_from_cookie

print("=" * 60)
print("  YouTube Music — One-Time Auth Setup")
print("=" * 60)
print("""
1. Open YouTube Music in Chrome: https://music.youtube.com
2. Press F12 → Network tab
3. Click any song to play it
4. Find any request to music.youtube.com (e.g. 'watchtime')
5. Click it → Headers → select ALL Request Headers → copy

Paste everything below, then press Enter, Ctrl-Z, Enter to finish.
""")

setup(filepath="headers_auth.json")

# ytmusicapi needs an 'authorization' header present in the file
# to detect browser-based auth. It regenerates the actual value
# on every request from your cookies anyway.
with open("headers_auth.json", encoding="utf-8") as f:
    headers = json.load(f)

if "authorization" not in headers:
    try:
        sapisid = sapisid_from_cookie(headers["cookie"])
        origin  = headers.get("origin", headers.get("x-origin", "https://music.youtube.com"))
        headers["authorization"] = get_authorization(sapisid + " " + origin)
        with open("headers_auth.json", "w", encoding="utf-8") as f:
            json.dump(headers, f, indent=4, sort_keys=True)
        print("✅ Authorization header generated from your cookies.")
    except Exception as e:
        print(f"⚠️  Could not generate authorization header: {e}")

print("\n✅ Saved to headers_auth.json — you're all set!")
print("   Now double-click Start Manager.bat to run.\n")
