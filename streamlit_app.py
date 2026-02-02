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
            
            # Limpieza Numérica Flexible
            cols_to_clean = ['Tiempo', 'Buenas', 'Retrabajo', 'Observadas', 'Ciclo']
            for target in cols_to_clean:
                matches = [c for c in df.columns if target.lower() in c.lower()]
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
            for c_txt in ['Máquina', 'Evento', 'Operador', 'Nivel', 'Código']:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for m in matches: df[m] = df[m].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), process_df(base_export + gid_prod), process_df(base_export + gid_operarios)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_datos, df_prod, df_op_raw = load_data()

# ==========================================
# 3. FILTROS Y LÓGICA
# ==========================================
if df_datos.empty or df_prod.empty:
    st.warning("⚠️ No se pudieron cargar los datos. Verifique la conexión con Google Sheets.")
    st.stop()

# Identificar columnas de Máquina dinámicamente
col_maq_datos = next((c for c in df_datos.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), 'Máquina')
col_maq_prod = next((c for c in df_prod.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), 'Máquina')

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_datos['Fecha_Filtro'].min().date(), df_datos['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="main_range")

st.sidebar.divider()
maquinas_dispo = sorted(df_datos[col_maq_datos].unique())
sel_maq = st.sidebar.multiselect("Seleccionar Máquinas", maquinas_dispo, default=maquinas_dispo)

if len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    f_datos = df_datos[(df_datos['Fecha_Filtro'] >= ini) & (df_datos['Fecha_Filtro'] <= fin) & (df_datos[col_maq_datos].isin(sel_maq))]
    f_prod = df_prod[(df_prod['Fecha_Filtro'] >= ini) & (df_prod['Fecha_Filtro'] <= fin) & (df_prod[col_maq_prod].isin(sel_maq))]
    f_op = df_op_raw[(df_op_raw['Fecha_Filtro'] >= ini) & (df_op_raw['Fecha_Filtro'] <= fin)] if not df_op_raw.empty else pd.DataFrame()
else:
    st.stop()

# ==========================================
# 4. MOTOR DE CÁLCULO OEE REAL (DINÁMICO)
# ==========================================
def calc_oee_logic(df_d, df_p):
    if df_d.empty or df_p.empty: return 0.0, 0.0, 0.0, 0.0
    
    # Identificar columnas clave en producción
    c_ciclo = next((c for c in df_p.columns if 'ciclo' in c.lower()), None)
    c_buenas = next((c for c in df_p.columns if 'buenas' in c.lower()), 'Buenas')
    c_ret = next((c for c in df_p.columns if 'retrabajo' in c.lower()), 'Retrabajo')
    c_obs = next((c for c in df_p.columns if 'observadas' in c.lower()), 'Observadas')

    # 1. DISPONIBILIDAD
    t_prod = df_d[df_d['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_total = df_d['Tiempo (Min)'].sum()
    disp = t_prod / t_total if t_total > 0 else 0
    
    # 2. CALIDAD
    buenas = df_p[c_buenas].sum()
    total_piezas = buenas + df_p[c_ret].sum() + df_p[c_obs].sum()
    cal = buenas / total_piezas if total_piezas > 0 else 0
    
    # 3. PERFORMANCE
    if c_ciclo and total_piezas > 0 and t_prod > 0:
        # Piezas Teóricas = (Tiempo de producción en seg) / Tiempo de Ciclo (seg)
        # Usamos el promedio de ciclo para el set de datos filtrado
        ciclo_medio = df_p[df_p[c_ciclo] > 0][c_ciclo].mean()
        piezas_teoricas = (t_prod * 60) / ciclo_medio if ciclo_medio > 0 else 0
        perf = total_piezas / piezas_teoricas if piezas_teoricas > 0 else 0
    else: perf = 0
    
    perf = min(perf, 1.0)
    oee = disp * perf * cal
    return oee, disp, perf, cal

# ==========================================
# 5. VISUALIZACIÓN DE KPIs
# ==========================================
st.title("🏭 INDICADORES DE EFICIENCIA (OEE REAL)")


oee_g, disp_g, perf_g, cal_g = calc_oee_logic(f_datos, f_prod)

c1, c2, c3, c4 = st.columns(4)
c1.metric("OEE GLOBAL", f"{oee_g:.1%}")
c2.metric("Disponibilidad", f"{disp_g:.1%}")
c3.metric("Performance", f"{perf_g:.1%}")
c4.metric("Calidad", f"{cal_g:.1%}")

# ==========================================
# 6. DESGLOSE POR MÁQUINA
# ==========================================
st.markdown("---")
with st.expander("🔍 Análisis Matemático por Unidad", expanded=False):
    res_maq = []
    for m in sel_maq:
        d_m = f_datos[f_datos[col_maq_datos] == m]
        p_m = f_prod[f_prod[col_maq_prod] == m]
        o, d, p, cal_m = calc_oee_logic(d_m, p_m)
        if d > 0 or cal_m > 0:
            res_maq.append({"Máquina": m, "OEE": o, "Disponibilidad": d, "Performance": p, "Calidad": cal_m})
    
    if res_maq:
        st.table(pd.DataFrame(res_maq).style.format({
            "OEE": "{:.1%}", "Disponibilidad": "{:.1%}", "Performance": "{:.1%}", "Calidad": "{:.1%}"
        }))

# ==========================================
# 7. MÓDULOS ADICIONALES (PRODUCCIÓN Y FALLAS)
# ==========================================
st.markdown("---")
t_p, t_f, t_op = st.tabs(["📦 Producción", "📉 Fallas", "👤 Operarios"])

with t_p:
    if not f_prod.empty:
        c_buenas = next((c for c in f_prod.columns if 'buenas' in c.lower()), 'Buenas')
        df_p_plot = f_prod.groupby(col_maq_prod)[[c_buenas]].sum().reset_index()
        st.plotly_chart(px.bar(df_p_plot, x=col_maq_prod, y=c_buenas, title="Total Piezas Buenas"), use_container_width=True)

with t_f:
    df_fallas = f_datos[f_datos['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    if not df_fallas.empty:
        top_f = df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
        fig_f = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Pareto de Fallas", color='Tiempo (Min)', color_continuous_scale='Reds')
        st.plotly_chart(fig_f, use_container_width=True)

with t_op:
    if not f_op.empty:
        col_op_name = next((c for c in f_op.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        df_dias = f_op.groupby(col_op_name)['Fecha_Filtro'].nunique().reset_index(name='Días')
        st.dataframe(df_dias.sort_values('Días', ascending=False), use_container_width=True, hide_index=True)
