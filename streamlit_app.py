import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Auditoría Integral de Planta", layout="wide")

# 2. CARGA DE DATOS ROBUSTA DESDE PANDAS (Doble Hoja)
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # GIDs de las pestañas
    gid_datos = "0"
    gid_oee = "1767654796" # <-- Verifica que este sea el GID de tu pestaña OEE
    
    url_csv_datos = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_datos}"
    url_csv_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

    @st.cache_data(ttl=300)
    def load_pandas_df(url):
        df = pd.read_csv(url)
        # Normalización de Fecha
        col_fecha = next((c for c in df.columns if c.lower() == 'fecha'), None)
        if col_fecha:
            df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
            df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
        
        # Limpieza de valores porcentuales y comas para todas las columnas numéricas
        for col in df.columns:
            if df[col].dtype == 'object':
                # Reemplazamos % y cambiamos coma por punto para que Pandas lo entienda como número
                df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '.')
        return df

    df_raw = load_pandas_df(url_csv_datos)
    df_oee_raw = load_pandas_df(url_csv_oee)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Rango de Auditoría")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="audit_range")

    st.sidebar.header("⚙️ Filtros de Planta")
    # Limpiamos nans para los filtros
    df_raw['Fábrica'] = df_raw['Fábrica'].fillna('Sin Especificar')
    df_raw['Máquina'] = df_raw['Máquina'].fillna('Sin Especificar')
    
    opciones_fabrica = sorted(df_raw['Fábrica'].unique())
    fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

    opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
    máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
        df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    else:
        st.stop()

    # 5. VISUALIZACIÓN DE VALORES OEE DETALLADOS
    st.title("🏭 Auditoría de Planta: OEE & Disponibilidad")
    
    if not df_oee_f.empty:
        # Función para extraer métricas por área
        def get_area_metrics(area_name):
            mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(area_name.upper()).any(), axis=1)
            datos = df_oee_f[mask]
            metrics = {'OEE': 0, 'DISP': 0, 'PERF': 0, 'CAL': 0}
            
            if not datos.empty:
                for key, col in zip(['OEE', 'DISP', 'PERF', 'CAL'], ['OEE', 'Disponibilidad', 'Performance', 'Calidad']):
                    # Buscamos la columna que contenga el nombre (flexibilidad por si cambia el nombre en Excel)
                    actual_col = next((c for c in datos.columns if col.lower() in c.lower()), None)
                    if actual_col:
                        val = pd.to_numeric(datos[actual_col], errors='coerce').mean()
                        metrics[key] = val / 100 if val > 1 else val
            return metrics

        # Presentación por Áreas
        areas = [('GENERAL', 'Planta Total'), ('SOLDADURA', 'Área Soldadura'), ('ESTAMPADO', 'Área Estampado')]
        
        for area_key, area_label in areas:
            st.markdown(f"### 🎯 Indicadores: {area_label}")
            m = get_area_metrics(area_key)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("OEE", f"{m['OEE']:.1%}")
            c2.metric("Disponibilidad", f"{m['DISP']:.1%}")
            c3.metric("Performance", f"{m['PERF']:.1%}")
            c4.metric("Calidad", f"{m['CAL']:.1%}")
        st.divider()

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Producción")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron registros para este intervalo.")
    else:
        # Totales
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Promedios específicos en Nivel Evento 4
        def get_avg_n4(txt):
            if 'Nivel Evento 4' in df_f.columns:
                mask = df_f['Nivel Evento 4'].str.contains(txt, case=False, na=False)
                val = df_f[mask]['Tiempo (Min)'].mean()
                return 0 if pd.isna(val) else val
            return 0

        # Mostrar Métricas principales
        c1, c2, c3 = st.columns(3)
        c1.metric("Producción Total", f"{t_prod:,.1f} min")
        c2.metric("Tiempo en Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")
        c3.metric("Eventos Registrados", len(df_f))

        # Mostrar Promedios
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{get_avg_n4('SMED'):.2f} min")
        p2.metric("Promedio Baño", f"{get_avg_n4('BAÑO'):.2f} min")
        p3.metric("Promedio Refrigerio", f"{get_avg_n4('REFRIGERIO'):.2f} min")

        st.divider()


    
    # 6. SECCIÓN DE GRÁFICOS DE REGISTROS
    if not df_f.empty:
        g1, g2 = st.columns(2)
        with g1:
            df_f['Tiempo (Min)'] = pd.to_numeric(df_f['Tiempo (Min)'], errors='coerce').fillna(0)
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
        with g2:
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Tiempos por Operador", barmode='group'), use_container_width=True)

        st.divider()

        # TOP 15 FALLAS
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        df_f6 = df_f[df_f['Nivel Evento 3'].astype(str).str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            st.plotly_chart(fig_f, use_container_width=True)

        st.divider()

        # MAPA DE CALOR (AL FINAL)
        st.subheader("🔥 Mapa de Calor: Máquinas vs Causa")
        df_hm = df_f[df_f['Evento'].astype(str).str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

except Exception as e:
    st.error(f"Error crítico: {e}")
