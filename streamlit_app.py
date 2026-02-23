import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import tempfile
import os

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS (LAYOUT ORIGINAL)
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
        gid_map = {"datos": "0", "oee": "1767654796", "prod": "315437448", "operarios": "354131379"}
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
                cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia']
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
                
                for c_txt in ['Máquina', 'Fábrica', 'Evento', 'Operador', 'Código', 'Nivel Evento 6', 'Nivel Evento 4', 'Nivel Evento 3']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df.dropna(subset=['Fecha_Filtro'])
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_map["oee"]), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d])

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")
opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas_sel = st.sidebar.multiselect("Seleccionar Planta", opciones_fabrica, default=opciones_fabrica)

opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas_sel)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", options=opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_f = df_f[df_f['Fábrica'].isin(fábricas_sel) & df_f['Máquina'].isin(máquinas_globales)]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]

# ==========================================
# 4. FUNCIONES KPI
# ==========================================
def get_metrics(df_source, name_filter):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_source.empty: return m
    mask = df_source.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_source[mask]
    if not datos.empty:
        for key, col_search in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                v = pd.to_numeric(datos[actual_col], errors='coerce').mean()
                m[key] = float(v/100 if v > 1.1 else v)
    return m

def show_metric_row(m):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{m['OEE']:.1%}"); c2.metric("Disp.", f"{m['DISP']:.1%}")
    c3.metric("Perf.", f"{m['PERF']:.1%}"); c4.metric("Calidad", f"{m['CAL']:.1%}")

# ==========================================
# 5. DASHBOARD (LAYOUT ORIGINAL)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics(df_oee_f, 'GENERAL'))

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics(df_oee_f, 'ESTAMPADO'))
    for l in ['L1', 'L2', 'L3', 'L4']:
        st.markdown(f"**{l}**"); show_metric_row(get_metrics(df_oee_f, l)); st.markdown("---")
with t2:
    show_metric_row(get_metrics(df_oee_f, 'SOLDADURA'))

st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
with st.expander("👉 Ver Resumen y Evolución de Operarios"):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        df_dias = df_op_f.groupby(col_op)['Fecha_Filtro'].nunique().reset_index()
        st.dataframe(df_dias.sort_values(by=df_dias.columns[1], ascending=False), use_container_width=True, hide_index=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    tb, tr = st.tabs(["Baño", "Refrigerio"])
    for i, label in enumerate(["Baño", "Refrigerio"]):
        with [tb, tr][i]:
            df_d = df_f[df_f['Nivel Evento 4'].astype(str).str.contains(label, case=False)]
            if not df_d.empty:
                res = df_d.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                st.dataframe(res, use_container_width=True)

st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    c_maq = next((c for c in df_prod_f.columns if 'maquina' in c.lower()), 'Máquina')
    df_st = df_prod_f.groupby(c_maq)[['Buenas', 'Retrabajo']].sum().reset_index()
    st.plotly_chart(px.bar(df_st, x=c_maq, y=['Buenas', 'Retrabajo'], barmode='stack'), use_container_width=True)

st.markdown("---")
st.header("Análisis de Tiempos")
df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Tipo', hole=0.4), use_container_width=True)

st.markdown("---")
st.header("Análisis de Fallas")
df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    top_f = df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    st.plotly_chart(px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h'), use_container_width=True)

st.divider()
with st.expander("📂 Registro Completo"): st.dataframe(df_f, use_container_width=True)

# ==========================================
# 11. MÓDULO PDF (CON FILTRO POR DÍA)
# ==========================================
st.markdown("---")
st.header("📄 Reportes PDF")

# Selector de día específico para el PDF
dias_disponibles = sorted(df_f['Fecha_Filtro'].dt.date.unique(), reverse=True)
dia_reporte = st.selectbox("📅 Seleccione el Día para el Reporte PDF:", dias_disponibles)

def clean_txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_table(pdf, df, widths):
    pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, widths): pdf.cell(width, 8, clean_txt(col), 1, 0, 'C', True)
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
    for _, row in df.iterrows():
        for i, (item, w) in enumerate(zip(row, widths)):
            val = f"{item:,.0f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(w, 8, clean_txt(val), 1)
        pdf.ln()

def generar_pdf_v4(area_nombre, fecha_seleccionada):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_txt(f"REPORTE {area_nombre.upper()} - FECHA: {fecha_seleccionada}"), ln=True, align='C'); pdf.ln(5)
    
    # Filtrar datos por Día y Área
    fecha_dt = pd.to_datetime(fecha_seleccionada)
    df_dia = df_f[df_f['Fecha_Filtro'] == fecha_dt]
    df_area = df_dia[df_dia['Fábrica'].str.upper().str.contains(area_nombre.upper())]
    
    if df_area.empty: return None

    # 1. KPIs del día
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. Metricas OEE del Dia", ln=True)
    df_oee_dia = df_oee_f[df_oee_f['Fecha_Filtro'] == fecha_dt]
    m = get_metrics(df_oee_dia, area_nombre)
    pdf.cell(0, 8, f"OEE: {m['OEE']:.1%} | Disp: {m['DISP']:.1%} | Perf: {m['PERF']:.1%} | Cal: {m['CAL']:.1%}", 1, 1); pdf.ln(5)

    # 2. Gráfico de Fallas del día
    df_fal_a = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fal_a.empty:
        pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Top Fallas del Dia (Grafico)", ln=True)
        top_f_pdf = df_fal_a.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        fig = px.bar(top_f_pdf, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.write_image(tmp.name); pdf.image(tmp.name, x=10, w=180); os.remove(tmp.name)
        pdf.ln(5)
        
        pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "Detalle de Fallas por Maquina", ln=True)
        for maq in sorted(df_area['Máquina'].unique()):
            df_m = df_fal_a[df_fal_a['Máquina'] == maq]
            if not df_m.empty:
                pdf.set_font("Arial", 'B', 10); pdf.cell(0, 8, f"Maquina: {maq}", ln=True)
                res_m = df_m.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(5)
                res_m.columns = ['Falla', 'Operador', 'Min']; draw_table(pdf, res_m, [90, 60, 40]); pdf.ln(5)

    # 3. Producción del día
    pdf.add_page(); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "3. Datos de Produccion del Dia", ln=True)
    df_p_dia = df_prod_f[df_prod_f['Fecha_Filtro'] == fecha_dt]
    df_p_a = df_p_dia[df_p_dia['Máquina'].isin(df_area['Máquina'].unique())] if not df_p_dia.empty else pd.DataFrame()
    if not df_p_a.empty:
        c_cod = next((c for c in df_p_a.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
        res_p = df_p_a.groupby(['Máquina', c_cod])[['Buenas', 'Retrabajo']].sum().reset_index()
        draw_table(pdf, res_p, [60, 60, 35, 35])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

col_pdf1, col_pdf2 = st.columns(2)
with col_pdf1:
    if st.button("🏗️ PDF Estampado"):
        res = generar_pdf_v4("ESTAMPADO", dia_reporte)
        if res: st.download_button(f"Descargar PDF Estampado ({dia_reporte})", res, f"Reporte_Estampado_{dia_reporte}.pdf")
with col_pdf2:
    if st.button("🤖 PDF Soldadura"):
        res = generar_pdf_v4("SOLDADURA", dia_reporte)
        if res: st.download_button(f"Descargar PDF Soldadura ({dia_reporte})", res, f"Reporte_Soldadura_{dia_reporte}.pdf")
