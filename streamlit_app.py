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
    [data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    hr { margin-top: 2rem; margin-bottom: 2rem; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; }
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
                # Limpieza Numérica Avanzada (Maneja 4.054,01 o 4,054.01)
                cols_num = ['Tiempo', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad']
                for c in cols_num:
                    target = [col for col in df.columns if c.lower() in col.lower()]
                    for col in target:
                        df[col] = df[col].astype(str).str.replace('.', '').str.replace(',', '.')
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                
                # Normalización de Fechas
                c_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
                if c_fecha:
                    df['Fecha_DT'] = pd.to_datetime(df[c_fecha], dayfirst=True, errors='coerce')
                    df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                
                # Limpieza Textos
                for c_txt in ['Máquina', 'Planta', 'Fábrica', 'Evento', 'Operador', 'Nivel Evento 6']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df.dropna(subset=['Fecha_Filtro'])
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_map["oee"]), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_op_raw = load_data()

# ==========================================
# 3. FILTROS GLOBALES (SIDEBAR)
# ==========================================
if df_raw.empty:
    st.warning("⚠️ No se pudieron cargar los datos. Revisa la conexión.")
    st.stop()

st.sidebar.header("📅 Rango Dashboard")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d])

col_planta = next((c for c in df_raw.columns if 'planta' in c.lower() or 'fábrica' in c.lower()), 'Fábrica')
plantas_sel = st.sidebar.multiselect("Seleccionar Planta", sorted(df_raw[col_planta].unique()), default=sorted(df_raw[col_planta].unique()))

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

# Bases filtradas para el Dashboard (acumulado)
df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin) & (df_raw[col_planta].isin(plantas_sel))]
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]

# ==========================================
# 4. LÓGICA KPI (BÚSQUEDA FLEXIBLE)
# ==========================================
def get_kpis(df_source, filter_str):
    mask = df_source.apply(lambda row: row.astype(str).str.upper().str.contains(filter_str.upper()).any(), axis=1)
    d = df_source[mask].copy()
    if d.empty: return {'OEE':0.0, 'D':0.0, 'P':0.0, 'C':0.0}

    def safe_mean(df, text):
        col = next((c for c in df.columns if text.lower() in c.lower()), None)
        if col:
            v = pd.to_numeric(df[col], errors='coerce').mean()
            return v / 100 if v > 1.1 else v
        return 0.0

    return {'OEE': safe_mean(d, 'OEE'), 'D': safe_mean(d, 'Disponibilidad'), 
            'P': safe_mean(d, 'Performance'), 'C': safe_mean(d, 'Calidad')}

def show_metrics(k):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OEE", f"{k['OEE']:.1%}"); c2.metric("Disp.", f"{k['D']:.1%}")
    c3.metric("Perf.", f"{k['P']:.1%}"); c4.metric("Calidad", f"{k['C']:.1%}")

# ==========================================
# 5. DASHBOARD UI (LAYOUT ORIGINAL)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metrics(get_kpis(df_oee_f, 'GENERAL'))

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metrics(get_kpis(df_oee_f, 'ESTAMPADO'))
    with st.expander("Ver Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            st.write(f"**{l}**"); show_metrics(get_kpis(df_oee_f, l))
with t2:
    show_metrics(get_kpis(df_oee_f, 'SOLDADURA'))
    with st.expander("Ver Detalle"):
        st.write("**Robotizada**"); show_metrics(get_kpis(df_oee_f, 'CELDA'))

st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
with st.expander("👉 Ver Resumen Operarios"):
    if not df_op_raw.empty:
        df_op_f = df_op_raw[(df_op_raw['Fecha_Filtro'] >= ini) & (df_op_raw['Fecha_Filtro'] <= fin)]
        st.dataframe(df_op_f.groupby('Operador')['Fecha_Filtro'].nunique().reset_index(), use_container_width=True)

with st.expander("☕ Tiempos de Baño y Refrigerio"):
    for label in ["Baño", "Refrigerio"]:
        df_br = df_f[df_f['Nivel Evento 4'].str.contains(label, case=False)]
        if not df_br.empty:
            st.write(f"**{label}**")
            st.table(df_br.groupby('Operador')['Tiempo (Min)'].sum().reset_index())

st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    c_m = next(c for c in df_prod_f.columns if 'maquina' in c.lower())
    st.plotly_chart(px.bar(df_prod_f.groupby(c_m)[['Buenas', 'Retrabajo']].sum().reset_index(), x=c_m, y=['Buenas', 'Retrabajo'], barmode='stack'), use_container_width=True)

st.markdown("---")
st.header("Análisis de Tiempos")
df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Produccion' if 'Producción' in str(x) or 'Produccion' in str(x) else 'Parada')
st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Tipo', color='Tipo', color_discrete_map={'Produccion':'#2ecc71','Parada':'#e74c3c'}), use_container_width=True)

# ==========================================
# 6. MÓDULO PDF (REPORTE DIARIO ESTRICTO)
# ==========================================
st.markdown("---")
st.header("📄 Generar Reporte PDF")
dia_pdf = st.selectbox("📅 Seleccione Fecha para el PDF:", sorted(df_raw['Fecha_Filtro'].dt.date.unique(), reverse=True))

def clean(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_table(pdf, df, widths):
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Arial", 'B', 9)
    for col, w in zip(df.columns, widths): pdf.cell(w, 7, clean(col), 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)
    for _, row in df.iterrows():
        for i, (item, w) in enumerate(zip(row, widths)):
            val = f"{item:,.2f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(w, 6, clean(val), 1)
        pdf.ln()

def generar_pdf_final(area, fecha_sel):
    f_dt = pd.to_datetime(fecha_sel)
    # FILTRO ESTRICTO: Solo el día seleccionado
    df_d = df_raw[df_raw['Fecha_Filtro'] == f_dt]
    df_a = df_d[df_d[col_planta].str.upper().str.contains(area.upper())]
    if df_a.empty: return None

    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, clean(f"REPORTE DE INDICADORES - {area}"), ln=True)
    pdf.set_font("Arial", '', 11); pdf.cell(0, 8, f"Fecha: {fecha_sel.strftime('%d/%m/%Y')}", ln=True); pdf.ln(5)

    # 1. KPIs
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "1. KPIs Generales y por Maquina", ln=True)
    k = get_kpis(df_oee_raw[df_oee_raw['Fecha_Filtro'] == f_dt], area)
    pdf.set_font("Arial", '', 10); pdf.cell(0, 7, clean(f" GLOBAL {area}: OEE {k['OEE']:.1%} | Disp: {k['D']:.1%} | Perf: {k['P']:.1%} | Cal: {k['C']:.1%}"), ln=True)
    for m in sorted(df_a['Máquina'].unique()):
        km = get_kpis(df_oee_raw[df_oee_raw['Fecha_Filtro'] == f_dt], m)
        pdf.cell(10); pdf.cell(0, 6, clean(f"- {m}: OEE {km['OEE']:.1%} (D: {km['D']:.1%} / P: {km['P']:.1%} / C: {km['C']:.1%})"), ln=True)

    # 2. FALLAS (GRÁFICO ROJO)
    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "2. Top 10 Fallas del Dia", ln=True)
    df_fal = df_a[df_a['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fal.empty:
        top_f = df_fal.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        draw_table(pdf, top_f, [140, 50])
        fig = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c'])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.write_image(tmp.name); pdf.ln(2); pdf.image(tmp.name, x=10, w=160); os.remove(tmp.name)

    # 3. BALANCE PIE
    pdf.add_page(); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "3. Produccion vs Paradas", ln=True)
    df_a['T'] = df_a['Evento'].apply(lambda x: 'Produccion' if 'Producción' in str(x) or 'Produccion' in str(x) else 'Parada')
    fig_p = px.pie(df_a, values='Tiempo (Min)', names='T', color='T', color_discrete_map={'Produccion':'#2ecc71','Parada':'#e74c3c'})
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        fig_p.write_image(tmp.name); pdf.image(tmp.name, x=40, w=120); os.remove(tmp.name)

    # 4. OPERADORES
    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "4. Tiempos Totales por Operador (Min)", ln=True)
    draw_table(pdf, df_a.groupby('Operador')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False), [140, 50])

    # 5. DETALLE FALLAS (QUIEN LEVANTO)
    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "5. Registro de Fallas con Operador", ln=True)
    if not df_fal.empty:
        res_fal = df_fal.groupby(['Máquina', 'Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values(['Máquina', 'Tiempo (Min)'], ascending=[True, False]).head(20)
        res_fal.columns = ['Maq', 'Falla', 'Levanto', 'Min']
        draw_table(pdf, res_fal, [40, 70, 50, 30])

    # 6. PRODUCCIÓN
    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "6. Produccion Total del Dia", ln=True)
    df_pd = df_prod_raw[df_prod_raw['Fecha_Filtro'] == f_dt]
    df_pa = df_pd[df_pd['Máquina'].isin(df_a['Máquina'].unique())]
    if not df_pa.empty:
        draw_table(pdf, df_pa.groupby('Máquina')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index(), [70, 40, 40, 40])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c1, c2 = st.columns(2)
with c1:
    if st.button("🏗️ PDF Estampado"):
        res = generar_pdf_final("ESTAMPADO", dia_pdf)
        if res: st.download_button(f"Reporte_Estampado_{dia_pdf}.pdf", res, f"Reporte_Estampado_{dia_pdf}.pdf")
with c2:
    if st.button("🤖 PDF Soldadura"):
        res = generar_pdf_final("SOLDADURA", dia_pdf)
        if res: st.download_button(f"Reporte_Soldadura_{dia_pdf}.pdf", res, f"Reporte_Soldadura_{dia_pdf}.pdf")
