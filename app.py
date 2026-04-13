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
CREADOR = "Rubén Darío Ávila Ávila"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)

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

# ====================== INTERFAZ ======================
st.set_page_config(page_title=APP_NAME, layout="wide")

st.title(APP_NAME)
st.caption(APP_SUBTITLE)

# ====================== LOGIN ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
    st.session_state.nombre_docente = None

if st.session_state.profesor_actual is None:
    st.header("🔑 Iniciar sesión")

    user = st.text_input("Usuario")
    pwd = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        res = conn.execute(
            "SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?",
            (user, hash_password(pwd))
        ).fetchone()

        if res:
            st.session_state.profesor_actual = user
            st.session_state.nombre_docente = res[0]
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

    st.markdown("### 🔐 Recuperar contraseña")
    user_rec = st.text_input("Usuario para recuperar")

    if st.button("Buscar usuario"):
        res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=?", (user_rec,)).fetchone()
        if res:
            st.success(f"Usuario encontrado: {res[0]}")
            nueva = st.text_input("Nueva contraseña", type="password")
            if st.button("Actualizar contraseña"):
                conn.execute("UPDATE profesores SET password_hash=? WHERE username=?",
                             (hash_password(nueva), user_rec))
                conn.commit()
                st.success("Contraseña actualizada")
        else:
            st.error("Usuario no encontrado")

    st.stop()

profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

st.sidebar.success(f"👨‍🏫 {nombre_docente}")

menu = st.sidebar.selectbox("Menú", [
    "Cursos",
    "Estudiantes",
    "Escáner QR",
    "Reporte"
])

# ====================== CURSOS ======================
if menu == "Cursos":
    st.header("📚 Cursos")

    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))

    if not df_cursos.empty:
        st.subheader("Cursos registrados")

        df_cursos["Seleccionar"] = False

        edited_df = st.data_editor(df_cursos, use_container_width=True)

        seleccionados = edited_df[edited_df["Seleccionar"] == True]

        if not seleccionados.empty:
            if st.button("🗑️ Eliminar cursos seleccionados"):
                for _, row in seleccionados.iterrows():
                    g = row["grado"]
                    m = row["materia"]

                    conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))

                conn.commit()
                st.success("Cursos eliminados correctamente")
                st.rerun()

    st.subheader("➕ Agregar curso")

    g = st.text_input("Grado")
    m = st.text_input("Materia")

    if st.button("Agregar curso"):
        try:
            conn.execute("INSERT INTO docentes_cursos VALUES (?, ?, ?)", (profesor, g.strip(), m.strip()))
            conn.commit()
            st.success("Curso agregado")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# ====================== ESTUDIANTES ======================
elif menu == "Estudiantes":
    st.header("👥 Subir estudiantes")

    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]

    if lista:
        sel = st.selectbox("Curso", lista)
        grado, materia = sel.split(" - ")

        st.info("📱 Usa archivos .xlsx para mejor compatibilidad en celular")

        archivo = st.file_uploader("Subir archivo", type=["xlsx", "xls", "csv"])

        if archivo:
            try:
                archivo.seek(0)
                nombre = archivo.name.lower()

                if nombre.endswith(".csv"):
                    df = pd.read_csv(archivo)
                elif nombre.endswith(".xlsx"):
                    df = pd.read_excel(archivo, engine="openpyxl")
                else:
                    df = pd.read_excel(archivo)

                df.columns = [c.lower().strip() for c in df.columns]

                if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                    st.error("Debe tener columnas: estudiante_id y nombre")
                else:
                    for _, row in df.iterrows():
                        try:
                            conn.execute(
                                "INSERT INTO estudiantes VALUES (?,?,?,?,?)",
                                (profesor, grado, materia, str(row["estudiante_id"]), row["nombre"])
                            )
                            conn.commit()
                        except:
                            pass

                    st.success("Estudiantes cargados")

            except Exception as e:
                st.error(f"Error: {e}")

# ====================== ESCÁNER ======================
elif menu == "Escáner QR":
    st.header("📸 Escanear QR")

    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]

    if lista:
        sel = st.selectbox("Curso", lista)
        grado, materia = sel.split(" - ")

        foto = st.camera_input("Tomar foto del QR")

        if foto:
            img = Image.open(foto)
            decoded = decode(np.array(img))

            if decoded:
                est_id = decoded[0].data.decode()

                fecha = datetime.now().strftime("%Y-%m-%d")
                hora = datetime.now().strftime("%H:%M:%S")

                try:
                    conn.execute(
                        "INSERT INTO asistencias VALUES (?,?,?,?,?,?)",
                        (profesor, grado, materia, est_id, fecha, hora)
                    )
                    conn.commit()
                    st.success("Asistencia registrada")
                except:
                    st.warning("Ya registrado hoy")
            else:
                st.error("No se detectó QR")

# ====================== REPORTE ======================
elif menu == "Reporte":
    st.header("📊 Reporte")

    df = pd.read_sql("SELECT * FROM asistencias", conn)
    st.dataframe(df, use_container_width=True)

st.caption("EduAsistencia Pro")
