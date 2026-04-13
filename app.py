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
import hashlib
import cv2
import numpy as np

# ====================== CONFIGURACIÓN ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)
conn.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
conn.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generar_qr(texto):
    qr = qrcode.make(texto)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def abreviar_nombre(nombre):
    partes = nombre.strip().split()
    if len(partes) <= 2:
        return nombre
    iniciales = [p[0].upper() + "." for p in partes[:-1]]
    return " ".join(iniciales) + " " + partes[-1]

# ====================== INICIALIZACIÓN SESSION STATE ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None
if 'uploaded_students_df' not in st.session_state:
    st.session_state.uploaded_students_df = None
if 'last_uploaded_file_name' not in st.session_state:
    st.session_state.last_uploaded_file_name = None

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

# ====================== LOGIN ======================
profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

if profesor is None:
    st.header("🔑 Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab1:
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        
        if st.button("Ingresar", type="primary"):
            if username and password:
                password_hash = hash_password(password)
                res = conn.execute(
                    "SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", 
                    (username.strip(), password_hash)
                ).fetchone()
                
                if res:
                    st.session_state.profesor_actual = username.strip()
                    st.session_state.nombre_docente = res[0]
                    st.success(f"✅ Bienvenido, {res[0]}")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
            else:
                st.warning("Por favor ingresa usuario y contraseña")
    
    with tab2:
        nuevo_user = st.text_input("Usuario", key="reg_user")
        nuevo_nombre = st.text_input("Nombre completo", key="reg_nombre")
        nueva_pass = st.text_input("Contraseña", type="password", key="reg_pass")
        
        if st.button("Registrarse", type="primary"):
            if nuevo_user and nuevo_nombre and nueva_pass:
                try:
                    conn.execute("INSERT INTO profesores VALUES (?, ?, ?)", 
                                 (nuevo_user.strip(), hash_password(nueva_pass), nuevo_nombre.strip()))
                    conn.commit()
                    st.success("✅ Registro exitoso. Ahora inicia sesión.")
                except:
                    st.error("❌ Ese usuario ya existe")
            else:
                st.warning("Completa todos los campos")

else:
    # ====================== MENÚ PRINCIPAL ======================
    st.sidebar.success(f"✅ Conectado como: {nombre_docente}")
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.profesor_actual = None
        st.session_state.nombre_docente = None
        st.rerun()

    menu = st.sidebar.selectbox("Menú principal:", [
        "1. Mis Cursos (Agregar / Eliminar)",
        "2. Gestionar Estudiantes y Generar PDF",
        "3. Escanear Asistencia con Cámara",
        "4. Reporte y Descargar Excel",
        "5. Reiniciar mis datos"
    ])

    # 1. MIS CURSOS
    if menu == "1. Mis Cursos (Agregar / Eliminar)":
        st.header("📚 Mis Cursos")
        df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=? ORDER BY grado, materia", 
                                conn, params=(profesor,))
        
        if not df_cursos.empty:
            st.subheader("Cursos registrados")
            st.dataframe(df_cursos, use_container_width=True)
            
            st.subheader("🗑️ Eliminar Curso")
            curso_elim = st.selectbox("Selecciona el curso a eliminar", 
                                      [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()], 
                                      key="curso_eliminar_key")
            
            if st.button("🗑️ Eliminar curso seleccionado", type="secondary"):
                if st.checkbox("Confirmo que deseo eliminar este curso y todos sus estudiantes"):
                    g, m = [x.strip() for x in curso_elim.split(" - ")]
                    conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.commit()
                    st.success(f"✅ Curso **{g} - {m}** eliminado correctamente")
                    st.rerun()
        else:
            st.info("Aún no tienes cursos registrados.")
        
        st.subheader("Agregar nuevo curso")
        col1, col2 = st.columns(2)
        with col1:
            nuevo_g = st.text_input("Grado", key="n_grado")
        with col2:
            nuevo_m = st.text_input("Materia", key="n_materia")
        
        if st.button("Agregar curso", type="primary"):
            if nuevo_g and nuevo_m:
                try:
                    conn.execute("INSERT INTO docentes_cursos VALUES (?, ?, ?)", 
                                 (profesor, nuevo_g.strip().upper(), nuevo_m.strip()))
                    conn.commit()
                    st.success("✅ Curso agregado correctamente")
                    st.rerun()
                except:
                    st.warning("Este curso ya existe para ti")

    # 2. GESTIONAR ESTUDIANTES - VERSIÓN MEJORADA PARA CELULAR
    elif menu == "2. Gestionar Estudiantes y Generar PDF":
        st.header("👥 Gestionar Estudiantes y Generar PDF")
        
        df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
        
        if df_cursos.empty:
            st.warning("Agrega cursos primero")
        else:
            lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
            seleccion = st.selectbox("Selecciona curso", lista, key="select_curso_estudiantes")
            grado, materia = [x.strip() for x in seleccion.split(" - ")]

            st.subheader("📁 Subir lista de estudiantes")
            st.markdown(""" 
            <div style='background:#FFF3CD; padding:15px; border-radius:10px; border:2px solid #FFC107;'>
             📱 <strong>Importante en celular:</strong><br>
             • Selecciona el archivo rápidamente<br>
             • Espera a que aparezca "Archivo leído correctamente"<br>
             • Luego presiona el botón Guardar
            </div>
            """, unsafe_allow_html=True)

            uploader_key = f"uploader_{profesor}_{grado}_{materia}"

            archivo = st.file_uploader(
                "Selecciona el archivo Excel o CSV", 
                type=["xlsx", "xls", "csv"], 
                key=uploader_key,
                help="Debe tener columnas: estudiante_id y nombre"
            )

            if archivo is not None:
                if (st.session_state.last_uploaded_file_name != archivo.name or 
                    st.session_state.uploaded_students_df is None):
                    
                    try:
                        if archivo.name.lower().endswith('.csv'):
                            df = pd.read_csv(archivo)
                        else:
                            df = pd.read_excel(archivo)

                        df.columns = [str(c).strip().lower() for c in df.columns]
                        if "id" in df.columns:
                            df = df.rename(columns={"id": "estudiante_id"})

                        if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                            st.error("❌ El archivo debe tener las columnas: **estudiante_id** y **nombre**")
                        else:
                            df["profesor"] = profesor
                            df["grado"] = grado
                            df["materia"] = materia
                            df = df[["profesor", "grado", "materia", "estudiante_id", "nombre"]].drop_duplicates()
                            
                            st.session_state.uploaded_students_df = df
                            st.session_state.last_uploaded_file_name = archivo.name
                            
                            st.success(f"✅ Archivo leído correctamente: **{len(df)} estudiantes** detectados")
                            st.dataframe(df[["estudiante_id", "nombre"]], use_container_width=True)

                    except Exception as e:
                        st.error(f"❌ Error al leer el archivo: {str(e)}")
                        st.info("Intenta guardar como .xlsx desde Excel.")

            # Botón Guardar
            if st.session_state.uploaded_students_df is not None:
                if st.button("💾 Guardar estudiantes en la base de datos", type="primary"):
                    df = st.session_state.uploaded_students_df
                    agregados = 0
                    for _, row in df.iterrows():
                        try:
                            conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)", 
                                         (row["profesor"], row["grado"], row["materia"], 
                                          str(row["estudiante_id"]), str(row["nombre"])))
                            agregados += 1
                        except:
                            pass
                    conn.commit()
                    st.success(f"✅ Se guardaron **{agregados}** estudiantes correctamente")
                    
                    # Limpiar
                    st.session_state.uploaded_students_df = None
                    st.session_state.last_uploaded_file_name = None
                    st.rerun()
            else:
                if archivo is None:
                    st.info("Selecciona un archivo Excel o CSV")

            # Generar PDF
            if st.button("📄 Generar PDF con QR (4x4 cm)", type="primary"):
                df_para_pdf = pd.read_sql(
                    "SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre",
                    conn, params=(profesor, grado, materia)
                )
                if df_para_pdf.empty:
                    st.warning("No hay estudiantes en este curso todavía.")
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

    # 3. ESCANEAR ASISTENCIA
    elif menu == "3. Escanear Asistencia con Cámara":
        st.header("📸 Escanear QR del estudiante")
        df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
        
        if df_cursos.empty:
            st.warning("Agrega cursos primero")
        else:
            lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
            sel = st.selectbox("Selecciona curso", lista)
            grado, materia = [x.strip() for x in sel.split(" - ")]
            
            picture = st.camera_input("Apunta al QR y toma la foto", key="cam_key")
            
            if picture is not None:
                bytes_data = picture.getvalue()
                cv2_img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
                
                detector = cv2.QRCodeDetector()
                data, bbox, _ = detector.detectAndDecode(cv2_img)
                
                if data:
                    est_id = data.strip()
                    info = pd.read_sql(
                        "SELECT nombre FROM estudiantes WHERE profesor=? AND estudiante_id=? AND grado=? AND materia=?", 
                        conn, params=(profesor, est_id, grado, materia)
                    )
                    if info.empty:
                        st.error("🚫 El estudiante no pertenece a este curso")
                    else:
                        nombre = info.iloc[0]["nombre"]
                        fecha = datetime.now().strftime("%Y-%m-%d")
                        hora = datetime.now().strftime("%H:%M:%S")
                        key = f"{profesor}_{grado}_{materia}_{est_id}_{fecha}"
                        
                        if key not in st.session_state:
                            try:
                                conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", 
                                             (profesor, grado, materia, est_id, fecha, hora))
                                conn.commit()
                                st.session_state[key] = True
                                st.balloons()
                                st.success(f"✅ Asistencia registrada para **{nombre}**")
                            except:
                                st.warning("Este estudiante ya tiene asistencia hoy")
                else:
                    st.error("No se pudo leer el código QR. Acerca más la cámara y toma la foto de nuevo.")

            if st.button("✅ Listo - Escanear siguiente"):
                if "cam_key" in st.session_state:
                    del st.session_state.cam_key
                st.rerun()

    # 4. REPORTE
    elif menu == "4. Reporte y Descargar Excel":
        st.header("📊 Reporte de Asistencia")
        df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
        
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
                WHERE a.profesor=? AND a.grado = ? AND a.materia = ?
            """, conn, params=(profesor, grado, materia))
            
            if data.empty:
                st.info("Todavía no hay asistencias")
            else:
                fechas = sorted(data['fecha'].unique())
                tabla = pd.DataFrame(index=sorted(data['nombre'].unique()), columns=fechas).fillna("Ausente")
                
                for _, row in data.iterrows():
                    tabla.loc[row['nombre'], row['fecha']] = "Presente"
                
                tabla['Total Presente'] = (tabla == "Presente").sum(axis=1)
                tabla['Total Ausente'] = len(fechas) - tabla['Total Presente']
                tabla['% Asistencia'] = ((tabla['Total Presente'] / len(fechas)) * 100).round(1) if len(fechas) > 0 else 0
                tabla = tabla.reset_index().rename(columns={'index': 'Estudiante'})
                
                st.dataframe(tabla, use_container_width=True)
                
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    pd.DataFrame([[f"ASISTENCIA - {materia} - GRADO {grado}"]]).to_excel(writer, startrow=0, header=False, index=False)
                    pd.DataFrame([[f"Docente: {nombre_docente}"]]).to_excel(writer, startrow=1, header=False, index=False)
                    tabla.to_excel(writer, startrow=3, index=False)
                output.seek(0)
                st.download_button("📥 Descargar Excel", output, f"Asistencia_{grado}_{materia}.xlsx")

    # 5. REINICIAR
    elif menu == "5. Reiniciar mis datos":
        st.header("⚠️ Reiniciar mis datos")
        st.warning("Esta acción borrará todos tus cursos, estudiantes y asistencias.")
        if st.checkbox("Entiendo y deseo reiniciar mis datos"):
            if st.button("🔄 Confirmar Reinicio", type="secondary"):
                conn.execute("DELETE FROM docentes_cursos WHERE profesor=?", (profesor,))
                conn.execute("DELETE FROM estudiantes WHERE profesor=?", (profesor,))
                conn.execute("DELETE FROM asistencias WHERE profesor=?", (profesor,))
                conn.commit()
                st.success("✅ Tus datos han sido reiniciados.")
                st.rerun()

st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")
