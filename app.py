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

# =========================
# Funzioni di supporto
# =========================
@st.cache_data
def load_trends_csv(file_like_or_path) -> pd.DataFrame:
    """
    Legge CSV di Google Trends (multiTimeline.csv) anche se contiene righe iniziali
    tipo 'Categoria: ...', 'Paese: ...', ecc. e intestazioni variabili.
    Restituisce un DataFrame con colonna 'Date' + serie numeriche.
    """

    # --- 1) Carica i bytes
    if isinstance(file_like_or_path, (str, os.PathLike)):
        with open(file_like_or_path, "rb") as f:
            raw_bytes = f.read()
    else:
        raw_bytes = file_like_or_path.read()
        try:
            file_like_or_path.seek(0)
        except Exception:
            pass

    # --- 2) Decodifica robusta
    try:
        text = raw_bytes.decode("utf-8-sig")
    except Exception:
        text = raw_bytes.decode("utf-8", errors="ignore")

    lines = text.splitlines()

    # --- 3) Trova header
    header_idx = 0
    header_found = False
    header_keys = ["tempo", "giorno", "settimana", "week", "date", "month", "mese"]

    for i, line in enumerate(lines[:100]):
        low = line.lower()
        if ("," in line or ";" in line or "\t" in line) and any(k in low for k in header_keys):
            header_idx = i
            header_found = True
            break

    # fallback: cerca una riga con YYYY-MM-DD
    if not header_found:
        date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
        for i, line in enumerate(lines[:100]):
            if date_re.search(line) and ("," in line or ";" in line or "\t" in line):
                header_idx = max(0, i - 1)
                header_found = True
                break

    csv_text = "\n".join(lines[header_idx:])

    # --- 4) Leggi CSV
    try:
        df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
    except Exception:
        df = pd.read_csv(io.StringIO(csv_text))

    if df.shape[1] == 0:
        return pd.DataFrame()

    # --- 5) Prima colonna → "Date"
    first_col = df.columns[0]
    df.rename(columns={first_col: "Date"}, inplace=True)

    # --- 6) Pulisci nomi colonne (toglie es. ': (Italy)')
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

    # --- 7) Drop colonna isPartial
    drop_cols = [c for c in df.columns if c.strip().lower() == "ispartial"]
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)

    # --- 8) Converte Date UNIFICANDO il fuso (evita mix tz-aware/naive)
    #     Tutte le date diventano UTC e poi tz-naive -> nessun conflitto in sort/comparison
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["Date"])

    # --- 9) Converte altre colonne in numerico (ripulisce eventuali caratteri non numerici)
    for c in df.columns[1:]:
        s = df[c].astype(str).str.replace(r"[^\d\.\-]", "", regex=True)
        df[c] = pd.to_numeric(s, errors="coerce")

    # --- 10) Tieni solo numeriche
    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)


def download_chart(fig, fallback_df: pd.DataFrame | None = None):
    """Tenta il download PNG (richiede kaleido). Se non disponibile, ritorna CSV."""
    try:
        import plotly.io as pio  # noqa
        buffer = BytesIO()
        fig.write_image(buffer, format="png")  # usa kaleido se presente
        buffer.seek(0)
        return buffer, "image/png", "trends_chart.png"
    except Exception:
        # fallback: offri il CSV dei dati visibili
        if fallback_df is None:
            fallback_df = pd.DataFrame()
        csv_bytes = fallback_df.to_csv(index=False).encode("utf-8")
        return BytesIO(csv_bytes), "text/csv", "trends_visible.csv"


# =========================
# Upload file
# =========================
uploaded_files = st.file_uploader(
    "Carica uno o più file CSV da Google Trends",
    type=["csv"],
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []
    for f in uploaded_files:
        df_tmp = load_trends_csv(f)
        if not df_tmp.empty:
            # normalizza subito la colonna Date (uniforme, tz-naive in UTC)
            df_tmp["Date"] = pd.to_datetime(df_tmp["Date"], errors="coerce", utc=True).dt.tz_localize(None)
            df_tmp = df_tmp.dropna(subset=["Date"])
            all_dfs.append(df_tmp)

    if all_dfs:
        # concatena in sicurezza e ordina
        try:
            df = pd.concat(all_dfs, ignore_index=True)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_localize(None)
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        except Exception as e:
            st.error(f"❌ Errore durante la concatenazione/ordinamento dei file: {e}")
            st.stop()

        st.subheader("✅ Dati caricati correttamente")
        st.dataframe(df.head(20))

        # =========================
        # Filtro periodo
        # =========================
        min_date_ts, max_date_ts = df["Date"].min(), df["Date"].max()
        # Streamlit preferisce oggetti date per il widget
        min_date, max_date = min_date_ts.date(), max_date_ts.date()

        start_date, end_date = st.date_input(
            "Seleziona l'intervallo di date",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        # normalizza in Timestamp
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)

        mask = (df["Date"] >= start_ts) & (df["Date"] <= end_ts)
        filtered_df = df.loc[mask].copy()

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
        numeric_cols = [c for c in filtered_df.columns if c != "Date" and pd.api.types.is_numeric_dtype(filtered_df[c])]
        if numeric_cols:
            for col in numeric_cols:
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
                c2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
                c3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")
        else:
            st.warning("Nessuna colonna numerica disponibile dopo il filtro.")

        # =========================
        # Grafico
        # =========================
        if numeric_cols:
            fig = px.line(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends", markers=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            fig = None

        # =========================
        # Download
        # =========================
        if fig is not None:
            payload, mime, filename = download_chart(fig, fallback_df=filtered_df[["Date"] + numeric_cols])
            st.download_button(
                label="📥 Scarica grafico in PNG (se disponibile) / altrimenti CSV",
                data=payload,
                file_name=filename,
                mime=mime
            )
            if mime != "image/png":
                st.info("Per il download PNG serve il pacchetto `kaleido`. Aggiungilo in `requirements.txt`.")
        else:
            st.download_button(
                label="⬇️ Scarica dati filtrati (CSV)",
                data=filtered_df.to_csv(index=False).encode("utf-8"),
                file_name="trends_filtrati.csv",
                mime="text/csv"
            )
    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("Carica un file CSV di Google Trends per iniziare.")
