import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import tempfile
import os

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Indicadores FAMMA", layout="wide", page_icon="🏭")

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    hr { margin-top: 2rem; margin-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS
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
                # Limpieza de números (manejo de comas y puntos)
                cols_num = ['Tiempo (Min)', 'Buenas', 'Retrabajo', 'Observadas', 'OEE', 'Disponibilidad', 'Performance', 'Calidad', 'Eficiencia']
                for c in cols_num:
                    matches = [col for col in df.columns if c.lower() in col.lower()]
                    for m in matches:
                        df[m] = df[m].astype(str).str.replace('.', '').str.replace(',', '.')
                        df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0.0)
                
                # Normalización estricta de Fecha
                col_fecha = next((c for c in df.columns if 'fecha' in c.lower()), None)
                if col_fecha:
                    df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                    df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
                
                # Limpieza de Textos
                for c_txt in ['Máquina', 'Planta', 'Fábrica', 'Evento', 'Operador', 'Nivel Evento 6', 'Nivel Evento 3']:
                    match = next((col for col in df.columns if c_txt.lower() in col.lower()), None)
                    if match: df[match] = df[match].fillna('').astype(str).str.strip()
                return df.dropna(subset=['Fecha_Filtro'])
            except: return pd.DataFrame()

        return process_df(base_export + gid_map["datos"]), process_df(base_export + gid_map["oee"]), \
               process_df(base_export + gid_map["prod"]), process_df(base_export + gid_map["operarios"])
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_raw, df_oee_raw, df_prod_raw, df_op_raw = load_data()

# ==========================================
# 3. FILTROS DEL DASHBOARD
# ==========================================
if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

st.sidebar.header("📅 Rango Dashboard")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d])

col_planta = next((c for c in df_raw.columns if 'planta' in c.lower() or 'fábrica' in c.lower()), 'Fábrica')
plantas_sel = st.sidebar.multiselect("Filtrar Planta", sorted(df_raw[col_planta].unique()), default=sorted(df_raw[col_planta].unique()))

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    ini = fin = pd.to_datetime(min_d)

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin) & (df_raw[col_planta].isin(plantas_sel))]

# ==========================================
# 4. DASHBOARD (LAYOUT ORIGINAL)
# ==========================================
st.title("🏭 INDICADORES FAMMA")

def get_kpis(df_source, filter_str):
    mask = df_source.apply(lambda row: row.astype(str).str.upper().str.contains(filter_str.upper()).any(), axis=1)
    d = df_source[mask]
    if d.empty: return {'OEE':0.0, 'D':0.0, 'P':0.0, 'C':0.0}
    return {
        'OEE': d['OEE'].mean()/100 if d['OEE'].mean() > 1.1 else d['OEE'].mean(),
        'D': d['Disponibilidad'].mean()/100 if d['Disponibilidad'].mean() > 1.1 else d['Disponibilidad'].mean(),
        'P': d['Performance'].mean()/100 if d['Performance'].mean() > 1.1 else d['Performance'].mean(),
        'C': d['Calidad'].mean()/100 if d['Calidad'].mean() > 1.1 else d['Calidad'].mean()
    }

k_g = get_kpis(df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)], 'GENERAL')
c1, c2, c3, c4 = st.columns(4)
c1.metric("OEE", f"{k_g['OEE']:.1%}"); c2.metric("Disp.", f"{k_g['D']:.1%}")
c3.metric("Perf.", f"{k_g['P']:.1%}"); c4.metric("Calidad", f"{k_g['C']:.1%}")

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    k_e = get_kpis(df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)], 'ESTAMPADO')
    st.write(f"**OEE Estampado:** {k_e['OEE']:.1%}")
with t2:
    k_s = get_kpis(df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)], 'SOLDADURA')
    st.write(f"**OEE Soldadura:** {k_s['OEE']:.1%}")

# ==========================================
# 5. MÓDULO PDF (FILTRO DE DÍA ESTRICTO)
# ==========================================
st.markdown("---")
st.header("📄 Generar Reporte PDF")

dias_disponibles = sorted(df_raw['Fecha_Filtro'].dt.date.unique(), reverse=True)
dia_reporte = st.selectbox("📅 Seleccione Día EXCLUSIVO para el PDF:", dias_disponibles)

def clean(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_table(pdf, df, widths):
    pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, widths): pdf.cell(width, 7, clean(col), 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)
    for _, row in df.iterrows():
        for i, (item, w) in enumerate(zip(row, widths)):
            val = f"{item:,.2f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(w, 6, clean(val), 1)
        pdf.ln()

def generar_pdf(area, fecha_sel):
    f_dt = pd.to_datetime(fecha_sel)
    
    # FILTRO ESTRICTO: Solo el día seleccionado
    df_dia = df_raw[df_raw['Fecha_Filtro'] == f_dt]
    df_area = df_dia[df_dia[col_planta].str.upper().str.contains(area.upper())]
    df_oee_dia = df_oee_raw[df_oee_raw['Fecha_Filtro'] == f_dt]
    df_prod_dia = df_prod_raw[df_prod_raw['Fecha_Filtro'] == f_dt]

    if df_area.empty:
        st.error(f"Sin datos para {area} el día {fecha_sel}"); return None

    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
    
    # TÍTULO Y FECHA
    pdf.cell(0, 10, clean(f"REPORTE DE INDICADORES - {area}"), ln=True)
    pdf.set_font("Arial", '', 11); pdf.cell(0, 8, f"Fecha: {fecha_sel.strftime('%d/%m/%Y')}", ln=True); pdf.ln(4)

    # 1. KPIs
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "1. KPIs Generales y por Maquina", ln=True)
    k = get_kpis(df_oee_dia, area)
    pdf.set_font("Arial", '', 10); pdf.cell(0, 7, clean(f" GLOBAL {area}: OEE {k['OEE']:.1%} | Disp: {k['D']:.1%} | Perf: {k['P']:.1%} | Cal: {k['C']:.1%}"), ln=True)
    
    maqs = sorted(df_area['Máquina'].unique())
    for m in maqs:
        km = get_kpis(df_oee_dia, m)
        pdf.cell(10); pdf.cell(0, 6, clean(f"- {m}: OEE {km['OEE']:.1%} (Disp: {km['D']:.1%} / Perf: {km['P']:.1%} / Cal: {km['C']:.1%})"), ln=True)
    pdf.ln(5)

    # 2. TOP 10 FALLAS (GRÁFICO ROJO)
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "2. Top 10 Fallas (Tiempo y Frecuencia)", ln=True)
    df_f_dia = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_f_dia.empty:
        top_f = df_f_dia.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        draw_table(pdf, top_f, [140, 50])
        fig = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c'])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.write_image(tmp.name); pdf.ln(2); pdf.image(tmp.name, x=10, w=160); os.remove(tmp.name)

    # 3. PRODUCCIÓN VS PARADAS (GRÁFICO COLORES)
    pdf.add_page(); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "3. Analisis de Eventos: Produccion vs Paradas", ln=True)
    df_area['Tipo'] = df_area['Evento'].apply(lambda x: 'Produccion' if 'Producción' in str(x) else 'Parada')
    fig_p = px.pie(df_area, values='Tiempo (Min)', names='Tipo', color='Tipo', color_discrete_map={'Produccion':'#2ecc71', 'Parada':'#e74c3c'})
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        fig_p.write_image(tmp.name); pdf.image(tmp.name, x=30, w=130); os.remove(tmp.name)

    # 4. TIEMPOS POR OPERADOR
    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "4. Tiempos Totales por Operador (Min)", ln=True)
    df_op = df_area.groupby('Operador')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
    draw_table(pdf, df_op, [140, 50])

    # 5. REGISTRO DE FALLAS DETALLADO (QUIEN LEVANTO)
    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "5. Detalle de Fallas por Maquina", ln=True)
    if not df_f_dia.empty:
        for m in maqs:
            dm = df_f_dia[df_f_dia['Máquina'] == m]
            if not dm.empty:
                pdf.set_font("Arial", 'B', 9); pdf.cell(0, 7, clean(f"Maq: {m}"), ln=True)
                res = dm.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
                res.columns = ['Falla', 'Levanto Parada', 'Min']
                draw_table(pdf, res, [80, 70, 40]); pdf.ln(3)

    # 6. PRODUCCIÓN
    pdf.add_page(); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "6. Produccion Total por Maquina", ln=True)
    df_p_a = df_prod_dia[df_prod_dia['Máquina'].isin(maqs)]
    if not df_p_a.empty:
        res_p = df_p_a.groupby('Máquina')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        draw_table(pdf, res_p, [70, 40, 40, 40])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c_btn1, c_btn2 = st.columns(2)
with c_btn1:
    if st.button("🏗️ PDF Estampado"):
        res = generar_pdf("ESTAMPADO", dia_reporte)
        if res: st.download_button(f"Reporte_Estampado_{dia_reporte}.pdf", res, f"Reporte_Estampado_{dia_reporte}.pdf")
with c_btn2:
    if st.button("🤖 PDF Soldadura"):
        res = generar_pdf("SOLDADURA", dia_reporte)
        if res: st.download_button(f"Reporte_Soldadura_{dia_reporte}.pdf", res, f"Reporte_Soldadura_{dia_reporte}.pdf")
