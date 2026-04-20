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
    partes = str(nombre).strip().split()
    if len(partes) <= 2: return nombre
    return " ".join([p[0].upper() + "." for p in partes[:-1]]) + " " + partes[-1]

# ====================== PERSISTENCIA DE SESIÓN ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None

st.set_page_config(page_title=APP_NAME, layout="wide")

# ====================== LOGIN ======================
if st.session_state.profesor_actual is None:
    st.title(f"🚀 {APP_NAME}")
    tab1, tab2 = st.tabs(["Ingresar", "Registrarse"])
    
    with tab1:
        u = st.text_input("Usuario", key="login_u")
        p = st.text_input("Contraseña", type="password", key="login_p")
        if st.button("Entrar", type="primary"):
            res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p))).fetchone()
            if res:
                st.session_state.profesor_actual = u
                st.session_state.nombre_docente = res[0]
                st.rerun()
            else: st.error("Usuario o clave incorrectos")
    with tab2:
        nu = st.text_input("Nuevo Usuario")
        nn = st.text_input("Nombre Completo")
        np = st.text_input("Clave", type="password")
        if st.button("Crear Cuenta"):
            try:
                conn.execute("INSERT INTO profesores VALUES (?,?,?)", (nu.strip(), hash_password(np), nn.strip()))
                conn.commit()
                st.success("¡Cuenta creada!")
            except: st.error("El usuario ya existe")
    st.stop()

# ====================== APP PRINCIPAL ======================
profesor = st.session_state.profesor_actual
st.sidebar.title(f"Hola, {st.session_state.nombre_docente}")
menu = st.sidebar.radio("Menú", ["1. Mis Cursos", "2. Cargar Estudiantes", "3. Escanear QR", "4. Reportes", "5. Salir"])

if menu == "5. Salir":
    st.session_state.profesor_actual = None
    st.rerun()

# 1. MIS CURSOS
if menu == "1. Mis Cursos":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado AS 'GRADO', materia AS 'MATERIA' FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    st.dataframe(df_cursos, use_container_width=True)
    
    with st.expander("➕ Agregar Nuevo Curso"):
        ng = st.text_input("Grado")
        nm = st.text_input("Materia")
        if st.button("Guardar Curso"):
            if ng and nm:
                conn.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, ng.upper(), nm))
                conn.commit()
                st.rerun()

# 2. CARGAR ESTUDIANTES (VERSIÓN ROBUSTA)
elif menu == "2. Cargar Estudiantes":
    st.header("👥 Carga de Alumnos")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if df_c.empty: st.warning("Primero crea un curso en el Menú 1")
    else:
        sel = st.selectbox("Seleccione Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        st.info("📱 Si el Excel falla en el celular, usa un archivo CSV.")
        archivo = st.file_uploader("Archivo (estudiante_id, nombre, whatsapp)", type=["xlsx", "csv"])
        
        if archivo:
            if st.button("💾 GUARDAR LISTA"):
                try:
                    if archivo.name.endswith('.csv'):
                        df = pd.read_csv(archivo)
                    else:
                        df = pd.read_excel(archivo, engine='openpyxl')
                    
                    df.columns = [str(c).lower().strip() for c in df.columns]
                    
                    for _, r in df.iterrows():
                        eid = str(r['estudiante_id']).split('.')[0]
                        nom = str(r['nombre']).strip()
                        ws = str(r.get('whatsapp', '')).split('.')[0] if 'whatsapp' in df.columns else ""
                        conn.execute("INSERT OR REPLACE INTO estudiantes VALUES (?,?,?,?,?,?)", (profesor, grado, materia, eid, nom, ws))
                    conn.commit()
                    st.success(f"✅ Cargados {len(df)} estudiantes correctamente.")
                except Exception as e:
                    st.error(f"Error al leer archivo: {e}")

        st.markdown("---")
        if st.button("📄 GENERAR PDF DE CÓDIGOS QR"):
            alumnos = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre", conn, params=(profesor, grado, materia))
            if not alumnos.empty:
                buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
                x, y = 50, 750
                for _, alu in alumnos.iterrows():
                    qr_img = generar_qr(str(alu['estudiante_id']))
                    c.drawImage(ImageReader(qr_img), x, y-100, width=100, height=100)
                    c.setFont("Helvetica-Bold", 8); c.drawCentredString(x+50, y-112, abreviar_nombre(alu['nombre']))
                    c.setFont("Helvetica", 7); c.drawCentredString(x+50, y-122, f"{grado} - {materia}")
                    x += 185
                    if x > 500: x = 50; y -= 160
                    if y < 150: c.showPage(); y = 750
                c.save(); st.download_button("⬇️ Descargar PDF", buf.getvalue(), f"QR_{grado}.pdf")

# 3. ESCANEAR (CÁMARA + PROCESO FINALIZADO)
elif menu == "3. Escanear QR":
    st.header("📸 Escáner de Asistencia")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso actual:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("Enfoque el QR del estudiante")
        if foto:
            decoded = decode(np.array(Image.open(foto)))
            if decoded:
                eid = decoded[0].data.decode("utf-8").strip()
                alu = conn.execute("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND estudiante_id=?", (profesor, g, m, eid)).fetchone()
                if alu:
                    f, h = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")
                    try:
                        conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g, m, eid, f, h)); conn.commit()
                        st.success(f"✅ {alu[0]} REGISTRADO")
                    except: st.warning("Ya tiene asistencia hoy")
                else: st.error("Estudiante no registrado en este curso")
        
        st.markdown("---")
        if st.button("🏁 PROCESO FINALIZADO", type="primary", use_container_width=True):
            hoy = datetime.now().strftime("%Y-%m-%d")
            total = pd.read_sql("SELECT estudiante_id, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", conn, params=(profesor, g, m))
            asistieron = pd.read_sql("SELECT estudiante_id FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", conn, params=(profesor, g, m, hoy))
            ausentes = total[~total['estudiante_id'].isin(asistieron['estudiante_id'])]
            
            if ausentes.empty: st.balloons(); st.success("¡Asistencia perfecta!")
            else:
                st.subheader(f"⚠️ Estudiantes Ausentes ({len(ausentes)})")
                for _, row in ausentes.iterrows():
                    nombre, tel = row['nombre'], str(row['whatsapp']).strip()
                    if tel and tel != "nan" and tel != "":
                        mensaje = f"Notificación: El estudiante {nombre} no asistió hoy {hoy} a la clase de {m}."
                        link = f"https://wa.me/{tel}?text={urllib.parse.quote(mensaje)}"
                        st.markdown(f"❌ {nombre} - [📲 Enviar WhatsApp]({link})")
                    else: st.write(f"❌ {nombre} (Sin número)")

# 4. REPORTES
elif menu == "4. Reportes":
    st.header("📊 Reportes")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        data = pd.read_sql("""SELECT e.nombre, a.fecha FROM asistencias a 
                              JOIN estudiantes e ON a.estudiante_id = e.estudiante_id AND a.profesor=e.profesor AND a.grado=e.grado AND a.materia=e.materia 
                              WHERE a.profesor=? AND a.grado=? AND a.materia=?""", conn, params=(profesor, g, m))
        if not data.empty:
            pivot = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: "P", 0: "A"})
            st.dataframe(pivot, use_container_width=True)
            out = BytesIO(); pivot.to_excel(out); st.download_button("📥 Descargar Excel", out.getvalue(), f"Reporte_{g}.xlsx")
        else: st.info("No hay registros de asistencia.")

st.sidebar.markdown("---")
st.sidebar.caption(f"{COLEGIO} • v3.0")
