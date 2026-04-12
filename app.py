import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import sqlite3
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ====================== CONFIGURACIÓN ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)

conn.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (grado TEXT, materia TEXT, PRIMARY KEY (grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (grado, materia, estudiante_id))")
conn.execute("CREATE TABLE IF NOT EXISTS asistencias (grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (grado, materia, estudiante_id, fecha))")


def generar_qr(texto):
    qr = qrcode.make(texto)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def obtener_nombre_docente():
    res = conn.execute("SELECT valor FROM config WHERE clave='nombre_docente'").fetchone()
    return res[0] if res else ""


def guardar_nombre_docente(nombre):
    conn.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('nombre_docente', ?)", (nombre,))
    conn.commit()


def abreviar_nombre(nombre):
    partes = nombre.strip().split()
    if len(partes) <= 2:
        return nombre
    iniciales = [p[0].upper() + "." for p in partes[:-1]]
    return " ".join(iniciales) + " " + partes[-1]


# ====================== INTERFAZ ======================
st.set_page_config(page_title=APP_NAME, layout="wide")

# CSS para mejorar la experiencia en móviles
st.markdown("""
<style>
    /* Hacer el botón de file_uploader más grande y fácil de tocar en móvil */
    [data-testid="stFileUploader"] {
        min-height: 80px;
    }
    [data-testid="stFileUploader"] section {
        padding: 15px;
    }
    [data-testid="stFileUploader"] button {
        font-size: 18px !important;
        padding: 14px 28px !important;
        min-height: 56px !important;
        touch-action: manipulation;
        -webkit-tap-highlight-color: transparent;
    }
    [data-testid="stFileUploader"] label {
        font-size: 16px !important;
    }
    /* Botones más grandes en móvil */
    @media (max-width: 768px) {
        .stButton > button {
            min-height: 52px !important;
            font-size: 16px !important;
            touch-action: manipulation;
            width: 100% !important;
        }
        /* Hacer el área de drop más grande */
        [data-testid="stFileUploadDropzone"] {
            min-height: 120px !important;
            padding: 20px !important;
        }
    }
    /* Alerta especial para instrucciones móvil */
    .mobile-tip {
        background: #FFF3CD;
        border: 2px solid #FFC107;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        font-size: 15px;
    }
    .mobile-tip strong {
        color: #856404;
    }
</style>
""", unsafe_allow_html=True)

col_escudo, col_titulo = st.columns([1, 4])
with col_escudo:
    try:
        escudo = Image.open(ESCUDO_PATH)
        st.image(escudo, width=130)
    except:
        pass

with col_titulo:
    st.markdown(f"""
        <h1 style='margin-bottom:0; color:#1E3A8A;'>{APP_NAME}</h1>
        <h3 style='margin-top:5px; color:#334155;'>{APP_SUBTITLE}</h3>
        <p style='color:#64748B; font-size:1.05em;'>{COLEGIO} • Creado por {CREADOR}</p>
    """, unsafe_allow_html=True)

st.markdown("<hr style='margin: 25px 0;'>", unsafe_allow_html=True)

if obtener_nombre_docente():
    st.markdown(f"**Docente:** {obtener_nombre_docente()}")

menu = st.sidebar.selectbox("Menú principal:", [
    "1. Nombre del Docente",
    "2. Mis Cursos (Agregar / Eliminar)",
    "3. Gestionar Estudiantes y Generar PDF",
    "4. Escanear Asistencia con Cámara",
    "5. Reporte y Descargar Excel",
    "6. Reiniciar Aplicación (Nuevo año lectivo)"
])

# =====================================================================
# 1. NOMBRE DEL DOCENTE
# =====================================================================
if menu == "1. Nombre del Docente":
    st.header("👨‍🏫 Nombre del Docente")
    nuevo = st.text_input("Tu nombre completo", value=obtener_nombre_docente())
    if st.button("Guardar nombre", type="primary"):
        if nuevo.strip():
            guardar_nombre_docente(nuevo.strip())
            st.success("✅ Nombre guardado correctamente")
            st.rerun()

# =====================================================================
# 2. MIS CURSOS
# =====================================================================
elif menu == "2. Mis Cursos (Agregar / Eliminar)":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos ORDER BY grado, materia", conn)

    if not df_cursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(df_cursos, use_container_width=True)

        st.subheader("🗑️ Eliminar Curso")
        curso_elim = st.selectbox(
            "Selecciona el curso a eliminar",
            [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()],
            key="curso_eliminar"
        )

        confirmar_eliminar = st.checkbox(
            "✅ Confirmo que deseo eliminar este curso y todos sus estudiantes y asistencias",
            key="confirmar_eliminar_curso"
        )

        if st.button("🗑️ Eliminar curso seleccionado", type="secondary", disabled=not confirmar_eliminar):
            g, m = [x.strip() for x in curso_elim.split(" - ")]
            conn.execute("DELETE FROM docentes_cursos WHERE grado=? AND materia=?", (g, m))
            conn.execute("DELETE FROM estudiantes WHERE grado=? AND materia=?", (g, m))
            conn.execute("DELETE FROM asistencias WHERE grado=? AND materia=?", (g, m))
            conn.commit()
            st.success(f"✅ Curso **{g} - {m}** eliminado correctamente.")
            st.rerun()
    else:
        st.info("Aún no tienes cursos registrados.")

    st.markdown("---")
    st.subheader("➕ Agregar nuevo curso")
    col1, col2 = st.columns(2)
    with col1:
        nuevo_g = st.text_input("Grado", key="n_grado")
    with col2:
        nuevo_m = st.text_input("Materia", key="n_materia")
    if st.button("Agregar curso", type="primary"):
        if nuevo_g and nuevo_m:
            try:
                conn.execute("INSERT INTO docentes_cursos VALUES (?, ?)",
                             (nuevo_g.strip().upper(), nuevo_m.strip()))
                conn.commit()
                st.success("✅ Curso agregado correctamente")
                st.rerun()
            except:
                st.warning("Este curso ya existe")

# =====================================================================
# 3. GESTIONAR ESTUDIANTES + PDF
# =====================================================================
elif menu == "3. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Gestionar Estudiantes y Generar PDF")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)
    if df_cursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in seleccion.split(" - ")]

        # Mostrar estudiantes actuales del curso
        df_existentes = pd.read_sql(
            "SELECT estudiante_id, nombre FROM estudiantes WHERE grado=? AND materia=? ORDER BY nombre",
            conn, params=(grado, materia)
        )
        if not df_existentes.empty:
            st.subheader(f"📋 Estudiantes registrados en {grado} - {materia} ({len(df_existentes)})")
            st.dataframe(df_existentes, use_container_width=True)

        # ============================================================
        # SUBIR ARCHIVO - Con instrucciones para móvil
        # ============================================================
        st.subheader("📁 Subir lista de estudiantes")

        # Instrucciones especiales para celular
        st.markdown("""
        <div class="mobile-tip">
        📱 <strong>¿Estás en el celular?</strong> Sigue estos pasos para que funcione correctamente:<br><br>
        1. <strong>Usa Firefox</strong> en vez de Chrome (Chrome tiene un bug conocido con Streamlit).<br>
        2. Si usas Chrome: cuando toques "Browse files", <strong>selecciona el archivo RÁPIDO</strong> (en menos de 10 segundos). Si tardas mucho, Chrome cancela la conexión.<br>
        3. El archivo debe estar <strong>guardado en tu celular</strong> (no en Google Drive ni OneDrive). Si está en la nube, descárgalo primero.<br>
        4. Formatos aceptados: <strong>.xlsx</strong> (Excel) o <strong>.csv</strong>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        **El archivo debe tener estas columnas:**
        - `estudiante_id` (o `id`): Identificador único del estudiante
        - `nombre`: Nombre completo del estudiante
        """)

        archivo = st.file_uploader(
            "Toca aquí para seleccionar tu archivo Excel (.xlsx) o CSV (.csv)",
            type=["xlsx", "csv"],
            key="file_uploader_estudiantes",
        )

        if archivo is not None:
            try:
                if archivo.name.endswith(".csv"):
                    df = pd.read_csv(archivo)
                else:
                    df = pd.read_excel(archivo)

                df.columns = [c.strip().lower() for c in df.columns]
                if "id" in df.columns:
                    df = df.rename(columns={"id": "estudiante_id"})

                if "estudiante_id" in df.columns:
                    df["estudiante_id"] = df["estudiante_id"].astype(str).str.strip()

                if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                    st.error("❌ El archivo debe tener columnas: **estudiante_id** (o **id**) y **nombre**")
                else:
                    df["nombre"] = df["nombre"].astype(str).str.strip()
                    df["grado"] = grado
                    df["materia"] = materia
                    df = df[["grado", "materia", "estudiante_id", "nombre"]].drop_duplicates()

                    st.success(f"✅ Archivo leído correctamente: **{len(df)} estudiantes** encontrados")
                    st.dataframe(df[["estudiante_id", "nombre"]], use_container_width=True)

                    if st.button("💾 Guardar estudiantes en la base de datos", type="primary", key="btn_guardar_archivo"):
                        agregados = 0
                        duplicados = 0
                        for _, row in df.iterrows():
                            try:
                                conn.execute(
                                    "INSERT INTO estudiantes VALUES (?,?,?,?)",
                                    (row["grado"], row["materia"], str(row["estudiante_id"]), row["nombre"])
                                )
                                conn.commit()
                                agregados += 1
                            except sqlite3.IntegrityError:
                                duplicados += 1
                        st.success(f"✅ Se agregaron **{agregados}** estudiantes. ({duplicados} ya existían)")
                        st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")

        # ============================================================
        # ALTERNATIVA: Pegar texto (backup si el archivo no funciona)
        # ============================================================
        with st.expander("📋 ¿No puedes subir el archivo? Pega los datos aquí"):
            st.markdown("""
            Copia los datos desde Excel o Google Sheets y pégalos aquí.  
            **Formato:** `ID, Nombre` o `ID[tab]Nombre` (uno por línea)
            
            **Ejemplo:**
            ```
            1001, Juan Pérez López
            1002, María García Ruiz
            1003, Carlos Rodríguez
            ```
            """)

            texto_masivo = st.text_area(
                "Pega aquí la lista de estudiantes:",
                placeholder="1001, Juan Pérez López\n1002, María García Ruiz\n1003, Carlos Rodríguez",
                key="texto_masivo_estudiantes",
                height=200
            )

            if texto_masivo.strip():
                estudiantes_parseados = []
                errores_parseo = 0
                lineas = texto_masivo.strip().split("\n")
                for linea in lineas:
                    linea = linea.strip()
                    if not linea:
                        continue
                    if "\t" in linea:
                        partes = linea.split("\t", 1)
                    else:
                        partes = linea.split(",", 1)
                    if len(partes) == 2:
                        est_id = partes[0].strip()
                        est_nombre = partes[1].strip()
                        if est_id and est_nombre:
                            estudiantes_parseados.append((est_id, est_nombre))
                        else:
                            errores_parseo += 1
                    else:
                        errores_parseo += 1

                if estudiantes_parseados:
                    st.write(f"**Vista previa:** {len(estudiantes_parseados)} estudiantes detectados")
                    df_preview = pd.DataFrame(estudiantes_parseados, columns=["ID", "Nombre"])
                    st.dataframe(df_preview, use_container_width=True)
                    if errores_parseo > 0:
                        st.warning(f"⚠️ {errores_parseo} línea(s) con formato incorrecto (serán ignoradas)")

                    if st.button("💾 Guardar estudiantes del texto", type="primary", key="btn_guardar_masivo"):
                        agregados = 0
                        duplicados = 0
                        for est_id, est_nombre in estudiantes_parseados:
                            try:
                                conn.execute(
                                    "INSERT INTO estudiantes VALUES (?,?,?,?)",
                                    (grado, materia, est_id, est_nombre)
                                )
                                conn.commit()
                                agregados += 1
                            except sqlite3.IntegrityError:
                                duplicados += 1
                        st.success(f"✅ Se agregaron **{agregados}** estudiantes. ({duplicados} ya existían)")
                        st.rerun()
                else:
                    st.warning("No se detectaron estudiantes válidos. Usa el formato: `ID, Nombre`")

        # ============ ELIMINAR ESTUDIANTES ============
        if not df_existentes.empty:
            st.markdown("---")
            st.subheader("🗑️ Eliminar estudiante")
            est_eliminar = st.selectbox(
                "Selecciona estudiante a eliminar",
                [f"{r.estudiante_id} - {r.nombre}" for _, r in df_existentes.iterrows()],
                key="est_eliminar_select"
            )
            confirmar_elim_est = st.checkbox("Confirmo que deseo eliminar este estudiante", key="confirmar_elim_est")
            if st.button("🗑️ Eliminar estudiante", type="secondary", disabled=not confirmar_elim_est, key="btn_elim_est"):
                est_id_elim = est_eliminar.split(" - ")[0].strip()
                conn.execute("DELETE FROM estudiantes WHERE grado=? AND materia=? AND estudiante_id=?",
                             (grado, materia, est_id_elim))
                conn.execute("DELETE FROM asistencias WHERE grado=? AND materia=? AND estudiante_id=?",
                             (grado, materia, est_id_elim))
                conn.commit()
                st.success("✅ Estudiante eliminado correctamente")
                st.rerun()

        # ============ GENERAR PDF CON QR ============
        st.markdown("---")
        st.subheader("📄 Generar PDF con códigos QR")

        df_para_pdf = pd.read_sql(
            "SELECT estudiante_id, nombre FROM estudiantes WHERE grado=? AND materia=? ORDER BY nombre",
            conn, params=(grado, materia)
        )

        if df_para_pdf.empty:
            st.info("Agrega estudiantes primero para poder generar el PDF con códigos QR.")
        else:
            st.write(f"Se generarán QR para **{len(df_para_pdf)} estudiantes**")
            if st.button("📄 Generar PDF con QR (4x4 cm)", type="primary", key="btn_generar_pdf"):
                with st.spinner("Generando PDF..."):
                    pdf_buffer = BytesIO()
                    c = canvas.Canvas(pdf_buffer, pagesize=A4)
                    width, height = A4
                    qr_size = 113.3858  # 4cm en puntos
                    margin_x = 45
                    margin_y = 70
                    spacing_x = 25
                    spacing_y = 65
                    cols = 3
                    rows_per_page = 4

                    for i, (_, row) in enumerate(df_para_pdf.iterrows()):
                        if i % (cols * rows_per_page) == 0 and i != 0:
                            c.showPage()

                        col = i % cols
                        row_num = (i // cols) % rows_per_page
                        x = margin_x + col * (qr_size + spacing_x)
                        y = height - margin_y - row_num * (qr_size + spacing_y)

                        qr_img = generar_qr(str(row["estudiante_id"]))
                        qr_pil = Image.open(qr_img)
                        qr_path = BytesIO()
                        qr_pil.save(qr_path, format="PNG")
                        qr_path.seek(0)
                        c.drawImage(ImageReader(qr_path), x, y - qr_size, width=qr_size, height=qr_size)

                        nombre_corto = abreviar_nombre(row["nombre"])

                        c.setFont("Helvetica-Bold", 9)
                        c.drawCentredString(x + qr_size / 2, y - qr_size - 15, nombre_corto)
                        c.setFont("Helvetica", 8)
                        c.drawCentredString(x + qr_size / 2, y - qr_size - 27, f"{grado} - {materia}")

                    c.save()
                    pdf_buffer.seek(0)

                st.download_button(
                    label="⬇️ Descargar PDF listo para imprimir",
                    data=pdf_buffer,
                    file_name=f"QR_{grado}_{materia}.pdf",
                    mime="application/pdf"
                )

# =====================================================================
# 4. ESCANEAR ASISTENCIA
# =====================================================================
elif menu == "4. Escanear Asistencia con Cámara":
    st.header("📸 Escanear QR del estudiante")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)
    if df_cursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]

        st.subheader("📝 Registrar asistencia por ID")
        st.markdown("Escanea el QR con la cámara de tu celular y luego ingresa el ID aquí:")

        est_id_manual = st.text_input("ID del estudiante (del QR)", key="id_asistencia")

        if st.button("✅ Registrar Asistencia", type="primary", key="btn_registrar_asistencia"):
            if est_id_manual.strip():
                info = pd.read_sql(
                    "SELECT nombre FROM estudiantes WHERE estudiante_id=? AND grado=? AND materia=?",
                    conn, params=(est_id_manual.strip(), grado, materia)
                )
                if info.empty:
                    st.error("🚫 El estudiante no pertenece a este curso")
                else:
                    nombre = info.iloc[0]["nombre"]
                    fecha = datetime.now().strftime("%Y-%m-%d")
                    hora = datetime.now().strftime("%H:%M:%S")
                    try:
                        conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?)",
                                     (grado, materia, est_id_manual.strip(), fecha, hora))
                        conn.commit()
                        st.success(f"✅ Asistencia registrada para **{nombre}** a las {hora}")
                    except sqlite3.IntegrityError:
                        st.warning(f"⚠️ {nombre} ya tiene asistencia registrada hoy ({fecha})")
            else:
                st.warning("Ingresa el ID del estudiante")

        # Mostrar asistencias del día
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        asistencias_hoy = pd.read_sql("""
            SELECT e.nombre, a.hora_registro
            FROM asistencias a
            JOIN estudiantes e ON a.estudiante_id = e.estudiante_id
                AND a.grado = e.grado AND a.materia = e.materia
            WHERE a.grado=? AND a.materia=? AND a.fecha=?
            ORDER BY a.hora_registro DESC
        """, conn, params=(grado, materia, fecha_hoy))

        if not asistencias_hoy.empty:
            st.markdown("---")
            st.subheader(f"📋 Asistencias de hoy ({fecha_hoy})")
            st.dataframe(asistencias_hoy, use_container_width=True)
            st.info(f"Total presentes hoy: **{len(asistencias_hoy)}**")

        st.markdown("---")
        st.subheader("📸 Cámara (opcional)")
        st.markdown("Si deseas usar la cámara directamente, toma la foto del QR:")
        picture = st.camera_input("Apunta al QR y toma la foto", key="cam_key")
        if picture is not None:
            st.info("📸 Foto tomada. Por favor ingresa el ID del QR en el campo de arriba para registrar la asistencia.")

# =====================================================================
# 5. REPORTE
# =====================================================================
elif menu == "5. Reporte y Descargar Excel":
    st.header("📊 Reporte de Asistencia")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)
    if df_cursos.empty:
        st.warning("No hay cursos")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]

        data = pd.read_sql("""
            SELECT e.nombre, a.fecha
            FROM asistencias a
            JOIN estudiantes e ON a.estudiante_id = e.estudiante_id
                AND a.grado = e.grado AND a.materia = e.materia
            WHERE a.grado = ? AND a.materia = ?
        """, conn, params=(grado, materia))

        if data.empty:
            st.info("Todavía no hay asistencias registradas para este curso")
        else:
            fechas = sorted(data['fecha'].unique())
            nombres = sorted(data['nombre'].unique())
            tabla = pd.DataFrame(index=nombres, columns=fechas).fillna("Ausente")
            for _, row in data.iterrows():
                tabla.loc[row['nombre'], row['fecha']] = "Presente"

            tabla['Total Presente'] = (tabla == "Presente").sum(axis=1)
            tabla['Total Ausente'] = len(fechas) - tabla['Total Presente']
            tabla['% Asistencia'] = ((tabla['Total Presente'] / len(fechas)) * 100).round(1) if len(fechas) > 0 else 0

            tabla = tabla.reset_index().rename(columns={'index': 'Estudiante'})
            st.dataframe(tabla, use_container_width=True)

            total_est = len(nombres)
            promedio_asistencia = tabla['% Asistencia'].mean()
            st.markdown(f"""
            **Resumen:**
            - Total estudiantes: **{total_est}**
            - Total fechas registradas: **{len(fechas)}**
            - Promedio de asistencia: **{promedio_asistencia:.1f}%**
            """)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame([[f"ASISTENCIA - {materia} - GRADO {grado}"]]).to_excel(writer, startrow=0, header=False, index=False)
                pd.DataFrame([[f"Colegio: {COLEGIO}"]]).to_excel(writer, startrow=1, header=False, index=False)
                pd.DataFrame([[f"Docente: {obtener_nombre_docente() or 'No registrado'}"]]).to_excel(writer, startrow=2, header=False, index=False)
                tabla.to_excel(writer, startrow=4, index=False)
            output.seek(0)
            st.download_button("📥 Descargar Excel", output, f"Asistencia_{grado}_{materia}.xlsx")

# =====================================================================
# 6. REINICIAR
# =====================================================================
elif menu == "6. Reiniciar Aplicación (Nuevo año lectivo)":
    st.header("⚠️ Reiniciar Aplicación")
    st.warning("""
        **¡Atención importante!**  
        Esta acción borrará **todos** los cursos, estudiantes y registros de asistencia.  
        Solo se mantendrá el nombre del docente.  
        Esta operación **no se puede deshacer**.
    """)

    confirmar_reinicio = st.checkbox("Entiendo las consecuencias y deseo reiniciar la aplicación", key="confirmar_reinicio")
    if st.button("🔄 Confirmar Reinicio Completo", type="secondary", disabled=not confirmar_reinicio):
        conn.execute("DELETE FROM docentes_cursos")
        conn.execute("DELETE FROM estudiantes")
        conn.execute("DELETE FROM asistencias")
        conn.commit()
        st.success("✅ La aplicación ha sido reiniciada correctamente.")
        st.rerun()

st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")
