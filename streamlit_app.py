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

        # CONFIGURACIÓN DE GIDs
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

        return process_df(base_export + gid_datos), \
               process_df(base_export + gid_oee), \
               process_df(base_export + gid_prod), \
               process_df(base_export + gid_operarios)

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
    
    # Filtrado de Paros
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    # Filtrado de OEE
    if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
        col_maq_oee = next((c for c in df_oee_f.columns if 'máquina' in c.lower()), None)
        if col_maq_oee:
             df_oee_f = df_oee_f[df_oee_f[col_maq_oee].isin(máquinas)]
    else:
        df_oee_f = df_oee_raw

    # Filtrado de Producción
    if not df_prod_raw.empty and 'Fecha_Filtro' in df_prod_raw.columns:
        df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
        col_maq_prod = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
        if col_maq_prod:
            df_prod_f = df_prod_f[df_prod_f[col_maq_prod].isin(máquinas)]
    else:
        df_prod_f = pd.DataFrame()

    # Performance Operarios
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()
else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 4. FUNCIONES DE MÉTRICAS Y GRÁFICOS
# ==========================================
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
                vals = pd.to_numeric(datos[actual_col], errors='coerce').dropna()
                if not vals.empty:
                    val_prom = vals.mean()
                    m[key] = float(val_prom / 100 if val_prom > 1.1 else val_prom)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

def show_historical_oee(filter_name, title):
    if not df_oee_f.empty:
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filter_name.upper()).any(), axis=1)
        df_proc = df_oee_f[mask].copy()
        col_oee = next((c for c in df_proc.columns if 'OEE' in c.upper()), None)
        if col_oee and not df_proc.empty:
            df_proc['OEE_Num'] = pd.to_numeric(df_proc[col_oee], errors='coerce')
            if df_proc['OEE_Num'].mean() <= 1.1: df_proc['OEE_Num'] *= 100
            trend = df_proc.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
            fig = px.line(trend, x='Fecha_Filtro', y='OEE_Num', markers=True, title=f'Tendencia OEE: {title}', labels={'OEE_Num': 'OEE %'})
            fig.add_hline(y=85, line_dash="dot", annotation_text="Meta 85%", line_color="green")
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 5. DASHBOARD PRINCIPAL (OEE)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
st.caption("Promedios del periodo seleccionado")
show_metric_row(get_metrics('GENERAL'))

with st.expander("📉 Ver Evolución Histórica OEE General", expanded=False):
    show_historical_oee('GENERAL', 'Planta General')

st.divider()

t1, t2 = st.tabs(["Estampado", "Soldadura"])

with t1:
    st.markdown("#### Total Estampado")
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("📉 Ver Evolución Histórica OEE - Estampado", expanded=False):
        show_historical_oee('ESTAMPADO', 'Estampado')
    
    with st.expander("Ver detalle por Líneas"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{linea}**")
            show_metric_row(get_metrics(linea))
            st.markdown("---")

with t2:
    st.markdown("#### Total Soldadura")
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("📉 Ver Evolución Histórica OEE - Soldadura", expanded=False):
        show_historical_oee('SOLDADURA', 'Soldadura')
    
    with st.expander("Ver detalle"):
        st.markdown("**Celdas Robotizadas**")
        show_metric_row(get_metrics('CELDA'))
        st.markdown("---")
        st.markdown("**PRP**")
        show_metric_row(get_metrics('PRP'))

# ==========================================
# 6. BLOQUE DE HORARIOS Y DESCANSOS
# ==========================================
st.markdown("---") 
with st.expander("⏱️ Detalle de Horarios y Tiempos", expanded=False):
    if not df_f.empty:
        df_calc = df_f.copy()
        def time_to_min(val):
            try:
                parts = str(val).split(':')
                return int(parts[0]) * 60 + int(parts[1])
            except: return None
        df_calc['min_ini'] = df_calc['Hora Inicio'].apply(time_to_min)
        df_calc['min_fin'] = df_calc['Hora Fin'].apply(time_to_min)
        res_maq = df_calc.groupby(['Fecha_Filtro', 'Máquina']).agg({'min_ini':'min', 'min_fin':'max', 'Tiempo (Min)':'sum'}).reset_index()
        avg_maq = res_maq.groupby('Máquina').mean().reset_index()
        avg_maq['Inicio'] = avg_maq['min_ini'].apply(lambda x: f"{int(x//60):02d}:{int(x%60):02d}" if pd.notnull(x) else "--:--")
        avg_maq['Fin'] = avg_maq['min_fin'].apply(lambda x: f"{int(x//60):02d}:{int(x%60):02d}" if pd.notnull(x) else "--:--")
        st.dataframe(avg_maq[['Máquina', 'Inicio', 'Fin', 'Tiempo (Min)']], use_container_width=True, hide_index=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    tabs_desc = st.tabs(["Baño", "Refrigerio"])
    for i, label in enumerate(["Baño", "Refrigerio"]):
        with tabs_desc[i]:
            df_desc = df_f[df_f['Nivel Evento 4'].astype(str).str.contains(label, case=False)]
            if not df_desc.empty:
                res = df_desc.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                st.dataframe(res, use_container_width=True)
            else: st.info(f"Sin datos de {label}")

# ==========================================
# 7. INDICADORES DIARIOS OPERARIOS
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS")
with st.expander("👉 Desplegar Análisis Diario (Operarios)", expanded=False):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if 'nombre' in c.lower() or 'operador' in c.lower()), None)
        if col_op:
            df_days = df_op_f.groupby(col_op)['Fecha_Filtro'].nunique().reset_index(name='Días')
            st.dataframe(df_days.sort_values('Días', ascending=False), use_container_width=True, hide_index=True)
            sel_ops = st.multiselect("Seleccione Operarios:", sorted(df_op_f[col_op].unique()))
            if sel_ops:
                df_filt_op = df_op_f[df_op_f[col_op].isin(sel_ops)]
                st.plotly_chart(px.line(df_filt_op, x='Fecha_Filtro', y='Performance', color=col_op, markers=True), use_container_width=True)

# ==========================================
# 8. PRODUCCIÓN GENERAL
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    col_buenas = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), None)
    if col_buenas:
        st.metric("Total Piezas Buenas", f"{df_prod_f[col_buenas].sum():,.0f}")
        with st.expander("📊 Gráfico de Producción"):
            fig_p = px.bar(df_prod_f, x='Máquina', y=col_buenas, color='Máquina', title="Piezas por Máquina")
            st.plotly_chart(fig_p, use_container_width=True)

# ==========================================
# 9. ANÁLISIS DE FALLAS Y TABLA FINAL
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")

if not df_f.empty:
    # Filtramos solo eventos que contienen la palabra FALLA en el Nivel 3
    df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
    
    if not df_fallas.empty:
        # Agrupamos por detalle de falla (Nivel 6) y sumamos tiempo
        # nlargest(15) obtiene el top, y sort_values(ascending=True) asegura que al graficar 
        # horizontalmente, la barra más larga (la primera del top) quede arriba.
        top_f = (df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)']
                 .sum()
                 .reset_index()
                 .nlargest(15, 'Tiempo (Min)')
                 .sort_values('Tiempo (Min)', ascending=True))
        
        # Creación del gráfico con gradiente y etiquetas
        fig_fallas = px.bar(
            top_f, 
            x='Tiempo (Min)', 
            y='Nivel Evento 6', 
            orientation='h', 
            title="Top 15 Causas de Paro por Falla (Minutos)",
            text_auto='.0f',               # Muestra el dato en la barra sin decimales
            color='Tiempo (Min)',          # Variable para el gradiente
            color_continuous_scale='Reds', # Escala de colores (tonos rojos)
            labels={'Tiempo (Min)': 'Minutos Totales', 'Nivel Evento 6': 'Causa de Falla'}
        )
        
        # Mejoras estéticas: quitar barra de escala lateral y forzar orden visual
        fig_fallas.update_layout(
            coloraxis_showscale=False,
            yaxis={'categoryorder':'total ascending'}
        )
        
        st.plotly_chart(fig_fallas, use_container_width=True)
    else:
        st.info("No se registraron paros por 'FALLA' en este periodo.")

with st.expander("📂 Ver Registro Detallado de Eventos", expanded=False):
    st.dataframe(df_f, use_container_width=True, hide_index=True)
