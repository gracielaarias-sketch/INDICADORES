import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_gsheets import GSheetsConnection


# Crear la conexión
conn = st.connection("gsheets", type=GSheetsConnection)

# Limpiamos la URL de cualquier carácter invisible antes de usarla
url_directa = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()

# Leer los datos usando la URL limpia
df = conn.read(spreadsheet=url_directa, ttl="5m", gid=0)

st.write("¡Datos cargados correctamente!")
st.dataframe(df.head())

# Configuración inicial
st.set_page_config(page_title="Dashboard de Producción", layout="wide")
st.title("🏭 Control de Eventos de Planta")

# Limpieza de datos (basado en tu estructura)
df = df.dropna(subset=['Operador', 'Evento'])
# Convertimos el tiempo a numérico por si acaso
df['Tiempo (Min)'] = pd.to_numeric(df['Tiempo (Min)'].str.replace(',', '.'), errors='coerce')

# --- FILTROS LATERALES ---
st.sidebar.header("Filtros de Análisis")
fábrica = st.sidebar.multiselect("Fábrica", df['Fábrica'].unique(), default=df['Fábrica'].unique())
máquina = st.sidebar.multiselect("Máquina", df['Máquina'].unique(), default=df['Máquina'].unique())

df_filtrado = df[(df['Fábrica'].isin(fábrica)) & (df['Máquina'].isin(máquina))]

# --- MÉTRICAS PRINCIPALES ---
m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Total Eventos", len(df_filtrado))
with m2:
    tiempo_total = df_filtrado['Tiempo (Min)'].sum()
    st.metric("Tiempo Total (Min)", f"{tiempo_total:,.2f}")
with m3:
    produccion_count = len(df_filtrado[df_filtrado['Evento'] == 'Producción'])
    st.metric("Eventos de Producción", produccion_count)

# --- GRÁFICOS ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("⏱️ Tiempo por Tipo de Evento")
    # Gráfico que muestra cuánto tiempo se pierde en 'Parada' vs 'Producción'
    fig_evento = px.pie(df_filtrado, values='Tiempo (Min)', names='Evento', 
                         hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
    st.plotly_chart(fig_evento, use_container_width=True)

with col2:
    st.subheader("👤 Rendimiento por Operador")
    # Gráfico de barras comparando el tiempo total por operador
    fig_operador = px.bar(df_filtrado, x='Operador', y='Tiempo (Min)', color='Evento',
                          title="Distribución de Tiempo por Operador", barmode='group')
    st.plotly_chart(fig_operador, use_container_width=True)

# --- DETALLE DE PARADAS ---
st.subheader("🚫 Análisis de Causas de Parada")
df_paradas = df_filtrado[df_filtrado['Evento'] == 'Parada']
if not df_paradas.empty:
    fig_parada = px.bar(df_paradas, x='Nivel Evento 3', y='Tiempo (Min)', 
                         color='Máquina', title="Tiempo Perdido por Motivo de Parada")
    st.plotly_chart(fig_parada, use_container_width=True)
else:
    st.info("No hay eventos de parada en la selección actual.")

# Mostrar tabla original
with st.expander("Ver registros detallados"):
    st.dataframe(df_filtrado)
