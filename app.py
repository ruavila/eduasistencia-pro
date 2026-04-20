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
import urllib.parse

# ====================== CONFIGURACIÓN ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "I.E. San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)
conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, whatsapp TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
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
    if len(partes) <= 2: return nombre
    return " ".join([p[0].upper() + "." for p in partes[:-1]]) + " " + partes[-1]

# ====================== INTERFAZ ======================
st.set_page_config(page_title=APP_NAME, layout="wide")

# Estilo para evitar cierres inesperados en móvil
st.markdown("""
    <style>
    .stApp { max-width: 100%; }
    @media (max-width: 640px) {
        .main .block-container { padding: 1rem 0.5rem; }
    }
    </style>
    """, unsafe_allow_html=True)

# Mantener la sesión activa
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None

# ====================== LOGIN ======================
if st.session_state.profesor_actual is None:
    col_escudo, col_titulo = st.columns([1, 3])
    with col_escudo:
        try: st.image(ESCUDO_PATH, width=100)
        except: pass
    with col_titulo:
        st.title(APP_NAME)
    
    tab1, tab2 = st.tabs(["Ingresar", "Registro"])
    with tab1:
        u = st.text_input("Usuario", key="u_login")
        p = st.text_input("Contraseña", type="password", key="p_login")
        if st.button("Entrar", type="primary"):
            res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p))).fetchone()
            if res:
                st.session_state.profesor_actual = u
                st.session_state.nombre_docente = res[0]
                st.rerun()
            else: st.error("Error de acceso")
    with tab2:
        nu = st.text_input("Nuevo Usuario")
        nn = st.text_input("Nombre Completo")
        np = st.text_input("Nueva Contraseña", type="password")
        if st.button("Registrar Docente"):
            try:
                conn.execute("INSERT INTO profesores VALUES (?,?,?)", (nu.strip(), hash_password(np), nn.strip()))
                conn.commit()
                st.success("Registrado. Ya puedes ingresar.")
            except: st.error("El usuario ya existe")
    st.stop()

# ====================== APP INICIADA ======================
profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

st.sidebar.title("Menú")
st.sidebar.write(f"👤 {nombre_docente}")
menu = st.sidebar.radio("Ir a:", ["Mis Cursos", "Cargar Alumnos/QR", "Escanear Asistencia", "Reportes", "Cerrar Sesión"])

if menu == "Cerrar Sesión":
    st.session_state.profesor_actual = None
    st.rerun()

# 1. MIS CURSOS
if menu == "Mis Cursos":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    st.table(df_cursos)
    
    st.subheader("➕ Agregar Curso")
    c1, c2 = st.columns(2)
    ng = c1.text_input("Grado (ej: 11-02)")
    nm = c2.text_input("Materia")
    if st.button("Guardar"):
        if ng and nm:
            conn.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, ng.upper(), nm))
            conn.commit()
            st.rerun()

# 2. CARGAR ALUMNOS (Optimizado para móvil)
elif menu == "Cargar Alumnos/QR":
    st.header("👥 Gestión de Alumnos")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if df_c.empty: st.warning("Crea un curso primero")
    else:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        # Tip para móviles
        st.info("📱 Si usas celular: selecciona el archivo y espera a que la barra de carga termine antes de tocar Guardar.")
        
        archivo = st.file_uploader("Subir Excel (.xlsx)", type=["xlsx"])
        if archivo:
            if st.button("💾 Guardar en Base de Datos"):
                try:
                    df = pd.read_excel(archivo)
                    df.columns = [c.lower().strip() for c in df.columns]
                    for _, r in df.iterrows():
                        ws = str(r['whatsapp']).split('.')[0] if 'whatsapp' in r else ""
                        conn.execute("INSERT OR REPLACE INTO estudiantes VALUES (?,?,?,?,?,?)", 
                                    (profesor, grado, materia, str(r['estudiante_id']), str(r['nombre']), ws))
                    conn.commit()
                    st.success("Lista cargada correctamente")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        st.markdown("---")
        if st.button("📄 Generar PDF de QRs"):
            alumnos = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre", conn, params=(profesor, grado, materia))
            if not alumnos.empty:
                buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
                x, y = 50, 750
                for _, alu in alumnos.iterrows():
                    qr = generar_qr(str(alu['estudiante_id']))
                    c.drawImage(ImageReader(qr), x, y-100, width=100, height=100)
                    c.setFont("Helvetica-Bold", 8); c.drawCentredString(x+50, y-112, abreviar_nombre(alu['nombre']))
                    c.setFont("Helvetica", 7); c.drawCentredString(x+50, y-122, f"{grado} - {materia}")
                    x += 185
                    if x > 500: x = 50; y -= 160
                    if y < 150: c.showPage(); y = 750
                c.save(); st.download_button("⬇️ Descargar PDF", buf.getvalue(), f"QR_{grado}.pdf")

# 3. ESCANEAR QR (Con botón Proceso Finalizado)
elif menu == "Escanear Asistencia":
    st.header("📸 Escáner")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Clase:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("Escanear QR")
        if foto:
            decoded = decode(np.array(Image.open(foto)))
            if decoded:
                eid = decoded[0].data.decode("utf-8").strip()
                alu = conn.execute("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND estudiante_id=?", (profesor, g, m, eid)).fetchone()
                if alu:
                    f, h = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")
                    try:
                        conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g, m, eid, f, h)); conn.commit()
                        st.success(f"✅ REGISTRADO: {alu[0]}")
                    except: st.warning("Ya tiene asistencia hoy")
        
        st.markdown("---")
        if st.button("🏁 PROCESO FINALIZADO", type="primary", use_container_width=True):
            hoy = datetime.now().strftime("%Y-%m-%d")
            total = pd.read_sql("SELECT estudiante_id, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", conn, params=(profesor, g, m))
            presentes = pd.read_sql("SELECT estudiante_id FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", conn, params=(profesor, g, m, hoy))
            ausentes = total[~total['estudiante_id'].isin(presentes['estudiante_id'])]
            
            if ausentes.empty: st.balloons(); st.success("¡Asistencia perfecta!")
            else:
                st.subheader(f"⚠️ Ausentes ({len(ausentes)})")
                for _, row in ausentes.iterrows():
                    nombre, tel = row['nombre'], str(row['whatsapp']).strip()
                    if tel and tel != "nan" and tel != "":
                        msg = f"Notificación: Estudiante {nombre} NO asistió a la clase de {m} el día {hoy}."
                        link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                        st.markdown(f"❌ {nombre} - [📲 Notificar]({link})")
                    else: st.write(f"❌ {nombre} (Sin WhatsApp)")

# 4. REPORTES
elif menu == "Reportes":
    st.header("📊 Reportes")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        data = pd.read_sql("SELECT e.nombre, a.fecha FROM asistencias a JOIN estudiantes e ON a.estudiante_id = e.estudiante_id AND a.profesor=e.profesor AND a.grado=e.grado AND a.materia=e.materia WHERE a.profesor=? AND a.grado=? AND a.materia=?", conn, params=(profesor, g, m))
        if not data.empty:
            df_p = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: "P", 0: "A"})
            st.dataframe(df_p)
        else: st.info("Sin datos")

st.sidebar.markdown("---")
st.sidebar.caption(f"{COLEGIO} - {CREADOR}")
