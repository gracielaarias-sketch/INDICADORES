
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
rango = st.sidebar.date_input("Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="main_date_filter")

st.sidebar.divider()
st.sidebar.header("⚙️ Filtros")

opciones_fabrica = sorted(df_raw['Fábrica'].unique())
fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
máquinas_globales = st.sidebar.multiselect("Máquina", options=opciones_maquina, default=opciones_maquina)

# Manejo robusto de fechas
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
elif isinstance(rango, (list, tuple)) and len(rango) == 1:
    ini = fin = pd.to_datetime(rango[0])
else:
    ini = fin = pd.to_datetime(min_d)

df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas_globales)]

df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
df_prod_f = df_prod_raw[(df_prod_raw['Fecha_Filtro'] >= ini) & (df_prod_raw['Fecha_Filtro'] <= fin)] if not df_prod_raw.empty else pd.DataFrame()
df_op_f = df_operarios_raw[(df_operarios_raw['Fecha_Filtro'] >= ini) & (df_operarios_raw['Fecha_Filtro'] <= fin)] if not df_operarios_raw.empty else pd.DataFrame()

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
            df_prod_f['Fecha_Str'] = df_prod_f['Fecha_Filtro'].dt.strftime('%d-%m-%Y')
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
# 11. EXPORTACIÓN A PDF POR ÁREA (MODIFICADO CON COLORES)
# ==========================================
st.markdown("---")
st.header("📄 Exportar Reportes PDF")

try:
    from fpdf import FPDF
    import tempfile
    import os
except ImportError:
    st.warning("⚠️ Faltan librerías para exportar. Asegúrate de tener 'fpdf2' y 'kaleido' en tu requirements.txt.")

# Función para limpiar texto y evitar errores de caracteres en FPDF
def clean_text(text):
    return str(text).encode('latin-1', 'replace').decode('latin-1')

# Función auxiliar para dibujar tablas a color en el PDF
def draw_pdf_table(pdf, df, col_widths, max_rows=10):
    if df.empty:
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 8, "No hay datos para mostrar en este periodo.", ln=True)
        return

    # Encabezados (Fondo Azul Noche)
    pdf.set_fill_color(44, 62, 80) 
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    for col, width in zip(df.columns, col_widths):
        pdf.cell(width, 8, clean_text(col)[:25], border=1, align='C', fill=True)
    pdf.ln()
    
    # Filas (Colores intercalados para fácil lectura)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", '', 9)
    for i, (_, row) in enumerate(df.head(max_rows).iterrows()):
        if i % 2 == 0:
            pdf.set_fill_color(236, 240, 241) # Gris claro
        else:
            pdf.set_fill_color(255, 255, 255) # Blanco
            
        for item, width in zip(row, col_widths):
            val = clean_text(item)
            if isinstance(item, float): val = f"{item:.2f}"
            pdf.cell(width, 8, val[:25], border=1, align='C', fill=True)
        pdf.ln()

def generar_pdf_area(area_nombre, lineas):
    if "FPDF" not in globals(): return None
    
    pdf = FPDF()
    pdf.add_page()
    
    # Función de ayuda para Títulos
    def titulo_seccion(texto):
        pdf.set_text_color(41, 128, 185) # Azul Institucional
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, texto, ln=True)
        pdf.set_text_color(0, 0, 0) # Vuelve a negro
        pdf.set_font("Arial", '', 11)

    # TÍTULO PRINCIPAL
    pdf.set_text_color(41, 128, 185)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"REPORTE DE INDICADORES - {area_nombre.upper()}", ln=True, align='C')
    pdf.ln(5)
    
    # ---------------------------------------------------------
    # 1. KPIs COMPLETOS (OEE, DISP, PERF, CAL)
    # ---------------------------------------------------------
    titulo_seccion("1. KPIs Generales y por Maquina")
    
    m_gen = get_metrics(area_nombre)
    # Fila global resaltada
    pdf.set_fill_color(214, 234, 248) # Fondo azul muy suave
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, f" GLOBAL {area_nombre}: OEE {m_gen['OEE']*100:.1f}% | Disp: {m_gen['DISP']*100:.0f}% | Perf: {m_gen['PERF']*100:.0f}% | Cal: {m_gen['CAL']*100:.0f}%", ln=True, fill=True)
    
    pdf.set_font("Arial", '', 10)
    for linea in lineas:
        ml = get_metrics(linea)
        pdf.cell(0, 8, f"   - {linea}: OEE {ml['OEE']*100:.1f}% (Disp: {ml['DISP']*100:.0f}%  /  Perf: {ml['PERF']*100:.0f}%  /  Cal: {ml['CAL']*100:.0f}%)", ln=True)
    pdf.ln(5)

    # Filtrar DataFrames para el área específica
    mask_f = df_f.apply(lambda r: r.astype(str).str.upper().str.contains(area_nombre.upper()).any(), axis=1)
    df_area = df_f[mask_f].copy()

    # ---------------------------------------------------------
    # 2. TOP FALLAS Y GRÁFICO (AHORA EN 2DO LUGAR)
    # ---------------------------------------------------------
    titulo_seccion("2. Top 10 Fallas (Tiempo y Frecuencia)")
    df_fallas_area = df_area[df_area['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False)]
    
    if not df_fallas_area.empty:
        top_fallas = df_fallas_area.groupby('Nivel Evento 6')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False).head(10)
        draw_pdf_table(pdf, top_fallas, [130, 40], max_rows=10)
        
        try:
            # Gráfico de fallas a color
            fig = px.bar(top_fallas, x='Tiempo (Min)', y='Nivel Evento 6', orientation='h', title=f"Top Fallas", color='Tiempo (Min)', color_continuous_scale='Reds')
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
                fig.write_image(tmp_img.name, format="png", width=700, height=350)
                pdf.ln(3)
                pdf.image(tmp_img.name, x=10, w=180)
        except Exception:
            pass # Falla silenciosa de la imagen si algo sale mal
    else:
        pdf.cell(0, 8, "No se registraron fallas en este periodo.", ln=True)

    pdf.add_page() # Pasamos a la hoja 2

    # ---------------------------------------------------------
    # 3. PARADA Y PRODUCCIÓN (AHORA EN GRÁFICO CON COLORES)
    # ---------------------------------------------------------
    titulo_seccion("3. Analisis de Eventos: Produccion vs Paradas")
    if not df_area.empty and 'Tipo' in df_area.columns:
        df_ev = df_area.groupby(['Tipo', 'Evento'])['Tiempo (Min)'].sum().reset_index()
        df_ev_top = df_ev.sort_values('Tiempo (Min)', ascending=False).head(15) # Top 15 total
        
        try:
            # Colores: Produccion en Verde, Parada en Rojo
            colores = {'Producción': '#2ecc71', 'Parada': '#e74c3c'}
            fig_ev = px.bar(df_ev_top, x='Tiempo (Min)', y='Evento', color='Tipo', orientation='h', title="Top 15 Eventos Totales", color_discrete_map=colores)
            fig_ev.update_layout(yaxis={'categoryorder':'total ascending'})
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img2:
                fig_ev.write_image(tmp_img2.name, format="png", width=700, height=450)
                pdf.image(tmp_img2.name, x=10, w=180)
        except Exception:
            pdf.cell(0, 8, "(No se pudo generar el grafico de eventos)", ln=True)
    else:
        pdf.cell(0, 8, "No hay datos de eventos para graficar.", ln=True)
    pdf.ln(5)

    # ---------------------------------------------------------
    # 4. TIEMPOS POR OPERADOR
    # ---------------------------------------------------------
    titulo_seccion("4. Tiempos Totales por Operador (Min)")
    if not df_area.empty:
        df_t_op = df_area.groupby('Operador')['Tiempo (Min)'].sum().reset_index().sort_values('Tiempo (Min)', ascending=False)
        draw_pdf_table(pdf, df_t_op, [100, 50])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf.output(tmp_pdf.name)
        with open(tmp_pdf.name, "rb") as f:
            return f.read()

# Interfaz de botones
if "FPDF" in globals():
    c1, c2 = st.columns(2)

    with c1:
        if st.button("🏗️ Preparar PDF - ESTAMPADO", use_container_width=True):
            with st.spinner("Compilando reporte de Estampado..."):
                pdf_bytes = generar_pdf_area("ESTAMPADO", ['L1', 'L2', 'L3', 'L4'])
                if pdf_bytes:
                    st.session_state['pdf_est'] = pdf_bytes

        if 'pdf_est' in st.session_state:
            st.download_button("⬇️ Descargar PDF Estampado", data=st.session_state['pdf_est'], file_name="Reporte_Estampado.pdf", mime="application/pdf", use_container_width=True)

    with c2:
        if st.button("🤖 Preparar PDF - SOLDADURA", use_container_width=True):
            with st.spinner("Compilando reporte de Soldadura..."):
                pdf_bytes = generar_pdf_area("SOLDADURA", ['CELDA', 'PRP'])
                if pdf_bytes:
                    st.session_state['pdf_sol'] = pdf_bytes

        if 'pdf_sol' in st.session_state:
            st.download_button("⬇️ Descargar PDF Soldadura", data=st.session_state['pdf_sol'], file_name="Reporte_Soldadura.pdf", mime="application/pdf", use_container_width=True)
