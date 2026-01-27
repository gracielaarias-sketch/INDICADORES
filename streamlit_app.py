import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(
    page_title="Indicadores FAMMA", 
    layout="wide", 
    page_icon="🏭",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para mejorar la visualización de métricas
st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 24px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS ROBUSTA
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        try:
            # Recuperamos la URL desde los secretos
            url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        except Exception:
            st.error("⚠️ No se encontró la configuración de secretos (.streamlit/secrets.toml).")
            return pd.DataFrame(), pd.DataFrame()

        # IDs de las hojas (GIDs) - Verifica que coincidan con tus pestañas de Google Sheets
        gid_datos = "0"          # Pestaña principal de datos crudos
        gid_oee = "1767654796"   # Pestaña de OEE calculado

        url_csv_datos = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_datos}"
        url_csv_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception as e:
                st.warning(f"No se pudo leer el CSV de la URL: {url}. Error: {e}")
                return pd.DataFrame()
            
            # 1. Limpieza de Tiempos
            if 'Tiempo (Min)' in df.columns:
                # Reemplazar comas por puntos y convertir a numérico
                df['Tiempo (Min)'] = df['Tiempo (Min)'].astype(str).str.replace(',', '.')
                df['Tiempo (Min)'] = pd.to_numeric(df['Tiempo (Min)'], errors='coerce').fillna(0.0)
            
            # 2. Limpieza de Fechas
            # Busca columnas que contengan 'fecha'
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                # Creamos columna auxiliar solo fecha (sin hora) para filtros
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                # Eliminamos filas sin fecha válida
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # 3. Rellenar textos nulos para evitar errores en filtros
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Nivel Evento 3', 'Nivel Evento 6']
            for col in cols_texto:
                if col in df.columns:
                    df[col] = df[col].fillna('Sin Especificar').astype(str)
            
            return df

        # Procesamos ambos DataFrames
        df1 = process_df(url_csv_datos)
        df2 = process_df(url_csv_oee)
        
        return df1, df2

    except Exception as e:
        st.error(f"Error general cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Carga inicial
df_raw, df_oee_raw = load_data()

# ==========================================
# 3. FILTROS (SIDEBAR)
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados. Verifique la conexión a Google Sheets.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()

# Widget de calendario
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="audit_range")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros de Planta")

# Filtro Fábrica
opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

# Filtro Máquina (dinámico según fábrica)
df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

# APLICACIÓN DE FILTROS
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    
    # Filtrar Datos Crudos
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # Filtrar Datos OEE (Solo por fecha, ya que el OEE suele venir pre-agregado)
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    else:
        df_oee_f = df_oee_raw
else:
    st.info("Seleccione un rango de fechas válido (Inicio y Fin).")
    st.stop()

# ==========================================
# 4. SECCIÓN OEE (KPIs)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
st.markdown("### OEE Detallado")

def get_metrics(name_filter):
    """Calcula promedios de OEE basados en un filtro de texto sobre el DataFrame filtrado"""
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    
    if df_oee_f.empty: 
        return m
    
    # Filtramos filas que contengan el nombre (ej: 'L1', 'SOLDADURA')
    # Buscamos en todas las columnas por si el nombre está en 'Máquina' o 'Línea'
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    
    if not datos.empty:
        cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
        
        for key, col_search in cols_map.items():
            # Buscar la columna que coincida parcialmente con el nombre (ej: 'Calidad %')
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            
            if actual_col:
                # Limpiar string de % y comas
                serie_limpia = datos[actual_col].astype(str).str.replace('%', '').str.replace(',', '.')
                vals = pd.to_numeric(serie_limpia, errors='coerce').dropna()
                
                if not vals.empty:
                    val_promedio = vals.mean()
                    # Normalización: si el dato viene como 85, es 0.85. Si es 0.85, es 0.85.
                    m[key] = float(val_promedio / 100 if val_promedio > 1.0 else val_promedio)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE Global", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

# KPI Principal
st.caption("Promedios del periodo seleccionado")
show_metric_row(get_metrics('GENERAL')) 
st.divider()

# Tabs por proceso
t1, t2 = st.tabs(["🔨 Estampado", "🔥 Soldadura"])

with t1:
    st.markdown("#### Total Estampado")
    show_metric_row(get_metrics('ESTAMPADO'))
    
    with st.expander("Ver detalle por Líneas (L1-L4)"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**Línea {linea}**")
            show_metric_row(get_metrics(linea))
            st.divider()

with t2:
    st.markdown("#### Total Soldadura")
    show_metric_row(get_metrics('SOLDADURA'))
    
    with st.expander("Ver detalle (Celda, PRP)"):
        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("**Celdas Robotizadas**")
            show_metric_row(get_metrics('CELDA'))
        with c_b:
            st.markdown("**Prensas PRP**")
            show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. GRÁFICO TENDENCIA OEE
# ==========================================
with st.expander("📉 Ver Evolución Histórica del OEE", expanded=False):
    if not df_oee_f.empty and 'OEE' in df_oee_f.columns:
        df_trend = df_oee_f.copy()
        
        # Limpieza para graficar
        if df_trend['OEE'].dtype == 'object':
            df_trend['OEE_Num'] = df_trend['OEE'].astype(str).str.replace('%','').str.replace(',','.').astype(float)
        else:
            df_trend['OEE_Num'] = df_trend['OEE']
        
        # Agrupación por fecha
        trend_data = df_trend.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
        
        fig_trend = px.line(
            trend_data, 
            x='Fecha_Filtro', 
            y='OEE_Num', 
            markers=True,
            title='Tendencia Diaria del OEE (%)',
            labels={'OEE_Num': 'OEE', 'Fecha_Filtro': 'Fecha'}
        )
        # Línea de meta visual
        fig_trend.add_hline(y=85, line_dash="dot", annotation_text="Meta (85%)", line_color="green")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No hay datos históricos de OEE disponibles para graficar.")

st.divider()

# ==========================================
# 6. ANÁLISIS DE TIEMPOS (Producción vs Fallas)
# ==========================================
if not df_f.empty:
    st.subheader("⏱️ Análisis de Tiempos")
    
    # Cálculos agregados
    t_prod = df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]['Tiempo (Min)'].sum()
    
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    col_kpi1.metric("Producción Real (min)", f"{t_prod:,.0f}")
    col_kpi2.metric("Tiempo en Fallas (min)", f"{t_fallas:,.0f}", delta_color="inverse")
    col_kpi3.metric("Total Eventos", len(df_f))

    # Gráficos Distribución y Operadores
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo Total", hole=0.4), use_container_width=True)
    with g2:
        if 'Operador' in df_f.columns:
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Tiempo Reportado por Operador"), use_container_width=True)

    # ---------------------------
    # Top Fallas (Pareto)
    # ---------------------------
    st.divider()
    
    # Determinar columna de detalle de falla
    col_falla_detalle = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
    
    # Filtrar solo eventos que sean fallas
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    
    if not df_fallas.empty:
        st.subheader(f"🛠️ Top 15 Causas de Paro ({col_falla_detalle})")
        
        top15 = df_fallas.groupby(col_falla_detalle)['Tiempo (Min)'].sum().nlargest(15).reset_index().sort_values('Tiempo (Min)', ascending=True)
        
        fig_pareto = px.bar(
            top15, 
            x='Tiempo (Min)', 
            y=col_falla_detalle, 
            orientation='h', 
            text_auto='.0f',
            color='Tiempo (Min)', 
            color_continuous_scale='Reds',
            title="Minutos perdidos por tipo de falla"
        )
        st.plotly_chart(fig_pareto, use_container_width=True)

        st.subheader("🔥 Mapa de Calor: Máquina vs Falla")
        pivot_hm = df_fallas.groupby(['Máquina', col_falla_detalle])['Tiempo (Min)'].sum().reset_index()
        
        # Filtramos para que el heatmap no sea gigante, solo las fallas relevantes (> 10 min)
        pivot_hm = pivot_hm[pivot_hm['Tiempo (Min)'] > 10]
        
        if not pivot_hm.empty:
            fig_hm = px.density_heatmap(
                pivot_hm, 
                x=col_falla_detalle, 
                y="Máquina", 
                z="Tiempo (Min)", 
                color_continuous_scale="Viridis", 
                text_auto=True
            )
            st.plotly_chart(fig_hm, use_container_width=True)
        else:
            st.info("No hay suficientes datos de fallas mayores a 10 min para el mapa de calor.")

# ==========================================
# 7. TABLA DE DATOS DETALLADA
# ==========================================
st.divider()
st.subheader("📋 Registro Detallado de Eventos")

with st.expander("📂 Abrir tabla de datos", expanded=False):
    if not df_f.empty:
        df_export = df_f.copy()
        
        # Formatear fecha para visualización
        if 'Fecha_DT' in df_export.columns:
            df_export['Fecha'] = df_export['Fecha_DT'].dt.strftime('%Y-%m-%d')
            df_export = df_export.sort_values(by=['Fecha_DT', 'Máquina'], ascending=[False, True])
        
        # Definir columnas a mostrar (evita errores si faltan columnas)
        posibles_cols = [
            'Fecha', 'Máquina', 'Operador', 
            'Hora Inicio', 'Hora Fin', 
            'Tiempo (Min)', 'Evento', 
            'Nivel Evento 3', 'Nivel Evento 6'
        ]
        cols_finales = [c for c in posibles_cols if c in df_export.columns]

        st.dataframe(
            df_export[cols_finales], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Tiempo (Min)": st.column_config.NumberColumn("Minutos", format="%.0f min"),
            }
        )
    else:
        st.info("No hay datos para mostrar con los filtros actuales.")
