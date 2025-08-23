import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import io
import os

st.set_page_config(
    page_title="Google Trends Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Google Trends Dashboard")

# =========================
# Funzioni di supporto
# =========================
@st.cache_data
def load_trends_csv(file_like_or_path):
    """
    Legge CSV di Google Trends (multiTimeline.csv) anche se contiene righe iniziali
    tipo 'Categoria: ...', 'Paese: ...', ecc. e intestazioni variabili ('Tempo',
    'Giorno', 'Week', 'Date'). Restituisce un DataFrame con colonna 'Date' + serie numeriche.
    """
    import re

    # 1) Carica i bytes (sia da path, sia da UploadedFile di Streamlit)
    if isinstance(file_like_or_path, (str, os.PathLike)):
        with open(file_like_or_path, "rb") as f:
            raw_bytes = f.read()
    else:
        raw_bytes = file_like_or_path.read()
        try:
            file_like_or_path.seek(0)  # ripristina se è un UploadedFile
        except Exception:
            pass

    # 2) Decodifica robusta
    try:
        text = raw_bytes.decode("utf-8-sig")
    except Exception:
        text = raw_bytes.decode("utf-8", errors="ignore")

    lines = text.splitlines()

    # 3) Trova header
    header_idx = 0
    header_found = False
    header_keys = ["tempo", "giorno", "settimana", "week", "date"]

    for i, line in enumerate(lines[:100]):  # prime 100 righe
        low = line.lower()
        if ("," in line or ";" in line or "\t" in line) and any(k in low for k in header_keys):
            header_idx = i
            header_found = True
            break

    # fallback: prima riga con una data tipo YYYY-MM-DD
    if not header_found:
        date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
        for i, line in enumerate(lines[:100]):
            if date_re.search(line) and ("," in line or ";" in line or "\t" in line):
                header_idx = max(0, i - 1)
                header_found = True
                break

    csv_text = "\n".join(lines[header_idx:])

    # 4) Leggi il CSV
    try:
        df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
    except Exception:
        df = pd.read_csv(io.StringIO(csv_text))

    if df.shape[1] == 0:
        return pd.DataFrame()

    # 5) Rinomina prima colonna in "Date"
    first_col = df.columns[0]
    df.rename(columns={first_col: "Date"}, inplace=True)

    # 6) Pulisci nomi serie
    cleaned = []
    for c in df.columns:
        if c == "Date":
            cleaned.append(c)
            continue
        base = c.split(":")[0].strip()
        if base == "":
            base = c.strip()
        cleaned.append(base)
    df.columns = cleaned

    # 7) Drop colonna "isPartial" se presente
    drop_cols = [c for c in df.columns if c.strip().lower() == "ispartial"]
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)

    # 8) Converte Date
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=False)
    df = df.dropna(subset=["Date"])

    # 9) Converte altre colonne in numerico
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 10) Tieni solo numeriche
    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)


def download_chart(fig):
    """Permette di scaricare il grafico in PNG"""
    buffer = BytesIO()
    fig.write_image(buffer, format="png")
    return buffer


# =========================
# Upload file
# =========================
uploaded_files = st.file_uploader(
    "Carica uno o più file CSV da Google Trends",
    type=["csv"],
    accept_multiple_files=True
)

if uploaded_files:
    # 🔥 FIX: combina tutti i CSV caricati in un unico DataFrame
    all_dfs = []
    for f in uploaded_files:
        df_tmp = load_trends_csv(f)
        if not df_tmp.empty:
            all_dfs.append(df_tmp)

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True).sort_values("Date")
        df = df.reset_index(drop=True)

        st.subheader("✅ Dati caricati correttamente")
        st.write(df.head())

        # =========================
        # Filtro periodo
        # =========================
        min_date, max_date = df["Date"].min(), df["Date"].max()
        start, end = st.date_input(
            "Seleziona l'intervallo di date",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        if isinstance(start, tuple):  # correzione per vecchie versioni streamlit
            start, end = start

        mask = (df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))
        filtered_df = df.loc[mask]

        # =========================
        # Resample
        # =========================
        freq = st.selectbox("Raggruppa dati per", ["Nessuno", "Giorno", "Settimana", "Mese"])
        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean().reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean().reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean().reset_index()

        # =========================
        # Statistiche
        # =========================
        st.subheader("📈 Statistiche principali")
        for col in filtered_df.columns[1:]:
            col1, col2, col3 = st.columns(3)
            col1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
            col2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
            col3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")

        # =========================
        # Grafico
        # =========================
        fig = px.line(filtered_df, x="Date", y=filtered_df.columns[1:], title="Andamento Google Trends", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        # =========================
        # Download
        # =========================
        st.download_button(
            label="📥 Scarica grafico in PNG",
            data=download_chart(fig),
            file_name="trends_chart.png",
            mime="image/png"
        )
    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("Carica un file CSV di Google Trends per iniziare.")
