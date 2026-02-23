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

        gid_datos, gid_oee, gid_prod, gid_operarios = "0", "1767654796", "315437448", "354131379"
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
            except Exception: return pd.DataFrame()
            
            # Limpieza Numérica
            cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia']
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
            
            # Limpieza Textos
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Código', 'Operador', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6', 'Nombre']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str)
            return df

        return process_df(base_export + gid_datos), process_df(base_export + gid_oee), \
               process_df(base_export + gid_prod), process_df(base_export + gid_operarios)
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")

opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", options=opciones_maquina, default=opciones_maquina)

# Manejo robusto de fechas
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
elif isinstance(rango, (list, tuple)) and len(rango) == 1:
    ini = fin = pd.to_datetime(rango[0])
else:
    ini = fin = pd.to_datetime(min_d)

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]

df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()

# ==========================================
# 4. FUNCIONES KPI
# ==========================================
def get_metrics_by_list(machines_list):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    
    # Buscamos coincidencias en la columna Máquina
    c_maq = next((c for c in df_oee_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
    if c_maq:
        datos = df_oee_f[df_oee_f[c_maq].isin(machines_list)]
    else:
        # Fallback si no encuentra la columna exacta, busca en toda la fila
        mask = df_oee_f.apply(lambda row: any(str(m).upper() in row.astype(str).str.upper().values for m in machines_list), axis=1)
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

def get_metrics(name_filter):
    # Función original para mantener compatibilidad con el Layout
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
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filter_name.upper()).any(), axis=1)
        df_proc = df_oee_f[mask].copy()
        col_oee = next((c for c in df_proc.columns if 'OEE' in c.upper()), None)
        if col_oee and not df_proc.empty:
            df_proc['OEE_Num'] = pd.to_numeric(df_proc[col_oee], errors='coerce')
            if df_proc['OEE_Num'].mean() <= 1.1: df_proc['OEE_Num'] *= 100
            trend = df_proc.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
            st.plotly_chart(px.line(trend, x='Fecha_Filtro', y='OEE_Num', markers=True, title=f'OEE: {title}'), use_container_width=True)

# ==========================================
# 5. DASHBOARD Y PESTAÑAS (OEE)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics('GENERAL'))
with st.expander("📉 Histórico OEE General"): show_historical_oee('GENERAL', 'Planta')

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
    with st.expander("Ver Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{l}**"); show_metric_row(get_metrics(l)); st.markdown("---")
with t2:
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')
    with st.expander("Ver Detalle"):
        st.markdown("**Celdas Robotizadas**"); show_metric_row(get_metrics('CELDA')); st.markdown("---")
        st.markdown("**PRP**"); show_metric_row(get_metrics('PRP'))

# ... [Módulos 6 al 10 se mantienen iguales] ...
# ==========================================
# (Omitidos en esta visualización por brevedad, pero presentes en tu archivo final)

# 11. EXPORTACIÓN A PDF POR ÁREA (CORREGIDO)
# ==========================================
st.markdown("---")
st.header("📄 Exportar Reportes PDF")

try:
    from fpdf import FPDF
    import tempfile
    import os
except ImportError:
    st.warning("⚠️ Faltan librerías para exportar.")

def clean_text(text):
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def draw_pdf_table(pdf, df, col_widths, max_rows=10):
    if df.empty:
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 8, "No hay datos.", ln=True)
        return
    pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, col_widths): pdf.cell(width, 8, clean_text(col)[:25], border=1, align='C', fill=True)
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
    for i, (_, row) in enumerate(df.head(max_rows).iterrows()):
        pdf.set_fill_color(236, 240, 241) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        for item, width in zip(row, col_widths):
            val = clean_text(item)
            if isinstance(item, float): val = f"{item:.2f}"
            pdf.cell(width, 8, val[:25], border=1, align='C', fill=True)
        pdf.ln()

def generar_pdf_area(area_nombre, lineas_incluidas, es_soldadura=False):
    pdf = FPDF()
    pdf.add_page()
    
    # Título y Fecha
    pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 8, f"REPORTE DE INDICADORES - {area_nombre.upper()}", ln=True, align='C')
    pdf.set_font("Arial", 'I', 11); pdf.set_text_color(100, 100, 100)
    texto_f = f"Periodo: {ini.strftime('%d/%m/%Y')} al {fin.strftime('%d/%m/%Y')}"
    pdf.cell(0, 6, texto_f, ln=True, align='C'); pdf.ln(5)

    # Lógica de Filtrado por Máquina (ESTRICTA)
    c_maq = next((c for c in df_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), 'Máquina')
    if es_soldadura:
        df_area = df_f[~df_f[c_maq].isin(lineas_incluidas)].copy() # Todo lo que NO sea L1-L4
        listado_maquinas_final = sorted(df_area[c_maq].unique())
    else:
        df_area = df_f[df_f[c_maq].isin(lineas_incluidas)].copy() # Solo L1-L4
        listado_maquinas_final = lineas_incluidas

    # 1. KPIs
    pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. KPIs Generales y por Maquina", ln=True)
    m_gen = get_metrics_by_list(listado_maquinas_final)
    pdf.set_fill_color(214, 234, 248); pdf.set_font("Arial", 'B', 11); pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, f" GLOBAL {area_nombre}: OEE {m_gen['OEE']*100:.1f}% | Disp: {m_gen['DISP']*100:.0f}% | Perf: {m_gen['PERF']*100:.0f}% | Cal: {m_gen['CAL']*100:.0f}%", ln=True, fill=True)
    
    pdf.set_font("Arial", '', 10)
    for linea in listado_maquinas_final:
        ml = get_metrics_by_list([linea])
        if ml['OEE'] > 0: pdf.cell(0, 8, f"   - {linea}: OEE {ml['OEE']*100:.1f}% (Disp: {ml['DISP']*100:.0f}% / Perf: {ml['PERF']*100:.0f}% / Cal: {ml['CAL']*100:.0f}%)", ln=True)

    # 2. FALLAS
    pdf.ln(5); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Top 10 Fallas (Tiempo y Frecuencia)", ln=True)
    df_fallas_area = df_area[df_area['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    if not df_fallas_area.empty:
        top_f = df_fallas_area.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        top_f.rename(columns={'Operador': 'Levanto Parada...'}, inplace=True)
        draw_pdf_table(pdf, top_fallas=top_f[['Nivel Evento 6', 'Tiempo (Min)', 'Levanto Parada...']], col_widths=[90, 30, 70], max_rows=10)
    
    # 3. EVENTOS (GRÁFICO)
    pdf.add_page(); pdf.cell(0, 10, "3. Analisis de Eventos", ln=True)
    if not df_area.empty:
        df_ev = df_area.groupby(['Tipo', 'Evento'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
        fig = px.bar(df_ev, x='Tiempo (Min)', y='Evento', color='Tipo', orientation='h', color_discrete_map={'Producción': '#2ecc71', 'Parada': '#e74c3c'})
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.write_image(tmp.name); pdf.image(tmp.name, x=10, w=180)

    # 5. PRODUCCIÓN
    pdf.add_page(); pdf.cell(0, 10, "4. Produccion Total por Maquina y Codigo", ln=True)
    c_maq_p = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), 'Máquina')
    if es_soldadura:
        df_p_area = df_prod_f[~df_prod_f[c_maq_p].isin(lineas_incluidas)].copy()
    else:
        df_p_area = df_prod_f[df_prod_f[c_maq_p].isin(lineas_incluidas)].copy()
    
    if not df_p_area.empty:
        c_cod = next((c for c in df_p_area.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
        df_res = df_p_area.groupby([c_maq_p, c_cod])[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        df_res.rename(columns={c_cod: 'Cod. Prod.', 'Buenas': 'Linea OK'}, inplace=True)
        draw_pdf_table(pdf, df_res, [50, 45, 30, 30, 30], max_rows=30)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

# BOTONES DE EXPORTACIÓN
c1, c2 = st.columns(2)
lista_estampado = ['L1', 'L2', 'L3', 'L4']

with c1:
    if st.button("🏗️ Preparar PDF - ESTAMPADO", use_container_width=True):
        st.session_state['pdf_est'] = generar_pdf_area("ESTAMPADO", lista_estampado, es_soldadura=False)
    if 'pdf_est' in st.session_state:
        st.download_button("⬇️ Descargar Estampado", data=st.session_state['pdf_est'], file_name="Estampado.pdf", mime="application/pdf", use_container_width=True)

with c2:
    if st.button("🤖 Preparar PDF - SOLDADURA", use_container_width=True):
        # Soldadura toma todo lo que NO sea L1-L4
        st.session_state['pdf_sol'] = generar_pdf_area("SOLDADURA", lista_estampado, es_soldadura=True)
    if 'pdf_sol' in st.session_state:
        st.download_button("⬇️ Descargar Soldadura", data=st.session_state['pdf_sol'], file_name="Soldadura.pdf", mime="application/pdf", use_container_width=True)
