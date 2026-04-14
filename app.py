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

# ====================== SESSION STATE ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None
if 'uploaded_students_df' not in st.session_state:
    st.session_state.uploaded_students_df = None
if 'archivo_subido' not in st.session_state:
    st.session_state.archivo_subido = None

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
    <p style='color:#64748B;'>{COLEGIO} • Creado por {CREADOR}</p>
    """, unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# ====================== LOGIN ======================
profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

if profesor is None:
    st.header("🔑 Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])

    with tab1:
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar"):
            if username and password:
                res = conn.execute(
                    "SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?",
                    (username.strip(), hash_password(password))
                ).fetchone()
                if res:
                    st.session_state.profesor_actual = username.strip()
                    st.session_state.nombre_docente = res[0]
                    st.success(f"✅ Bienvenido, {res[0]}")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")

    with tab2:
        nuevo_user = st.text_input("Usuario", key="reg_user")
        nuevo_nombre = st.text_input("Nombre completo", key="reg_nombre")
        nueva_pass = st.text_input("Contraseña", type="password", key="reg_pass")
        if st.button("Registrarse"):
            if nuevo_user and nuevo_nombre and nueva_pass:
                try:
                    conn.execute("INSERT INTO profesores VALUES (?, ?, ?)", 
                                 (nuevo_user.strip(), hash_password(nueva_pass), nuevo_nombre.strip()))
                    conn.commit()
                    st.success("✅ Registro exitoso. Ahora inicia sesión.")
                except:
                    st.error("❌ Ese usuario ya existe")

else:
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

    # ====================== 1. CURSOS ======================
    if menu == "1. Mis Cursos (Agregar / Eliminar)":
        st.header("📚 Mis Cursos")

        df_cursos = pd.read_sql(
            "SELECT grado, materia FROM docentes_cursos WHERE profesor=? ORDER BY grado, materia",
            conn, params=(profesor,)
        )

        if not df_cursos.empty:
            st.dataframe(df_cursos, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            nuevo_g = st.text_input("Grado")
        with col2:
            nuevo_m = st.text_input("Materia")

        if st.button("Agregar curso"):
            try:
                conn.execute(
                    "INSERT INTO docentes_cursos VALUES (?,?,?)",
                    (profesor, nuevo_g.strip().upper(), nuevo_m.strip())
                )
                conn.commit()
                st.success("Curso agregado")
                st.rerun()
            except:
                st.warning("Ya existe")

    # ====================== 2. ESTUDIANTES ======================
    elif menu == "2. Gestionar Estudiantes y Generar PDF":
        st.header("👥 Gestionar Estudiantes")

        df_cursos = pd.read_sql(
            "SELECT grado, materia FROM docentes_cursos WHERE profesor=?",
            conn, params=(profesor,)
        )

        if df_cursos.empty:
            st.warning("Agrega cursos primero")
        else:
            lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
            seleccion = st.selectbox("Selecciona curso", lista)
            grado, materia = [x.strip() for x in seleccion.split(" - ")]

            archivo = st.file_uploader("Archivo", type=["xlsx", "xls", "csv"])

            if archivo is not None:
                st.session_state.archivo_subido = archivo

            archivo = st.session_state.archivo_subido

            if st.button("Procesar archivo"):
                if archivo is None:
                    st.error("Debes subir un archivo")
                else:
                    if archivo.name.endswith(".csv"):
                        df = pd.read_csv(archivo)
                    else:
                        df = pd.read_excel(archivo)

                    df.columns = [c.lower().strip() for c in df.columns]

                    if "id" in df.columns:
                        df = df.rename(columns={"id": "estudiante_id"})

                    df["profesor"] = profesor
                    df["grado"] = grado
                    df["materia"] = materia

                    st.session_state.uploaded_students_df = df
                    st.success("Archivo procesado")
                    st.dataframe(df)

            if st.session_state.uploaded_students_df is not None:
                if st.button("Guardar"):
                    for _, r in st.session_state.uploaded_students_df.iterrows():
                        try:
                            conn.execute(
                                "INSERT INTO estudiantes VALUES (?,?,?,?,?)",
                                (r["profesor"], r["grado"], r["materia"], str(r["estudiante_id"]), r["nombre"])
                            )
                        except:
                            pass
                    conn.commit()
                    st.success("Guardado correctamente")
                    st.session_state.uploaded_students_df = None

            # ✅ GENERAR PDF QR
            if st.button("📄 Generar PDF con QR (4x4 cm)"):
                df_para_pdf = pd.read_sql(
                    "SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre",
                    conn, params=(profesor, grado, materia)
                )

                if df_para_pdf.empty:
                    st.warning("No hay estudiantes en este curso.")
                else:
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
                        "⬇️ Descargar PDF",
                        pdf_buffer,
                        file_name=f"QR_{grado}_{materia}.pdf",
                        mime="application/pdf"
                    )

    # ====================== 3. ESCANEAR ======================
    elif menu == "3. Escanear Asistencia con Cámara":
        st.header("📸 Escanear QR")

        picture = st.camera_input("Tomar foto QR")

        if picture:
            img = cv2.imdecode(np.frombuffer(picture.getvalue(), np.uint8), 1)
            detector = cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(img)

            if data:
                st.success(f"Asistencia registrada: {data}")
            else:
                st.error("No se detectó QR")

    # ====================== 4. REPORTE ======================
    elif menu == "4. Reporte y Descargar Excel":
        st.header("📊 Reporte")
        data = pd.read_sql("SELECT * FROM asistencias WHERE profesor=?", conn, params=(profesor,))
        if not data.empty:
            st.dataframe(data)

    # ====================== 5. RESET ======================
    elif menu == "5. Reiniciar mis datos":
        if st.button("Borrar todo"):
            conn.execute("DELETE FROM estudiantes WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM asistencias WHERE profesor=?", (profesor,))
            conn.commit()
            st.success("Datos eliminados")
