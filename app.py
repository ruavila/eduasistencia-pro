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
APP_SUBTITLE = "Gestión Multiusuario con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "I. E. San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

st.set_page_config(page_title=APP_NAME, layout="wide")

# ====================== BASE DE DATOS Y AUTO-CORRECCIÓN ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)
cursor = conn.cursor()

def inicializar_db():
    # Tabla de Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        correo TEXT UNIQUE,
        clave TEXT,
        pregunta TEXT,
        respuesta TEXT
    )""")
    
    # Tablas Principales (Aseguramos que existan)
    cursor.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (grado TEXT, materia TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS estudiantes (grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS asistencias (grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT)")
    
    # MIGRACIÓN: Corrige el error de "DatabaseError" agregando usuario_id si falta
    tablas = ["docentes_cursos", "estudiantes", "asistencias"]
    for tabla in tablas:
        cursor.execute(f"PRAGMA table_info({tabla})")
        columnas = [col[1] for col in cursor.fetchall()]
        if "usuario_id" not in columnas:
            try:
                cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN usuario_id INTEGER DEFAULT 1")
                conn.commit()
            except:
                pass

inicializar_db()

# ====================== GESTIÓN DE SESIÓN ======================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_name = ""

# ====================== INTERFAZ DE ACCESO (LOGIN/REGISTRO) ======================
if not st.session_state.logged_in:
    st.title(f"🏫 {APP_NAME}")
    st.markdown(f"**{COLEGIO}**")
    
    tab_log, tab_reg, tab_rec = st.tabs(["🔑 Iniciar Sesión", "📝 Registrarse", "❓ Recuperar Clave"])

    with tab_log:
        l_email = st.text_input("Correo Electrónico")
        l_pass = st.text_input("Contraseña", type="password")
        if st.button("Entrar", type="primary"):
            user = cursor.execute("SELECT id, nombre FROM usuarios WHERE correo=? AND clave=?", 
                                 (l_email, l_pass)).fetchone()
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.rerun()
            else:
                st.error("Credenciales incorrectas.")

    with tab_reg:
        st.subheader("Nueva Cuenta de Docente")
        r_nombre = st.text_input("Nombre Completo")
        r_email = st.text_input("Correo")
        r_pass = st.text_input("Contraseña ", type="password")
        r_preg = st.selectbox("Pregunta de seguridad", ["¿Mascota?", "¿Ciudad?", "¿Color favorito?"])
        r_resp = st.text_input("Respuesta")
        if st.button("Completar Registro"):
            try:
                cursor.execute("INSERT INTO usuarios (nombre, correo, clave, pregunta, respuesta) VALUES (?,?,?,?,?)",
                               (r_nombre, r_email, r_pass, r_preg, r_resp.lower()))
                conn.commit()
                st.success("¡Registro exitoso! Ya puedes iniciar sesión.")
            except:
                st.error("El correo ya está en uso.")

    with tab_rec:
        rec_email = st.text_input("Ingresa tu correo registrado")
        if rec_email:
            u = cursor.execute("SELECT pregunta, respuesta, clave FROM usuarios WHERE correo=?", (rec_email,)).fetchone()
            if u:
                st.write(f"**Pregunta:** {u[0]}")
                rec_resp = st.text_input("Tu respuesta secreta")
                if st.button("Ver mi clave"):
                    if rec_resp.lower() == u[1]:
                        st.success(f"Tu contraseña es: **{u[2]}**")
                    else:
                        st.error("Respuesta incorrecta.")
            else:
                st.error("Usuario no encontrado.")
    st.stop()

# ====================== PANEL PRINCIPAL (DOCENTE LOGUEADO) ======================
st.sidebar.title("EduAsistencia")
st.sidebar.write(f"👨‍🏫 **Docente:** {st.session_state.user_name}")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.logged_in = False
    st.rerun()

menu = st.sidebar.selectbox("Opciones", ["📚 Gestión de Cursos", "👥 Cargar Estudiantes", "📸 Escanear QR"])

# ----------------- 2. GESTIÓN DE CURSOS -----------------
if menu == "📚 Gestión de Cursos":
    st.header("Mis Cursos")
    
    with st.expander("➕ Añadir Curso"):
        col1, col2 = st.columns(2)
        g = col1.text_input("Grado")
        m = col2.text_input("Materia")
        if st.button("Guardar"):
            if g and m:
                cursor.execute("INSERT INTO docentes_cursos (usuario_id, grado, materia) VALUES (?, ?, ?)", 
                               (st.session_state.user_id, g.upper(), m))
                conn.commit()
                st.rerun()

    df_c = pd.read_sql(f"SELECT grado, materia FROM docentes_cursos WHERE usuario_id={st.session_state.user_id}", conn)
    
    if not df_c.empty:
        st.table(df_c)
        st.subheader("Eliminar")
        sel_del = st.selectbox("Seleccione curso a borrar", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        if st.button("Eliminar Curso"):
            g_d, m_d = sel_del.split(" - ")
            cursor.execute("DELETE FROM docentes_cursos WHERE usuario_id=? AND grado=? AND materia=?", 
                           (st.session_state.user_id, g_d, m_d))
            cursor.execute("DELETE FROM estudiantes WHERE usuario_id=? AND grado=? AND materia=?", 
                           (st.session_state.user_id, g_d, m_d))
            conn.commit()
            st.rerun()
    else:
        st.info("No tienes cursos creados.")

# ----------------- 3. ESTUDIANTES -----------------
elif menu == "👥 Cargar Estudiantes":
    st.header("Importar Estudiantes")
    df_c = pd.read_sql(f"SELECT grado, materia FROM docentes_cursos WHERE usuario_id={st.session_state.user_id}", conn)
    
    if df_c.empty:
        st.warning("Crea un curso primero.")
    else:
        sel_curso = st.selectbox("Destino", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g_dest, m_dest = sel_curso.split(" - ")
        
        archivo = st.file_uploader("Subir Excel (.xlsx)", type=["xlsx"])
        if archivo:
            try:
                # COMPATIBILIDAD MÓVIL
                df_est = pd.read_excel(archivo, engine='openpyxl')
                df_est.columns = [c.strip().lower() for c in df_est.columns]
                
                if 'estudiante_id' in df_est.columns and 'nombre' in df_est.columns:
                    for _, row in df_est.iterrows():
                        cursor.execute("INSERT INTO estudiantes (usuario_id, grado, materia, estudiante_id, nombre) VALUES (?,?,?,?,?)",
                                       (st.session_state.user_id, g_dest, m_dest, str(row['estudiante_id']), row['nombre']))
                    conn.commit()
                    st.success("Lista cargada con éxito.")
                else:
                    st.error("Faltan columnas: 'estudiante_id' y 'nombre'")
            except Exception as e:
                st.error(f"Error al procesar: {e}")

# ----------------- 4. ESCANEAR -----------------
elif menu == "📸 Escanear QR":
    st.header("Escáner de Asistencia")
    foto = st.camera_input("Enfocar QR")
    if foto:
        try:
            img = Image.open(foto)
            decoded = decode(np.array(img))
            if decoded:
                id_qr = decoded[0].data.decode("utf-8")
                st.success(f"ID detectado: {id_qr}")
            else:
                st.error("No se leyó el QR.")
        except Exception as e:
            st.error("Error técnico: Verifique 'packages.txt' en GitHub")

st.sidebar.markdown("---")
st.sidebar.caption(f"{COLEGIO} • {CREADOR}")
