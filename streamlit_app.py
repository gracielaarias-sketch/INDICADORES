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
fábricas = st.sidebar.multiselect("Fábrica", sorted(df_raw['Fábrica'].unique()), default=sorted(df_raw['Fábrica'].unique()))
máquinas_globales = st.sidebar.multiselect("Máquina", sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique()), default=sorted(df_raw['Máquina'].unique()))

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]
    df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
    df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
    df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()
else: st.stop()

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

def show_historical_oee(filter_name, title):
    if not df_oee_f.empty:
        mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filter_name.upper()).any(), axis=1)
        df_proc = df_oee_f[mask].copy()
        col_oee = next((c for c in df_proc.columns if 'OEE' in c.upper()), None)
        if col_oee and not df_proc.empty:
            df_proc['OEE_Num'] = pd.to_numeric(df_proc[col_oee], errors='coerce')
            if df_proc['OEE_Num'].mean() <= 1.1: df_proc['OEE_Num'] *= 100
            trend = df_proc.groupby('Fecha_Filtro')['OEE_Num'].mean().reset_index()
            st.plotly_chart(px.line(trend, x='Fecha_Filtro', y='OEE_Num', markers=True, title=f'OEE: {title}'), use_container_width=True)

# ==========================================
# 5. DASHBOARD Y PESTAÑAS (OEE)
# ==========================================
st.title("🏭 INDICADORES FAMMA")
show_metric_row(get_metrics(df_oee_f, 'GENERAL'))
with st.expander("📉 Histórico OEE General"): show_historical_oee('GENERAL', 'Planta')

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics(df_oee_f, 'ESTAMPADO'))
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
    with st.expander("Ver Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{l}**"); show_metric_row(get_metrics(df_oee_f, l)); st.markdown("---")
with t2:
    show_metric_row(get_metrics(df_oee_f, 'SOLDADURA'))
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')
    with st.expander("Ver Detalle"):
        st.markdown("**Celdas Robotizadas**"); show_metric_row(get_metrics(df_oee_f, 'CELDA')); st.markdown("---")
        st.markdown("**PRP**"); show_metric_row(get_metrics(df_oee_f, 'PRP'))

# ==========================================
# 6. MÓDULO INDICADORES POR OPERADOR
# ==========================================
st.markdown("---")
st.header("📈 INDICADORES POR OPERADOR")
with st.expander("👉 Ver Resumen y Evolución de Operarios", expanded=False):
    if not df_op_f.empty:
        col_op = next((c for c in df_op_f.columns if any(x in c.lower() for x in ['operador', 'nombre'])), 'Operador')
        st.subheader("📋 Resumen de Días por Personal")
        df_dias = df_op_f.groupby(col_op)['Fecha_Filtro'].nunique().reset_index()
        df_dias.columns = ['Operador', 'Días con Registro']
        st.dataframe(df_dias.sort_values('Días con Registro', ascending=False), use_container_width=True, hide_index=True)
        
        sel_ops = st.multiselect("Seleccione Operarios para Graficar:", sorted(df_op_f[col_op].unique()))
        if sel_ops:
            df_perf = df_op_f[df_op_f[col_op].isin(sel_ops)].sort_values('Fecha_Filtro')
            st.plotly_chart(px.line(df_perf, x='Fecha_Filtro', y='Performance', color=col_op, markers=True, title="Evolución Performance"), use_container_width=True)

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
# 8. MÓDULO PRODUCCIÓN (CORREGIDO)
# ==========================================
st.markdown("---")
st.header("Producción General")
if not df_prod_f.empty:
    c_maq = next((c for c in df_prod_f.columns if 'máquina' in c.lower() or 'maquina' in c.lower()), None)
    c_cod = next((c for c in df_prod_f.columns if 'código' in c.lower() or 'codigo' in c.lower()), None)
    c_b = next((c for c in df_prod_f.columns if 'buenas' in c.lower()), 'Buenas')
    c_r = next((c for c in df_prod_f.columns if 'retrabajo' in c.lower()), 'Retrabajo')
    c_o = next((c for c in df_prod_f.columns if 'observadas' in c.lower()), 'Observadas')

    if c_maq:
        df_st = df_prod_f.groupby(c_maq)[[c_b, c_r, c_o]].sum().reset_index()
        st.plotly_chart(px.bar(df_st, x=c_maq, y=[c_b, c_r, c_o], title="Balance Producción", barmode='stack'), use_container_width=True)
    
        with st.expander("📂 Tablas Detalladas por Código, Máquina y Fecha"):
            df_prod_f['Fecha_Str'] = df_prod_f['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
            cols_group = [col for col in [c_cod, c_maq, 'Fecha_Str'] if col is not None]
            df_tab = df_prod_f.groupby(cols_group)[[c_b, c_r, c_o]].sum().reset_index()
            st.dataframe(df_tab.sort_values(cols_group, ascending=[True]*len(cols_group)), use_container_width=True, hide_index=True)

# ==========================================
# 9. ANÁLISIS DE TIEMPOS
# ==========================================
st.markdown("---")
st.header("Análisis de Tiempos")
if not df_f.empty:
    df_f['Tipo'] = df_f['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
    col1, col2 = st.columns([1, 2])
    with col1: st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Tipo', title="Global", hole=0.4), use_container_width=True)
    with col2: st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Tipo', title="Por Operador", barmode='group'), use_container_width=True)

# ==========================================
# 10. ANÁLISIS DE FALLAS
# ==========================================
st.markdown("---")
st.header("Análisis de Fallas")
df_fallas_app = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas_app.empty:
    m_f = st.multiselect("Filtrar Máquinas:", sorted(df_fallas_app['Máquina'].unique()), default=sorted(df_fallas_app['Máquina'].unique()))
    top_f = df_fallas_app[df_fallas_app['Máquina'].isin(m_f)].groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top 15 Fallas", text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    fig.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, height=600)
    st.plotly_chart(fig, use_container_width=True)

st.divider()
with st.expander("📂 Registro Completo"): 
    st.dataframe(df_f, use_container_width=True)

# ==========================================
# 11. DESCARGA DE PDF PROFESIONAL (MEJORADO)
# ==========================================
st.markdown("---")
st.header("📄 Generar Reporte PDF Diario")

# Selector de fecha exclusiva para el PDF (Sin acumulados)
dias_pdf = sorted(df_raw['Fecha_Filtro'].dt.date.unique(), reverse=True)
dia_reporte = st.selectbox("📅 Seleccione Fecha EXCLUSIVA para el PDF:", dias_pdf)

def clean_txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1')

def draw_table_custom(pdf, df, widths):
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, widths): pdf.cell(width, 7, clean_txt(col), 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)
    for _, row in df.iterrows():
        for i, (item, w) in enumerate(zip(row, widths)):
            val = f"{item:,.2f}" if isinstance(item, (float, int)) else str(item)
            pdf.cell(w, 6, clean_txt(val), 1)
        pdf.ln()

def generar_pdf_vfinal(area_nombre, fecha_sel):
    f_dt = pd.to_datetime(fecha_sel)
    
    # FILTRADO ESTRICTO POR DÍA (Ignora filtros de dashboard)
    df_d = df_raw[df_raw['Fecha_Filtro'] == f_dt]
    df_area = df_d[df_d['Fábrica'].str.upper().str.contains(area_nombre.upper())]
    if df_area.empty:
        st.error(f"No hay registros para {area_nombre} el día {fecha_sel}"); return None

    df_oee_d = df_oee_raw[df_oee_raw['Fecha_Filtro'] == f_dt]
    df_prod_d = df_prod_raw[df_prod_raw['Fecha_Filtro'] == f_dt]

    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, clean_txt(f"REPORTE DE INDICADORES - {area_nombre.upper()}"), ln=True, align='L')
    pdf.set_font("Arial", '', 11); pdf.cell(0, 8, f"Fecha: {fecha_sel.strftime('%d/%m/%Y')}", ln=True); pdf.ln(4)

    # 1. KPIs
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "1. KPIs Generales y por Maquina", ln=True)
    m = get_metrics(df_oee_d, area_nombre)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 7, clean_txt(f" GLOBAL {area_nombre.upper()}: OEE {m['OEE']:.1%} | Disp: {m['DISP']:.1%} | Perf: {m['PERF']:.1%} | Cal: {m['CAL']:.1%}"), ln=True)
    
    maqs_area = sorted(df_area['Máquina'].unique())
    for maq in maqs_area:
        m_maq = get_metrics(df_oee_d, maq)
        pdf.cell(10); pdf.cell(0, 6, clean_txt(f"- {maq}: OEE {m_maq['OEE']:.1%} (Disp: {m_maq['DISP']:.1%} / Perf: {m_maq['PERF']:.1%} / Cal: {m_maq['CAL']:.1%})"), ln=True)
    pdf.ln(5)

    # 2. TOP 10 FALLAS (CON GRÁFICO ROJO)
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "2. Top 10 Fallas (Tiempo y Frecuencia)", ln=True)
    df_fal_dia = df_area[df_area['Nivel Evento 3'].str.contains('FALLA', case=False)]
    if not df_fal_dia.empty:
        top_f_pdf = df_fal_dia.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        draw_table_custom(pdf, top_f_pdf, [140, 50])
        fig_fal = px.bar(top_f_pdf, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', color_discrete_sequence=['#e74c3c'])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig_fal.write_image(tmp.name); pdf.ln(2); pdf.image(tmp.name, x=10, w=160); os.remove(tmp.name)
    pdf.ln(5)

    # 3. ANALISIS EVENTOS (PIE VERDE/ROJO)
    pdf.add_page(); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "3. Analisis de Eventos: Produccion vs Paradas", ln=True)
    df_area_bal = df_area.copy()
    df_area_bal['Tipo'] = df_area_bal['Evento'].apply(lambda x: 'Produccion' if 'Producción' in str(x) else 'Parada')
    fig_pie = px.pie(df_area_bal, values='Tiempo (Min)', names='Tipo', color='Tipo', color_discrete_map={'Produccion': '#2ecc71', 'Parada': '#e74c3c'})
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        fig_pie.write_image(tmp.name); pdf.image(tmp.name, x=40, w=120); os.remove(tmp.name)
    pdf.ln(5)

    # 4. TIEMPOS POR OPERADOR
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "4. Tiempos Totales por Operador (Min)", ln=True)
    df_op_dia = df_area.groupby('Operador')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
    draw_table_custom(pdf, df_op_dia, [140, 50])
    pdf.ln(5)

    # 5. DETALLE FALLAS (CON QUIEN LEVANTO)
    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "5. Registro de Paradas Detallado (Maquina y Operador)", ln=True)
    if not df_fal_dia.empty:
        for m in maqs_area:
            df_m = df_fal_dia[df_fal_dia['Máquina'] == m]
            if not df_m.empty:
                pdf.set_font("Arial", 'B', 10); pdf.cell(0, 7, clean_txt(f"Maq: {m}"), ln=True)
                res_m = df_m.groupby(['Nivel Evento 6', 'Operador'])['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
                res_m.columns = ['Falla', 'Levanto Parada', 'Min']
                draw_table_custom(pdf, res_m, [80, 70, 40]); pdf.ln(4)

    # 6. PRODUCCIÓN TOTAL
    pdf.add_page(); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, "6. Produccion Total por Maquina", ln=True)
    df_p_dia = df_prod_d[df_prod_d['Máquina'].isin(maqs_area)]
    if not df_p_dia.empty:
        res_p = df_p_dia.groupby('Máquina')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        draw_table_custom(pdf, res_p, [70, 40, 40, 40])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name); return open(tmp.name, "rb").read()

c1, c2 = st.columns(2)
with c1:
    if st.button("🏗️ Descargar PDF Estampado"):
        res = generar_pdf_vfinal("ESTAMPADO", dia_reporte)
        if res: st.download_button(f"Confirmar Estampado {dia_reporte}", res, f"Reporte_Estampado_{dia_reporte}.pdf")
with c2:
    if st.button("🤖 Descargar PDF Soldadura"):
        res = generar_pdf_vfinal("SOLDADURA", dia_reporte)
        if res: st.download_button(f"Confirmar Soldadura {dia_reporte}", res, f"Reporte_Soldadura_{dia_repor
