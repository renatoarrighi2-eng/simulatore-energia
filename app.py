import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import math
import random

st.set_page_config(layout="wide")
st.title("⚡ Simulatore Energia Casa - Livorno")
st.markdown("Fotovoltaico + Batteria + Profilo orario avanzato (produzione FV simulata)")

# -----------------------
# INPUT UTENTE
# -----------------------
mq = st.slider("Superficie casa (m²)", 30, 150, 47)
kwp = st.slider("Potenza FV (kW)", 1.0, 6.0, 3.0)
batt_kwh = st.slider("Batteria (kWh)", 0.0, 10.0, 5.0)

# -----------------------
# SIMULAZIONE 7 GIORNI ORARIO
# -----------------------
soc = 0.5
batt = batt_kwh * soc

consumi = []
produzione = []
rete = []

for i in range(24*7):
    ora = i % 24

    # temperatura / umidità semplificate
    T = 15 + 10 * math.sin((i/24-80)*2*math.pi/365) + random.gauss(0,2)
    U = 60 + 15*math.sin(i/24*2*math.pi/365) + random.uniform(-5,5)

    # consumo orario
    base = 0.2
    if 12 <= ora <= 18:
        base += 0.3
    elif 19 <= ora <= 23:
        base += 0.5
    cool = max(T-24,0)*0.02*(mq/50)
    heat = max(18-T,0)*0.03*(mq/50)
    deum = 0.1 if U>70 else 0
    c = base + cool + heat + deum

    # produzione FV (curva generica)
    rad = max(0, math.sin(math.pi*(ora/24))*1000)
    p = rad/1000 * kwp * 0.75

    # gestione batteria
    autoconsumo = min(c,p)
    surplus = p - autoconsumo
    spazio = batt_kwh - batt
    carica = min(surplus*0.9, spazio)
    batt += carica
    immesso = max(surplus - carica,0)
    richiesta = c - autoconsumo
    scarica = min(richiesta, batt*0.9)
    batt -= scarica/0.9
    rete_h = richiesta - scarica

    consumi.append(c)
    produzione.append(p)
    rete.append(rete_h)

# -----------------------
# COSTI FASCE ORARIE
# -----------------------
costo = 0
for i, val in enumerate(rete):
    ora = i % 24
    prezzo = 0.35 if 8<=ora<=19 else 0.25
    costo += val*prezzo
ricavo = sum([max(0,prod-c) for c,prod in zip(consumi,produzione)])*0.10
netto = costo - ricavo

# -----------------------
# OUTPUT
# -----------------------
st.subheader("Risultati 7 giorni")
st.metric("Consumo (kWh)", round(sum(consumi),1))
st.metric("Produzione FV (kWh)", round(sum(produzione),1))
st.metric("Prelievo rete (kWh)", round(sum(rete),1))
st.metric("Costo netto (€)", round(netto,1))

# GRAFICO
fig, ax = plt.subplots()
ax.plot(consumi,label="Consumo")
ax.plot(produzione,label="FV")
ax.plot(rete,label="Rete")
ax.legend()
st.pyplot(fig)

# ROI
st.subheader("ROI stimato")
costo_impianto = kwp*2000
costo_batt = batt_kwh*800
investimento = costo_impianto + costo_batt
risparmio_annuo = sum(consumi)*0.30 - netto
if risparmio_annuo>0:
    anni = investimento/risparmio_annuo
    st.write(f"ROI: {round(anni,1)} anni")