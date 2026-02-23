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
                df = df.dropna(subset=['Fecha_Filtro'])
            
            cols_texto = ['Fábrica', 'Planta', 'Máquina', 'Evento', 'Código', 'Operador', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6', 'Nombre']
            for c_txt in cols_texto:
                matches = [col for col in df.columns if c_txt.lower() in col.lower()]
                for match in matches:
                    df[match] = df[match].fillna('').astype(str).str.strip()
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
col_planta = next((c for c in df_raw.columns if 'planta' in c.lower() or 'fábrica' in c.lower()), 'Fábrica')
opciones_planta = sorted(df_raw[col_planta].unique())
plantas_sel = st.sidebar.multiselect("Seleccionar Planta", opciones_planta, default=opciones_planta)

opciones_maquina = sorted(df_raw[df_raw[col_planta].isin(plantas_sel)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", options=opciones_maquina, default=opciones_maquina)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f[col_planta].isin(plantas_sel) & df_f['Máquina'].isin(máquinas_globales)]
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()
else: st.stop()

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

# ==========================================
# 6. MÓDULO OPERADOR
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
with st.expander("👉 Ver Resumen y Evolución de Operarios", expanded=False):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        df_dias = df_op_f.groupby(col_op)['Fecha_Filtro'].nunique().reset_index()
        df_dias.columns = ['Operador', 'Días con Registro']
        st.dataframe(df_dias.sort_values('Días con Registro', ascending=False), use_container_width=True, hide_index=True)

# ==========================================
# 7. MÓDULO BAÑO Y REFRIGERIO
# ==========================================
with st.expander("☕ Tiempos de Baño y Refrigerio"):
    tb, tr = st.tabs(["Baño", "Refrigerio"])
    for i, label in enumerate(["Baño", "Refrigerio"]):
        with [tb, tr][i]:
            df_d = df_f[df_f['Nivel Evento 4'].astype(str).str.contains(label, case=False)]
            if not df_d.empty:
                res = df_d.groupby('Operador')['Tiempo (Min)'].agg(['sum', 'mean', 'count']).reset_index()
                st.dataframe(res.sort_values('sum', ascending=False), use_container_width=True)

# ==========================================
# 8. MÓDULO PRODUCCIÓN
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    c_maq = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
    c_b = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), 'Buenas')
    c_r = next((c for c in df_prod_f.columns if 'retrabajo' in c.lower()), 'Retrabajo')
    if c_maq:
        df_st = df_prod_f.groupby(c_maq)[[c_b, c_r]].sum().reset_index()
        st.plotly_chart(px.bar(df_st, x=c_maq, y=[c_b, c_r], barmode='stack'), use_container_width=True)

# ==========================================
# 9. ANÁLISIS DE TIEMPOS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos")
if not df_f.empty:
    df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
    st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Tipo', hole=0.4), use_container_width=True)

# ==========================================
# 10. ANÁLISIS DE FALLAS
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")
df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    top_f = df_fallas.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig_fallas = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top 15 Fallas")
    st.plotly_chart(fig_fallas, use_container_width=True)

# ==========================================
# 11. MÓDULO PDF (NUEVO)
# ==========================================
st.markdown("---")
st.header("📄 Reportes PDF")

def clean_text(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_pdf_table(pdf, df, col_widths):
    pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, col_widths):
        pdf.cell(width, 8, clean_text(col), border=1, align='C', fill=True)
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
    for _, row in df.iterrows():
        for i, (item, width) in enumerate(zip(row, col_widths)):
            val = f"{item:,.0f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(width, 8, clean_text(val), border=1)
        pdf.ln()

def generar_pdf_v3(area):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_text(f"REPORTE DE INDICADORES - {area}"), ln=True, align='C')
    pdf.set_font("Arial", 'I', 10); pdf.cell(0, 8, f"Periodo: {ini.date()} al {fin.date()}", ln=True, align='C'); pdf.ln(5)

    df_a = df_f[df_f[col_planta].str.upper().str.contains(area.upper())]
    if df_a.empty: return None

    # 1. METRICAS OEE
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. Metricas OEE", ln=True); pdf.set_font("Arial", '', 11)
    m = get_metrics(area)
    pdf.cell(0, 8, f"OEE: {m['OEE']:.1%} | Disp: {m['DISP']:.1%} | Perf: {m['PERF']:.1%} | Cal: {m['CAL']:.1%}", ln=True); pdf.ln(5)

    # 2. GRAFICO DE FALLAS
    df_fal_area = df_a[df_a['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fal_area.empty:
        pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Analisis de Fallas (Top)", ln=True)
        top_f_pdf = df_fal_area.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        
        fig = px.bar(top_f_pdf, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.write_image(tmp.name); pdf.image(tmp.name, x=10, w=180); os.remove(tmp.name)
        pdf.ln(5)
        
        # Tabla detallada por máquina/operador
        pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "Detalle de Fallas por Maquina", ln=True)
        for maq in sorted(df_a['Máquina'].unique()):
            df_m = df_fal_area[df_fal_area['Máquina'] == maq]
            if not df_m.empty:
                pdf.set_font("Arial", 'B', 10); pdf.cell(0, 8, f"Maquina: {maq}", ln=True)
                res_m = df_m.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(5)
                res_m.columns = ['Falla', 'Operador', 'Min']
                draw_pdf_table(pdf, res_m, [90, 60, 40]); pdf.ln(5)

    # 3. PRODUCCION
    pdf.add_page(); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "3. Datos de Produccion", ln=True)
    df_p_a = df_prod_f[df_prod_f['Máquina'].isin(df_a['Máquina'].unique())] if not df_prod_f.empty else pd.DataFrame()
    if not df_p_a.empty:
        c_cod_p = next((c for c in df_p_a.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
        res_prod = df_p_a.groupby([c_cod_p, 'Máquina'])[['Buenas', 'Retrabajo']].sum().reset_index()
        draw_pdf_table(pdf, res_prod, [60, 60, 35, 35])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c_p1, c_p2 = st.columns(2)
with c_p1:
    if st.button("🏗️ PDF Estampado"):
        res = generar_pdf_v3("ESTAMPADO")
        if res: st.download_button("Descargar", res, "Reporte_Estampado.pdf")
with c_p2:
    if st.button("🤖 PDF Soldadura"):
        res = generar_pdf_v3("SOLDADURA")
        if res: st.download_button("Descargar", res, "Reporte_Soldadura.pdf")

st.divider()
with st.expander("📂 Registro Completo"): st.dataframe(df_f, use_container_width=True)
