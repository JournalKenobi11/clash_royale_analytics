import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import pandas as pd
import plotly.express as px
import streamlit as st

# Configuration is loaded from .env via CR_SQLITE_DB.

DB_PATH = Path(os.getenv("CR_SQLITE_DB", "./clash_royale.db")).expanduser()

st.set_page_config(page_title="Clash Royale Analysis Dashboard", page_icon="CR", layout="wide")
st.title("Clash Royale Analysis Dashboard")
st.caption(f"SQLite database: {DB_PATH}")

if not DB_PATH.exists():
    st.error(f"Database not found: {DB_PATH}")
    st.stop()

@st.cache_data(ttl=5)
def load_data():
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query("""
            SELECT battle_id, chronology_id, player_tag, player_name, opponent_tag, result,
                   player_deck_vector, opponent_deck_vector,
                   player_ADSI, opponent_ADSI, ADSI_difference,
                   H, P, S, LH, LH_band, player_trophies
            FROM battles
            ORDER BY battle_id ASC
        """, con)

try:
    df = load_data()
except Exception as e:
    st.error(f"Could not read battles table: {e}")
    st.stop()

if df.empty:
    st.warning("The battles table is empty.")
    st.stop()

for col in ["battle_id", "chronology_id", "player_ADSI", "opponent_ADSI", "ADSI_difference",
            "H", "P", "S", "LH", "player_trophies"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")


st.sidebar.header("Filters")
players = df[["player_tag", "player_name"]].drop_duplicates("player_tag").sort_values("player_tag")
tags = players["player_tag"].tolist()

def player_label(tag):
    row = players[players["player_tag"] == tag]
    name = row["player_name"].iloc[0] if not row.empty else None
    return f"{name} ({tag})" if pd.notna(name) and name else tag

selected = st.sidebar.selectbox("Player", tags, format_func=player_label)
work = df[df["player_tag"] == selected].copy()

n = len(work)
window = st.sidebar.slider("Recent matches", 1, n, min(30, n))

work = work.sort_values("chronology_id", ascending=True).tail(window).copy()
work["match_number"] = range(1, len(work) + 1)

wins = (work["result"].str.upper() == "W").sum()
losses = (work["result"].str.upper() == "L").sum()
games = wins + losses
wr = 100 * wins / games if games else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Matches", games)
c2.metric("Wins", wins)
c3.metric("Losses", losses)
c4.metric("Win rate", f"{wr:.1f}%")
t = work["player_trophies"].dropna()
c5.metric("Latest trophies", f"{int(t.iloc[-1])}" if not t.empty else "—")

st.divider()

st.subheader("Trophy progression")
x = work.dropna(subset=["player_trophies"])
if not x.empty:
    fig = px.line(x, x="match_number", y="player_trophies", markers=True,
                  labels={"match_number": "Match", "player_trophies": "Trophies"})
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Level Handicap (LH)")
x = work.dropna(subset=["LH"])
if not x.empty:
    fig = px.line(x, x="match_number", y="LH", markers=True,
                  hover_data=["result", "opponent_tag", "LH_band"],
                  labels={"match_number": "Match", "LH": "LH"})
    fig.add_hline(y=0, line_dash="dash")
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("ADSI difference")
x = work.dropna(subset=["ADSI_difference"])
if not x.empty:
    fig = px.line(x, x="match_number", y="ADSI_difference", markers=True,
                  hover_data=["result", "opponent_tag", "player_ADSI", "opponent_ADSI"],
                  labels={"match_number": "Match",
                          "ADSI_difference": "Opponent ADSI − Player ADSI"})
    fig.add_hline(y=0, line_dash="dash")
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Metric vs result")
a, b = st.columns(2)

with a:
    x = work.dropna(subset=["LH"])
    if not x.empty:
        fig = px.box(x, x="result", y="LH", points="all",
                     labels={"result": "Result", "LH": "LH"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

with b:
    x = work.dropna(subset=["ADSI_difference"])
    if not x.empty:
        fig = px.box(x, x="result", y="ADSI_difference", points="all",
                     labels={"result": "Result",
                             "ADSI_difference": "Opponent ADSI − Player ADSI"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

st.subheader("LH-band performance")
bands = ["< -3", "-3 to -1", "-1 to +1", "+1 to +3", "+3 to +6", "> +6"]
band_df = (work.groupby(["LH_band", "result"]).size()
           .unstack(fill_value=0).reindex(bands, fill_value=0))
for r in ["W", "L"]:
    if r not in band_df:
        band_df[r] = 0

fig = px.bar(band_df.reset_index(), x="LH_band", y=["W", "L"], barmode="group",
             labels={"value": "Matches", "LH_band": "LH band", "variable": "Result"})
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Statistics")
a, b = st.columns(2)

with a:
    vals = work["LH"].dropna()
    st.markdown("**LH — selected matches**")
    if vals.empty:
        st.write("No data.")
    else:
        st.dataframe(pd.DataFrame({
            "Statistic": ["Mean", "Median", "Minimum", "Maximum"],
            "LH": [vals.mean(), vals.median(), vals.min(), vals.max()]
        }).round(3), hide_index=True, use_container_width=True)

with b:
    vals = work["ADSI_difference"].dropna()
    st.markdown("**ADSI difference — selected matches**")
    if vals.empty:
        st.write("No data.")
    else:
        st.dataframe(pd.DataFrame({
            "Statistic": ["Mean", "Median"],
            "ADSI difference": [vals.mean(), vals.median()]
        }).round(3), hide_index=True, use_container_width=True)

st.subheader("Battle records")
cols = ["match_number", "battle_id", "result", "player_trophies", "opponent_tag",
        "player_ADSI", "opponent_ADSI", "ADSI_difference", "H", "P", "S",
        "LH", "LH_band", "player_deck_vector", "opponent_deck_vector"]
st.dataframe(work[cols], hide_index=True, use_container_width=True)

st.caption("Read-only dashboard: the SQLite database is not modified.")
