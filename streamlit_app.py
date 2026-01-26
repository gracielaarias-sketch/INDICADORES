import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

    @st.cache_data(ttl=300)
    def load_data(url):
        data = pd.read_csv(url)
        # Limpieza de Tiempo
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # Conversión de Fecha a DateTime (Normalizado)
        if 'Fecha' in data.columns:
            data['Fecha'] = pd.to_datetime(data['Fecha'], errors='coerce').dt.normalize()
        
        data = data.dropna(subset=['Operador', 'Evento'])
        return data

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    
    min_fecha_data = df_raw['Fecha'].min().date()
    max_fecha_data = df_raw['Fecha'].max().date()

    # Ajuste 1: Manejo de error si el usuario limpia el filtro o selecciona incompleto
    rango_fechas = st.sidebar.date_input(
        "Rango de fechas", 
        [min_fecha_data, max_fecha_data],
        min_value=min_fecha_data,
        max_value=max_fecha_data
    )

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE LOS FILTROS
    df_filtrado = df_raw.copy()
    
    # Ajuste 2: Validación robusta del rango
    if isinstance(rango_fechas, (list, tuple)) and len(rango_fechas) == 2:
        inicio, fin = rango_fechas
        # Convertimos a datetime para asegurar coincidencia con el dataframe
        df_filtrado = df_filtrado[
            (df_filtrado['Fecha'] >= pd.to_datetime(inicio)) & 
            (df_filtrado['Fecha'] <= pd.to_datetime(fin))
        ]
    elif len(rango_fechas) == 1:
        # Si solo hay una fecha seleccionada, mostramos un aviso y detenemos ejecución
        st.warning("Selecciona la fecha final para filtrar los datos.")
        st.stop()

    # Filtro de Fábrica y Máquina
    df_filtrado = df_filtrado[df_filtrado['Fábrica'].isin(fábricas) & df_filtrado['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Planta")
    
    if df_filtrado.empty:
        st.error("No se encontraron datos para los filtros seleccionados.")
    else:
        # Cálculos sobre el DF FILTRADO
        total_eventos = len(df_filtrado)
        
        # Ajuste 3: Búsqueda exacta de términos clave
        tiempo_prod = df_filtrado[df_filtrado['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        tiempo_fallas = df_filtrado[df_filtrado['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Métricas de tiempo específicas
        prom_smed = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('SMED', case=False, na=False)]['Tiempo (Min)'].mean()
        prom_baño = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('BAÑO', case=False, na=False)]['Tiempo (Min)'].mean()
        prom_refrigerio = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('REFRIGERIO', case=False, na=False)]['Tiempo (Min)'].mean()

        # Visualización de métricas
        st.subheader(f"🚀 Indicadores del Período Seleccionado")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Eventos", total_eventos)
        c2.metric("Producción Total", f"{tiempo_prod:,.1f} min")
        c3.metric("Tiempo de Fallas", f"{tiempo_fallas:,.1f} min")

        st.subheader("⏱️ Promedios por Categoría")
        m1, m2, m3 = st.columns(3)
        
        def format_avg(val):
            return f"{0 if pd.isna(val) else val:.2f} min"

        m1.metric("Promedio SMED", format_avg(prom_smed))
        m2.metric("Promedio Baño", format_avg(prom_baño))
        m3.metric("Promedio Refrigerio", format_avg(prom_refrigerio))

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

        # 7. TOP 15 FALLAS
        st.divider()
        st.subheader("⚠️ Top 15 Principales Fallas")
        df_solo_fallas = df_filtrado[df_filtrado['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        
        if not df_solo_fallas.empty:
            top_15 = df_solo_fallas.groupby('Nivel Evento 3')['Tiempo (Min)'].sum().reset_index()
            top_15 = top_15.sort_values(by='Tiempo (Min)', ascending=True).tail(15)
            
            fig_top = px.bar(top_15, x='Tiempo (Min)', y='Nivel Evento 3', orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            st.plotly_chart(fig_top, use_container_width=True)

        # 8. ANÁLISIS DE PARADAS
        st.subheader("🚫 Distribución de Paradas")
        df_paradas = df_filtrado[df_filtrado['Evento'].str.contains('Parada', case=False, na=False)]
        if not df_paradas.empty:
            fig_parada = px.bar(df_paradas, x='Nivel Evento 3', y='Tiempo (Min)', color='Máquina')
            st.plotly_chart(fig_parada, use_container_width=True)

        # 9. TABLA
        with st.expander("📂 Ver registros completos"):
            st.dataframe(df_filtrado)

except Exception as e:
    st.error(f"Se produjo un error al cargar los datos: {e}")
