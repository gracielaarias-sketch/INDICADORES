import streamlit as st
import pandas as pd
import plotly.express as px
@@ -46,20 +45,19 @@ def load_data(url):

    df_f = df_f[df_f['Fábrica'].isin(fábricas) & df_f['Máquina'].isin(máquinas)]

    # 5. TÍTULO Y MÉTRICAS (PROMEDIOS Y TOTALES)
    # 5. TÍTULO Y MÉTRICAS
    st.title("🏭 Panel de Control de Producción")

    if df_f.empty:
        st.warning("⚠️ No se encontraron registros.")
        st.warning("⚠️ No se encontraron registros para los filtros seleccionados.")
    else:
        # --- CÁLCULOS ---
        # Totales
        tiempo_produccion = df_f[df_f['Evento'].str.contains('Producción', case=False, na=False)]['Tiempo (Min)'].sum()
        tiempo_fallas = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]['Tiempo (Min)'].sum()

        # Promedios (Usando Nivel Evento 4 como referencia común para estos tipos)
        def calc_prom(filtro):
            val = df_f[df_f.stack().str.contains(filtro, case=False, na=False).any(level=0)]['Tiempo (Min)'].mean()
            mask = df_f.apply(lambda row: row.astype(str).str.contains(filtro, case=False).any(), axis=1)
            val = df_f[mask]['Tiempo (Min)'].mean()
            return 0 if pd.isna(val) else val

        prom_smed = calc_prom('SMED')
@@ -82,39 +80,53 @@ def calc_prom(filtro):
        st.divider()

        # 6. SECCIÓN DE GRÁFICOS
             
        
        # DISTRIBUCIÓN Y OPERADORES
        c_left, c_right = st.columns(2)
        with c_left:
        col_izq, col_der = st.columns(2)
        with col_izq:
            st.subheader("⏱️ Distribución de Tiempo")
            st.plotly_chart(px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4), use_container_width=True)
        with c_right:
            fig_pie = px.pie(df_f, values='Tiempo (Min)', names='Evento', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_der:
            st.subheader("👤 Rendimiento por Operador")
            st.plotly_chart(px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group'), use_container_width=True)
            fig_op = px.bar(df_f, x='Operador', y='Tiempo (Min)', color='Evento', barmode='group')
            st.plotly_chart(fig_op, use_container_width=True)

        # TOP 15 FALLAS
        st.divider()

        # Identificamos columna de detalle (Nivel 6)
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]

        # --- TOP 15 FALLAS (AHORA PRIMERO) ---
        st.subheader(f"⚠️ Top 15 Fallas Detalladas ({col_6})")
        df_f6 = df_f[df_f['Nivel Evento 3'].str.contains('FALLA', case=False, na=False)]
        
        if not df_f6.empty:
            top15 = df_f6.groupby(col_6)['Tiempo (Min)'].sum().nlargest(15).reset_index()
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f = px.bar(top15, x='Tiempo (Min)', y=col_6, orientation='h', 
                           color='Tiempo (Min)', color_continuous_scale='Reds')
            fig_f.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_f, use_container_width=True)
            
       # MAPA DE CALOR
                if not df_hm.empty:
        else:
            st.info("No se detectaron fallas con detalle de Nivel 6 para el ranking.")

        st.divider()

        # --- MAPA DE CALOR (AHORA DESPUÉS DEL TOP 15) ---
        st.subheader(f"🔥 Mapa de Calor: Máquina vs Causa Raíz ({col_6})")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        
        if not df_hm.empty:
            pivot_hm = df_hm.groupby(['Máquina', col_6])['Tiempo (Min)'].sum().reset_index()
            fig_hm = px.density_heatmap(pivot_hm, x=col_6, y="Máquina", z="Tiempo (Min)",
                                        color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_hm, use_container_width=True)
        else:
            st.info("No hay eventos de parada suficientes para generar el Mapa de Calor.")

        st.subheader("🔥 Mapa de Calor: Máquina vs Causa Raíz (Nivel 6)")
        df_hm = df_f[df_f['Evento'].str.contains('Parada|Falla', case=False, na=False)]
        col_6 = 'Nivel Evento 6' if 'Nivel Evento 6' in df_f.columns else df_f.columns[5]

        # 7. TABLA DE DATOS
        with st.expander("📂 Ver registros detallados"):
            st.dataframe(df_f)

except Exception as e:
    st.error(f"Error: {e}")
    st.error(f"Error detectado: {e}")
