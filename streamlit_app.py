El código que enviaste tiene algunos errores de estructura (como el st.set_page_config en el medio y bloques try/except entrecortados). He consolidado todo en una sola versión limpia, funcional y con todos los filtros (Fecha, Fábrica y Máquina) actuando al mismo tiempo sobre los gráficos y las métricas.

Copia este código íntegro en tu archivo streamlit_app.py:

Python

import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA (Debe ser lo primero)
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS
url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

@st.cache_data(ttl=300)
def load_data(url):
    data = pd.read_csv(url)
    # Limpieza de Tiempo
    if 'Tiempo (Min)' in data.columns:
        data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
        data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
    
    # Conversión de Fecha
    if 'Fecha' in data.columns:
        data['Fecha'] = pd.to_datetime(data['Fecha'], errors='coerce')
    
    # Limpieza de filas vacías críticas
    data = data.dropna(subset=['Operador', 'Evento'])
    return data

try:
    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    
    # Filtro de Fecha
    min_fecha = df_raw['Fecha'].min().date()
    max_fecha = df_raw['Fecha'].max().date()
    rango_fechas = st.sidebar.date_input("Rango de fechas", [min_fecha, max_fecha])

    # Filtros de Fábrica y Máquina
    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS (CASCADA)
    df_filtrado = df_raw.copy()
    
    # Aplicar fecha
    if isinstance(rango_fechas, list) and len(rango_fechas) == 2:
        inicio, fin = rango_fechas
        df_filtrado = df_filtrado[(df_filtrado['Fecha'].dt.date >= inicio) & (df_filtrado['Fecha'].dt.date <= fin)]
    
    # Aplicar Fábrica y Máquina
    df_filtrado = df_filtrado[df_filtrado['Fábrica'].isin(fábricas) & df_filtrado['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Control de Eventos de Planta")
    
    # Cálculos basados en el DF filtrado
    total_eventos = len(df_filtrado)
    tiempo_prod = df_filtrado[df_filtrado['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
    tiempo_fallas = df_filtrado[df_filtrado['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
    
    prom_smed = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('SMED', case=False, na=False)]['Tiempo (Min)'].mean()
    prom_baño = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('BAÑO', case=False, na=False)]['Tiempo (Min)'].mean()
    prom_refrigerio = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('REFRIGERIO', case=False, na=False)]['Tiempo (Min)'].mean()

    # Mostrar Métricas
    st.subheader("🚀 Totales Generales")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Eventos", total_eventos)
    c2.metric("Tiempo Producción", f"{tiempo_prod:,.2f} min")
    c3.metric("Tiempo Fallas", f"{tiempo_fallas:,.2f} min")

    st.subheader("⏱️ Promedios de Tiempos (Min)")
    m1, m2, m3 = st.columns(3)
    m1.metric("Promedio SMED", f"{0 if pd.isna(prom_smed) else prom_smed:.2f}")
    m2.metric("Promedio Baño", f"{0 if pd.isna(prom_baño) else prom_baño:.2f}")
    m3.metric("Promedio Refrigerio", f"{0 if pd.isna(prom_refrigerio) else prom_refrigerio:.2f}")

    st.divider()

    # 6. GRÁFICOS
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("⏱️ Tiempo por Tipo de Evento")
        fig_evento = px.pie(df_filtrado, values='Tiempo (Min)', names='Evento', hole=0.4)
        st.plotly_chart(fig_evento, use_container_width=True)

    with col_g2:
        st.subheader("👤 Tiempo por Operador")
        fig_operador = px.bar(df_filtrado, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group')
        st.plotly_chart(fig_operador, use_container_width=True)

    # 7. DETALLE DE PARADAS
    st.subheader("🚫 Análisis de Causas de Parada")
    df_paradas = df_filtrado[df_filtrado['Evento'] == 'Parada']
    if not df_paradas.empty:
        fig_parada = px.bar(df_paradas, x='Nivel Evento 3', y='Tiempo (Min)', color='Máquina')
        st.plotly_chart(fig_parada, use_container_width=True)
    else:
        st.info("No hay paradas en el rango seleccionado.")

    # 8. TABLA DE DATOS
    with st.expander("📂 Ver registros detallados"):
        st.dataframe(df_filtrado)

except Exception as e:
    st.error(f"Error crítico: {e}")
