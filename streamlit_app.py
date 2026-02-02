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
        gid_datos = "0"             # Datos crudos de paros
        gid_oee = "1767654796"      # Datos de OEE
        gid_prod = "315437448"      # PRODUCCION
        gid_operarios = "354131379" # PERFO OPERARIOS
        # ---------------------------------------------------------

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
                'Eficiencia', 'Performance', 'Cumplimiento', 'Meta', 'Objetivo', 'OEE'
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
# Key única para evitar errores de duplicado
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
    
    # 1. Paros
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # 2. OEE General
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
        col_maq_oee = next((c for c in df_oee_f.columns if 'máquina' in c.lower()), None)
        if col_maq_oee:
             df_oee_f = df_oee_f[df_oee_f[col_maq_oee].isin(máquinas)]
    else:
        df_oee_f = df_oee_raw
        
    # 3. Producción
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
        col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
        if col_maq_prod:
            df_prod_f = df_prod_f[df_prod_f[col_maq_prod].isin(máquinas)]
    else:
        df_prod_f = pd.DataFrame()

    # 4. Operarios (Performance)
    if not df_operarios_raw.empty and 'Fecha_Filtro' in df_operarios_raw.columns:
         df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]
    else:
         df_op_f = pd.DataFrame()
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

# --- KPI Principal ---
st.caption("Promedios del periodo")
show_metric_row(get_metrics('GENERAL')) 

# ------------------------------------------------------------------------
# 📉 GRÁFICO HISTÓRICO OEE
# ------------------------------------------------------------------------
with st.expander("📉 Ver Gráfico de Evolución Histórica OEE", expanded=False):
    if not df_oee_f.empty:
        col_oee_trend = next((c for c in df_oee_f.columns if 'OEE' in c.upper()), None)
        if col_oee_trend:
             df_trend = df_oee_f.copy()
             if df_trend[col_oee_trend].dtype == 'object':
                df_trend['OEE_Num'] = df_trend[col_oee_trend].astype(str).str.replace('%','').str.replace(',','.').astype(float)
             else:
                df_trend['OEE_Num'] = df_trend[col_oee_trend]
             
             trend_data = df_trend.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
             
             fig_trend = px.line(trend_data, x='Fecha_Filtro', y='OEE_Num', markers=True,
                                 title='Tendencia Diaria del OEE (%)', labels={'OEE_Num': 'OEE', 'Fecha_Filtro': 'Fecha'})
             fig_trend.add_hline(y=85, line_dash="dot", annotation_text="Meta (85%)", line_color="green")
             st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("No se encontró columna OEE para graficar.")
    else:
        st.info("No hay datos históricos para graficar.")

# ------------------------------------------------------------------------
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

# --- 5.1 INICIO Y FIN DE TURNO ---
with st.expander("⏱️ Detalle de Horarios y Tiempos", expanded=False):
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
            st.warning("Faltan columnas 'Hora Inicio' o 'Hora Fin'.")
    else:
        st.info("No hay datos cargados.")

# --- 5.2 BAÑO Y REFRIGERIO ---
with st.expander("☕ Tiempos de Baño y Refrigerio"):
    if not df_f.empty and 'Operador' in df_f.columns:
        
        tab_bano, tab_refri = st.tabs(["Baño", "Refrigerio"])

        def crear_tabla_descanso(keyword, tab_destino):
            col_target = 'Nivel Evento 4'
            col_match = next((c for c in df_f.columns if col_target.lower() in c.lower()), None)
            
            if not col_match:
                with tab_destino: st.warning(f"No se encontró la columna '{col_target}'.")
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
                    st.info(f"No se encontraron registros de '{keyword}'.")

        crear_tabla_descanso("Baño", tab_bano)
        crear_tabla_descanso("Refrigerio", tab_refri)
    else:
        st.warning("No se encontró la columna 'Operador'.")

# =========================================================
# 6. SECCIÓN: INDICADORES DIARIOS (EN DESPLEGABLE)
# =========================================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS")

with st.expander("👉 Desplegar Análisis Diario (Operarios y Máquinas)", expanded=False):
    if not df_op_f.empty:
        # 1. IDENTIFICACIÓN DE COLUMNAS
        col_op_name = next((c for c in df_op_f.columns if any(x in c.lower() for x in ['operador', 'nombre', 'empleado'])), None)
        cols_metrics = [c for c in df_op_f.select_dtypes(include=['number']).columns 
                        if 'fecha' not in c.lower() and 'gid' not in c.lower()]
        col_metric_graph = next((c for c in cols_metrics if 'oee' in c.lower()), 
                           next((c for c in cols_metrics if 'efic' in c.lower()), 
                           next((c for c in cols_metrics if 'perf' in c.lower()), None)))

        if col_op_name and col_metric_graph:
            
            # --- TABLA DE RESUMEN DE DÍAS (NUEVA IMPLEMENTACIÓN) ---
            st.subheader("📋 Resumen de Días Registrados")
            # Agrupar por operario y contar fechas únicas
            df_dias_count = df_op_f.groupby(col_op_name)['Fecha_Filtro'].nunique().reset_index()
            df_dias_count.columns = ['Operador', 'Días con Registro']
            df_dias_count = df_dias_count.sort_values(by='Días con Registro', ascending=False)
            
            st.dataframe(
                df_dias_count,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Días con Registro": st.column_config.NumberColumn(format="%d días")
                }
            )
            st.divider()

            # 2. SELECTOR DE OPERARIOS
            lista_operarios = sorted(df_op_f[col_op_name].astype(str).unique())
            st.subheader("Selección de Personal para Gráficos")
            
            sel_operarios = st.multiselect(
                "👤 Seleccione Operarios para visualizar evolución:", 
                lista_operarios,
                placeholder="Escriba o seleccione nombres..."
            )

            if sel_operarios:
                # A. GRÁFICO
                df_graph = df_op_f[df_op_f[col_op_name].astype(str).isin(sel_operarios)].copy()
                df_graph = df_graph.sort_values(by='Fecha_Filtro')
                is_scale_100 = df_graph[col_metric_graph].max() > 1.5
                
                fig_daily = px.line(
                    df_graph, 
                    x='Fecha_Filtro', 
                    y=col_metric_graph, 
                    color=col_op_name,
                    markers=True,
                    title=f"Evolución Diaria: {col_metric_graph}",
                    labels={'Fecha_Filtro': 'Fecha', col_metric_graph: 'Valor', col_op_name: 'Operario'}
                )
                if not is_scale_100: fig_daily.update_layout(yaxis_tickformat='.0%')
                st.plotly_chart(fig_daily, use_container_width=True)

                # B. TABLA DE MÁQUINAS (BÚSQUEDA 1-6)
                st.markdown("#### 🏗️ Detalle de Actividad en Máquinas")
                if not df_prod_f.empty:
                    c_maq_prod = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), None)
                    c_piezas = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
                    cols_usuarios = []
                    for i in range(1, 7):
                        col = next((c for c in df_prod_f.columns if 'usuario' in c.lower() and str(i) in c), None)
                        if col: cols_usuarios.append(col)

                    if cols_usuarios and c_maq_prod:
                        id_vars = ['Fecha_Filtro', c_maq_prod]
                        if c_piezas: id_vars.append(c_piezas)
                        
                        df_melted = df_prod_f.melt(id_vars=id_vars, value_vars=cols_usuarios, value_name='Operador_Encontrado').dropna(subset=['Operador_Encontrado'])
                        df_maq_op = df_melted[df_melted['Operador_Encontrado'].astype(str).isin(sel_operarios)].copy()
                        
                        if not df_maq_op.empty:
                            cols_group = ['Fecha_Filtro', 'Operador_Encontrado', c_maq_prod]
                            if c_piezas:
                                df_table_maq = df_maq_op.groupby(cols_group)[c_piezas].sum().reset_index()
                            else:
                                df_table_maq = df_maq_op.groupby(cols_group).size().reset_index(name='Registros')
                            
                            df_table_maq = df_table_maq.sort_values(by=['Fecha_Filtro', 'Operador_Encontrado'], ascending=[False, True])
                            df_table_maq['Fecha'] = df_table_maq['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
                            
                            cols_finales_t = ['Fecha', 'Operador_Encontrado', c_maq_prod]
                            if c_piezas: cols_finales_t.append(c_piezas)
                            
                            st.dataframe(
                                df_table_maq[cols_finales_t],
                                use_container_width=True, hide_index=True,
                                column_config={
                                    c_piezas: st.column_config.NumberColumn("Piezas Buenas", format="%d") if c_piezas else None,
                                    c_maq_prod: "Máquina", 'Operador_Encontrado': "Operario"
                                }
                            )
                        else:
                            st.warning(f"Los operarios seleccionados no aparecen como Usuario (1-6) en Producción.")
                    else:
                        st.warning("Faltan columnas de Usuario o Máquina en Producción.")
                else:
                    st.info("No hay datos de producción.")
            else:
                st.info("👆 Seleccione operarios para ver datos.")
        else:
            st.warning("No se detectaron columnas de métricas u operarios.")
    else:
        st.info("No hay datos de Performance de Operarios.")

# ==========================================
# 7. SECCIÓN PRODUCCIÓN GENERAL
# ==========================================
st.markdown("---") 
st.header("Producción General")

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
            # Calculamos agrupación para el gráfico (Total por maq y cod)
            df_grouped_total = df_prod_f.groupby([col_maq, col_cod]).agg(agg_dict).reset_index()
            
            total_buenas = df_grouped_total[col_buenas].sum() if col_buenas else 0
            st.metric("Total Piezas Buenas (Global)", f"{total_buenas:,.0f}")

            # ----------------------------------------------------
            # GRÁFICO DE BARRAS
            # ----------------------------------------------------
            with st.expander("📊 Ver Gráfico de Barras de Producción", expanded=False):
                cols_grafico = [c for c in [col_buenas, col_retrabajo, col_observadas] if c is not None]
                if cols_grafico:
                    df_melt = df_grouped_total.melt(id_vars=[col_maq, col_cod], value_vars=cols_grafico, var_name='Tipo', value_name='Cantidad')
                    fig_prod = px.bar(
                        df_melt, x=col_maq, y='Cantidad', color='Tipo',
                        hover_data=[col_cod], title="Producción por Máquina",
                        barmode='stack', text_auto='.2s'
                    )
                    st.plotly_chart(fig_prod, use_container_width=True)

            # ----------------------------------------------------
            # TABLA 1: PRODUCCIÓN DETALLADA POR FECHA
            # ----------------------------------------------------
            with st.expander("📅 Producción Detallada por Fecha", expanded=False):
                # Agrupamos también por Fecha
                df_grouped_date = df_prod_f.groupby(['Fecha_Filtro', col_maq, col_cod]).agg(agg_dict).reset_index()
                
                # Formato y Orden
                df_grouped_date = df_grouped_date.sort_values(by=['Fecha_Filtro', col_maq], ascending=[False, True])
                df_grouped_date['Fecha'] = df_grouped_date['Fecha_Filtro'].dt.strftime('%d-%m-%Y')

                cols_finales_date = ['Fecha', col_maq, col_cod]
                if col_buenas: cols_finales_date.append(col_buenas)
                if col_retrabajo: cols_finales_date.append(col_retrabajo)
                if col_observadas: cols_finales_date.append(col_observadas)

                st.dataframe(
                    df_grouped_date[cols_finales_date],
                    use_container_width=True, hide_index=True,
                    column_config={
                        col_buenas: st.column_config.NumberColumn("Buenas", format="%d"),
                        col_maq: "Máquina",
                        col_cod: "Código"
                    }
                )

            # ----------------------------------------------------
            # TABLA 2: SUMA TOTAL POR MÁQUINA Y PRODUCTO (CON SELECTOR Y TOTAL)
            # ----------------------------------------------------
            with st.expander("∑ Resumen Acumulado por Máquina y Producto", expanded=False):
                
                # 1. Selector de Máquinas
                maquinas_disponibles = sorted(df_grouped_total[col_maq].astype(str).unique())
                sel_maq_acum = st.multiselect("🔍 Filtrar Máquinas (Dejar vacío para ver todas):", maquinas_disponibles)
                
                # 2. Filtrado
                df_acum_show = df_grouped_total.copy()
                if sel_maq_acum:
                    df_acum_show = df_acum_show[df_acum_show[col_maq].astype(str).isin(sel_maq_acum)]

                # 3. Ordenamiento
                df_acum_show = df_acum_show.sort_values(by=[col_maq, col_buenas] if col_buenas else [col_maq], ascending=[True, False])

                # 4. Cálculo y Agregado de Fila TOTAL
                if not df_acum_show.empty:
                    cols_finales_total = [col_maq, col_cod]
                    
                    # Totales
                    sum_buenas = df_acum_show[col_buenas].sum() if col_buenas else 0
                    sum_retrabajo = df_acum_show[col_retrabajo].sum() if col_retrabajo else 0
                    sum_obs = df_acum_show[col_observadas].sum() if col_observadas else 0
                    
                    # Crear fila Total
                    row_total = {col_maq: 'TOTAL', col_cod: ''}
                    if col_buenas: 
                        cols_finales_total.append(col_buenas)
                        row_total[col_buenas] = sum_buenas
                    if col_retrabajo: 
                        cols_finales_total.append(col_retrabajo)
                        row_total[col_retrabajo] = sum_retrabajo
                    if col_observadas: 
                        cols_finales_total.append(col_observadas)
                        row_total[col_observadas] = sum_obs
                    if col_ciclo: 
                        cols_finales_total.append(col_ciclo)
                        row_total[col_ciclo] = 0 

                    # Concatenar la fila de total al final
                    df_total_row = pd.DataFrame([row_total])
                    df_acum_show = pd.concat([df_acum_show, df_total_row], ignore_index=True)

                    st.dataframe(
                        df_acum_show[cols_finales_total],
                        use_container_width=True, hide_index=True,
                        column_config={
                            col_ciclo: st.column_config.NumberColumn("Ciclo Prom (s)", format="%.1f s"),
                            col_buenas: st.column_config.NumberColumn("Total Buenas", format="%d"),
                            col_maq: "Máquina",
                            col_cod: "Código de Producto"
                        }
                    )
                else:
                    st.info("No hay datos para las máquinas seleccionadas.")

    else:
        st.warning("Faltan columnas clave en Producción.")
else:
    st.info("No hay datos de producción.")

# ==========================================
# 8. ANÁLISIS DE TIEMPOS Y PAROS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos y Fallas")

if not df_f.empty:
    t_prod = df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]['Tiempo (Min)'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Minutos Producción", f"{t_prod:,.0f}")
    c2.metric("Minutos Fallas", f"{t_fallas:,.0f}", delta_color="inverse")
    c3.metric("Total Eventos", len(df_f))

    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
    with g2:
        if 'Operador' in df_f.columns:
             st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Tiempos por Operador"), use_container_width=True)

    # Fallas
    col_falla = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
    
    if not df_fallas.empty:
        df_fallas['Etiqueta'] = df_fallas[col_falla]
        st.divider()
        st.subheader(f"Top 15 Causas de fallo")
        top15 = df_fallas.groupby('Etiqueta')['Tiempo (Min)'].sum().reset_index().nlargest(15, 'Tiempo (Min)').sort_values('Tiempo (Min)', ascending=True)

        fig_pareto = px.bar(top15, x='Tiempo (Min)', y='Etiqueta', orientation='h', text_auto='.0f', color='Tiempo (Min)', title="Pareto de Fallas")
        st.plotly_chart(fig_pareto, use_container_width=True)

# ==========================================
# 9. TABLA DETALLADA
# ==========================================
st.divider()

with st.expander("📂 Ver Registro Detallado de Eventos", expanded=True):
    if not df_f.empty:
        df_show = df_f.copy()
        df_show['Fecha_Txt'] = df_show['Fecha_DT'].dt.strftime('%d-%m-%Y') if 'Fecha_DT' in df_show.columns else 'N/A'

        columnas_mapeo = {
            'Fecha_Txt': 'Fecha', 'Máquina': 'Máquina', 'Hora Inicio': 'Hora Inicio',
            'Hora Fin': 'Hora Fin', 'Tiempo (Min)': 'Tiempo (min)', 'Evento': 'Evento',
            'Nivel Evento 5': 'Categoría Falla', 'Nivel Evento 6': 'Detalle Falla', 'Operador': 'Operador'
        }
        cols_finales = [c for c in columnas_mapeo.keys() if c in df_show.columns]
        df_final = df_show[cols_finales].rename(columns=columnas_mapeo)
        
        st.dataframe(df_final, use_container_width=True, hide_index=True)
    else:
        st.info("No hay datos para mostrar.")
