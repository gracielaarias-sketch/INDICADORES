
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

        # 🟢 CONFIGURACIÓN DE GIDs
        gid_datos = "0"             
        gid_oee = "1767654796"      
        gid_prod = "315437448"      
        gid_operarios = "354131379" 

        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url, is_prod=False):
            try:
                df = pd.read_csv(url)
            except Exception:
                return pd.DataFrame()
            
            # Limpieza Numérica General
            cols_num = [
                'Tiempo (Min)', 'Cantidad', 'Piezas', 'Produccion', 'Total',
                'Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)', 
                'Tiempo de Ciclo', 'Ciclo', 'OEE', 'Disponibilidad', 'Calidad'
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
                'Nivel Evento 3', 'Nivel Evento 4', 'Operador', 'Nombre', 'Apellido', 'Turno'
            ]
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)

            if is_prod:
                # Mapeo por posición basado en tus datos crudos para evitar KeyError
                # H=7, I=8, J=9, K=10, M=12
                mapping = {
                    df.columns[7]: 'Buenas', 
                    df.columns[8]: 'Retrabajo', 
                    df.columns[9]: 'Observadas', 
                    df.columns[10]: 'T_Prod_Real_K',
                    df.columns[12]: 'Ciclo_Teorico_M'
                }
                df = df.rename(columns=mapping)
            
            return df

        df1 = process_df(base_export + gid_datos)
        df2 = process_df(base_export + gid_oee)
        df3 = process_df(base_export + gid_prod, is_prod=True)
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
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="main_date_filter_unique")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")
opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)
df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
máquinas = st.sidebar.multiselect("Máquina", sorted(df_temp['Máquina'].unique()), default=sorted(df_temp['Máquina'].unique()))

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    es_rango = (ini != fin)
    
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin) & (df_raw['Máquina'].isin(máquinas))]
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin) & (df_prod_raw['Máquina'].isin(máquinas))]
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()
else:
    st.stop()

# ==========================================
# 4. SECCIÓN OEE (KPIs)
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_metrics(name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    
    if es_rango:
        # 1. Filtrado para cálculo matemático
        if name_filter.upper() == 'GENERAL':
            d_paros, d_prod = df_f, df_prod_f
        else:
            d_paros = df_f[df_f.apply(lambda r: name_filter.upper() in str(r).upper(), axis=1)]
            d_prod = df_prod_f[df_prod_f.apply(lambda r: name_filter.upper() in str(r).upper(), axis=1)]
        
        if not d_paros.empty and not d_prod.empty:
            # Disponibilidad (Basado en Pestaña Datos)
            t_produccion = d_paros[d_paros['Evento'].str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
            t_paradas = d_paros[d_paros['Evento'].str.contains('Parada', case=False)]['Tiempo (Min)'].sum()
            disp = t_produccion / (t_produccion + t_paradas) if (t_produccion + t_paradas) > 0 else 0
            
            # Calidad (Buenas vs Malas [Ret+Obs])
            buenas = d_prod['Buenas'].sum()
            malas = d_prod['Retrabajo'].sum() + d_prod['Observadas'].sum()
            cal = buenas / (buenas + malas) if (buenas + malas) > 0 else 0
            
            # Performance (Ciclo Teorico vs Tiempo Real Columna K)
            t_teorico_seg = (buenas + malas) * d_prod['Ciclo_Teorico_M'].mean()
            t_real_seg = d_prod['T_Prod_Real_K'].sum() * 60
            perf = t_teorico_seg / t_real_seg if t_real_seg > 0 else 0
            perf = min(perf, 1.0)
            
            return {'OEE': disp * perf * cal, 'DISP': disp, 'PERF': perf, 'CAL': cal}

    # 2. Lógica para día único o si el cálculo de rango no tiene datos
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    if not datos.empty:
        cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
        for key, col_search in cols_map.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                val = datos[actual_col].mean()
                m[key] = float(val / 100 if val > 1.1 else val)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

st.caption(f"Modo: {'Cálculo Matemático (Rango)' if es_rango else 'Lectura Directa (Día)'}")
show_metric_row(get_metrics('GENERAL'))

# ------------------------------------------------------------------------
# 📉 GRÁFICO HISTÓRICO OEE
# ------------------------------------------------------------------------
with st.expander("📉 Ver Gráfico de Evolución Histórica OEE", expanded=False):
    if not df_oee_f.empty:
        df_trend = df_oee_f.copy()
        c_oee = next((c for c in df_trend.columns if 'OEE' in c.upper()), None)
        if c_oee:
            df_trend['V'] = pd.to_numeric(df_trend[c_oee], errors='coerce').apply(lambda x: x/100 if x > 1.1 else x)
            fig = px.line(df_trend.groupby('Fecha_Filtro')['V'].mean().reset_index(), x='Fecha_Filtro', y='V', markers=True)
            st.plotly_chart(fig.update_layout(yaxis_tickformat='.0%'), use_container_width=True)

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    st.markdown("#### Total Estampado"); show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("Ver detalle por Líneas"):
        for linea in ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4']:
            st.markdown(f"**{linea}**"); show_metric_row(get_metrics(linea))
with t2:
    st.markdown("#### Total Soldadura"); show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("Ver detalle"):
        st.markdown("**Celdas Robotizadas**"); show_metric_row(get_metrics('Cell'))
        st.markdown("**PRP**"); show_metric_row(get_metrics('PRP'))

# ==========================================
# 5. BLOQUE DE HORARIOS Y DESCANSOS
# ==========================================
st.markdown("---") 
with st.expander("⏱️ Detalle de Horarios y Tiempos", expanded=False):
    if not df_f.empty:
        st.dataframe(df_f[['Máquina','Hora Inicio','Hora Fin','Tiempo (Min)','Evento']], use_container_width=True, hide_index=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    if not df_f.empty and 'Operador' in df_f.columns:
        col_desc = next((c for c in df_f.columns if 'Evento 4' in c), df_f.columns[0])
        st.dataframe(df_f[df_f[col_desc].str.contains('Baño|Refrigerio', case=False)].groupby(['Operador', col_desc])['Tiempo (Min)'].sum().reset_index(), use_container_width=True)

# ==========================================
# 6. INDICADORES DIARIOS (OPERARIOS)
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES DIARIOS")
with st.expander("👉 Desplegar Análisis Diario", expanded=False):
    if not df_op_f.empty:
        sel_ops = st.multiselect("👤 Seleccione Operarios:", sorted(df_op_f['Operador'].unique()))
        if sel_ops:
            df_g = df_op_f[df_op_f['Operador'].isin(sel_ops)]
            st.plotly_chart(px.line(df_g, x='Fecha_Filtro', y='OEE', color='Operador', markers=True), use_container_width=True)

# ==========================================
# 7. PRODUCCIÓN GENERAL
# ==========================================
st.markdown("---") 
st.header("Producción General")
if not df_prod_f.empty:
    st.metric("Total Piezas Buenas", f"{df_prod_f['Buenas'].sum():,.0f}")
    st.plotly_chart(px.bar(df_prod_f.groupby('Máquina')['Buenas'].sum().reset_index(), x='Máquina', y='Buenas', text_auto='.2s'), use_container_width=True)

# ==========================================
# 8. ANÁLISIS DE FALLAS
# ==========================================
st.header("Análisis de Tiempos y Fallas")
if not df_f.empty:
    df_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)].copy()
    if not df_fallas.empty:
        col_f = 'Nivel Evento 6' if 'Nivel Evento 6' in df_fallas.columns else df_fallas.columns[5]
        top15 = df_fallas.groupby(col_f)['Tiempo (Min)'].sum().nlargest(15).reset_index()
        st.plotly_chart(px.bar(top15, x='Tiempo (Min)', y=col_f, orientation='h', title="Top 15 Causas de fallo"), use_container_width=True)

with st.expander("📂 Registro Detallado"):
    st.dataframe(df_f, use_container_width=True)
