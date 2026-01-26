import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS DESDE PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    if "/edit" in url_base:
        url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"
    else:
        url_csv = url_base

    @st.cache_data(ttl=300)
    def load_data(url):
        data = pd.read_csv(url)
        
        # Limpieza de Tiempo
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # CONVERSIÓN DE FECHA NORMALIZADA (Sin horas para evitar errores de filtro)
        if 'Fecha' in data.columns:
            data['Fecha'] = pd.to_datetime(data['Fecha'], errors='coerce').dt.normalize()
        
        data = data.dropna(subset=['Operador', 'Evento'])
        return data

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    
    # Obtenemos fechas min y max para el calendario
    min_fecha_data = df_raw['Fecha'].min().date()
    max_fecha_data = df_raw['Fecha'].max().date()

    rango_fechas = st.sidebar.date_input(
        "Rango de fechas", 
        [min_fecha_data, max_fecha_data],
        min_value=min_fecha_data,
        max_value=max_fecha_data
    )

    # Filtros de Fábrica y Máquina
    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE LOS FILTROS (Lógica corregida)
    df_filtrado = df_raw.copy()
    
    # Verificamos que el rango de fechas esté completo (Inicio y Fin)
    if isinstance(rango_fechas, list) and len(rango_fechas) == 2:
        inicio, fin = rango_fechas
        # Convertimos los inputs de Streamlit a Datetime de Pandas para comparar
        df_filtrado = df_filtrado[
            (df_filtrado['Fecha'] >= pd.to_datetime(inicio)) & 
            (df_filtrado['Fecha'] <= pd.to_datetime(fin))
        ]
    
    df_filtrado = df_filtrado[df_filtrado['Fábrica'].isin(fábricas) & df_filtrado['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Planta")
    
    # Si el filtro vacía los datos, avisamos al usuario
    if df_filtrado.empty:
        st.warning("No hay datos para los filtros seleccionados. Intenta ampliar el rango de fechas.")
    else:
        # Cálculos
        total_eventos = len(df_filtrado)
        tiempo_prod = df_filtrado[df_filtrado['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        tiempo_fallas = df_filtrado[df_filtrado['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        prom_smed = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('SMED', case=False, na=False)]['Tiempo (Min)'].mean()
        prom_baño = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('BAÑO', case=False, na=False)]['Tiempo (Min)'].mean()
        prom_refrigerio = df_filtrado[df_filtrado['Nivel Evento 4'].str.contains('REFRIGERIO', case=False, na=False)]['Tiempo (Min)'].mean()

        # Mostrar Métricas
        st.subheader(f"🚀 Totales del período seleccionado")
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

        # 7. GRÁFICO: TOP 15 FALLAS
        st.divider()
        st.subheader("⚠️ Top 15 Principales Fallas")
        
        df_solo_fallas = df_filtrado[df_filtrado['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        
        if not df_solo_fallas.empty:
            top_15_fallas = (
                df_solo_fallas.groupby('Nivel Evento 3')['Tiempo (Min)']
                .sum()
                .reset_index()
                .sort_values(by='Tiempo (Min)', ascending=True)
                .tail(15) 
            )
            
            fig_top_fallas = px.bar(
                top_15_fallas, 
                x='Tiempo (Min)', 
                y='Nivel Evento 3', 
                orientation='h',
                color='Tiempo (Min)',
                color_continuous_scale='Reds'
            )
            st.plotly_chart(fig_top_fallas, use_container_width=True)

        # 8. ANÁLISIS DE PARADAS
        st.subheader("🚫 Distribución de las paradas")
        df_paradas = df_filtrado[df_filtrado['Evento'].str.contains('Parada', case=False, na=False)]
        if not df_paradas.empty:
            fig_parada = px.bar(df_paradas, x='Nivel Evento 3', y='Tiempo (Min)', color='Máquina')
            st.plotly_chart(fig_parada, use_container_width=True)

        # 9. VISUALIZACIÓN DE TABLA
        with st.expander("📂 Ver registros completos"):
            st.dataframe(df_filtrado)

except Exception as e:
    st.error(f"Error al cargar datos: {e}")
