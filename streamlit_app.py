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
    hr { margin-top: 2rem; margin-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS ROBUSTA
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        try:
            url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        except Exception:
            st.error("⚠️ No se encontró la configuración de secretos (.streamlit/secrets.toml).")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        gid_datos = "0"             # Paros
        gid_oee = "1767654796"      # OEE
        gid_prod = "315437448"      # PRODUCCION
        gid_operarios = "354131379" # PERFO OPERARIOS

        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception: return pd.DataFrame()
            
            # Limpieza Numérica
            cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia', 'Cumplimiento', 'Meta']
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace(',', '.')
                    df[match] = df[match].str.replace('%', '')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            # Limpieza Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Rellenar Textos
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Código', 'Operador', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), \
               process_df(base_export + gid_oee), \
               process_df(base_export + gid_prod), \
               process_df(base_export + gid_operarios)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")
opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()
else:
    st.stop()

# ==========================================
# 4. FUNCIONES KPI
# ==========================================
def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    if not datos.empty:
        for key, col_search in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                vals = pd.to_numeric(datos[actual_col], errors='coerce').dropna()
                if not vals.empty:
                    v = vals.mean()
                    m[key] = float(v/100 if v > 1.1 else v)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

def show_historical_oee(filter_name, title):
    if not df_oee_f.empty:
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filter_name.upper()).any(), axis=1)
        df_proc = df_oee_f[mask].copy()
        col_oee = next((c for c in df_proc.columns if 'OEE' in c.upper()), None)
        if col_oee and not df_proc.empty:
            df_proc['OEE_Num'] = pd.to_numeric(df_proc[col_oee], errors='coerce')
            if df_proc['OEE_Num'].mean() <= 1.1: df_proc['OEE_Num'] *= 100
            trend = df_proc.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
            fig = px.line(trend, x='Fecha_Filtro', y='OEE_Num', markers=True, title=f'Tendencia OEE: {title}')
            fig.add_hline(y=85, line_dash="dot", annotation_text="Meta 85%", line_color="green")
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 5. MÓDULO OEE Y APERTURAS
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics('GENERAL'))
with st.expander("📉 Ver Evolución Histórica OEE General"):
    show_historical_oee('GENERAL', 'Planta')

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    st.markdown("#### Total Estampado")
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
    with st.expander("Ver detalle por Líneas"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{linea}**")
            show_metric_row(get_metrics(linea))
            st.markdown("---")
with t2:
    st.markdown("#### Total Soldadura")
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')
    with st.expander("Ver detalle"):
        st.markdown("**Celdas Robotizadas**")
        show_metric_row(get_metrics('CELDA'))
        st.markdown("---")
        st.markdown("**PRP**")
        show_metric_row(get_metrics('PRP'))

# ==========================================
# 6. MÓDULO BAÑO Y REFRIGERIO
# ==========================================
st.markdown("---")
with st.expander("☕ Tiempos de Baño y Refrigerio", expanded=False):
    tab_b, tab_r = st.tabs(["Baño", "Refrigerio"])
    for i, label in enumerate(["Baño", "Refrigerio"]):
        with [tab_b, tab_r][i]:
            df_desc = df_f[df_f['Nivel Evento 4'].astype(str).str.contains(label, case=False)]
            if not df_desc.empty:
                res = df_desc.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                res.columns = ['Operador', 'Total Min', 'Promedio Min', 'Eventos']
                st.dataframe(res.sort_values('Total Min', ascending=False), use_container_width=True, hide_index=True)
            else: st.info(f"Sin registros de {label}")

# ==========================================
# 7. PERFORMANCE POR OPERARIO
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS (OPERARIOS)")
with st.expander("👉 Ver Análisis de Performance", expanded=False):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if 'nombre' in c.lower() or 'operador' in c.lower()), 'Operador')
        sel_ops = st.multiselect("Seleccione Operarios:", sorted(df_op_f[col_op].unique()), key="perf_ops")
        if sel_ops:
            df_filt_op = df_op_f[df_op_f[col_op].isin(sel_ops)].sort_values('Fecha_Filtro')
            st.plotly_chart(px.line(df_filt_op, x='Fecha_Filtro', y='Performance', color=col_op, markers=True, title="Evolución de Performance"), use_container_width=True)

# ==========================================
# 8. MÓDULO PRODUCCIÓN (GRÁFICO Y TABLAS DETALLADAS)
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    col_maq = next((c for c in df_prod_f.columns if 'máquina' in c.lower()), 'Máquina')
    col_cod = next((c for c in df_prod_f.columns if 'código' in c.lower()), 'Código')
    c_b, c_r, c_o = 'Buenas', 'Retrabajo', 'Observadas'
    
    # Gráfico de Barras Apiladas
    df_stack = df_prod_f.groupby(col_maq)[[c_b, c_r, c_o]].sum().reset_index()
    st.plotly_chart(px.bar(df_stack, x=col_maq, y=[c_b, c_r, c_o], title="Balance de Producción por Máquina", barmode='stack'), use_container_width=True)

    with st.expander("📂 Tablas de Producción Detallada"):
        df_prod_f['Fecha'] = df_prod_f['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
        df_det = df_prod_f.groupby([col_cod, col_maq, 'Fecha'])[[c_b, c_r, c_o]].sum().reset_index()
        st.dataframe(df_det.sort_values([col_cod, 'Fecha'], ascending=[True, False]), use_container_width=True, hide_index=True)

# ==========================================
# 9. TIEMPOS: PROD VS PARADA POR OPERARIO
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos")
if not df_f.empty:
    df_f['Tipo_Evento'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Tipo_Evento', title="Eficiencia de Tiempo Global", color_discrete_sequence=['#2ecc71', '#e74c3c'], hole=0.4), use_container_width=True)
    with col2:
        fig_op = px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Tipo_Evento', title="Producción vs Parada por Operario", barmode='group')
        st.plotly_chart(fig_op, use_container_width=True)

# ==========================================
# 10. ANÁLISIS DE FALLAS (CON GRADIENTE Y FILTRO)
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")
col_cat, col_det = 'Nivel Evento 3', 'Nivel Evento 6'
df_fallas = df_f[df_f[col_cat].astype(str).str.contains('FALLA', case=False)].copy()

if not df_fallas.empty:
    sel_maq_f = st.multiselect("Filtrar máquinas para fallas:", sorted(df_fallas['Máquina'].unique()), default=sorted(df_fallas['Máquina'].unique()), key="falla_maq")
    df_filt_f = df_fallas[df_fallas['Máquina'].isin(sel_maq_f)]
    
    top_f = df_filt_f.groupby(col_det)['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig_f = px.bar(top_f, x='Tiempo (Min)', y=col_det, orientation='h', title="Top 15 Fallas (Gradiente Rojo)", text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig_f.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    fig_f.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, height=600)
    st.plotly_chart(fig_f, use_container_width=True)
    

st.divider()
with st.expander("📂 Registro Crudo de Eventos"):
    st.dataframe(df_f, use_container_width=True)
