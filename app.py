import streamlit as st
import pandas as pd
import qrcode
import sqlite3
import numpy as np
from io import BytesIO
from PIL import Image
from pyzbar.pyzbar import decode
from datetime import datetime

# ====================== CONFIGURACIÓN GENERAL ======================
APP_NAME = "EduAsistencia Pro"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "I. E. San Antonio de Padua"

st.set_page_config(page_title=APP_NAME, layout="wide")

# ====================== BASE DE DATOS Y AUTO-CORRECCIÓN ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)
cursor = conn.cursor()

def inicializar_db():
    # Crear tabla de usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        correo TEXT UNIQUE,
        clave TEXT,
        pregunta TEXT,
        respuesta TEXT
    )""")
    
    # Crear tablas principales
    cursor.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (usuario_id INTEGER, grado TEXT, materia TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS estudiantes (usuario_id INTEGER, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS asistencias (usuario_id INTEGER, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT)")
    
    # MIGRACIÓN: Corregir el error de "DatabaseError" agregando usuario_id si falta
    tablas = ["docentes_cursos", "estudiantes", "asistencias"]
    for tabla in tablas:
        cursor.execute(f"PRAGMA table_info({tabla})")
        columnas = [col[1] for col in cursor.fetchall()]
        if "usuario_id" not in columnas:
            try:
                cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN usuario_id INTEGER DEFAULT 1")
            except:
                pass
    conn.commit()

inicializar_db()

# ====================== GESTIÓN DE SESIÓN ======================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_name = ""

# ====================== INTERFAZ DE LOGIN / REGISTRO ======================
if not st.session_state.logged_in:
    st.title(f"🏫 {APP_NAME}")
    tab_log, tab_reg, tab_rec = st.tabs(["🔑 Iniciar Sesión", "📝 Registrarse", "❓ Olvidé mi clave"])

    with tab_log:
        login_email = st.text_input("Correo Electrónico", key="log_email")
        login_pass = st.text_input("Contraseña", type="password", key="log_pass")
        if st.button("Ingresar", type="primary"):
            user = cursor.execute("SELECT id, nombre FROM usuarios WHERE correo=? AND clave=?", 
                                 (login_email, login_pass)).fetchone()
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.rerun()
            else:
                st.error("Correo o contraseña incorrectos")

    with tab_reg:
        r_nombre = st.text_input("Nombre Completo")
        r_email = st.text_input("Correo")
        r_pass = st.text_input("Contraseña ", type="password")
        r_preg = st.selectbox("Pregunta de seguridad", ["¿Mascota?", "¿Ciudad?", "¿Color favorito?"])
        r_resp = st.text_input("Respuesta")
        if st.button("Crear Cuenta"):
            try:
                cursor.execute("INSERT INTO usuarios (nombre, correo, clave, pregunta, respuesta) VALUES (?,?,?,?,?)",
                               (r_nombre, r_email, r_pass, r_preg, r_resp.lower()))
                conn.commit()
                st.success("¡Cuenta creada! Ahora puedes iniciar sesión.")
            except:
                st.error("Ese correo ya está registrado.")

    with tab_rec:
        rec_email = st.text_input("Correo para recuperar")
        if rec_email:
            u = cursor.execute("SELECT pregunta, respuesta, clave FROM usuarios WHERE correo=?", (rec_email,)).fetchone()
            if u:
                st.info(f"Pregunta: {u[0]}")
                rec_resp = st.text_input("Tu respuesta")
                if st.button("Recuperar Clave"):
                    if rec_resp.lower() == u[1]:
                        st.success(f"Tu clave es: **{u[2]}**")
                    else:
                        st.error("Respuesta incorrecta")
    st.stop()

# ====================== PANEL PRINCIPAL (DOCENTE) ======================
st.sidebar.title(f"Bienvenido/a")
st.sidebar.info(f"👨‍🏫 {st.session_state.user_name}")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.logged_in = False
    st.rerun()

menu = st.sidebar.selectbox("Menú Principal", ["📚 Mis Cursos", "👥 Estudiantes y QR", "📸 Escanear Asistencia"])

# ----------------- OPCIÓN 2: MIS CURSOS -----------------
if menu == "📚 Mis Cursos":
    st.header("Gestión de Mis Cursos")
    
    with st.expander("➕ Añadir Nuevo Curso"):
        col1, col2 = st.columns(2)
        g = col1.text_input("Grado (ej: 6-A)")
        m = col2.text_input("Materia")
        if st.button("Guardar"):
            if g and m:
                cursor.execute("INSERT INTO docentes_cursos (usuario_id, grado, materia) VALUES (?, ?, ?)", 
                               (st.session_state.user_id, g.upper(), m))
                conn.commit()
                st.success("Curso guardado")
                st.rerun()

    # Mostrar cursos del usuario logueado
    df_c = pd.read_sql(f"SELECT grado, materia FROM docentes_cursos WHERE usuario_id={st.session_state.user_id}", conn)
    
    if not df_c.empty:
        st.subheader("Cursos Registrados")
        st.table(df_c)
        
        st.subheader("🗑️ Eliminar Curso")
        opciones = [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()]
        sel_del = st.selectbox("Seleccione el curso a borrar", opciones)
        if st.button("Eliminar"):
            g_d, m_d = sel_del.split(" - ")
            cursor.execute("DELETE FROM docentes_cursos WHERE usuario_id=? AND grado=? AND materia=?", 
                           (st.session_state.user_id, g_d, m_d))
            cursor.execute("DELETE FROM estudiantes WHERE usuario_id=? AND grado=? AND materia=?", 
                           (st.session_state.user_id, g_d, m_d))
            conn.commit()
            st.warning("Curso eliminado correctamente.")
            st.rerun()
    else:
        st.info("No tienes cursos creados aún.")

# ----------------- OPCIÓN 3: ESTUDIANTES -----------------
elif menu == "👥 Estudiantes y QR":
    st.header("Carga de Estudiantes")
    df_c = pd.read_sql(f"SELECT grado, materia FROM docentes_cursos WHERE usuario_id={st.session_state.user_id}", conn)
    
    if df_c.empty:
        st.warning("Primero crea un curso en 'Mis Cursos'.")
    else:
        sel_curso = st.selectbox("Selecciona curso destino", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g_dest, m_dest = sel_curso.split(" - ")
        
        archivo = st.file_uploader("Subir Excel (.xlsx)", type=["xlsx"])
        if archivo:
            try:
                # COMPATIBILIDAD MÓVIL: Usar engine openpyxl
                df_est = pd.read_excel(archivo, engine='openpyxl')
                df_est.columns = [c.strip().lower() for c in df_est.columns]
                
                if 'estudiante_id' in df_est.columns and 'nombre' in df_est.columns:
                    for _, row in df_est.iterrows():
                        cursor.execute("INSERT INTO estudiantes (usuario_id, grado, materia, estudiante_id, nombre) VALUES (?,?,?,?,?)",
                                       (st.session_state.user_id, g_dest, m_dest, str(row['estudiante_id']), row['nombre']))
                    conn.commit()
                    st.success(f"Se cargaron {len(df_est)} estudiantes.")
                else:
                    st.error("El Excel debe tener las columnas 'estudiante_id' y 'nombre'.")
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

# ----------------- OPCIÓN 4: ESCANEAR -----------------
elif menu == "📸 Escanear Asistencia":
    st.header("Escáner de QR")
    foto = st.camera_input("Tome foto al código QR")
    if foto:
        img_pil = Image.open(foto)
        img_np = np.array(img_pil)
        codigos = decode(img_np)
        if codigos:
            id_detectado = codigos[0].data.decode("utf-8")
            st.success(f"Estudiante detectado ID: {id_detectado}")
            # Aquí puedes añadir la lógica para guardar la asistencia con la fecha actual
        else:
            st.error("No se detectó ningún QR. Intente de nuevo.")

st.sidebar.markdown("---")
st.sidebar.caption(f"{COLEGIO} • {CREADOR}")
