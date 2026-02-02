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

        gid_datos, gid_oee, gid_prod, gid_operarios = "0", "1767654796", "315437448", "354131379"
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception: return pd.DataFrame()
            
            # Limpieza Numérica
            cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia', 'Ciclo', 'Tiempo de Ciclo']
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
            
            # Limpieza Textos
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Código', 'Operador', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6', 'Nombre']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), process_df(base_export + gid_oee), \
               process_df(base_export + gid_prod), process_df(base_export + gid_operarios)
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw_datos, df_raw_oee, df_raw_prod, df_raw_operarios = load_data()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
if df_raw_datos.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw_datos['Fecha_Filtro'].min().date(), df_raw_datos['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")
fábricas = st.sidebar.multiselect("Fábrica", sorted(df_raw_datos['Fábrica'].unique()), default=sorted(df_raw_datos['Fábrica'].unique()))
df_temp = df_raw_datos[df_raw_datos['Fábrica'].isin(fábricas)]
máquinas_globales = st.sidebar.multiselect("Máquina", sorted(df_temp['Máquina'].unique()), default=sorted(df_temp['Máquina'].unique()))

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    # Filtrar todos los DataFrames por el periodo y máquinas
    df_f_datos = df_raw_datos[(df_raw_datos['Fecha_Filtro'] >= ini) & (df_raw_datos['Fecha_Filtro'] <= fin) & (df_raw_datos['Máquina'].isin(máquinas_globales))]
    df_f_prod = df_raw_prod[(df_raw_prod['Fecha_Filtro'] >= ini) & (df_raw_prod['Fecha_Filtro'] <= fin) & (df_raw_prod['Máquina'].isin(máquinas_globales))]
    df_f_op = df_raw_operarios[(df_raw_operarios['Fecha_Filtro'] >= ini) & (df_raw_operarios['Fecha_Filtro'] <= fin)]
    # Para históricos usamos df_raw_oee filtrado por máquinas
    df_oee_f = df_raw_oee[(df_raw_oee['Fecha_Filtro'] >= ini) & (df_raw_oee['Fecha_Filtro'] <= fin) & (df_raw_oee['Máquina'].isin(máquinas_globales))]
else: 
    st.stop()

# ==========================================
# 4. MOTOR DE CÁLCULO OEE CORREGIDO
# ==========================================
def get_real_oee_metrics(df_d, df_p):
    # Inicialización
    metrics = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0, 'REAL_P': 0, 'EST_P': 0}
    if df_d.empty or df_p.empty: return metrics

    # 1. DISPONIBILIDAD (Pestaña Datos)
    t_produccion = df_d[df_d['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_total = df_d['Tiempo (Min)'].sum()
    disp = t_produccion / t_total if t_total > 0 else 0

    # 2. CALIDAD (Pestaña Producción)
    c_b = next((c for c in df_p.columns if 'buenas' in c.lower()), 'Buenas')
    c_r = next((c for c in df_p.columns if 'retrabajo' in c.lower()), 'Retrabajo')
    c_o = next((c for c in df_p.columns if 'observadas' in c.lower()), 'Observadas')
    sum_buenas = df_p[c_b].sum()
    sum_totales = sum_buenas + df_p[c_r].sum() + df_p[c_o].sum()
    cal = sum_buenas / sum_totales if sum_totales > 0 else 0

    # 3. PERFORMANCE (Pestaña Producción)
    # Piezas Estimadas = Tiempo Producción / Tiempo Ciclo
    c_ciclo = next((c for c in df_p.columns if 'ciclo' in c.lower()), None)
    c_tiempo_p = next((c for c in df_p.columns if 'tiempo' in c.lower() and 'min' in c.lower()), None)
    
    if c_ciclo and c_tiempo_p:
        # Evitar división por cero en ciclo
        df_p_calc = df_p[df_p[c_ciclo] > 0].copy()
        df_p_calc['Piezas_Estimadas'] = df_p_calc[c_tiempo_p] / df_p_calc[c_ciclo]
        piezas_estimadas = df_p_calc['Piezas_Estimadas'].sum()
        perf = sum_totales / piezas_estimadas if piezas_estimadas > 0 else 0
    else:
        perf, piezas_estimadas = 0.0, 0.0

    perf = min(perf, 1.0) # Cap al 100%
    metrics.update({'OEE': disp * perf * cal, 'DISP': disp, 'PERF': perf, 'CAL': cal, 'REAL_P': sum_totales, 'EST_P': piezas_estimadas})
    return metrics

# ==========================================
# 5. DASHBOARD PRINCIPAL
# ==========================================
st.title("🏭 INDICADORES FAMMA")
m_g = get_real_oee_metrics(df_f_datos, df_f_prod)

c1, c2, c3, c4 = st.columns(4)
c1.metric("OEE Real", f"{m_g['OEE']:.1%}")
c2.metric("Disponibilidad", f"{m_g['DISP']:.1%}")
c3.metric("Performance", f"{m_g['PERF']:.1%}")
c4.metric("Calidad", f"{m_g['CAL']:.1%}")



st.divider()

# --- Bloque de Históricos y Pestañas ---
def show_historical_oee(filter_name, title):
    if not df_oee_f.empty:
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filter_name.upper()).any(), axis=1)
        df_proc = df_oee_f[mask].copy()
        col_oee = next((c for c in df_proc.columns if 'OEE' in c.upper()), None)
        if col_oee and not df_proc.empty:
            df_proc['OEE_Num'] = pd.to_numeric(df_proc[col_oee], errors='coerce')
            if df_proc['OEE_Num'].mean() <= 1.1: df_proc['OEE_Num'] *= 100
            trend = df_proc.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
            st.plotly_chart(px.line(trend, x='Fecha_Filtro', y='OEE_Num', markers=True, title=f'Tendencia OEE: {title}'), use_container_width=True)

t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    m_est = get_real_oee_metrics(df_f_datos[df_f_datos['Fábrica'].str.contains('ESTAMPADO', case=False)], df_f_prod[df_f_prod['Máquina'].str.contains('L1|L2|L3|L4', case=False)])
    st.columns(4)[0].metric("OEE Estampado", f"{m_est['OEE']:.1%}")
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
    with st.expander("Ver Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            m_l = get_real_oee_metrics(df_f_datos[df_f_datos['Máquina'].str.contains(l)], df_f_prod[df_f_prod['Máquina'].str.contains(l)])
            st.write(f"**{l}**: {m_l['OEE']:.1%} OEE")
with t2:
    m_sold = get_real_oee_metrics(df_f_datos[df_f_datos['Fábrica'].str.contains('SOLDADURA', case=False)], df_f_prod[df_f_prod['Máquina'].str.contains('CELDA|PRP', case=False)])
    st.columns(4)[0].metric("OEE Soldadura", f"{m_sold['OEE']:.1%}")
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')

# ==========================================
# 6. MÓDULO INDICADORES POR OPERADOR
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
with st.expander("👉 Ver Resumen y Evolución de Operarios", expanded=False):
    if not df_f_op.empty:
        col_op = next((c for c in df_f_op.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        df_dias = df_f_op.groupby(col_op)['Fecha_Filtro'].nunique().reset_index(name='Días con Registro')
        st.dataframe(df_dias.sort_values('Días con Registro', ascending=False), use_container_width=True, hide_index=True)
        sel_ops = st.multiselect("Seleccione Operarios:", sorted(df_f_op[col_op].unique()))
        if sel_ops:
            df_perf = df_f_op[df_f_op[col_op].isin(sel_ops)].sort_values('Fecha_Filtro')
            st.plotly_chart(px.line(df_perf, x='Fecha_Filtro', y='Performance', color=col_op, markers=True), use_container_width=True)

# ==========================================
# 7. MÓDULO BAÑO Y REFRIGERIO
# ==========================================
with st.expander("☕ Tiempos de Baño y Refrigerio"):
    tb, tr = st.tabs(["Baño", "Refrigerio"])
    for i, label in enumerate(["Baño", "Refrigerio"]):
        with [tb, tr][i]:
            df_d = df_f_datos[df_f_datos['Nivel Evento 4'].astype(str).str.contains(label, case=False)]
            if not df_d.empty:
                res = df_d.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                st.dataframe(res.sort_values('sum', ascending=False), use_container_width=True)

# ==========================================
# 8. MÓDULO PRODUCCIÓN
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_f_prod.empty:
    c_maq, c_cod, c_b, c_r, c_o = 'Máquina', 'Código', 'Buenas', 'Retrabajo', 'Observadas'
    df_st = df_f_prod.groupby(c_maq)[[c_b, c_r, c_o]].sum().reset_index()
    st.plotly_chart(px.bar(df_st, x=c_maq, y=[c_b, c_r, c_o], title="Balance Producción", barmode='stack'), use_container_width=True)
    with st.expander("📂 Tablas Detalladas"):
        df_f_prod['Fecha_Str'] = df_f_prod['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
        df_tab = df_f_prod.groupby([c_cod, c_maq, 'Fecha_Str'])[[c_b, c_r, c_o]].sum().reset_index()
        st.dataframe(df_tab.sort_values([c_cod, 'Fecha_Str'], ascending=[True, False]), use_container_width=True, hide_index=True)

# ==========================================
# 9. ANÁLISIS DE TIEMPOS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos")
if not df_f_datos.empty:
    df_f_datos['Tipo'] = df_f_datos['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
    col1, col2 = st.columns([1, 2])
    with col1: st.plotly_chart(px.pie(df_f_datos, values='Tiempo (Min)', names='Tipo', title="Uso Global de Tiempo", hole=0.4), use_container_width=True)
    with col2: st.plotly_chart(px.bar(df_f_datos, x='Operador', y='Tiempo (Min)', color='Tipo', title="Tiempo por Operador", barmode='group'), use_container_width=True)

# ==========================================
# 10. ANÁLISIS DE FALLAS
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")
df_fallas = df_f_datos[df_f_datos['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    m_f = st.multiselect("Filtrar Máquinas:", sorted(df_fallas['Máquina'].unique()), default=sorted(df_fallas['Máquina'].unique()))
    top_f = df_fallas[df_fallas['Máquina'].isin(m_f)].groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top 15 Fallas", text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    fig.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, height=600)
    st.plotly_chart(fig, use_container_width=True)

st.divider()
with st.expander("📂 Auditoría: Desglose Matemático por Máquina"):
    audit_data = []
    for m in máquinas_globales:
        res = get_real_oee_metrics(df_f_datos[df_f_datos['Máquina'] == m], df_f_prod[df_f_prod['Máquina'] == m])
        if res['EST_P'] > 0:
            audit_data.append({"Máquina": m, "Piezas Reales": int(res['REAL_P']), "Piezas Estimadas": round(res['EST_P'],1), "Perf %": f"{res['PERF']:.1%}"})
    st.table(pd.DataFrame(audit_data))
