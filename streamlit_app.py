import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS ROBUSTA CON PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

    @st.cache_data(ttl=300)
    def load_data(url):
        # Lectura directa desde Pandas
        data = pd.read_csv(url)
        
        # Limpieza de columna Tiempo
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # --- BLOQUE DE FECHA ROBUSTA ---
        if 'Fecha' in data.columns:
            # Convertimos a datetime y normalizamos (eliminamos horas/minutos ocultos)
            data['Fecha'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce').dt.normalize()
        
        # Limpieza de textos para evitar errores en filtros .str
        cols_texto = ['Operador', 'Evento', 'Fábrica', 'Máquina', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6']
        for col in cols_texto:
            if col in data.columns:
                data[col] = data[col].astype(str).replace('nan', '').fillna('')
            
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    min_d = df_raw['Fecha'].min().date()
    max_d = df_raw['Fecha'].max().date()

    rango = st.sidebar.date_input("Rango de fechas", [min_d, max_d], min_value=min_d, max_value=max_d)
    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    df_f = df_raw.copy()
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        # Convertimos el rango del widget al formato Timestamp de Pandas
        inicio, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_f[(df_f['Fecha'] >= inicio) & (df_f['Fecha'] <= fin)]
    elif len(rango) == 1:
        st.info("💡 Selecciona la fecha final en el calendario.")
        st.stop()
    
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Producción")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron registros para los filtros seleccionados.")
    else:
        # --- CÁLCULOS DE TOTALES ---
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_falla = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # --- CÁLCULO DE PROMEDIOS CORREGIDO ---
        # Filtramos por el nombre de la columna para evitar que Baño y Refrigerio se mezclen
        def calc_prom_seguro(termino):
            # Buscamos el término específicamente en las columnas de detalle de evento
            mask = df_f.apply(lambda row: row.astype(str).str.upper().str.contains(termino).any(), axis=1)
            df_sub = df_f[mask]
            return df_sub['Tiempo (Min)'].mean() if not df_sub.empty else 0

        prom_smed = calc_prom_seguro('SMED')
        prom_baño = calc_prom_seguro('BAÑO')
        prom_refrigerio = calc_prom_seguro('REFRIGERIO')

        # --- MOSTRAR MÉTRICAS ---
        st.subheader("🚀 Indicadores Generales")
        c1, c2, c3 = st.columns(3)
        c1.metric("Registros", f"{len(df_f)}")
        c2.metric("Producción Total", f"{t_prod:,.1f} min")
        c3.metric("Tiempo en Fallas", f"{t_falla:,.1f} min", delta_color="inverse")

        st.subheader("⏱️ Promedios Operativos")
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{prom_smed:.2f} min")
        p2.metric("Promedio Baño", f"{prom_baño:.2f} min")
        p3.metric("Promedio Refrigerio", f"{prom_refrigerio:.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
        
        # Distribución y Operadores
        col_izq, col_der = st.columns(2)
        with col_izq:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with col_der:
            st.subheader("👤 Tiempos por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # Identificación de columna 6
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]

        # TOP 15 FALLAS
        st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)
        else:
            st.info("No se encontraron fallas detalladas.")

        st.divider()

        # MAPA DE CALOR (AL FINAL)
        st.subheader(f"🔥 Mapa de Calor: Máquina vs {col_6}")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        with st.expander("📂 Ver registros detallados"):
            st.dataframe(df_f)

except Exception as e:
    st.error(f"Error crítico: {e}")
