import streamlit as st
import pandas as pd
import plotly.express as px
import tempfile
import os
from fpdf import FPDF

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
            
            cols_texto = ['Fábrica', 'Máquina', 'Evento', 'Código', 'Operador', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6', 'Nombre', 'Inicio', 'Fin', 'Desde', 'Hasta']
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

if df_raw.empty:
    st.warning("No hay datos cargados.")
    st.stop()

# ==========================================
# 3. FILTROS GLOBALES
# ==========================================
st.sidebar.header("📅 Rango de tiempo")
min_d, max_d = df_raw['Fecha_Filtro'].min().date(), df_raw['Fecha_Filtro'].max().date()
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")

opciones_fabricas = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabricas, default=opciones_fabricas)

opciones_maquinas = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", opciones_maquinas, default=opciones_maquinas)

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]).normalize(), pd.to_datetime(rango[1]).normalize()
    df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]
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
show_metric_row(get_metrics('GENERAL'))
with st.expander("📉 Histórico OEE General"): show_historical_oee('GENERAL', 'Planta')

st.divider()
t1, t2 = st.tabs(["Estampado", "Soldadura"])
with t1:
    show_metric_row(get_metrics('ESTAMPADO'))
    with st.expander("📉 Histórico Estampado"): show_historical_oee('ESTAMPADO', 'Estampado')
    with st.expander("Ver Líneas"):
        for l in ['L1', 'L2', 'L3', 'L4']:
            st.markdown(f"**{l}**"); show_metric_row(get_metrics(l)); st.markdown("---")
with t2:
    show_metric_row(get_metrics('SOLDADURA'))
    with st.expander("📉 Histórico Soldadura"): show_historical_oee('SOLDADURA', 'Soldadura')
    with st.expander("Ver Detalle"):
        st.markdown("**Celdas Robotizadas**"); show_metric_row(get_metrics('CELDA')); st.markdown("---")
        st.markdown("**PRP**"); show_metric_row(get_metrics('PRP'))

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
# 8. MÓDULO PRODUCCIÓN
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
            df_prod_f['Fecha_Str'] = pd.to_datetime(df_prod_f['Fecha_Filtro']).dt.strftime('%d-%m-%Y')
            cols_group = [col for col in [c_cod, c_maq, 'Fecha_Str'] if col is not None]
            df_tab = df_prod_f.groupby(cols_group)[[c_b, c_r, c_o]].sum().reset_index()
            sort_cols = [c for c in [c_cod, 'Fecha_Str'] if c in df_tab.columns]
            st.dataframe(df_tab.sort_values(sort_cols, ascending=[True, False]), use_container_width=True, hide_index=True)

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
df_fallas = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)].copy()
if not df_fallas.empty:
    m_f = st.multiselect("Filtrar Máquinas:", sorted(df_fallas['Máquina'].unique()), default=sorted(df_fallas['Máquina'].unique()))
    top_f = df_fallas[df_fallas['Máquina'].isin(m_f)].groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(15)
    fig = px.bar(top_f, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title="Top 15 Fallas", text='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Reds')
    fig.update_traces(texttemplate='%{text:.0f} min', textposition='outside')
    fig.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, height=600)
    st.plotly_chart(fig, use_container_width=True)

st.divider()
with st.expander("📂 Registro Completo"): st.dataframe(df_f, use_container_width=True)

# ==========================================
# 11. EXPORTACIÓN A PDF (INDEPENDIENTE DEL DASHBOARD)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("📄 Exportar Reportes PDF")

fecha_pdf = st.sidebar.date_input(
    "Seleccionar fecha para el reporte", 
    value=max_d, 
    min_value=min_d, 
    max_value=max_d,
    key="pdf_date_filter"
)

def clean_text(text):
    if pd.isna(text): return "-"
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def get_metrics_pdf(name_filter, df_oee_target):
    m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
    if df_oee_target.empty: return m
    mask = df_oee_target.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
    datos = df_oee_target[mask]
    if not datos.empty:
        for key, col_search in {'OEE':'OEE', 'DISP':'Disponibilidad', 'PERF':'Performance', 'CAL':'Calidad'}.items():
            actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
            if actual_col:
                vals = pd.to_numeric(datos[actual_col], errors='coerce').dropna()
                if not vals.empty:
                    v = vals.mean()
                    m[key] = float(v/100 if v > 1.1 else v)
    return m

def crear_pdf(area, fecha):
    fecha_target = pd.to_datetime(fecha).normalize()
    
    # Filtrar datos principales por fecha y área
    df_pdf = df_raw[(df_raw['Fecha_Filtro'] == fecha_target) & (df_raw['Fábrica'].str.contains(area, case=False))].copy()
    df_oee_pdf = df_oee_raw[df_oee_raw['Fecha_Filtro'] == fecha_target].copy()
    
    # Filtrar producción
    df_prod_pdf = pd.DataFrame()
    if not df_prod_raw.empty:
        df_prod_pdf = df_prod_raw[(df_prod_raw['Fecha_Filtro'] == fecha_target) & 
                                  (df_prod_raw['Máquina'].str.contains(area, case=False) | df_prod_raw['Máquina'].isin(df_pdf['Máquina'].unique()))].copy()
    
    # Filtrar operarios (sin restricción de área para la tabla de Performance general)
    df_op_pdf = pd.DataFrame()
    if not df_operarios_raw.empty:
        df_op_pdf = df_operarios_raw[df_operarios_raw['Fecha_Filtro'] == fecha_target].copy()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_text(f"Reporte de Indicadores - {area.upper()}"), ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, clean_text(f"Fecha del Reporte: {fecha.strftime('%d-%m-%Y')}"), ln=True, align='C')
    pdf.ln(5)

    # 1. OEE DEL ÁREA Y MÁQUINAS
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("1. Resumen General y OEE"), ln=True)
    pdf.set_font("Arial", 'B', 10)
    
    metrics_area = get_metrics_pdf(area, df_oee_pdf)
    pdf.cell(0, 8, clean_text(f"General {area.upper()} | OEE: {metrics_area['OEE']:.1%} | Disp: {metrics_area['DISP']:.1%} | Perf: {metrics_area['PERF']:.1%} | Calidad: {metrics_area['CAL']:.1%}"), ln=True)
    
    # PROMEDIOS BAÑO Y REFRIGERIO
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, clean_text("Tiempos Promedio (por registro):"), ln=True)
    pdf.set_font("Arial", '', 10)
    
    if not df_pdf.empty:
        avg_bano = df_pdf[df_pdf['Nivel Evento 4'].astype(str).str.contains('Baño', case=False, na=False)]['Tiempo (Min)'].mean()
        avg_refr = df_pdf[df_pdf['Nivel Evento 4'].astype(str).str.contains('Refrigerio', case=False, na=False)]['Tiempo (Min)'].mean()
        
        avg_bano_str = f"{avg_bano:.1f} min" if not pd.isna(avg_bano) else "Sin registros"
        avg_refr_str = f"{avg_refr:.1f} min" if not pd.isna(avg_refr) else "Sin registros"
        
        pdf.cell(0, 6, clean_text(f"   -> Promedio Baño: {avg_bano_str}"), ln=True)
        pdf.cell(0, 6, clean_text(f"   -> Promedio Refrigerio: {avg_refr_str}"), ln=True)
    else:
         pdf.cell(0, 6, clean_text("   -> Sin datos de tiempos para el área seleccionada."), ln=True)
    pdf.ln(3)

    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, clean_text("Detalle OEE por Máquina/Línea:"), ln=True)
    pdf.set_font("Arial", '', 10)
    lineas = ['L1', 'L2', 'L3', 'L4'] if area.upper() == 'ESTAMPADO' else ['CELDA', 'PRP']
    for l in lineas:
        m_l = get_metrics_pdf(l, df_oee_pdf)
        pdf.cell(0, 6, clean_text(f"   -> {l}  -  OEE: {m_l['OEE']:.1%} | Disp: {m_l['DISP']:.1%} | Perf: {m_l['PERF']:.1%} | Calidad: {m_l['CAL']:.1%}"), ln=True)
    pdf.ln(5)

    # 2. ANÁLISIS DE FALLAS
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("2. Análisis de Fallas"), ln=True)
    df_fallas_area = df_pdf[df_pdf['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    
    if not df_fallas_area.empty:
        top_fallas = df_fallas_area.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        
        fig_fallas = px.bar(top_fallas, x='Nivel Evento 6', y='Tiempo (Min)', title=f"Top 10 Fallas - {area}", color='Tiempo (Min)', color_continuous_scale='Reds', text='Tiempo (Min)')
        fig_fallas.update_traces(texttemplate='%{text:.1f}', textposition='outside', cliponaxis=False)
        fig_fallas.update_layout(width=800, height=450, margin=dict(t=80, b=150, l=40, r=40))
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            fig_fallas.write_image(tmpfile.name, engine="kaleido")
            pdf.image(tmpfile.name, w=170)
            os.remove(tmpfile.name)
        
        pdf.ln(5)
        
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, clean_text("Detalle de Fallas por Máquina:"), ln=True)
        pdf.ln(2)
        
        col_inicio = next((c for c in df_pdf.columns if 'inicio' in c.lower() or 'desde' in c.lower()), None)
        col_fin = next((c for c in df_pdf.columns if 'fin' in c.lower() or 'hasta' in c.lower()), None)

        maquinas_con_fallas = sorted(df_fallas_area['Máquina'].unique())
        for maq in maquinas_con_fallas:
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 8, clean_text(f"-> Máquina: {maq}"), ln=True)
            
            pdf.set_font("Arial", 'B', 8)
            pdf.cell(15, 8, clean_text("Inicio"), border=1, align='C')
            pdf.cell(15, 8, clean_text("Fin"), border=1, align='C')
            pdf.cell(90, 8, clean_text("Falla"), border=1)
            pdf.cell(15, 8, clean_text("Min"), border=1, align='C')
            pdf.cell(45, 8, clean_text("Levantó la falla"), border=1, ln=True)
            
            pdf.set_font("Arial", '', 8)
            df_maq = df_fallas_area[df_fallas_area['Máquina'] == maq]
            
            cols_dup = [c for c in [col_inicio, col_fin, 'Nivel Evento 6', 'Operador'] if c is not None]
            if cols_dup: df_maq = df_maq.drop_duplicates(subset=cols_dup)
            df_maq = df_maq.sort_values('Tiempo (Min)', ascending=False)
            
            for _, row in df_maq.iterrows():
                val_inicio = str(row[col_inicio])[:5] if col_inicio and str(row[col_inicio]) != 'nan' else "-"
                val_fin = str(row[col_fin])[:5] if col_fin and str(row[col_fin]) != 'nan' else "-"
                
                pdf.cell(15, 8, clean_text(val_inicio), border=1, align='C')
                pdf.cell(15, 8, clean_text(val_fin), border=1, align='C')
                pdf.cell(90, 8, clean_text(str(row['Nivel Evento 6'])[:60]), border=1)
                pdf.cell(15, 8, clean_text(f"{row['Tiempo (Min)']:.1f}"), border=1, align='C')
                pdf.cell(45, 8, clean_text(str(row['Operador'])[:30]), border=1, ln=True)
            pdf.ln(3) 
            
    pdf.ln(5)
    
    # 3. PRODUCCIÓN VS PARADA
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("3. Relación Producción vs Parada"), ln=True)
    if not df_pdf.empty:
        df_pdf['Tipo'] = df_pdf['Evento'].apply(lambda x: 'Producción' if 'Producción' in str(x) else 'Parada')
        fig_pie = px.pie(df_pdf, values='Tiempo (Min)', names='Tipo', hole=0.4, color='Tipo', color_discrete_map={'Producción':'#2CA02C', 'Parada':'#D62728'})
        fig_pie.update_layout(width=500, height=350, margin=dict(t=30, b=20, l=20, r=20))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile2:
            fig_pie.write_image(tmpfile2.name, engine="kaleido")
            pdf.image(tmpfile2.name, w=110)
            os.remove(tmpfile2.name)

    pdf.ln(5)
    
    # 4. PRODUCCIÓN POR MÁQUINA
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("4. Producción por Máquina"), ln=True)
    if not df_prod_pdf.empty and 'Buenas' in df_prod_pdf.columns:
        prod_maq = df_prod_pdf.groupby('Máquina')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        
        fig_prod = px.bar(prod_maq, x='Máquina', y=['Buenas', 'Retrabajo', 'Observadas'], barmode='stack', color_discrete_sequence=['#1F77B4', '#FF7F0E', '#d62728'], text_auto=True)
        fig_prod.update_layout(width=800, height=450, margin=dict(t=60, b=150, l=40, r=40))
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile3:
            fig_prod.write_image(tmpfile3.name, engine="kaleido")
            pdf.image(tmpfile3.name, w=170)
            os.remove(tmpfile3.name)
            
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 8, clean_text("Desglose por Código de Producto:"), ln=True)
        pdf.set_font("Arial", 'B', 8)
        
        pdf.cell(40, 8, clean_text("Máquina"), border=1)
        pdf.cell(60, 8, clean_text("Código de Producto"), border=1)
        pdf.cell(25, 8, clean_text("Buenas"), border=1, align='C')
        pdf.cell(25, 8, clean_text("Retrabajo"), border=1, align='C')
        pdf.cell(30, 8, clean_text("Observadas"), border=1, align='C', ln=True)
        
        pdf.set_font("Arial", '', 8)
        c_cod = next((c for c in df_prod_pdf.columns if 'código' in c.lower() or 'codigo' in c.lower()), 'Código')
        
        df_prod_group = df_prod_pdf.groupby(['Máquina', c_cod])[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index().sort_values('Máquina')
        for _, row in df_prod_group.iterrows():
            pdf.cell(40, 8, clean_text(str(row['Máquina'])[:25]), border=1)
            pdf.cell(60, 8, clean_text(str(row[c_cod])[:40]), border=1) 
            pdf.cell(25, 8, clean_text(str(int(row['Buenas']))), border=1, align='C')
            pdf.cell(25, 8, clean_text(str(int(row['Retrabajo']))), border=1, align='C')
            pdf.cell(30, 8, clean_text(str(int(row['Observadas']))), border=1, align='C', ln=True)

    pdf.ln(5)

    # 5. TIEMPOS POR OPERARIO
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("5. Tiempos por Operario"), ln=True)
    if not df_pdf.empty:
        op_tiempos = df_pdf.groupby('Operador')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
        
        fig_op = px.bar(op_tiempos, x='Operador', y='Tiempo (Min)', color='Tiempo (Min)', color_continuous_scale='Blues', text='Tiempo (Min)')
        fig_op.update_traces(texttemplate='%{text:.1f}', textposition='outside', cliponaxis=False)
        fig_op.update_layout(width=800, height=450, margin=dict(t=80, b=150, l=40, r=40))
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile4:
            fig_op.write_image(tmpfile4.name, engine="kaleido")
            pdf.image(tmpfile4.name, w=170)
            os.remove(tmpfile4.name)
            
        pdf.ln(5)
        
        # Tabla resumen (solo tiempos)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 8, clean_text("Resumen de Tiempos:"), ln=True)
        pdf.set_font("Arial", 'B', 8)
        
        pdf.cell(100, 8, clean_text("Operador"), border=1)
        pdf.cell(50, 8, clean_text("Tiempo Total (Min)"), border=1, align='C', ln=True)
        
        pdf.set_font("Arial", '', 8)
        for _, row in op_tiempos.iterrows():
            pdf.cell(100, 8, clean_text(str(row['Operador'])[:50]), border=1)
            pdf.cell(50, 8, clean_text(f"{row['Tiempo (Min)']:.1f}"), border=1, align='C', ln=True)

    pdf.ln(5)
    
    # =========================================================
    # 6. TABLA INDEPENDIENTE: PERFORMANCE GENERAL DE OPERARIOS
    # =========================================================
    pdf.add_page() # Lo enviamos a una página limpia para no agolpar datos
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("6. Performance de Operarios (Día Seleccionado)"), ln=True)
    
    if not df_op_pdf.empty:
        c_op_name = next((c for c in df_op_pdf.columns if 'operador' in c.lower() or 'nombre' in c.lower()), None)
        c_perf = next((c for c in df_op_pdf.columns if 'performance' in c.lower()), None)
        
        if c_op_name and c_perf:
            # Ordenamos alfabéticamente a los operarios
            df_op_print = df_op_pdf.sort_values(c_op_name)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(120, 8, clean_text("Operador"), border=1)
            pdf.cell(60, 8, clean_text("Performance"), border=1, align='C', ln=True)
            
            pdf.set_font("Arial", '', 10)
            for _, row in df_op_print.iterrows():
                # Convertimos y formateamos para evitar errores de impresión
                perf_val = pd.to_numeric(row[c_perf], errors='coerce')
                perf_str = f"{perf_val:.2f}" if pd.notna(perf_val) else "-"
                
                pdf.cell(120, 8, clean_text(str(row[c_op_name])[:60]), border=1)
                pdf.cell(60, 8, clean_text(perf_str), border=1, align='C', ln=True)
        else:
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 8, clean_text("No se encontraron columnas de Operador/Performance en la base de datos."), ln=True)
    else:
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 8, clean_text("No hay registros de performance para el día seleccionado."), ln=True)

    # FINALIZAR Y GUARDAR PDF
    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_pdf.name)
    with open(temp_pdf.name, "rb") as f:
        pdf_bytes = f.read()
    os.remove(temp_pdf.name)
    return pdf_bytes

# Botones de descarga
if st.sidebar.button("Generar PDF Estampado"):
    with st.spinner(f"Generando PDF de Estampado para el {fecha_pdf.strftime('%d-%m-%Y')}..."):
        try:
            pdf_data = crear_pdf("Estampado", fecha_pdf)
            st.sidebar.download_button(label="⬇️ Descargar PDF Estampado", data=pdf_data, file_name=f"Reporte_Estampado_{fecha_pdf.strftime('%d_%m_%Y')}.pdf", mime="application/pdf")
            st.sidebar.success("¡PDF listo para descargar!")
        except Exception as e:
            st.sidebar.error(f"Error generando el PDF. ¿Instalaste 'kaleido' y 'fpdf'?: {e}")

if st.sidebar.button("Generar PDF Soldadura"):
    with st.spinner(f"Generando PDF de Soldadura para el {fecha_pdf.strftime('%d-%m-%Y')}..."):
        try:
            pdf_data = crear_pdf("Soldadura", fecha_pdf)
            st.sidebar.download_button(label="⬇️ Descargar PDF Soldadura", data=pdf_data, file_name=f"Reporte_Soldadura_{fecha_pdf.strftime('%d_%m_%Y')}.pdf", mime="application/pdf")
            st.sidebar.success("¡PDF listo para descargar!")
        except Exception as e:
            st.sidebar.error(f"Error generando el PDF. ¿Instalaste 'kaleido' y 'fpdf'?: {e}")
