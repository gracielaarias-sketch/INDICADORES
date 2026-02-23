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
# 2. CARGA DE DATOS ROBUSTA (GOOGLE SHEETS)
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        # IDs de las pestañas según lo verificado
        gid_map = {"datos": "0", "oee": "1767654796", "prod": "315437448", "operarios": "354131379"}
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
                # Limpieza Numérica Universal
                cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia']
                for c in cols_num:
                    matches = [col for col in df.columns if c.lower() in col.lower()]
                    for match in matches:
                        df[match] = df[match].astype(str).str.replace(',', '.')
                        df[match] = df[match].str.replace('%', '')
                        df[match] = pd.to_numeric(df[match], errors='coerce').fillna(0.0)
                
                # Limpieza de Fechas
                col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
                if col_fecha:
                    df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                    df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                    df = df.dropna(subset=['Fecha_Filtro'])
                
                # Limpieza de Textos (Nombres de máquinas, operadores, etc.)
                for c_txt in ['Máquina', 'Fábrica', 'Evento', 'Operador', 'Código', 'Nivel Evento 6', 'Nivel Evento 3']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_map["oee"]), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except Exception as e:
        st.error(f"Error crítico de conexión: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES E IDENTIFICACIÓN DE COLUMNAS
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados. Verifica los permisos de tu Google Sheet.")
    st.stop()

# Detectamos la columna máquina en la hoja DATOS (Maestra)
c_maq_datos = next((c for c in df_raw.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d])

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

# DataFrames filtrados por fecha
df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()

# ==========================================
# 4. FUNCIONES KPI (SOPORTE LAYOUT 1-10)
# ==========================================
def get_metrics_list(machines_list):
    """Obtiene métricas de OEE buscando en cualquier columna de la pestaña OEE."""
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    
    # Normalizamos la búsqueda para que coincida con la estructura de categorías compartida
    search_terms = [str(x).upper() for x in machines_list]
    mask = df_oee_f.apply(lambda row: any(term in str(val).upper() for term in search_terms for val in row), axis=1)
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
# 5. DASHBOARD VISUAL (SECCIONES 1-10)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics_list(['GENERAL']))

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics_list(['ESTAMPADO']))
    st.write("---")
    for l in ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4']:
        # Buscamos tanto el nombre completo como la abreviatura (L1, L2, etc)
        abr = l.replace('INEA ', '')
        st.write(f"**{l}**")
        show_metric_row(get_metrics_list([l, abr]))

with t2:
    show_metric_row(get_metrics_list(['SOLDADURA']))
    st.write("---")
    for s in ['CELDA', 'PRP']:
        st.write(f"**{s}**")
        show_metric_row(get_metrics_list([s]))

st.markdown("---")
# Módulos de Producción, Tiempos y Fallas (Resumen Visual)
col_prod, col_fallas = st.columns(2)
with col_prod:
    st.subheader("📊 Producción por Máquina")
    if not df_prod_f.empty:
        c_m = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')
        df_p_plot = df_prod_f.groupby(c_m)[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        st.plotly_chart(px.bar(df_p_plot, x=c_m, y=['Buenas', 'Retrabajo', 'Observadas'], barmode='group'), use_container_width=True)

with col_fallas:
    st.subheader("⚠️ Top 10 Fallas")
    df_f_filt = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_f_filt.empty:
        top_f_plot = df_f_filt.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        st.plotly_chart(px.bar(top_f_plot, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c']), use_container_width=True)

# ==========================================
# 11. EXPORTACIÓN A PDF POR ÁREA
# ==========================================
st.markdown("---")
st.header("📄 Exportar Reportes PDF")

try:
    from fpdf import FPDF
    import tempfile

    def clean_text(text): return str(text).encode('latin-1', 'replace').decode('latin-1')

    def draw_pdf_table(pdf, df, col_widths, max_rows=15):
        if df.empty: return
        pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
        for col, width in zip(df.columns, col_widths):
            pdf.cell(width, 8, clean_text(col)[:25], border=1, align='C', fill=True)
        pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
        for i, (_, row) in enumerate(df.head(max_rows).iterrows()):
            pdf.set_fill_color(236, 240, 241) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
            for item, width in zip(row, col_widths):
                val = clean_text(item)
                if isinstance(item, (float, int)): val = f"{item:,.1f}"
                pdf.cell(width, 8, val[:25], border=1, align='C', fill=True)
            pdf.ln()

    def generar_pdf_area(area_nombre, base_filter, is_soldadura=False):
        pdf = FPDF()
        pdf.add_page()
        
        # 1. TÍTULO Y FECHA
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"REPORTE DE INDICADORES - {area_nombre.upper()}", ln=True, align='C')
        pdf.set_font("Arial", 'I', 10); pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 8, f"Periodo: {ini.strftime('%d/%m/%Y')} al {fin.strftime('%d/%m/%Y')}", ln=True, align='C')
        pdf.ln(5)

        # 2. FILTRADO DE MÁQUINAS (GUÍA: HOJA DATOS)
        if is_soldadura:
            df_area = df_f[~df_f[c_maq_datos].str.upper().str.startswith(tuple(base_filter))].copy()
        else:
            df_area = df_f[df_f[c_maq_datos].str.upper().str.startswith(tuple(base_filter))].copy()

        if df_area.empty: return "VACIO"
        list_maquinas = sorted(df_area[c_maq_datos].unique())

        # 3. KPIs Y OEE
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. KPIs y OEE por Maquina", ln=True)
        m_gen = get_metrics_list(base_filter if not is_soldadura else list_maquinas)
        pdf.set_fill_color(214, 234, 248); pdf.set_font("Arial", 'B', 11); pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 8, f" GLOBAL: OEE {m_gen['OEE']:.1%} | D: {m_gen['DISP']:.1%} | P: {m_gen['PERF']:.1%} | C: {m_gen['CAL']:.1%}", ln=True, fill=True)
        
        pdf.set_font("Arial", '', 10)
        for m_name in list_maquinas:
            abr = m_name.replace('INEA ', '').upper()
            mets = get_metrics_list([m_name.upper(), abr])
            if mets['OEE'] > 0:
                pdf.cell(0, 7, f"   - {m_name}: OEE {mets['OEE']:.1%} (D: {mets['DISP']:.1%} / P: {mets['PERF']:.1%} / C: {mets['CAL']:.1%})", ln=True)

        # 4. TOP FALLAS Y OPERADORES
        pdf.ln(5); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Top 10 Fallas", ln=True)
        df_fallas_pdf = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
        if not df_fallas_pdf.empty:
            top_f = df_fallas_pdf.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
            top_f.rename(columns={'Operador': 'Levanto Parada...'}, inplace=True)
            draw_pdf_table(pdf, top_f, [90, 30, 70])
            
            # Detalle por máquina
            pdf.add_page(); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 10, "Detalle de Fallas por Maquina:", ln=True)
            for m in list_maquinas:
                df_m = df_fallas_pdf[df_fallas_pdf[c_maq_datos] == m]
                if not df_m.empty:
                    pdf.set_font("Arial", 'B', 9); pdf.cell(0, 7, f"Maquina: {m}", ln=True)
                    top_m = df_m.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(5)
                    top_m.rename(columns={'Operador': 'Levanto Parada...'}, inplace=True)
                    draw_pdf_table(pdf, top_m, [90, 30, 70], max_rows=5); pdf.ln(2)

        # 5. GRÁFICO DE EVENTOS
        pdf.add_page(); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "3. Analisis de Eventos (Produccion vs Paradas)", ln=True)
        if not df_area.empty:
            df_ev = df_area.groupby(['Tipo', 'Evento'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
            fig_ev = px.bar(df_ev, x='Tiempo (Min)', y='Evento', color='Tipo', orientation='h', color_discrete_map={'Producción': '#2ecc71', 'Parada': '#e74c3c'})
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                fig_ev.write_image(tmp.name); pdf.image(tmp.name, x=10, w=180)

        # 6. PRODUCCIÓN POR MÁQUINA Y CÓDIGO
        pdf.add_page(); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "4. Produccion Detallada", ln=True)
        c_maq_p = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), c_maq_datos)
        df_p_area = df_prod_f[df_prod_f[c_maq_p].isin(list_maquinas)]
        if not df_p_area.empty:
            c_cod = next((c for c in df_p_area.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
            res_p = df_p_area.groupby([c_maq_p, c_cod])[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
            res_p.rename(columns={c_cod: 'Cod. Prod.', 'Buenas': 'Linea OK'}, inplace=True)
            draw_pdf_table(pdf, res_p, [50, 45, 30, 30, 30], max_rows=40)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name); return open(tmp.name, "rb").read()

    # Interfaz de Botones
    c1, c2 = st.columns(2)
    filtros_estampado = ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4', 'L1', 'L2', 'L3', 'L4']
    
    with c1:
        if st.button("🏗️ PREPARAR REPORTE ESTAMPADO", use_container_width=True):
            res = generar_pdf_area("ESTAMPADO", filtros_estampado, False)
            if res == "VACIO": st.error("Sin datos para este periodo.")
            else: st.session_state['pdf_est'] = res
        if 'pdf_est' in st.session_state:
            st.download_button("⬇️ DESCARGAR PDF ESTAMPADO", data=st.session_state['pdf_est'], file_name="Reporte_Estampado.pdf")
            
    with c2:
        if st.button("🤖 PREPARAR REPORTE SOLDADURA", use_container_width=True):
            res = generar_pdf_area("SOLDADURA", filtros_estampado, True)
            if res == "VACIO": st.error("Sin datos para este periodo.")
            else: st.session_state['pdf_sol'] = res
        if 'pdf_sol' in st.session_state:
            st.download_button("⬇️ DESCARGAR PDF SOLDADURA", data=st.session_state['pdf_sol'], file_name="Reporte_Soldadura.pdf")

except Exception as e:
    st.error(f"Error en módulo PDF: {e}")
