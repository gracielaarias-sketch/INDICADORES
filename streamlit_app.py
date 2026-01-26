import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Auditoría Integral de Planta", layout="wide")

# ==========================================
# 🆕 LOGO GRANDE EN BARRA LATERAL 
# ==========================================
url_logo = "https://raw.githubusercontent.com/gracielaarias-sketch/INDICADORES/refs/heads/main/LOGOFAMMA.png?token=GHSAT0AAAAAADUB4YKJ5G5TPVKNFQIQ5JD62LXPWXA"
# 'use_container_width=True' hace que ocupe todo el ancho de la columna
st.sidebar.image(url_logo, use_container_width=True)

# ==========================================

# 2. CARGA DE DATOS ROBUSTA DESDE PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    gid_datos = "0"
    gid_oee = "1767654796" 
    
    url_csv_datos = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_datos}"
    url_csv_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

    @st.cache_data(ttl=300)
    def load_pandas_df(url):
        df = pd.read_csv(url)
        if 'Tiempo (Min)' in df.columns:
            df['Tiempo (Min)'] = df['Tiempo (Min)'].astype(str).str.replace(',', '.')
            df['Tiempo (Min)'] = pd.to_numeric(df['Tiempo (Min)'], errors='coerce').fillna(0.0)
        
        col_fecha = next((c for c in df.columns if c.lower() == 'fecha'), None)
        if col_fecha:
            df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
            df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
        return df

    df_raw = load_pandas_df(url_csv_datos)
    df_oee_raw = load_pandas_df(url_csv_oee)

    # 3. FILTROS
    st.sidebar.header("📅 Rango de Auditoría")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="audit_range")

    st.sidebar.header("⚙️ Filtros de Planta")
    df_raw['Fábrica'] = df_raw['Fábrica'].fillna('Sin Especificar').astype(str)
    df_raw['Máquina'] = df_raw['Máquina'].fillna('Sin Especificar').astype(str)
    
    opciones_fabrica = sorted(df_raw['Fábrica'].unique())
    fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)
    opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
    máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

    # 4. APLICACIÓN DE FILTROS
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
        df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
    else:
        st.stop()

    # 5. VISUALIZACIÓN OEE CON DESPLEGABLES
    st.title("🏭 OEE Detallado")
    
    if not df_oee_f.empty:
        def get_metrics(name_filter):
            mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(name_filter.upper()).any(), axis=1)
            datos = df_oee_f[mask]
            m = {'OEE': 0.0, 'DISP': 0.0, 'PERF': 0.0, 'CAL': 0.0}
            if not datos.empty:
                cols_map = {'OEE': 'OEE', 'DISP': 'Disponibilidad', 'PERF': 'Performance', 'CAL': 'Calidad'}
                for key, col_search in cols_map.items():
                    actual_col = next((c for c in datos.columns if col_search.lower() in c.lower()), None)
                    if actual_col:
                        val = str(datos[actual_col].iloc[0]).replace('%', '').replace(',', '.')
                        val_num = pd.to_numeric(val, errors='coerce')
                        m[key] = float(val_num / 100 if val_num > 1.0 else val_num)
            return m

        def show_metric_row(m):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("OEE", f"{m['OEE']:.1%}")
            c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
            c3.metric("Performance", f"{m['PERF']:.1%}")
            c4.metric("Calidad", f"{m['CAL']:.1%}")

        # SECCIÓN PLANTA GENERAL
        st.subheader("Planta Total")
        show_metric_row(get_metrics('GENERAL'))
        st.divider()

        # SECCIÓN ESTAMPADO
        st.subheader("Estampado")
        show_metric_row(get_metrics('ESTAMPADO'))
        with st.expander("Ver detalle por Líneas (L1, L2, L3, L4)"):
            for linea in ['L1', 'L2', 'L3', 'L4']:
                st.markdown(f"**Línea {linea}**")
                show_metric_row(get_metrics(linea))
        st.divider()

        # SECCIÓN SOLDADURA
        st.subheader("Soldadura")
        show_metric_row(get_metrics('SOLDADURA'))
        with st.expander("Ver detalle Soldadura (Celda, PRP)"):
            for sub in ['CELDA', 'PRP']:
                st.markdown(f"**Proceso {sub}**")
                show_metric_row(get_metrics(sub))
        st.divider()

    # 6. MÉTRICAS OPERATIVAS (REGISTROS)
    if not df_f.empty:
        t_prod = float(df_f[df_f['Evento'].astype(str).str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum())
        t_fallas = float(df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum())
        
        st.subheader("Resumen de Tiempos Registrados")
        m1, m2, m3 = st.columns(3)
        m1.metric("Producción Real", f"{t_prod:,.1f} min")
        m2.metric("Tiempo en Fallas", f"{t_fallas:,.1f} min")
        m3.metric("Eventos del Periodo", len(df_f))

        # 7. GRÁFICOS
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
        with g2:
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Rendimiento por Operador", barmode='group'), use_container_width=True)

        st.divider()
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        df_f6 = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            st.plotly_chart(px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds'), use_container_width=True)

        st.divider()
        st.subheader("🔥 Mapa de Calor: Máquinas vs Causa")
        df_hm = df_f[df_f['Evento'].astype(str).str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            st.plotly_chart(px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True), use_container_width=True)

except Exception as e:
    st.error(f"Error crítico: {e}")
