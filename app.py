import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import io
import os
import re

# =========================
# Config base
# =========================
st.set_page_config(
    page_title="Google Trends Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Google Trends Dashboard")

# =========================
# Helpers parsing / cleaning
# =========================
HEADER_KEYS = ["tempo", "giorno", "settimana", "week", "date", "month", "mese"]

def _read_bytes(file_like_or_path):
    """Legge bytes sia da path che da UploadedFile"""
    if isinstance(file_like_or_path, (str, os.PathLike)):
        with open(file_like_or_path, "rb") as f:
            raw = f.read()
    else:
        raw = file_like_or_path.read()
        try:
            file_like_or_path.seek(0)
        except Exception:
            pass
    return raw

def _decode_to_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except Exception:
        return raw.decode("utf-8", errors="ignore")

def _find_csv_header_index(lines: list[str]) -> int:
    """Trova l'indice da cui inizia la tabella vera nei CSV Google Trends con preambolo."""
    header_idx = 0
    # 1) Cerca una riga con separatori e parole chiave da header
    for i, line in enumerate(lines[:100]):
        low = line.lower()
        if ("," in line or ";" in line or "\t" in line) and any(k in low for k in HEADER_KEYS):
            return i
    # 2) Fallback: cerca una riga che contenga una data + separatore
    date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
    for i, line in enumerate(lines[:100]):
        if date_re.search(line) and ("," in line or ";" in line or "\t" in line):
            return max(0, i - 1)
    return 0

def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Rende la prima colonna 'Date' e la converte a datetime in modo robusto."""
    if df.shape[1] == 0:
        return df

    # Rinominare la prima colonna in 'Date'
    first_col = df.columns[0]
    df = df.rename(columns={first_col: "Date"})

    # Se ci sono intervalli tipo "2020-01-01 - 2020-01-07", estrai la prima data
    df["Date"] = df["Date"].astype(str).str.extract(r"(\d{4}-\d{2}-\d{2})")[0].fillna(df["Date"])

    # Prova 1: parsing standard
    date_parsed = pd.to_datetime(df["Date"], errors="coerce", utc=False)

    # Se quasi tutto è NaT, prova con dayfirst
    if date_parsed.isna().mean() > 0.5:
        date_parsed = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True, utc=False)

    df["Date"] = date_parsed
    df = df.dropna(subset=["Date"]).copy()
    # rimuove time zone eventualmente presenti
    if pd.api.types.is_datetime64tz_dtype(df["Date"]):
        df["Date"] = df["Date"].dt.tz_localize(None)

    return df

def _clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Rimuove suffissi tipo ': (Italy)' e spazi, e la colonna isPartial se presente."""
    cleaned = []
    for c in df.columns:
        if c == "Date":
            cleaned.append(c)
            continue
        base = str(c).split(":")[0].strip()
        base = base if base else str(c).strip()
        cleaned.append(base)
    df.columns = cleaned

    drop_cols = [c for c in df.columns if str(c).strip().lower() == "ispartial"]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df

def _to_numeric_strict(df: pd.DataFrame) -> pd.DataFrame:
    """Converte le colonne (tranne Date) a numerico, ripulendo caratteri strani."""
    for c in df.columns:
        if c == "Date":
            continue
        s = df[c].astype(str).str.replace(r"[^\d\.\-]", "", regex=True)
        df[c] = pd.to_numeric(s, errors="coerce")
    return df

@st.cache_data
def load_trends_file(file_like_or_path) -> pd.DataFrame:
    """
    Carica file Google Trends nei formati: CSV, XLSX/XLS, TSV/TXT.
    - Rimuove preamboli
    - Uniforma 'Date'
    - Converte i valori in numerico
    Restituisce DataFrame con ['Date', ...serie numeriche...] ordinato.
    """
    # Determina estensione
    if isinstance(file_like_or_path, (str, os.PathLike)):
        ext = os.path.splitext(file_like_or_path)[1].lower()
        name_for_err = os.path.basename(file_like_or_path)
    else:
        ext = os.path.splitext(file_like_or_path.name)[1].lower()
        name_for_err = file_like_or_path.name

    df = None

    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_like_or_path)
        elif ext in [".tsv", ".txt"]:
            # TSV/TXT
            df = pd.read_csv(file_like_or_path, sep="\t")
        else:
            # CSV (anche con preamboli Google Trends)
            raw = _read_bytes(file_like_or_path)
            text = _decode_to_text(raw)
            lines = text.splitlines()
            header_idx = _find_csv_header_index(lines)
            csv_text = "\n".join(lines[header_idx:])
            try:
                df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
            except Exception:
                df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:
        st.error(f"❌ Errore durante la lettura del file {name_for_err}: {e}")
        return pd.DataFrame()

    if df is None or df.shape[1] == 0:
        return pd.DataFrame()

    # Normalizzazioni
    df = _normalize_date_column(df)
    if df.empty:
        return pd.DataFrame()

    df = _clean_column_names(df)
    df = _to_numeric_strict(df)

    # Tieni solo le numeriche
    numeric_cols = [c for c in df.columns if c != "Date" and pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    df = df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)
    return df

def download_chart(fig, fallback_df: pd.DataFrame | None = None):
    """Prova a esportare PNG; se manca 'kaleido', ricade su CSV dei dati del grafico."""
    try:
        import plotly.io as pio  # noqa: F401
        png_bytes = fig.to_image(format="png", engine="kaleido")
        return BytesIO(png_bytes), "image/png", "trends_chart.png"
    except Exception:
        if fallback_df is None:
            fallback_df = pd.DataFrame()
        csv_bytes = fallback_df.to_csv(index=False).encode("utf-8")
        return BytesIO(csv_bytes), "text/csv", "trends_visible.csv"

def df_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

def df_to_excel(df: pd.DataFrame) -> BytesIO:
    to_excel = BytesIO()
    try:
        with pd.ExcelWriter(to_excel, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Trends")
            worksheet = writer.sheets["Trends"]
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
    except Exception:
        # Fallback senza auto-fit
        with pd.ExcelWriter(to_excel, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Trends")
    to_excel.seek(0)
    return to_excel

def _to_timestamp(x):
    """Converte qualsiasi (date/datetime/Timestamp/str) in pandas.Timestamp naive."""
    ts = pd.to_datetime(x, errors="coerce")
    if pd.isna(ts):
        return ts
    if isinstance(ts, pd.Timestamp) and ts.tz is not None:
        ts = ts.tz_localize(None)
    return ts

# =========================
# Upload file
# =========================
uploaded_files = st.sidebar.file_uploader(
    "📂 Carica uno o più file di Google Trends (CSV, XLSX, TSV/TXT)",
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
        try:
            df = pd.concat(all_dfs, ignore_index=True)
            # Normalizza definitivamente la colonna Date
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            if pd.api.types.is_datetime64tz_dtype(df["Date"]):
                df["Date"] = df["Date"].dt.tz_localize(None)
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        except Exception as e:
            st.error(f"❌ Errore durante la concatenazione dei file: {e}")
            st.stop()

        if df.empty:
            st.warning("⚠️ I file caricati non contengono serie numeriche valide.")
            st.stop()

        st.success("✅ Dati caricati correttamente")

        # Intervallo date per il filtro (usa .date() per compatibilità con st.date_input)
        min_dt = pd.to_datetime(df["Date"].min()).to_pydatetime().date()
        max_dt = pd.to_datetime(df["Date"].max()).to_pydatetime().date()

        with st.sidebar:
            st.markdown("---")
            start_end = st.date_input(
                "📅 Seleziona l'intervallo di date",
                value=(min_dt, max_dt),
                min_value=min_dt,
                max_value=max_dt
            )
            # Streamlit può restituire un singolo date o una tupla
            if isinstance(start_end, tuple) and len(start_end) == 2:
                start, end = start_end
            else:
                start, end = min_dt, max_dt

            freq = st.selectbox("⏱️ Raggruppa dati per", ["Nessuno", "Giorno", "Settimana", "Mese"])

        # Confronto type-safe: converto start/end in Timestamp
        start_ts = _to_timestamp(start)
        end_ts = _to_timestamp(end)

        mask = (df["Date"] >= start_ts) & (df["Date"] <= end_ts)
        filtered_df = df.loc[mask].copy()

        # Resampling
        if not filtered_df.empty:
            if freq == "Giorno":
                filtered_df = filtered_df.resample("D", on="Date").mean(numeric_only=True).reset_index()
            elif freq == "Settimana":
                filtered_df = filtered_df.resample("W", on="Date").mean(numeric_only=True).reset_index()
            elif freq == "Mese":
                filtered_df = filtered_df.resample("M", on="Date").mean(numeric_only=True).reset_index()

        # =========================
        # TABS UI
        # =========================
        tab1, tab2, tab3 = st.tabs(["📊 Grafici", "📈 Statistiche", "🗂️ Dati grezzi"])

        with tab1:
            numeric_cols = [c for c in filtered_df.columns if c != "Date" and pd.api.types.is_numeric_dtype(filtered_df[c])]
            if not filtered_df.empty and numeric_cols:
                chart_type = st.selectbox("Tipo di grafico", ["Linee", "Barre", "Area", "Scatter"], index=0)
                if chart_type == "Linee":
                    fig = px.line(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends", markers=True)
                elif chart_type == "Barre":
                    fig = px.bar(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends")
                elif chart_type == "Area":
                    fig = px.area(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends")
                else:
                    fig = px.scatter(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends")

                st.plotly_chart(fig, use_container_width=True)

                st.markdown("### 📥 Esporta dati e grafico")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.download_button(
                        label="📊 Scarica CSV",
                        data=df_to_csv(filtered_df[["Date"] + numeric_cols]),
                        file_name="trends_data.csv",
                        mime="text/csv"
                    )
                with c2:
                    st.download_button(
                        label="📈 Scarica Excel",
                        data=df_to_excel(filtered_df[["Date"] + numeric_cols]),
                        file_name="trends_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                with c3:
                    payload, mime, fname = download_chart(fig, fallback_df=filtered_df[["Date"] + numeric_cols])
                    st.download_button(
                        label="🖼️ Scarica grafico (PNG/CSV)",
                        data=payload,
                        file_name=fname,
                        mime=mime
                    )
            else:
                st.info("Nessun dato da visualizzare per l'intervallo/aggregazione selezionati.")

        with tab2:
            st.subheader("📈 Statistiche principali")
            if not filtered_df.empty:
                numeric_cols = [c for c in filtered_df.columns if c != "Date" and pd.api.types.is_numeric_dtype(filtered_df[c])]
                if numeric_cols:
                    for col in numeric_cols:
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
                        col2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
                        col3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")
                        last_val = filtered_df[col].iloc[-1]
                        col4.metric("Ultimo", f"{last_val:.0f}")
                else:
                    st.info("Nessuna colonna numerica disponibile dopo il filtro.")
            else:
                st.info("Carica dati e seleziona un intervallo valido.")

        with tab3:
            st.subheader("🗂️ Dati grezzi")
            if not filtered_df.empty:
                st.dataframe(filtered_df, use_container_width=True)
            else:
                st.info("Nessun dato disponibile per i filtri scelti.")

    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("⬅️ Carica uno o più file (CSV, XLSX, TSV/TXT) per iniziare.")
