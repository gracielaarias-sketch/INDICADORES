import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Indicadores FAMMA", layout="wide", page_icon="🏭")

# ==========================================
# 3. CARGA DE DATOS ROBUSTA
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        try:
            url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        except:
            st.error("⚠️ No se encontró la configuración de secretos (secrets.toml).")
            return pd.DataFrame(), pd.DataFrame()

        gid_datos = "0"
        gid_oee = "1767654796"
        
        url_csv_datos = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_datos}"
        url_csv_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

        def process_df(url):
            df = pd.read_csv(url)
            
            # Limpieza de Tiempos
            if 'Tiempo (Min)' in df.columns:
                df['Tiempo (Min)'] = df['Tiempo (Min)'].astype(str).str.replace(',', '.')
                df['Tiempo (Min)'] = pd.to_numeric(df['Tiempo (Min)'], errors='coerce').fillna(0.0)
            
            # Limpieza de Fechas
            col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
            
            # Rellenar textos nulos para evitar errores en filtros
            for col in ['Fábrica', 'Máquina', 'Evento', 'Nivel Evento 3', 'Nivel Evento 6']:
                if col in df.columns:
                    df[col] = df[col].fillna('Sin Especificar').astype(str)
            
            return df

        return process_df(url_csv_datos), process_df(url_csv_oee)

    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw = load_data()

# ==========================================
# 4. FILTROS
# ==========================================
if df_raw.empty:
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d = df_raw['Fecha_Filtro'].min().date() if not df_raw.empty else None
max_d = df_raw['Fecha_Filtro'].max().date() if not df_raw.empty else None

if min_d and max_d:
    rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="audit_range")
else:
    st.stop()

st.sidebar.header("⚙️ Filtros de Planta")
opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

df_temp = df_raw[df_raw['Fábrica'].isin(fábricas)]
opciones_maquina = sorted(df_temp['Máquina'].unique())
máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
    
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
else:
    st.info("Seleccione un rango de fechas válido.")
    st.stop()

# ==========================================
# 5. OEE SECTION
# ==========================================
st.title("🏭 INDICADORES FAMMA")

# ==========================================
# 5. OEE SECTION
# ==========================================
st.title("OEE Detallado")

def get_metrics(name_filter):
    if df_oee_f.empty: return {'OEE': 0, 'DISP': 0, 'PERF': 0, 'CAL': 0}
    
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_f[mask]
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    
    if not datos.empty:
        cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
        for key, col_search in cols_map.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                val = str(datos[actual_col].iloc[0]).replace('%', '').replace(',', '.')
                val_num = pd.to_numeric(val, errors='coerce')
                m[key] = float(val_num / 100 if val_num > 1.0 else val_num)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

st.subheader("Planta Total")
show_metric_row(get_metrics('GENERAL'))
st.divider()

col_t1, col_t2 = st.tabs(["Estampado", "Soldadura"])

with col_t1:
    st.markdown("**Total Estampado**")
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("Ver detalle Líneas (L1-L4)"):
        for linea in ['L1', 'L2', 'L3', 'L4']:
            st.caption(f"Línea {linea}")
            show_metric_row(get_metrics(linea))

with col_t2:
    st.markdown("**Total Soldadura**")
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("Ver detalle (Celda, PRP)"):
        for sub in ['CELDA', 'PRP']:
            st.caption(f"Proceso {sub}")
            show_metric_row(get_metrics(sub))

# ==========================================
# 6. GRÁFICOS Y TIEMPOS
# ==========================================
st.divider()

if not df_f.empty:
    t_prod = df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False)]['Tiempo (Min)'].sum()
    t_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]['Tiempo (Min)'].sum()
    
    m1, m2, m3 = st.columns(3)
    
    # KPIs (Neutros, sin indicación de pérdida visual)
    m1.metric("Producción Real", f"{t_prod:,.0f} min")
    m2.metric("Tiempo en Fallas", f"{t_fallas:,.0f} min")
    m3.metric("Eventos Registrados", len(df_f))

    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
    with g2:
        st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Rendimiento por Operador"), use_container_width=True)

    # Top 15 Fallas
    col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
    df_f6 = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    
    if not df_f6.empty:
        st.divider()
        st.subheader(f"Top 15 Fallas Detalladas ({col_6})")
        top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
        st.plotly_chart(px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds'), use_container_width=True)

        st.subheader("Mapa de Calor: Máquinas vs Causa")
        pivot_hm = df_f6.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
        st.plotly_chart(px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True), use_container_width=True)

# ==========================================
# 7. INFORME DETALLADO (DIRECTO DE TABLA)
# ==========================================
st.divider()
st.subheader("📋 Registro de Eventos")

with st.expander("📂 Ver registros detallados", expanded=True):
    if not df_f.empty:
        df_export = df_f.copy()

        # Formatear solo la fecha para que se vea corta (la hora la sacamos de las columnas originales)
        if 'Fecha_DT' in df_export.columns:
            df_export['Fecha'] = df_export['Fecha_DT'].dt.strftime('%d-%m-%Y')
            # Ordenar: Máquina -> Fecha/Hora cronológica
            df_export = df_export.sort_values(by=['Máquina', 'Fecha_DT'], ascending=[True, True])
        
        # Lista de columnas que QUIERES mostrar
        # Incluyo variantes comunes por si acaso (Hora Inicio, Hora Fin, Hora_Txt)
        cols_deseadas = [
            'Máquina', 
            'Fecha', 
            'Hora Inicio', 'Hora Fin', 'Hora_Txt', # Busca estas columnas en tu excel
            'Tiempo (Min)', 
            'Evento', 
            'Nivel Evento 3', 
            'Nivel Evento 6', 
            'Operador'
        ]
        
        # Filtramos para mostrar solo las que realmente existen en el archivo
        cols_finales = [c for c in cols_deseadas if c in df_export.columns]

        st.dataframe(
            df_export[cols_finales], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Tiempo (Min)": st.column_config.NumberColumn("Minutos", format="%.1f min")
            }
        )
    else:
        st.info("No hay datos para mostrar con los filtros actuales.")
