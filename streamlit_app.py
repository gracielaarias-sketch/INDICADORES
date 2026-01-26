import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Auditoría OEE y Producción", layout="wide")

# 2. CARGA DE DATOS ROBUSTA DESDE PANDAS
try:
    url_base = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    
    # GIDs de las pestañas
    gid_datos = "0"
    gid_oee = "1133129596" # <-- Verifica que este sea el GID de tu pestaña OEE
    
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
        
        # Limpieza inicial de nulos y strings
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).replace(['nan', 'None', 'NaN'], '').fillna('')
        return df

    df_raw = load_pandas_df(url_csv_datos)
    df_oee_raw = load_pandas_df(url_csv_oee)

    # 3. FILTROS EN LA BARRA LATERAL (RESTAURADOS)
    st.sidebar.header("📅 Rango de Auditoría")
    min_d = df_raw['Fecha_Filtro'].min().date()
    max_d = df_raw['Fecha_Filtro'].max().date()
    rango = st.sidebar.date_input("Periodo", [min_d, max_d], key="audit_range")

    st.sidebar.header("⚙️ Filtros de Planta")
    opciones_fabrica = sorted(df_raw['Fábrica'].unique())
    fábricas = st.sidebar.multiselect("Fábrica", opciones_fabrica, default=opciones_fabrica)

    opciones_maquina = sorted(df_raw[df_raw['Fábrica'].isin(fábricas)]['Máquina'].unique())
    máquinas = st.sidebar.multiselect("Máquina", opciones_maquina, default=opciones_maquina)

    # 4. APLICACIÓN DE FILTROS ROBUSTOS
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        # Filtrado para Registros
        df_f = df_raw[(df_raw['Fecha_Filtro'] >= ini) & (df_raw['Fecha_Filtro'] <= fin)]
        df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]
        
        # Filtrado para OEE (Solo por fecha para no perder los totales de Soldadura/Estampado)
        df_oee_f = df_oee_raw[(df_oee_raw['Fecha_Filtro'] >= ini) & (df_oee_raw['Fecha_Filtro'] <= fin)]
    else:
        st.stop()

    # 5. VISUALIZACIÓN DE VALORES OEE
    st.title("🏭 Auditoría de Planta: OEE y Registros")
    
    if not df_oee_f.empty:
        st.subheader("🎯 Valores OEE Directos (Hoja OEE)")
        o1, o2, o3 = st.columns(3)
        
        def get_oee_val(filtro_nombre):
            # Limpiamos el texto de la columna OEE para que sea numérico
            mask = df_oee_f.apply(lambda row: row.astype(str).str.upper().str.contains(filtro_nombre.upper()).any(), axis=1)
            datos_area = df_oee_f[mask]
            if not datos_area.empty and 'OEE' in df_oee_f.columns:
                # Convertir a número quitando % y manejando comas
                val_limpio = datos_area['OEE'].astype(str).str.replace('%', '').str.replace(',', '.')
                val = pd.to_numeric(val_limpio, errors='coerce').mean()
                return val / 100 if val > 1 else val
            return 0

        o1.metric("OEE SOLDADURA", f"{get_oee_val('SOLDADURA'):.1%}")
        o2.metric("OEE ESTAMPADO", f"{get_oee_val('ESTAMPADO'):.1%}")
        o3.metric("OEE GENERAL", f"{get_oee_val('GENERAL'):.1%}")
        st.divider()

    # 6. SECCIÓN DE GRÁFICOS DE REGISTROS (MANTENIENDO EL ORDEN)
    if not df_f.empty:
        # Fila 1: Distribución y Operadores
        g1, g2 = st.columns(2)
        with g1:
            # Asegurar que Tiempo sea numérico para el gráfico
            df_f['Tiempo (Min)'] = pd.to_numeric(df_f['Tiempo (Min)'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
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
