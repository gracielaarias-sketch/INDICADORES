import streamlit as st
import pandas as pd
import plotly.express as px

# 1. Obtenemos la URL de los Secrets
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # 2. Convertimos la URL normal en una URL de descarga directa de CSV
    # Esto reemplaza el final de la URL automáticamente
    if "/edit" in url_base:
        url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"
    else:
        url_csv = url_base

    # 3. Leer los datos con Pandas
    @st.cache_data(ttl=300) # Se actualiza cada 5 minutos
    def load_data(url):
        return pd.read_csv(url)

    df = load_data(url_csv)

    # 4. Mostrar los datos
    st.success("¡Datos cargados con éxito!")
    st.metric("Total de Registros", len(df))
    st.dataframe(df)

except Exception as e:
    st.error(f"Error al cargar los datos: {e}")
    st.info("Asegúrate de que la URL en Secrets sea la correcta y que la hoja sea pública (Cualquier persona con el enlace puede ver).")

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
# 1. Total Eventos
total_eventos = len(df)

# 2. Total Tiempo de Fallas (Suma de minutos)
# Filtramos donde la columna Nivel Evento 3 contenga la palabra "FALLA"
tiempo_fallas = df[df['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()

# 3. Promedio SMED
promedio_smed = df[df['Nivel Evento 4'].str.contains('SMED', case=False, na=False)]['Tiempo (Min)'].mean()

# 4. Promedio Baño
promedio_baño = df[df['Nivel Evento 4'].str.contains('BAÑO', case=False, na=False)]['Tiempo (Min)'].mean()

# 5. Promedio Refrigerio
promedio_refrigerio = df[df['Nivel Evento 4'].str.contains('REFRIGERIO', case=False, na=False)]['Tiempo (Min)'].mean()

# --- MOSTRAR MÉTRICAS ---

# Primera fila: Totales
col1, col2 = st.columns(2)
with col1:
    st.metric("Total Eventos", f"{total_eventos}")
with col2:
    st.metric("Total Tiempo Fallas", f"{tiempo_fallas:,.2f} min")

st.markdown("---")

# Segunda fila: Promedios
st.subheader("⏱️ Promedios de Tiempo")
m1, m2, m3 = st.columns(3)

# Usamos fillna(0) por si no hay registros de ese tipo aún
m1.metric("Promedio SMED", f"{0 if pd.isna(promedio_smed) else promedio_smed:.2f} min")
m2.metric("Promedio Baño", f"{0 if pd.isna(promedio_baño) else promedio_baño:.2f} min")
m3.metric("Promedio Refrigerio", f"{0 if pd.isna(promedio_refrigerio) else promedio_refrigerio:.2f} min")

st.divider()

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
