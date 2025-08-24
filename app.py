import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import io
import os
import re
import zipfile

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

    # --- 8) Converte Date UNIFICANDO il fuso (UTC tz-naive)
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
    """PNG se kaleido disponibile, altrimenti CSV dei dati visibili."""
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


def generate_insights(df: pd.DataFrame, cols):
    """Restituisce alcuni insight testuali di base"""
    insights = []
    for col in cols:
        series = df[col].dropna()
        if series.empty:
            continue
        mean = series.mean()
        last = series.iloc[-1]
        first = series.iloc[0]
        trend = ((last - first) / first * 100) if first != 0 else 0
        max_val = series.max()
        min_val = series.min()
        insights.append(
            f"🔎 **{col}**: media {mean:.1f}, max {max_val:.0f}, min {min_val:.0f}, trend {trend:+.1f}% (primo→ultimo)."
        )
    return insights


def build_excel_multisheet(df: pd.DataFrame, numeric_cols):
    """Excel multi-sheet in modo sicuro: prova xlsxwriter, poi openpyxl; se fallisce -> None."""
    buf = BytesIO()

    def _write(writer):
        safe_cols = ["Date"] + [c for c in df.columns if c in numeric_cols]
        df[safe_cols].to_excel(writer, sheet_name="Dati_Completi", index=False)
        for col in numeric_cols:
            sub = df[["Date", col]].dropna()
            sheet = (col or "Serie")[:31]
            sub.to_excel(writer, sheet_name=sheet, index=False)

    try:
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            _write(writer)
        return buf.getvalue()
    except Exception:
        try:
            buf2 = BytesIO()
            with pd.ExcelWriter(buf2, engine="openpyxl") as writer:
                _write(writer)
            return buf2.getvalue()
        except Exception:
            return None


def build_zip_package(df: pd.DataFrame, numeric_cols, fig_or_none):
    """Crea ZIP con CSV, Excel (se possibile) e PNG (se possibile)."""
    mem = BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # CSV
        zf.writestr("trends_filtrati.csv", df.to_csv(index=False))

        # Excel multi-sheet
        excel_bytes = build_excel_multisheet(df, numeric_cols)
        if excel_bytes:
            zf.writestr("trends_multi.xlsx", excel_bytes)

        # PNG (se kaleido presente)
        if fig_or_none is not None:
            try:
                import plotly.io as pio  # noqa
                img_buf = BytesIO()
                fig_or_none.write_image(img_buf, format="png")
                img_buf.seek(0)
                zf.writestr("grafico_trends.png", img_buf.read())
            except Exception:
                pass

        # README
        readme = (
            "Pacchetto esportazione Google Trends\n"
            "- trends_filtrati.csv: dati filtrati/resamplati\n"
            "- trends_multi.xlsx: dati in Excel (uno sheet per serie)\n"
            "- grafico_trends.png: grafico principale (se disponibile)\n"
        )
        zf.writestr("README.txt", readme)

    mem.seek(0)
    return mem.getvalue()


def apply_moving_average(df: pd.DataFrame, cols, window: int, overlay: bool):
    """Applica media mobile alle colonne selezionate.
       overlay=True -> aggiunge nuove colonne col suffisso _MA{window}
       overlay=False -> sostituisce i valori originali (solo per il grafico)
    """
    if window <= 1 or not cols:
        return df.copy(), cols

    out = df.copy()
    if overlay:
        new_cols = []
        for c in cols:
            ma_col = f"{c}_MA{window}"
            out[ma_col] = out[c].rolling(window, min_periods=1).mean()
            new_cols.append(ma_col)
        return out, cols + new_cols
    else:
        for c in cols:
            out[c] = out[c].rolling(window, min_periods=1).mean()
        return out, cols


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
        st.dataframe(df.head(20), use_container_width=True)

        # =========================
        # Filtro periodo
        # =========================
        min_date_ts, max_date_ts = df["Date"].min(), df["Date"].max()
        min_date, max_date = min_date_ts.date(), max_date_ts.date()

        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            start_date, end_date = st.date_input(
                "Intervallo di date",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
        with c2:
            freq = st.selectbox("Raggruppa per", ["Nessuno", "Giorno", "Settimana", "Mese"])
        with c3:
            chart_type = st.selectbox("Tipo di grafico", ["Linee", "Barre", "Area", "Scatter"])

        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)

        mask = (df["Date"] >= start_ts) & (df["Date"] <= end_ts)
        filtered_df = df.loc[mask].copy()

        # =========================
        # Resample
        # =========================
        if freq == "Giorno":
            filtered_df = filtered_df.resample("D", on="Date").mean().reset_index()
        elif freq == "Settimana":
            filtered_df = filtered_df.resample("W", on="Date").mean().reset_index()
        elif freq == "Mese":
            filtered_df = filtered_df.resample("M", on="Date").mean().reset_index()
        # Nessuno -> lasciamo così

        # Colonne numeriche
        numeric_cols = [c for c in filtered_df.columns if c != "Date" and pd.api.types.is_numeric_dtype(filtered_df[c])]
        if not numeric_cols:
            st.warning("Nessuna colonna numerica disponibile dopo il filtro.")
            st.stop()

        # Scelta serie + media mobile
        st.markdown("### 🎛️ Opzioni visualizzazione")
        csel1, csel2, csel3 = st.columns([2, 1, 1])
        with csel1:
            selected_cols = st.multiselect(
                "Seleziona le serie da visualizzare", options=numeric_cols, default=numeric_cols
            )
        with csel2:
            ma_window = st.slider("Media mobile (periodi)", min_value=1, max_value=30, value=1, step=1)
        with csel3:
            overlay_ma = st.checkbox("Sovrapponi MA (non sostituire)", value=True)

        plot_df, plot_cols = apply_moving_average(filtered_df, selected_cols, ma_window, overlay_ma)

        # =========================
        # Statistiche
        # =========================
        st.subheader("📈 Statistiche principali")
        for col in selected_cols:
            cA, cB, cC, cD = st.columns(4)
            cA.metric(f"Media {col}", f"{filtered_df[col].mean():.2f}")
            cB.metric(f"Max {col}", f"{filtered_df[col].max():.0f}")
            cC.metric(f"Min {col}", f"{filtered_df[col].min():.0f}")
            try:
                cD.metric("Ultimo", f"{filtered_df[col].dropna().iloc[-1]:.0f}")
            except Exception:
                cD.metric("Ultimo", "—")

        # =========================
        # Grafico
        # =========================
        st.subheader("📊 Grafici")
        fig = None
        if plot_cols:
            if chart_type == "Linee":
                fig = px.line(plot_df, x="Date", y=plot_cols, title="Andamento Google Trends", markers=True)
            elif chart_type == "Barre":
                fig = px.bar(plot_df, x="Date", y=plot_cols, title="Andamento Google Trends")
            elif chart_type == "Area":
                fig = px.area(plot_df, x="Date", y=plot_cols, title="Andamento Google Trends")
            else:
                fig = px.scatter(plot_df, x="Date", y=plot_cols, title="Andamento Google Trends")
            st.plotly_chart(fig, use_container_width=True)

        # =========================
        # Confronto 2 keyword
        # =========================
        if len(numeric_cols) >= 2:
            st.subheader("📉 Confronto tra due keyword")
            col1, col2 = st.columns(2)
            k1 = col1.selectbox("Keyword 1", numeric_cols, index=0, key="k1")
            k2 = col2.selectbox("Keyword 2", numeric_cols, index=1, key="k2")
            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Scatter(x=filtered_df["Date"], y=filtered_df[k1], mode="lines", name=k1))
            fig_cmp.add_trace(go.Scatter(x=filtered_df["Date"], y=filtered_df[k2], mode="lines", name=k2))
            fig_cmp.update_layout(title=f"Confronto: {k1} vs {k2}")
            st.plotly_chart(fig_cmp, use_container_width=True)

        # =========================
        # Correlazioni
        # =========================
        if len(numeric_cols) >= 2:
            st.subheader("📌 Correlazioni")
            corr = filtered_df[numeric_cols].corr()
            fig_corr = px.imshow(
                corr, text_auto=True, title="Matrice di correlazione", aspect="auto", color_continuous_scale="RdBu_r"
            )
            st.plotly_chart(fig_corr, use_container_width=True)

        # =========================
        # Download
        # =========================
        st.subheader("📥 Download")
        # 1) Grafico PNG (o CSV fallback)
        if fig is not None and plot_cols:
            payload, mime, filename = download_chart(fig, fallback_df=plot_df[["Date"] + plot_cols])
            st.download_button(
                label="Scarica grafico (PNG o CSV)",
                data=payload,
                file_name=filename,
                mime=mime
            )

        # 2) CSV dati filtrati completi
        st.download_button(
            label="⬇️ Scarica dati filtrati (CSV)",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name="trends_filtrati.csv",
            mime="text/csv"
        )

        # 3) Excel multi-sheet (fallback automatico)
        excel_bytes = build_excel_multisheet(filtered_df, numeric_cols)
        if excel_bytes:
            st.download_button(
                label="⬇️ Scarica dati in Excel (multi-sheet)",
                data=excel_bytes,
                file_name="trends_multi.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Per l'Excel è consigliato installare `xlsxwriter` oppure `openpyxl`.")

        # 4) Pacchetto ZIP (CSV + Excel + PNG se disponibili)
        zip_bytes = build_zip_package(filtered_df, numeric_cols, fig)
        st.download_button(
            label="📦 Scarica pacchetto completo (ZIP)",
            data=zip_bytes,
            file_name="pacchetto_trends.zip",
            mime="application/zip"
        )

        # =========================
        # Insights
        # =========================
        st.subheader("🧠 Insights automatici")
        insights = generate_insights(filtered_df, selected_cols)
        for ins in insights:
            st.markdown(ins)

    else:
        st.warning("⚠️ Nessun dato valido trovato nei file caricati.")
else:
    st.info("Carica un file CSV di Google Trends per iniziare.")
