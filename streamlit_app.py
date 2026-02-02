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
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        gid_datos, gid_prod, gid_operarios = "0", "315437448", "354131379"
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception: return pd.DataFrame()
            
            # Limpieza Numérica Flexible
            for target in ['Tiempo', 'Buenas', 'Retrabajo', 'Observadas', 'Ciclo']:
                matches = [c for c in df.columns if target.lower() in c.lower()]
                for m in matches:
                    df[m] = df[m].astype(str).str.replace(',', '.')
                    df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0.0)
            
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
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

df_raw_datos, df_raw_prod, df_raw_operarios = load_data()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
if df_raw_datos.empty or df_raw_prod.empty:
    st.warning("No hay datos cargados en las pestañas principales.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw_datos['Fecha_Filtro'].min().date(), df_raw_datos['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")
fábricas = st.sidebar.multiselect("Fábrica", sorted(df_raw_datos['Fábrica'].unique()), default=sorted(df_raw_datos['Fábrica'].unique()))

opciones_maquina = sorted(df_raw_datos[df_raw_datos['Fábrica'].isin(fábricas)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f_datos = df_raw_datos[(df_raw_datos['Fecha_Filtro'] >= ini) & (df_raw_datos['Fecha_Filtro'] <= fin)]
    df_f_datos = df_f_datos[df_f_datos['Fábrica'].isin(fábricas) & df_f_datos['Máquina'].isin(máquinas_globales)]
    
    df_f_prod = df_raw_prod[(df_raw_prod['Fecha_Filtro'] >= ini) & (df_raw_prod['Fecha_Filtro'] <= fin)]
    df_f_prod = df_f_prod[df_f_prod['Máquina'].isin(máquinas_globales)]
    
    df_f_op = df_raw_operarios[(df_raw_operarios['Fecha_Filtro'] >= ini) & (df_raw_operarios['Fecha_Filtro'] <= fin)] if not df_raw_operarios.empty else pd.DataFrame()
else: st.stop()

# ==========================================
# 4. MOTOR DE CÁLCULO OEE MEJORADO (DINÁMICO)
# ==========================================
def calculate_real_oee(df_d, df_p):
    if df_d.empty or df_p.empty:
        return {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}

    # 1. DISPONIBILIDAD (Desde Datos/Paros)
    t_produccion = df_d[df_d['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_total = df_d['Tiempo (Min)'].sum()
    disp = t_produccion / t_total if t_total > 0 else 0

    # 2. CALIDAD (Desde Producción)
    c_b = next((c for c in df_p.columns if 'buenas' in c.lower()), 'Buenas')
    c_r = next((c for c in df_p.columns if 'retrabajo' in c.lower()), 'Retrabajo')
    c_o = next((c for c in df_p.columns if 'observadas' in c.lower()), 'Observadas')
    
    buenas = df_p[c_b].sum()
    total_reales = buenas + df_p[c_r].sum() + df_p[c_o].sum()
    calidad = buenas / total_reales if total_reales > 0 else 0

    # 3. PERFORMANCE (Desde Producción y Tiempo de Datos)
    # Fórmula solicitada: ((60 / Tiempo Ciclo) / 60) * Tiempo Producción (Min)
    c_ciclo = next((c for c in df_p.columns if 'ciclo' in c.lower()), None)
    if c_ciclo and t_produccion > 0:
        # Calculamos ciclo promedio ponderado por la cantidad de registros en el periodo
        ciclo_promedio = df_p[df_p[c_ciclo] > 0][c_ciclo].mean()
        if ciclo_promedio > 0:
            piezas_estimadas = ((60 / ciclo_promedio) / 60) * t_produccion
            perf = total_reales / piezas_estimadas if piezas_estimadas > 0 else 0
        else: perf = 0
    else: perf = 0

    perf = min(perf, 1.0) # Cap al 100%
    oee = disp * perf * calidad
    return {'OEE': oee, 'DISP': disp, 'PERF': perf, 'CAL': calidad}

# ==========================================
# 5. DASHBOARD PRINCIPAL
# ==========================================
st.title("🏭 INDICADORES FAMMA (OEE REAL)")
metrics_global = calculate_real_oee(df_f_datos, df_f_prod)

c1, c2, c3, c4 = st.columns(4)
c1.metric("OEE Real", f"{metrics_global['OEE']:.1%}")
c2.metric("Disponibilidad", f"{metrics_global['DISP']:.1%}")
c3.metric("Performance", f"{metrics_global['PERF']:.1%}")
c4.metric("Calidad", f"{metrics_global['CAL']:.1%}")



st.divider()

# --- Pestañas con Apertura por Fábrica/Línea ---
t1, t2 = st.tabs(["Estampado", "Soldadura"])

with t1:
    m_est = calculate_real_oee(df_f_datos[df_f_datos['Fábrica'].str.contains('ESTAMPADO', case=False)], 
                               df_f_prod[df_f_prod['Máquina'].str.contains('L1|L2|L3|L4', case=False)])
    show_metric_row_manual = lambda m: (st.columns(4)[0].metric("OEE", f"{m['OEE']:.1%}"), 
                                        st.columns(4)[1].metric("Disp.", f"{m['DISP']:.1%}"), 
                                        st.columns(4)[2].metric("Perf.", f"{m['PERF']:.1%}"), 
                                        st.columns(4)[3].metric("Cal.", f"{m['CAL']:.1%}"))
    st.markdown("#### Total Estampado")
    c_e = st.columns(4)
    c_e[0].metric("OEE", f"{m_est['OEE']:.1%}")
    c_e[1].metric("Disponibilidad", f"{m_est['DISP']:.1%}")
    c_e[2].metric("Performance", f"{m_est['PERF']:.1%}")
    c_e[3].metric("Calidad", f"{m_est['CAL']:.1%}")

    with st.expander("Ver detalle por Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            m_l = calculate_real_oee(df_f_datos[df_f_datos['Máquina'].str.contains(l)], 
                                     df_f_prod[df_f_prod['Máquina'].str.contains(l)])
            st.markdown(f"**{l}**")
            cl = st.columns(4)
            cl[0].metric("OEE", f"{m_l['OEE']:.1%}", label_visibility="collapsed")
            cl[1].metric("Disp", f"{m_l['DISP']:.1%}", label_visibility="collapsed")
            cl[2].metric("Perf", f"{m_l['PERF']:.1%}", label_visibility="collapsed")
            cl[3].metric("Cal", f"{m_l['CAL']:.1%}", label_visibility="collapsed")
            st.markdown("---")

with t2:
    m_sold = calculate_real_oee(df_f_datos[df_f_datos['Fábrica'].str.contains('SOLDADURA', case=False)], 
                                df_f_prod[df_f_prod['Máquina'].str.contains('CELDA|PRP', case=False)])
    st.markdown("#### Total Soldadura")
    c_s = st.columns(4)
    c_s[0].metric("OEE", f"{m_sold['OEE']:.1%}")
    c_s[1].metric("Disponibilidad", f"{m_sold['DISP']:.1%}")
    c_s[2].metric("Performance", f"{m_sold['PERF']:.1%}")
    c_s[3].metric("Calidad", f"{m_sold['CAL']:.1%}")

# ==========================================
# 6. DESPLEGABLE MATEMÁTICO POR MÁQUINA
# ==========================================
st.markdown("---")
with st.expander("🔍 Desglose Matemático del OEE por Máquina", expanded=False):
    res_maq = []
    for m in máquinas_globales:
        m_stats = calculate_real_oee(df_f_datos[df_f_datos['Máquina'] == m], df_f_prod[df_f_prod['Máquina'] == m])
        if m_stats['DISP'] > 0 or m_stats['CAL'] > 0:
            res_maq.append({
                "Máquina": m,
                "OEE Real": f"{m_stats['OEE']:.1%}",
                "Disponibilidad (Prod/Total)": f"{m_stats['DISP']:.1%}",
                "Performance (Real/Estimado)": f"{m_stats['PERF']:.1%}",
                "Calidad (Buenas/Total)": f"{m_stats['CAL']:.1%}"
            })
    st.table(pd.DataFrame(res_maq))

# ==========================================
# 7. INDICADORES POR OPERADOR
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
with st.expander("👉 Ver Resumen y Evolución de Operarios"):
    if not df_f_op.empty:
        col_op = next((c for c in df_f_op.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        st.subheader("📋 Días con Registro")
        df_dias = df_f_op.groupby(col_op)['Fecha_Filtro'].nunique().reset_index(name='Días')
        st.dataframe(df_dias.sort_values('Días', ascending=False), use_container_width=True, hide_index=True)
        
        sel_ops = st.multiselect("Graficar Performance Temporal:", sorted(df_f_op[col_op].unique()))
        if sel_ops:
            df_perf = df_f_op[df_f_op[col_op].isin(sel_ops)].sort_values('Fecha_Filtro')
            st.plotly_chart(px.line(df_perf, x='Fecha_Filtro', y='Performance', color=col_op, markers=True), use_container_width=True)

# ==========================================
# 8. MÓDULO PRODUCCIÓN
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_f_prod.empty:
    c_maq = next((c for c in df_f_prod.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), 'Máquina')
    c_cod = next((c for c in df_f_prod.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
    c_b, c_r, c_o = 'Buenas', 'Retrabajo', 'Observadas'
    
    # Gráfico
    df_st = df_f_prod.groupby(c_maq)[[c_b, c_r, c_o]].sum().reset_index()
    st.plotly_chart(px.bar(df_st, x=c_maq, y=[c_b, c_r, c_o], title="Balance Producción", barmode='stack'), use_container_width=True)
    
    # Tablas
    with st.expander("📂 Tablas Detalladas (Código, Máquina, Fecha)"):
        df_f_prod['Fecha'] = df_f_prod['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
        df_tab = df_f_prod.groupby([c_cod, c_maq, 'Fecha'])[[c_b, c_r, c_o]].sum().reset_index()
        st.dataframe(df_tab.sort_values([c_cod, 'Fecha'], ascending=[True, False]), use_container_width=True, hide_index=True)

# ==========================================
# 9. ANÁLISIS DE TIEMPOS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos")
if not df_f_datos.empty:
    df_f_datos['Tipo'] = df_f_datos['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
    col1, col2 = st.columns([1, 2])
    with col1: st.plotly_chart(px.pie(df_f_datos, values='Tiempo (Min)', names='Tipo', title="Eficiencia de Tiempo", hole=0.4), use_container_width=True)
    with col2: st.plotly_chart(px.bar(df_f_datos, x='Operador', y='Tiempo (Min)', color='Tipo', title="Tiempo por Operador", barmode='group'), use_container_width=True)

# ==========================================
# 10. ANÁLISIS DE FALLAS
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")
df_fallas = df_f_datos[df_f_datos['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    m_f = st.multiselect("Filtrar Máquinas para Fallas:", sorted(df_fallas['Máquina'].unique()), default=sorted(df_fallas['Máquina'].unique()))
    top_f = df_fallas[df_fallas['Máquina'].isin(m_f)].groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig_f = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top 15 Fallas", text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig_f.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    fig_f.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, height=600)
    st.plotly_chart(fig_f, use_container_width=True)

st.divider()
with st.expander("📂 Registro Crudo de Datos"): st.dataframe(df_f_datos, use_container_width=True)
