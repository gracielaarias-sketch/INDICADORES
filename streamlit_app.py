import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard Producción & OEE", layout="wide")

# 2. CARGA DE DATOS ROBUSTA CON PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # GIDs de las pestañas
    gid_datos = "0"
    gid_oee = "1767654796"  # <-- ASEGÚRATE DE QUE ESTE GID SEA EL CORRECTO
    
    url_csv_datos = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_datos}"
    url_csv_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

    @st.cache_data(ttl=300)
    def load_pandas_df(url, is_oee=False):
        try:
            df = pd.read_csv(url)
            
            # Limpieza de Tiempo (Solo para hoja de datos)
            if 'Tiempo (Min)' in df.columns:
                df['Tiempo (Min)'] = df['Tiempo (Min)'].astype(str).str.replace(',', '.')
                df['Tiempo (Min)'] = pd.to_numeric(df['Tiempo (Min)'], errors='coerce').fillna(0)
            
            # NORMALIZACIÓN DE FECHA ROBUSTA
            # Buscamos 'Fecha' o 'FECHA'
            col_fecha = next((c for c in df.columns if c.lower() == 'fecha'), None)
            
            if col_fecha:
                df['Fecha_DT'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
                df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
            else:
                # Si no hay fecha, creamos la columna vacía para evitar el Error Crítico
                df['Fecha_Filtro'] = pd.NaT
            
            # Limpieza de textos
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].astype(str).replace(['nan', 'None'], '').fillna('')
            return df
        except:
            return pd.DataFrame()

    df_raw = load_pandas_df(url_csv_datos)
    df_oee_raw = load_pandas_df(url_csv_oee, is_oee=True)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Rango de Análisis")
    
    # Validamos que df_raw tenga datos
    if df_raw.empty or 'Fecha_Filtro' not in df_raw.columns:
        st.error("La hoja principal no tiene columna 'Fecha' o está vacía.")
        st.stop()

    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Intervalo de tiempo", [min_d, max_d], key="filtro_global")

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        
        # Filtro hoja Datos
        df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
        
        # Filtro hoja OEE (Solo si tiene la columna y no está vacía)
        if not df_oee_raw.empty and 'Fecha_Filtro' in df_oee_raw.columns:
            df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
        else:
            df_oee_f = pd.DataFrame()
    else:
        st.stop()
    
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS OEE
    st.title("🏭 Panel de Control de Producción y OEE")
    
    if not df_oee_f.empty:
        st.subheader("🎯 Indicadores de Eficiencia (OEE)")
        o1, o2, o3, o4 = st.columns(4)
        
        def get_oee_metric(col_name):
            # Buscar columna ignorando mayúsculas
            actual_col = next((c for c in df_oee_f.columns if c.lower() == col_name.lower()), None)
            if actual_col:
                val = pd.to_numeric(df_oee_f[actual_col].astype(str).str.replace('%',''), errors='coerce').mean()
                return val / 100 if val > 1 else val
            return 0

        o1.metric("OEE", f"{get_oee_metric('OEE'):.1%}")
        o2.metric("Disponibilidad", f"{get_oee_metric('Disponibilidad'):.1%}")
        o3.metric("Rendimiento", f"{get_oee_metric('Rendimiento'):.1%}")
        o4.metric("Calidad", f"{get_oee_metric('Calidad'):.1%}")
        st.divider()
    else:
        st.info("ℹ️ No se encontraron datos de OEE para este rango o el GID es incorrecto.")

    # 6. MÉTRICAS OPERATIVAS
    if not df_f.empty:
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()

        def get_avg_n4(txt):
            col_n4 = next((c for c in df_f.columns if 'Nivel Evento 4' in c), None)
            if col_n4:
                mask = df_f[col_n4].str.contains(txt, case=False, na=False)
                val = df_f[mask]['Tiempo (Min)'].mean()
                return 0 if pd.isna(val) else val
            return 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Producción Total", f"{t_prod:,.1f} min")
        c2.metric("Tiempo Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")
        c3.metric("Promedio SMED", f"{get_avg_n4('SMED'):.2f} min")

        st.divider()

        # 7. GRÁFICOS (ORDEN SOLICITADO)
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with g2:
            st.subheader("👤 Rendimiento por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # TOP 15 FALLAS
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            st.plotly_chart(px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds'), use_container_width=True)

        st.divider()

        # MAPA DE CALOR (AL FINAL)
        st.subheader("🔥 Mapa de Calor: Máquinas vs Causa")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

except Exception as e:
    st.error(f"Error crítico: {e}")
