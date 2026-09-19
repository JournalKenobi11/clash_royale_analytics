#!/usr/bin/env python3
"""
Clash Royale Personal Performance Analyzer — SQLite edition

Usage:
    python3 analyser.py "#822JCG2YL"
    python3 analyser.py "#822JCG2YL" --last 15
    python3 analyser.py "#822JCG2YL" --no-fetch

Required environment variable:
    CR_API_TOKEN

Optional environment variables:
    CR_API_BASE_URL   Defaults to https://proxy.royaleapi.dev/v1
    CR_SQLITE_DB      Defaults to ./clash_royale.db

Database identity:
    opponent_tag is the unique battle identifier within each player dataset.
    battle_id is only the sequential SQLite row ID.

Only gameMode.name == "Ladder" is stored.

Normalized displayed card level:
    Common    +0
    Rare      +2
    Epic      +5
    Legendary +8
    Champion  +10

ADSI:
    x_i = (L_i - 1) / 15
    w_i = i / 36
    ADSI = 100 * sum(w_i * x_i)
    where sorted normalized displayed levels are L_1 ... L_8.

Level Handicap:
    g(d) = d,                         d <= 2
           2 + 1.5(d - 2),            d > 2

    opponent multiplier:
        <=12: 1.00
        13:   1.10
        14:   1.25
        15:   1.50
        16+:  1.80

    P = sum |g(d)| for d < 0
    H = sum g(d)*w(o) for d > 0
    S = g(o8-y8)*w(o8)
    LH = H - P + 0.25*S
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Any

import requests


RARITY_OFFSETS = {
    "common": 0,
    "rare": 2,
    "epic": 5,
    "legendary": 8,
    "champion": 10,
}

BANDS = (
    "< -3",
    "-3 to -1",
    "-1 to +1",
    "+1 to +3",
    "+3 to +6",
    "> +6",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS battles (
    battle_id INTEGER PRIMARY KEY AUTOINCREMENT,

    chronology_id INTEGER NOT NULL,

    player_tag TEXT NOT NULL,
    player_name TEXT NOT NULL,
    opponent_tag TEXT NOT NULL,

    result TEXT NOT NULL CHECK (result IN ('W', 'L')),

    player_deck_vector TEXT NOT NULL,
    opponent_deck_vector TEXT NOT NULL,
    LH_difference TEXT NOT NULL,

    player_ADSI REAL NOT NULL,
    opponent_ADSI REAL NOT NULL,
    ADSI_difference REAL NOT NULL,

    H REAL NOT NULL,
    P REAL NOT NULL,
    S REAL NOT NULL,
    LH REAL NOT NULL,

    LH_band TEXT NOT NULL CHECK (
        LH_band IN (
            '< -3',
            '-3 to -1',
            '-1 to +1',
            '+1 to +3',
            '+3 to +6',
            '> +6'
        )
    ),

    player_trophies INTEGER NOT NULL,

    UNIQUE (player_tag, opponent_tag)
);

CREATE INDEX IF NOT EXISTS idx_battles_player_tag_id
ON battles(player_tag, battle_id ASC);
"""


def normalize_tag(tag: str) -> str:
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag


def api_tag(tag: str) -> str:
    return requests.utils.quote(tag, safe="")


def normalize_level(card: dict[str, Any]) -> int:
    rarity = str(card["rarity"]).lower()

    if rarity not in RARITY_OFFSETS:
        raise ValueError(f"Unknown rarity: {card.get('rarity')!r}")

    return int(card["level"]) + RARITY_OFFSETS[rarity]


def extract_deck(
    side: dict[str, Any],
) -> tuple[list[str], list[int], list[int], list[bool]]:
    cards = side.get("cards") or []

    if len(cards) != 8:
        raise ValueError(f"Expected exactly 8 cards, got {len(cards)}")

    rows = []

    for card in cards:
        rows.append(
            {
                "name": str(card["name"]),
                "level": normalize_level(card),
                "evolution": int(card.get("evolutionLevel", 0) or 0),
                "hero": bool(
                    (card.get("iconUrls") or {}).get("heroMedium")
                ),
            }
        )

    rows.sort(key=lambda r: (r["level"], r["name"]))

    return (
        [r["name"] for r in rows],
        [r["level"] for r in rows],
        [r["evolution"] for r in rows],
        [r["hero"] for r in rows],
    )


def calculate_adsi(levels: list[int]) -> float:
    """Absolute Deck Strength Index, using the locked formula."""
    if len(levels) != 8:
        raise ValueError("ADSI requires exactly 8 card levels.")

    ordered = sorted(levels)

    return 100.0 * sum(
        (i / 36.0) * ((level - 1) / 15.0)
        for i, level in enumerate(ordered, start=1)
    )


def g(d: float) -> float:
    if d <= 2:
        return d
    return 2.0 + 1.5 * (d - 2.0)


def opponent_weight(level: int) -> float:
    if level <= 12:
        return 1.00
    if level == 13:
        return 1.10
    if level == 14:
        return 1.25
    if level == 15:
        return 1.50
    return 1.80


def calculate_lh(
    player_levels: list[int],
    opponent_levels: list[int],
) -> tuple[float, float, float, float]:
    if len(player_levels) != 8 or len(opponent_levels) != 8:
        raise ValueError("LH requires two 8-card level vectors.")

    y = sorted(player_levels)
    o = sorted(opponent_levels)

    d = [o[i] - y[i] for i in range(8)]
    base = [g(x) for x in d]

    P = sum(abs(base[i]) for i in range(8) if d[i] < 0)

    H = sum(
        base[i] * opponent_weight(o[i])
        for i in range(8)
        if d[i] > 0
    )

    S = g(o[7] - y[7]) * opponent_weight(o[7])

    LH = H - P + 0.25 * S

    return H, P, S, LH


def get_lh_band(lh: float) -> str:
    if lh < -3:
        return "< -3"
    if lh < -1:
        return "-3 to -1"
    if lh <= 1:
        return "-1 to +1"
    if lh <= 3:
        return "+1 to +3"
    if lh <= 6:
        return "+3 to +6"
    return "> +6"


def fetch_battlelog(
    tag: str,
    token: str,
    base_url: str,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/players/{api_tag(tag)}/battlelog"

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Clash Royale API returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(
            "Unexpected battlelog response: expected JSON array."
        )

    return data


def battle_to_record(
    battle: dict[str, Any],
    player_tag: str,
) -> dict[str, Any] | None:
    # Exact Ladder-only filter.
    if (battle.get("gameMode") or {}).get("name") != "Ladder":
        return None

    team = battle.get("team") or []
    opponent = battle.get("opponent") or []

    if len(team) != 1 or len(opponent) != 1:
        return None

    player = team[0]
    enemy = opponent[0]

    trophy_change = player.get("trophyChange")

    if trophy_change is None:
        return None

    if trophy_change > 0:
        result = "W"
    elif trophy_change < 0:
        result = "L"
    else:
        return None

    opponent_tag = str(enemy.get("tag", "")).strip()

    if not opponent_tag:
        return None

    _, p_levels, _, _ = extract_deck(player)
    _, o_levels, _, _ = extract_deck(enemy)

    player_deck_vector = sorted(p_levels)
    opponent_deck_vector = sorted(o_levels)

    LH_difference = [
        opponent_deck_vector[i] - player_deck_vector[i]
        for i in range(8)
    ]

    player_adsi = calculate_adsi(player_deck_vector)
    opponent_adsi = calculate_adsi(opponent_deck_vector)
    adsi_difference = opponent_adsi - player_adsi

    H, P, S, LH = calculate_lh(
        player_deck_vector,
        opponent_deck_vector,
    )

    # Trophies AFTER this battle.
    post_battle_trophies = (
        int(player["startingTrophies"]) + int(player["trophyChange"])
    )

    return {
        "player_tag": player_tag,
        "player_name": str(player.get("name", "")),
        "opponent_tag": opponent_tag,
        "result": result,
        "player_deck_vector": player_deck_vector,
        "opponent_deck_vector": opponent_deck_vector,
        "LH_difference": LH_difference,
        "player_ADSI": player_adsi,
        "opponent_ADSI": opponent_adsi,
        "ADSI_difference": adsi_difference,
        "H": H,
        "P": P,
        "S": S,
        "LH": LH,
        "LH_band": get_lh_band(LH),
        "player_trophies": post_battle_trophies,
    }


def sqlite_object_exists(
    conn: sqlite3.Connection,
    name: str,
) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE name = ? LIMIT 1",
            (name,),
        ).fetchone()
        is not None
    )


def archive_old_battles_table(conn: sqlite3.Connection) -> str | None:
    """
    Archive an incompatible old battles table under a collision-free name.

    This is required because the old schema cannot be converted into the new
    opponent-tag identity model: it did not store opponent_tag.
    """
    if not sqlite_object_exists(conn, "battles"):
        return None

    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(battles)").fetchall()
    }

    required = {
        "opponent_tag",
        "player_ADSI",
        "opponent_ADSI",
        "ADSI_difference",
        "player_trophies",
    }

    if required.issubset(columns):
        return None

    suffix = 0
    while True:
        name = (
            "battles_legacy"
            if suffix == 0
            else f"battles_legacy_{suffix}"
        )

        if not sqlite_object_exists(conn, name):
            break

        suffix += 1

    conn.execute(
        f'ALTER TABLE battles RENAME TO "{name}"'
    )
    conn.commit()

    return name


def connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    archived = archive_old_battles_table(conn)

    if archived:
        print(
            f"Existing incompatible battles table archived as: {archived}"
        )

    conn.executescript(SCHEMA)
    conn.commit()

    return conn


def insert_records(
    conn: sqlite3.Connection,
    records: list[dict[str, Any]],
) -> int:
    inserted = 0

    if records:
        player_tag = records[0]["player_tag"]
        row = conn.execute(
            "SELECT COALESCE(MAX(chronology_id), 0) "
            "FROM battles WHERE player_tag = ?",
            (player_tag,),
        ).fetchone()
        next_chronology = int(row[0]) + 1
    else:
        next_chronology = 1

    for record in reversed(records):
        chronology_id = next_chronology

        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO battles (
                chronology_id,
                player_tag,
                player_name,
                opponent_tag,
                result,
                player_deck_vector,
                opponent_deck_vector,
                LH_difference,
                player_ADSI,
                opponent_ADSI,
                ADSI_difference,
                H,
                P,
                S,
                LH,
                LH_band,
                player_trophies
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chronology_id,
                record["player_tag"],
                record["player_name"],
                record["opponent_tag"],
                record["result"],
                json.dumps(
                    record["player_deck_vector"],
                    separators=(",", ":"),
                ),
                json.dumps(
                    record["opponent_deck_vector"],
                    separators=(",", ":"),
                ),
                json.dumps(
                    record["LH_difference"],
                    separators=(",", ":"),
                ),
                record["player_ADSI"],
                record["opponent_ADSI"],
                record["ADSI_difference"],
                record["H"],
                record["P"],
                record["S"],
                record["LH"],
                record["LH_band"],
                record["player_trophies"],
            ),
        )

        if cursor.rowcount == 1:
            inserted += 1
            next_chronology += 1

    conn.commit()
    return inserted


def decode_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)

    for key in (
        "player_deck_vector",
        "opponent_deck_vector",
        "LH_difference",
    ):
        data[key] = json.loads(data[key])

    return data


def latest_battles(
    conn: sqlite3.Connection,
    player_tag: str,
    n: int,
) -> list[dict[str, Any]]:
    # API battlelog is newest -> oldest. New rows are inserted in that order,
    # therefore smaller battle_id means newer battle for each fetch.
    rows = conn.execute(
        """
        SELECT *
        FROM battles
        WHERE player_tag = ?
        ORDER BY battle_id ASC
        LIMIT ?
        """,
        (player_tag, n),
    ).fetchall()

    return [decode_row(row) for row in rows]


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("Median requires at least one value.")

    ordered = sorted(values)
    n = len(ordered)

    if n % 2:
        return ordered[n // 2]

    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0


def print_analysis(
    battles: list[dict[str, Any]],
    player_tag: str,
) -> None:
    print()
    print("=" * 72)

    if not battles:
        print(f"CLASH ROYALE ANALYSIS — {player_tag}")
        print("=" * 72)
        print("No stored Ladder battles found.")
        return

    print(
        f"CLASH ROYALE ANALYSIS — "
        f"{battles[0]['player_name']} ({player_tag})"
    )
    print("=" * 72)

    wins = [b for b in battles if b["result"] == "W"]
    losses = [b for b in battles if b["result"] == "L"]

    lh_values = [float(b["LH"]) for b in battles]
    adsi_diff_values = [
        float(b["ADSI_difference"]) for b in battles
    ]

    print(f"Battles analyzed: {len(battles)}")
    print(f"Wins:             {len(wins)}")
    print(f"Losses:           {len(losses)}")
    print(f"Win rate:         {len(wins) / len(battles):.1%}")

    latest = battles[0]

    print()
    print("Latest Ladder battle")
    print(f"  ADSI:            {latest['player_ADSI']:.2f}")
    print(f"  Trophies:        {latest['player_trophies']}")
    print(f"  Opponent tag:    {latest['opponent_tag']}")

    print()
    print("ADSI_difference statistics")
    print(
        f"  Mean:            "
        f"{sum(adsi_diff_values) / len(adsi_diff_values):.3f}"
    )
    print(f"  Median:          {median(adsi_diff_values):.3f}")

    last_10 = battles[:10]
    last_10_adsi_diff = [
        float(b["ADSI_difference"]) for b in last_10
    ]

    last_10_lh = [float(b["LH"]) for b in last_10]

    print()
    print("LH statistics — last 10 Ladder matches")
    print(f"  Mean:            {sum(last_10_lh) / len(last_10_lh):.3f}")
    print(f"  Median:          {median(last_10_lh):.3f}")
    print(f"  Minimum:         {min(last_10_lh):.3f}")
    print(f"  Maximum:         {max(last_10_lh):.3f}")

    print()
    print("LH statistics")
    print(f"  Mean:            {sum(lh_values) / len(lh_values):.3f}")
    print(f"  Median:          {median(lh_values):.3f}")
    print(f"  Minimum:         {min(lh_values):.3f}")
    print(f"  Maximum:         {max(lh_values):.3f}")

    print()
    print("LH-band performance")

    for band in BANDS:
        band_rows = [b for b in battles if b["LH_band"] == band]
        band_wins = sum(b["result"] == "W" for b in band_rows)
        band_losses = sum(b["result"] == "L" for b in band_rows)
        total = len(band_rows)

        wr = band_wins / total if total else 0.0
        lr = band_losses / total if total else 0.0

        print(
            f"  {band:10s}: "
            f"{band_wins}W / {band_losses}L — "
            f"{wr:.1%} WR — {lr:.1%} LR"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clash Royale Ladder analyzer using SQLite."
    )

    parser.add_argument(
        "tag",
        help="Clash Royale player tag, e.g. #822JCG2YL",
    )

    parser.add_argument(
        "--last",
        type=int,
        default=30,
        help="Latest stored battles to analyze, 1-30. Default: 30.",
    )

    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not call the API; analyze existing SQLite data.",
    )

    args = parser.parse_args()

    if not 1 <= args.last <= 30:
        parser.error("--last must be between 1 and 30.")

    tag = normalize_tag(args.tag)

    db_path = os.getenv(
        "CR_SQLITE_DB",
        os.path.join(os.getcwd(), "clash_royale.db"),
    )

    conn = connect_db(db_path)

    try:
        if not args.no_fetch:
            token = os.getenv("CR_API_TOKEN")

            if not token:
                print(
                    "ERROR: CR_API_TOKEN environment variable is not set.",
                    file=sys.stderr,
                )
                return 2

            base_url = os.getenv(
                "CR_API_BASE_URL",
                "https://proxy.royaleapi.dev/v1",
            )

            print(f"Fetching battlelog for {tag}...")

            try:
                battlelog = fetch_battlelog(
                    tag,
                    token,
                    base_url,
                )
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1

            records = []
            non_ladder = 0
            invalid = 0

            for battle in battlelog:
                if (
                    battle.get("gameMode") or {}
                ).get("name") != "Ladder":
                    non_ladder += 1
                    continue

                try:
                    record = battle_to_record(battle, tag)
                except (KeyError, TypeError, ValueError) as exc:
                    invalid += 1
                    print(
                        f"Skipping malformed Ladder battle: {exc}",
                        file=sys.stderr,
                    )
                    continue

                if record is None:
                    invalid += 1
                else:
                    records.append(record)

            inserted = insert_records(conn, records)

            print(f"API battles received:       {len(battlelog)}")
            print(f"Non-Ladder discarded:       {non_ladder}")
            print(f"Invalid/incomplete skipped: {invalid}")
            print(f"Ladder records found:       {len(records)}")
            print(f"New rows inserted:          {inserted}")
            print(f"SQLite database:             {db_path}")

            # The API response is newest -> oldest.
            # Analyze this fetch in that exact order.
            battles = records[:args.last]

        else:
            battles = latest_battles(
                conn,
                tag,
                args.last,
            )

        print_analysis(battles, tag)

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
