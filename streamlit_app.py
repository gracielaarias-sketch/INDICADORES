import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import time

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Dashboard de Producción", layout="wide")

# 2. CARGA DE DATOS ROBUSTA CON PANDAS
try:
    # Obtención de URL desde Secrets
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    url_csv = url_base.split("/edit")[0] + "/export?format=csv&gid=0"

    @st.cache_data(ttl=300)
    def load_data(url):
        # Lectura directa desde el CSV exportado por Google
        data = pd.read_csv(url)
        
        # Limpieza de columna Tiempo (Minutos)
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # NORMALIZACIÓN ROBUSTA DE FECHAS
        if 'Fecha' in data.columns:
            # Convertimos a datetime asegurando el formato día/mes/año
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            # Fecha normalizada (medianoche) para el filtro de calendario
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            # Extracción de la hora exacta para filtros de turno
            data['Hora_Solo'] = data['Fecha_DT'].dt.time
            # Texto de Hora de Inicio para la tabla detallada
            data['Hora_Inicio'] = data['Fecha_DT'].dt.strftime('%H:%M')
            
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Rango de Fechas")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()

    rango = st.sidebar.date_input("Selecciona Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

    # Filtro de Hora (Inicio y Cierre de Turno)
    st.sidebar.header("⏰ Franja Horaria")
    hora_rango = st.sidebar.slider(
        "Hora de Inicio y Cierre:",
        value=(time(0, 0), time(23, 59)),
        format="HH:mm"
    )
    h_inicio, h_fin = hora_rango

    fábricas = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    máquinas = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    df_f = df_raw.copy()
    
    # Lógica de Fechas (soporta selección de un solo día o rango)
    if isinstance(rango, (list, tuple)):
        if len(rango) == 2:
            inicio_dt, fin_dt = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
            df_f = df_f[(df_f['Fecha_Filtro'] >= inicio_dt) & (df_f['Fecha_Filtro'] <= fin_dt)]
        else:
            # Solo un día seleccionado
            inicio_dt = pd.to_datetime(rango[0])
            df_f = df_f[df_f['Fecha_Filtro'] == inicio_dt]
    
    # Filtro de Hora
    df_f = df_f[(df_f['Hora_Solo'] >= h_inicio) & (df_f['Hora_Solo'] <= h_fin)]
    
    # Filtros de Categoría
    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS PRINCIPALES
    st.title("🏭 Panel de Control de Producción")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron registros. Ajusta los filtros de fecha u hora.")
    else:
        # Totales
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Promedios corregidos
        cols_busqueda = [c for c in df_f.columns if 'Nivel Evento' in c] + ['Evento']
        def get_avg(texto):
            mask = df_f[cols_busqueda].apply(lambda x: x.str.contains(texto, case=False, na=False)).any(axis=1)
            mean_val = df_f[mask]['Tiempo (Min)'].mean()
            return 0 if pd.isna(mean_val) else mean_val

        st.subheader("🚀 Totales y Rendimiento")
        c1, c2, c3 = st.columns(3)
        c1.metric("Registros Filtrados", len(df_f))
        c2.metric("Producción Total", f"{t_prod:,.1f} min")
        c3.metric("Tiempo en Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")

        st.subheader("⏱️ Promedios por Actividad")
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{get_avg('SMED'):.2f} min")
        p2.metric("Promedio Baño", f"{get_avg('BAÑO'):.2f} min")
        p3.metric("Promedio Refrigerio", f"{get_avg('REFRIGERIO'):.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with g2:
            st.subheader("👤 Rendimiento por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # Identificación de columna 6
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]

        # --- TOP 15 FALLAS ---
        st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
        df_fallas_det = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_fallas_det.empty:
            top15 = df_fallas_det.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_bar = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # --- MAPA DE CALOR ---
        st.subheader(f"🔥 Mapa de Calor: Máquina vs {col_6}")
        df_heatmap = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_heatmap.empty:
            pivot_hm = df_heatmap.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        # 7. TABLA DE DATOS (Muestra Hora de Inicio si es un solo día)
        with st.expander("📂 Ver registros detallados"):
            if len(rango) == 1 or (len(rango) == 2 and rango[0] == rango[1]):
                # Priorizamos ver la hora si es un solo día seleccionado
                cols_v = ['Hora_Inicio', 'Operador', 'Evento', 'Máquina', 'Tiempo (Min)', col_6]
                st.dataframe(df_f[[c for c in cols_v if c in df_f.columns]])
            else:
                st.dataframe(df_f)

except Exception as e:
    st.error(f"Error crítico: {e}")
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
        
        # Limpieza de columna Tiempo (Min)
        if 'Tiempo (Min)' in data.columns:
            data['Tiempo (Min)'] = data['Tiempo (Min)'].astype(str).str.replace(',', '.')
            data['Tiempo (Min)'] = pd.to_numeric(data['Tiempo (Min)'], errors='coerce').fillna(0)
        
        # BLOQUE DE FECHA ROBUSTO: Unificación de formatos
        if 'Fecha' in data.columns:
            # Convertir a datetime ignorando errores y forzando formato día-primero
            data['Fecha_DT'] = pd.to_datetime(data['Fecha'], dayfirst=True, errors='coerce')
            # Normalizar para filtro de calendario (quita horas/minutos)
            data['Fecha_Filtro'] = data['Fecha_DT'].dt.normalize()
            # Extraer hora para filtros de turno
            data['Hora_Solo'] = data['Fecha_DT'].dt.time
            # Formato de hora para visualización en tabla
            data['Hora_Inicio'] = data['Fecha_DT'].dt.strftime('%H:%M')
            
        # Limpieza de nulos en columnas de texto para evitar error .str accessor
        cols_texto = ['Operador', 'Evento', 'Máquina', 'Nivel Evento 3', 'Nivel Evento 6']
        for col in cols_texto:
            if col in data.columns:
                data[col] = data[col].astype(str).replace('nan', '').fillna('')
        
        return data.dropna(subset=['Operador', 'Evento'])

    df_raw = load_data(url_csv)

    # 3. FILTROS EN LA BARRA LATERAL
    st.sidebar.header("📅 Rango de Fechas")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Selecciona Periodo", [min_d, max_d], min_value=min_d, max_value=max_d)

    # Detección de día único
    es_un_solo_dia = False
    if isinstance(rango, (list, tuple)):
        if len(rango) == 2:
            inicio_f, fin_f = rango[0], rango[1]
            if inicio_f == fin_f: es_un_solo_dia = True
        else:
            inicio_f = fin_f = rango[0]
            es_un_solo_dia = True
    else:
        inicio_f = fin_f = rango
        es_un_solo_dia = True

    st.sidebar.header("⏰ Horario de Turno")
    h_rango = st.sidebar.slider("Inicio y Cierre:", value=(time(0, 0), time(23, 59)), format="HH:mm")
    h_ini, h_fin = h_rango

    fab = st.sidebar.multiselect("Fábrica", df_raw['Fábrica'].unique(), default=df_raw['Fábrica'].unique())
    maq = st.sidebar.multiselect("Máquina", df_raw['Máquina'].unique(), default=df_raw['Máquina'].unique())

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    df_f = df_raw.copy()
    
    # Filtro de fecha usando comparación Datetime de Pandas
    df_f = df_f[(df_f['Fecha_Filtro'] >= pd.to_datetime(inicio_f)) & 
                (df_f['Fecha_Filtro'] <= pd.to_datetime(fin_f))]
    
    # Filtro de hora
    df_f = df_f[(df_f['Hora_Solo'] >= h_ini) & (df_f['Hora_Solo'] <= h_fin)]
    
    # Filtros de texto
    df_f = df_f[df_f['Fábrica'].isin(fab) & df_f['Máquina'].isin(maq)]

    # 5. TÍTULO Y MÉTRICAS
    txt_periodo = f"Día: {inicio_f}" if es_un_solo_dia else f"Periodo: {inicio_f} al {fin_f}"
    st.title(f"🏭 Panel de Control: {txt_periodo}")
    
    if df_f.empty:
        st.warning("⚠️ No se encontraron datos para los filtros seleccionados.")
    else:
        # Cálculos de Totales
        t_prod = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        t_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()
        
        # Función de promedios corregida para que no se crucen (búsqueda específica)
        def get_avg(txt):
            mask = df_f['Nivel Evento 4'].str.contains(txt, case=False, na=False) if 'Nivel Evento 4' in df_f.columns else df_f['Evento'].str.contains(txt, case=False, na=False)
            val = df_f[mask]['Tiempo (Min)'].mean()
            return 0 if pd.isna(val) else val

        st.subheader("🚀 Indicadores de Eficiencia")
        c1, c2, c3 = st.columns(3)
        c1.metric("Eventos Totales", len(df_f))
        c2.metric("Producción Total", f"{t_prod:,.1f} min")
        c3.metric("Tiempo Fallas", f"{t_fallas:,.1f} min", delta_color="inverse")

        st.subheader("⏱️ Promedios por Categoría")
        p1, p2, p3 = st.columns(3)
        p1.metric("Promedio SMED", f"{get_avg('SMED'):.2f} min")
        p2.metric("Promedio Baño", f"{get_avg('BAÑO'):.2f} min")
        p3.metric("Promedio Refrigerio", f"{get_avg('REFRIGERIO'):.2f} min")

        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with g2:
            st.subheader("👤 Tiempo por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)

        st.divider()

        # TOP 15 FALLAS (Nivel 6)
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]
        st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        if not df_f6.empty:
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)

        st.divider()

        # MAPA DE CALOR
        st.subheader(f"🔥 Mapa de Calor: Máquina vs {col_6}")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)", color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)

        # 7. TABLA DE REGISTROS (Condicional según día único)
        with st.expander("📂 Ver registros detallados"):
            if es_un_solo_dia:
                # Mostrar columna de Hora de Inicio primero para análisis secuencial
                cols_ord = ['Hora_Inicio', 'Operador', 'Evento', 'Máquina', 'Tiempo (Min)', col_6]
                st.dataframe(df_f[[c for c in cols_ord if c in df_f.columns]])
            else:
                st.dataframe(df_f)

except Exception as e:
    st.error(f"Error crítico de aplicación: {e}")
