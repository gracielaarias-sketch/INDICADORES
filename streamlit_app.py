Aquí tienes el código completo, definitivo y blindado.

He corregido el error del campo 'Tipo', he asegurado que la columna de máquinas se rija por la hoja DATOS, y he mantenido estrictamente el layout original con las métricas en la parte superior, las pestañas de Estampado/Soldadura y los gráficos de barras inferiores.

Python
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
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS (GOOGLE SHEETS)
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
                for c_txt in ['Máquina', 'Fábrica', 'Evento', 'Operador', 'Código', 'Nivel Evento 6', 'Nivel Evento 3']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_oee), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS Y CREACIÓN DE 'TIPO' (FIX ERROR)
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

# Detectamos columna maquina en DATOS
c_maq_datos = next((c for c in df_raw.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d])

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

# Filtrado y creación de columna Tipo para el PDF y Gráficos
df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)].copy()
if not df_f.empty and 'Evento' in df_f.columns:
    df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')

df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()

# ==========================================
# 4. FUNCIONES KPI
# ==========================================
def get_metrics_list(machines_list):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
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
# 5. DASHBOARD VISUAL (LAYOUT ORIGINAL)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics_list(['GENERAL']))

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics_list(['ESTAMPADO']))
    st.write("---")
    for l in ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4']:
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
col_graf1, col_graf2 = st.columns(2)
with col_graf1:
    st.subheader("📊 Producción por Máquina")
    if not df_prod_f.empty:
        c_m = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')
        df_p_plot = df_prod_f.groupby(c_m)[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        st.plotly_chart(px.bar(df_p_plot, x=c_m, y=['Buenas', 'Retrabajo', 'Observadas'], barmode='group'), use_container_width=True)

with col_graf2:
    st.subheader("⚠️ Top 15 Fallas")
    df_f_filt = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_f_filt.empty:
        top_f_plot = df_f_filt.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
        st.plotly_chart(px.bar(top_f_plot, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c']), use_container_width=True)

# ==========================================
# 11. EXPORTACIÓN A PDF POR ÁREA
# ==========================================
st.markdown("---")
st.header("📄 Exportar Reportes PDF")

try:
    from fpdf import FPDF
    import tempfile
    import os

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
        
        # TÍTULO
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"REPORTE DE INDICADORES - {area_nombre.upper()}", ln=True, align='C')
        pdf.set_font("Arial", 'I', 10); pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 8, f"Periodo: {ini.strftime('%d/%m/%Y')} al {fin.strftime('%d/%m/%Y')}", ln=True, align='C')
        pdf.ln(5)

        # FILTRADO (BASADO EN HOJA DATOS)
        if is_soldadura:
            df_area = df_f[~df_f[c_maq_datos].str.upper().str.startswith(tuple(base_filter))].copy()
        else:
            df_area = df_f[df_f[c_maq_datos].str.upper().str.startswith(tuple(base_filter))].copy()

        if df_area.empty: return "VACIO"
        list_maquinas = sorted(df_area[c_maq_datos].unique())

        # 1. KPIs
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. KPIs y OEE por Maquina", ln=True)
        m_gen = get_metrics_list(base_filter if not is_soldadura else list_maquinas)
        pdf.set_fill_color(214, 234, 248); pdf.set_font("Arial", 'B', 11); pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 8, f" GLOBAL: OEE {m_gen['OEE']:.1%} | D: {m_gen['DISP']:.1%} | P: {m_gen['PERF']:.1%} | C: {m_gen['CAL']:.1%}", ln=True, fill=True)
        pdf.ln(5)

        # 2. TOP FALLAS
        pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Top 10 Fallas", ln=True)
        df_fallas_pdf = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
        if not df_fallas_pdf.empty:
            top_f = df_fallas_pdf.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
            top_f.rename(columns={'Operador': 'Levanto Parada...'}, inplace=True)
            draw_pdf_table(pdf, top_f, [90, 30, 70])
            
            # Gráfico de Fallas
            fig_f = px.bar(df_fallas_pdf.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10), 
                           x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c'])
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                fig_f.write_image(tmp.name); pdf.ln(3); pdf.image(tmp.name, x=10, w=180)

        # 3. ANÁLISIS EVENTOS
        pdf.add_page(); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "3. Analisis de Eventos", ln=True)
        if not df_area.empty and 'Tipo' in df_area.columns:
            df_ev = df_area.groupby(['Tipo', 'Evento'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
            fig_ev = px.bar(df_ev, x='Tiempo (Min)', y='Evento', color='Tipo', orientation='h', color_discrete_map={'Producción': '#2ecc71', 'Parada': '#e74c3c'})
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                fig_ev.write_image(tmp.name); pdf.image(tmp.name, x=10, w=180)

        # 4. PRODUCCIÓN DETALLADA
        pdf.add_page(); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "4. Produccion por Codigo", ln=True)
        c_maq_p = next((c for c in df_prod_f.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), c_maq_datos)
        df_p_area = df_prod_f[df_prod_f[c_maq_p].isin(list_maquinas)]
        if not df_p_area.empty:
            c_cod = next((c for c in df_p_area.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
            res_p = df_p_area.groupby([c_maq_p, c_cod])[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
            res_p.rename(columns={c_cod: 'Cod. Prod.', 'Buenas': 'Linea OK'}, inplace=True)
            draw_pdf_table(pdf, res_p, [50, 45, 30, 30, 30], max_rows=35)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name); return open(tmp.name, "rb").read()

    col1, col2 = st.columns(2)
    filtros_estampado = ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4', 'L1', 'L2', 'L3', 'L4']
    with col1:
        if st.button("🏗️ PDF ESTAMPADO", use_container_width=True):
            res = generar_pdf_area("ESTAMPADO", filtros_estampado, False)
            if res == "VACIO": st.error("Sin datos.")
            else: st.session_state['pdf_est'] = res
        if 'pdf_est' in st.session_state:
            st.download_button("⬇️ Descargar Estampado", data=st.session_state['pdf_est'], file_name="Reporte_Estampado.pdf")
    with col2:
        if st.button("🤖 PDF SOLDADURA", use_container_width=True):
            res = generar_pdf_area("SOLDADURA", filtros_estampado, True)
            if res == "VACIO": st.error("Sin datos.")
            else: st.session_state['pdf_sol'] = res
        if 'pdf_sol' in st.session_state:
            st.download_button("⬇️ Descargar Soldadura", data=st.session_state['pdf_sol'], file_name="Reporte_Soldadura.pdf")

except Exception as e:
    st.error(f"Error en módulo PDF: {e}")
