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
        gid_datos, gid_prod, gid_operarios = "0", "315437448", "354131379"
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except: return pd.DataFrame()
            
            # Limpieza Numérica Flexible
            for target in ['Tiempo', 'Buenas', 'Retrabajo', 'Observadas', 'Ciclo']:
                matches = [c for c in df.columns if target.lower() in c.lower()]
                for m in matches:
                    df[m] = df[m].astype(str).str.replace(',', '.')
                    df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0.0)
            
            col_f = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_f:
                df['Fecha_DT'] = pd.to_datetime(df[col_f], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            for c_txt in ['Máquina', 'Evento', 'Operador', 'Nivel', 'Código', 'Fábrica']:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for m in matches: df[m] = df[m].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), process_df(base_export + gid_prod), process_df(base_export + gid_operarios)
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_datos, df_prod, df_op_raw = load_data()

# ==========================================
# 3. FILTROS (ESTILO ORIGINAL)
# ==========================================
if df_datos.empty or df_prod.empty:
    st.warning("⚠️ Datos no encontrados en Google Sheets.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_datos['Fecha_Filtro'].min().date(), df_datos['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")
fábricas = sorted(df_datos['Fábrica'].unique())
sel_fab = st.sidebar.multiselect("Fábrica", fábricas, default=fábricas)

maquinas_dispo = sorted(df_datos[df_datos['Fábrica'].isin(sel_fab)]['Máquina'].unique())
sel_maq = st.sidebar.multiselect("Máquina", maquinas_dispo, default=maquinas_dispo)

if len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    f_datos = df_datos[(df_datos['Fecha_Filtro'] >= ini) & (df_datos['Fecha_Filtro'] <= fin) & (df_datos['Máquina'].isin(sel_maq))]
    f_prod = df_prod[(df_prod['Fecha_Filtro'] >= ini) & (df_prod['Fecha_Filtro'] <= fin) & (df_prod['Máquina'].isin(sel_maq))]
    f_op = df_op_raw[(df_op_raw['Fecha_Filtro'] >= ini) & (df_op_raw['Fecha_Filtro'] <= fin)]
else: st.stop()

# ==========================================
# 4. MOTOR DE CÁLCULO OEE REAL (LÓGICA PIEZAS/HORA)
# ==========================================
def calc_oee_real(df_d, df_p):
    if df_d.empty or df_p.empty: return {'OEE':0,'DISP':0,'PERF':0,'CAL':0, 'TEO':0, 'REAL':0}
    
    # 1. DISPONIBILIDAD
    t_prod = df_d[df_d['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_total = df_d['Tiempo (Min)'].sum()
    disp = t_prod / t_total if t_total > 0 else 0
    
    # 2. CALIDAD
    c_b, c_r, c_o = 'Buenas', 'Retrabajo', 'Observadas'
    buenas = df_p[c_b].sum()
    reales_totales = buenas + df_p[c_r].sum() + df_p[c_o].sum()
    cal = buenas / reales_totales if reales_totales > 0 else 0
    
    # 3. PERFORMANCE (Lógica: Piezas/Hora = 60 / Ciclo)
    c_ciclo = next((c for c in df_p.columns if 'ciclo' in c.lower()), None)
    if c_ciclo and t_prod > 0:
        # Piezas por minuto = 1 / Ciclo (si el ciclo es en minutos)
        # O Piezas por hora = 60 / Ciclo
        ciclo_medio = df_p[df_p[c_ciclo] > 0][c_ciclo].mean()
        # Capacidad = (60 / Ciclo) * (Tiempo Prod en horas)
        piezas_estimadas = (60 / ciclo_medio) * (t_prod / 60) if ciclo_medio > 0 else 0
        perf = min(reales_totales / piezas_estimadas, 1.0) if piezas_estimadas > 0 else 0
    else: 
        piezas_estimadas = 0
        perf = 0
    
    return {'OEE': disp*perf*cal, 'DISP': disp, 'PERF': perf, 'CAL': cal, 'TEO': piezas_estimadas, 'REAL': reales_totales}

# ==========================================
# 5. DASHBOARD PRINCIPAL
# ==========================================
st.title("🏭 INDICADORES FAMMA")
m_g = calc_oee_real(f_datos, f_prod)

c1, c2, c3, c4 = st.columns(4)
c1.metric("OEE Real", f"{m_g['OEE']:.1%}")
c2.metric("Disponibilidad", f"{m_g['DISP']:.1%}")
c3.metric("Performance", f"{m_g['PERF']:.1%}")
c4.metric("Calidad", f"{m_g['CAL']:.1%}")



st.divider()

t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    m_est = calc_oee_real(f_datos[f_datos['Fábrica'].str.contains('ESTAMPADO', case=False)], f_prod[f_prod['Máquina'].str.contains('L1|L2|L3|L4', case=False)])
    st.metric("OEE Estampado", f"{m_est['OEE']:.1%}")
    with st.expander("Detalle por Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            m_l = calc_oee_real(f_datos[f_datos['Máquina'].str.contains(l)], f_prod[f_prod['Máquina'].str.contains(l)])
            st.write(f"**{l}**: {m_l['OEE']:.1%} OEE | {m_l['DISP']:.1%} Disp | {m_l['PERF']:.1%} Perf")

with t2:
    m_sold = calc_oee_real(f_datos[f_datos['Fábrica'].str.contains('SOLDADURA', case=False)], f_prod[f_prod['Máquina'].str.contains('CELDA|PRP', case=False)])
    st.metric("OEE Soldadura", f"{m_sold['OEE']:.1%}")

# ==========================================
# 6. DESPLEGABLE MATEMÁTICO (AUDITORÍA)
# ==========================================
st.markdown("---")
with st.expander("🔍 Auditoría de Performance: Real vs Estimado", expanded=False):
    res_list = []
    for m in sel_maq:
        res = calc_oee_real(f_datos[f_datos['Máquina']==m], f_prod[f_prod['Máquina']==m])
        if res['DISP'] > 0 or res['REAL'] > 0:
            res_list.append({
                "Máquina": m,
                "Piezas Reales": int(res['REAL']),
                "Piezas Estimadas (Teóricas)": int(res['TEO']),
                "Performance": f"{res['PERF']:.1%}",
                "OEE": f"{res['OEE']:.1%}"
            })
    st.table(pd.DataFrame(res_list))

# ==========================================
# 7. OPERARIOS, PRODUCCIÓN Y FALLAS
# ==========================================
st.markdown("---")
col_izq, col_der = st.columns(2)

with col_izq:
    st.header("👤 Performance Operarios")
    col_op_n = next((c for c in f_op.columns if 'operador' in c.lower() or 'nombre' in c.lower()), 'Operador')
    df_dias = f_op.groupby(col_op_n)['Fecha_Filtro'].nunique().reset_index(name='Días')
    st.dataframe(df_dias.sort_values('Días', ascending=False), use_container_width=True, hide_index=True)
    
    with st.expander("☕ Tiempos de Baño y Refrigerio"):
        df_desc = f_datos[f_datos['Nivel Evento 4'].astype(str).str.contains('Baño|Refrigerio', case=False)]
        st.dataframe(df_desc.groupby(['Operador', 'Nivel Evento 4'])['Tiempo (Min)'].sum(), use_container_width=True)

with col_der:
    st.header("📦 Balance de Producción")
    df_st = f_prod.groupby('Máquina')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
    st.plotly_chart(px.bar(df_st, x='Máquina', y=['Buenas', 'Retrabajo', 'Observadas'], barmode='stack'), use_container_width=True)

st.markdown("---")
st.header("📉 Pareto de Fallas")
df_f = f_datos[f_datos['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
if not df_f.empty:
    top_f = df_f.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig_f = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig_f.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    st.plotly_chart(fig_f, use_container_width=True)

st.divider()
with st.expander("📂 Registro Crudo"):
    st.dataframe(f_datos, use_container_width=True)
