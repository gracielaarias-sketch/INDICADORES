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

        gid_datos = "0"             # Datos crudos de paros
        gid_oee = "1767654796"      # Datos de OEE
        gid_prod = "315437448"      # PRODUCCION
        gid_operarios = "354131379" # PERFO OPERARIOS

        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception:
                return pd.DataFrame()
            
            # Limpieza Numérica
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
            
            # Limpieza Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Rellenar Textos
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

# APLICAR FILTROS GLOBALES
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    es_dia_unico = (rango[0] == rango[1])
    
    # 1. Paros
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # 2. OEE General
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
        
    # 3. Producción
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
    else:
        df_prod_f = pd.DataFrame()

    # 4. Operarios
    if not df_operarios_raw.empty and 'Fecha_Filtro' in df_operarios_raw.columns:
         df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]
    else:
         df_op_f = pd.DataFrame()
else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 4. SECCIÓN OEE (KPIs) - LÓGICA HÍBRIDA
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    
    # --- CASO 1: DÍA ÚNICO (LEER DE GOOGLE SHEETS) ---
    if es_dia_unico:
        if df_oee_f.empty: return m
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
        datos = df_oee_f[mask]
        if not datos.empty:
            cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
            for key, col_search in cols_map.items():
                actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
                if actual_col:
                    serie_limpia = datos[actual_col].astype(str).str.replace('%', '').str.replace(',', '.')
                    vals = pd.to_numeric(serie_limpia, errors='coerce').dropna()
                    if not vals.empty:
                        val_promedio = vals.mean()
                        m[key] = float(val_promedio / 100 if val_promedio > 1.1 else val_promedio)
        return m

    # --- CASO 2: RANGO DE TIEMPO (CÁLCULO MATEMÁTICO) ---
    else:
        # A. Disponibilidad (Pestaña Datos)
        mask_paros = df_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
        d_paros = df_f[mask_paros]
        t_prod = d_paros[d_paros['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
        t_fallas = d_paros[d_paros['Nivel Evento 3'].astype(str).str.contains('FALLA|PARO|MICRO', case=False, na=False)]['Tiempo (Min)'].sum()
        
        disp = t_prod / (t_prod + t_fallas) if (t_prod + t_fallas) > 0 else 0

        # B. Calidad y Performance (Pestaña Producción)
        mask_prod = df_prod_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
        d_prod = df_prod_f[mask_prod]
        
        p_buenas = d_prod['Buenas'].sum() if 'Buenas' in d_prod.columns else 0
        p_retrabajo = d_prod['Retrabajo'].sum() if 'Retrabajo' in d_prod.columns else 0
        p_observadas = d_prod['Observadas'].sum() if 'Observadas' in d_prod.columns else 0
        p_total = p_buenas + p_retrabajo + p_observadas
        
        cal = p_buenas / p_total if p_total > 0 else 0

        # Performance: (Piezas Totales * Tiempo de Ciclo) / (Tiempo Producción en Segundos)
        ciclo_medio = d_prod['Tiempo de Ciclo'].mean() if 'Tiempo de Ciclo' in d_prod.columns else 0
        t_real_seg = t_prod * 60
        t_teorico_seg = p_total * ciclo_medio
        
        perf = t_teorico_seg / t_real_seg if t_real_seg > 0 else 0
        perf = min(perf, 1.0) # Cap al 100%

        return {'OEE': disp * perf * cal, 'DISP': disp, 'PERF': perf, 'CAL': cal}

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

# --- KPI Principal ---
st.caption(f"Modo: {'Lectura Directa de Hoja' if es_dia_unico else 'Cálculo Matemático por Rango'}")
show_metric_row(get_metrics('GENERAL'))

# ------------------------------------------------------------------------
# 📉 GRÁFICO HISTÓRICO OEE
# ------------------------------------------------------------------------
with st.expander("📉 Ver Gráfico de Evolución Histórica OEE", expanded=False):
    if not df_oee_f.empty:
        col_oee_trend = next((c for c in df_oee_f.columns if 'OEE' in c.upper()), None)
        if col_oee_trend:
             df_trend = df_oee_f.copy()
             df_trend['OEE_Num'] = pd.to_numeric(df_trend[col_oee_trend].astype(str).str.replace('%','').str.replace(',','.'), errors='coerce')
             df_trend['OEE_Num'] = df_trend['OEE_Num'].apply(lambda x: x/100 if x > 1.1 else x)
             
             trend_data = df_trend.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
             fig_trend = px.line(trend_data, x='Fecha_Filtro', y='OEE_Num', markers=True,
                                 title='Tendencia Diaria del OEE (%)')
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
        st.markdown("**Celdas Robotizadas**")
        show_metric_row(get_metrics('CELDA'))
        st.markdown("---")
        st.markdown("**PRP**")
        show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. BLOQUE DE HORARIOS Y DESCANSOS
# ==========================================
st.markdown("---") 
with st.expander("⏱️ Detalle de Horarios y Tiempos", expanded=False):
    if not df_f.empty:
        c_ini, c_fin, c_tiempo, c_maq, c_fecha = 'Hora Inicio', 'Hora Fin', 'Tiempo (Min)', 'Máquina', 'Fecha_Filtro'
        if all(col in df_f.columns for col in [c_ini, c_fin, c_tiempo, c_maq, c_fecha]):
            df_calc = df_f[[c_fecha, c_maq, c_ini, c_fin, c_tiempo]].copy()
            def time_to_min(val):
                try:
                    parts = str(val).split(":")
                    return int(parts[0]) * 60 + int(parts[1])
                except: return None
            df_calc['min_ini'] = df_calc[c_ini].apply(time_to_min)
            df_calc['min_fin'] = df_calc[c_fin].apply(time_to_min)
            df_daily = df_calc.groupby([c_fecha, c_maq]).agg({'min_ini': 'min', 'min_fin': 'max', c_tiempo: 'sum'}).reset_index()
            df_final_avg = df_daily.groupby(c_maq).agg({'min_ini': 'mean', 'min_fin': 'mean', c_tiempo: 'mean'}).reset_index()
            def min_to_str(val):
                if pd.isna(val): return "--:--"
                return f"{int(val // 60):02d}:{int(val % 60):02d}"
            df_final_avg['Promedio Inicio'] = df_final_avg['min_ini'].apply(min_to_str)
            df_final_avg['Promedio Fin'] = df_final_avg['min_fin'].apply(min_to_str)
            st.dataframe(df_final_avg[[c_maq, 'Promedio Inicio', 'Promedio Fin', c_tiempo]], use_container_width=True, hide_index=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    if not df_f.empty and 'Operador' in df_f.columns:
        tab_bano, tab_refri = st.tabs(["Baño", "Refrigerio"])
        def crear_tabla_descanso(keyword, tab_destino):
            col_target = 'Nivel Evento 4'
            mask = df_f[col_target].astype(str).str.contains(keyword, case=False)
            df_sub = df_f[mask]
            if not df_sub.empty:
                resumen = df_sub.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                resumen.columns = ['Operador', 'Total (Min)', 'Prom (Min)', 'Cant']
                with tab_destino:
                    st.dataframe(resumen.sort_values('Total (Min)', ascending=False), use_container_width=True, hide_index=True)
        crear_tabla_descanso("Baño", tab_bano)
        crear_tabla_descanso("Refrigerio", tab_refri)

# ==========================================
# 6. INDICADORES DIARIOS
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS")
with st.expander("👉 Desplegar Análisis Diario (Operarios y Máquinas)", expanded=False):
    if not df_op_f.empty:
        col_op_name = next((c for c in df_op_f.columns if any(x in c.lower() for x in ['operador', 'nombre'])), None)
        if col_op_name:
            lista_operarios = sorted(df_op_f[col_op_name].astype(str).unique())
            sel_operarios = st.multiselect("👤 Seleccione Operarios:", lista_operarios)
            if sel_operarios:
                df_graph = df_op_f[df_op_f[col_op_name].astype(str).isin(sel_operarios)].copy()
                fig_daily = px.line(df_graph, x='Fecha_Filtro', y='OEE', color=col_op_name, markers=True, title="Evolución OEE")
                st.plotly_chart(fig_daily, use_container_width=True)

# ==========================================
# 7. PRODUCCIÓN GENERAL
# ==========================================
st.markdown("---") 
st.header("Producción General")
if not df_prod_f.empty:
    col_maq = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), None)
    col_buenas = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
    if col_maq and col_buenas:
        st.metric("Total Piezas Buenas (Global)", f"{df_prod_f[col_buenas].sum():,.0f}")
        with st.expander("📊 Ver Gráfico de Barras"):
            st.plotly_chart(px.bar(df_prod_f.groupby(col_maq)[col_buenas].sum().reset_index(), x=col_maq, y=col_buenas), use_container_width=True)

# ==========================================
# 8. ANÁLISIS DE TIEMPOS Y FALLAS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos y Fallas")
if not df_f.empty:
    t_prod = df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]['Tiempo (Min)'].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Minutos Producción", f"{t_prod:,.0f}")
    c2.metric("Minutos Fallas", f"{t_fallas:,.0f}")
    c3.metric("Total Eventos", len(df_f))
    
    col_falla = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
    if not df_fallas.empty:
        top15 = df_fallas.groupby(col_falla)['Tiempo (Min)'].sum().nlargest(15).reset_index()
        st.plotly_chart(px.bar(top15, x='Tiempo (Min)', y=col_falla, orientation='h', title="Pareto de Fallas"), use_container_width=True)

# ==========================================
# 9. TABLA DETALLADA
# ==========================================
st.divider()
with st.expander("📂 Ver Registro Detallado de Eventos", expanded=False):
    if not df_f.empty:
        st.dataframe(df_f, use_container_width=True, hide_index=True)
