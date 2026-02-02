import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(
    page_title="Indicadores FAMMA - OEE Real", 
    layout="wide", 
    page_icon="🏭", 
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 22px; color: #1f77b4; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .formula-box { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS ROBUSTA
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        gid_datos, gid_prod, gid_operarios = "0", "315437448", "354131379"
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except: return pd.DataFrame()
            
            # Limpieza Numérica
            cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'Tiempo de Ciclo', 'Ciclo', 'Performance', 'Meta']
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for m in matches:
                    df[m] = df[m].astype(str).str.replace(',', '.')
                    df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0.0)
            
            # Limpieza Fechas
            col_f = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_f:
                df['Fecha_DT'] = pd.to_datetime(df[col_f], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Limpieza Textos
            for c_txt in ['Máquina', 'Evento', 'Operador', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6', 'Código']:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for m in matches: df[m] = df[m].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), process_df(base_export + gid_prod), process_df(base_export + gid_operarios)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_datos, df_prod, df_op_raw = load_data()

# ==========================================
# 3. FILTROS Y LÓGICA DE FILTRADO
# ==========================================
if df_datos.empty or df_prod.empty:
    st.warning("⚠️ No se pudieron cargar las pestañas de Datos o Producción.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_datos['Fecha_Filtro'].min().date(), df_datos['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="main_range")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros de Planta")
fábricas = sorted(df_datos['Fábrica'].unique()) if 'Fábrica' in df_datos.columns else []
sel_fab = st.sidebar.multiselect("Fábrica", fábricas, default=fábricas)

maquinas_dispo = sorted(df_datos[df_datos['Fábrica'].isin(sel_fab)]['Máquina'].unique())
sel_maq = st.sidebar.multiselect("Máquinas", maquinas_dispo, default=maquinas_dispo)

if len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    f_datos = df_datos[(df_datos['Fecha_Filtro'] >= ini) & (df_datos['Fecha_Filtro'] <= fin) & (df_datos['Máquina'].isin(sel_maq))]
    f_prod = df_prod[(df_prod['Fecha_Filtro'] >= ini) & (df_prod['Fecha_Filtro'] <= fin) & (df_prod['Máquina'].isin(sel_maq))]
    f_op = df_op_raw[(df_op_raw['Fecha_Filtro'] >= ini) & (df_op_raw['Fecha_Filtro'] <= fin)] if not df_op_raw.empty else pd.DataFrame()
else:
    st.info("Seleccione un rango de fechas.")
    st.stop()

# ==========================================
# 4. MOTOR DE CÁLCULO OEE REAL
# ==========================================
def calc_oee_logic(df_d, df_p):
    if df_d.empty or df_p.empty: return 0, 0, 0, 0
    
    # 1. DISPONIBILIDAD = Tiempo Prod / (Tiempo Prod + Tiempo Parada)
    t_prod = df_d[df_d['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_total = df_d['Tiempo (Min)'].sum()
    disp = t_prod / t_total if t_total > 0 else 0
    
    # 2. CALIDAD = Buenas / (Buenas + Retrabajo + Observadas)
    buenas = df_p['Buenas'].sum()
    total_piezas = buenas + df_p['Retrabajo'].sum() + df_p['Observadas'].sum()
    cal = buenas / total_piezas if total_piezas > 0 else 0
    
    # 3. PERFORMANCE = Piezas Totales / (Capacidad Teórica)
    # Capacidad Teórica = Tiempo Prod (Min) / Tiempo de Ciclo (seg) * 60
    # Obtenemos un tiempo de ciclo ponderado por las piezas producidas
    if not df_p.empty and total_piezas > 0:
        # Relación: si el ciclo es en segundos, 1 min produce 60/ciclo piezas.
        df_p['Capacidad_Teorica'] = (t_prod * 60) / df_p['Tiempo de Ciclo'].replace(0, 999999)
        perf = total_piezas / df_p['Capacidad_Teorica'].sum() if df_p['Capacidad_Teorica'].sum() > 0 else 0
    else: perf = 0
    
    perf = min(perf, 1.0) # Cap al 100% para ruidos de data entry
    oee = disp * perf * cal
    return oee, disp, perf, cal

# ==========================================
# 5. DASHBOARD - MÉTRICAS PRINCIPALES
# ==========================================
st.title("🏭 DASHBOARD DE INDICADORES FAMMA")
oee_g, disp_g, perf_g, cal_g = calc_oee_logic(f_datos, f_prod)

c1, c2, c3, c4 = st.columns(4)
c1.metric("OEE REAL GLOBAL", f"{oee_g:.1%}")
c2.metric("Disponibilidad", f"{disp_g:.1%}")
c3.metric("Performance", f"{perf_g:.1%}")
c4.metric("Calidad", f"{cal_g:.1%}")



# ==========================================
# 6. DESPLEGABLE MATEMÁTICO POR MÁQUINA
# ==========================================
st.markdown("---")
with st.expander("🔍 Análisis Matemático Detallado por Máquina", expanded=False):
    st.info("Cálculos realizados cruzando las pestañas de 'Datos' (Tiempos) y 'Producción' (Ciclos y Piezas).")
    res_maq = []
    for m in sel_maq:
        d_m = f_datos[f_datos['Máquina'] == m]
        p_m = f_prod[f_prod['Máquina'] == m]
        o, d, p, c = calc_oee_logic(d_m, p_m)
        if d > 0 or c > 0:
            res_maq.append({"Máquina": m, "OEE": o, "Disponibilidad": d, "Performance": p, "Calidad": c})
    
    df_res_maq = pd.DataFrame(res_maq)
    if not df_res_maq.empty:
        st.dataframe(df_res_maq.style.format({
            "OEE": "{:.1%}", "Disponibilidad": "{:.1%}", "Performance": "{:.1%}", "Calidad": "{:.1%}"
        }), use_container_width=True, hide_index=True)

# ==========================================
# 7. MÓDULO INDICADORES DIARIOS (OPERARIOS)
# ==========================================
st.markdown("---")
st.header("📈 Indicadores por Operador")
t_op1, t_op2 = st.tabs(["Performance y Días", "Baño y Refrigerio"])

with t_op1:
    if not f_op.empty:
        col_op_name = next((c for c in f_op.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        
        c_op1, c_op2 = st.columns([1, 2])
        with c_op1:
            st.subheader("Días Registrados")
            df_dias = f_op.groupby(col_op_name)['Fecha_Filtro'].nunique().reset_index(name='Días')
            st.dataframe(df_dias.sort_values('Días', ascending=False), use_container_width=True, hide_index=True)
        
        with c_op2:
            sel_ops = st.multiselect("Graficar Performance:", sorted(f_op[col_op_name].unique()))
            if sel_ops:
                fig_perf = px.line(f_op[f_op[col_op_name].isin(sel_ops)], x='Fecha_Filtro', y='Performance', color=col_op_name, markers=True)
                st.plotly_chart(fig_perf, use_container_width=True)

with t_op2:
    df_desc = f_datos[f_datos['Nivel Evento 4'].astype(str).str.contains('Baño|Refrigerio', case=False)]
    if not df_desc.empty:
        res_desc = df_desc.groupby(['Operador', 'Nivel Evento 4'])['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
        st.dataframe(res_desc, use_container_width=True, hide_index=True)

# ==========================================
# 8. MÓDULO PRODUCCIÓN DETALLADA
# ==========================================
st.markdown("---")
st.header("📦 Producción y Calidad")
if not f_prod.empty:
    # Gráfico Apilado
    df_st = f_prod.groupby('Máquina')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
    fig_prod = px.bar(df_st, x='Máquina', y=['Buenas', 'Retrabajo', 'Observadas'], title="Balance de Piezas por Máquina", barmode='stack')
    st.plotly_chart(fig_prod, use_container_width=True)
    
    with st.expander("📂 Ver Tabla Detallada (Código, Máquina, Fecha)"):
        f_prod['Fecha'] = f_prod['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
        col_cod = next((c for c in f_prod.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
        st.dataframe(f_prod[[col_cod, 'Máquina', 'Fecha', 'Buenas', 'Retrabajo', 'Observadas']].sort_values([col_cod, 'Fecha'], ascending=[True, False]), use_container_width=True, hide_index=True)

# ==========================================
# 9. ANÁLISIS DE TIEMPOS Y FALLAS
# ==========================================
st.markdown("---")
st.header("📉 Análisis de Fallas (Top 15)")
df_f = f_datos[f_datos['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_f.empty:
    m_f = st.multiselect("Filtrar Máquina para Fallas:", sorted(df_f['Máquina'].unique()), default=sorted(df_f['Máquina'].unique()))
    top_f = df_f[df_f['Máquina'].isin(m_f)].groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    
    fig_fallas = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Pareto de Fallas", text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig_fallas.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    fig_fallas.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
    st.plotly_chart(fig_fallas, use_container_width=True)

st.divider()
with st.expander("📂 Registro Crudo de Paros (Datos)"):
    st.dataframe(f_datos, use_container_width=True)
