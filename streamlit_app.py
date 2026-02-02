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
                'Disponibilidad', 'Calidad'
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
                'Operador', 'Hora Inicio', 'Hora Fin', 'Nombre', 'Apellido', 'Turno'
            ]
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), process_df(base_export + gid_oee), \
               process_df(base_export + gid_prod), process_df(base_export + gid_operarios)

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
    es_rango = ini != fin
    
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]
else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 4. SECCIÓN OEE (KPIs CALCULADOS)
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    
    # --- FILTRADO DE DATOS PARA EL CÁLCULO ---
    if name_filter.upper() == 'GENERAL':
        d_paros = df_f
        d_prod = df_prod_f
    else:
        d_paros = df_f[df_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]
        d_prod = df_prod_f[df_prod_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)]

    # --- LÓGICA DE CÁLCULO SI ES RANGO ---
    if es_rango and not d_paros.empty and not d_prod.empty:
        # 1. Disponibilidad
        t_produccion = d_paros[d_paros['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
        t_paros_total = d_paros[d_paros['Evento'].str.contains('Parada', case=False)]['Tiempo (Min)'].sum()
        disp = t_produccion / (t_produccion + t_paros_total) if (t_produccion + t_paros_total) > 0 else 0
        
        # 2. Calidad
        buenas = d_prod['Buenas'].sum()
        malas = d_prod['Retrabajo'].sum() + d_prod['Observadas'].sum()
        cal = buenas / (buenas + malas) if (buenas + malas) > 0 else 0
        
        # 3. Performance
        # (Piezas Totales * Ciclo Promedio Segundos) / (Minutos Producción Real * 60)
        ciclo_prom = d_prod['Tiempo de Ciclo'].mean()
        t_teorico_seg = (buenas + malas) * ciclo_prom
        t_real_seg = t_produccion * 60
        perf = t_teorico_seg / t_real_seg if t_real_seg > 0 else 0
        perf = min(perf, 1.0) # Cap al 100%
        
        m = {'OEE': disp * perf * cal, 'DISP': disp, 'PERF': perf, 'CAL': cal}
        return m

    # --- LÓGICA ORIGINAL (DÍA ÚNICO O FALLA DE DATOS) ---
    mask_oee = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos_oee = df_oee_f[mask_oee]
    
    if not datos_oee.empty:
        cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
        for key, col_search in cols_map.items():
            actual_col = next((c for c in datos_oee.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                vals = pd.to_numeric(datos_oee[actual_col], errors='coerce').dropna()
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

st.caption("Indicadores del periodo (Calculados en Rango / Hoja en Día)")
show_metric_row(get_metrics('GENERAL'))

# ------------------------------------------------------------------------
# 📉 GRÁFICO HISTÓRICO OEE (IGUAL)
# ------------------------------------------------------------------------
with st.expander("📉 Ver Gráfico de Evolución Histórica OEE", expanded=False):
    if not df_oee_f.empty:
        col_oee_trend = next((c for c in df_oee_f.columns if 'OEE' in c.upper()), None)
        if col_oee_trend:
             df_trend = df_oee_f.copy()
             df_trend['OEE_Num'] = pd.to_numeric(df_trend[col_oee_trend].astype(str).str.replace('%','').str.replace(',','.'), errors='coerce')
             df_trend['OEE_Num'] = df_trend['OEE_Num'].apply(lambda x: x/100 if x > 1.0 else x)
             trend_data = df_trend.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
             fig_trend = px.line(trend_data, x='Fecha_Filtro', y='OEE_Num', markers=True, title='Tendencia Diaria del OEE (%)')
             fig_trend.update_layout(yaxis_tickformat='.0%')
             fig_trend.add_hline(y=0.85, line_dash="dot", annotation_text="Meta (85%)", line_color="green")
             st.plotly_chart(fig_trend, use_container_width=True)

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
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
        st.write("**Celdas Robotizadas**"); show_metric_row(get_metrics('CELDA'))
        st.write("**PRP**"); show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. BLOQUE DE HORARIOS (IGUAL)
# ==========================================
st.markdown("---")
with st.expander("⏱️ Detalle de Horarios y Tiempos", expanded=False):
    if not df_f.empty:
        c_ini, c_fin, c_tiempo, c_maq, c_fecha = 'Hora Inicio', 'Hora Fin', 'Tiempo (Min)', 'Máquina', 'Fecha_Filtro'
        if all(col in df_f.columns for col in [c_ini, c_fin, c_tiempo, c_maq, c_fecha]):
            df_calc = df_f[[c_fecha, c_maq, c_ini, c_fin, c_tiempo]].copy()
            def t2m(v):
                try:
                    p = str(v).strip().split(":")
                    return int(p[0]) * 60 + int(p[1])
                except: return None
            df_calc['min_ini'] = df_calc[c_ini].apply(t2m)
            df_calc['min_fin'] = df_calc[c_fin].apply(t2m)
            df_daily = df_calc.groupby([c_fecha, c_maq]).agg({'min_ini': 'min', 'min_fin': 'max', c_tiempo: 'sum'}).reset_index()
            df_final_avg = df_daily.groupby(c_maq).agg({'min_ini': 'mean', 'min_fin': 'mean', c_tiempo: 'mean'}).reset_index()
            df_final_avg['Promedio Inicio'] = df_final_avg['min_ini'].apply(lambda x: f"{int(x//60):02d}:{int(x%60):02d}" if pd.notna(x) else "--:--")
            df_final_avg['Promedio Fin'] = df_final_avg['min_fin'].apply(lambda x: f"{int(x//60):02d}:{int(x%60):02d}" if pd.notna(x) else "--:--")
            st.dataframe(df_final_avg[[c_maq, 'Promedio Inicio', 'Promedio Fin', c_tiempo]], use_container_width=True, hide_index=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    if not df_f.empty and 'Operador' in df_f.columns:
        tb1, tb2 = st.tabs(["Baño", "Refrigerio"])
        for lab, tdest in zip(["Baño", "Refrigerio"], [tb1, tb2]):
            col_ev = next((c for c in df_f.columns if 'Evento 4' in c), None)
            if col_ev:
                sub = df_f[df_f[col_ev].str.contains(lab, case=False)]
                if not sub.empty:
                    res = sub.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                    with tdest: st.dataframe(res, use_container_width=True, hide_index=True)

# ==========================================
# 6. INDICADORES DIARIOS (IGUAL)
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS")
with st.expander("👉 Desplegar Análisis Diario", expanded=False):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if 'operador' in c.lower() or 'nombre' in c.lower()), None)
        if col_op:
            df_dias = df_op_f.groupby(col_op)['Fecha_Filtro'].nunique().reset_index(name='Días')
            st.dataframe(df_dias.sort_values('Días', ascending=False), use_container_width=True, hide_index=True)
            sel_ops = st.multiselect("👤 Seleccione Operarios:", sorted(df_op_f[col_op].unique()))
            if sel_ops:
                col_m = next((c for c in df_op_f.columns if 'oee' in c.lower() or 'perf' in c.lower()), df_op_f.columns[0])
                fig_op = px.line(df_op_f[df_op_f[col_op].isin(sel_ops)], x='Fecha_Filtro', y=col_m, color=col_op, markers=True)
                st.plotly_chart(fig_op, use_container_width=True)

# ==========================================
# 7. PRODUCCIÓN GENERAL (IGUAL)
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    c_mq = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), None)
    c_bn = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
    if c_mq and c_bn:
        st.metric("Total Piezas Buenas", f"{df_prod_f[c_bn].sum():,.0f}")
        st.plotly_chart(px.bar(df_prod_f.groupby(c_mq)[c_bn].sum().reset_index(), x=c_mq, y=c_bn), use_container_width=True)

# ==========================================
# 8. ANÁLISIS DE FALLAS (IGUAL)
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos y Fallas")
if not df_f.empty:
    df_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)].copy()
    if not df_fallas.empty:
        c_fl = next((c for c in df_fallas.columns if 'Evento 6' in c), df_fallas.columns[0])
        top = df_fallas.groupby(c_fl)['Tiempo (Min)'].sum().nlargest(15).reset_index()
        st.plotly_chart(px.bar(top, x='Tiempo (Min)', y=c_fl, orientation='h'), use_container_width=True)

# ==========================================
# 9. TABLA DETALLADA (IGUAL)
# ==========================================
with st.expander("📂 Ver Registro Detallado", expanded=True):
    if not df_f.empty:
        st.dataframe(df_f, use_container_width=True, hide_index=True)
