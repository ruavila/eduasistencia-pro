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
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
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

col_escudo, col_titulo = st.columns([1, 4])
with col_escudo:
    try: st.image(Image.open(ESCUDO_PATH), width=130)
    except: pass

with col_titulo:
    st.markdown(f"""
        <h1 style='margin-bottom:0; color:#1E3A8A;'>{APP_NAME}</h1>
        <h3 style='margin-top:5px; color:#334155;'>{APP_SUBTITLE}</h3>
        <p style='color:#64748B; font-size:1.05em;'>{COLEGIO} • Creado por {CREADOR}</p>
    """, unsafe_allow_html=True)

st.markdown("<hr style='margin: 25px 0;'>", unsafe_allow_html=True)

# ====================== LOGIN ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
    st.session_state.nombre_docente = None

if st.session_state.profesor_actual is None:
    st.header("🔑 Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    with tab1:
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", type="primary"):
            res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p))).fetchone()
            if res:
                st.session_state.profesor_actual, st.session_state.nombre_docente = u, res[0]
                st.rerun()
            else: st.error("Credenciales incorrectas")
    with tab2:
        nu, nn, np = st.text_input("Nuevo Usuario"), st.text_input("Nombre Completo"), st.text_input("Contraseña Nueva", type="password")
        if st.button("Registrarse"):
            try:
                conn.execute("INSERT INTO profesores VALUES (?,?,?)", (nu.strip(), hash_password(np), nn.strip()))
                conn.commit()
                st.success("Usuario creado exitosamente")
            except: st.error("El usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

st.sidebar.success(f"✅ Docente: {nombre_docente}")
menu = st.sidebar.selectbox("Menú principal:", ["1. Mis Cursos", "2. Gestión Estudiantes", "3. Escanear QR", "4. Reportes", "5. Reiniciar Datos"])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.profesor_actual = None
    st.rerun()

# ====================== 1. MIS CURSOS ======================
if menu == "1. Mis Cursos":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado AS 'GRADO', materia AS 'MATERIA' FROM docentes_cursos WHERE profesor=? ORDER BY grado", conn, params=(profesor,))
    
    if not df_cursos.empty:
        st.subheader("Cursos Registrados")
        st.dataframe(df_cursos, use_container_width=True)
        
        st.subheader("🗑️ Eliminar Curso")
        opc = [f"{r['GRADO']} - {r['MATERIA']}" for _, r in df_cursos.iterrows()]
        sel_del = st.selectbox("Curso a eliminar", opc)
        conf_del = st.checkbox(f"Confirmar eliminación de {sel_del}")
        if st.button("Eliminar", disabled=not conf_del):
            g, m = [x.strip() for x in sel_del.split("-")]
            conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            conn.commit()
            st.rerun()
    
    st.subheader("➕ Agregar Curso")
    c1, c2 = st.columns(2)
    ng, nm = c1.text_input("Grado"), c2.text_input("Materia")
    if st.button("Guardar Curso"):
        if ng and nm:
            try:
                conn.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, ng.upper(), nm))
                conn.commit(); st.rerun()
            except: st.error("Ya existe este curso")

# ====================== 2. ESTUDIANTES ======================
elif menu == "2. Gestión Estudiantes":
    st.header("👥 Gestión de Alumnos")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if df_c.empty: st.warning("Agregue un curso primero")
    else:
        sel = st.selectbox("Seleccione Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        archivo = st.file_uploader("Subir Excel (.xlsx) con: estudiante_id, nombre, whatsapp", type=["xlsx"])
        if archivo and st.button("💾 Cargar Estudiantes"):
            df = pd.read_excel(archivo)
            df.columns = [c.lower().strip() for c in df.columns]
            for _, r in df.iterrows():
                ws = str(r['whatsapp']).split('.')[0] if 'whatsapp' in r else ""
                conn.execute("INSERT OR REPLACE INTO estudiantes VALUES (?,?,?,?,?,?)", 
                            (profesor, grado, materia, str(r['estudiante_id']), str(r['nombre']), ws))
            conn.commit(); st.success("Estudiantes cargados con éxito")
            
        if st.button("📄 Generar PDF de Carnets QR"):
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

# ====================== 3. ESCANEAR QR ======================
elif menu == "3. Escanear QR":
    st.header("📸 Registro de Asistencia")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("Enfoque el código QR")
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
                    except: st.warning("Este estudiante ya registró asistencia hoy")
                else: st.error("Estudiante no pertenece a este curso")
        
        st.markdown("---")
        if st.button("🏁 PROCESO FINALIZADO", type="primary", use_container_width=True):
            hoy = datetime.now().strftime("%Y-%m-%d")
            total = pd.read_sql("SELECT estudiante_id, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", conn, params=(profesor, g, m))
            presentes = pd.read_sql("SELECT estudiante_id FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", conn, params=(profesor, g, m, hoy))
            ausentes = total[~total['estudiante_id'].isin(presentes['estudiante_id'])]
            
            if ausentes.empty: st.balloons(); st.success("¡Asistencia perfecta!")
            else:
                st.subheader(f"⚠️ Reporte de Inasistencia ({len(ausentes)})")
                for _, row in ausentes.iterrows():
                    nombre, tel = row['nombre'], str(row['whatsapp']).strip()
                    if tel and tel != "nan" and tel != "":
                        msg = f"Hola, notificamos que el estudiante {nombre} no asistió a la clase de {m} hoy {hoy} a las {datetime.now().strftime('%H:%M')}."
                        link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"❌ {nombre}")
                        c2.markdown(f"[📲 Notificar]({link})")
                    else: st.write(f"❌ {nombre} (Sin WhatsApp)")

# ====================== 4. REPORTES ======================
elif menu == "4. Reportes":
    st.header("📊 Reporte Consolidado")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Ver Reporte de:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        data = pd.read_sql("""SELECT e.nombre, a.fecha FROM asistencias a JOIN estudiantes e 
                              ON a.estudiante_id = e.estudiante_id AND a.profesor=e.profesor AND a.grado=e.grado AND a.materia=e.materia 
                              WHERE a.profesor=? AND a.grado=? AND a.materia=?""", conn, params=(profesor, g, m))
        if not data.empty:
            df_p = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: "P", 0: "A"})
            st.dataframe(df_p, use_container_width=True)
            out = BytesIO(); df_p.to_excel(out); st.download_button("📥 Excel", out.getvalue(), f"Reporte_{g}.xlsx")
        else: st.info("Sin registros")

# ====================== 5. REINICIAR ======================
elif menu == "5. Reiniciar Datos":
    st.header("⚠️ Peligro")
    if st.checkbox("Deseo borrar TODOS mis datos"):
        if st.button("CONFIRMAR BORRADO"):
            conn.execute("DELETE FROM docentes_cursos WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM estudiantes WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM asistencias WHERE profesor=?", (profesor,))
            conn.commit(); st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(f"{APP_NAME} v2.5 • {COLEGIO}")
