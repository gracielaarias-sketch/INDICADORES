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
        
        # CONVERSIÓN ROBUSTA DE FECHA
        if 'Fecha' in data.columns:
            # Convertimos a datetime y luego a DATE (solo año-mes-día) para evitar errores de hora
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            data['Fecha_Solo'] = data['Fecha_DT'].dt.date
        
        data = data.dropna(subset=['Operador', 'Evento'])
        return data

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    
    # Obtenemos el rango real de los datos
    min_data = df_raw['Fecha_Solo'].min()
    max_data = df_raw['Fecha_Solo'].max()

    rango_fechas = st.sidebar.date_input(
        "Rango de fechas", 
        [min_data, max_data],
        min_value=min_data,
        max_value=max_data
    )

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE LOS FILTROS
    df_filtrado = df_raw.copy()
    
    # Lógica de filtrado de fecha corregida
    if isinstance(rango_fechas, (list, tuple)) and len(rango_fechas) == 2:
        inicio, fin = rango_fechas
        # Filtramos directamente contra el objeto date
        df_filtrado = df_filtrado[
            (df_filtrado['Fecha_Solo'] >= inicio) & 
            (df_filtrado['Fecha_Solo'] <= fin)
        ]
    elif len(rango_fechas) == 1:
        st.info("💡 Por favor, selecciona la fecha de fin en el calendario.")
        st.stop()

    # Filtros de Fábrica y Máquina
    df_filtrado = df_filtrado[df_filtrado['Fábrica'].isin(fábricas) & df_filtrado['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Planta")
    
    if df_filtrado.empty:
        st.error("❌ No se encontraron datos para los filtros seleccionados.")
        st.info(f"Rango seleccionado: {rango_fechas}")
        # DEBUG: Esto ayuda a ver qué fechas hay en el sistema si falla
        with st.expander("Ayuda técnica: Fechas detectadas"):
            st.write(df_raw['Fecha_Solo'].unique())
    else:
        # --- CÁLCULOS SOBRE EL DF FILTRADO ---
        total_eventos = len(df_filtrado)
        tiempo_prod = df_filtrado[df_filtrado['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        tiempo_fallas = df_filtrado[df_filtrado['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Métricas
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Eventos", total_eventos)
        c2.metric("Tiempo Producción", f"{tiempo_prod:,.1f} min")
        c3.metric("Tiempo Total Fallas", f"{tiempo_fallas:,.1f} min")

        st.divider()

        # 6. GRÁFICOS
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_evento = px.pie(df_filtrado, values='Tiempo (Min)', names='Evento', hole=0.4, title="Tiempo por Evento")
            st.plotly_chart(fig_evento, use_container_width=True)
        with col_g2:
            fig_operador = px.bar(df_filtrado, x='Operador', y='Tiempo (Min)', color='Evento', title="Rendimiento por Operador")
            st.plotly_chart(fig_operador, use_container_width=True)


# 1. MAPA DE CALOR (Máquina vs Nivel Evento 6)
st.subheader("🔥 Mapa de Calor: Máquinas vs Causa Raíz (Nivel 6)")
df_heatmap = df_filtrado[df_filtrado['Evento'].str.contains('Parada|Falla', case=False, na=False)]

if 'Nivel Evento 6' in df_heatmap.columns and not df_heatmap.empty:
    # Agrupamos por Máquina y el detalle del Nivel 6
    pivot_hm = df_heatmap.groupby(['Máquina', 'Nivel Evento 6'])['Tiempo (Min)'].sum().reset_index()
    
    fig_hm = px.density_heatmap(
        pivot_hm, 
        x='Nivel Evento 6', 
        y="Máquina", 
        z="Tiempo (Min)",
        color_continuous_scale="Viridis",
        text_auto=True,
        labels={'Nivel Evento 6': 'Causa Específica', 'Tiempo (Min)': 'Minutos Totales'}
    )
    st.plotly_chart(fig_hm, use_container_width=True)
else:
    st.info("No hay datos suficientes en 'Nivel Evento 6' para generar el Mapa de Calor.")

st.divider()

        # 8. TABLA
        with st.expander("📂 Ver registros completos"):
            st.dataframe(df_filtrado)

except Exception as e:
    st.error(f"Error crítico: {e}")
