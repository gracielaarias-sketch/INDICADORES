import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import tempfile
import os

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
        url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
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
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

# Bases filtradas
df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]

# ==========================================
# 4. FUNCIONES KPI Y VISUALES
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
                v = pd.to_numeric(datos[actual_col], errors='coerce').mean()
                m[key] = float(v/100 if v > 1.1 else v)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}")
    c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
    c3.metric("Performance", f"{m['PERF']:.1%}")
    c4.metric("Calidad", f"{m['CAL']:.1%}")

def show_historical_oee(filter_name, title):
    mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filter_name.upper()).any(), axis=1)
    df_proc = df_oee_f[mask].copy()
    if not df_proc.empty:
        trend = df_proc.groupby('Fecha_Filtro').OEE.mean().reset_index()
        st.plotly_chart(px.line(trend, x='Fecha_Filtro', y='OEE', markers=True, title=f'Evolución OEE: {title}'), use_container_width=True)

# ==========================================
# 5. DASHBOARD PRINCIPAL
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics('GENERAL'))
with st.expander("📉 Histórico OEE General"): show_historical_oee('GENERAL', 'Planta')

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
    for l in ['L1', 'L2', 'L3', 'L4']:
        st.markdown(f"**{l}**"); show_metric_row(get_metrics(l)); st.markdown("---")
with t2:
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')

# ==========================================
# 10. ANÁLISIS DE FALLAS (DASHBOARD)
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")
df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    top_f = df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    st.plotly_chart(px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top 15 Fallas Globales"), use_container_width=True)

# ==========================================
# 11. EXPORTACIÓN PDF (REESTRUCTURADO)
# ==========================================
st.markdown("---")
st.header("📄 Reportes PDF Profesionales")

def clean_txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_table(pdf, df, widths):
    pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, widths): pdf.cell(width, 8, clean_txt(col), 1, 0, 'C', True)
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
    for _, row in df.iterrows():
        for i, (item, w) in enumerate(zip(row, widths)):
            val = f"{item:,.1f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(w, 8, clean_txt(val), 1)
        pdf.ln()

def generar_pdf_area(area_nombre):
    pdf = FPDF(); pdf.add_page()
    # Título
    pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_txt(f"REPORTE {area_nombre.upper()}"), ln=True, align='C')
    pdf.set_font("Arial", 'I', 10); pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Periodo: {ini.date()} a {fin.date()}", ln=True, align='C'); pdf.ln(5)

    # Filtrar datos de la planta específica
    df_a = df_f[df_f['Fábrica'].astype(str).str.upper().str.contains(area_nombre.upper())]
    if df_a.empty: return None

    # 1. KPIs
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. KPIs del Area", ln=True)
    m = get_metrics(area_nombre); pdf.set_fill_color(214, 234, 248)
    pdf.cell(0, 8, f" OEE: {m['OEE']:.1%} | D: {m['DISP']:.1%} | P: {m['PERF']:.1%} | C: {m['CAL']:.1%}", 1, 1, fill=True); pdf.ln(5)

    # 2. TOP 10 FALLAS (RESUMEN)
    pdf.cell(0, 10, "2. Top 10 Fallas del Area (Resumen)", ln=True)
    df_fal_a = df_a[df_a['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    if not df_fal_a.empty:
        top_10 = df_fal_area = df_fal_a.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        draw_table(pdf, top_10, [140, 50])

    # 3. FALLAS POR MÁQUINA CON OPERADOR
    pdf.add_page(); pdf.cell(0, 10, "3. Desglose de Fallas por Maquina", ln=True); pdf.ln(2)
    for maq in sorted(df_a['Máquina'].unique()):
        df_maq = df_fal_a[df_fal_a['Máquina'] == maq]
        if not df_maq.empty:
            pdf.set_font("Arial", 'B', 10); pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, clean_txt(f"Maquina: {maq}"), ln=True)
            res_m = df_maq.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(5)
            res_m.columns = ['Falla', 'Operador', 'Minutos']
            draw_table(pdf, res_m, [90, 60, 40]); pdf.ln(5)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c_pdf1, c_pdf2 = st.columns(2)
with c_pdf1:
    if st.button("🏗️ PDF Estampado"):
        res = generar_pdf_area("ESTAMPADO")
        if res: st.download_button("Descargar", res, "Reporte_Estampado.pdf")
with c_pdf2:
    if st.button("🤖 PDF Soldadura"):
        res = generar_pdf_area("SOLDADURA")
        if res: st.download_button("Descargar", res, "Reporte_Soldadura.pdf")

# Registro Completo al final como en el original
with st.expander("📂 Registro Completo"): st.dataframe(df_f, use_container_width=True)
