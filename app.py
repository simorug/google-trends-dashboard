import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

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
    tipo 'Categoria: ...', 'Paese, ...', ecc. e intestazioni variabili ('Tempo',
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

    # 2) Decodifica robusta (gestisce BOM e caratteri strani)
    try:
        text = raw_bytes.decode("utf-8-sig")
    except Exception:
        text = raw_bytes.decode("utf-8", errors="ignore")

    lines = text.splitlines()

    # 3) Trova la riga di header (prima riga con separatore e una parola chiave tipica)
    header_idx = 0
    header_found = False
    header_keys = ["tempo", "giorno", "settimana", "week", "date"]

    for i, line in enumerate(lines[:100]):  # controlla prime 100 righe
        low = line.lower()
        if ("," in line or ";" in line or "\t" in line) and any(k in low for k in header_keys):
            header_idx = i
            header_found = True
            break

    # fallback: cerca la prima riga con una data tipo YYYY-MM-DD e un separatore
    if not header_found:
        date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
        for i, line in enumerate(lines[:100]):
            if date_re.search(line) and ("," in line or ";" in line or "\t" in line):
                header_idx = max(0, i - 1)  # spesso l'header è la riga prima della prima data
                header_found = True
                break

    csv_text = "\n".join(lines[header_idx:])

    # 4) Leggi il CSV con auto-rilevamento del separatore
    try:
        df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
    except Exception:
        # fallback semplice
        df = pd.read_csv(io.StringIO(csv_text))

    if df.shape[1] == 0:
        return pd.DataFrame()

    # 5) Rinomina la prima colonna in 'Date'
    first_col = df.columns[0]
    df.rename(columns={first_col: "Date"}, inplace=True)

    # 6) Pulisci i nomi delle serie (togli suffissi tipo ': (Italia)')
    cleaned = []
    for c in df.columns:
        if c == "Date":
            cleaned.append(c)
            continue
        base = c.split(":")[0].strip()  # es. "AI: (Italy)" -> "AI"
        if base == "":
            base = c.strip()
        cleaned.append(base)
    df.columns = cleaned

    # 7) Elimina colonna isPartial se presente (case-insensitive)
    drop_cols = [c for c in df.columns if c.strip().lower() == "ispartial"]
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)

    # 8) Converti Date
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=False)
    df = df.dropna(subset=["Date"])

    # 9) Converti le altre colonne in numerico (coerce)
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 10) Tieni solo le colonne numeriche
    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    # 11) Ordina per data e ritorna
    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)

def clean_trends(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizza il CSV Google Trends in formato corretto"""
    # Togli le righe di intestazione non necessarie
    df = df.dropna().reset_index(drop=True)
    # Gestione colonne
    if "Tempo" in df.columns:
        df = df.rename(columns={"Tempo": "Date"})
    if len(df.columns) > 1:
        df = df.rename(columns={df.columns[1]: "Value"})
    # Parsing data
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df.dropna(subset=["Value"])
    return df


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
    df = load_data(uploaded_files)

    if not df.empty:
        # =========================
        # Controlli qualità
        # =========================
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
        # Resample (giornaliero, settimanale, mensile)
        # =========================
        freq = st.selectbox("Raggruppa dati per", ["Nessuno", "Giorno", "Settimana", "Mese"])
        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean().reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean().reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean().reset_index()

        # =========================
        # Statistiche rapide
        # =========================
        st.subheader("📈 Statistiche principali")
        col1, col2, col3 = st.columns(3)
        col1.metric("Media", f"{filtered_df['Value'].mean():.2f}")
        col2.metric("Massimo", f"{filtered_df['Value'].max():.0f}")
        col3.metric("Minimo", f"{filtered_df['Value'].min():.0f}")

        # =========================
        # Grafico
        # =========================
        fig = px.line(filtered_df, x="Date", y="Value", title="Andamento Google Trends", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        # =========================
        # Download grafico
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

