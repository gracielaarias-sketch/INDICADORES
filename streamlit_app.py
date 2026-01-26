import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS DESDE PANDAS (MÉTODO CSV DIRECTO)
# Obtenemos la URL de los Secrets
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # Convertimos la URL de Google Sheets en una URL de descarga de CSV
    if "/edit" in url_base:
        url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"
    else:
        url_csv = url_base

    @st.cache_data(ttl=300) # Se actualiza cada 5 minutos
    def load_data(url):
        # Leer los datos directamente con Pandas
        data = pd.read_csv(url)
        
        # Limpieza de Tiempo (convertir comas a puntos y a número)
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # Conversión de Fecha
        if 'Fecha' in data.columns:
            data['Fecha'] = pd.to_datetime(data['Fecha'], errors='coerce')
        
        # Eliminar filas donde Operador o Evento estén vacíos
        data = data.dropna(subset=['Operador', 'Evento'])
        return data

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

    # 4. APLICACIÓN DE LOS FILTROS
    df_filtrado = df_raw.copy()
    
    if isinstance(rango_fechas, (list, tuple)) and len(rango_fechas) == 2:
        inicio, fin = rango_fechas
        df_filtrado = df_filtrado[(df_filtrado['Fecha'].dt.date >= inicio) & (df_filtrado['Fecha'].dt.date <= fin)]
    
    df_filtrado = df_filtrado[df_filtrado['Fábrica'].isin(fábricas) & df_filtrado['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Planta")
    
    # Cálculos
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
    c2.metric("Tiempo Producción", f"{tiempo_prod:,.1f} min")
    c3.metric("Tiempo Fallas", f"{tiempo_fallas:,.1f} min")

    st.subheader("⏱️ Promedios de Tiempo (Min)")
    m1, m2, m3 = st.columns(3)
    
    def format_avg(val):
        return f"{0 if pd.isna(val) else val:.2f}"

    m1.metric("Promedio SMED", format_avg(prom_smed))
    m2.metric("Promedio Baño", format_avg(prom_baño))
    m3.metric("Promedio Refrigerio", format_avg(prom_refrigerio))

    st.divider()

    # 6. GRÁFICOS INTERACTIVOS
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("⏱️ Tiempo por Tipo de Evento")
        fig_evento = px.pie(df_filtrado, values='Tiempo (Min)', names='Evento', hole=0.4)
        st.plotly_chart(fig_evento, use_container_width=True)

    with col_g2:
        st.subheader("👤 Rendimiento por Operador")
        fig_operador = px.bar(df_filtrado, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group')
        st.plotly_chart(fig_operador, use_container_width=True)

    # 7. ANÁLISIS DE PARADAS
    st.subheader("🚫 Distribucion de las paradas")
    df_paradas = df_filtrado[df_filtrado['Evento'].str.contains('Parada', case=False, na=False)]
    if not df_paradas.empty:
        fig_parada = px.bar(df_paradas, x='Nivel Evento 3', y='Tiempo (Min)', color='Máquina')
        st.plotly_chart(fig_parada, use_container_width=True)
    else:
        st.info("No hay paradas registradas para el filtro seleccionado.")

    # 8. VISUALIZACIÓN DE TABLA
    with st.expander("📂 Ver registros completos"):
        st.dataframe(df_filtrado)

except Exception as e:
    st.error(f"Error al cargar datos: {e}")
    st.info("Asegúrate de que la hoja de Google sea pública ('Cualquier persona con el enlace').")
