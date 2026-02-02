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
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        gids = {"datos": "0", "oee": "1767654796", "prod": "315437448", "op": "354131379"}

        def process_df(url):
            try:
                df = pd.read_csv(url)
                if df.empty: return pd.DataFrame()
                
                # Limpieza numérica: incluye todas las columnas de cálculo
                cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 
                            'Tiempo Producción (Min)', 'Tiempo Ciclo', 'OEE', 
                            'Disponibilidad', 'Performance', 'Calidad']
                for c in cols_num:
                    matches = [col for col in df.columns if c.lower() in col.lower()]
                    for match in matches:
                        df[match] = df[match].astype(str).str.replace(',', '.')
                        df[match] = df[match].str.replace('%', '')
                        df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
                
                # Fechas
                col_f = next((c for c in df.columns if 'fecha' in c.lower()), None)
                if col_f:
                    df['Fecha_DT'] = pd.to_datetime(df[col_f], dayfirst=True, errors='coerce')
                    df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                return df.dropna(subset=['Fecha_Filtro'])
            except: return pd.DataFrame()

        return (process_df(base_export + gids["datos"]), 
                process_df(base_export + gids["oee"]), 
                process_df(base_export + gids["prod"]), 
                process_df(base_export + gids["op"]))
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS LATERALES
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Configuración Global")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Rango de Análisis", [min_d, max_d], key="global_range")

st.sidebar.divider()
fábricas = st.sidebar.multiselect("Fábrica", sorted(df_raw['Fábrica'].unique()), default=df_raw['Fábrica'].unique())
máquinas = st.sidebar.multiselect("Máquina", sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique()), default=df_raw['Máquina'].unique())

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin) & df_raw['Fábrica'].isin(fábricas) & df_raw['Máquina'].isin(máquinas)]
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]
else:
    st.stop()

# ==========================================
# 4. SELECTOR DÍA PARTICULAR Y LÓGICA OEE
# ==========================================
st.title("🏭 INDICADORES FAMMA")

with st.expander("🔍 CONSULTAR DÍA ESPECÍFICO (Datos directos de Planilla)", expanded=True):
    dia_consulta = st.date_input("Seleccione un día para ver valores cargados en Sheets:", value=max_d)
    df_dia_oee = df_oee_raw[df_oee_raw['Fecha_Filtro'] == pd.to_datetime(dia_consulta)]
    
    if not df_dia_oee.empty:
        st.success(f"✅ Visualizando datos de Google Sheets para el: {dia_consulta.strftime('%d/%m/%Y')}")
        use_day = True
    else:
        st.warning("⚠️ No se ha seleccionado un día con registros manuales.")
        st.info("Los indicadores mostrados abajo corresponden al cálculo matemático del periodo seleccionado en la barra lateral.")
        use_day = False

def get_metrics(name_filter, use_specific_day=False):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    target_oee = df_dia_oee if use_specific_day else df_oee_f
    
    d_oee = target_oee[target_oee.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]
    d_paro = df_f[df_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]
    d_prod = df_prod_f[df_prod_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]

    if use_specific_day:
        # LÓGICA SHEETS DIRECTO
        for k, s in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            c = next((col for col in d_oee.columns if s.lower() in col.lower()), None)
            if c:
                val = pd.to_numeric(d_oee[c].astype(str).str.replace('%','').str.replace(',','.'), errors='coerce').mean()
                m[k] = val/100 if val > 1.0 else val
    else:
        # LÓGICA CÁLCULO PONDERADO
        t_prod_paro = d_paro[d_paro['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
        t_total_paro = d_paro['Tiempo (Min)'].sum()
        m['DISP'] = t_prod_paro / t_total_paro if t_total_paro > 0 else 0.0
        
        if not d_prod.empty:
            b, r, o = d_prod['Buenas'].sum(), d_prod['Retrabajo'].sum(), d_prod['Observadas'].sum()
            total_real = b + r + o
            m['CAL'] = b / total_real if total_real > 0 else 0.0
            # Performance: Real / (Tiempo Producción * Tasa Horaria)
            d_prod['esperadas'] = d_prod['Tiempo Producción (Min)'] * d_prod['Tiempo Ciclo']
            m['PERF'] = total_real / d_prod['esperadas'].sum() if d_prod['esperadas'].sum() > 0 else 0.0
        m['OEE'] = m['DISP'] * m['PERF'] * m['CAL']

    for k in m: m[k] = max(0.0, min(float(m[k]), 1.0))
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

# --- DESPLIEGUE KPIs ---
st.subheader("📊 Resumen General")
show_metric_row(get_metrics('GENERAL', use_specific_day=use_day))

t_maq1, t_maq2 = st.tabs(["Estampado", "Soldadura"])
with t_maq1:
    st.markdown("### 🏗️ Sector Estampado")
    show_metric_row(get_metrics('ESTAMPADO', use_specific_day=use_day))
    with st.expander("Detalle por Líneas"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**Línea {linea}**")
            show_metric_row(get_metrics(linea, use_specific_day=use_day))
with t_maq2:
    st.markdown("### 👨‍🏭 Sector Soldadura")
    show_metric_row(get_metrics('SOLDADURA', use_specific_day=use_day))
    with st.expander("Detalle por Celdas / PRP"):
        for sub in ['CELDA', 'PRP']:
            st.markdown(f"**{sub}**")
            show_metric_row(get_metrics(sub, use_specific_day=use_day))

# ==========================================
# 5. BLOQUE DE HORARIOS Y DESCANSOS
# ==========================================
st.markdown("---")
with st.expander("⏱️ Detalle de Horarios y Tiempos"):
    if not df_f.empty:
        df_calc = df_f[['Fecha_Filtro', 'Máquina', 'Hora Inicio', 'Hora Fin', 'Tiempo (Min)']].copy()
        def time_to_min(v):
            try:
                p = str(v).strip().split(":")
                return int(p[0])*60 + int(p[1])
            except: return None
        df_calc['min_ini'] = df_calc['Hora Inicio'].apply(time_to_min)
        df_calc['min_fin'] = df_calc['Hora Fin'].apply(time_to_min)
        df_daily = df_calc.groupby(['Fecha_Filtro', 'Máquina']).agg({'min_ini':'min','min_fin':'max','Tiempo (Min)':'sum'}).reset_index()
        df_final_avg = df_daily.groupby('Máquina').agg({'min_ini':'mean','min_fin':'mean','Tiempo (Min)':'mean'}).reset_index()
        def min_to_str(v):
            if pd.isna(v): return "--:--"
            return f"{int(v//60):02d}:{int(v%60):02d}"
        df_final_avg['Promedio Inicio'] = df_final_avg['min_ini'].apply(min_to_str)
        df_final_avg['Promedio Fin'] = df_final_avg['min_fin'].apply(min_to_str)
        st.dataframe(df_final_avg[['Máquina', 'Promedio Inicio', 'Promedio Fin', 'Tiempo (Min)']], use_container_width=True, hide_index=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    if not df_f.empty and 'Operador' in df_f.columns:
        t_b, t_r = st.tabs(["Baño", "Refrigerio"])
        def render_descanso(key, tab):
            df_s = df_f[df_f['Nivel Evento 4'].astype(str).str.contains(key, case=False)]
            if not df_s.empty:
                res = df_s.groupby('Operador')['Tiempo (Min)'].agg(['sum','mean','count']).reset_index()
                res.columns = ['Operador','Total (Min)','Promedio (Min)','Eventos']
                with tab:
                    st.metric(f"Total {key}", f"{res['Total (Min)'].sum():,.0f}")
                    st.dataframe(res, use_container_width=True, hide_index=True)
        render_descanso("Baño", t_b); render_descanso("Refrigerio", t_r)

# ==========================================
# 6. INDICADORES DIARIOS
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS")
with st.expander("👉 Desplegar Análisis Diario"):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if any(x in c.lower() for x in ['operador','nombre'])), None)
        if col_op:
            sel_ops = st.multiselect("👤 Seleccione Operarios:", sorted(df_op_f[col_op].unique()))
            if sel_ops:
                df_g = df_op_f[df_op_f[col_op].isin(sel_ops)].sort_values('Fecha_Filtro')
                st.plotly_chart(px.line(df_g, x='Fecha_Filtro', y='Performance', color=col_op, markers=True), use_container_width=True)

# ==========================================
# 7. PRODUCCIÓN GENERAL
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    col_maq = next((c for c in df_prod_f.columns if 'máquina' in c.lower()), None)
    if col_maq:
        df_gp = df_prod_f.groupby(col_maq)['Buenas'].sum().reset_index()
        st.plotly_chart(px.bar(df_gp, x=col_maq, y='Buenas', title="Producción por Máquina"), use_container_width=True)

# ==========================================
# 8. ANÁLISIS DE TIEMPOS Y PAROS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos y Fallas")
if not df_f.empty:
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución", hole=0.4), use_container_width=True)
    df_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fallas.empty:
        top = df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().nlargest(15).reset_index()
        c2.plotly_chart(px.bar(top, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top Fallas"), use_container_width=True)

# ==========================================
# 9. TABLA DETALLADA
# ==========================================
st.divider()
with st.expander("📂 Ver Registro Detallado de Eventos", expanded=True):
    if not df_f.empty:
        st.dataframe(df_f[['Fecha_Filtro','Máquina','Hora Inicio','Hora Fin','Tiempo (Min)','Evento','Operador']], use_container_width=True, hide_index=True)
