
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
        url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        gids = {"paros": "0", "oee": "1767654796", "prod": "315437448", "operarios": "354131379"}
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception: return pd.DataFrame()
            
            # Limpieza Numérica
            cols_num = ['Tiempo (Min)', 'Cantidad', 'Piezas', 'Produccion', 'Total', 'Buenas', 'Retrabajo', 
                        'Observadas', 'Tiempo de Ciclo', 'Ciclo', 'Eficiencia', 'Performance', 'OEE', 'Disponibilidad', 'Calidad']
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace(',', '.')
                    df[match] = df[match].str.replace('%', '')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            # Limpieza Fechas
            col_f = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_f:
                df['Fecha_DT'] = pd.to_datetime(df[col_f], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Rellenar Textos
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Operador', 'Nombre', 'Turno', 'Nivel Evento 4']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for m in matches: df[m] = df[m].fillna('').astype(str)
            return df

        return process_df(base_export + gids["paros"]), process_df(base_export + gids["oee"]), \
               process_df(base_export + gids["prod"]), process_df(base_export + gids["operarios"])
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
if df_raw.empty: st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

if not (isinstance(rango, (list, tuple)) and len(rango) == 2): st.stop()
ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
es_rango = ini != fin

st.sidebar.divider()
fábricas = st.sidebar.multiselect("Fábrica", sorted(df_raw['Fábrica'].unique()), default=df_raw['Fábrica'].unique())
máquinas = st.sidebar.multiselect("Máquina", sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique()), 
                                  default=df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin) & df_raw['Máquina'].isin(máquinas)]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]

# ==========================================
# 4. LÓGICA SMART OEE Y KPIs
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0, 'MODO': 'DIRECTO'}
    d_oee = df_oee_f[df_oee_f.apply(lambda r: r.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]
    
    if not es_rango:
        if not d_oee.empty:
            for k, v in {'OEE':'OEE','DISP':'Disponibilidad','PERF':'Performance','CAL':'Calidad'}.items():
                c = next((col for col in d_oee.columns if v.lower() in col.lower()), None)
                if c: 
                    val = d_oee[c].mean()
                    m[k] = val / 100 if val > 1.1 else val
        m['MODO'] = 'INDIVIDUAL'
    else:
        m['MODO'] = 'RECALCULADO'
        d_p = df_prod_f[df_prod_f.apply(lambda r: r.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]
        col_b = next((c for c in d_p.columns if 'buenas' in c.lower()), None)
        col_c = next((c for c in d_p.columns if 'ciclo' in c.lower()), None)
        t_min = df_f[df_f.apply(lambda r: r.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]['Tiempo (Min)'].sum()
        
        if not d_p.empty and col_b and col_c and t_min > 0:
            m['PERF'] = d_p[col_b].sum() / ((t_min * 60) / d_p[col_c].mean())
        
        if not d_oee.empty:
            c_d = next((c for c in d_oee.columns if 'disponibilidad' in c.lower()), None)
            c_q = next((c for c in d_oee.columns if 'calidad' in c.lower()), None)
            if c_d: m['DISP'] = d_oee[c_d].mean() / (100 if d_oee[c_d].mean() > 1.1 else 1)
            if c_q: m['CAL'] = d_oee[c_q].mean() / (100 if d_oee[c_q].mean() > 1.1 else 1)
            m['OEE'] = m['DISP'] * m['PERF'] * m['CAL']
    return m

def show_metric_row(m):
    if m['MODO'] == 'RECALCULADO': st.info("📊 **Modo Rango:** Performance calculada por balance de piezas.")
    else: st.success("📌 **Dato Diario:** Valor directo del registro.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}"); c2.metric("Disp.", f"{m['DISP']:.1%}"); c3.metric("Perf.", f"{m['PERF']:.1%}"); c4.metric("Cal.", f"{m['CAL']:.1%}")

show_metric_row(get_metrics('GENERAL'))

# ==========================================
# 5. NUEVO: PERFORMANCE REAL POR MÁQUINA
# ==========================================
st.markdown("---")
st.header("⚙️ Análisis de Performance Real")

with st.expander("📊 Ver Performance por Máquina (Cálculo Real vs Promedio)", expanded=False):
    if not df_prod_f.empty and not df_f.empty:
        c_mq = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
        c_bn = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
        c_cl = next((c for c in df_prod_f.columns if 'ciclo' in c.lower()), None)
        
        if all([c_mq, c_bn, c_cl]):
            p_dia = df_prod_f.groupby(['Fecha_Filtro', c_mq]).agg({c_bn:'sum', c_cl:'mean'}).reset_index()
            t_dia = df_f.groupby(['Fecha_Filtro', 'Máquina'])['Tiempo (Min)'].sum().reset_index()
            df_res = pd.merge(p_dia, t_dia, left_on=['Fecha_Filtro', c_mq], right_on=['Fecha_Filtro', 'Máquina'])
            df_res['P_Esp'] = (df_res['Tiempo (Min)'] * 60) / df_res[c_cl]
            df_res['Perf_Real'] = (df_res[c_bn] / df_res['P_Esp']).clip(upper=1.2)

            mq_sel = st.selectbox("Máquina para evolución:", sorted(df_res[c_mq].unique()))
            df_plot = df_res[df_res[c_mq] == mq_sel].sort_values('Fecha_Filtro')
            
            st.metric(f"Promedio {mq_sel}", f"{df_plot['Perf_Real'].mean():.1%}")
            fig_p = px.line(df_plot, x='Fecha_Filtro', y='Perf_Real', markers=True, title=f"Evolución Performance: {mq_sel}")
            fig_p.add_hline(y=df_plot['Perf_Real'].mean(), line_dash="dash", line_color="red")
            st.plotly_chart(fig_p, use_container_width=True)
            
            st.dataframe(df_res.groupby(c_mq).agg({c_bn:'sum', 'P_Esp':'sum', 'Perf_Real':'mean'}), use_container_width=True)

# ==========================================
# 6. TABS ESTAMPADO / SOLDADURA
# ==========================================
st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("Detalle Líneas"):
        for l in ['L1','L2','L3','L4']: 
            st.markdown(f"**{l}**"); show_metric_row(get_metrics(l))
with t2:
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("Detalle Celdas"):
        show_metric_row(get_metrics('CELDA'))

# ==========================================
# 7. SECCIONES ORIGINALES (PRODUCCIÓN / FALLAS)
# ==========================================
st.divider()
st.header("Producción General")
if not df_prod_f.empty:
    c_mq_p = next((c for c in df_prod_f.columns if 'maquina' in c.lower()), None)
    c_bn_p = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
    if c_mq_p and c_bn_p:
        st.metric("Total Piezas Buenas", f"{df_prod_f[c_bn_p].sum():,.0f}")
        fig_prod = px.bar(df_prod_f.groupby(c_mq_p)[c_bn_p].sum().reset_index(), x=c_mq_p, y=c_bn_p, title="Producción por Máquina")
        st.plotly_chart(fig_prod, use_container_width=True)

st.divider()
st.header("Análisis de Fallas")
if not df_f.empty:
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    if not df_fallas.empty:
        fig_fallas = px.pie(df_fallas, values='Tiempo (Min)', names='Evento', title="Distribución de Fallas")
        st.plotly_chart(fig_fallas, use_container_width=True)

st.divider()
with st.expander("📂 Ver Registro Detallado"):
    st.dataframe(df_f, use_container_width=True)
