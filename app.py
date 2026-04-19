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
# Se usa un nuevo nombre (v3) para asegurar que la base de datos se cree de cero en Streamlit Cloud
conn = sqlite3.connect("asistencia_v3.db", check_same_thread=False)

def inicializar_sistema():
    conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
    conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))")
    conn.commit()

inicializar_sistema()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generar_qr(texto):
    qr = qrcode.make(str(texto))
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def abreviar_nombre(nombre):
    partes = nombre.strip().split()
    if len(partes) <= 2: return nombre
    return " ".join([p[0].upper() + "." for p in partes[:-1]]) + " " + partes[-1]

# ====================== INTERFAZ ======================
st.set_page_config(page_title=APP_NAME, layout="wide")

col_escudo, col_titulo = st.columns([1, 4])
with col_escudo:
    try:
        st.image(Image.open(ESCUDO_PATH), width=130)
    except:
        st.title("🏫")

with col_titulo:
    st.markdown(f"""
        <h1 style='margin-bottom:0; color:#1E3A8A;'>{APP_NAME}</h1>
        <h3 style='margin-top:5px; color:#334155;'>{APP_SUBTITLE}</h3>
        <p style='color:#64748B;'>{COLEGIO} • Creado por {CREADOR}</p>
    """, unsafe_allow_html=True)

# ====================== LOGIN ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None

if st.session_state.profesor_actual is None:
    st.header("🔑 Acceso")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    with tab1:
        u = st.text_input("Usuario", key="l_u")
        p = st.text_input("Contraseña", type="password", key="l_p")
        if st.button("Ingresar", type="primary"):
            res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p))).fetchone()
            if res:
                st.session_state.profesor_actual = u
                st.session_state.nombre_docente = res[0]
                st.rerun()
            else: st.error("Credenciales incorrectas")
    with tab2:
        nu = st.text_input("Nuevo Usuario")
        nn = st.text_input("Nombre Completo")
        np_ = st.text_input("Nueva Contraseña", type="password")
        if st.button("Registrar"):
            try:
                conn.execute("INSERT INTO profesores VALUES (?,?,?)", (nu, hash_password(np_), nn))
                conn.commit()
                st.success("¡Registro exitoso!")
            except: st.error("El usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
st.sidebar.success(f"Docente: {st.session_state.nombre_docente}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.profesor_actual = None
    st.rerun()

menu = st.sidebar.selectbox("Menú", ["1. Mis Cursos", "2. Estudiantes y PDF", "3. Escanear QR", "4. Reportes"])

# 1. CURSOS
if menu == "1. Mis Cursos":
    st.header("📚 Gestión de Cursos")
    # Uso de lista [profesor] para evitar errores de base de datos en Pandas 
    df = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=[profesor])
    st.subheader("Tus cursos actuales")
    st.dataframe(df, use_container_width=True)
    
    with st.expander("➕ Agregar Nuevo Curso"):
        g = st.text_input("Grado (ej: 601)")
        m = st.text_input("Materia")
        if st.button("Guardar Curso"):
            if g and m:
                conn.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, g.upper(), m))
                conn.commit()
                st.rerun()

# 2. ESTUDIANTES
elif menu == "2. Estudiantes y PDF":
    st.header("👥 Estudiantes")
    cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=[profesor])
    if cursos.empty: st.warning("Primero crea un curso")
    else:
        opciones = [f"{r.grado} - {r.materia}" for _, r in cursos.iterrows()]
        sel = st.selectbox("Selecciona Curso", opciones)
        grado, materia = [x.strip() for x in sel.split("-")]
        
        archivo = st.file_uploader("Cargar Excel (.xlsx)", type=["xlsx"])
        if archivo and st.button("Procesar Lista"):
            df_s = pd.read_excel(archivo)
            df_s.columns = [c.lower().strip() for c in df_s.columns]
            for _, r in df_s.iterrows():
                try:
                    conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)", (profesor, grado, materia, str(r['id']), r['nombre']))
                except: pass
            conn.commit()
            st.success("Estudiantes cargados correctamente")

        if st.button("📄 Generar PDF de Códigos QR"):
            estud = pd.read_sql("SELECT * FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", conn, params=[profesor, grado, materia])
            if not estud.empty:
                buf = BytesIO()
                can = canvas.Canvas(buf, pagesize=A4)
                for i, r in estud.iterrows():
                    if i > 0 and i % 6 == 0: can.showPage()
                    qr = generar_qr(r['estudiante_id'])
                    pos_y = 700 - ((i % 6) * 110)
                    can.drawImage(ImageReader(qr), 50, pos_y, width=90, height=90)
                    can.drawString(150, pos_y + 45, f"{r['nombre']}")
                    can.drawString(150, pos_y + 30, f"{grado} - {materia}")
                can.save()
                st.download_button("Descargar PDF", buf.getvalue(), f"QRs_{grado}.pdf")

# 3. ESCANEAR
elif menu == "3. Escanear QR":
    st.header("📸 Escáner de Asistencia")
    cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=[profesor])
    if not cursos.empty:
        sel = st.selectbox("Curso", [f"{r.grado} - {r.materia}" for _, r in cursos.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("Capturar QR del estudiante")
        if foto:
            img = Image.open(foto)
            # Conversión necesaria a numpy array para pyzbar 
            dec = decode(np.array(img))
            if dec:
                eid = dec[0].data.decode('utf-8').strip()
                try:
                    conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", 
                                (profesor, grado, materia, eid, datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")))
                    conn.commit()
                    st.success(f"✅ Asistencia registrada: {eid}")
                    st.balloons()
                except: st.warning("El estudiante ya fue registrado el día de hoy")
            else: st.error("No se detectó ningún código QR. Intente de nuevo.")

# 4. REPORTES
elif menu == "4. Reportes":
    st.header("📊 Reporte General")
    df_rep = pd.read_sql("""
        SELECT e.nombre, a.grado, a.materia, a.fecha, a.hora_registro 
        FROM asistencias a JOIN estudiantes e ON a.estudiante_id = e.estudiante_id 
        AND a.profesor=e.profesor AND a.grado=e.grado AND a.materia=e.materia
        WHERE a.profesor=?
    """, conn, params=[profesor])
    
    st.dataframe(df_rep, use_container_width=True)
    
    if not df_rep.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_rep.to_excel(writer, index=False)
        st.download_button("📥 Descargar Reporte Excel", output.getvalue(), "asistencia_total.xlsx")

st.markdown("---")
st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")
