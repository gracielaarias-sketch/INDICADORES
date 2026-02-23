import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import tempfile
import os

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS (ORIGINAL)
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
# 2. CARGA DE DATOS ROBUSTA (CORREGIDA)
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
                # Limpieza Textos
                for c_txt in ['Fábrica', 'Máquina', 'Evento', 'Operador', 'Nivel Evento 3', 'Nivel Evento 6']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str)
                return df.dropna(subset=['Fecha_Filtro'])
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_map["oee"]), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES (ORIGINAL)
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d])

# Manejo de filtros multiselect
opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)
opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", options=opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)]

# ==========================================
# 4. FUNCIONES KPI
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
    c1.metric("OEE", f"{m['OEE']:.1%}"); c2.metric("Disp.", f"{m['DISP']:.1%}")
    c3.metric("Perf.", f"{m['PERF']:.1%}"); c4.metric("Calidad", f"{m['CAL']:.1%}")

# ==========================================
# 5. DASHBOARD Y PESTAÑAS (LAYOUT ORIGINAL)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics('GENERAL'))

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics('ESTAMPADO'))
    for l in ['L1', 'L2', 'L3', 'L4']:
        st.markdown(f"**{l}**"); show_metric_row(get_metrics(l)); st.markdown("---")
with t2:
    show_metric_row(get_metrics('SOLDADURA'))

# 6. MÓDULO INDICADORES POR OPERADOR
st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
if not df_op_f.empty:
    col_op = next((c for c in df_op_f.columns if 'operador' in c.lower() or 'nombre' in c.lower()), 'Operador')
    df_dias = df_op_f.groupby(col_op)['Fecha_Filtro'].nunique().reset_index()
    st.dataframe(df_dias.sort_values(by=df_dias.columns[1], ascending=False), use_container_width=True, hide_index=True)

# 7. MÓDULO BAÑO Y REFRIGERIO
with st.expander("☕ Tiempos de Baño y Refrigerio"):
    for label in ["Baño", "Refrigerio"]:
        st.subheader(label)
        df_d = df_f[df_f['Nivel Evento 4'].astype(str).str.contains(label, case=False)]
        if not df_d.empty:
            res = df_d.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
            st.dataframe(res, use_container_width=True)

# 8. MÓDULO PRODUCCIÓN
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    c_maq = next((c for c in df_prod_f.columns if 'maquina' in c.lower()), 'Máquina')
    df_st = df_prod_f.groupby(c_maq)[['Buenas', 'Retrabajo']].sum().reset_index()
    st.plotly_chart(px.bar(df_st, x=c_maq, y=['Buenas', 'Retrabajo'], barmode='stack'), use_container_width=True)

# 9. ANÁLISIS DE TIEMPOS
st.markdown("---")
st.header("Análisis de Tiempos")
df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Tipo', hole=0.4), use_container_width=True)

# 10. ANÁLISIS DE FALLAS
st.markdown("---")
st.header("Análisis de Fallas")
df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    top_f = df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    st.plotly_chart(px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h'), use_container_width=True)

# ==========================================
# 11. MÓDULO PDF (REESTRUCTURADO)
# ==========================================
st.markdown("---")
st.header("📄 Exportar Reportes PDF")

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

def generar_pdf(area_nombre):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_txt(f"REPORTE {area_nombre}"), 0, 1, 'C'); pdf.ln(5)
    
    df_a = df_f[df_f['Fábrica'].astype(str).str.upper().str.contains(area_nombre.upper())]
    if df_a.empty: return None

    # KPIs
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. Resumen OEE", 0, 1)
    m = get_metrics(area_nombre)
    pdf.cell(0, 8, f"OEE: {m['OEE']:.1%} | Disp: {m['DISP']:.1%} | Perf: {m['PERF']:.1%} | Cal: {m['CAL']:.1%}", 1, 1); pdf.ln(5)

    # Top 10 Global (Sin Operador)
    pdf.cell(0, 10, "2. Top 10 Fallas Area", 0, 1)
    df_fal_a = df_a[df_a['Nivel Evento 3'].str.contains('FALLA', case=False)]
    top_10 = df_fal_a.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
    draw_table(pdf, top_10, [140, 50])

    # Tablas por Máquina (Con Operador)
    pdf.add_page(); pdf.cell(0, 10, "3. Detalle por Maquina", 0, 1)
    for m in sorted(df_a['Máquina'].unique()):
        df_m = df_fal_a[df_fal_a['Máquina'] == m]
        if not df_m.empty:
            pdf.set_font("Arial", 'B', 10); pdf.cell(0, 8, f"Maquina: {m}", 0, 1)
            res_m = df_m.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(5)
            draw_table(pdf, res_m, [90, 60, 40]); pdf.ln(5)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c_p1, c_p2 = st.columns(2)
with c_p1:
    if st.button("🏗️ PDF Estampado"):
        res = generar_pdf("ESTAMPADO")
        if res: st.download_button("Descargar Estampado", res, "Estampado.pdf")
with c_p2:
    if st.button("🤖 PDF Soldadura"):
        res = generar_pdf("SOLDADURA")
        if res: st.download_button("Descargar Soldadura", res, "Soldadura.pdf")

st.divider()
with st.expander("📂 Registro Completo"): st.dataframe(df_f, use_container_width=True)
