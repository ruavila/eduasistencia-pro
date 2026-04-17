import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import io
import sqlite3
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import hashlib

# ====================== CONFIG ======================
APP_NAME = "EduAsistencia Pro"

conn = sqlite3.connect("asistencia.db", check_same_thread=False)

conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
conn.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))")

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def generar_qr(texto):
    qr = qrcode.make(texto)
    buf = BytesIO()
    qr.save(buf)
    buf.seek(0)
    return buf

# ====================== LOGIN / REGISTRO ======================
if "user" not in st.session_state:
    st.session_state.user = None
    st.session_state.nombre = None

if st.session_state.user is None:
    st.title("🔐 Acceso")

    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])

    with tab1:
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")

        if st.button("Ingresar"):
            res = conn.execute(
                "SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?",
                (u, hash_password(p))
            ).fetchone()

            if res:
                st.session_state.user = u
                st.session_state.nombre = res[0]
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

    with tab2:
        nu = st.text_input("Nuevo usuario")
        nn = st.text_input("Nombre completo")
        np = st.text_input("Nueva contraseña", type="password")

        if st.button("Registrarse"):
            try:
                conn.execute("INSERT INTO profesores VALUES (?,?,?)",
                             (nu, hash_password(np), nn))
                conn.commit()
                st.success("Usuario creado")
            except:
                st.error("Usuario ya existe")

    st.stop()

profesor = st.session_state.user

st.sidebar.success(f"Conectado: {st.session_state.nombre}")

# ====================== MENÚ ======================
menu = st.sidebar.selectbox("Menú", [
    "1. Cursos",
    "2. Estudiantes",
    "3. Escanear",
    "4. Reporte",
    "5. Reiniciar"
])

# ====================== 1. CURSOS ======================
if menu == "1. Cursos":
    st.header("Cursos")

    g = st.text_input("Grado")
    m = st.text_input("Materia")

    if st.button("Agregar curso"):
        try:
            conn.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, g, m))
            conn.commit()
            st.success("Agregado")
        except:
            st.warning("Ya existe")

    df = pd.read_sql("SELECT * FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    st.dataframe(df)

# ====================== 2. ESTUDIANTES ======================
elif menu == "2. Estudiantes":
    st.header("Subir estudiantes")

    cursos = pd.read_sql("SELECT * FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))

    if cursos.empty:
        st.warning("Primero crea un curso")
    else:
        lista = [f"{r.grado}-{r.materia}" for _, r in cursos.iterrows()]
        sel = st.selectbox("Curso", lista)

        grado, materia = sel.split("-")

        st.info("📱 En celular usar archivo .xlsx")

        archivo = st.file_uploader("Archivo", type=["xlsx", "xls", "csv"])

        if archivo:
            try:
                contenido = archivo.read()

                if archivo.name.endswith(".csv"):
                    df = pd.read_csv(io.BytesIO(contenido))
                else:
                    df = pd.read_excel(io.BytesIO(contenido), engine="openpyxl")

                if df.empty:
                    st.error("Archivo vacío")
                else:
                    df.columns = [c.lower().strip() for c in df.columns]

                    if "id" in df.columns:
                        df.rename(columns={"id": "estudiante_id"}, inplace=True)

                    st.dataframe(df.head())

                    if st.button("Guardar estudiantes"):
                        for _, row in df.iterrows():
                            try:
                                conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)",
                                             (profesor, grado, materia,
                                              row["estudiante_id"], row["nombre"]))
                                conn.commit()
                            except:
                                pass

                        st.success("Guardados correctamente")

            except Exception as e:
                st.error(e)

# ====================== 3. ESCANEAR ======================
elif menu == "3. Escanear":
    st.header("Escaneo QR")
    st.info("Puedes integrar pyzbar aquí")

# ====================== 4. REPORTE ======================
elif menu == "4. Reporte":
    st.header("Reporte")

    data = pd.read_sql("SELECT * FROM asistencias", conn)

    if data.empty:
        st.info("Sin datos")
    else:
        st.dataframe(data)

# ====================== 5. REINICIAR ======================
elif menu == "5. Reiniciar":
    st.warning("Eliminar datos")

    if st.button("Confirmar"):
        conn.execute("DELETE FROM estudiantes")
        conn.execute("DELETE FROM asistencias")
        conn.commit()
        st.success("Datos eliminados")
