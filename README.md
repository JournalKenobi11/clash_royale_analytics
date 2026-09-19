**# Clash Royale Personal Performance Analyzer**

A local **\*\*Clash Royale Ladder analysis system\*\*** that collects battle logs from the Clash Royale API, stores them in SQLite, calculates deck-strength and level-handicap metrics, and provides an interactive Streamlit dashboard.

The project is designed for personal performance analysis, with an emphasis on comparing deck levels and battle outcomes.

**---**

**## Features**

**### Battle collection**

\- Fetches a player's battle log from the Clash Royale API.

\- Processes **\*\*Ladder\*\*** battles only.

\- Ignores non-Ladder and incomplete/malformed battles.

\- Stores processed battles in SQLite.

\- Prevents duplicate records using the database uniqueness constraint.

\- Supports analyzing the most recent 1–30 battles.

**### Deck normalization**

Card levels are converted into normalized displayed levels using rarity offsets:

\| Rarity | Offset |

\|---|---:|

\| Common | +0 |

\| Rare | +2 |

\| Epic | +5 |

\| Legendary | +8 |

\| Champion | +10 |

The numerical deck vectors are sorted before ADSI and LH calculations.

The analyzer also preserves detailed deck information in the **\*\*original API card order\*\***, including Evolution and Hero status.

**### Evolution and Hero tracking**

The current deck representation records:

\`\`\`text

slot

name

level

has\_evolution

has\_hero

evolution\_active

hero\_active

\`\`\`

Special slots are interpreted as:

\| API slot | Interpretation |

\|---|---|

\| 1 | Evolution slot |

\| 2 | Hero slot |

\| 3 | Hybrid slot — Evolution preferred, otherwise Hero |

\| 4–8 | Normal slots |

Capability is determined from the API icon URLs:

\`\`\`text

evolutionMedium → Evolution capability

heroMedium      → Hero capability

\`\`\`

\`evolutionLevel\` is deliberately not used.

This produces two complementary representations:

\- **\*\*Deck vectors\*\*** — normalized, sorted numerical levels used by ADSI/LH.

\- **\*\*Deck info\*\*** — original API order with card and Evolution/Hero metadata.

**---**

**## ADSI — Absolute Deck Strength Index**

For sorted normalized levels \\(L\_1,\ldots,L\_8\\):

\\[

x\_i = \frac{L\_i-1}{15}

\\]

\\[

w\_i = \frac{i}{36}

\\]

\\[

ADSI = 100\sum\_{i=1}^{8}w\_i x\_i

\\]

The analyzer also records:

\\[

ADSI\_{difference} =

ADSI\_{opponent} - ADSI\_{player}

\\]

A positive ADSI difference therefore indicates a higher opponent ADSI.

**---**

**## LH — Level Handicap**

For sorted player levels \\(y\_i\\) and opponent levels \\(o\_i\\):

\\[

d\_i=o\_i-y\_i

\\]

The base pressure function is:

\\[

g(d)=

\begin{cases}

d, & d\leq2\\\\

2+1.5(d-2), & d>2

\end{cases}

\\]

Opponent-card level multipliers:

\| Opponent level | Weight |

\|---|---:|

\| ≤ 12 | 1.00 |

\| 13 | 1.10 |

\| 14 | 1.25 |

\| 15 | 1.50 |

\| 16+ | 1.80 |

The analyzer calculates:

\\[

P=\sum |g(d\_i)| \quad \text{for }d\_i<0

\\]

\\[

H=\sum g(d\_i)w(o\_i) \quad \text{for }d\_i>0

\\]

\\[

S=g(o\_8-y\_8)w(o\_8)

\\]

and:

\\[

LH=H-P+0.25S

\\]

**### LH bands**

\`\`\`text

< -3

-3 to -1

-1 to +1

+1 to +3

+3 to +6

\> +6

\`\`\`

**---**

**# Project structure**

\`\`\`text

clash\_royale\_analytics/

├── analyser.py

├── tough_cards.py

├── dashboard.py

├── requirements.txt

├── .env.example

├── .gitignore

├── README.md

├── LICENSE

└── clash\_royale.db

\`\`\`

**### \`analyser.py\`**

The command-line collector and analyzer.

It:

1\. Fetches the battle log.

2\. Keeps Ladder battles.

3\. Extracts deck information.

4\. Normalizes card levels.

5\. Calculates ADSI.

6\. Calculates LH.

7\. Stores the battle in SQLite.

8\. Prints analysis statistics.

**### \`tough_cards.py\`**

A standalone command-line analysis of opponent cards associated with the player's losses.

It:

- Reads the existing \`battles\` table from SQLite.
- Uses \`opponent_deck_info\`.
- Counts card encounters.
- Counts losses associated with each opponent card.
- Calculates card loss rates.
- Tracks Hero, Evolution, and Normal forms.
- Uses Evo > Hero > Normal active-form precedence.
- Produces Top 5 cards by losses.
- Produces Top 5 cards by loss rate.
- Supports the existing \`--db\` database-path option.
- Supports the existing \`--min-encounters\` threshold for the loss-rate ranking.
- Does not fetch new battles or modify the database.

**### \`dashboard.py\`**

The Streamlit interface for exploring stored battles.

It provides:

\- Player selection

\- Recent-match window

\- Match/win/loss statistics

\- Win rate

\- Trophy progression

\- LH progression

\- ADSI difference progression

\- LH vs. result

\- ADSI difference vs. result

\- LH-band performance

\- Summary statistics

\- Battle records

The dashboard is read-only and does not modify the SQLite database.

**---**

**# Installation**

**## Clone the repository**

\`\`\`bash

git clone https\://github.com/JournalKenobi11/clash\_royale\_analytics.git

cd clash\_royale\_analytics

\`\`\`

**## Create a virtual environment**

Linux/macOS:

\`\`\`bash

python3 -m venv .venv

source .venv/bin/activate

\`\`\`

Windows:

\`\`\`powershell

python -m venv .venv

.venv\Scripts\activate

\`\`\`

**## Install dependencies**

\`\`\`bash

pip install -r requirements.txt

\`\`\`

**---**

**# Configuration**

Configuration is kept outside the Python source code in \`.env\`.

Copy the example:

\`\`\`bash

cp .env.example .env

\`\`\`

Then edit \`.env\`:

\`\`\`env

CR\_API\_TOKEN=YOUR\_CLASH\_ROYALE\_API\_TOKEN

CR\_API\_BASE\_URL=https\://proxy.royaleapi.dev/v1

CR\_SQLITE\_DB=./clash\_royale.db

\`\`\`

The analyzer reads these values through centralized configuration helpers.

\| Variable | Required | Description |

\|---|---|---|

\| \`CR\_API\_TOKEN\` | Yes\* | Clash Royale API token |

\| \`CR\_API\_BASE\_URL\` | No | API base URL |

\| \`CR\_SQLITE\_DB\` | No | SQLite database path |

\\\* Required only when fetching from the API.

The analyzer and dashboard can therefore point to the same SQLite database without hardcoding a machine-specific path.

**---**

**# Usage**

**## Analyze a player**

\`\`\`bash

python3 analyser.py "#822JCG2YL"

\`\`\`

Default analysis window:

\`\`\`text

30 battles

\`\`\`

**## Analyze a specific number of battles**

\`\`\`bash

python3 analyser.py "#822JCG2YL" --last 15

\`\`\`

Valid values:

\`\`\`text

1–30

\`\`\`

**## Analyze existing database data**

\`\`\`bash

python3 analyser.py "#822JCG2YL" --no-fetch

\`\`\`

This does not make an API request.

**---

# Opponent card loss analysis

Run:

```bash
python3 tough_cards.py "#822JCG2YL"
```

The existing `--db` option overrides the SQLite database path:

```bash
python3 tough_cards.py "#822JCG2YL" --db ./clash_royale.db
```

By default, the database path is taken from `CR_SQLITE_DB`, falling back to `clash_royale.db`.

The existing `--min-encounters` option controls the minimum number of encounters required for the loss-rate ranking:

```bash
python3 tough_cards.py "#822JCG2YL" --min-encounters 3
```

Default:

```text
1
```

Both options can be used together:

```bash
python3 tough_cards.py "#822JCG2YL" --db ./clash_royale.db --min-encounters 3
```

The script reports:

```text
TOP 5 CARDS BY LOSSES
TOP 5 CARDS BY LOSS RATE
```

For each applicable card, Hero and Evolution form statistics are also shown.

**---

**# Dashboard**

Start Streamlit:

\`\`\`bash

streamlit run dashboard.py

\`\`\`

The dashboard reads the SQLite database configured by:

\`\`\`env

CR\_SQLITE\_DB=./clash\_royale.db

\`\`\`

**---**

**# Database**

The project uses SQLite with a main table named:

\`\`\`text

battles

\`\`\`

Important fields:

\`\`\`text

battle\_id

chronology\_id

player\_tag

player\_name

opponent\_tag

result

player\_deck\_vector

opponent\_deck\_vector

player\_deck\_info

opponent\_deck\_info

LH\_difference

player\_ADSI

opponent\_ADSI

ADSI\_difference

H

P

S

LH

LH\_band

player\_trophies

\`\`\`

**### Battle identity**

The current database uses:

\`\`\`text

(player\_tag, opponent\_tag)

\`\`\`

as the uniqueness constraint.

\`battle\_id\` is the SQLite row ID.

\`chronology\_id\` represents the chronological position of battles for a player.

**### Deck storage**

The database intentionally stores both:

\`\`\`text

player\_deck\_vector

opponent\_deck\_vector

\`\`\`

and:

\`\`\`text

player\_deck\_info

opponent\_deck\_info

\`\`\`

The vectors are normalized numerical representations used for metric calculations.

The deck-info fields preserve API card order and Evolution/Hero metadata for later structural analysis.

**---**

**# Data flow**

\`\`\`text

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

       │               │

       ▼               ▼

Normalized         Deck Metadata

Level Vectors      API Card Order

       │               │

       ├───────┐       │

       ▼       ▼       │

     ADSI      LH      │

       │       │       │

       └───┬───┴───────┘

           ▼

       SQLite DB

           │

      ┌────┴────┐

      ▼         ▼

    CLI      Dashboard

\`\`\`

**---**

**# Design principles**

**## Ladder only**

Only battles where:

\`\`\`text

gameMode.name == "Ladder"

\`\`\`

are stored.

**## Separate numerical and structural deck representations**

The numerical vectors are optimized for deterministic metric calculations.

The deck-info structures preserve the original API order and Evolution/Hero information so future analysis can use card-slot structure without reconstructing it from sorted levels.

**## Externalized configuration**

Secrets and machine-specific paths are kept outside the Python source code.

Use \`.env\` locally and keep it out of version control.

**## Read-only dashboard**

The dashboard only reads the SQLite database. It does not modify stored battles.

**---**

**# Security**

Do **\*\*not\*\*** commit your real \`.env\` file.

Add:

\`\`\`gitignore

.env

.venv/

\_\_pycache\_\_/

\*.pyc

\*.db

\*.db-wal

\*.db-shm

\`\`\`

to \`.gitignore\` if the local database should remain private.

Keep:

\`\`\`text

.env.example

\`\`\`

in the repository so other users know which configuration variables are required.

**---**

**# Troubleshooting**

**## API token error**

If you see:

\`\`\`text

CR\_API\_TOKEN environment variable is not set.

\`\`\`

make sure \`.env\` exists and contains:

\`\`\`env

CR\_API\_TOKEN=your\_token\_here

\`\`\`

and install:

\`\`\`bash

pip install -r requirements.txt

\`\`\`

**## Database not found**

Check:

\`\`\`env

CR\_SQLITE\_DB=./clash\_royale.db

\`\`\`

or specify an absolute path.

Both the analyzer and dashboard should use the same value if they are intended to share a database.

**## Existing database has an incompatible schema**

The analyzer checks the existing \`battles\` table before creating the current schema. If the table is incompatible with the current schema, it archives the old table under a collision-free \`battles\_legacy...\` name before creating the current table.

**---**

**# Limitations**

\- Only Ladder battles are stored.

\- The CLI analysis window is limited to 1–30 battles.

\- Numerical deck vectors are normalized and sorted for metric calculations.

\- Detailed deck information is separately preserved in API card order.

\- Evolution/Hero capability is determined from the API icon URLs.

\- \`evolutionLevel\` is not used.

\- Card rarity is used during normalization but is not stored as a separate database field.

\- The dashboard is read-only.

\- API availability and authentication depend on the configured API endpoint and token.

**---**

**# License**

This project is licensed under the **\*\*Apache License 2.0\*\***.

See the [\`LICENSE\`]\(LICENSE) file for the complete license text.

Copyright © 2026 Aashay Kadu.

**---**

**# Third-party software and services**

This project uses third-party software and services, each subject to its own license and terms:

\- Python

\- Requests

\- python-dotenv

\- Pandas

\- Plotly

\- Streamlit

\- SQLite

\- Clash Royale API / configured API proxy

The Apache License 2.0 applies to the original source code of this project. It does not relicense third-party software, trademarks, game assets, or external services.

**## Clash Royale / Supercell**

This is an independent, community-made analytics project.

It is **\*\*not affiliated with, endorsed by, sponsored by, or officially connected to Supercell\*\***.

Clash Royale and Supercell are trademarks of their respective owners. Use of the Clash Royale API is subject to the applicable API/service terms.

**---**

**# Repository**

https\://github.com/JournalKenobi11/clash\_royale\_analytics

**# Author**

**\*\*Aashay Kadu\*\***