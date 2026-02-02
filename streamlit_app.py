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

        return process_df(base_export + gid_datos), \
               process_df(base_export + gid_oee), \
               process_df(base_export + gid_prod), \
               process_df(base_export + gid_operarios)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS LATERALES (GLOBALES)
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date()
max_d = df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter_unique")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros Globales")

opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
else:
    st.stop()

# ==========================================
# 4. FUNCIONES AUXILIARES
# ==========================================
def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    if not datos.empty:
        for key, col_search in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                vals = pd.to_numeric(datos[actual_col], errors='coerce').dropna()
                if not vals.empty:
                    v = vals.mean()
                    m[key] = float(v/100 if v > 1.1 else v)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

def show_historical_oee(filter_name, title):
    if not df_oee_f.empty:
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
        df_proc = df_oee_f[mask].copy()
        col_oee = next((c for c in df_proc.columns if 'OEE' in c.upper()), None)
        if col_oee and not df_proc.empty:
            df_proc['OEE_Num'] = pd.to_numeric(df_proc[col_oee], errors='coerce')
            if df_proc['OEE_Num'].mean() <= 1.1: df_proc['OEE_Num'] *= 100
            trend = df_proc.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
            fig = px.line(trend, x='Fecha_Filtro', y='OEE_Num', markers=True, title=f'Tendencia OEE: {title}')
            fig.add_hline(y=85, line_dash="dot", annotation_text="Meta 85%", line_color="green")
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 5. DASHBOARD PRINCIPAL
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics('GENERAL'))
with st.expander("📉 Ver Evolución Histórica OEE General"):
    show_historical_oee('GENERAL', 'Planta')

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
with t2:
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')

# ==========================================
# 9. ANÁLISIS DE FALLAS (CON FILTRO POR MÁQUINA)
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")

if not df_f.empty:
    col_cat = next((c for c in df_f.columns if 'nivel evento 3' in c.lower()), None)
    col_det = next((c for c in df_f.columns if 'nivel evento 6' in c.lower()), None)

    if col_cat and col_det:
        # Filtrar solo FALLAS primero
        df_fallas_base = df_f[df_f[col_cat].astype(str).str.contains('FALLA', case=False)].copy()
        
        if not df_fallas_base.empty:
            # --- NUEVO FILTRO INTERNO POR MÁQUINA ---
            maquinas_con_fallas = sorted(df_fallas_base['Máquina'].unique())
            sel_maq_falla = st.multiselect(
                "🔍 Filtrar fallas por Máquina:", 
                options=maquinas_con_fallas,
                default=maquinas_con_fallas,
                help="Seleccione máquinas específicas para ver sus fallas más frecuentes."
            )
            
            # Aplicar filtro de máquina seleccionado en este bloque
            df_fallas_filt = df_fallas_base[df_fallas_base['Máquina'].isin(sel_maq_falla)]

            if not df_fallas_filt.empty:
                # Procesar Top 15 ordenado de mayor a menor
                top_f = (df_fallas_filt.groupby(col_det)['Tiempo (Min)']
                         .sum()
                         .reset_index()
                         .sort_values('Tiempo (Min)', ascending=False)
                         .head(15))

                # Visualización con Gradiente y Etiquetas
                fig_fallas = px.bar(
                    top_f, 
                    x='Tiempo (Min)', 
                    y=col_det, 
                    orientation='h', 
                    title=f"Top 15 Causas de Paro por Falla (Minutos) - {len(sel_maq_falla)} máquina(s)",
                    text='Tiempo (Min)',             
                    color='Tiempo (Min)',           
                    color_continuous_scale='Reds',  
                    labels={'Tiempo (Min)': 'Minutos Totales', col_det: 'Causa de Falla'}
                )
                
                fig_fallas.update_traces(
                    texttemplate='%{text:.0f} min',  
                    textposition='outside'           
                )
                
                fig_fallas.update_layout(
                    coloraxis_showscale=False,      
                    yaxis={'categoryorder':'total ascending'}, 
                    height=600,
                    margin=dict(l=20, r=60, t=50, b=20)
                )
                
                st.plotly_chart(fig_fallas, use_container_width=True)
            else:
                st.info("No hay registros de fallas para las máquinas seleccionadas en este filtro.")
        else:
            st.info("No se registraron paros por 'FALLA' en el periodo seleccionado.")
    else:
        st.warning("No se encontraron las columnas 'Nivel Evento 3' o 'Nivel Evento 6'.")

st.divider()
with st.expander("📂 Ver Registro Detallado de Eventos", expanded=False):
    st.dataframe(df_f, use_container_width=True, hide_index=True)
