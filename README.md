# Clash Royale Personal Performance Analyzer

A local **Clash Royale Ladder analysis system** that collects battle logs from the Clash Royale API, stores them in SQLite, calculates deck-strength and level-handicap metrics, and provides an interactive Streamlit dashboard.

The project is designed for personal performance analysis rather than generic player ranking. It focuses on answering questions such as:

- How strong is my deck relative to my opponents?
- How much level pressure did I face?
- How does Level Handicap (LH) relate to wins and losses?
- How does my deck strength compare with my opponents?
- How has my trophy count changed across recent matches?

---

## Features

### Battle collection

- Fetches a player's battle log from the Clash Royale API.
- Processes **Ladder** battles only.
- Ignores non-Ladder and incomplete/malformed battles.
- Stores processed battles in SQLite.
- Prevents duplicate opponent records using the database uniqueness constraint.
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

The resulting eight card levels are sorted before the deck metrics are calculated.

### ADSI — Absolute Deck Strength Index

ADSI is an absolute deck-strength metric based on normalized card levels and their ordered positions in the deck.

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

The system also records:

\[
ADSI_{difference} =
ADSI_{opponent} - ADSI_{player}
\]

A positive ADSI difference therefore means the opponent's deck has a higher ADSI.

### LH — Level Handicap

LH measures the level-pressure relationship between the player's deck and the opponent's deck.

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

Opponent-card level multipliers are:

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

and finally:

\[
LH=H-P+0.25S
\]

### LH bands

The dashboard and CLI classify LH into:

| Band |
|---|
| `< -3` |
| `-3 to -1` |
| `-1 to +1` |
| `+1 to +3` |
| `+3 to +6` |
| `> +6` |

---

## Project structure

```text
.
├── analyser.py
├── dashboard.py
├── .env
├── .env.example
├── clash_royale.db
└── README.md
```

### `analyser.py`

Command-line analyzer and API collector.

It:

1. Fetches the player's battle log.
2. Keeps Ladder battles.
3. Normalizes card levels.
4. Calculates ADSI.
5. Calculates LH.
6. Stores the result in SQLite.
7. Prints a statistical summary.

### `dashboard.py`

Streamlit dashboard for exploring the stored battles.

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
- Battle-level records

The dashboard is read-only and does not modify the SQLite database.

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/JournalKenobi11/clash_royale_analytics.git
cd <your-repository-directory>
```

## 2. Create a virtual environment

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

## 3. Install dependencies

```bash
pip install requests python-dotenv pandas plotly streamlit
```

---

# Configuration

Configuration is kept outside the Python source code in a `.env` file.

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

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `CR_API_TOKEN` | Yes* | Clash Royale API token |
| `CR_API_BASE_URL` | No | Clash Royale API base URL |
| `CR_SQLITE_DB` | No | SQLite database path |

\* `CR_API_TOKEN` is only required when running the analyzer without `--no-fetch`.

For example, to use a database stored elsewhere:

```env
CR_SQLITE_DB=/home/user/clash_api_dump/clash_royale.db
```

Both the analyzer and dashboard use this same variable, so they can operate on the same database.

---

# Usage

## Analyze a player

```bash
python3 analyser.py "#822JCG2YL"
```

The analyzer will:

- fetch the battle log,
- process Ladder battles,
- insert new records,
- and analyze the requested number of recent battles.

The default is **30 battles**.

## Analyze a different number of battles

```bash
python3 analyser.py "#822JCG2YL" --last 15
```

Valid values are:

```text
1–30
```

## Analyze existing database data without calling the API

```bash
python3 analyser.py "#822JCG2YL" --no-fetch
```

This is useful when:

- the API is unavailable,
- you want to avoid another API request,
- or you want to analyze already collected battles.

---

# Dashboard

Start Streamlit with:

```bash
streamlit run dashboard.py
```

Then open the local Streamlit URL shown in the terminal.

The dashboard automatically reads the SQLite database configured through:

```env
CR_SQLITE_DB=./clash_royale.db
```

## Dashboard controls

### Player

Select one of the player tags present in the database.

### Recent matches

Choose how many recent battles to display.

The dashboard orders battles using `chronology_id` for the selected player.

---

# Database

The project uses SQLite.

The main table is:

```text
battles
```

Important fields include:

```text
battle_id
chronology_id
player_tag
player_name
opponent_tag
result
player_deck_vector
opponent_deck_vector
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

The database uses:

```text
(player_tag, opponent_tag)
```

as the uniqueness constraint for stored battle records.

`battle_id` is the SQLite sequential row ID.

`chronology_id` represents the chronological position of battles for a player.

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
Card Level Normalization
       │
       ├──────────────┐
       ▼              ▼
     ADSI             LH
       │              │
       └──────┬───────┘
              ▼
          SQLite DB
              │
       ┌──────┴──────┐
       ▼             ▼
   CLI Analyzer   Streamlit
                    Dashboard
```

---

# Example analyzer output

A typical analysis contains:

```text
CLASH ROYALE ANALYSIS — Player Name (#PLAYER_TAG)
========================================================================

Battles analyzed: 30
Wins:             20
Losses:           10
Win rate:         66.7%

Latest Ladder battle
  ADSI:            72.31
  Trophies:        10234
  Opponent tag:    #XXXXXXXX

ADSI_difference statistics
  Mean:            1.842
  Median:          1.500

LH statistics — last 10 Ladder matches
  Mean:            2.763
  Median:          2.500
  Minimum:         -6.000
  Maximum:         12.350
```

The exact values depend on the stored battle data.

---

# Design principles

## Ladder only

Only battles where:

```text
gameMode.name == "Ladder"
```

are processed.

Other game modes are discarded.

## No API data is required by the dashboard

The dashboard operates entirely from SQLite. Once battles have been collected, the dashboard does not need to call the Clash Royale API.

## Configuration is externalized

Secrets and machine-specific paths are not embedded in the source code.

Use `.env` for local configuration and keep it out of version control.

---

# Security

Do **not** commit your real `.env` file.

Add this to `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.pyc
```

The repository should contain:

```text
.env.example
```

but not:

```text
.env
```

Your real API token should only exist in your local environment or another secure secret-management system.

---

# Troubleshooting

## `CR_API_TOKEN environment variable is not set`

Make sure `.env` exists in the directory from which the script is being run and contains:

```env
CR_API_TOKEN=your_token_here
```

Also make sure `python-dotenv` is installed:

```bash
pip install python-dotenv
```

## Database not found

Check:

```env
CR_SQLITE_DB=./clash_royale.db
```

or provide the full path:

```env
CR_SQLITE_DB=/path/to/clash_royale.db
```

The analyzer and dashboard must point to the same database if you want the dashboard to display the analyzer's collected data.

## Want to inspect existing data only?

Use:

```bash
python3 analyser.py "#YOURTAG" --no-fetch
```

This prevents an API request and analyzes the existing SQLite data.

---

# Limitations

The current system is intentionally focused on the data and metrics implemented by the analyzer.

In particular:

- Only Ladder battles are stored.
- The analysis window exposed by the CLI is 1–30 battles.
- Deck vectors are stored as normalized, sorted level vectors rather than full card metadata.
- The current database schema does not store card rarity separately.
- The dashboard is read-only.
- API availability and authentication depend on the configured Clash Royale API endpoint and token.

---

# License

This project is licensed under the **Apache License 2.0**.

See the [`LICENSE`](LICENSE) file for the complete license text.

Copyright © 2026 Aashay Kadu

---

# Author

**Aashay Kadu**

Built as a personal Clash Royale performance-analysis project using Python, SQLite, Pandas, Plotly, Streamlit, and the Clash Royale API.


---

# Repository

Source code:

https://github.com/JournalKenobi11/clash_royale_analytics

---

# Third-party software and services

This project uses third-party software and services, each of which remains subject to its own license and terms:

- **Python** — programming language/runtime
- **Requests** — HTTP client
- **python-dotenv** — environment-variable configuration
- **Pandas** — data processing
- **Plotly** — data visualization
- **Streamlit** — dashboard framework
- **SQLite** — database engine
- **Clash Royale API / RoyaleAPI proxy** — external API service

The Apache License 2.0 in this repository applies to the original source code of this project. It does not relicense third-party software, trademarks, game assets, or external services.

## Clash Royale / Supercell

This is an independent, community-made analytics project.

It is **not affiliated with, endorsed by, sponsored by, or officially connected to Supercell**.

Clash Royale and Supercell are trademarks of their respective owners. Use of the Clash Royale API is subject to the applicable API/service terms.
