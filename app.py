import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import os

# =========================
# CONFIGURAZIONE BASE
# =========================
st.set_page_config(
    page_title="Google Trends Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Google Trends Dashboard")

# =========================
# FUNZIONE PER CARICARE FILE
# =========================
@st.cache_data
def load_trends_file(file):
    ext = os.path.splitext(file.name)[1].lower()

    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file)
        elif ext in [".tsv", ".txt"]:
            df = pd.read_csv(file, sep="\t")
        else:  # CSV di default
            df = pd.read_csv(file)
    except Exception as e:
        st.error(f"❌ Errore durante la lettura del file {file.name}: {e}")
        return pd.DataFrame()

    # Se dataframe vuoto → stop
    if df.shape[1] == 0:
        return pd.DataFrame()

    # Rinominare prima colonna in Date
    first_col = df.columns[0]
    df.rename(columns={first_col: "Date"}, inplace=True)

    # Conversione Date robusta
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # Conversione numerica delle altre colonne
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)

# =========================
# ESPORTAZIONI
# =========================
def df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")

def df_to_excel(df):
    to_excel = BytesIO()
    with pd.ExcelWriter(to_excel, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Trends")
        worksheet = writer.sheets["Trends"]
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_len)
    to_excel.seek(0)
    return to_excel

# =========================
# SIDEBAR: UPLOAD FILE
# =========================
uploaded_files = st.sidebar.file_uploader(
    "📂 Carica uno o più file di Google Trends",
    type=["csv", "xlsx", "xls", "tsv", "txt"],
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []
    for f in uploaded_files:
        df_tmp = load_trends_file(f)
        if not df_tmp.empty:
            all_dfs.append(df_tmp)

    if all_dfs:
        # Unisci più file
        df = pd.concat(all_dfs, ignore_index=True)
        df = df.sort_values("Date").reset_index(drop=True)

        st.success("✅ Dati caricati correttamente")

        # Intervallo date
        min_date, max_date = df["Date"].min(), df["Date"].max()
        with st.sidebar:
            st.markdown("---")
            start, end = st.date_input(
                "📅 Seleziona l'intervallo di date",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
            freq = st.selectbox("⏱️ Raggruppa dati per", ["Nessuno", "Giorno", "Settimana", "Mese"])

        mask = (df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))
        filtered_df = df.loc[mask]

        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean().reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean().reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean().reset_index()

        # =========================
        # TABS
        # =========================
        tab1, tab2, tab3 = st.tabs(["📊 Grafici", "📈 Statistiche", "🗂️ Dati grezzi"])

        with tab1:
            fig = px.line(
                filtered_df,
                x="Date",
                y=filtered_df.columns[1:],
                title="📊 Andamento Google Trends",
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("### 📥 Esporta dati")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button("📊 Scarica CSV", data=df_to_csv(filtered_df), file_name="trends.csv", mime="text/csv")
            with col2:
                st.download_button("📈 Scarica Excel", data=df_to_excel(filtered_df), file_name="trends.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        with tab2:
            st.subheader("📈 Statistiche principali")
            for col in filtered_df.columns[1:]:
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
                c2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
                c3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")

        with tab3:
            st.subheader("🗂️ Dati grezzi")
            st.dataframe(filtered_df, use_container_width=True)

    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("⬅️ Carica un file per iniziare.")
