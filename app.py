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
import numpy as np
from pyzbar.pyzbar import decode

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
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
    st.session_state.nombre_docente = None

if st.session_state.profesor_actual is None:
    st.header("🔑 Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])

    with tab1:
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar", type="primary"):
            if username and password:
                password_hash = hash_password(password)
                res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", 
                                  (username, password_hash)).fetchone()
                if res:
                    st.session_state.profesor_actual = username
                    st.session_state.nombre_docente = res[0]
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

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
                    st.success("Registro exitoso. Ahora inicia sesión.")
                except:
                    st.error("Ese usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

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

# ====================== 1. MIS CURSOS ======================
if menu == "1. Mis Cursos (Agregar / Eliminar)":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=? ORDER BY grado, materia", conn, params=(profesor,))

    if not df_cursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(df_cursos, use_container_width=True)

        st.subheader("🗑️ Eliminar Curso")
        curso_elim = st.selectbox("Selecciona el curso a eliminar", 
                                  [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()], 
                                  key="curso_eliminar_key")

        # ===== NUEVA CONFIRMACIÓN =====
        if "confirmar_eliminacion" not in st.session_state:
            st.session_state.confirmar_eliminacion = False

        if st.button("🗑️ Eliminar curso seleccionado", type="secondary"):
            st.session_state.confirmar_eliminacion = True

        if st.session_state.confirmar_eliminacion:
            st.warning("⚠️ Esta acción eliminará el curso y todos sus estudiantes.")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Sí, eliminar definitivamente"):
                    g, m = [x.strip() for x in curso_elim.split(" - ")]

                    conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.commit()

                    st.session_state.confirmar_eliminacion = False
                    st.success(f"✅ Operación exitosa. Curso **{g} - {m}** eliminado correctamente")
                    st.rerun()

            with col2:
                if st.button("❌ Cancelar"):
                    st.session_state.confirmar_eliminacion = False

    else:
        st.info("Aún no tienes cursos registrados.")

    st.subheader("Agregar nuevo curso")
    col1, col2 = st.columns(2)
    with col1: nuevo_g = st.text_input("Grado", key="n_grado")
    with col2: nuevo_m = st.text_input("Materia", key="n_materia")
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

# ====================== 2. ESTUDIANTES ======================
elif menu == "2. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Gestionar Estudiantes y Generar PDF")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if df_cursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in seleccion.split(" - ")]

        archivo = st.file_uploader("Archivo", type=["xlsx","csv"])
        if archivo:
            df = pd.read_excel(archivo) if archivo.name.endswith("xlsx") else pd.read_csv(archivo)
            df.columns = [c.lower() for c in df.columns]

            if "id" in df.columns:
                df = df.rename(columns={"id":"estudiante_id"})

            if "estudiante_id" in df.columns and "nombre" in df.columns:
                if st.button("Guardar"):
                    for _, row in df.iterrows():
                        try:
                            conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)",
                                         (profesor,grado,materia,row["estudiante_id"],row["nombre"]))
                        except:
                            pass
                    conn.commit()
                    st.success("Guardados")

# ====================== 3. ESCANER ======================
elif menu == "3. Escanear Asistencia con Cámara":
    st.header("📸 Escanear QR")
    picture = st.camera_input("Escanear")
    if picture:
        img = Image.open(picture)
        decoded = decode(np.array(img))
        if decoded:
            st.success("QR leído")

# ====================== 4. REPORTES ======================
elif menu == "4. Reporte y Descargar Excel":
    st.header("📊 Reportes")

# ====================== 5. REINICIO ======================
elif menu == "5. Reiniciar mis datos":
    if st.button("Reiniciar"):
        conn.execute("DELETE FROM docentes_cursos WHERE profesor=?", (profesor,))
        conn.commit()
        st.success("Reiniciado")

st.caption(f"{APP_NAME} • {COLEGIO}")
