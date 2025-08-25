import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO

st.set_page_config(page_title="Google Trends Dashboard", layout="wide")

st.title("📊 Google Trends Dashboard")

# --- Upload file ---
uploaded_file = st.file_uploader("Carica uno o più file CSV da Google Trends", type=["csv"], accept_multiple_files=False)

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    # Conversione robusta della colonna Date
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])  # Rimuove eventuali righe senza data valida

    st.success("✅ Dati caricati correttamente")

    # --- Selezione intervallo date ---
    if "Date" in df.columns:
        min_date = df["Date"].min().date()
        max_date = df["Date"].max().date()

        start, end = st.date_input(
            "Seleziona l'intervallo di date",
            [min_date, max_date],
            min_value=min_date,
            max_value=max_date
        )

        if isinstance(start, pd.Timestamp):  # Streamlit a volte restituisce già Timestamp
            start = start.to_pydatetime().date()
        if isinstance(end, pd.Timestamp):
            end = end.to_pydatetime().date()

        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)

        mask = (df["Date"] >= start_dt) & (df["Date"] <= end_dt)
        df = df.loc[mask]

    # --- Raggruppamento opzionale ---
    group_option = st.selectbox("Raggruppa dati per", ["Nessuno", "Settimana", "Mese"])
    if group_option == "Settimana":
        df = df.groupby(pd.Grouper(key="Date", freq="W")).mean().reset_index()
    elif group_option == "Mese":
        df = df.groupby(pd.Grouper(key="Date", freq="M")).mean().reset_index()

    # --- Mostra tabella ---
    st.subheader("📋 Anteprima dati")
    st.dataframe(df.head(20))

    # --- Grafico ---
    st.subheader("📈 Andamento nel tempo")
    plt.figure(figsize=(12, 6))
    for col in df.columns:
        if col != "Date":
            sns.lineplot(data=df, x="Date", y=col, label=col)

    plt.xlabel("Data")
    plt.ylabel("Valore")
    plt.legend()
    st.pyplot(plt)

    # --- Esportazione dati ---
    st.subheader("📤 Esporta dati filtrati")

    def convert_df_to_csv(df):
        return df.to_csv(index=False).encode("utf-8")

    csv_data = convert_df_to_csv(df)

    col1, col2 = st.columns([1, 3])
    with col1:
        st.download_button(
            label="💾 Scarica CSV",
            data=csv_data,
            file_name="google_trends_filtrato.csv",
            mime="text/csv"
        )
    with col2:
        st.info("Premi il pulsante per esportare i dati filtrati in CSV.")
