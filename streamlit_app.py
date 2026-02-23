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

# CSS para mantener el estilo de las tarjetas de métricas
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: bold; color: #1f77b4; }
    [data-testid="stMetricLabel"] { font-size: 16px; }
    .stMetric { 
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid #e1e4e8;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f8f9fa;
        border-radius: 5px 5px 0 0;
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS (FIX GID DEFINITION)
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    try:
        url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
        gid_map = {
            "datos": "0", 
            "oee": "1767654796", 
            "prod": "315437448", 
            "operarios": "354131379"
        }
        base_export = url_base.split("/edit")[0] + "/export?format=csv&gid="
        
        def process_df(url):
            try:
                df = pd.read_csv(url)
                # Limpieza numérica robusta
                cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia']
                for c in cols_num:
                    matches = [col for col in df.columns if c.lower() in col.lower()]
                    for m in matches:
                        df[m] = df[m].astype(str).str.replace(',', '.').str.replace('%', '')
                        df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0.0)
                
                # Normalización de fechas
                c_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
                if c_fecha:
                    df['Fecha_DT'] = pd.to_datetime(df[c_fecha], dayfirst=True, errors='coerce')
                    df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                    df = df.dropna(subset=['Fecha_Filtro'])
                
                # Normalización de textos
                for c_txt in ['Máquina', 'Planta', 'Evento', 'Operador', 'Código', 'Nivel Evento 6']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df
            except: return pd.DataFrame()

        return (
            process_df(base_export + gid_map["datos"]), 
            process_df(base_export + gid_map["oee"]), 
            process_df(base_export + gid_map["prod"]), 
            process_df(base_export + gid_map["operarios"])
        )
    except Exception as e:
        st.error(f"Error en carga: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_operarios_raw = load_data()

# ==========================================
# 3. FILTROS Y LÓGICA
# ==========================================
if df_raw.empty:
    st.stop()

c_maq_datos = next((c for c in df_raw.columns if 'maquina' in c.lower() or 'máquina' in c.lower()), 'Máquina')
c_planta_datos = next((c for c in df_raw.columns if 'planta' in c.lower()), 'Planta')

st.sidebar.header("📅 Periodo de Análisis")
rango = st.sidebar.date_input("Seleccione fechas", [df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()])

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(rango[0])

# Bases de datos filtradas
df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)].copy()
df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)]

# Función para calcular KPIs por lista de máquinas
def get_metrics_list(machines):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_f.empty: return m
    mask = df_oee_f.apply(lambda row: any(str(x).upper() in str(val).upper() for x in machines for val in row), axis=1)
    datos = df_oee_f[mask]
    if not datos.empty:
        for k, col in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            c_act = next((c for c in datos.columns if col.lower() in c.lower()), None)
            if c_act:
                v = pd.to_numeric(datos[c_act], errors='coerce').mean()
                m[k] = float(v/100 if v > 1.1 else v)
    return m

# ==========================================
# 4. DASHBOARD - LAYOUT ORIGINAL
# ==========================================
st.title("🏭 INDICADORES FAMMA")

# INDICADORES GENERALES (ARRIBA)
st.subheader("Indicadores Globales")
show_metric_row = st.columns(4)
m_gral = get_metrics_list(['GENERAL'])
show_metric_row[0].metric("OEE", f"{m_gral['OEE']:.1%}")
show_metric_row[1].metric("Disponibilidad", f"{m_gral['DISP']:.1%}")
show_metric_row[2].metric("Performance", f"{m_gral['PERF']:.1%}")
show_metric_row[3].metric("Calidad", f"{m_gral['CAL']:.1%}")

st.divider()

# PESTAÑAS (MEDIO)
t1, t2 = st.tabs(["🏗️ ESTAMPADO", "🤖 SOLDADURA"])

with t1:
    m_est = get_metrics_list(['ESTAMPADO'])
    c_est = st.columns(4)
    c_est[0].metric("OEE Estampado", f"{m_est['OEE']:.1%}")
    c_est[1].metric("Disponibilidad", f"{m_est['DISP']:.1%}")
    c_est[2].metric("Performance", f"{m_est['PERF']:.1%}")
    c_est[3].metric("Calidad", f"{m_est['CAL']:.1%}")
    
    st.write("---")
    for l in ['LINEA 1', 'LINEA 2', 'LINEA 3', 'LINEA 4']:
        st.write(f"**{l}**")
        col_l = st.columns(4)
        m_l = get_metrics_list([l, l.replace('INEA ', '')])
        col_l[0].metric("OEE", f"{m_l['OEE']:.1%}")
        col_l[1].metric("Disp.", f"{m_l['DISP']:.1%}")
        col_l[2].metric("Perf.", f"{m_l['PERF']:.1%}")
        col_l[3].metric("Cal.", f"{m_l['CAL']:.1%}")

with t2:
    m_sol = get_metrics_list(['SOLDADURA'])
    c_sol = st.columns(4)
    c_sol[0].metric("OEE Soldadura", f"{m_sol['OEE']:.1%}")
    c_sol[1].metric("Disponibilidad", f"{m_sol['DISP']:.1%}")
    c_sol[2].metric("Performance", f"{m_sol['PERF']:.1%}")
    c_sol[3].metric("Calidad", f"{m_sol['CAL']:.1%}")

st.divider()

# GRÁFICOS (ABAJO)
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("📊 Producción por Máquina")
    if not df_prod_f.empty:
        c_m = next((c for c in df_prod_f.columns if 'maquina' in c.lower()), 'Máquina')
        st.plotly_chart(px.bar(df_prod_f.groupby(c_m)[['Buenas', 'Retrabajo']].sum().reset_index(), 
                               x=c_m, y=['Buenas', 'Retrabajo'], barmode='group', 
                               color_discrete_map={'Buenas': '#2ecc71', 'Retrabajo': '#f1c40f'}), use_container_width=True)

with col_b:
    st.subheader("⚠️ Top 15 Fallas")
    df_fal = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fal.empty:
        st.plotly_chart(px.bar(df_fal.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15), 
                               x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', 
                               color_discrete_sequence=['#e74c3c']), use_container_width=True)

# TABLAS DE FALLAS BAJO GRÁFICOS
st.markdown("### 📋 Desglose de Fallas por Máquina")
df_fallas_tab = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False)]
if not df_fallas_tab.empty:
    for maq in sorted(df_fallas_tab[c_maq_datos].unique()):
        with st.expander(f"Fallas Detectadas en {maq}"):
            df_m = df_fallas_tab[df_fallas_tab[c_maq_datos] == maq].groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
            df_m.columns = ['Tipo de Falla', 'Levantó Parada (Operador)', 'Minutos Parada']
            st.table(df_m)

# ==========================================
# 5. EXPORTACIÓN PDF (DISTINCIÓN POR PLANTA)
# ==========================================
st.header("📄 Reportes PDF")

def clean(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_table(pdf, df, widths):
    pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, widths):
        pdf.cell(width, 8, clean(col), border=1, align='C', fill=True)
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
    for i, (_, row) in enumerate(df.iterrows()):
        pdf.set_fill_color(236, 240, 241) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        for item, width in zip(row, widths):
            val = f"{item:,.1f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(width, 8, clean(val), border=1, align='C', fill=True)
        pdf.ln()

def generar_pdf_area(area):
    pdf = FPDF(); pdf.add_page(); pdf.set_text_color(41, 128, 185); pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"REPORTE DE INDICADORES - {area.upper()}", ln=True, align='C'); pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 8, f"Periodo: {ini.date()} al {fin.date()}", ln=True, align='C'); pdf.ln(5)

    # FILTRADO POR COLUMNA 'PLANTA'
    df_area = df_f[df_f[c_planta_datos].str.upper() == area.upper()].copy()
    if df_area.empty: return None
    
    # 1. KPIs
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. KPIs del Area", ln=True)
    m = get_metrics_list([area]); pdf.set_fill_color(214, 234, 248); pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, f" OEE: {m['OEE']:.1%} | D: {m['DISP']:.1%} | P: {m['PERF']:.1%} | C: {m['CAL']:.1%}", 1, 1, fill=True); pdf.ln(5)

    # 2. TOP 10 GLOBAL (SIN OPERADOR)
    pdf.cell(0, 10, "2. Top 10 Fallas del Area", ln=True)
    df_fal = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fal.empty:
        top_g = df_fal.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        draw_table(pdf, top_g, [140, 50])

    # 3. DETALLE POR MÁQUINA (CON OPERADOR)
    pdf.add_page(); pdf.cell(0, 10, "3. Detalle de Fallas por Maquina", ln=True)
    for maq in sorted(df_area[c_maq_datos].unique()):
        df_m = df_fal[df_fal[c_maq_datos] == maq].groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(5)
        if not df_m.empty:
            pdf.set_font("Arial", 'B', 10); pdf.cell(0, 8, f"Maquina: {maq}", ln=True)
            df_m.columns = ['Falla', 'Levantó Parada...', 'Min']; draw_table(pdf, df_m, [90, 60, 40]); pdf.ln(5)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c_btn = st.columns(2)
with c_btn[0]:
    if st.button("🏗️ PDF ESTAMPADO", use_container_width=True):
        res = generar_pdf_area("ESTAMPADO")
        if res: st.session_state['pdf_est'] = res
    if 'pdf_est' in st.session_state:
        st.download_button("⬇️ Descargar Reporte Estampado", st.session_state['pdf_est'], "Estampado.pdf")

with c_btn[1]:
    if st.button("🤖 PDF SOLDADURA", use_container_width=True):
        res = generar_pdf_area("SOLDADURA")
        if res: st.session_state['pdf_sol'] = res
    if 'pdf_sol' in st.session_state:
        st.download_button("⬇️ Descargar Reporte Soldadura", st.session_state['pdf_sol'], "Soldadura.pdf")

# BOTÓN DE RESPALDO DE CÓDIGO (PARA GITHUB)
with st.expander("🛠️ Herramientas de Desarrollador"):
    with open(__file__, "r", encoding="utf-8") as f:
        st.download_button("💾 Descargar Código Fuente (.txt)", f.read(), "streamlit_app.txt")
