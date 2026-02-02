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

        gid_datos = "0" 
        gid_oee = "1767654796" 
        gid_prod = "315437448" 
        gid_operarios = "354131379" 

        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception:
                return pd.DataFrame()
            
            cols_num = [
                'Tiempo (Min)', 'Cantidad', 'Piezas', 'Produccion', 'Total',
                'Buenas', 'Retrabajo', 'Observadas', 'Tiempo de Ciclo', 'Ciclo',
                'Eficiencia', 'Performance', 'Cumplimiento', 'Meta', 'Objetivo', 'OEE',
                'Tiempo Producción (Min)', 'Tiempo Ciclo'
            ]
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace(',', '.')
                    df[match] = df[match].str.replace('%', '')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            cols_texto = [
                'Fábrica', 'Máquina', 'Evento', 'Código', 'Producto', 'Referencia',
                'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 5', 'Nivel Evento 6',
                'Operador', 'Hora Inicio', 'Hora Fin', 'Nombre', 'Apellido', 'Turno',
                'Usuario 1', 'Usuario 2', 'Usuario 3', 'Usuario 4', 'Usuario 5', 'Usuario 6'
            ]
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)
            return df

        df1 = process_df(base_export + gid_datos)
        df2 = process_df(base_export + gid_oee)
        df3 = process_df(base_export + gid_prod)
        df4 = process_df(base_export + gid_operarios)
        return df1, df2, df3, df4

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados en la hoja principal.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter_unique")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")

opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
        col_maq_oee = next((c for c in df_oee_f.columns if 'máquina' in c.lower()), None)
        if col_maq_oee:
            df_oee_f = df_oee_f[df_oee_f[col_maq_oee].isin(máquinas)]
    
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
        col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
        if col_maq_prod:
            df_prod_f = df_prod_f[df_prod_f[col_maq_prod].isin(máquinas)]
    
    if not df_operarios_raw.empty and 'Fecha_Filtro' in df_operarios_raw.columns:
        df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]
else:
    st.stop()

# ==========================================
# 4. LÓGICA DE CÁLCULO OEE ACTUALIZADA
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    
    # Filtros por nombre para las 3 fuentes
    mask_oee = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    d_oee = df_oee_f[mask_oee]
    
    mask_paro = df_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    d_paro = df_f[mask_paro]
    
    mask_prod = df_prod_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    d_prod = df_prod_f[mask_prod]

    if d_oee['Fecha_Filtro'].nunique() == 1:
        # CASO DÍA ÚNICO: Datos de la planilla
        for key, col_s in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            c = next((col for col in d_oee.columns if col_s.lower() in col.lower()), None)
            if c:
                val = pd.to_numeric(d_oee[c].astype(str).str.replace('%','').str.replace(',','.'), errors='coerce').mean()
                m[key] = val/100 if val > 1.0 else val
    else:
        # CASO RANGO: Cálculo Matemático
        # 1. DISPONIBILIDAD (Desde pestaña Paros/Datos)
        t_produccion = d_paro[d_paro['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
        t_total = d_paro['Tiempo (Min)'].sum()
        m['DISP'] = t_produccion / t_total if t_total > 0 else 0.0
        
        # 2. PERFORMANCE Y CALIDAD (Desde pestaña Producción)
        if not d_prod.empty:
            buenas = d_prod['Buenas'].sum()
            total_p = buenas + d_prod['Retrabajo'].sum() + d_prod['Observadas'].sum()
            m['CAL'] = buenas / total_p if total_p > 0 else 0.0
            
            # Performance: Real / Esperada
            d_prod['esperadas'] = (d_prod['Tiempo Producción (Min)'] * 60) / d_prod['Tiempo Ciclo'].replace(0, float('inf'))
            t_esperado = d_prod['esperadas'].sum()
            m['PERF'] = total_p / t_esperado if t_esperado > 0 else 0.0
            
        m['OEE'] = m['DISP'] * m['PERF'] * m['CAL']

    for k in m: m[k] = max(0.0, min(float(m[k]), 1.0))
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

st.caption("Promedios del periodo")
show_metric_row(get_metrics('GENERAL'))

# --- SECCIONES ORIGINALES RESTAURADAS ---
st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    st.markdown("#### Total Estampado")
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("Ver detalle por Líneas"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{linea}**")
            show_metric_row(get_metrics(linea))

with t2:
    st.markdown("#### Total Soldadura")
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("Ver detalle"):
        st.markdown("**Celdas Robotizadas**")
        show_metric_row(get_metrics('CELDA'))
        st.markdown("---")
        st.markdown("**PRP**")
        show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. BLOQUE DE HORARIOS Y DESCANSOS
# ==========================================
st.markdown("---")
with st.expander("⏱️ Detalle de Horarios y Tiempos"):
    if not df_f.empty:
        c_ini, c_fin, c_tiempo, c_maq, c_fecha = 'Hora Inicio', 'Hora Fin', 'Tiempo (Min)', 'Máquina', 'Fecha_Filtro'
        if all(col in df_f.columns for col in [c_ini, c_fin, c_tiempo, c_maq, c_fecha]):
            df_calc = df_f[[c_fecha, c_maq, c_ini, c_fin, c_tiempo]].copy()
            def time_to_min(v):
                try:
                    p = str(v).strip().split(":")
                    return int(p[0])*60 + int(p[1])
                except: return None
            df_calc['min_ini'] = df_calc[c_ini].apply(time_to_min)
            df_calc['min_fin'] = df_calc[c_fin].apply(time_to_min)
            df_daily = df_calc.groupby([c_fecha, c_maq]).agg({'min_ini':'min','min_fin':'max',c_tiempo:'sum'}).reset_index()
            df_final_avg = df_daily.groupby(c_maq).agg({'min_ini':'mean','min_fin':'mean',c_tiempo:'mean'}).reset_index()
            def min_to_str(v):
                if pd.isna(v): return "--:--"
                return f"{int(v//60):02d}:{int(v%60):02d}"
            df_final_avg['Promedio Inicio'] = df_final_avg['min_ini'].apply(min_to_str)
            df_final_avg['Promedio Fin'] = df_final_avg['min_fin'].apply(min_to_str)
            st.dataframe(df_final_avg[[c_maq, 'Promedio Inicio', 'Promedio Fin', c_tiempo]], use_container_width=True, hide_index=True)

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
        render_descanso("Baño", t_b)
        render_descanso("Refrigerio", t_r)

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
                fig = px.line(df_g, x='Fecha_Filtro', y='Performance', color=col_op, markers=True, title="Evolución Performance")
                st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 7. PRODUCCIÓN GENERAL
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    col_maq = next((c for c in df_prod_f.columns if 'máquina' in c.lower()), None)
    col_buenas = 'Buenas'
    if col_maq:
        df_gp = df_prod_f.groupby(col_maq)[col_buenas].sum().reset_index()
        st.plotly_chart(px.bar(df_gp, x=col_maq, y=col_buenas, title="Producción por Máquina"), use_container_width=True)

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
