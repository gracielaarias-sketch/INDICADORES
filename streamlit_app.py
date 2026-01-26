Aquí tienes el código definitivo. He eliminado los selectores manuales de hora y el slider de la barra lateral para que el sistema trabaje por ti: ahora detecta automáticamente la hora exacta del primer y último registro basándose en tus filtros de fecha, fábrica o máquina.

Se mantiene la carga robusta con Pandas, la normalización de fechas y el orden jerárquico de los gráficos.

Python

import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Auditoría de Producción", layout="wide")

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
            # Forzamos conversión a datetime (Día/Mes/Año)
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            # Normalizamos (medianoche) para el filtro de calendario
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            # Texto de hora para visualización
            data['Hora_Txt'] = data['Fecha_DT'].dt.strftime('%H:%M')
            
        # LIMPIEZA DE TEXTO PARA EVITAR ERROR .STR ACCESSOR
        cols_texto = ['Operador', 'Evento', 'Máquina', 'Nivel Evento 3', 'Nivel Evento 6']
        for col in cols_texto:
            if col in data.columns:
                data[col] = data[col].astype(str).replace(['nan', 'None', 'NaN'], '').fillna('')
        
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL (SIN SLIDERS)
    st.sidebar.header("📅 Filtros de Auditoría")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    
    # Filtro de calendario robusto
    fecha_sel = st.sidebar.date_input("Selecciona el día", min_d, min_value=min_d, max_value=max_d, key="cal_audit")

    fab = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    maq = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS
    df_f = df_raw.copy()
    # Filtro por el día seleccionado (normalizado)
    df_f = df_f[df_f['Fecha_Filtro'] == pd.to_datetime(fecha_sel)]
    df_f = df_f[df_f['Fábrica'].isin(fab) & df_f['Máquina'].isin(maq)]

    # 5. PANEL DE AUDITORÍA AUTOMÁTICA
    st.title(f"🏭 Auditoría de Actividad")
    st.subheader(f"📅 Fecha: {fecha_sel}")

    if not df_f.empty:
        # --- CÁLCULO AUTOMÁTICO DE INICIO Y FIN REAL ---
        hora_apertura = df_f['Fecha_DT'].min().strftime('%H:%M')
        hora_cierre = df_f['Fecha_DT'].max().strftime('%H:%M')

        # Visualización de Horarios Reales en recuadros
        st.markdown("### ⏱️ Cronología Detectada")
        col_cron1, col_cron2 = st.columns(2)
        col_cron1.metric("Hora Primer Registro", hora_apertura)
        col_cron2.metric("Hora Último Registro", hora_cierre)
        
        st.divider()

        # 6. MÉTRICAS GENERALES
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Eventos Totales", len(df_f))
        m2.metric("Total Producción", f"{t_prod:,.1f} min")
        m3.metric("Tiempo en Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")

        # 7. SECCIÓN DE GRÁFICOS (ORDEN SOLICITADO)
        
        # Rendimiento por Operador
        st.subheader("👤 Rendimiento por Operador")
        st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # TOP 15 FALLAS (Nivel 6)
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            st.subheader(f"⚠️ Top 15 Fallas ({col_6})")
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)

        st.divider()

        # MAPA DE CALOR
        st.subheader("🔥 Mapa de Calor: Máquinas vs Causa")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        # 8. TABLA DE REGISTROS (Ordenada Cronológicamente)
        with st.expander("📂 Ver bitácora detallada del día"):
            df_display = df_f.sort_values(by='Fecha_DT')
            cols_v = ['Hora_Txt', 'Operador', 'Evento', 'Máquina', 'Tiempo (Min)', col_6]
            st.dataframe(df_display[[c for c in cols_v if c in df_display.columns]], use_container_width=True)
    else:
        st.warning("⚠️ No se detectó actividad para los filtros seleccionados en este día.")

except Exception as e:
    st.error(f"Error crítico: {e}")
¿Por qué este diseño es superior para tu necesidad?
Auditoría Real: Al calcular el mínimo y máximo de la columna Fecha_DT, el sistema te muestra el horario real de trabajo, no el horario teórico. Si alguien empezó a registrar tarde, lo verás reflejado en la métrica "Hora Primer Registro".

Filtro por Máquina: Si seleccionas una sola máquina en la barra lateral, los cuadros de Inicio y Cierre te dirán exactamente a qué hora empezó y terminó esa máquina específica.

Tabla Cronológica: He añadido un sort_values en la tabla detallada para que puedas leer los eventos en orden, como si fuera una línea de tiempo del día.

Robustez de Fechas: Se mantiene el uso de normalize() para asegurar que el día seleccionado en el calendario siempre encuentre los datos en el DataFrame, sin importar el formato interno del archivo.
