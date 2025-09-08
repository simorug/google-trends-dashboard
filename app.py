import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import io
import os
import re

st.set_page_config(page_title="Google Trends Dashboard", page_icon="📈", layout="wide")
st.title("📊 Google Trends Dashboard")

@st.cache_data
def load_trends_file(file_like_or_path):
    if isinstance(file_like_or_path, (str, os.PathLike)):
        ext = os.path.splitext(file_like_or_path)[1].lower()
    else:
        ext = os.path.splitext(getattr(file_like_or_path, "name", ""))[1].lower()
    df = None
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_like_or_path)
        elif ext in [".tsv", ".txt"]:
            df = pd.read_csv(file_like_or_path, sep="\t")
        else:
            if isinstance(file_like_or_path, (str, os.PathLike)):
                with open(file_like_or_path, "rb") as f:
                    raw_bytes = f.read()
            else:
                raw_bytes = file_like_or_path.read()
                try:
                    file_like_or_path.seek(0)
                except Exception:
                    pass
            text = raw_bytes.decode("utf-8-sig", errors="ignore")
            lines = text.splitlines()
            header_idx = 0
            header_found = False
            header_keys = ["tempo", "giorno", "settimana", "week", "date", "time", "tempo (italia)"]
            for i, line in enumerate(lines[:200]):
                low = line.lower()
                if ("," in line or ";" in line or "\t" in line) and any(k in low for k in header_keys):
                    header_idx = i
                    header_found = True
                    break
            if not header_found:
                date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
                for i, line in enumerate(lines[:200]):
                    if date_re.search(line) and ("," in line or ";" in line or "\t" in line):
                        header_idx = max(0, i - 1)
                        header_found = True
                        break
            csv_text = "\n".join(lines[header_idx:])
            try:
                df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
            except Exception:
                df = pd.read_csv(io.StringIO(csv_text))
    except Exception:
        return pd.DataFrame()
    if df is None or df.shape[1] == 0:
        return pd.DataFrame()
    first_col = df.columns[0]
    df.rename(columns={first_col: "Date"}, inplace=True)
    cleaned = []
    for c in df.columns:
        if c == "Date":
            cleaned.append(c)
            continue
        base = str(c).split(":")[0].strip()
        if base == "":
            base = str(c).strip()
        cleaned.append(base)
    df.columns = cleaned
    drop_cols = [c for c in df.columns if str(c).strip().lower() == "ispartial"]
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True, errors="ignore")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        try:
            df["Date"] = df["Date"].dt.tz_convert(None)
        except Exception:
            df["Date"] = df["Date"].dt.tz_localize(None)
        df = df.dropna(subset=["Date"])
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(r"[^\d\.\-]", "", regex=True), errors="coerce")
    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()
    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)

def df_to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")

def df_to_excel_bytes(df):
    to_excel = BytesIO()
    with pd.ExcelWriter(to_excel, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Trends")
        workbook = writer.book
        worksheet = writer.sheets["Trends"]
        for i, col in enumerate(df.columns):
            try:
                max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
            except Exception:
                max_len = len(str(col)) + 2
            worksheet.set_column(i, i, max_len)
    to_excel.seek(0)
    return to_excel.getvalue()

def download_chart_bytes(fig, fallback_df=None):
    try:
        img = fig.to_image(format="png", engine="kaleido")
        return img, "image/png"
    except Exception:
        if fallback_df is not None:
            return df_to_csv_bytes(fallback_df), "text/csv"
        return b"", "application/octet-stream"

uploaded_files = st.sidebar.file_uploader("📂 Carica file (CSV/TSV/XLSX) Google Trends", type=["csv","tsv","txt","xlsx","xls"], accept_multiple_files=True)

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
            df = pd.concat(all_dfs, ignore_index=True, sort=False)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        except Exception as e:
            st.error("Errore durante concatenazione: " + str(e))
            st.stop()
        st.success("✅ Dati caricati")
        min_ts, max_ts = df["Date"].min(), df["Date"].max()
        min_date, max_date = min_ts.date(), max_ts.date()
        with st.sidebar:
            st.markdown("---")
            date_range = st.date_input("📅 Intervallo", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            freq = st.selectbox("⏱ Raggruppa per", ["Nessuno","Giorno","Settimana","Mese"])
        if isinstance(date_range, tuple):
            start_date, end_date = date_range
        else:
            start_date, end_date = date_range, date_range
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        mask = (df["Date"] >= start_ts) & (df["Date"] <= end_ts)
        filtered_df = df.loc[mask].copy()
        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean(numeric_only=True).reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean(numeric_only=True).reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean(numeric_only=True).reset_index()
        tab1, tab2, tab3 = st.tabs(["📊 Grafici","📈 Statistiche","🗂 Dati grezzi"])
        with tab1:
            numeric_cols = [c for c in filtered_df.columns if c != "Date" and pd.api.types.is_numeric_dtype(filtered_df[c])]
            if numeric_cols:
                chart_type = st.selectbox("Tipo grafico", ["Linee","Barre","Area","Scatter"])
                if chart_type == "Linee":
                    fig = px.line(filtered_df, x="Date", y=numeric_cols, title="Andamento", markers=True)
                elif chart_type == "Barre":
                    fig = px.bar(filtered_df, x="Date", y=numeric_cols, title="Andamento")
                elif chart_type == "Area":
                    fig = px.area(filtered_df, x="Date", y=numeric_cols, title="Andamento")
                else:
                    fig = px.scatter(filtered_df, x="Date", y=numeric_cols, title="Andamento")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Nessuna colonna numerica.")
                fig = None
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button("📊 Scarica CSV", data=df_to_csv_bytes(filtered_df), file_name="trends_data.csv", mime="text/csv")
            with col2:
                st.download_button("📈 Scarica Excel", data=df_to_excel_bytes(filtered_df), file_name="trends_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col3:
                if fig is not None:
                    payload, mime = download_chart_bytes(fig, fallback_df=filtered_df)
                    fname = "trends_chart.png" if mime == "image/png" else "trends_data.csv"
                    st.download_button("🖼️ Scarica grafico (PNG o CSV)", data=payload, file_name=fname, mime=mime)
        with tab2:
            st.subheader("Statistiche principali")
            for col in filtered_df.columns[1:]:
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
                c2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
                c3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")
        with tab3:
            st.subheader("Dati")
            st.dataframe(filtered_df, use_container_width=True)
    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("⬅️ Carica un file di Google Trends per iniziare")
