# =====================================================================
# 3. GESTIONAR ESTUDIANTES Y GENERAR PDF - Optimizado para Celular
# =====================================================================
elif menu == "3. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Gestionar Estudiantes y Generar PDF")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if df_cursos.empty:
        st.warning("Agrega cursos primero en la opción 2")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in seleccion.split(" - ")]

        st.subheader("📁 Subir lista de estudiantes")
        
        st.markdown("""
        <div style='background:#FFF3CD; padding:15px; border-radius:10px; border:2px solid #FFC107;'>
        📱 <strong>Consejos para subir archivo desde celular (Samsung/Android):</strong><br><br>
        • Usa <strong>Chrome</strong> o <strong>Google</strong><br>
        • Toca "Examinar" y selecciona el archivo <strong>rápidamente</strong><br>
        • El archivo debe estar guardado en tu celular (no en Drive)<br>
        • Formatos aceptados: <strong>.xlsx, .xls, .csv</strong>
        </div>
        """, unsafe_allow_html=True)

        archivo = st.file_uploader(
            "Selecciona el archivo Excel o CSV",
            type=["xlsx", "xls", "csv"],
            key="file_uploader_mobile",
            help="Formatos: .xlsx, .xls, .csv"
        )

        if archivo is not None:
            try:
                with st.spinner("Leyendo el archivo..."):
                    if archivo.name.lower().endswith('.csv'):
                        df = pd.read_csv(archivo)
                    else:
                        df = pd.read_excel(archivo)

                df.columns = [str(c).strip().lower() for c in df.columns]

                # Soporte para columnas comunes
                if "id" in df.columns and "estudiante_id" not in df.columns:
                    df = df.rename(columns={"id": "estudiante_id"})
                if "name" in df.columns and "nombre" not in df.columns:
                    df = df.rename(columns={"name": "nombre"})

                if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                    st.error("❌ El archivo debe tener las columnas **estudiante_id** (o **id**) y **nombre**")
                    st.info(f"Columnas detectadas: {list(df.columns)}")
                else:
                    df["profesor"] = profesor
                    df["grado"] = grado
                    df["materia"] = materia
                    df = df[["profesor", "grado", "materia", "estudiante_id", "nombre"]].drop_duplicates()

                    st.success(f"✅ Archivo leído correctamente: **{len(df)} estudiantes**")

                    if st.button("💾 Guardar estudiantes en la base de datos", type="primary"):
                        agregados = 0
                        for _, row in df.iterrows():
                            try:
                                conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)",
                                            (row["profesor"], row["grado"], row["materia"], str(row["estudiante_id"]), row["nombre"]))
                                conn.commit()
                                agregados += 1
                            except:
                                pass
                        st.success(f"✅ Se guardaron **{agregados}** estudiantes correctamente")
                        st.rerun()

            except Exception as e:
                st.error(f"❌ Error al leer el archivo: {str(e)}")
                st.info("Intenta guardar el archivo nuevamente desde Excel como .xlsx")

        # Alternativa: Pegar texto (útil en celular)
        with st.expander("📋 Alternativa: Pegar datos manualmente"):
            st.markdown("Copia desde Excel y pega aquí (un estudiante por línea)")
            texto = st.text_area("Pega los datos aquí", height=150, placeholder="1001,Juan Pérez\n1002,María García")
            if texto and st.button("Guardar desde texto"):
                lines = texto.strip().split("\n")
                agregados = 0
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if "," in line:
                        parts = line.split(",", 1)
                    elif "\t" in line:
                        parts = line.split("\t", 1)
                    else:
                        continue
                    if len(parts) == 2:
                        est_id = parts[0].strip()
                        est_nombre = parts[1].strip()
                        try:
                            conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)",
                                        (profesor, grado, materia, est_id, est_nombre))
                            conn.commit()
                            agregados += 1
                        except:
                            pass
                st.success(f"✅ Se guardaron {agregados} estudiantes desde texto")
                st.rerun()

        # Generar PDF
        if st.button("📄 Generar PDF con QR (4x4 cm)", type="primary"):
            df_para_pdf = pd.read_sql(
                "SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre",
                conn, params=(profesor, grado, materia)
            )
            if df_para_pdf.empty:
                st.warning("No hay estudiantes para generar el PDF")
            else:
                with st.spinner("Generando PDF..."):
                    pdf_buffer = BytesIO()
                    c = canvas.Canvas(pdf_buffer, pagesize=A4)
                    width, height = A4
                    qr_size = 113.3858
                    margin_x = 45
                    margin_y = 70
                    spacing_x = 25
                    spacing_y = 65
                    cols = 3

                    for i, (_, row) in enumerate(df_para_pdf.iterrows()):
                        if i % (cols * 4) == 0 and i != 0:
                            c.showPage()
                        col = i % cols
                        row_num = (i // cols) % 4
                        x = margin_x + col * (qr_size + spacing_x)
                        y = height - margin_y - row_num * (qr_size + spacing_y)

                        qr_img = generar_qr(row["estudiante_id"])
                        qr_pil = Image.open(qr_img)
                        qr_path = BytesIO()
                        qr_pil.save(qr_path, format="PNG")
                        qr_path.seek(0)
                        c.drawImage(ImageReader(qr_path), x, y - qr_size, width=qr_size, height=qr_size)

                        nombre_corto = abreviar_nombre(row["nombre"])
                        c.setFont("Helvetica-Bold", 9)
                        c.drawCentredString(x + qr_size/2, y - qr_size - 15, nombre_corto)
                        c.setFont("Helvetica", 8)
                        c.drawCentredString(x + qr_size/2, y - qr_size - 27, f"{grado} - {materia}")

                    c.save()
                    pdf_buffer.seek(0)

                st.download_button(
                    label="⬇️ Descargar PDF listo para imprimir",
                    data=pdf_buffer,
                    file_name=f"QR_{grado}_{materia}.pdf",
                    mime="application/pdf"
                )
