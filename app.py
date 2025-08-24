import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Google Trends Dashboard", layout="wide")

st.title("📊 Google Trends Dashboard")
st.markdown("Carica uno o più file CSV da Google Trends")

# Funzione per leggere CSV
def read_trends_csv(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file, skiprows=0)
    except Exception:
        df = pd.read_csv(uploaded_file, skiprows=1)

    df = df.rename(columns=lambda x: x.strip().replace(" ", "").replace("<", "").replace(">", ""))

    date_col = None
    for c in df.columns:
        if "date" in c.lower():
            date_col = c
            break
    if not date_col:
        return None

    df = df.rename(columns={date_col: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    for col in df.columns:
        if col != "Date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

# Funzione export multiplo
def export_excel(df, numeric_cols):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Dati_Completi", index=False)

        for col in numeric_cols:
            subset = df[["Date", col]].dropna()
            subset.to_excel(writer, sheet_name=col[:31], index=False)

    return output.getvalue()

def export_png(fig, df, numeric_cols):
    try:
        import plotly.io as pio
        buf = io.BytesIO()
        pio.write_image(fig, buf, format="png")
        return buf.getvalue(), "image/png", "grafico_trends.png"
    except Exception:
        return df[["Date"] + numeric_cols].to_csv(index=False).encode("utf-8"), "text/csv", "trends_filtrati.csv"

# --- SIDEBAR ---
st.sidebar.header("⚙️ Controlli")

uploaded_files = st.sidebar.file_uploader(
    "Carica uno o più CSV", type=["csv"], accept_multiple_files=True
)

resample_option = st.sidebar.selectbox(
    "Raggruppamento date", ["Giornaliero", "Settimanale", "Mensile"]
)

# --- MAIN ---
if uploaded_files:
    all_dfs = []
    for f in uploaded_files:
        df = read_trends_csv(f)
        if df is not None:
            df["SourceFile"] = f.name
            all_dfs.append(df)

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True).sort_values("Date")

        rule = {"Giornaliero": "D", "Settimanale": "W", "Mensile": "M"}[resample_option]
        df = df.set_index("Date").resample(rule).mean().reset_index()

        tab1, tab2, tab3, tab4 = st.tabs(["📑 Anteprima", "📊 Statistiche", "📈 Grafici", "⬇️ Esportazione"])

        with tab1:
            st.subheader("Anteprima dati filtrati")
            st.dataframe(df.head(20))

        with tab2:
            st.subheader("Statistiche principali")
            numeric_cols = [c for c in df.columns if c not in ["Date", "SourceFile"] and pd.api.types.is_numeric_dtype(df[c])]
            if numeric_cols:
                for col in numeric_cols:
                    c1, c2, c3 = st.columns(3)
                    c1.metric(f"Media {col}", f"{df[col].mean():.2f}")
                    c2.metric(f"Max {col}", f"{df[col].max():.0f}")
                    c3.metric(f"Min {col}", f"{df[col].min():.0f}")
            else:
                st.warning("Nessuna colonna numerica disponibile.")

        with tab3:
            st.subheader("Andamento Google Trends")
            if numeric_cols:
                fig = px.line(df, x="Date", y=numeric_cols, title="Andamento Google Trends", markers=True)
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = None

        with tab4:
            st.subheader("Esporta dati e grafici")

            # Export CSV
            st.download_button(
                label="⬇️ Scarica dati in CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="trends_filtrati.csv",
                mime="text/csv"
            )

            # Export Excel
            if numeric_cols:
                excel_bytes = export_excel(df, numeric_cols)
                st.download_button(
                    label="⬇️ Scarica Excel multi-sheet",
                    data=excel_bytes,
                    file_name="trends_multi.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # Export Grafico
            if 'fig' in locals() and fig is not None:
                payload, mime, filename = export_png(fig, df, numeric_cols)
                st.download_button(
                    label="📥 Scarica grafico in PNG (se disponibile)",
                    data=payload,
                    file_name=filename,
                    mime=mime
                )
    else:
        st.error("❌ Nessun dato valido trovato nei file caricati.")
else:
    st.info("📂 Carica uno o più file CSV dalla sidebar per iniziare.")
