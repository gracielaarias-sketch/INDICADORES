import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import time

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS ROBUSTA DESDE PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

    @st.cache_data(ttl=300)
    def load_data(url):
        # Lectura directa
        data = pd.read_csv(url)
        
        # Limpieza de columna Tiempo (Minutos)
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # BLOQUE DE FECHA ROBUSTO: Sincronización total
        if 'Fecha' in data.columns:
            # Forzamos conversión a datetime (Día/Mes/Año)
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            # Normalizamos (medianoche) para que el filtro por día sea exacto
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            # Extraemos la hora para comparación y visualización
            data['Hora_Solo'] = data['Fecha_DT'].dt.time
            data['Hora_Inicio_Txt'] = data['Fecha_DT'].dt.strftime('%H:%M')
            
        # LIMPIEZA DE TEXTO PARA EVITAR ERROR .STR ACCESSOR
        cols_texto = ['Operador', 'Evento', 'Máquina', 'Nivel Evento 3', 'Nivel Evento 4', 'Nivel Evento 6']
        for col in cols_texto:
            if col in data.columns:
                data[col] = data[col].astype(str).replace(['nan', 'None', 'NaN'], '').fillna('')
        
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Filtros de Tiempo")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    
    rango = st.sidebar.date_input("Selecciona Periodo", [min_d, max_d], min_value=min_d, max_value=max_d, key="cal_final")

    # Determinar si es un solo día
    es_un_solo_dia = False
    if isinstance(rango, (list, tuple)):
        inicio_f = rango[0]
        fin_f = rango[1] if len(rango) > 1 else inicio_f
        if inicio_f == fin_f: es_un_solo_dia = True
    else:
        inicio_f = fin_f = rango
        es_un_solo_dia = True

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS
    df_f = df_raw.copy()
    df_f = df_f[(df_f['Fecha_Filtro'] >= pd.to_datetime(inicio_f)) & (df_f['Fecha_Filtro'] <= pd.to_datetime(fin_f))]
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS DE AUDITORÍA
    st.title("🏭 Panel de Control de Producción")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron registros con los filtros actuales.")
    else:
        # Cálculo de horas reales detectadas
        h_primera = df_f['Fecha_DT'].min().strftime('%H:%M')
        h_ultima = df_f['Fecha_DT'].max().strftime('%H:%M')
        
        st.info(f"🕒 **Actividad en Planta:** Primer registro a las **{h_primera}** | Último registro a las **{h_ultima}**")

        # Métricas de Totales
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Eventos Totales", len(df_f))
        c2.metric("Total Producción", f"{t_prod:,.1f} min")
        c3.metric("Tiempo Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")

        # Promedios corregidos para Baño y Refrigerio
        def get_avg_estricto(txt):
            mask = df_f.apply(lambda row: row.astype(str).str.upper().str.contains(txt).any(), axis=1)
            df_sub = df_f[mask]
            return df_sub['Tiempo (Min)'].mean() if not df_sub.empty else 0

        st.subheader("⏱️ Promedios por Categoría")
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{get_avg_estricto('SMED'):.2f} min")
        p2.metric("Promedio Baño", f"{get_avg_estricto('BAÑO'):.2f} min")
        p3.metric("Promedio Refrigerio", f"{get_avg_estricto('REFRIGERIO'):.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', title="Distribución de Tiempos", hole=0.4), use_container_width=True)
        with g2:
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', title="Rendimiento por Operador", barmode='group'), use_container_width=True)

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

        # --- MAPA DE CALOR (AL FINAL) ---
        st.subheader(f"🔥 Mapa de Calor: Máquina vs {col_6}")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        # 7. TABLA DE REGISTROS
        with st.expander("📂 Ver registros detallados"):
            if es_un_solo_dia:
                cols_v = ['Hora_Inicio_Txt', 'Operador', 'Evento', 'Máquina', 'Tiempo (Min)', col_6]
                st.dataframe(df_f[[c for c in cols_v if c in df_f.columns]])
            else:
                st.dataframe(df_f)

except Exception as e:
    st.error(f"Error crítico: {e}")
    
