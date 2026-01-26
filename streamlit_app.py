import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import time

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS DESDE PANDAS (MÉTODO ROBUSTO)
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

    @st.cache_data(ttl=300)
    def load_data(url):
        # Lectura directa con Pandas
        data = pd.read_csv(url)
        
        # Limpieza de columna Tiempo (Min)
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # NORMALIZACIÓN CRÍTICA DE FECHAS Y HORAS
        if 'Fecha' in data.columns:
            # Convertimos a datetime completo
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            # Creamos columna de Fecha normalizada (solo día) para el filtro de calendario
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            # Extraemos la hora para el filtro de franja horaria
            data['Hora_Solo'] = data['Fecha_DT'].dt.time
        
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Tiempo")
    
    # Rango de fechas para el calendario
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Rango de fechas", [min_d, max_d], min_value=min_d, max_value=max_d)

    # Filtro de Franja Horaria (Inicio y Cierre)
    st.sidebar.header("⏰ Franja Horaria")
    hora_rango = st.sidebar.slider(
        "Selecciona horario de turno:",
        value=(time(0, 0), time(23, 59)),
        format="HH:mm"
    )
    h_inicio, h_fin = hora_rango

    # Filtros de Categoría
    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    df_f = df_raw.copy()
    
    # Filtro de Fecha (Comparación Datetime)
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        inicio_dt, fin_dt = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_f[(df_f['Fecha_Filtro'] >= inicio_dt) & (df_f['Fecha_Filtro'] <= fin_dt)]
    elif len(rango) == 1:
        st.stop()
    
    # Filtro de Hora
    df_f = df_f[(df_f['Hora_Solo'] >= h_inicio) & (df_f['Hora_Solo'] <= h_fin)]
    
    # Filtros de Fábrica y Máquina
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Producción")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron registros para los filtros seleccionados.")
    else:
        # Cálculos de Totales
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Función para promedios (buscando específicamente en columnas de evento)
        cols_busqueda = [c for c in df_f.columns if 'Nivel Evento' in c] + ['Evento']
        def get_avg(texto):
            mask = df_f[cols_busqueda].apply(lambda x: x.str.contains(texto, case=False, na=False)).any(axis=1)
            mean_val = df_f[mask]['Tiempo (Min)'].mean()
            return 0 if pd.isna(mean_val) else mean_val

        # Visualización de métricas
        st.subheader("🚀 Indicadores del Periodo y Turno")
        c1, c2, c3 = st.columns(3)
        c1.metric("Registros Filtrados", len(df_f))
        c2.metric("Total Producción", f"{t_prod:,.1f} min")
        c3.metric("Total Tiempo Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")

        st.subheader("⏱️ Promedios por Actividad")
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{get_avg('SMED'):.2f} min")
        p2.metric("Promedio Baño", f"{get_avg('BAÑO'):.2f} min")
        p3.metric("Promedio Refrigerio", f"{get_avg('REFRIGERIO'):.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]

        # DISTRIBUCIÓN Y OPERADORES
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("⏱️ Tiempo por Evento")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with g2:
            st.subheader("👤 Rendimiento por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # --- TOP 15 FALLAS ---
        st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
        df_fallas_det = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_fallas_det.empty:
            top15 = df_fallas_det.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_bar = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No hay fallas detalladas en este periodo.")

        st.divider()

        # --- MAPA DE CALOR ---
        st.subheader(f"🔥 Mapa de Calor: Máquina vs {col_6}")
        df_heatmap = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_heatmap.empty:
            pivot_hm = df_heatmap.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        with st.expander("📂 Ver registros detallados"):
            st.dataframe(df_f)

except Exception as e:
    st.error(f"Error crítico: {e}")
