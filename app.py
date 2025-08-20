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
def load_data(uploaded_files):
    """Carica e concatena i file CSV di Google Trends."""
    dfs = []
    for uploaded_file in uploaded_files:
        try:
            df = pd.read_csv(uploaded_file)
            df = clean_trends(df)
            dfs.append(df)
        except Exception as e:
            st.error(f"Errore nel file {uploaded_file.name}: {e}")
    if dfs:
        return pd.concat(dfs, axis=0).reset_index(drop=True)
    return pd.DataFrame()


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

