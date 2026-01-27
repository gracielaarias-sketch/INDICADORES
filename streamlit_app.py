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

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS ROBUSTA (3 FUENTES)
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        try:
            url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        except Exception:
            st.error("⚠️ No se encontró la configuración de secretos (.streamlit/secrets.toml).")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # ---------------------------------------------------------
        # 🟢 CONFIGURACIÓN DE GIDs (IDs de las pestañas)
        # ---------------------------------------------------------
        gid_datos = "0"             # Datos crudos de paros
        gid_oee = "1767654796"      # Datos de OEE
        gid_prod = "315437448"    # <--- ¡PEGA AQUÍ EL GID DE LA PESTAÑA PRODUCCION!
        # ---------------------------------------------------------

        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        url_csv_datos = base_export + gid_datos
        url_csv_oee = base_export + gid_oee
        url_csv_prod = base_export + gid_prod

        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception:
                return pd.DataFrame()
            
            # Limpieza General de columnas numéricas
            cols_num = ['Tiempo (Min)', 'Cantidad', 'Piezas', 'Produccion', 'Total']
            for c in cols_num:
                # Buscamos columnas que contengan estos nombres (case insensitive)
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace(',', '.')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            # Limpieza de Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Rellenar textos nulos
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Código', 'Producto', 'Referencia']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('Sin Especificar').astype(str)
            
            return df

        # Procesamos los 3 DataFrames
        df1 = process_df(url_csv_datos)
        df2 = process_df(url_csv_oee)
        df3 = process_df(url_csv_prod)
        
        return df1, df2, df3

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# Carga inicial
df_raw, df_oee_raw, df_prod_raw = load_data()

# ==========================================
# 3. FILTROS
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados en la hoja principal.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()

rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")

opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

# APLICAR FILTROS A LOS 3 DATAFRAMES
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    
    # 1. Datos Paros
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # 2. Datos OEE
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    else:
        df_oee_f = df_oee_raw
        
    # 3. Datos Producción (NUEVO)
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
        # Intentar filtrar por máquina si existe la columna
        col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
        if col_maq_prod:
            df_prod_f = df_prod_f[df_prod_f[col_maq_prod].isin(máquinas)]
    else:
        df_prod_f = pd.DataFrame()
else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 4. SECCIÓN OEE (KPIs)
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    
    if not datos.empty:
        cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
        for key, col_search in cols_map.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                serie_limpia = datos[actual_col].astype(str).str.replace('%', '').str.replace(',', '.')
                vals = pd.to_numeric(serie_limpia, errors='coerce').dropna()
                if not vals.empty:
                    val_promedio = vals.mean()
                    m[key] = float(val_promedio / 100 if val_promedio > 1.0 else val_promedio)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

# KPI Principal
st.caption("Promedios del periodo")
show_metric_row(get_metrics('GENERAL')) 

st.divider() # Separador visual

t1, t2 = st.tabs(["🔨 Estampado", "🔥 Soldadura"])

with t1:
    st.markdown("#### Total Estampado")
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("Ver detalle por Líneas"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{linea}**")
            show_metric_row(get_metrics(linea))
            st.markdown("---")

with t2:
    st.markdown("#### Total Soldadura")
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("Ver detalle"):
        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("**Celdas Robotizadas**")
            show_metric_row(get_metrics('CELDA'))
        with c_b:
            st.markdown("**Prensas PRP**")
            show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. SEPARADOR Y GRÁFICO HISTÓRICO
# ==========================================
st.markdown("---") # <--- SEPARADOR SOLICITADO
st.header("📉 Evolución Histórica")

if not df_oee_f.empty and 'OEE' in df_oee_f.columns:
    df_trend = df_oee_f.copy()
    if df_trend['OEE'].dtype == 'object':
        df_trend['OEE_Num'] = df_trend['OEE'].astype(str).str.replace('%','').str.replace(',','.').astype(float)
    else:
        df_trend['OEE_Num'] = df_trend['OEE']
    
    trend_data = df_trend.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
    
    fig_trend = px.line(trend_data, x='Fecha_Filtro', y='OEE_Num', markers=True,
                        title='Tendencia Diaria del OEE (%)', labels={'OEE_Num': 'OEE', 'Fecha_Filtro': 'Fecha'})
    fig_trend.add_hline(y=85, line_dash="dot", annotation_text="Meta (85%)", line_color="green")
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("No hay datos históricos para graficar.")

# ==========================================
# 6. NUEVA SECCIÓN: PRODUCCIÓN (BAR CHART)
# ==========================================
st.markdown("---")
st.header("📦 Producción Realizada")

if not df_prod_f.empty:
    # Detección automática de columnas
    col_codigo = next((c for c in df_prod_f.columns if any(x in c.lower() for x in ['código', 'codigo', 'producto', 'referencia'])), None)
    col_cantidad = next((c for c in df_prod_f.columns if any(x in c.lower() for x in ['cantidad', 'piezas', 'unidades', 'produccion'])), None)
    col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)

    if col_codigo and col_cantidad and col_maq_prod:
        # KPI Total
        total_p = df_prod_f[col_cantidad].sum()
        st.metric("Total Piezas Fabricadas", f"{total_p:,.0f}")

        # Agrupación
        prod_grouped = df_prod_f.groupby([col_maq_prod, col_codigo])[col_cantidad].sum().reset_index()
        
        # Gráfico
        fig_prod = px.bar(
            prod_grouped,
            x=col_maq_prod,
            y=col_cantidad,
            color=col_codigo,
            title="Producción por Máquina y Código",
            labels={col_cantidad: 'Cantidad', col_maq_prod: 'Máquina', col_codigo: 'Producto'},
            text_auto='.2s'
        )
        fig_prod.update_traces(textposition="inside", cliponaxis=False)
        st.plotly_chart(fig_prod, use_container_width=True)
    else:
        st.warning(f"No se pudieron identificar automáticamente las columnas de Producto, Cantidad o Máquina en la hoja de Producción. Columnas disponibles: {list(df_prod_f.columns)}")
else:
    st.info("No hay datos de producción disponibles para este periodo.")

# ==========================================
# 7. ANÁLISIS DE TIEMPOS (PAROS)
# ==========================================
st.markdown("---")
st.header("⏱️ Análisis de Tiempos y Paros")

if not df_f.empty:
    t_prod = df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]['Tiempo (Min)'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Minutos Producción", f"{t_prod:,.0f}")
    c2.metric("Minutos Fallas", f"{t_fallas:,.0f}", delta_color="inverse")
    c3.metric("Total Eventos", len(df_f))

    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
    with g2:
        col_falla = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
        if not df_fallas.empty:
            top_fallas = df_fallas.groupby(col_falla)['Tiempo (Min)'].sum().nlargest(10).reset_index().sort_values('Tiempo (Min)', ascending=True)
            st.plotly_chart(px.bar(top_fallas, x='Tiempo (Min)', y=col_falla, orientation='h', title="Top 10 Fallas", color='Tiempo (Min)'), use_container_width=True)

# ==========================================
# 8. TABLA DETALLADA
# ==========================================
st.divider()
with st.expander("📂 Ver Registro Detallado de Eventos", expanded=False):
    if not df_f.empty:
        st.dataframe(df_f, use_container_width=True, hide_index=True)
    else:
        st.info("No hay datos.")
