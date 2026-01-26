import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS ROBUSTA DESDE PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

    @st.cache_data(ttl=300)
    def load_data(url):
        data = pd.read_csv(url)
        # Limpieza de columna Tiempo
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # BLOQUE DE FECHA ROBUSTO
        if 'Fecha' in data.columns:
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            data['Hora_Txt'] = data['Fecha_DT'].dt.strftime('%H:%M')
            
        # Limpieza de texto contra error .str accessor
        cols_texto = ['Operador', 'Evento', 'Máquina', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6']
        for col in cols_texto:
            if col in data.columns:
                data[col] = data[col].astype(str).replace(['nan', 'None', 'NaN'], '').fillna('')
        
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    fecha_sel = st.sidebar.date_input("Selecciona el día", min_d, key="cal_prod")

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS
    df_f = df_raw.copy()
    df_f = df_f[df_f['Fecha_Filtro'] == pd.to_datetime(fecha_sel)]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title(f"🏭 Panel de Control de Producción")
    st.subheader(f"📊 Reporte del día: {fecha_sel}")

    if not df_f.empty:
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
        c3.metric("Eventos Totales", len(df_f))

        # Mostrar Promedios
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{get_avg_n4('SMED'):.2f} min")
        p2.metric("Promedio Baño", f"{get_avg_n4('BAÑO'):.2f} min")
        p3.metric("Promedio Refrigerio", f"{get_avg_n4('REFRIGERIO'):.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
        
        # Fila 1: Distribución y Operadores
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with g2:
            st.subheader("👤 Rendimiento por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # Fila 2: Top 15 Fallas
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)

        st.divider()

        # Fila 3: Mapa de Calor (Al final)
        st.subheader("🔥 Mapa de Calor: Máquinas vs Causa")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        # 7. TABLA DE REGISTROS
        with st.expander("📂 Ver registros detallados"):
            df_display = df_f.sort_values(by='Fecha_DT')
            cols_v = ['Hora_Txt', 'Operador', 'Evento', 'Máquina', 'Tiempo (Min)', 'Nivel Evento 4', col_6]
            st.dataframe(df_display[[c for c in cols_v if c in df_display.columns]], use_container_width=True)
    else:
        st.warning("No hay datos registrados para este día.")

except Exception as e:
    st.error(f"Error crítico: {e}")
