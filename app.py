import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

    if isinstance(file_like_or_path, (str, os.PathLike)):
        with open(file_like_or_path, "rb") as f:
            raw_bytes = f.read()
    else:
        raw_bytes = file_like_or_path.read()
        try:
            file_like_or_path.seek(0)
        except Exception:
            pass

    try:
        text = raw_bytes.decode("utf-8-sig")
    except Exception:
        text = raw_bytes.decode("utf-8", errors="ignore")

    lines = text.splitlines()

    header_idx = 0
    header_found = False
    header_keys = ["tempo", "giorno", "settimana", "week", "date", "month", "mese"]

    for i, line in enumerate(lines[:100]):
        low = line.lower()
        if ("," in line or ";" in line or "\t" in line) and any(k in low for k in header_keys):
            header_idx = i
            header_found = True
            break

    if not header_found:
        date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
        for i, line in enumerate(lines[:100]):
            if date_re.search(line) and ("," in line or ";" in line or "\t" in line):
                header_idx = max(0, i - 1)
                header_found = True
                break

    csv_text = "\n".join(lines[header_idx:])

    try:
        df = pd.read_csv(io.StringIO(csv_text), sep=None, engine="python")
    except Exception:
        df = pd.read_csv(io.StringIO(csv_text))

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

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["Date"])

    for c in df.columns[1:]:
        s = df[c].astype(str).str.replace(r"[^\d\.\-]", "", regex=True)
        df[c] = pd.to_numeric(s, errors="coerce")

    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return pd.DataFrame()

    return df[["Date"] + numeric_cols].sort_values("Date").reset_index(drop=True)


def download_chart(fig, fallback_df: pd.DataFrame | None = None):
    try:
        import plotly.io as pio  # noqa
        buffer = BytesIO()
        fig.write_image(buffer, format="png")
        buffer.seek(0)
        return buffer, "image/png", "trends_chart.png"
    except Exception:
        if fallback_df is None:
            fallback_df = pd.DataFrame()
        csv_bytes = fallback_df.to_csv(index=False).encode("utf-8")
        return BytesIO(csv_bytes), "text/csv", "trends_visible.csv"


def generate_insights(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """Restituisce alcuni insight testuali di base"""
    insights = []
    for col in cols:
        mean = df[col].mean()
        last = df[col].iloc[-1]
        first = df[col].iloc[0]
        trend = ((last - first) / first * 100) if first != 0 else 0
        max_val = df[col].max()
        min_val = df[col].min()
        insights.append(
            f"🔎 **{col}**: media {mean:.1f}, max {max_val:.0f}, min {min_val:.0f}, trend {trend:+.1f}% dal primo all’ultimo punto."
        )
    return insights


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
            df_tmp["Date"] = pd.to_datetime(df_tmp["Date"], errors="coerce", utc=True).dt.tz_localize(None)
            df_tmp = df_tmp.dropna(subset=["Date"])
            all_dfs.append(df_tmp)

    if all_dfs:
        try:
            df = pd.concat(all_dfs, ignore_index=True)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_localize(None)
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        except Exception as e:
            st.error(f"❌ Errore durante la concatenazione/ordinamento dei file: {e}")
            st.stop()

        st.subheader("✅ Dati caricati correttamente")
        st.dataframe(df.head(20))

        min_date_ts, max_date_ts = df["Date"].min(), df["Date"].max()
        min_date, max_date = min_date_ts.date(), max_date_ts.date()

        start_date, end_date = st.date_input(
            "Seleziona l'intervallo di date",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)

        mask = (df["Date"] >= start_ts) & (df["Date"] <= end_ts)
        filtered_df = df.loc[mask].copy()

        freq = st.selectbox("Raggruppa dati per", ["Nessuno", "Giorno", "Settimana", "Mese"])
        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean().reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean().reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean().reset_index()

        st.subheader("📈 Statistiche principali")
        numeric_cols = [c for c in filtered_df.columns if c != "Date" and pd.api.types.is_numeric_dtype(filtered_df[c])]
        if numeric_cols:
            for col in numeric_cols:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
                c2.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
                c3.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")
                c4.metric(f"Ultimo", f"{filtered_df[col].iloc[-1]:.0f}")
        else:
            st.warning("Nessuna colonna numerica disponibile dopo il filtro.")

        st.subheader("📊 Grafici")
        chart_type = st.selectbox("Tipo di grafico", ["Linee", "Barre", "Area", "Scatter"])
        if numeric_cols:
            if chart_type == "Linee":
                fig = px.line(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends", markers=True)
            elif chart_type == "Barre":
                fig = px.bar(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends")
            elif chart_type == "Area":
                fig = px.area(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends")
            else:
                fig = px.scatter(filtered_df, x="Date", y=numeric_cols, title="Andamento Google Trends")

            st.plotly_chart(fig, use_container_width=True)
        else:
            fig = None

        if len(numeric_cols) >= 2:
            st.subheader("📉 Confronto tra due keyword")
            col1, col2 = st.columns(2)
            k1 = col1.selectbox("Keyword 1", numeric_cols, index=0)
            k2 = col2.selectbox("Keyword 2", numeric_cols, index=1)
            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Scatter(x=filtered_df["Date"], y=filtered_df[k1], mode="lines", name=k1))
            fig_cmp.add_trace(go.Scatter(x=filtered_df["Date"], y=filtered_df[k2], mode="lines", name=k2))
            st.plotly_chart(fig_cmp, use_container_width=True)

        if len(numeric_cols) >= 2:
            st.subheader("📌 Correlazioni")
            corr = filtered_df[numeric_cols].corr()
            fig_corr = px.imshow(corr, text_auto=True, title="Matrice di correlazione", aspect="auto", color_continuous_scale="RdBu_r")
            st.plotly_chart(fig_corr, use_container_width=True)

        st.subheader("📥 Download")
        if fig is not None:
            payload, mime, filename = download_chart(fig, fallback_df=filtered_df[["Date"] + numeric_cols])
            st.download_button(
                label="Scarica grafico (PNG o CSV)",
                data=payload,
                file_name=filename,
                mime=mime
            )
        st.download_button(
            label="⬇️ Scarica dati filtrati (CSV)",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name="trends_filtrati.csv",
            mime="text/csv"
        )
        to_excel = BytesIO()
        with pd.ExcelWriter(to_excel, engine="xlsxwriter") as writer:
            filtered_df.to_excel(writer, sheet_name="Dati", index=False)
        st.download_button(
            label="⬇️ Scarica dati in Excel",
            data=to_excel.getvalue(),
            file_name="trends_filtrati.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.subheader("🧠 Insights automatici")
        insights = generate_insights(filtered_df, numeric_cols)
        for ins in insights:
            st.markdown(ins)
    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("Carica un file CSV di Google Trends per iniziare.")
