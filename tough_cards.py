#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict

def normalize_tag(tag):
    tag = tag.strip().upper()
    return tag if tag.startswith("#") else "#" + tag

def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze opponent cards you lose against."
    )
    parser.add_argument(
        "tag",
        help="Player tag, e.g. #ABC123",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("CR_SQLITE_DB", "clash_royale.db"),
        help="SQLite database path (default: CR_SQLITE_DB or clash_royale.db)",
    )
    parser.add_argument(
        "--min-encounters",
        type=int,
        default=1,
        help="Minimum encounters for the loss-rate ranking (default: 1)",
    )
    return parser.parse_args()

def validate_schema(conn):
    columns = {r[1] for r in conn.execute("PRAGMA table_info(battles)")}
    required = {"player_tag", "result", "opponent_deck_info"}
    missing = required - columns
    if missing:
        raise RuntimeError("Missing database column(s): " + ", ".join(sorted(missing)))

def active_form(card):
    # Frozen hybrid rule: Evo takes precedence if both are active.
    if card.get("evolution_active") is True:
        return "Evo"
    if card.get("hero_active") is True:
        return "Hero"
    return "Normal"

def load_stats(conn, tag):
    rows = conn.execute(
        """
        SELECT result, opponent_deck_info
        FROM battles
        WHERE player_tag = ?
        ORDER BY battle_id ASC
        """,
        (tag,),
    ).fetchall()

    stats = defaultdict(lambda: {
        "encounters": 0,
        "losses": 0,
        "forms": {
            "Hero": {"encounters": 0, "losses": 0},
            "Evo": {"encounters": 0, "losses": 0},
            "Normal": {"encounters": 0, "losses": 0},
        },
    })

    skipped = 0

    for result, raw_deck in rows:
        try:
            deck = json.loads(raw_deck)
        except (TypeError, json.JSONDecodeError):
            skipped += 1
            continue

        if not isinstance(deck, list) or len(deck) != 8:
            skipped += 1
            continue

        is_loss = result == "L"

        for card in deck:
            name = card.get("name")
            if not name:
                continue

            name = str(name)
            form = active_form(card)

            stats[name]["encounters"] += 1
            stats[name]["forms"][form]["encounters"] += 1

            if is_loss:
                stats[name]["losses"] += 1
                stats[name]["forms"][form]["losses"] += 1

    return rows, stats, skipped

def rate(data):
    return 100.0 * data["losses"] / data["encounters"] if data["encounters"] else 0.0

def form_rate(data):
    return 100.0 * data["losses"] / data["encounters"] if data["encounters"] else 0.0

def top_by_losses(stats):
    return sorted(
        stats.items(),
        key=lambda x: (-x[1]["losses"], -rate(x[1]), -x[1]["encounters"], x[0].lower()),
    )[:5]

def top_by_rate(stats, minimum):
    eligible = [
        x for x in stats.items()
        if x[1]["encounters"] >= minimum
    ]
    return sorted(
        eligible,
        key=lambda x: (-rate(x[1]), -x[1]["losses"], -x[1]["encounters"], x[0].lower()),
    )[:5]

def print_loss_section(stats):
    print("\n" + "=" * 60)
    print("TOP 5 CARDS BY LOSSES")
    print("=" * 60)

    for rank, (name, data) in enumerate(top_by_losses(stats), 1):
        print(f"\n{rank}. {name}: {data['losses']}")
        for form in ("Hero", "Evo"):
            n = data["forms"][form]["losses"]
            if n > 0:
                print(f"    {form} {name}: {n}")

def print_rate_section(stats, minimum):
    print("\n" + "=" * 60)
    print("TOP 5 CARDS BY LOSS RATE")
    print("=" * 60)

    for rank, (name, data) in enumerate(top_by_rate(stats, minimum), 1):
        matches = data["encounters"]
        label = "match" if matches == 1 else "matches"
        print(f"\n{rank}. {name}: {rate(data):.1f}% ({matches} {label})")

        for form in ("Hero", "Evo"):
            form_data = data["forms"][form]
            if form_data["encounters"] > 0:
                form_matches = form_data["encounters"]
                form_label = "match" if form_matches == 1 else "matches"
                print(
                    f"    {form} {name}: "
                    f"{form_rate(form_data):.1f}% "
                    f"({form_matches} {form_label})"
                )

def main():
    args = parse_args()

    if args.min_encounters < 1:
        print("ERROR: --min-encounters must be >= 1", file=sys.stderr)
        return 2

    tag = normalize_tag(args.tag)

    if not os.path.exists(args.db):
        print(f"ERROR: database not found: {args.db}", file=sys.stderr)
        return 1

    try:
        conn = sqlite3.connect(args.db)
        validate_schema(conn)
        rows, stats, skipped = load_stats(conn, tag)
        conn.close()
    except (sqlite3.Error, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print(f"No battles found for {tag}.")
        return 0

    print(f"\nPLAYER: {tag}")
    print(f"BATTLES: {len(rows)}")

    if skipped:
        print(f"WARNING: skipped {skipped} malformed opponent deck record(s).")

    print_loss_section(stats)
    print_rate_section(stats, args.min_encounters)
    print()

    return 0

if __name__ == "__main__":
    raise SystemExit(main())