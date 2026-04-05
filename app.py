import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import os
import pickle

st.set_page_config(layout="wide")
st.title("⚡ Simulatore Energia Casa Livorno - Versione Realistica Corretta")

# -----------------------
# INPUT UTENTE
# -----------------------
mq = st.slider("Superficie casa (m²)", 30, 150, 47)
kwp = st.slider("Potenza FV (kW)", 1.0, 6.0, 3.0)
batt_kwh = st.slider("Batteria (kWh)", 0.0, 10.0, 5.0)
anno = st.selectbox("Anno di simulazione", [2024, 2025, 2026])

# Parametri tetto
pendenza = st.slider("Pendenza del tetto (gradi)", 0, 45, 12)
orientamento = st.selectbox("Orientamento del tetto",
                            ["Est", "Sud-Est", "Sud", "Sud-Ovest", "Ovest"])

# Mappa orientamento a fattore correttivo
fattori_orientamento = {"Est":0.9, "Sud-Est":0.95, "Sud":1.0, "Sud-Ovest":0.95, "Ovest":0.9}
fattore_orientamento = fattori_orientamento[orientamento]

# Correzione pendenza (ottimale ~30°)
fattore_pendenza = 1 - abs(pendenza-30)/100

# Perdite di sistema (inverter, cablaggi)
fattore_sistema = 0.9

# Ombre / sporco
fattore_ombre = 0.95

CACHE_FILE = f"meteo_cache_{anno}.pkl"

# -----------------------
# FUNZIONE PER SCARICARE SOLO I NUOVI GIORNI
# -----------------------
@st.cache_data
def scarica_meteo_incrementale(anno):
    oggi = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            df_cache = pickle.load(f)
        last_date = pd.to_datetime(df_cache['time'].iloc[-1]).date()
        start_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        df_all = df_cache
    else:
        df_all = pd.DataFrame()
        start_date = f"{anno}-01-01"

    end_date = oggi

    if start_date <= end_date:
        all_data = []
        current = datetime.strptime(start_date, "%Y-%m-%d")
        while current <= datetime.strptime(end_date, "%Y-%m-%d"):
            mese = current.month
            mese_inizio = current.strftime("%Y-%m-%d")
            if mese == 12:
                mese_fine = datetime(current.year, 12, 31).strftime("%Y-%m-%d")
            else:
                mese_fine = (datetime(current.year, mese+1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")

            url = (
                f"https://archive-api.open-meteo.com/v1/archive"
                f"?latitude=43.55&longitude=10.31"
                f"&start_date={mese_inizio}&end_date={mese_fine}"
                "&hourly=temperature_2m,relative_humidity_2m,shortwave_radiation"
                "&timezone=Europe/Rome"
            )
            r = requests.get(url)
            data = r.json().get("hourly", {})
            if data:
                df_month = pd.DataFrame(data)
                all_data.append(df_month)
            current = datetime.strptime(mese_fine, "%Y-%m-%d") + timedelta(days=1)
        if all_data:
            df_new = pd.concat(all_data, ignore_index=True)
            df_all = pd.concat([df_all, df_new], ignore_index=True)
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(df_all, f)

    return df_all

st.info(f"Scaricamento dati meteo incrementale {anno} fino a oggi…")
df = scarica_meteo_incrementale(anno)

# -----------------------
# CONTROLLO DATI
# -----------------------
if df.empty:
    st.error("Errore: nessun dato meteo scaricato. Controlla connessione o anno scelto.")
    st.stop()

# -----------------------
# SIMULAZIONE ORARIA
# -----------------------
soc = 0.5
batt = batt_kwh * soc
consumi = []
produzione = []
rete = []
batt_soc = []

for idx, row in df.iterrows():
    T = row["temperature_2m"]
    U = row["relative_humidity_2m"]
    rad = row["shortwave_radiation"]

    # consumo orario
    base = 0.2
    ora = idx % 24
    if 12 <= ora <= 18:
        base += 0.3
    elif 19 <= ora <= 23:
        base += 0.5
    cool = max(T-24,0)*0.02*(mq/50)
    heat = max(18-T,0)*0.03*(mq/50)
    deum = 0.1 if U>70 else 0
    c = base + cool + heat + deum

    # produzione FV base
    p = rad/1000 * kwp * 0.75

    # correzione orientamento e pendenza
    p *= fattore_orientamento * fattore_pendenza

    # correzione temperatura (>25°C riduce efficienza 0.4%/°C)
    coeff_temp = 0.004
    fattore_temp = max(0, 1 - coeff_temp * max(T-25, 0))
    p *= fattore_temp

    # perdite sistema e ombre
    p *= fattore_sistema * fattore_ombre

    # gestione batteria
    autoconsumo = min(c,p)
    surplus = p - autoconsumo
    spazio = batt_kwh - batt
    carica = min(surplus*0.9, spazio)
    batt += carica
    richiesta = c - autoconsumo
    scarica = min(richiesta, batt*0.9)
    batt -= scarica/0.9
    rete_h = richiesta - scarica

    consumi.append(c)
    produzione.append(p)
    rete.append(rete_h)
    batt_soc.append(batt)

# -----------------------
# PRODUZIONE MATTINA / POMERIGGIO
# -----------------------
produzione_mattina = []
produzione_pomeriggio = []

for idx, p in enumerate(produzione):
    ora = idx % 24
    if 6 <= ora < 12:
        produzione_mattina.append(p)
        produzione_pomeriggio.append(0)
    elif 12 <= ora <= 18:
        produzione_pomeriggio.append(p)
        produzione_mattina.append(0)
    else:
        produzione_mattina.append(0)
        produzione_pomeriggio.append(0)

st.subheader("Produzione FV Mattina / Pomeriggio")
fig_fv = go.Figure()
fig_fv.add_trace(go.Scatter(y=produzione_mattina, name="Mattina", line=dict(color="orange")))
fig_fv.add_trace(go.Scatter(y=produzione_pomeriggio, name="Pomeriggio", line=dict(color="red")))
fig_fv.update_layout(height=400, xaxis_title="Ore", yaxis_title="kWh")
st.plotly_chart(fig_fv, use_container_width=True)

# -----------------------
# COSTI E ROI
# -----------------------
costo = 0
for i, val in enumerate(rete):
    ora = i % 24
    prezzo = 0.35 if 8<=ora<=19 else 0.25
    costo += val*prezzo
ricavo = sum([max(0,prod-c) for c,prod in zip(consumi,produzione)])*0.10
netto = costo - ricavo
costo_impianto = kwp*2000
costo_batt = batt_kwh*800
investimento = costo_impianto + costo_batt
risparmio_annuo = sum(consumi)*0.30 - netto
anni_roi = investimento/risparmio_annuo if risparmio_annuo>0 else None

# -----------------------
# GRAFICI INTERATTIVI
# -----------------------
st.subheader("Consumi e Produzione Oraria")
fig = go.Figure()
fig.add_trace(go.Scatter(y=consumi, name="Consumo"))
fig.add_trace(go.Scatter(y=produzione, name="FV"))
fig.add_trace(go.Scatter(y=rete, name="Rete"))
fig.update_layout(height=400, xaxis_title="Ore", yaxis_title="kWh")
st.plotly_chart(fig, use_container_width=True)

st.subheader("SOC Batteria")
fig2 = px.line(y=batt_soc, labels={"y":"kWh"}, title="Livello Batteria")
st.plotly_chart(fig2, use_container_width=True)

# -----------------------
# CONFRONTO MENSILE
# -----------------------
df_sim = pd.DataFrame({
    "consumo": consumi,
    "produzione": produzione,
    "rete": rete,
    "batt": batt_soc
})

# controllo prima di creare time
if len(df_sim) > 0:
    df_sim["time"] = pd.date_range(start=df.index[0], periods=len(df_sim), freq="H")
else:
    st.error("Errore: df_sim vuoto, impossibile generare intervallo orario")
    st.stop()

df_sim["month"] = df_sim["time"].dt.month
monthly = df_sim.groupby("month")[["consumo","produzione","rete"]].sum().reset_index()
st.subheader("Riepilogo Mensile")
fig3 = px.bar(monthly, x="month", y=["consumo","produzione","rete"], barmode="group")
st.plotly_chart(fig3, use_container_width=True)

# -----------------------
# OUTPUT METRICHE
# -----------------------
st.subheader(f"Risultati {anno}")
st.metric("Consumo totale (kWh)", round(sum(consumi),1))
st.metric("Produzione FV (kWh)", round(sum(produzione),1))
st.metric("Prelievo rete (kWh)", round(sum(rete),1))
st.metric("Costo netto (€)", round(netto,1))
if anni_roi:
    st.write(f"ROI stimato: {round(anni_roi,1)} anni")
else:
    st.write("ROI non positivo con i parametri attuali")