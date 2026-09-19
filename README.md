# Clash Royale Personal Performance Analyzer

A local **Clash Royale Ladder analysis system** that collects battle logs from the Clash Royale API, stores them in SQLite, calculates deck-strength and level-handicap metrics, and provides an interactive Streamlit dashboard.

The project is designed for personal performance analysis, with an emphasis on comparing deck levels and battle outcomes.

---

## Features

### Battle collection

- Fetches a player's battle log from the Clash Royale API.
- Processes **Ladder** battles only.
- Ignores non-Ladder and incomplete/malformed battles.
- Stores processed battles in SQLite.
- Prevents duplicate records using the database uniqueness constraint.
- Supports analyzing the most recent 1–30 battles.

### Deck normalization

Card levels are converted into normalized displayed levels using rarity offsets:

| Rarity | Offset |
|---|---:|
| Common | +0 |
| Rare | +2 |
| Epic | +5 |
| Legendary | +8 |
| Champion | +10 |

The numerical deck vectors are sorted before ADSI and LH calculations.

The analyzer also preserves detailed deck information in the **original API card order**, including Evolution and Hero status.

### Evolution and Hero tracking

The current deck representation records:

```text
slot
name
level
has_evolution
has_hero
evolution_active
hero_active
```

Special slots are interpreted as:

| API slot | Interpretation |
|---|---|
| 1 | Evolution slot |
| 2 | Hero slot |
| 3 | Hybrid slot — Evolution preferred, otherwise Hero |
| 4–8 | Normal slots |

Capability is determined from the API icon URLs:

```text
evolutionMedium → Evolution capability
heroMedium      → Hero capability
```

`evolutionLevel` is deliberately not used.

This produces two complementary representations:

- **Deck vectors** — normalized, sorted numerical levels used by ADSI/LH.
- **Deck info** — original API order with card and Evolution/Hero metadata.

---

## ADSI — Absolute Deck Strength Index

For sorted normalized levels \(L_1,\ldots,L_8\):

\[
x_i = \frac{L_i-1}{15}
\]

\[
w_i = \frac{i}{36}
\]

\[
ADSI = 100\sum_{i=1}^{8}w_i x_i
\]

The analyzer also records:

\[
ADSI_{difference} =
ADSI_{opponent} - ADSI_{player}
\]

A positive ADSI difference therefore indicates a higher opponent ADSI.

---

## LH — Level Handicap

For sorted player levels \(y_i\) and opponent levels \(o_i\):

\[
d_i=o_i-y_i
\]

The base pressure function is:

\[
g(d)=
\begin{cases}
d, & d\leq2\\
2+1.5(d-2), & d>2
\end{cases}
\]

Opponent-card level multipliers:

| Opponent level | Weight |
|---|---:|
| ≤ 12 | 1.00 |
| 13 | 1.10 |
| 14 | 1.25 |
| 15 | 1.50 |
| 16+ | 1.80 |

The analyzer calculates:

\[
P=\sum |g(d_i)| \quad \text{for }d_i<0
\]

\[
H=\sum g(d_i)w(o_i) \quad \text{for }d_i>0
\]

\[
S=g(o_8-y_8)w(o_8)
\]

and:

\[
LH=H-P+0.25S
\]

### LH bands

```text
< -3
-3 to -1
-1 to +1
+1 to +3
+3 to +6
> +6
```

---

# Project structure

```text
clash_royale_analytics/
├── analyser.py
├── dashboard.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── LICENSE
└── clash_royale.db
```

### `analyser.py`

The command-line collector and analyzer.

It:

1. Fetches the battle log.
2. Keeps Ladder battles.
3. Extracts deck information.
4. Normalizes card levels.
5. Calculates ADSI.
6. Calculates LH.
7. Stores the battle in SQLite.
8. Prints analysis statistics.

### `dashboard.py`

The Streamlit interface for exploring stored battles.

It provides:

- Player selection
- Recent-match window
- Match/win/loss statistics
- Win rate
- Trophy progression
- LH progression
- ADSI difference progression
- LH vs. result
- ADSI difference vs. result
- LH-band performance
- Summary statistics
- Battle records

The dashboard is read-only and does not modify the SQLite database.

---

# Installation

## Clone the repository

```bash
git clone https://github.com/JournalKenobi11/clash_royale_analytics.git
cd clash_royale_analytics
```

## Create a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

## Install dependencies

```bash
pip install -r requirements.txt
```

---

# Configuration

Configuration is kept outside the Python source code in `.env`.

Copy the example:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
CR_API_TOKEN=YOUR_CLASH_ROYALE_API_TOKEN
CR_API_BASE_URL=https://proxy.royaleapi.dev/v1
CR_SQLITE_DB=./clash_royale.db
```

The analyzer reads these values through centralized configuration helpers.

| Variable | Required | Description |
|---|---|---|
| `CR_API_TOKEN` | Yes* | Clash Royale API token |
| `CR_API_BASE_URL` | No | API base URL |
| `CR_SQLITE_DB` | No | SQLite database path |

\* Required only when fetching from the API.

The analyzer and dashboard can therefore point to the same SQLite database without hardcoding a machine-specific path.

---

# Usage

## Analyze a player

```bash
python3 analyser.py "#822JCG2YL"
```

Default analysis window:

```text
30 battles
```

## Analyze a specific number of battles

```bash
python3 analyser.py "#822JCG2YL" --last 15
```

Valid values:

```text
1–30
```

## Analyze existing database data

```bash
python3 analyser.py "#822JCG2YL" --no-fetch
```

This does not make an API request.

---

# Dashboard

Start Streamlit:

```bash
streamlit run dashboard.py
```

The dashboard reads the SQLite database configured by:

```env
CR_SQLITE_DB=./clash_royale.db
```

---

# Database

The project uses SQLite with a main table named:

```text
battles
```

Important fields:

```text
battle_id
chronology_id
player_tag
player_name
opponent_tag
result
player_deck_vector
opponent_deck_vector
player_deck_info
opponent_deck_info
LH_difference
player_ADSI
opponent_ADSI
ADSI_difference
H
P
S
LH
LH_band
player_trophies
```

### Battle identity

The current database uses:

```text
(player_tag, opponent_tag)
```

as the uniqueness constraint.

`battle_id` is the SQLite row ID.

`chronology_id` represents the chronological position of battles for a player.

### Deck storage

The database intentionally stores both:

```text
player_deck_vector
opponent_deck_vector
```

and:

```text
player_deck_info
opponent_deck_info
```

The vectors are normalized numerical representations used for metric calculations.

The deck-info fields preserve API card order and Evolution/Hero metadata for later structural analysis.

---

# Data flow

```text
Clash Royale API
       │
       ▼
   Battle Log
       │
       ▼
 Ladder Filter
       │
       ▼
 Deck Extraction
       │
       ├───────────────┐
       │               │
       ▼               ▼
Normalized         Deck Metadata
Level Vectors      API Card Order
       │               │
       ├───────┐       │
       ▼       ▼       │
     ADSI      LH      │
       │       │       │
       └───┬───┴───────┘
           ▼
       SQLite DB
           │
      ┌────┴────┐
      ▼         ▼
    CLI      Dashboard
```

---

# Design principles

## Ladder only

Only battles where:

```text
gameMode.name == "Ladder"
```

are stored.

## Separate numerical and structural deck representations

The numerical vectors are optimized for deterministic metric calculations.

The deck-info structures preserve the original API order and Evolution/Hero information so future analysis can use card-slot structure without reconstructing it from sorted levels.

## Externalized configuration

Secrets and machine-specific paths are kept outside the Python source code.

Use `.env` locally and keep it out of version control.

## Read-only dashboard

The dashboard only reads the SQLite database. It does not modify stored battles.

---

# Security

Do **not** commit your real `.env` file.

Add:

```gitignore
.env
.venv/
__pycache__/
*.pyc
*.db
*.db-wal
*.db-shm
```

to `.gitignore` if the local database should remain private.

Keep:

```text
.env.example
```

in the repository so other users know which configuration variables are required.

---

# Troubleshooting

## API token error

If you see:

```text
CR_API_TOKEN environment variable is not set.
```

make sure `.env` exists and contains:

```env
CR_API_TOKEN=your_token_here
```

and install:

```bash
pip install -r requirements.txt
```

## Database not found

Check:

```env
CR_SQLITE_DB=./clash_royale.db
```

or specify an absolute path.

Both the analyzer and dashboard should use the same value if they are intended to share a database.

## Existing database has an incompatible schema

The analyzer checks the existing `battles` table before creating the current schema. If the table is incompatible with the current schema, it archives the old table under a collision-free `battles_legacy...` name before creating the current table.

---

# Limitations

- Only Ladder battles are stored.
- The CLI analysis window is limited to 1–30 battles.
- Numerical deck vectors are normalized and sorted for metric calculations.
- Detailed deck information is separately preserved in API card order.
- Evolution/Hero capability is determined from the API icon URLs.
- `evolutionLevel` is not used.
- Card rarity is used during normalization but is not stored as a separate database field.
- The dashboard is read-only.
- API availability and authentication depend on the configured API endpoint and token.

---

# License

This project is licensed under the **Apache License 2.0**.

See the [`LICENSE`](LICENSE) file for the complete license text.

Copyright © 2026 Aashay Kadu.

---

# Third-party software and services

This project uses third-party software and services, each subject to its own license and terms:

- Python
- Requests
- python-dotenv
- Pandas
- Plotly
- Streamlit
- SQLite
- Clash Royale API / configured API proxy

The Apache License 2.0 applies to the original source code of this project. It does not relicense third-party software, trademarks, game assets, or external services.

## Clash Royale / Supercell

This is an independent, community-made analytics project.

It is **not affiliated with, endorsed by, sponsored by, or officially connected to Supercell**.

Clash Royale and Supercell are trademarks of their respective owners. Use of the Clash Royale API is subject to the applicable API/service terms.

---

# Repository

https://github.com/JournalKenobi11/clash_royale_analytics

# Author

**Aashay Kadu**
