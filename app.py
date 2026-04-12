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

# 1. NOMBRE DEL DOCENTE
if menu == "1. Nombre del Docente":
    st.header("👨‍🏫 Nombre del Docente")
    nuevo = st.text_input("Tu nombre completo", value=obtener_nombre_docente())
    if st.button("Guardar nombre", type="primary"):
        if nuevo.strip():
            guardar_nombre_docente(nuevo.strip())
            st.success("✅ Nombre guardado correctamente")
            st.rerun()

# 2. MIS CURSOS
# ====================== CORRECCIÓN 1: Eliminar curso ======================
# El problema original era que el checkbox estaba DENTRO del if st.button(),
# lo que causaba que al hacer clic en el botón apareciera el checkbox,
# pero al marcar el checkbox se hacía un rerun y se perdía el estado del botón.
# SOLUCIÓN: Primero el checkbox de confirmación, luego el botón de eliminar.
elif menu == "2. Mis Cursos (Agregar / Eliminar)":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos ORDER BY grado, materia", conn)
    
    if not df_cursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(df_cursos, use_container_width=True)

        st.subheader("🗑️ Eliminar Curso")
        curso_elim = st.selectbox("Selecciona el curso a eliminar", 
                                  [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()], 
                                  key="curso_eliminar")
        
        # CORRECCIÓN: checkbox ANTES del botón, no dentro
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
            st.success(f"✅ Curso **{g} - {m}** eliminado correctamente junto con sus estudiantes y asistencias.")
            st.rerun()
    else:
        st.info("Aún no tienes cursos registrados.")

    st.markdown("---")
    st.subheader("➕ Agregar nuevo curso")
    col1, col2 = st.columns(2)
    with col1: nuevo_g = st.text_input("Grado", key="n_grado")
    with col2: nuevo_m = st.text_input("Materia", key="n_materia")
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

# 3. GESTIONAR ESTUDIANTES + PDF
# ====================== CORRECCIÓN 2: Carga de archivos en móvil ======================
# Se agrega una opción alternativa para agregar estudiantes manualmente
# cuando el file_uploader no funciona en dispositivos móviles.
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
            st.subheader(f"📋 Estudiantes registrados en {grado} - {materia}")
            st.dataframe(df_existentes, use_container_width=True)

        # Método de ingreso: pestañas
        tab_archivo, tab_manual = st.tabs(["📁 Subir archivo (Excel/CSV)", "✍️ Agregar manualmente"])

        with tab_archivo:
            st.markdown("""
            **Instrucciones:** Sube un archivo Excel (.xlsx) o CSV (.csv) con las columnas:
            - `estudiante_id` (o `id`): Identificador único del estudiante
            - `nombre`: Nombre completo del estudiante
            
            > ⚠️ **¿Estás en el celular y no puedes subir archivos?** Usa la pestaña **"Agregar manualmente"**.
            """)
            archivo = st.file_uploader(
                "Selecciona el archivo", 
                type=["xlsx", "csv"],
                key="file_uploader_estudiantes",
                help="Si estás en el celular y no funciona, usa la opción 'Agregar manualmente'"
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

                    # Convertir estudiante_id a string para evitar problemas
                    if "estudiante_id" in df.columns:
                        df["estudiante_id"] = df["estudiante_id"].astype(str).str.strip()

                    if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                        st.error("El archivo debe tener columnas: **estudiante_id** (o **id**) y **nombre**")
                    else:
                        df["grado"] = grado
                        df["materia"] = materia
                        df = df[["grado", "materia", "estudiante_id", "nombre"]].drop_duplicates()

                        st.write("**Vista previa de los datos:**")
                        st.dataframe(df[["estudiante_id", "nombre"]], use_container_width=True)

                        if st.button("💾 Guardar estudiantes del archivo", type="primary", key="btn_guardar_archivo"):
                            agregados = 0
                            duplicados = 0
                            for _, row in df.iterrows():
                                try:
                                    conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?)", 
                                                (row["grado"], row["materia"], str(row["estudiante_id"]), row["nombre"]))
                                    conn.commit()
                                    agregados += 1
                                except sqlite3.IntegrityError:
                                    duplicados += 1
                            st.success(f"✅ Se agregaron {agregados} estudiantes. ({duplicados} ya existían)")
                            st.rerun()
                except Exception as e:
                    st.error(f"Error al leer el archivo: {str(e)}")

        with tab_manual:
            st.markdown("**Agrega estudiantes uno por uno** (ideal para celular):")
            col_id, col_nombre = st.columns(2)
            with col_id:
                manual_id = st.text_input("ID del estudiante", key="manual_est_id", 
                                          placeholder="Ej: 1001")
            with col_nombre:
                manual_nombre = st.text_input("Nombre completo", key="manual_est_nombre",
                                              placeholder="Ej: Juan Pérez López")
            
            if st.button("➕ Agregar estudiante", type="primary", key="btn_agregar_manual"):
                if manual_id.strip() and manual_nombre.strip():
                    try:
                        conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?)", 
                                    (grado, materia, manual_id.strip(), manual_nombre.strip()))
                        conn.commit()
                        st.success(f"✅ Estudiante **{manual_nombre.strip()}** agregado correctamente")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.warning("Este estudiante ya existe en este curso")
                else:
                    st.warning("Debes completar ambos campos: ID y Nombre")

            st.markdown("---")
            st.markdown("**Agregar varios estudiantes (texto):**")
            st.markdown("Escribe un estudiante por línea con formato: `ID, Nombre completo`")
            texto_masivo = st.text_area(
                "Estudiantes (uno por línea)", 
                placeholder="1001, Juan Pérez López\n1002, María García Ruiz\n1003, Carlos Rodríguez",
                key="texto_masivo_estudiantes",
                height=200
            )
            if st.button("💾 Guardar todos los estudiantes del texto", type="primary", key="btn_guardar_masivo"):
                if texto_masivo.strip():
                    lineas = texto_masivo.strip().split("\n")
                    agregados = 0
                    errores = 0
                    for linea in lineas:
                        linea = linea.strip()
                        if not linea:
                            continue
                        partes = linea.split(",", 1)
                        if len(partes) == 2:
                            est_id = partes[0].strip()
                            est_nombre = partes[1].strip()
                            if est_id and est_nombre:
                                try:
                                    conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?)", 
                                                (grado, materia, est_id, est_nombre))
                                    conn.commit()
                                    agregados += 1
                                except sqlite3.IntegrityError:
                                    errores += 1
                            else:
                                errores += 1
                        else:
                            errores += 1
                    st.success(f"✅ Se agregaron {agregados} estudiantes. ({errores} con errores o duplicados)")
                    if errores > 0:
                        st.info("Formato correcto: `ID, Nombre completo` (separado por coma)")
                    st.rerun()

        # Sección para eliminar estudiantes individuales
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

        # Generar PDF con QR
        st.markdown("---")
        st.subheader("📄 Generar PDF con códigos QR")
        
        # Recargar estudiantes para el PDF
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

# 4. ESCANEAR
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

# 5. REPORTE
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

            # Resumen
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

# 6. REINICIAR
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
        st.success("✅ La aplicación ha sido reiniciada correctamente. Todos los cursos, estudiantes y asistencias han sido eliminados.")
        st.rerun()

st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")
