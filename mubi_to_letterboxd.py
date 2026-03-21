#!/usr/bin/env python3
"""
mubi_to_letterboxd.py
──────────────────────────────────────────────────────────────────────────────
Exports your MUBI watchlist to a Letterboxd-compatible CSV, then opens the
Letterboxd import page so you can upload it in one click.

QUICK START
────────────
1.  pip3 install requests
2.  Get your MUBI user ID  →  go to https://mubi.com and click your avatar.
    Your profile URL looks like:  https://mubi.com/en/users/12345678
    Your user ID is the number at the end.
3.  Get your MUBI Bearer token (see below).
4.  Run:
        python3 mubi_to_letterboxd.py --user-id 12345678 --token "Bearer ..."

HOW TO GET YOUR MUBI TOKEN
───────────────────────────
a. Open https://mubi.com in Chrome or Firefox and sign in.
b. Open DevTools → Network tab  (Cmd+Option+I → Network).
c. Reload the page, then filter requests by typing "wishes" or "api".
d. Click any request to  mubi.com/services/api/…
e. In the "Headers" panel find the "Authorization" request header.
   It looks like:  Authorization: Bearer ...
f. Copy the full value including "Bearer ".

TROUBLESHOOTING
───────────────
If fewer films are returned than expected, run with --debug to see the raw
API response and help identify the correct pagination fields:
    python3 mubi_to_letterboxd.py --user-id 12345678 --token "Bearer ..." --debug
──────────────────────────────────────────────────────────────────────────────
"""

import argparse
import csv
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("❌  Missing dependency. Run:  pip3 install requests")
    sys.exit(1)

# ── MUBI internal API constants ───────────────────────────────────────────────
MUBI_WATCHLIST_URL = "https://mubi.com/services/api/wishes"
MUBI_HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin":          "https://mubi.com",
    "Referer":         "https://mubi.com/",
    "client":          "web",
    "client-version":  "4.0.0",
}

LETTERBOXD_IMPORT_URL = "https://letterboxd.com/import/"
PER_PAGE = 24  # Use MUBI's natural page size to avoid any server-side capping


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_headers(token: str) -> Dict[str, str]:
    h = dict(MUBI_HEADERS)
    h["Authorization"] = token if token.startswith("Bearer ") else "Bearer " + token
    return h


def extract_items_and_meta(data: object, resp: requests.Response, debug: bool) -> Tuple[List[dict], Optional[int], Optional[bool]]:
    """
    Given a parsed JSON response, return:
      (items_list, total_count_or_None, has_next_page_or_None)

    We inspect all common pagination shapes MUBI might use.
    """
    items: List[dict] = []
    total: Optional[int] = None
    has_next: Optional[bool] = None

    if debug:
        print("\n── DEBUG: Response headers ──")
        for k, v in resp.headers.items():
            print("    {}: {}".format(k, v))
        print("\n── DEBUG: Raw JSON (first 1500 chars) ──")
        print(json.dumps(data, indent=2)[:1500])
        print()

    if isinstance(data, list):
        # Plain list — no meta available
        items = data

    elif isinstance(data, dict):
        # Try to find the items array under common key names
        for key in ("wishes", "films", "items", "results", "data", "movies"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break

        # Total count — check common field names
        for key in ("total_count", "total", "count", "meta_count", "film_count"):
            if key in data and isinstance(data[key], int):
                total = data[key]
                break

        # Check nested meta object
        meta = data.get("meta") or data.get("pagination") or {}
        if isinstance(meta, dict):
            for key in ("total_count", "total", "count", "total_entries"):
                if key in meta and isinstance(meta[key], int):
                    total = meta[key]
                    break
            # next_page in meta
            if "next_page" in meta:
                has_next = meta["next_page"] is not None
            if "has_next_page" in meta:
                has_next = bool(meta["has_next_page"])

        # Top-level next_page field
        if has_next is None and "next_page" in data:
            has_next = data["next_page"] is not None

    # Also check response headers for total (some APIs use X-Total-Count etc.)
    for header in ("X-Total-Count", "X-Total", "Total-Count", "total-count"):
        if header in resp.headers:
            try:
                total = int(resp.headers[header])
            except ValueError:
                pass
            break

    return items, total, has_next


def fetch_watchlist(session: requests.Session, token: str, user_id: str, debug: bool) -> List[dict]:
    all_items: List[dict] = []
    headers = make_headers(token)
    page = 1
    known_total: Optional[int] = None

    print("\n📥  Fetching MUBI watchlist for user {} …".format(user_id))

    while True:
        params: Dict[str, object] = {
            "user_id":  user_id,
            "page":     page,
            "per_page": PER_PAGE,
        }

        try:
            resp = session.get(MUBI_WATCHLIST_URL, headers=headers, params=params, timeout=20)
        except requests.RequestException as exc:
            print("\n❌  Network error: {}".format(exc))
            sys.exit(1)

        if resp.status_code == 401:
            print("\n❌  Authentication failed (401). Your Bearer token has expired.")
            print("    Grab a fresh one from DevTools → Network → any mubi.com/services/api request.")
            sys.exit(1)

        if resp.status_code == 404:
            print("\n❌  404 Not Found for user ID {}.".format(user_id))
            print("    Double-check your user ID — it's the number in your MUBI profile URL.")
            print("    e.g. https://mubi.com/en/users/12345678  →  --user-id 12345678")
            sys.exit(1)

        if not resp.ok:
            print("\n❌  MUBI API error (HTTP {}) on page {}:".format(resp.status_code, page))
            print("   ", resp.text[:300])
            sys.exit(1)

        try:
            data = resp.json()
        except Exception:
            print("\n❌  Could not parse JSON response on page {}.".format(page))
            print("    Response snippet:", resp.text[:300])
            sys.exit(1)

        items, total, has_next = extract_items_and_meta(data, resp, debug and page == 1)

        if total is not None and known_total is None:
            known_total = total
            print("    API reports {} total films in watchlist.".format(known_total))

        if not items:
            # No items on this page — we're done
            break

        all_items.extend(items)
        fetched = len(all_items)
        print("    Page {}: {} items fetched  (running total: {}{})".format(
            page,
            len(items),
            fetched,
            " / {}".format(known_total) if known_total else "",
        ))

        # Decide whether to continue paginating
        # Strategy 1: API told us there's a next page
        if has_next is True:
            page += 1
            time.sleep(0.3)
            continue

        # Strategy 2: API told us there is NO next page
        if has_next is False:
            break

        # Strategy 3: We know the total — keep going until we have it all
        if known_total is not None and fetched < known_total:
            page += 1
            time.sleep(0.3)
            continue

        # Strategy 4: No meta at all — keep paginating as long as we got a full page
        if len(items) == PER_PAGE:
            page += 1
            time.sleep(0.3)
            continue

        # Got a partial page with no other signal — assume we're done
        break

    if known_total is not None and len(all_items) < known_total:
        print("\n⚠️   Warning: fetched {} films but API reported {}. Some may be missing.".format(
            len(all_items), known_total
        ))
        print("    Try running with --debug to inspect the API response structure.")

    return all_items


def parse_film(item: dict) -> Optional[Dict[str, str]]:
    """Extract title and year from a raw MUBI watchlist item."""
    film = item.get("film") or item

    title = (
        film.get("title")
        or film.get("original_title")
        or film.get("name")
        or ""
    ).strip()

    year = (
        film.get("year")
        or film.get("release_year")
        or film.get("production_year")
        or ""
    )

    if not title:
        return None

    return {"Title": title, "Year": str(year) if year else ""}


def write_csv(films: List[Dict[str, str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Title", "Year"])
        writer.writeheader()
        writer.writerows(films)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export your MUBI watchlist to a Letterboxd CSV import file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--token", "-t",
        default=os.environ.get("MUBI_TOKEN", ""),
        metavar="BEARER_TOKEN",
        help='Your MUBI Bearer token (include "Bearer "). Also: set MUBI_TOKEN env var.',
    )
    p.add_argument(
        "--user-id", "-u",
        default=os.environ.get("MUBI_USER_ID", ""),
        metavar="USER_ID",
        help="Your MUBI numeric user ID (from your profile URL). Also: set MUBI_USER_ID env var.",
    )
    p.add_argument(
        "--output", "-o",
        default="mubi_watchlist.csv",
        metavar="FILE",
        help="Output CSV filename (default: mubi_watchlist.csv)",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the Letterboxd import page automatically.",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Print raw API response from page 1 to diagnose pagination issues.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    token: str = args.token.strip()
    user_id: str = (args.user_id or "").strip()

    if not token:
        print("❌  No MUBI token supplied.")
        print("    Use --token 'Bearer eyJ...' or set the MUBI_TOKEN environment variable.")
        print()
        print("    To find your token:")
        print("    1. Open https://mubi.com in Chrome/Firefox and sign in.")
        print("    2. Open DevTools → Network tab (Cmd+Option+I).")
        print("    3. Filter requests by 'wishes' or 'api'.")
        print("    4. Click any request to mubi.com/services/api/…")
        print("    5. Copy the 'Authorization' header (starts with 'Bearer ').")
        sys.exit(1)

    if not user_id:
        print("❌  No MUBI user ID supplied.")
        print("    Use --user-id 12345678 or set the MUBI_USER_ID environment variable.")
        print()
        print("    To find your user ID:")
        print("    1. Go to https://mubi.com and click your avatar → Profile.")
        print("    2. Your profile URL looks like:  https://mubi.com/en/users/12345678")
        print("    3. The number at the end is your user ID.")
        sys.exit(1)

    output_path = Path(args.output)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})

    raw_items = fetch_watchlist(session, token, user_id, args.debug)

    if not raw_items:
        print("\n⚠️   Watchlist appears empty (API returned no items).")
        print("    Make sure you've added films to your MUBI watchlist (the bookmark icon).")
        sys.exit(0)

    films: List[Dict[str, str]] = []
    skipped = 0
    for item in raw_items:
        info = parse_film(item)
        if info:
            films.append(info)
        else:
            skipped += 1

    print("\n✅  {} films ready for export.".format(len(films)), end="")
    if skipped:
        print("  ({} skipped — no title data)".format(skipped), end="")
    print()

    write_csv(films, output_path)
    print("💾  Saved: {}".format(output_path.resolve()))

    n = min(5, len(films))
    print("\n   First {} films:".format(n))
    for f in films[:n]:
        year_str = " ({})".format(f["Year"]) if f["Year"] else ""
        print("   • {}{}".format(f["Title"], year_str))
    if len(films) > n:
        print("   … and {} more.".format(len(films) - n))

    print("""
─────────────────────────────────────────────────────────────────
📋  NEXT STEPS — Import to Letterboxd
─────────────────────────────────────────────────────────────────
1. The Letterboxd import page will open in your browser.
2. Log in to Letterboxd if prompted.
3. Choose "Import to a List" to create a new list.
4. Upload the CSV file saved above.
5. Letterboxd matches films by Title + Year.
   Unmatched films are listed so you can add them manually.
─────────────────────────────────────────────────────────────────
""")

    if not args.no_browser:
        print("🌐  Opening {} …".format(LETTERBOXD_IMPORT_URL))
        webbrowser.open(LETTERBOXD_IMPORT_URL)

    print("Done! 🎬")


if __name__ == "__main__":
    main()
