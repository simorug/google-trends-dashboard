import os
import io
import pandas as pd
import streamlit as st
import plotly.express as px

# Configurazione pagina
st.set_page_config(page_title="TrendVision Analytics", page_icon="📊", layout="wide")

st.title("📊 TrendVision Analytics")
st.caption("Dashboard portfolio — analisi interesse nel tempo (Google Trends).")

# ----------------------------
# Utility: lettura robusta CSV
# ----------------------------
def load_trends_csv(file_like_or_path: str | io.BytesIO) -> pd.DataFrame:
    """
    Legge CSV di Google Trends anche se contiene righe iniziali tipo 'Categoria: ...'
    e variazioni di intestazione ('Tempo', 'Giorno', 'Date', 'Week').
    Restituisce un DataFrame con colonna 'Date' + colonne numeriche.
    """
    # Carica bytes (sia da path che da UploadedFile)
    if isinstance(file_like_or_path, (str, os.PathLike)):
        with open(file_like_or_path, "rb") as f:
            raw_bytes = f.read()
    else:
        raw_bytes = file_like_or_path.read()
        try:
            file_like_or_path.seek(0)  # ripristina il puntatore se è un UploadedFile
        except Exception:
            pass

    text = raw_bytes.decode("utf-8", errors="ignore")
    lines = text.splitlines()

    # Trova la riga header (prima riga con una delle parole chiave + virgola)
    header_idx = 0
    for i, line in enumerate(lines[:50]):  # controlla prime 50 righe
        low = line.lower()
        if "," in line and any(k in low for k in ["tempo", "giorno", "date", "week"]):
            header_idx = i
            break

    csv_text = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(csv_text))

    # Rinomina la prima colonna in 'Date'
    first_col = df.columns[0]
    df = df.rename(columns={first_col: "Date"})

    # Normalizza i nomi serie (rimuove eventuale suffisso ': (Tutto il mondo)' ecc.)
    new_cols = []
    for c in df.columns:
        if c == "Date":
            new_cols.append(c)
        else:
            new_cols.append(c.split(":")[0].strip())
    df.columns = new_cols

    # Converte Date e pulisce
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # Converte tutte le altre colonne a numerico
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Tieni solo colonne numeriche
    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)

# ----------------------------
# Sorgente dati: repo o upload
# ----------------------------
st.sidebar.header("Dati")
uploaded = st.sidebar.file_uploader("Carica CSV (Google Trends)", type=["csv"])
use_repo = st.sidebar.checkbox("Usa dataset di default del repository (data/trend.csv)", value=True if uploaded is None else False)

df = pd.DataFrame()
origin = ""

if uploaded is not None:
    df = load_trends_csv(uploaded)
    origin = "CSV caricato dall'utente"
elif use_repo:
    path = os.path.join(os.path.dirname(__file__), "data", "trend.csv")
    if os.path.exists(path):
        df = load_trends_csv(path)
        origin = "data/trend.csv (repo)"
    else:
        origin = "Nessun file trovato"

# Messaggi di stato
if df.empty:
    st.warning("Nessuna serie numerica trovata nel CSV. Verifica il formato (prima colonna = data, almeno una serie numerica).")
    st.stop()

st.success(f"Dati caricati da: **{origin}**")

# ----------------------------
# Filtri e opzioni
# ----------------------------
numeric_cols = df.columns[1:].tolist()
default_selection = numeric_cols[:1] if numeric_cols else []
selected_cols = st.multiselect("Seleziona serie da visualizzare", options=numeric_cols, default=default_selection)

if not selected_cols:
    st.info("Seleziona almeno una serie per procedere.")
    st.stop()

# Filtro date
min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
date_range = st.date_input(
    "Intervallo temporale",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    mask = (df["Date"] >= start) & (df["Date"] <= end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
    df = df.loc[mask].copy()

# Smoothing
smoothing = st.selectbox("Smoothing (media mobile)", options=[1, 3, 7, 14], index=0)
plot_df = df.copy()
if smoothing > 1:
    for c in selected_cols:
        plot_df[c] = plot_df[c].rolling(window=smoothing, min_periods=1).mean()

# ----------------------------
# Grafico
# ----------------------------
fig = px.line(
    plot_df,
    x="Date",
    y=selected_cols,
    markers=True,
    title="Andamento interesse nel tempo"
)
fig.update_layout(legend_title_text="Serie")

st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# KPI rapidi (max 3 serie)
# ----------------------------
st.subheader("KPI rapidi")
kpi_cols = st.columns(min(3, len(selected_cols)))
for i, col in enumerate(selected_cols[:3]):
    last_val = int(plot_df[col].iloc[-1]) if not plot_df.empty else 0
    peak_val = int(plot_df[col].max()) if not plot_df.empty else 0
    peak_date = plot_df.loc[plot_df[col].idxmax(), "Date"].date() if not plot_df.empty else "-"
    with kpi_cols[i]:
        st.metric(label=f"{col} — ultimo valore", value=last_val, delta=f"picco {peak_val} il {peak_date}")

# ----------------------------
# Download dati filtrati
# ----------------------------
st.download_button(
    "⬇️ Scarica CSV (dati filtrati)",
    data=plot_df[["Date"] + selected_cols].to_csv(index=False).encode("utf-8"),
    file_name="trends_filtrati.csv",
    mime="text/csv"
)

st.caption("Suggerimento: carica CSV direttamente da Google Trends (grafico 'Interesse nel tempo').")
