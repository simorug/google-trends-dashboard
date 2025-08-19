import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# ==== Config app (branding leggero) ====
st.set_page_config(page_title="TrendVision Analytics", page_icon="📊", layout="wide")
st.title("📊 TrendVision Analytics")
st.caption("Dashboard demo per portfolio — analisi trend da CSV (Google Trends esportato)")

DATA_PATH = Path("data/trend.csv")

@st.cache_data(ttl=600)
def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Non trovo {path}. Carica un CSV in data/trend.csv.")
    df = pd.read_csv(path)
    # Normalizza possibili nomi di colonna
    cols = {c.lower().strip(): c for c in df.columns}
    # Prova a individuare la colonna data
    date_col_guess = None
    for candidate in ["date", "data", "time", "timestamp", "giorno"]:
        if candidate in cols:
            date_col_guess = cols[candidate]; break
    if date_col_guess is None:
        # Se il primo campo sembra una data, usalo
        try:
            pd.to_datetime(df.iloc[:,0])
            date_col_guess = df.columns[0]
        except Exception as _:
            pass
    # Riconosci formato "long" (date, keyword, value)
    long_candidates = {"keyword","term","query","chiave","categoria"}
    value_candidates = {"value","score","interest","valore","ricerche"}
    is_long = any(c in cols for c in long_candidates) and any(v in cols for v in value_candidates)

    if is_long:
        key_col = cols[[c for c in long_candidates if c in cols][0]]
        val_col = cols[[v for v in value_candidates if v in cols][0]]
        if date_col_guess is None:
            date_col_guess = df.columns[0]
        df[date_col_guess] = pd.to_datetime(df[date_col_guess], errors="coerce")
        df = df.dropna(subset=[date_col_guess])
        # pivot a “wide” per grafico multi-serie
        wide = df.pivot_table(index=date_col_guess, columns=key_col, values=val_col, aggfunc="mean").reset_index()
    else:
        # Formato "wide": prima colonna date, le altre serie
        if date_col_guess is None:
            date_col_guess = df.columns[0]
        df[date_col_guess] = pd.to_datetime(df[date_col_guess], errors="coerce")
        df = df.dropna(subset=[date_col_guess])
        wide = df.rename(columns={date_col_guess: "Date"}).copy()
        if "Date" not in wide.columns:
            wide = wide.rename(columns={date_col_guess: "Date"})
    # Assicura che la colonna data si chiami "Date"
    if "Date" not in wide.columns:
        wide = wide.rename(columns={date_col_guess: "Date"})
    # Tieni solo numeriche + Date
    keep = ["Date"] + [c for c in wide.columns if c != "Date" and pd.api.types.is_numeric_dtype(wide[c])]
    wide = wide[keep].sort_values("Date")
    return wide

def moving_average(df: pd.DataFrame, cols: list[str], window: int) -> pd.DataFrame:
    if window <= 1: 
        return df
    out = df.copy()
    for c in cols:
        out[c] = out[c].rolling(window=window, min_periods=1, center=False).mean()
    return out

# ==== Sidebar ====
with st.sidebar:
    st.header("Impostazioni")
    st.write("Il CSV deve essere in `data/trend.csv` nella repo.")
    smooth = st.selectbox("Smoothing (media mobile)", [1, 3, 7, 14], index=2)
    date_range = st.date_input("Intervallo date (opzionale)", value=[], help="Lascia vuoto per tutte le date")

# ==== Body ====
try:
    wide = load_csv(DATA_PATH)
    all_series = [c for c in wide.columns if c != "Date"]
    if not all_series:
        st.warning("Nessuna serie numerica trovata nel CSV. Verifica il formato.")
    else:
        selected = st.multiselect("Seleziona le serie (keyword) da visualizzare", options=all_series, default=all_series[: min(3, len(all_series))])
        if not selected:
            st.info("Seleziona almeno una serie.")
        else:
            df = wide.copy()
            # filtro date
            if isinstance(date_range, list) and len(date_range) == 2:
                start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
                df = df[(df["Date"] >= start) & (df["Date"] <= end)]
            # smoothing
            df = moving_average(df, selected, smooth)

            # Grafico
            fig = px.line(df, x="Date", y=selected, markers=True, title="Andamento ricerche (CSV)")
            st.plotly_chart(fig, use_container_width=True)

            # KPI (ultimi valori e picchi)
            kpi_cols = st.columns(min(4, len(selected)))
            for i, k in enumerate(selected[:4]):
                last = int(round(df[k].dropna().iloc[-1])) if df[k].notna().any() else 0
                peak_val = int(round(df[k].max())) if df[k].notna().any() else 0
                peak_date = df.loc[df[k].idxmax(), "Date"].date() if df[k].notna().any() else "-"
                with kpi_cols[i]:
                    st.metric(label=f"{k} — ultimo", value=last, delta=f"picco {peak_val} il {peak_date}")

            # Tabella + download
            with st.expander("Vedi dati"):
                st.dataframe(df[["Date"] + selected], use_container_width=True, hide_index=True)
            st.download_button("⬇️ Scarica CSV filtrato", df[["Date"] + selected].to_csv(index=False).encode("utf-8"),
                               file_name="trends_filtered.csv", mime="text/csv")

            st.success("Caso d'uso: individua stagionalità e finestre di lancio/promozioni in base ai picchi di interesse.")
except FileNotFoundError as e:
    st.error(str(e))
except Exception as e:
    st.error(f"Errore in lettura/visualizzazione CSV: {e}")
