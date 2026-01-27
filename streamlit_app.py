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

        # ---------------------------------------------------------
        # 🟢 CONFIGURACIÓN DE GIDs
        # ---------------------------------------------------------
        gid_datos = "0"             # Datos crudos de paros
        gid_oee = "1767654796"      # Datos de OEE
        gid_prod = "315437448"      # PRODUCCION
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
                'Buenas', 'Retrabajo', 'Observadas', 'Tiempo de Ciclo', 'Ciclo'
            ]
            for c in cols_num:
                matches = [col for col in df.columns if c.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].astype(str).str.replace(',', '.')
                    df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
            
            # Limpieza Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                df = df.dropna(subset=['Fecha_Filtro'])
            
            # Rellenar Textos
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Código', 'Producto', 'Referencia', 'Nivel Evento 3', 'Nivel Evento 6', 'Operador', 'Hora Inicio', 'Hora Fin']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)
            return df

        df1 = process_df(base_export + gid_datos)
        df2 = process_df(base_export + gid_oee)
        df3 = process_df(base_export + gid_prod)
        
        return df1, df2, df3

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw = load_data()

# ==========================================
# 3. FILTROS
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados en la hoja principal.")
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

# APLICAR FILTROS
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    
    # 1. Paros
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # 2. OEE
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
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

# KPI Principal
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
    
    # MODIFICADO: Ahora en vertical (Celdas arriba, PRP abajo) como Estampado
    with st.expander("Ver detalle"):
        st.markdown("**Celdas Robotizadas**")
        show_metric_row(get_metrics('CELDA'))
        
        st.markdown("---")
        
        st.markdown("**PRP**")
        show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. GRÁFICO HISTÓRICO OEE (DESPLEGABLE)
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
        
        fig_trend = px.line(trend_data, x='Fecha_Filtro', y='OEE_Num', markers=True,
                            title='Tendencia Diaria del OEE (%)', labels={'OEE_Num': 'OEE', 'Fecha_Filtro': 'Fecha'})
        fig_trend.add_hline(y=85, line_dash="dot", annotation_text="Meta (85%)", line_color="green")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No hay datos históricos para graficar.")

# ==========================================
# 6. SECCIÓN PRODUCCIÓN (CON BARRAS DESPLEGABLES)
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
            
            # KPI Total (Visible)
            total_buenas = df_grouped[col_buenas].sum() if col_buenas else 0
            st.metric("Total Piezas Buenas", f"{total_buenas:,.0f}")

            # Desplegable de Gráfico
            with st.expander("📊 Ver Gráfico de Barras de Producción", expanded=False):
                cols_grafico = [c for c in [col_buenas, col_retrabajo, col_observadas] if c is not None]
                if cols_grafico:
                    df_melt = df_grouped.melt(id_vars=[col_maq, col_cod], value_vars=cols_grafico, var_name='Tipo', value_name='Cantidad')
                    
                    fig_prod = px.bar(
                        df_melt,
                        x=col_maq,
                        y='Cantidad',
                        color='Tipo',
                        hover_data=[col_cod],
                        title="Producción por Máquina (Buenas vs Retrabajo vs Obs.)",
                        barmode='stack',
                        text_auto='.2s'
                    )
                    st.plotly_chart(fig_prod, use_container_width=True)
                else:
                    st.warning("No hay columnas numéricas (Buenas/Retrabajo) para graficar.")

            # Desplegable de Tabla
            with st.expander("📋 Ver Tabla Detallada por Código"):
                cols_finales = [col_maq, col_cod]
                if col_buenas: cols_finales.append(col_buenas)
                if col_retrabajo: cols_finales.append(col_retrabajo)
                if col_observadas: cols_finales.append(col_observadas)
                if col_ciclo: cols_finales.append(col_ciclo)
                
                st.dataframe(
                    df_grouped[cols_finales],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        col_ciclo: st.column_config.NumberColumn("Tiempo Ciclo (s)", format="%.1f s"),
                        col_buenas: st.column_config.NumberColumn("Buenas", format="%d"),
                        col_retrabajo: st.column_config.NumberColumn("Retrabajo", format="%d"),
                        col_observadas: st.column_config.NumberColumn("Observadas", format="%d"),
                    }
                )

        else:
            st.warning("Se encontraron Máquina y Código, pero no las columnas de métricas.")
    else:
        st.warning(f"No se detectaron las columnas 'Máquina' y 'Código'.")
else:
    st.info("No hay datos de producción disponibles.")

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
    with g1:
        st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
    with g2:
        if 'Operador' in df_f.columns:
             st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Tiempos por Operador"), use_container_width=True)

    # Gráficos Detallados de Fallas
    col_falla = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    
    if not df_fallas.empty:
        st.divider()
        st.subheader(f"Top 15 Causas de fallo ({col_falla})")
        
        top15 = df_fallas.groupby(col_falla)['Tiempo (Min)'].sum().nlargest(15).reset_index().sort_values('Tiempo (Min)', ascending=True)
        fig_pareto = px.bar(top15, x='Tiempo (Min)', y=col_falla, orientation='h', text_auto='.0f', color='Tiempo (Min)', color_continuous_scale='Reds', title="Minutos perdidos por tipo de falla")
        st.plotly_chart(fig_pareto, use_container_width=True)

        # -------------------------------------------------------------
        # NUEVO: DESPLEGABLE CON FALLAS POR MÁQUINA (TOP 10)
        # -------------------------------------------------------------
        with st.expander("Top 10 Fallas por Máquina"):
            list_maquinas = sorted(df_fallas['Máquina'].unique())
            if list_maquinas:
                maq_sel = st.selectbox("Seleccione la Máquina a analizar:", list_maquinas)
                
                # Filtrar por máquina seleccionada
                df_maq_falla = df_fallas[df_fallas['Máquina'] == maq_sel]
                
                # Agrupar, ordenar y tomar top 10
                top10_maq = df_maq_falla.groupby(col_falla)['Tiempo (Min)'].sum().nlargest(10).reset_index().sort_values('Tiempo (Min)', ascending=True)
                
                if not top10_maq.empty:
                    fig_top10 = px.bar(
                        top10_maq, 
                        x='Tiempo (Min)', 
                        y=col_falla, 
                        orientation='h', 
                        text_auto='.0f',
                        title=f"Top 10 Fallas: {maq_sel}",
                        color='Tiempo (Min)',
                        color_continuous_scale='Oranges'
                    )
                    st.plotly_chart(fig_top10, use_container_width=True)
                else:
                    st.info(f"No hay registros de fallas para {maq_sel} en este periodo.")
            else:
                st.warning("No hay datos de fallas para las máquinas seleccionadas.")
        # -------------------------------------------------------------

        st.subheader("Mapa de Calor")
        pivot_hm = df_fallas.groupby(['Máquina', col_falla])['Tiempo (Min)'].sum().reset_index()
        pivot_hm = pivot_hm[pivot_hm['Tiempo (Min)'] > 10]
        
        if not pivot_hm.empty:
            fig_hm = px.density_heatmap(pivot_hm, x=col_falla, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

# ==========================================
# 8. TABLA DETALLADA (PERSONALIZADA)
# ==========================================
st.divider()
with st.expander("📂 Ver Registro Detallado de Eventos", expanded=True):
    if not df_f.empty:
        # Copia para no alterar el original
        df_show = df_f.copy()

        # Creamos columna de Fecha texto si no existe (usamos la columna Fecha_DT)
        if 'Fecha_DT' in df_show.columns:
             df_show['Fecha_Txt'] = df_show['Fecha_DT'].dt.strftime('%d-%m-%Y')
        else:
             df_show['Fecha_Txt'] = 'N/A'

        # Mapa de columnas deseadas vs nombres reales en DataFrame
        columnas_mapeo = {
            'Fecha_Txt': 'Fecha',             # Nueva columna creada arriba
            'Máquina': 'Máquina',
            'Hora Inicio': 'Hora Inicio',
            'Hora Fin': 'Hora Fin',
            'Tiempo (Min)': 'Tiempo (min)',
            'Evento': 'Evento',
            'Nivel Evento 6': 'Detalle Falla',
            'Operador': 'Operador'
        }

        # Filtramos solo las que existen
        cols_finales = [c for c in columnas_mapeo.keys() if c in df_show.columns]
        
        # Seleccionamos y renombramos
        df_final = df_show[cols_finales].rename(columns=columnas_mapeo)

        # Ordenar por Máquina primero, luego por Hora Inicio
        if 'Máquina' in df_final.columns:
            sort_cols = ['Máquina']
            if 'Hora Inicio' in df_final.columns:
                sort_cols.append('Hora Inicio')
            
            df_final = df_final.sort_values(by=sort_cols, ascending=True)

        st.dataframe(
            df_final, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Tiempo (min)": st.column_config.NumberColumn("Tiempo (min)", format="%.0f min")
            }
        )
    else:
        st.info("No hay datos para mostrar.")
