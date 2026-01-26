import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard Integral de Producción", layout="wide")

# 2. CARGA DE DATOS ROBUSTA (HOJA PRINCIPAL Y HOJA OEE)
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # GID 0: Hoja de registros / GID OEE: Reemplaza con el de tu pestaña OEE
    gid_datos = "0"
    gid_oee = "1133129596"  # <--- CAMBIA ESTE NÚMERO POR EL GID DE TU PESTAÑA OEE
    
    url_csv_datos = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_datos}"
    url_csv_oee = url_base.split("/edit")[0] + f"/export?format=csv&gid={gid_oee}"

    @st.cache_data(ttl=300)
    def load_pandas_df(url):
        df = pd.read_csv(url)
        # Limpieza de Tiempo
        if 'Tiempo (Min)' in df.columns:
            df['Tiempo (Min)'] = df['Tiempo (Min)'].astype(str).str.replace(',', '.')
            df['Tiempo (Min)'] = pd.to_numeric(df['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # NORMALIZACIÓN DE FECHA ROBUSTA
        if 'Fecha' in df.columns:
            df['Fecha_DT'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce')
            df['Fecha_Filtro'] = df['Fecha_DT'].dt.normalize()
        
        # Limpieza de textos contra errores .str accessor
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).replace(['nan', 'None'], '').fillna('')
            
        return df

    df_raw = load_pandas_df(url_csv_datos)
    df_oee_raw = load_pandas_df(url_csv_oee)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Rango de Análisis")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    
    rango = st.sidebar.date_input("Intervalo de tiempo", [min_d, max_d], key="filtro_global")

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    else:
        st.stop()
    
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS OEE (Pestaña OEE)
    st.title("🏭 Panel de Control de Producción y OEE")
    
    if not df_oee_f.empty:
        st.subheader("🎯 Indicadores de Eficiencia (OEE)")
        o1, o2, o3, o4 = st.columns(4)
        
        # Función para obtener promedios de OEE de forma segura
        def get_oee_metric(col_name):
            if col_name in df_oee_f.columns:
                val = pd.to_numeric(df_oee_f[col_name].astype(str).str.replace('%',''), errors='coerce').mean()
                return val / 100 if val > 1 else val
            return 0

        o1.metric("OEE", f"{get_oee_metric('OEE'):.1%}")
        o2.metric("Disponibilidad", f"{get_oee_metric('Disponibilidad'):.1%}")
        o3.metric("Rendimiento", f"{get_oee_metric('Rendimiento'):.1%}")
        o4.metric("Calidad", f"{get_oee_metric('Calidad'):.1%}")
        st.divider()

    # 6. MÉTRICAS OPERATIVAS (Pestaña Principal)
    if not df_f.empty:
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()

        def get_avg_n4(txt):
            if 'Nivel Evento 4' in df_f.columns:
                mask = df_f['Nivel Evento 4'].str.contains(txt, case=False, na=False)
                val = df_f[mask]['Tiempo (Min)'].mean()
                return 0 if pd.isna(val) else val
            return 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Producción Total", f"{t_prod:,.1f} min")
        c2.metric("Tiempo Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")
        c3.metric("Promedio SMED", f"{get_avg_n4('SMED'):.2f} min")

        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio Baño", f"{get_avg_n4('BAÑO'):.2f} min")
        p2.metric("Promedio Refrigerio", f"{get_avg_n4('REFRIGERIO'):.2f} min")
        p3.metric("Total Eventos", len(df_f))

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
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)

        st.divider()

        # MAPA DE CALOR (AL FINAL)
        st.subheader("🔥 Mapa de Calor: Máquinas vs Causa")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        with st.expander("📂 Ver registros detallados"):
            st.dataframe(df_f.sort_values(by='Fecha_DT'))

except Exception as e:
    st.error(f"Error crítico: {e}")
