# 📊 Google Trends Dashboard

**Live demo:** https://app-trend-dashboard.streamlit.app/  <!-- Sostituisci con il tuo link live, se disponibile -->

Dashboard Streamlit per visualizzare e analizzare esportazioni di **Google Trends**.  
Ideale come demo portfolio per recruiter / clienti.

---

## 🚀 Funzionalità principali
- Caricamento multi-formato: **CSV, XLSX/XLS, TSV/TXT** (gestione automatica header Google Trends).  
- Normalizzazione automatica della colonna `Date`.  
- Filtri: intervallo di date, raggruppamento per Giorno/Settimana/Mese.  
- Grafici interattivi (linee, barre, area, scatter) con Plotly.  
- Statistiche rapide: media, max, min, ultimo valore.  
- Esportazione: CSV, Excel (.xlsx) e PNG del grafico (se `kaleido` installato), con fallback CSV.  
- Supporto multi-file (merge automatico e ordinamento temporale).

---

## 🔧 Requisiti / Installazione (locale)
1. Clona la repo (opzionale se lavori via web):
```bash
git clone https://github.com/TUO-UTENTE/google-trends-dashboard.git
cd google-trends-dashboard
