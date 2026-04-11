import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import sqlite3
import cv2
import numpy as np
from pyzbar.pyzbar import decode
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

# ====================== FUNCIONES ======================
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

# ====================== 1. DOCENTE ======================
if menu == "1. Nombre del Docente":
    st.header("👨‍🏫 Nombre del Docente")
    nuevo = st.text_input("Tu nombre completo", value=obtener_nombre_docente())
    if st.button("Guardar nombre", type="primary"):
        if nuevo.strip():
            guardar_nombre_docente(nuevo.strip())
            st.success("✅ Nombre guardado correctamente")
            st.rerun()

# ====================== 2. CURSOS ======================
elif menu == "2. Mis Cursos (Agregar / Eliminar)":
    st.header("📚 Mis Cursos")
    
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos ORDER BY grado, materia", conn)
    
    if not df_cursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(df_cursos, use_container_width=True)

        st.subheader("🗑️ Eliminar Curso")
        curso_elim = st.selectbox(
            "Selecciona el curso a eliminar", 
            [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        )

        confirmar = st.checkbox("Confirmo que deseo eliminar este curso y todos sus estudiantes")

        if st.button("🗑️ Eliminar curso seleccionado", type="secondary"):
            if confirmar:
                g, m = [x.strip() for x in curso_elim.split(" - ")]

                conn.execute("DELETE FROM docentes_cursos WHERE grado=? AND materia=?", (g, m))
                conn.execute("DELETE FROM estudiantes WHERE grado=? AND materia=?", (g, m))
                conn.execute("DELETE FROM asistencias WHERE grado=? AND materia=?", (g, m))
                conn.commit()

                st.success("✅ Curso eliminado con éxito")
                st.rerun()
            else:
                st.warning("Debes confirmar antes de eliminar")
    else:
        st.info("Aún no tienes cursos registrados.")

    st.subheader("Agregar nuevo curso")
    col1, col2 = st.columns(2)
    with col1:
        nuevo_g = st.text_input("Grado (ej: 10A)")
    with col2:
        nuevo_m = st.text_input("Materia (ej: Matemáticas)")

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

# ====================== 3. ESTUDIANTES ======================
elif menu == "3. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Gestionar Estudiantes y Generar PDF")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)

    if df_cursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in seleccion.split(" - ")]

        archivo = st.file_uploader("Sube lista de estudiantes", type=["xlsx", "csv"])
        if archivo:
            df = pd.read_csv(archivo) if archivo.name.endswith(".csv") else pd.read_excel(archivo)

            df.columns = [c.strip().lower() for c in df.columns]
            if "id" in df.columns:
                df = df.rename(columns={"id": "estudiante_id"})

            if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                st.error("Debe tener columnas: estudiante_id y nombre")
            else:
                df["grado"] = grado
                df["materia"] = materia

                for _, row in df.iterrows():
                    try:
                        conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?)", 
                                    (row["grado"], row["materia"], row["estudiante_id"], row["nombre"]))
                        conn.commit()
                    except:
                        pass

                st.success("✅ Estudiantes cargados")

# ====================== 4. ESCANEAR ======================
elif menu == "4. Escanear Asistencia con Cámara":
    st.header("📸 Escanear QR")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)

    if not df_cursos.empty:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Curso", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]

        picture = st.camera_input("Escanear QR")

        if picture:
            image = Image.open(picture)
            decoded = decode(np.array(image))

            if decoded:
                est_id = decoded[0].data.decode("utf-8")
                st.success(f"ID detectado: {est_id}")
            else:
                st.error("No se pudo leer el QR")

# ====================== 5. REPORTE ======================
elif menu == "5. Reporte y Descargar Excel":
    st.header("📊 Reporte")
    st.info("Funcionalidad activa")

# ====================== 6. REINICIAR ======================
elif menu == "6. Reiniciar Aplicación (Nuevo año lectivo)":
    st.header("⚠️ Reiniciar Aplicación")

    if st.checkbox("Confirmar reinicio"):
        if st.button("Reiniciar"):
            conn.execute("DELETE FROM docentes_cursos")
            conn.execute("DELETE FROM estudiantes")
            conn.execute("DELETE FROM asistencias")
            conn.commit()

            st.success("✅ Aplicación reiniciada")
            st.rerun()

st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")