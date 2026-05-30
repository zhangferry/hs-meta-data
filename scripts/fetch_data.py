"""
Hearthstone Meta Data Fetcher

Collects data from multiple sources and saves to the repo structure:
1. HearthstoneJSON - Complete card database
2. Firestone/ZeroToHeroes - Meta deck statistics
3. HSReplay - Archetype definitions
4. Vicious Syndicate - Matchup winrates (weekly)

Run daily via GitHub Actions.
"""

import json
import gzip
import os
import sys
from datetime import datetime, timezone

import requests

# Add scripts dir to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_vs_matchup import fetch_and_parse_vs_matchup

# --- Configuration ---

HEARTHSTONE_JSON_BASE = "https://api.hearthstonejson.com/v1/latest"
HSREPLAY_ARCHETYPES = "https://hsreplay.net/api/v1/archetypes/"
FIRESTONE_BASE = "https://static.zerotoheroes.com/api/constructed/stats/decks"

LOCALES = {
    "zhCN": "Simplified Chinese",
    "enUS": "English",
}

FORMATS = ["standard", "wild"]
RANKS = ["all", "diamond", "legend"]
PERIODS = ["past-3", "past-7", "past-20"]  # past-30 returns 404 from Firestone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- Helpers ---

def fetch_json(url, is_gzip=False, timeout=60):
    """Fetch JSON from a URL, optionally gzip-compressed."""
    headers = {"User-Agent": "hs-meta-data-bot/1.0"}
    resp = requests.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    if is_gzip:
        # Firestone URLs end in .gz.json but may return plain JSON
        try:
            return json.loads(gzip.decompress(resp.content))
        except (gzip.BadGzipFile, OSError):
            return resp.json()
    return resp.json()


def save_json(data, *path_parts):
    """Save data as JSON to a path relative to repo root."""
    path = os.path.join(REPO_ROOT, *path_parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


# --- Data Fetchers ---

def fetch_card_database():
    """Fetch complete card database from HearthstoneJSON."""
    results = {}
    for locale in LOCALES:
        url = f"{HEARTHSTONE_JSON_BASE}/{locale}/cards.collectible.json"
        try:
            data = fetch_json(url)
            path = save_json(data, "cards", f"cards_collectible_{locale}.json")
            results[locale] = len(data)
            print(f"  ✅ {locale}: {len(data)} cards → {path}")
        except Exception as e:
            print(f"  ❌ {locale}: {e}")
            results[locale] = 0
    return results


def fetch_archetypes():
    """Fetch archetype definitions from HSReplay."""
    try:
        data = fetch_json(HSREPLAY_ARCHETYPES)
        save_json(data, "archetypes", "archetypes.json")
        print(f"  ✅ archetypes: {len(data)} entries")
        return len(data)
    except Exception as e:
        print(f"  ❌ archetypes: {e}")
        return 0


def fetch_meta_stats():
    """Fetch meta deck statistics from Firestone for all format/rank/period combos."""
    total = 0
    for fmt in FORMATS:
        for rank in RANKS:
            for period in PERIODS:
                url = f"{FIRESTONE_BASE}/{fmt}/{rank}/{period}/overview-from-hourly.gz.json"
                try:
                    data = fetch_json(url, is_gzip=True)
                    save_json(data, "meta", fmt, rank, f"{period}.json")
                    decks = len(data.get("deckStats", []))
                    total += decks
                    print(f"  ✅ {fmt}/{rank}/{period}: {decks} decks")
                except Exception as e:
                    print(f"  ⚠️  {fmt}/{rank}/{period}: {e}")
    return total


def fetch_matchup_data():
    """Fetch and parse vS matchup data."""
    try:
        result = fetch_and_parse_vs_matchup()
        if result:
            # Save latest
            save_json(result, "matchup", "latest.json")
            # Save to history
            report_num = result.get("reportNumber")
            if report_num:
                save_json(result, "matchup", "history", f"{report_num}.json")
            return result
    except Exception as e:
        print(f"  ⚠️  matchup: {e}")
    return None


# --- Main ---

def main():
    print("=" * 60)
    print("🎮 Hearthstone Meta Data Fetcher")
    print(f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    sources_status = {}

    # 1. Card Database
    print("\n📚 [1/4] Fetching card database from HearthstoneJSON...")
    card_results = fetch_card_database()
    sources_status["cards"] = card_results

    # 2. Archetypes
    print("\n🏗️  [2/4] Fetching archetypes from HSReplay...")
    archetype_count = fetch_archetypes()
    sources_status["archetypes"] = archetype_count

    # 3. Meta Stats
    print("\n📊 [3/4] Fetching meta stats from Firestone...")
    meta_count = fetch_meta_stats()
    sources_status["meta_decks"] = meta_count

    # 4. Matchup Data
    print("\n⚔️  [4/4] Fetching matchup data from Vicious Syndicate...")
    matchup_result = fetch_matchup_data()
    sources_status["matchup"] = {
        "quality": matchup_result.get("dataQuality", "none") if matchup_result else "none",
        "report": matchup_result.get("reportNumber") if matchup_result else None,
    }

    # 5. Write metadata
    metadata = {
        "lastUpdated": datetime.now(timezone.utc).isoformat() + "Z",
        "version": "1.0.0",
        "sources": {
            "hearthstone_json": "https://api.hearthstonejson.com",
            "firestone": "https://static.zerotoheroes.com",
            "hsreplay": "https://hsreplay.net",
            "vicious_syndicate": "https://www.vicioussyndicate.com",
        },
        "stats": {
            "cards_zhCN": card_results.get("zhCN", 0),
            "cards_enUS": card_results.get("enUS", 0),
            "archetypes": archetype_count,
            "meta_deck_entries": meta_count,
            "matchup_quality": sources_status["matchup"]["quality"],
            "matchup_report": sources_status["matchup"]["report"],
        },
    }
    save_json(metadata, "metadata.json")

    # Summary
    print("\n" + "=" * 60)
    print("📋 Summary:")
    print(f"  Cards (zhCN): {card_results.get('zhCN', 0)}")
    print(f"  Cards (enUS): {card_results.get('enUS', 0)}")
    print(f"  Archetypes:   {archetype_count}")
    print(f"  Meta decks:   {meta_count}")
    print(f"  Matchup:      {sources_status['matchup']['quality']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
