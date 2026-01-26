import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción y OEE", layout="wide")

# 2. CARGA DE DATOS ROBUSTA (Doble Hoja: Datos y OEE)
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # URL para la hoja principal (gid=0)
    url_datos = url_base.split("/edit")[0] + "/export?format=csv&gid=0"
    
    # URL para la hoja OEE (Debes verificar el GID de tu pestaña OEE. Normalmente si es la segunda es un número distinto)
    # Por defecto probamos con gid=12345678 (cambia este número por el gid que ves en la URL de tu navegador al abrir esa pestaña)
    # Si no conoces el GID, puedes probar cargar por nombre si usas librerías como gspread, 
    # pero aquí mantenemos la carga rápida por CSV.
    gid_oee = "1767654796" # Reemplaza con el ID de la pestaña OEE
    url_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

    @st.cache_data(ttl=300)
    def load_data(url):
        data = pd.read_csv(url)
        # Limpieza de columna Tiempo
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # Bloque de Fecha
        if 'Fecha' in data.columns:
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            
        # Limpieza de texto
        for col in data.select_dtypes(include=['object']).columns:
            data[col] = data[col].astype(str).replace(['nan', 'None'], '').fillna('')
            
        return data

    df_raw = load_data(url_datos)
    
    # Intentamos cargar OEE (si el GID es correcto)
    try:
        df_oee_raw = pd.read_csv(url_oee)
        if 'Fecha' in df_oee_raw.columns:
            df_oee_raw['Fecha_Filtro'] = pd.to_datetime(df_oee_raw['Fecha'], dayfirst=True, errors='coerce').dt.normalize()
    except:
        df_oee_raw = pd.DataFrame()

    # 3. FILTROS
    st.sidebar.header("📅 Filtros de Análisis")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Selecciona Intervalo", [min_d, max_d], min_value=min_d, max_value=max_d)

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        inicio, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_raw[(df_raw['Fecha_Filtro'] >= inicio) & (df_raw['Fecha_Filtro'] <= fin)]
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= inicio) & (df_oee_raw['Fecha_Filtro'] <= fin)] if not df_oee_raw.empty else pd.DataFrame()
    else:
        st.stop()
    
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS DE OEE
    st.title("🏭 Dashboard de Producción y Eficiencia (OEE)")
    
    if not df_oee_f.empty:
        st.subheader("🎯 Indicadores de Eficiencia Global")
        # Asumiendo que las columnas en tu hoja OEE se llaman así:
        oee_medio = df_oee_f['OEE'].mean() if 'OEE' in df_oee_f.columns else 0
        disp_media = df_oee_f['Disponibilidad'].mean() if 'Disponibilidad' in df_oee_f.columns else 0
        perf_media = df_oee_f['Rendimiento'].mean() if 'Rendimiento' in df_oee_f.columns else 0
        cal_media = df_oee_f['Calidad'].mean() if 'Calidad' in df_oee_f.columns else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("OEE Promedio", f"{oee_medio:.1%}")
        m2.metric("Disponibilidad", f"{disp_media:.1%}")
        m3.metric("Rendimiento", f"{perf_media:.1%}")
        m4.metric("Calidad", f"{cal_media:.1%}")
        st.divider()

    # 6. MÉTRICAS OPERATIVAS (CÓDIGO ANTERIOR)
    if not df_f.empty:
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()

        def get_avg_n4(txt):
            mask = df_f['Nivel Evento 4'].str.contains(txt, case=False, na=False) if 'Nivel Evento 4' in df_f.columns else [False]*len(df_f)
            return df_f[mask]['Tiempo (Min)'].mean() if any(mask) else 0

        st.subheader("🚀 Resumen Operativo")
        c1, c2, c3 = st.columns(3)
        c1.metric("Producción Total", f"{t_prod:,.1f} min")
        c2.metric("Tiempo Fallas", f"{t_fallas:,.1f} min")
        c3.metric("Promedio SMED", f"{get_avg_n4('SMED'):.2f} min")

        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio Baño", f"{get_avg_n4('BAÑO'):.2f} min")
        p2.metric("Promedio Refrigerio", f"{get_avg_n4('REFRIGERIO'):.2f} min")
        p3.metric("Eventos", len(df_f))

        st.divider()

        # 7. GRÁFICOS (ORDEN SOLICITADO)
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempo", hole=0.4), use_container_width=True)
        with g2:
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Rendimiento Operador", barmode='group'), use_container_width=True)

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
        st.subheader("🔥 Mapa de Calor: Máquina vs Causa")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            st.plotly_chart(px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True), use_container_width=True)

except Exception as e:
    st.error(f"Error crítico: {e}")
