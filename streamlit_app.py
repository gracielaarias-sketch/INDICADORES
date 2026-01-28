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
# 2. CARGA DE DATOS (4 FUENTES INDEPENDIENTES)
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        try:
            url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        except Exception:
            st.error("⚠️ No se encontró la configuración de secretos (.streamlit/secrets.toml).")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # ---------------------------------------------------------
        # 🟢 CONFIGURACIÓN DE GIDs (IDENTIFICADORES DE PESTAÑAS)
        # ---------------------------------------------------------
        gid_datos = "0"             # 1. DATOS DE PAROS
        gid_oee = "1767654796"      # 2. OEE GENERAL (KPIs)
        gid_prod = "315437448"      # 3. PRODUCCIÓN
        gid_performance = "354131379"  # 4.  PERFORMANCE
        # ---------------------------------------------------------

        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception:
                return pd.DataFrame()
            
            # Limpieza Numérica General
            cols_num = [
                'Tiempo (Min)', 'Cantidad', 'Piezas', 'Produccion', 'Total',
                'Buenas', 'Retrabajo', 'Observadas', 'Tiempo de Ciclo', 'Ciclo',
                'Performance', 'OEE', 'Disponibilidad', 'Calidad', 'Meta'
            ]
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace(',', '.')
                    df[match] = df[match].astype(str).str.replace('%', '')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            # Limpieza de Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Limpieza de Textos
            cols_texto = [
                'Fábrica', 'Máquina', 'Evento', 'Código', 'Producto', 'Referencia', 
                'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 5', 'Nivel Evento 6', 
                'Operador', 'Hora Inicio', 'Hora Fin'
            ]
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str).str.strip()
            return df

        # Cargar las 4 fuentes por separado
        df1 = process_df(base_export + gid_datos)
        df2 = process_df(base_export + gid_oee)
        df3 = process_df(base_export + gid_prod)
        df4 = process_df(base_export + gid_performance)
        
        return df1, df2, df3, df4

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_perf_raw = load_data()

# ==========================================
# 3. FILTROS (APLICADOS A CADA FUENTE)
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados en la hoja principal (DATOS).")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()

rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")

opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

# LÓGICA DE FILTRADO INDEPENDIENTE
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    
    # 1. FILTRO DATOS (PAROS)
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # 2. FILTRO OEE (KPIs GENERALES)
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
        col_maq_oee = next((c for c in df_oee_f.columns if 'máquina' in c.lower()), None)
        if col_maq_oee:
             df_oee_f = df_oee_f[df_oee_f[col_maq_oee].isin(máquinas)]
    else:
        df_oee_f = df_oee_raw
        
    # 3. FILTRO PRODUCCIÓN
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
        col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
        if col_maq_prod:
            df_prod_f = df_prod_f[df_prod_f[col_maq_prod].isin(máquinas)]
    else:
        df_prod_f = pd.DataFrame()

    # 4. FILTRO PERFORMANCE (OPERADORES) - NUEVA PESTAÑA
    if not df_perf_raw.empty and 'Fecha_Filtro' in df_perf_raw.columns:
        df_perf_f = df_perf_raw[(df_perf_raw['Fecha_Filtro'] >= ini) & (df_perf_raw['Fecha_Filtro'] <= fin)]
        # Intentamos filtrar por máquina también si la columna existe en la pestaña Performance
        col_maq_perf = next((c for c in df_perf_f.columns if 'máquina' in c.lower()), None)
        if col_maq_perf:
             df_perf_f = df_perf_f[df_perf_f[col_maq_perf].isin(máquinas)]
    else:
        df_perf_f = df_perf_raw # Si falla, dejamos el raw o vacío

else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 4. SECCIÓN OEE GENERAL (Fuente: Pestaña OEE)
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    
    # Busca coincidencias en todas las columnas de texto de la fila (ej: 'L1', 'Estampado')
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    
    if not datos.empty:
        cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
        for key, col_search in cols_map.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                vals = pd.to_numeric(datos[actual_col], errors='coerce').dropna()
                if not vals.empty:
                    val_promedio = vals.mean()
                    # Ajuste si viene en % (ej 85) a decimal (0.85)
                    m[key] = float(val_promedio / 100 if val_promedio > 1.0 else val_promedio)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

# KPI Principal
st.caption("Promedios del periodo (Fuente: Pestaña OEE)")
show_metric_row(get_metrics('GENERAL')) 

# ==========================================
# 🟢 SECCIÓN: PERFORMANCE POR OPERADOR (Fuente: Pestaña PERFORMANCE)
# ==========================================
st.markdown("---")
st.subheader("👷 Performance Promedio por Operador")
st.caption("Datos extraídos de la pestaña independiente 'PERFORMANCE'")

if not df_perf_f.empty:
    # Buscar columnas 'Performance' y 'Operador' en el DF de Performance
    col_perf = next((c for c in df_perf_f.columns if 'performance' in c.lower()), None)
    col_op = next((c for c in df_perf_f.columns if 'operador' in c.lower()), None)

    if col_perf and col_op:
        # 1. Limpiar filas sin operador
        df_p_clean = df_perf_f[df_perf_f[col_op] != ''].copy()
        
        # 2. Agrupar por Operador y calcular PROMEDIO
        df_resumen = df_p_clean.groupby(col_op)[col_perf].mean().reset_index()
        
        # 3. Normalizar para visualización (si > 1.0 asumimos base 100)
        df_resumen['Performance_Norm'] = df_resumen[col_perf].apply(lambda x: x/100 if x > 1.0 else x)
        
        # 4. Ordenar Alfabéticamente por Operador
        df_resumen = df_resumen.sort_values(by=col_op, ascending=True)

        with st.expander("📊 Ver Tabla Detallada de Performance", expanded=True):
            st.dataframe(
                df_resumen[[col_op, 'Performance_Norm']], 
                use_container_width=True,
                hide_index=True,
                column_config={
                    col_op: "Operador",
                    "Performance_Norm": st.column_config.ProgressColumn(
                        "Performance Promedio",
                        format="%.1f%%",
                        min_value=0,
                        max_value=1,
                    )
                }
            )
    else:
        st.warning(f"⚠️ No se encontraron las columnas 'Operador' o 'Performance' en la pestaña PERFORMANCE. Columnas detectadas: {df_perf_f.columns.tolist()}")
else:
    if df_perf_raw.empty:
        st.error("❌ No hay datos cargados. Verifique el GID de la pestaña PERFORMANCE en el código.")
    else:
        st.info("No hay datos de performance para el rango seleccionado.")

st.divider()

# ==========================================
# RESTO DE SECCIONES (TABS ESTAMPADO/SOLDADURA, TURNOS, ETC)
# ==========================================

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
# 🛑 FUNCIONALIDAD: INICIO Y FIN DE TURNO (Fuente: DATOS)
# ==========================================
st.markdown("---")
with st.expander("⏱️ Detalle de Horarios y Tiempos (Fuente: DATOS)", expanded=False):
    if not df_f.empty:
        c_ini = 'Hora Inicio'
        c_fin = 'Hora Fin'
        c_tiempo = 'Tiempo (Min)'
        c_maq = 'Máquina'
        c_fecha = 'Fecha_Filtro'

        if all(col in df_f.columns for col in [c_ini, c_fin, c_tiempo, c_maq, c_fecha]):
            
            df_calc = df_f[[c_fecha, c_maq, c_ini, c_fin, c_tiempo]].copy()

            def time_str_to_min(val):
                try:
                    val = str(val).strip()
                    if ":" in val:
                        parts = val.split(":")
                        return int(parts[0]) * 60 + int(parts[1])
                    return None
                except:
                    return None

            df_calc['min_ini'] = df_calc[c_ini].apply(time_str_to_min)
            df_calc['min_fin'] = df_calc[c_fin].apply(time_str_to_min)
            
            df_daily = df_calc.groupby([c_fecha, c_maq]).agg({
                'min_ini': 'min',      
                'min_fin': 'max',      
                c_tiempo: 'sum'        
            }).reset_index()

            df_final_avg = df_daily.groupby(c_maq).agg({
                'min_ini': 'mean',     
                'min_fin': 'mean',     
                c_tiempo: 'mean'       
            }).reset_index()

            def min_to_time_str(val):
                if pd.isna(val): return "--:--"
                h = int(val // 60)
                m = int(val % 60)
                return f"{h:02d}:{m:02d}"

            df_final_avg['Promedio Inicio'] = df_final_avg['min_ini'].apply(min_to_time_str)
            df_final_avg['Promedio Fin'] = df_final_avg['min_fin'].apply(min_to_time_str)
            
            st.dataframe(
                df_final_avg[[c_maq, 'Promedio Inicio', 'Promedio Fin', c_tiempo]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    c_tiempo: st.column_config.NumberColumn("Tiempo Total Promedio (Min)", format="%.0f min")
                }
            )
        else:
            st.warning("Faltan columnas 'Hora Inicio' o 'Hora Fin' en la pestaña de DATOS.")
    else:
        st.info("No hay datos cargados en la pestaña principal.")

# ==========================================
# 🛑 FUNCIONALIDAD: BAÑO Y REFRIGERIO (Fuente: DATOS)
# ==========================================
st.markdown("---")
with st.expander("☕ Tiempos de Descanso por Operador (Fuente: DATOS)"):
    if not df_f.empty and 'Operador' in df_f.columns:
        
        tab_bano, tab_refri = st.tabs(["Baño", "Refrigerio"])

        def crear_tabla_descanso(keyword, tab_destino):
            col_target = 'Nivel Evento 4'
            col_match = next((c for c in df_f.columns if col_target.lower() in c.lower()), None)
            
            if not col_match:
                with tab_destino: st.warning(f"No se encontró la columna '{col_target}' en los datos.")
                return

            mask = df_f[col_match].astype(str).str.contains(keyword, case=False)
            df_sub = df_f[mask]

            if not df_sub.empty:
                resumen = df_sub.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                resumen.columns = ['Operador', 'Tiempo Total (Min)', 'Promedio por vez (Min)', 'Eventos']
                
                resumen = resumen.sort_values('Tiempo Total (Min)', ascending=False)
                
                val_total = resumen['Tiempo Total (Min)'].sum()
                val_promedio = resumen['Tiempo Total (Min)'].mean()

                with tab_destino:
                    c1, c2 = st.columns(2)
                    c1.metric(f"Total Minutos ({keyword})", f"{val_total:,.0f}")
                    c2.metric(f"Promedio General ({keyword})", f"{val_promedio:,.1f} min")
                    
                    st.dataframe(
                        resumen,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Tiempo Total (Min)": st.column_config.NumberColumn(format="%.0f min"),
                            "Promedio por vez (Min)": st.column_config.NumberColumn(format="%.1f min")
                        }
                    )
            else:
                with tab_destino:
                    st.info(f"No se encontraron registros que contengan '{keyword}' en la columna '{col_target}'.")

        crear_tabla_descanso("Baño", tab_bano)
        crear_tabla_descanso("Refrigerio", tab_refri)
    else:
        st.warning("No se encontró la columna 'Operador' o datos suficientes.")
