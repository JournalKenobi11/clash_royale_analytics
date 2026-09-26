#!/usr/bin/env python3
"""
Clash Royale Ladder analyzer.

The analyser is a silent backend engine.

Usage:
    python3 analyser.py "#822JCG2YL"
    python3 analyser.py "#822JCG2YL" --last 15
    python3 analyser.py "#822JCG2YL" --no-fetch

Configuration is loaded from .env.

Environment variables:
    CR_API_TOKEN      Required when fetching from the API
    CR_API_BASE_URL   Optional; defaults to https://proxy.royaleapi.dev/v1
    CR_SQLITE_DB      Optional; defaults to ./clash_royale.db

Database identity:
    opponent_tag is the unique battle identifier within each player dataset.
    battle_id is only the sequential SQLite row ID.

    player_deck_info / opponent_deck_info preserve API card order and
    record active Evolution/Hero status. evolutionLevel is not used.

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
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


RARITY_OFFSETS = {
    "common": 0,
    "rare": 2,
    "epic": 5,
    "legendary": 8,
    "champion": 10,
}

DEFAULT_API_BASE_URL = "https://proxy.royaleapi.dev/v1"
DEFAULT_DB_PATH = os.path.join(os.getcwd(), "clash_royale.db")


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
    player_deck_info TEXT NOT NULL,
    opponent_deck_info TEXT NOT NULL,
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


def get_db_path() -> str:
    """Return the SQLite path configured through CR_SQLITE_DB."""
    return os.getenv("CR_SQLITE_DB", DEFAULT_DB_PATH)


def get_api_config() -> tuple[str, str]:
    """Return the API token and base URL from the environment."""
    token = os.getenv("CR_API_TOKEN")

    if not token:
        raise RuntimeError(
            "CR_API_TOKEN environment variable is not set."
        )

    base_url = os.getenv(
        "CR_API_BASE_URL",
        DEFAULT_API_BASE_URL,
    )

    return token, base_url


def normalize_tag(tag: str) -> str:
    tag = tag.strip().upper()

    if not tag.startswith("#"):
        tag = "#" + tag

    return tag


def api_tag(tag: str) -> str:
    return requests.utils.quote(
        tag,
        safe="",
    )


def normalize_level(card: dict[str, Any]) -> int:
    rarity = str(card["rarity"]).lower()

    if rarity not in RARITY_OFFSETS:
        raise ValueError(
            f"Unknown rarity: {card.get('rarity')!r}"
        )

    return int(card["level"]) + RARITY_OFFSETS[rarity]


def extract_deck(
    side: dict[str, Any],
) -> tuple[list[int], list[dict[str, Any]]]:
    """
    Extract an 8-card battle deck while preserving API card order.

    Special-form slots:
        cards[0] -> Evolution slot
        cards[1] -> Hero slot
        cards[2] -> Hybrid slot (Evolution preferred)
        cards[3:8] -> normal slots

    Capability is determined from iconUrls:
        evolutionMedium -> Evolution available
        heroMedium      -> Hero available

    evolutionLevel is deliberately not used.
    """
    cards = side.get("cards") or []

    if len(cards) != 8:
        raise ValueError(
            f"Expected exactly 8 cards, got {len(cards)}"
        )

    deck_info = []

    for index, card in enumerate(cards):
        icon_urls = card.get("iconUrls") or {}

        has_evolution = bool(
            icon_urls.get("evolutionMedium")
        )

        has_hero = bool(
            icon_urls.get("heroMedium")
        )

        evolution_active = False
        hero_active = False

        if index == 0:
            evolution_active = has_evolution

        elif index == 1:
            hero_active = has_hero

        elif index == 2:
            if has_evolution:
                evolution_active = True
            elif has_hero:
                hero_active = True

        deck_info.append(
            {
                "slot": index + 1,
                "name": str(card["name"]),
                "level": normalize_level(card),
                "has_evolution": has_evolution,
                "has_hero": has_hero,
                "evolution_active": evolution_active,
                "hero_active": hero_active,
            }
        )

    levels = [
        item["level"]
        for item in deck_info
    ]

    return levels, deck_info


def calculate_adsi(
    levels: list[int],
) -> float:
    """Absolute Deck Strength Index, using the locked formula."""
    if len(levels) != 8:
        raise ValueError(
            "ADSI requires exactly 8 card levels."
        )

    ordered = sorted(levels)

    return 100.0 * sum(
        (i / 36.0) * ((level - 1) / 15.0)
        for i, level in enumerate(
            ordered,
            start=1,
        )
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
    if (
        len(player_levels) != 8
        or len(opponent_levels) != 8
    ):
        raise ValueError(
            "LH requires two 8-card level vectors."
        )

    y = sorted(player_levels)
    o = sorted(opponent_levels)

    d = [
        o[i] - y[i]
        for i in range(8)
    ]

    base = [
        g(x)
        for x in d
    ]

    P = sum(
        abs(base[i])
        for i in range(8)
        if d[i] < 0
    )

    H = sum(
        base[i] * opponent_weight(o[i])
        for i in range(8)
        if d[i] > 0
    )

    S = (
        g(o[7] - y[7])
        * opponent_weight(o[7])
    )

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
    url = (
        f"{base_url.rstrip('/')}"
        f"/players/{api_tag(tag)}/battlelog"
    )

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
            f"Clash Royale API returned HTTP "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(
            "Unexpected battlelog response: "
            "expected JSON array."
        )

    return data


def battle_to_record(
    battle: dict[str, Any],
    player_tag: str,
) -> dict[str, Any] | None:
    # Exact Ladder-only filter.
    if (
        battle.get("gameMode") or {}
    ).get("name") != "Ladder":
        return None

    team = battle.get("team") or []
    opponent = battle.get("opponent") or []

    if len(team) != 1 or len(opponent) != 1:
        return None

    player = team[0]
    enemy = opponent[0]

    trophy_change = player.get(
        "trophyChange"
    )

    if trophy_change is None:
        return None

    if trophy_change > 0:
        result = "W"

    elif trophy_change < 0:
        result = "L"

    else:
        return None

    opponent_tag = str(
        enemy.get("tag", "")
    ).strip()

    if not opponent_tag:
        return None

    player_levels, player_deck_info = extract_deck(
        player
    )

    opponent_levels, opponent_deck_info = extract_deck(
        enemy
    )

    player_deck_vector = sorted(
        player_levels
    )

    opponent_deck_vector = sorted(
        opponent_levels
    )

    LH_difference = [
        opponent_deck_vector[i]
        - player_deck_vector[i]
        for i in range(8)
    ]

    player_adsi = calculate_adsi(
        player_deck_vector
    )

    opponent_adsi = calculate_adsi(
        opponent_deck_vector
    )

    adsi_difference = (
        opponent_adsi
        - player_adsi
    )

    H, P, S, LH = calculate_lh(
        player_deck_vector,
        opponent_deck_vector,
    )

    # Trophies AFTER this battle.
    post_battle_trophies = (
        int(player["startingTrophies"])
        + int(player["trophyChange"])
    )

    return {
        "player_tag": player_tag,
        "player_name": str(
            player.get("name", "")
        ),
        "opponent_tag": opponent_tag,
        "result": result,
        "player_deck_vector": player_deck_vector,
        "opponent_deck_vector": opponent_deck_vector,
        "player_deck_info": player_deck_info,
        "opponent_deck_info": opponent_deck_info,
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
            """
            SELECT 1
            FROM sqlite_master
            WHERE name = ?
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        is not None
    )


def archive_old_battles_table(
    conn: sqlite3.Connection,
) -> str | None:
    """
    Archive an incompatible old battles table under
    a collision-free name.

    This is required because the old schema cannot be
    converted into the new opponent-tag identity model:
    it did not store opponent_tag.
    """
    if not sqlite_object_exists(
        conn,
        "battles",
    ):
        return None

    columns = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(battles)"
        ).fetchall()
    }

    required = {
        "opponent_tag",
        "player_ADSI",
        "opponent_ADSI",
        "ADSI_difference",
        "player_deck_info",
        "opponent_deck_info",
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

        if not sqlite_object_exists(
            conn,
            name,
        ):
            break

        suffix += 1

    conn.execute(
        f'ALTER TABLE battles RENAME TO "{name}"'
    )

    conn.commit()

    return name


def connect_db(
    path: str,
) -> sqlite3.Connection:
    """
    Open SQLite and ensure the current schema exists.

    This function is completely silent.
    """
    conn = sqlite3.connect(path)

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    conn.execute(
        "PRAGMA journal_mode = WAL"
    )

    conn.execute(
        "PRAGMA synchronous = NORMAL"
    )

    archive_old_battles_table(conn)

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
            """
            SELECT COALESCE(MAX(chronology_id), 0)
            FROM battles
            WHERE player_tag = ?
            """,
            (player_tag,),
        ).fetchone()

        next_chronology = (
            int(row[0]) + 1
        )

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
                player_deck_info,
                opponent_deck_info,
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
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
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
                    record["player_deck_info"],
                    separators=(",", ":"),
                ),
                json.dumps(
                    record["opponent_deck_info"],
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


def decode_row(
    row: sqlite3.Row,
) -> dict[str, Any]:
    data = dict(row)

    for key in (
        "player_deck_vector",
        "opponent_deck_vector",
        "player_deck_info",
        "opponent_deck_info",
        "LH_difference",
    ):
        data[key] = json.loads(
            data[key]
        )

    return data


def latest_battles(
    conn: sqlite3.Connection,
    player_tag: str,
    n: int,
) -> list[dict[str, Any]]:
    """
    API battlelog is newest -> oldest.

    New rows are inserted in that order, therefore
    smaller battle_id means newer battle for each fetch.
    """
    rows = conn.execute(
        """
        SELECT *
        FROM battles
        WHERE player_tag = ?
        ORDER BY battle_id ASC
        LIMIT ?
        """,
        (
            player_tag,
            n,
        ),
    ).fetchall()

    return [
        decode_row(row)
        for row in rows
    ]


def analyse_player(
    tag: str,
) -> dict[str, Any]:
    """
    Silent backend engine used by the dashboard.

    Performs:

        API fetch
        -> Ladder filtering
        -> battle processing
        -> SQLite insertion

    Produces no terminal output.
    """
    tag = normalize_tag(tag)

    db_path = get_db_path()

    conn = connect_db(
        db_path,
    )

    try:
        token, base_url = get_api_config()

        battlelog = fetch_battlelog(
            tag,
            token,
            base_url,
        )

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
                record = battle_to_record(
                    battle,
                    tag,
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                invalid += 1
                continue

            if record is None:
                invalid += 1
            else:
                records.append(record)

        inserted = insert_records(
            conn,
            records,
        )

        return {
            "tag": tag,
            "api_battles": len(battlelog),
            "non_ladder": non_ladder,
            "invalid": invalid,
            "ladder_records": len(records),
            "inserted": inserted,
        }

    finally:
        conn.close()


def main() -> int:
    """
    Silent CLI entry point.

    The analyser no longer prints analysis or progress output.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Clash Royale Ladder analyzer "
            "using SQLite."
        )
    )

    parser.add_argument(
        "tag",
        help=(
            "Clash Royale player tag, "
            "e.g. #822JCG2YL"
        ),
    )

    parser.add_argument(
        "--last",
        type=int,
        default=30,
        help=(
            "Latest stored battles to analyze, "
            "1-30. Default: 30."
        ),
    )

    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help=(
            "Do not call the API; analyze "
            "existing SQLite data."
        ),
    )

    args = parser.parse_args()

    if not 1 <= args.last <= 30:
        parser.error(
            "--last must be between 1 and 30."
        )

    tag = normalize_tag(
        args.tag
    )

    db_path = get_db_path()

    conn = connect_db(
        db_path,
    )

    try:
        if not args.no_fetch:
            token, base_url = get_api_config()

            battlelog = fetch_battlelog(
                tag,
                token,
                base_url,
            )

            records = []

            for battle in battlelog:
                if (
                    battle.get("gameMode") or {}
                ).get("name") != "Ladder":
                    continue

                try:
                    record = battle_to_record(
                        battle,
                        tag,
                    )

                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    continue

                if record is not None:
                    records.append(record)

            insert_records(
                conn,
                records,
            )

        else:
            latest_battles(
                conn,
                tag,
                args.last,
            )

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())