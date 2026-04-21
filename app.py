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
import time

# ====================== CONFIGURACIÓN ======================
st.set_page_config(page_title="EduAsistencia Pro", layout="wide")

if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None

# ====================== FUNCIONES DE BASE DE DATOS ======================
def ejecutar_query(query, params=(), commit=False, select=False):
    """Maneja la apertura y cierre de conexiones de forma segura para evitar bloqueos"""
    # El timeout de 20 segundos ayuda a evitar el error 'database is locked'
    conn = sqlite3.connect("asistencia.db", timeout=20, check_same_thread=False)
    cursor = conn.cursor()
    resultado = None
    try:
        cursor.execute(query, params)
        if commit:
            conn.commit()
        if select:
            resultado = cursor.fetchall()
    except Exception as e:
        if commit: conn.rollback()
        raise e
    finally:
        conn.close()
    return resultado

# Inicialización de tablas al arrancar
def inicializar_sistema():
    # Crear tablas una por una
    ejecutar_query("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)", commit=True)
    ejecutar_query("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))", commit=True)
    ejecutar_query("""CREATE TABLE IF NOT EXISTS estudiantes (
                    profesor TEXT, grado TEXT, materia TEXT, 
                    estudiante_id TEXT, nombre TEXT, whatsapp TEXT, 
                    PRIMARY KEY (profesor, grado, materia, estudiante_id))""", commit=True)
    ejecutar_query("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))", commit=True)
    
    # Verificar columna whatsapp de forma segura
    conn = sqlite3.connect("asistencia.db", timeout=20)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(estudiantes)")
    columnas = [col[1] for col in cursor.fetchall()]
    conn.close()
    
    if 'whatsapp' not in columnas:
        try:
            ejecutar_query("ALTER TABLE estudiantes ADD COLUMN whatsapp TEXT DEFAULT ''", commit=True)
        except:
            pass # Ya existe o error menor

inicializar_sistema()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generar_qr(texto):
    qr = qrcode.make(texto)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def abreviar_nombre(nombre):
    partes = str(nombre).strip().split()
    if len(partes) <= 2: return nombre
    return " ".join([p[0].upper() + "." for p in partes[:-1]]) + " " + partes[-1]

# ====================== LOGIN ======================
if st.session_state.profesor_actual is None:
    st.header("🔑 Acceso Docente")
    tab1, tab2 = st.tabs(["Ingresar", "Registrarse"])
    with tab1:
        u = st.text_input("Usuario", key="u_login")
        p = st.text_input("Contraseña", type="password", key="p_login")
        if st.button("Entrar", type="primary"):
            res = ejecutar_query("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p)), select=True)
            if res:
                st.session_state.profesor_actual, st.session_state.nombre_docente = u, res[0][0]
                st.rerun()
            else: st.error("Credenciales incorrectas")
    with tab2:
        nu, nn, np = st.text_input("Nuevo Usuario"), st.text_input("Nombre Completo"), st.text_input("Clave", type="password")
        if st.button("Crear Cuenta"):
            try:
                ejecutar_query("INSERT INTO profesores VALUES (?,?,?)", (nu, hash_password(np), nn), commit=True)
                st.success("Cuenta creada")
            except: st.error("El usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
menu = st.sidebar.selectbox("Menú:", ["1. Mis Cursos", "2. Cargar Estudiantes", "3. Escanear QR", "4. Reportes", "5. Salir"])

if menu == "5. Salir":
    st.session_state.profesor_actual = None
    st.rerun()

# ====================== 1. MIS CURSOS ======================
if menu == "1. Mis Cursos":
    st.header("📚 Mis Cursos")
    conn = sqlite3.connect("asistencia.db")
    df_cursos = pd.read_sql("SELECT grado AS 'GRADO', materia AS 'MATERIA' FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    conn.close()
    
    if not df_cursos.empty:
        st.dataframe(df_cursos, use_container_width=True)
        st.subheader("🗑️ Eliminar")
        opc = [f"{r['GRADO']} - {r['MATERIA']}" for _, r in df_cursos.iterrows()]
        sel_del = st.selectbox("Seleccione", opc)
        if st.button("Borrar Curso"):
            g, m = [x.strip() for x in sel_del.split("-")]
            ejecutar_query("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m), commit=True)
            ejecutar_query("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m), commit=True)
            st.rerun()

    st.subheader("➕ Nuevo Curso")
    c1, c2 = st.columns(2)
    ng, nm = c1.text_input("Grado"), c2.text_input("Materia")
    if st.button("Añadir"):
        if ng and nm:
            ejecutar_query("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, ng.upper(), nm), commit=True)
            st.rerun()

# ====================== 2. CARGAR ESTUDIANTES ======================
elif menu == "2. Cargar Estudiantes":
    st.header("👥 Carga de Alumnos")
    conn = sqlite3.connect("asistencia.db")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    conn.close()
    
    if not df_c.empty:
        sel = st.selectbox("Curso destino:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        archivo = st.file_uploader("Subir Excel", type=["xlsx", "csv"])
        if archivo and st.button("🚀 Cargar"):
            try:
                df = pd.read_excel(archivo) if archivo.name.endswith('.xlsx') else pd.read_csv(archivo)
                df.columns = [c.lower().strip() for c in df.columns]
                for _, r in df.iterrows():
                    eid = str(r['estudiante_id']).split('.')[0]
                    nom = str(r['nombre']).strip()
                    ws = str(r.get('whatsapp', '')).split('.')[0] if 'whatsapp' in df.columns else ""
                    ejecutar_query("""INSERT OR REPLACE INTO estudiantes 
                                   (profesor, grado, materia, estudiante_id, nombre, whatsapp) 
                                   VALUES (?,?,?,?,?,?)""", (profesor, grado, materia, eid, nom, ws), commit=True)
                st.success("Carga exitosa")
            except Exception as e: st.error(f"Error: {e}")
            
        if st.button("📄 Generar PDF"):
            conn = sqlite3.connect("asistencia.db")
            alumnos = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre", conn, params=(profesor, grado, materia))
            conn.close()
            if not alumnos.empty:
                buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
                x, y = 50, 750
                for _, alu in alumnos.iterrows():
                    qr = generar_qr(str(alu['estudiante_id']))
                    c.drawImage(ImageReader(qr), x, y-100, width=90, height=90)
                    c.setFont("Helvetica-Bold", 8); c.drawCentredString(x+45, y-110, abreviar_nombre(alu['nombre']))
                    x += 185
                    if x > 500: x = 50; y -= 160
                    if y < 150: c.showPage(); y = 750
                c.save(); st.download_button("⬇️ Descargar PDF", buf.getvalue(), f"QR_{grado}.pdf")

# ====================== 3. ESCANEAR QR ======================
elif menu == "3. Escanear QR":
    st.header("📸 Escáner")
    conn = sqlite3.connect("asistencia.db")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    conn.close()
    
    if not df_c.empty:
        sel = st.selectbox("Clase:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("QR Estudiante")
        if foto:
            dec = decode(np.array(Image.open(foto)))
            if dec:
                eid = dec[0].data.decode("utf-8").strip()
                alu = ejecutar_query("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND estudiante_id=?", (profesor, g, m, eid), select=True)
                if alu:
                    hoy, ahora = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")
                    try:
                        ejecutar_query("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g, m, eid, hoy, ahora), commit=True)
                        st.success(f"✅ {alu[0][0]}")
                    except: st.warning("Ya registrado")

        st.markdown("---")
        if st.button("🏁 VER AUSENTES"):
            hoy = datetime.now().strftime("%Y-%m-%d")
            conn = sqlite3.connect("asistencia.db")
            total = pd.read_sql("SELECT estudiante_id, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", conn, params=(profesor, g, m))
            asist = pd.read_sql("SELECT estudiante_id FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", conn, params=(profesor, g, m, hoy))
            conn.close()
            aus = total[~total['estudiante_id'].isin(asist['estudiante_id'])]
            for _, r in aus.iterrows():
                tel = str(r['whatsapp']).strip()
                if tel and tel != "nan":
                    msg = urllib.parse.quote(f"Aviso: {r['nombre']} no asistió hoy a {m}.")
                    st.markdown(f"❌ {r['nombre']} - [📲 WhatsApp](https://wa.me/{tel}?text={msg})")

# ====================== 4. REPORTES ======================
elif menu == "4. Reportes":
    st.header("📊 Reportes")
    conn = sqlite3.connect("asistencia.db")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        data = pd.read_sql("""SELECT e.nombre, a.fecha FROM asistencias a 
                              JOIN estudiantes e ON a.estudiante_id = e.estudiante_id AND a.profesor = e.profesor
                              WHERE a.profesor=? AND a.grado=? AND a.materia=?""", conn, params=(profesor, g, m))
        conn.close()
        if not data.empty:
            piv = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: 'P', 0: 'A'})
            st.dataframe(piv, use_container_width=True)
