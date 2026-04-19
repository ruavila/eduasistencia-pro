import streamlit as st
import pandas as pd
import sqlite3
import qrcode
import numpy as np
from io import BytesIO
from PIL import Image
from datetime import datetime

# ====================== CONFIGURACIÓN VISUAL ======================
APP_NAME = "EduAsistencia Pro"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

st.set_page_config(page_title=APP_NAME, layout="wide")

# ====================== GESTIÓN DE BASE DE DATOS ======================
def get_connection():
    conn = sqlite3.connect("asistencia.db", check_same_thread=False)
    return conn

conn = get_connection()
cursor = conn.cursor()

# Creación de tablas con relación al usuario_id
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    correo TEXT UNIQUE,
    clave TEXT,
    pregunta TEXT,
    respuesta TEXT
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS docentes_cursos (
    usuario_id INTEGER, 
    grado TEXT, 
    materia TEXT, 
    PRIMARY KEY (usuario_id, grado, materia)
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS estudiantes (
    usuario_id INTEGER, 
    grado TEXT, 
    materia TEXT, 
    estudiante_id TEXT, 
    nombre TEXT, 
    PRIMARY KEY (usuario_id, grado, materia, estudiante_id)
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS asistencias (
    usuario_id INTEGER, 
    grado TEXT, 
    materia TEXT, 
    estudiante_id TEXT, 
    fecha TEXT, 
    hora TEXT
)""")
conn.commit()

# ====================== LÓGICA DE SESIÓN ======================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_name = ""

# ====================== INTERFAZ DE ACCESO (LOGIN/REGISTRO) ======================
if not st.session_state.logged_in:
    render_col_escudo, render_col_tit = st.columns([1, 5])
    with render_col_tit:
        st.title(APP_NAME)
        st.write(f"{COLEGIO} • Por {CREADOR}")

    tab_login, tab_reg, tab_rec = st.tabs(["🔑 Ingresar", "📝 Registrarse", "❓ Recuperar Clave"])

    with tab_login:
        user_mail = st.text_input("Correo electrónico")
        user_pass = st.text_input("Contraseña", type="password")
        if st.button("Iniciar Sesión", type="primary"):
            user = cursor.execute("SELECT id, nombre FROM usuarios WHERE correo=? AND clave=?", (user_mail, user_pass)).fetchone()
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.rerun()
            else:
                st.error("Correo o contraseña incorrectos")

    with tab_reg:
        reg_nom = st.text_input("Nombre Completo")
        reg_mail = st.text_input("Email")
        reg_pass = st.text_input("Contraseña ", type="password")
        reg_preg = st.selectbox("Pregunta secreta", ["¿Mascota favorita?", "¿Ciudad natal?", "¿Primer colegio?"])
        reg_resp = st.text_input("Respuesta a la pregunta")
        if st.button("Crear Cuenta"):
            try:
                cursor.execute("INSERT INTO usuarios (nombre, correo, clave, pregunta, respuesta) VALUES (?,?,?,?,?)",
                               (reg_nom, reg_mail, reg_pass, reg_preg, reg_resp.lower().strip()))
                conn.commit()
                st.success("¡Cuenta creada! Ya puedes ingresar.")
            except:
                st.error("Ese correo ya está registrado.")

    with tab_rec:
        mail_rec = st.text_input("Correo para recuperar")
        if mail_rec:
            data = cursor.execute("SELECT pregunta, respuesta, clave FROM usuarios WHERE correo=?", (mail_rec,)).fetchone()
            if data:
                st.info(f"Pregunta: {data[0]}")
                resp_rec = st.text_input("Tu respuesta")
                if st.button("Mostrar mi clave"):
                    if resp_rec.lower().strip() == data[1]:
                        st.success(f"Tu contraseña es: {data[2]}")
                    else:
                        st.error("Respuesta incorrecta")
            else:
                st.warning("Correo no encontrado")
    st.stop()

# ====================== DASHBOARD (USUARIO IDENTIFICADO) ======================
st.sidebar.title(f"Hola, {st.session_state.user_name}")
menu = st.sidebar.radio("Menú de Navegación", [
    "📚 Mis Cursos", 
    "👥 Estudiantes y QR", 
    "📸 Tomar Asistencia", 
    "📊 Reportes",
    "⚙️ Configuración"
])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.logged_in = False
    st.rerun()

# --- MODULO 2: GESTIONAR CURSOS (CORREGIDO) ---
if menu == "📚 Mis Cursos":
    st.header("Gestión de Cursos")
    
    with st.expander("➕ Agregar Nuevo Curso", expanded=True):
        col1, col2 = st.columns(2)
        nuevo_g = col1.text_input("Grado (ej: 601)")
        nuevo_m = col2.text_input("Materia")
        if st.button("Registrar"):
            if nuevo_g and nuevo_m:
                cursor.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", 
                               (st.session_state.user_id, nuevo_g.upper(), nuevo_m))
                conn.commit()
                st.success("Curso añadido")
                st.rerun()

    st.subheader("Cursos Registrados")
    df_c = pd.read_sql(f"SELECT grado, materia FROM docentes_cursos WHERE usuario_id={st.session_state.user_id}", conn)
    if not df_c.empty:
        st.dataframe(df_c, use_container_width=True)
        
        # ELIMINAR CURSO (CORRECCIÓN FUNCIONAL)
        st.subheader("🗑️ Eliminar Curso")
        sel_elim = st.selectbox("Seleccione para borrar", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        if st.button("Confirmar Eliminación"):
            g_e, m_e = sel_elim.split(" - ")
            cursor.execute("DELETE FROM docentes_cursos WHERE usuario_id=? AND grado=? AND materia=?", 
                           (st.session_state.user_id, g_e, m_e))
            cursor.execute("DELETE FROM estudiantes WHERE usuario_id=? AND grado=? AND materia=?", 
                           (st.session_state.user_id, g_e, m_e))
            conn.commit()
            st.warning("Curso eliminado correctamente")
            st.rerun()
    else:
        st.info("No tienes cursos creados.")

# --- MODULO 3: ESTUDIANTES Y QR (CORREGIDO PARA MÓVILES) ---
elif menu == "👥 Estudiantes y QR":
    st.header("Carga de Estudiantes")
    df_c = pd.read_sql(f"SELECT grado, materia FROM docentes_cursos WHERE usuario_id={st.session_state.user_id}", conn)
    
    if df_c.empty:
        st.warning("Debes crear un curso primero.")
    else:
        opciones = [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()]
        seleccion = st.selectbox("Curso destino", opciones)
        g_dest, m_dest = seleccion.split(" - ")

        archivo = st.file_uploader("Subir Excel (.xlsx)", type=["xlsx"])
        if archivo:
            try:
                # 'openpyxl' es clave para que funcione en servidores móviles/nube
                df_est = pd.read_excel(archivo, engine='openpyxl')
                df_est.columns = [str(c).strip().lower() for c in df_est.columns]
                
                if "id" in df_est.columns: df_est.rename(columns={"id":"estudiante_id"}, inplace=True)
                
                if "estudiante_id" in df_est.columns and "nombre" in df_est.columns:
                    for _, fila in df_est.iterrows():
                        cursor.execute("INSERT OR REPLACE INTO estudiantes VALUES (?,?,?,?,?)",
                                       (st.session_state.user_id, g_dest, m_dest, str(fila["estudiante_id"]), fila["nombre"]))
                    conn.commit()
                    st.success("Estudiantes cargados exitosamente.")
                else:
                    st.error("El archivo debe tener columnas: 'estudiante_id' y 'nombre'")
            except Exception as e:
                st.error(f"Error: {e}")

# --- PIE DE PÁGINA ---
st.markdown("---")
st.caption(f"{APP_NAME} • {COLEGIO} • Usuario: {st.session_state.user_name}")
