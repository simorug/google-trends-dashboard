import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import io
import os
import re

st.set_page_config(
    page_title="Google Trends Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Google Trends Dashboard")

@st.cache_data
def load_trends_file(file_like_or_path):
    if isinstance(file_like_or_path, (str, os.PathLike)):
        ext = os.path.splitext(file_like_or_path)[1].lower()
        with open(file_like_or_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            raw_text = f.read()
    else:
        ext = os.path.splitext(file_like_or_path.name)[1].lower()
        raw_text = file_like_or_path.read().decode("utf-8-sig", errors="ignore")
        file_like_or_path.seek(0)

    lines = raw_text.splitlines()
    header_idx = 0
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

    for i, line in enumerate(lines[:100]):
        low = line.lower()
        if "date" in low or date_pattern.search(line):
            header_idx = i
            break

    clean_text = "\n".join(lines[header_idx:])
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(io.BytesIO(raw_text.encode("utf-8")))
        else:
            df = pd.read_csv(io.StringIO(clean_text))
    except Exception as e:
        st.error(f"Errore durante la lettura del file {file_like_or_path}: {e}")
        return pd.DataFrame()

    if df.shape[1] == 0:
        return pd.DataFrame()

    first_col = df.columns[0]
    df.rename(columns={first_col: "Date"}, inplace=True)

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

    drop_cols = [c for c in df.columns if c.strip().lower() == "ispartial"]
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])

    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)

def download_chart(fig):
    buffer = BytesIO()
    fig.write_image(buffer, format="png")
    return buffer

def df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")

def df_to_excel(df):
    to_excel = BytesIO()
    with pd.ExcelWriter(to_excel, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Trends")
        workbook = writer.book
        worksheet = writer.sheets["Trends"]
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_len)
    to_excel.seek(0)
    return to_excel

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
            df_tmp["Date"] = pd.to_datetime(df_tmp["Date"], errors="coerce")
            df_tmp = df_tmp.dropna(subset=["Date"])
            all_dfs.append(df_tmp)

    if all_dfs:
        try:
            df = pd.concat(all_dfs, ignore_index=True)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        except Exception as e:
            st.error(f"❌ Errore durante la concatenazione dei file: {e}")
            st.stop()

        st.success("✅ Dati caricati correttamente")

        min_date, max_date = df["Date"].min(), df["Date"].max()
        with st.sidebar:
            st.markdown("---")
            start, end = st.date_input(
                "📅 Seleziona l'intervallo di date",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
            if isinstance(start, tuple):
                start, end = start

            freq = st.selectbox("⏱️ Raggruppa dati per", ["Nessuno", "Giorno", "Settimana", "Mese"])

        mask = (df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))
        filtered_df = df.loc[mask]

        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean().reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean().reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean().reset_index()

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

            st.markdown("### 📥 Esporta dati e grafico")
            with st.container():
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.download_button(
                        label="📊 Scarica CSV",
                        data=df_to_csv(filtered_df),
                        file_name="trends_data.csv",
                        mime="text/csv"
                    )
                with col2:
                    st.download_button(
                        label="📈 Scarica Excel",
                        data=df_to_excel(filtered_df),
                        file_name="trends_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                with col3:
                    st.download_button(
                        label="🖼️ Scarica grafico PNG",
                        data=download_chart(fig),
                        file_name="trends_chart.png",
                        mime="image/png"
                    )

        with tab2:
            st.subheader("📈 Statistiche principali")
            for col in filtered_df.columns[1:]:
                col1, col2, col3 = st.columns(3)
                col1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
                col2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
                col3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")

        with tab3:
            st.subheader("🗂️ Dati grezzi")
            st.dataframe(filtered_df, use_container_width=True)

    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("⬅️ Carica un file CSV di Google Trends per iniziare.")
