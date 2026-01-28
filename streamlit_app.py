
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

        # ---------------------------------------------------------
        # 🟢 CONFIGURACIÓN DE GIDs
        # ---------------------------------------------------------
        gid_datos = "0"             # Datos crudos de paros (PESTAÑA DATOS)
        gid_oee = "1767654796"      # Datos de OEE
        gid_prod = "315437448"      # PRODUCCION
        
        # 👇 VERIFICA ESTE GID CON TU HOJA DE "PERFORMANCE" 👇
        gid_perf = "354131379"      # PERFORMANCE 
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
                'Performance', 'Eficiencia', 'Velocidad', 'Ritmo', 'OEE' 
            ]
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace('%', '').str.replace(',', '.')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            # Limpieza Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
            
            # Rellenar Textos
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

        df1 = process_df(base_export + gid_datos)
        df2 = process_df(base_export + gid_oee)
        df3 = process_df(base_export + gid_prod)
        df4 = process_df(base_export + gid_perf) 
        
        return df1, df2, df3, df4

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_perf_raw = load_data()

# ==========================================
# 3. FILTROS
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados en la hoja principal.")
    st.stop()

if 'Fecha_Filtro' in df_raw.columns:
     df_raw = df_raw.dropna(subset=['Fecha_Filtro'])

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

# APLICAR FILTROS GLOBALES
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    
    # 1. Paros (DATOS)
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # 2. OEE
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw.dropna(subset=['Fecha_Filtro'])
        df_oee_f = df_oee_f[(df_oee_f['Fecha_Filtro'] >= ini) & (df_oee_f['Fecha_Filtro'] <= fin)]
        col_maq_oee = next((c for c in df_oee_f.columns if 'máquina' in c.lower()), None)
        if col_maq_oee: df_oee_f = df_oee_f[df_oee_f[col_maq_oee].isin(máquinas)]
    else: df_oee_f = df_oee_raw
        
    # 3. Producción
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw.dropna(subset=['Fecha_Filtro'])
        df_prod_f = df_prod_f[(df_prod_f['Fecha_Filtro'] >= ini) & (df_prod_f['Fecha_Filtro'] <= fin)]
        col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower()), None)
        if col_maq_prod: df_prod_f = df_prod_f[df_prod_f[col_maq_prod].isin(máquinas)]
    else: df_prod_f = pd.DataFrame()

    # 4. Performance
    if not df_perf_raw.empty and 'Fecha_Filtro' in df_perf_raw.columns:
        df_perf_f = df_perf_raw.dropna(subset=['Fecha_Filtro'])
        df_perf_f = df_perf_f[(df_perf_f['Fecha_Filtro'] >= ini) & (df_perf_f['Fecha_Filtro'] <= fin)]
        col_maq_perf = next((c for c in df_perf_f.columns if 'máquina' in c.lower()), None)
        if col_maq_perf:
            # Filtro flexible
            maquinas_lower = [m.lower().strip() for m in máquinas]
            mask_maq = df_perf_f[col_maq_perf].astype(str).str.lower().str.strip().isin(maquinas_lower)
            df_perf_f = df_perf_f[mask_maq]
    else: df_perf_f = pd.DataFrame()

else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 4. SECCIÓN OEE (KPIs)
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
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
                    m[key] = float(val_promedio / 100 if val_promedio > 1.0 else val_promedio)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

st.caption("Promedios del periodo")
show_metric_row(get_metrics('GENERAL')) 
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
# 5. GRÁFICO HISTÓRICO OEE
# ==========================================
st.markdown("---")
with st.expander("📉 Ver Gráfico de Evolución Histórica OEE", expanded=False):
    if not df_oee_f.empty and 'OEE' in df_oee_f.columns:
        df_trend = df_oee_f.copy()
        if df_trend['OEE'].dtype == 'object':
            df_trend['OEE_Num'] = df_trend['OEE'].astype(str).str.replace('%','').str.replace(',','.').astype(float)
        else:
            df_trend['OEE_Num'] = df_trend['OEE']
        trend_data = df_trend.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
        fig_trend = px.line(trend_data, x='Fecha_Filtro', y='OEE_Num', markers=True, title='Tendencia Diaria del OEE (%)')
        fig_trend.add_hline(y=85, line_dash="dot", annotation_text="Meta (85%)", line_color="green")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No hay datos históricos para graficar.")

# ==============================================================================
# 📋 BLOQUE CENTRAL: ANÁLISIS OPERATIVO
# ==============================================================================
st.markdown("---")
st.header("📋 Análisis Operativo")

# 1. HORARIOS DE TURNO
with st.expander("⏱️ 1. Horarios de Turno (Inicio/Fin)", expanded=False):
    if not df_f.empty:
        c_ini = 'Hora Inicio'; c_fin = 'Hora Fin'; c_tiempo = 'Tiempo (Min)'; c_maq = 'Máquina'; c_fecha = 'Fecha_Filtro'
        if all(col in df_f.columns for col in [c_ini, c_fin, c_tiempo, c_maq, c_fecha]):
            df_calc = df_f[[c_fecha, c_maq, c_ini, c_fin, c_tiempo]].copy()
            def time_str_to_min(val):
                try:
                    val = str(val).strip()
                    if ":" in val: 
                        parts = val.split(":")
                        return int(parts[0]) * 60 + int(parts[1])
                    return None
                except: return None
            df_calc['min_ini'] = df_calc[c_ini].apply(time_str_to_min)
            df_calc['min_fin'] = df_calc[c_fin].apply(time_str_to_min)
            
            df_daily = df_calc.groupby([c_fecha, c_maq]).agg({'min_ini': 'min', 'min_fin': 'max', c_tiempo: 'sum'}).reset_index()
            df_final_avg = df_daily.groupby(c_maq).agg({'min_ini': 'mean', 'min_fin': 'mean', c_tiempo: 'mean'}).reset_index()
            def min_to_time_str(val):
                if pd.isna(val): return "--:--"
                h = int(val // 60); m = int(val % 60)
                return f"{h:02d}:{m:02d}"
            df_final_avg['Promedio Inicio'] = df_final_avg['min_ini'].apply(min_to_time_str)
            df_final_avg['Promedio Fin'] = df_final_avg['min_fin'].apply(min_to_time_str)
            st.dataframe(df_final_avg[[c_maq, 'Promedio Inicio', 'Promedio Fin', c_tiempo]], use_container_width=True, hide_index=True, column_config={c_tiempo: st.column_config.NumberColumn("Tiempo Total Promedio (Min)", format="%.0f min")})
        else: st.warning("Faltan columnas de horario.")
    else: st.info("No hay datos de paros.")

# 2. TIEMPOS DE DESCANSO
with st.expander("☕ 2. Tiempos de Descanso por Operador"):
    if not df_f.empty and 'Operador' in df_f.columns:
        tab_bano, tab_refri = st.tabs(["🚽 Baño", "🥪 Refrigerio"])
        
        def crear_tabla_descanso(keyword, tab_destino):
            col_target = 'Nivel Evento 4'
            col_match = next((c for c in df_f.columns if col_target.lower() in c.lower()), None)
            
            if not col_match:
                with tab_destino: 
                    st.warning(f"No se encontró la columna '{col_target}'.")
                return
            
            mask = df_f[col_match].astype(str).str.contains(keyword, case=False)
            df_sub = df_f[mask]
            
            if not df_sub.empty:
                resumen = df_sub.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                resumen.columns = ['Operador', 'Tiempo Total (Min)', 'Promedio por vez (Min)', 'Eventos']
                resumen = resumen.sort_values('Tiempo Total (Min)', ascending=False)
                with tab_destino:
                    st.dataframe(resumen, use_container_width=True, hide_index=True, column_config={"Tiempo Total (Min)": st.column_config.NumberColumn(format="%.0f min"), "Promedio por vez (Min)": st.column_config.NumberColumn(format="%.1f min")})
            else:
                with tab_destino:
                    st.info(f"No se encontraron registros de '{keyword}'.")
        
        crear_tabla_descanso("Baño", tab_bano)
        crear_tabla_descanso("Refrigerio", tab_refri)
    else:
        st.warning("No se encontró la columna 'Operador'.")


# ==============================================================================
# 🛑 9. ANÁLISIS DETALLADO POR OPERADOR
# ==============================================================================
st.markdown("---")
st.subheader("👤 Análisis Detallado por Operador")

with st.expander("Ver Reporte: Performance, Máquinas y Gráficos", expanded=True):
    
    # LAS 3 PESTAÑAS SOLICITADAS
    tab_op_perf, tab_op_maq, tab_op_graf = st.tabs([
        "📊 Performance Promedio (Fuente: Performance)", 
        "🏗️ Máquinas Iniciadas (Fuente: Producción)", 
        "📈 Evolución Temporal (Fuente: Performance)"
    ])

    # ------------------------------------------------
    # PESTAÑA 1: PERFORMANCE PROMEDIO (Desde Pestaña PERFORMANCE)
    # ------------------------------------------------
    with tab_op_perf:
        if not df_perf_f.empty:
            # Buscamos columnas clave
            c_op = next((c for c in df_perf_f.columns if any(x in c.lower() for x in ['operador', 'operario', 'nombre'])), None)
            c_perf = next((c for c in df_perf_f.columns if any(x in c.lower() for x in ['performance', 'eficiencia', 'vel'])), None)

            if c_op and c_perf:
                # Filtrar vacíos
                df_p_clean = df_perf_f[df_perf_f[c_op].astype(str).str.strip() != '']
                if not df_p_clean.empty:
                    # Agrupar por Operador -> Promedio Performance
                    df_res = df_p_clean.groupby(c_op)[c_perf].mean().reset_index()
                    df_res = df_res.sort_values(c_perf, ascending=False)
                    
                    st.dataframe(
                        df_res,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            c_perf: st.column_config.ProgressColumn(
                                "Performance Promedio (%)", 
                                format="%.1f%%", 
                                min_value=0, 
                                max_value=100
                            )
                        }
                    )
                else:
                    st.info("Hay datos en Performance, pero la columna de Operador está vacía.")
            else:
                st.warning("No se encontraron las columnas 'Operador' o 'Performance' en la pestaña Performance.")
        else:
            st.info("No hay datos en la pestaña Performance para este periodo/máquina.")

    # ------------------------------------------------
    # PESTAÑA 2: MÁQUINAS INICIADAS (Desde Pestaña PRODUCCIÓN)
    # ------------------------------------------------
    with tab_op_maq:
        if not df_prod_f.empty:
            c_op_prod = next((c for c in df_prod_f.columns if 'operador' in c.lower()), None)
            c_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower()), None)
            
            if c_op_prod and c_maq_prod:
                df_prod_clean = df_prod_f[df_prod_f[c_op_prod].astype(str).str.strip() != '']
                
                if not df_prod_clean.empty:
                    # Agrupar por Operador -> Lista única de Máquinas
                    df_maq_op = df_prod_clean.groupby(c_op_prod)[c_maq_prod].unique().apply(lambda x: ", ".join(sorted(map(str, x)))).reset_index()
                    df_maq_op.columns = ['Operador', 'Máquinas Operadas (Producción)']
                    
                    st.dataframe(df_maq_op, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay operadores registrados en Producción.")
            else:
                st.warning("Faltan columnas 'Operador' o 'Máquina' en la pestaña Producción.")
        else:
            st.info("No hay datos en la pestaña Producción para este periodo.")

    # ------------------------------------------------
    # PESTAÑA 3: GRÁFICO EVOLUCIÓN (Desde Pestaña PERFORMANCE)
    # ------------------------------------------------
    with tab_op_graf:
        if not df_perf_f.empty:
            c_op = next((c for c in df_perf_f.columns if any(x in c.lower() for x in ['operador', 'operario'])), None)
            c_perf = next((c for c in df_perf_f.columns if any(x in c.lower() for x in ['performance', 'eficiencia'])), None)
            
            if c_op and c_perf:
                df_graf = df_perf_f[df_perf_f[c_op].astype(str).str.strip() != ''].copy()
                
                if not df_graf.empty:
                    # Agrupar por Fecha y Operador (promedio diario si hay duplicados)
                    df_trend_op = df_graf.groupby(['Fecha_Filtro', c_op])[c_perf].mean().reset_index()
                    
                    fig_op = px.line(
                        df_trend_op, 
                        x='Fecha_Filtro', 
                        y=c_perf, 
                        color=c_op,
                        markers=True,
                        title="Evolución de Performance por Operador",
                        labels={c_perf: 'Performance (%)', 'Fecha_Filtro': 'Fecha'}
                    )
                    st.plotly_chart(fig_op, use_container_width=True)
                else:
                    st.info("No hay datos suficientes para graficar.")
            else:
                st.warning("Columnas no encontradas para el gráfico.")
        else:
            st.info("No hay datos en Performance para el gráfico.")


# ==========================================
# 6. SECCIÓN PRODUCCIÓN
# ==========================================
st.markdown("---")
st.header("Producción")

if not df_prod_f.empty:
    col_maq = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
    col_cod = next((c for c in df_prod_f.columns if any(x in c.lower() for x in ['código', 'codigo', 'producto'])), None)
    col_buenas = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
    col_retrabajo = next((c for c in df_prod_f.columns if 'retrabajo' in c.lower()), None)
    col_observadas = next((c for c in df_prod_f.columns if 'observadas' in c.lower()), None)
    col_ciclo = next((c for c in df_prod_f.columns if 'ciclo' in c.lower()), None)

    if col_maq and col_cod:
        agg_dict = {}
        if col_buenas: agg_dict[col_buenas] = 'sum'
        if col_retrabajo: agg_dict[col_retrabajo] = 'sum'
        if col_observadas: agg_dict[col_observadas] = 'sum'
        if col_ciclo: agg_dict[col_ciclo] = 'mean'

        if agg_dict:
            df_grouped = df_prod_f.groupby([col_maq, col_cod]).agg(agg_dict).reset_index()
            total_buenas = df_grouped[col_buenas].sum() if col_buenas else 0
            st.metric("Total Piezas Buenas", f"{total_buenas:,.0f}")

            with st.expander("📊 Ver Gráfico de Barras de Producción", expanded=False):
                cols_grafico = [c for c in [col_buenas, col_retrabajo, col_observadas] if c is not None]
                if cols_grafico:
                    df_melt = df_grouped.melt(id_vars=[col_maq, col_cod], value_vars=cols_grafico, var_name='Tipo', value_name='Cantidad')
                    fig_prod = px.bar(df_melt, x=col_maq, y='Cantidad', color='Tipo', hover_data=[col_cod], title="Producción por Máquina", barmode='stack')
                    st.plotly_chart(fig_prod, use_container_width=True)
                else: st.warning("No hay columnas numéricas.")

            with st.expander("📋 Ver Tabla Detallada por Código"):
                cols_finales = [col_maq, col_cod]
                if col_buenas: cols_finales.append(col_buenas)
                if col_retrabajo: cols_finales.append(col_retrabajo)
                if col_observadas: cols_finales.append(col_observadas)
                if col_ciclo: cols_finales.append(col_ciclo)
                st.dataframe(df_grouped[cols_finales], use_container_width=True, hide_index=True)
        else: st.warning("No métricas.")
    else: st.warning(f"No columnas Maquina/Codigo.")
else: st.info("No hay datos de producción.")

# ==========================================
# 7. ANÁLISIS DE TIEMPOS Y PAROS
# ==========================================
st.markdown("---")
st.header("⏱️ Análisis de Tiempos y Fallas")

if not df_f.empty:
    t_prod = df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]['Tiempo (Min)'].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Minutos Producción", f"{t_prod:,.0f}")
    c2.metric("Minutos Fallas", f"{t_fallas:,.0f}", delta_color="inverse")
    c3.metric("Total Eventos", len(df_f))

    g1, g2 = st.columns(2)
    with g1: st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
    with g2: 
        if 'Operador' in df_f.columns: st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Tiempos por Operador"), use_container_width=True)

    col_falla = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
    col_cat_falla = 'Nivel Evento 5' if 'Nivel Evento 5' in df_f.columns else None
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
    if col_cat_falla: df_fallas['Etiqueta_Falla'] = df_fallas[col_cat_falla].astype(str) + " - " + df_fallas[col_falla].astype(str)
    else: df_fallas['Etiqueta_Falla'] = df_fallas[col_falla]

    if not df_fallas.empty:
        st.divider()
        st.subheader(f"Top 15 Causas de fallo")
        top15 = df_fallas.groupby('Etiqueta_Falla')['Tiempo (Min)'].sum().reset_index().nlargest(15, 'Tiempo (Min)').sort_values('Tiempo (Min)', ascending=True)
        fig_pareto = px.bar(top15, x='Tiempo (Min)', y='Etiqueta_Falla', orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
        st.plotly_chart(fig_pareto, use_container_width=True)

# ==========================================
# 8. TABLA DETALLADA
# ==========================================
st.divider()
with st.expander("📂 Ver Registro Detallado de Eventos", expanded=True):
    if not df_f.empty:
        df_show = df_f.copy()
        if 'Fecha_DT' in df_show.columns: df_show['Fecha_Txt'] = df_show['Fecha_DT'].dt.strftime('%d-%m-%Y')
        else: df_show['Fecha_Txt'] = 'N/A'
        
        cols_map = {'Fecha_Txt': 'Fecha', 'Máquina': 'Máquina', 'Hora Inicio': 'Hora Inicio', 'Hora Fin': 'Hora Fin', 'Tiempo (Min)': 'Tiempo (min)', 'Evento': 'Evento', 'Nivel Evento 4': 'Subcategoría', 'Nivel Evento 5': 'Categoría Falla', 'Nivel Evento 6': 'Detalle Falla', 'Operador': 'Operador'}
        c_final = [c for c in cols_map.keys() if c in df_show.columns]
        df_final = df_show[c_final].rename(columns=cols_map)
        
        if 'Máquina' in df_final.columns:
            sort_c = ['Máquina']
            if 'Hora Inicio' in df_final.columns: sort_c.append('Hora Inicio')
            df_final = df_final.sort_values(by=sort_c)
            
        st.dataframe(df_final, use_container_width=True, hide_index=True, column_config={"Tiempo (min)": st.column_config.NumberColumn(format="%.0f min")})
    else: st.info("No hay datos.")s: sort_c.append('Hora Inicio')
            df_final = df_final.sort_values(by=sort_c)
            
        st.dataframe(df_final, use_container_width=True, hide_index=True, column_config={"Tiempo (min)": st.column_config.NumberColumn(format="%.0f min")})
    else: st.info("No hay datos.")
