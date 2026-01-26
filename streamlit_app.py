¡Tienes razón! Al reorganizar los gráficos, se nos quedaron fuera esas métricas clave en la parte superior. He reintegrado los promedios específicos (SMED, Baño, Refrigerio) y los totales de producción y fallas, asegurando que todos se calculen dinámicamente sobre el DataFrame filtrado (df_f).

Aquí tienes el código completo y corregido:

Python

import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS DESDE PANDAS
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
        
        # BLOQUE DE FECHAS ROBUSTO
        if 'Fecha' in data.columns:
            data['Fecha'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce').dt.normalize()
        
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Análisis")
    min_d = df_raw['Fecha'].min().date()
    max_d = df_raw['Fecha'].max().date()

    rango = st.sidebar.date_input("Rango de fechas", [min_d, max_d], min_value=min_d, max_value=max_d)
    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS
    df_f = df_raw.copy()
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        inicio, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        df_f = df_f[(df_f['Fecha'] >= inicio) & (df_f['Fecha'] <= fin)]
    elif len(rango) == 1:
        st.stop()
    
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS (PROMEDIOS Y TOTALES)
    st.title("🏭 Panel de Control de Producción")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron registros.")
    else:
        # --- CÁLCULOS ---
        # Totales
        tiempo_produccion = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        tiempo_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Promedios (Usando Nivel Evento 4 como referencia común para estos tipos)
        def calc_prom(filtro):
            val = df_f[df_f.stack().str.contains(filtro, case=False, na=False).any(level=0)]['Tiempo (Min)'].mean()
            return 0 if pd.isna(val) else val

        prom_smed = calc_prom('SMED')
        prom_baño = calc_prom('BAÑO')
        prom_refrigerio = calc_prom('REFRIGERIO')

        # --- MOSTRAR MÉTRICAS ---
        st.subheader("🚀 Totales de Tiempo")
        c1, c2, c3 = st.columns(3)
        c1.metric("Eventos Totales", f"{len(df_f)}")
        c2.metric("Total Producción", f"{tiempo_produccion:,.1f} min")
        c3.metric("Total Tiempo Fallas", f"{tiempo_fallas:,.1f} min", delta_color="inverse")

        st.subheader("⏱️ Promedios de Tiempos No Productivos")
        m1, m2, m3 = st.columns(3)
        m1.metric("Promedio SMED", f"{prom_smed:.2f} min")
        m2.metric("Promedio Baño", f"{prom_baño:.2f} min")
        m3.metric("Promedio Refrigerio", f"{prom_refrigerio:.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
             
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)",
                                        color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        # DISTRIBUCIÓN Y OPERADORES
        c_left, c_right = st.columns(2)
        with c_left:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with c_right:
            st.subheader("👤 Rendimiento por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        # TOP 15 FALLAS
        st.divider()
        st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)
            
       # MAPA DE CALOR
        st.subheader("🔥 Mapa de Calor: Máquina vs Causa Raíz (Nivel 6)")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]

        with st.expander("📂 Ver registros detallados"):
            st.dataframe(df_f)

except Exception as e:
    st.error(f"Error: {e}")
