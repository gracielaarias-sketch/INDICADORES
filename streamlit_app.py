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
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 10px; border: 1px solid #dee2e6; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS ROBUSTA
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        gid_map = {"datos": "0", "oee": "1767654796", "prod": "315437448", "operarios": "354131379"}
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
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
                for c_txt in ['Máquina', 'Fábrica', 'Evento', 'Operador', 'Código', 'Nivel Evento 6']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_map["oee"]), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES E IDENTIFICACIÓN DE COLUMNAS
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados. Revisa la conexión con Google Sheets.")
    st.stop()

# Identificamos la columna maquina en la hoja principal (DATOS)
c_maq_datos = next((c for c in df_raw.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()

# ==========================================
# 4. FUNCIONES KPI
# ==========================================
def get_metrics_list(machines_list):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    
    # Búsqueda robusta en la hoja OEE
    c_maq_oee = next((c for c in df_oee_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), None)
    
    if c_maq_oee:
        mask = df_oee_f[c_maq_oee].str.upper().str.startswith(tuple(machines_list))
    else:
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.startswith(tuple(machines_list)).any(), axis=1)
    
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

# ==========================================
# 5. LAYOUT VISUAL (INDICADORES 1-10)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics_list(['GENERAL', 'PLANTA']))

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics_list(['ESTAMPADO']))
    st.write("---")
    for l in ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4']:
        st.write(f"**{l}**")
        show_metric_row(get_metrics_list([l]))

with t2:
    show_metric_row(get_metrics_list(['SOLDADURA', 'CELL']))

st.markdown("---")
# Módulos de Operadores, Producción y Fallas
c_left, c_right = st.columns(2)
with c_left:
    st.subheader("📈 Producción por Máquina")
    if not df_prod_f.empty:
        c_m = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')
        df_p_plot = df_prod_f.groupby(c_m)[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        st.plotly_chart(px.bar(df_p_plot, x=c_m, y=['Buenas', 'Retrabajo', 'Observadas'], barmode='group'), use_container_width=True)

with c_right:
    st.subheader("⚠️ Top 10 Fallas")
    df_fallas_plot = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    if not df_fallas_plot.empty:
        top_f = df_fallas_plot.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        st.plotly_chart(px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c']), use_container_width=True)

# ==========================================
# 11. EXPORTACIÓN A PDF (LOGICA DE FILTRADO DATOS)
# ==========================================
st.markdown("---")
st.header("📄 Exportar Reportes PDF")

try:
    from fpdf import FPDF
    import tempfile

    def clean_text(text): return str(text).encode('latin-1', 'replace').decode('latin-1')

    def generar_pdf_area(area_nombre, base_filter, is_exclusive=False):
        pdf = FPDF()
        pdf.add_page()
        
        # Estilo de Encabezado
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"REPORTE - {area_nombre.upper()}", ln=True, align='C')
        pdf.set_font("Arial", 'I', 10); pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 8, f"Periodo: {ini.strftime('%d/%m/%Y')} al {fin.strftime('%d/%m/%Y')}", ln=True, align='C')
        pdf.ln(5)

        # Filtrado de Máquinas según hoja DATOS
        if is_exclusive:
            df_area = df_f[~df_f[c_maq_datos].str.upper().str.startswith(tuple(base_filter))].copy()
            list_maquinas = sorted(df_area[c_maq_datos].unique())
        else:
            df_area = df_f[df_f[c_maq_datos].str.upper().str.startswith(tuple(base_filter))].copy()
            list_maquinas = [m for m in sorted(df_f[c_maq_datos].unique()) if m.upper().startswith(tuple(base_filter))]

        if df_area.empty: return "VACIO"

        # 1. KPIs
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. KPIs y OEE", ln=True)
        m_gen = get_metrics_list(list_maquinas)
        pdf.set_fill_color(214, 234, 248); pdf.set_font("Arial", 'B', 11); pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 8, f" GLOBAL {area_nombre}: OEE {m_gen['OEE']:.1%} | D: {m_gen['DISP']:.1%} | P: {m_gen['PERF']:.1%} | C: {m_gen['CAL']:.1%}", ln=True, fill=True)
        
        pdf.set_font("Arial", '', 10)
        for m_name in list_maquinas:
            mets = get_metrics_list([m_name.upper()])
            if mets['OEE'] > 0:
                pdf.cell(0, 7, f"   - {m_name}: OEE {mets['OEE']:.1%} (D: {mets['DISP']:.1%} / P: {mets['PERF']:.1%} / C: {mets['CAL']:.1%})", ln=True)

        # 2. Fallas
        pdf.ln(5); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Top Fallas y Responsables", ln=True)
        df_fallas = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
        if not df_fallas.empty:
            top_f = df_fallas.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
            top_f.rename(columns={'Operador': 'Levanto Parada...'}, inplace=True)
            
            # Tabla Fallas
            pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
            pdf.cell(90, 8, "Falla", 1, 0, 'C', True); pdf.cell(30, 8, "Minutos", 1, 0, 'C', True); pdf.cell(70, 8, "Operador", 1, 1, 'C', True)
            pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
            for _, r in top_f.iterrows():
                pdf.cell(90, 7, clean_text(r[0]), 1); pdf.cell(30, 7, str(r[1]), 1, 0, 'C'); pdf.cell(70, 7, clean_text(r[2]), 1, 1)

        # 3. Producción
        pdf.add_page(); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "3. Produccion Detallada", ln=True)
        c_maq_p = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), c_maq_datos)
        df_p_area = df_prod_f[df_prod_f[c_maq_p].isin(list_maquinas)]
        if not df_p_area.empty:
            c_cod = next((c for c in df_p_area.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
            res_p = df_p_area.groupby([c_maq_p, c_cod])[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
            pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255)
            pdf.cell(50, 8, "Maquina", 1, 0, 'C', True); pdf.cell(50, 8, "Codigo", 1, 0, 'C', True); pdf.cell(30, 8, "OK", 1, 0, 'C', True); pdf.cell(30, 8, "Ret.", 1, 0, 'C', True); pdf.cell(30, 8, "Obs.", 1, 1, 'C', True)
            pdf.set_text_color(0, 0, 0)
            for _, r in res_p.head(30).iterrows():
                pdf.cell(50, 7, clean_text(r[0]), 1); pdf.cell(50, 7, clean_text(r[1]), 1); pdf.cell(30, 7, str(int(r[2])), 1, 0, 'C'); pdf.cell(30, 7, str(int(r[3])), 1, 0, 'C'); pdf.cell(30, 7, str(int(r[4])), 1, 1, 'C')

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name); return open(tmp.name, "rb").read()

    c1, c2 = st.columns(2)
    l_est = ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4']
    with c1:
        if st.button("🏗️ PDF - ESTAMPADO", use_container_width=True):
            res = generar_pdf_area("ESTAMPADO", l_est, False)
            if res == "VACIO": st.error("No hay datos.")
            else: st.session_state['pdf_est'] = res
        if 'pdf_est' in st.session_state:
            st.download_button("⬇️ Descargar", data=st.session_state['pdf_est'], file_name="Estampado.pdf")
    with c2:
        if st.button("🤖 PDF - SOLDADURA", use_container_width=True):
            res = generar_pdf_area("SOLDADURA", l_est, True)
            if res == "VACIO": st.error("No hay datos.")
            else: st.session_state['pdf_sol'] = res
        if 'pdf_sol' in st.session_state:
            st.download_button("⬇️ Descargar", data=st.session_state['pdf_sol'], file_name="Soldadura.pdf")

except ImportError:
    st.error("Librerías PDF no encontradas.")
