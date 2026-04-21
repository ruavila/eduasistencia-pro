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
st.set_page_config(page_title="EduAsistencia Pro", layout="wide")

# Mantenemos la sesión activa de forma persistente
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None

# ====================== BASE DE DATOS ======================
# Usamos cache_resource para que la conexión no se pierda al subir archivos
@st.cache_resource
def obtener_conexion():
    conn = sqlite3.connect("asistencia.db", check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
    conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, whatsapp TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))")
    return conn

db = obtener_conexion()

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
    st.header("🔑 Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    with tab1:
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", type="primary"):
            res = db.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p))).fetchone()
            if res:
                st.session_state.profesor_actual = u
                st.session_state.nombre_docente = res[0]
                st.rerun()
            else: st.error("Usuario o contraseña incorrectos")
    with tab2:
        nu, nn, np = st.text_input("Nuevo Usuario"), st.text_input("Nombre"), st.text_input("Contraseña Nueva", type="password")
        if st.button("Registrar"):
            try:
                db.execute("INSERT INTO profesores VALUES (?,?,?)", (nu, hash_password(np), nn))
                db.commit(); st.success("Registrado exitosamente")
            except: st.error("El usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
st.sidebar.success(f"Docente: {st.session_state.nombre_docente}")
menu = st.sidebar.selectbox("Menú principal:", ["1. Mis Cursos", "2. Gestionar Estudiantes", "3. Escanear Asistencia", "4. Reportes", "5. Cerrar Sesión"])

if menu == "5. Cerrar Sesión":
    st.session_state.profesor_actual = None
    st.rerun()

# ====================== 1. MIS CURSOS ======================
if menu == "1. Mis Cursos":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado AS 'GRADO', materia AS 'MATERIA' FROM docentes_cursos WHERE profesor=? ORDER BY grado", db, params=(profesor,))
    
    if not df_cursos.empty:
        st.subheader("Cursos actuales (Tabla tipo Excel)")
        st.dataframe(df_cursos, use_container_width=True)

        st.subheader("🗑️ Eliminar un curso")
        opciones = [f"{r['GRADO']} - {r['MATERIA']}" for _, r in df_cursos.iterrows()]
        curso_sel = st.selectbox("Selecciona curso a borrar", opciones)
        confirmar = st.checkbox(f"Confirmo que deseo eliminar {curso_sel}")
        
        if st.button("Eliminar Seleccionado", type="secondary", disabled=not confirmar):
            g, m = [x.strip() for x in curso_sel.split("-")]
            db.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            db.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            db.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            db.commit(); st.rerun()
    
    st.subheader("➕ Añadir nuevo curso")
    c1, c2 = st.columns(2)
    ng, nm = c1.text_input("Grado"), c2.text_input("Materia")
    if st.button("Guardar Curso"):
        if ng and nm:
            try:
                db.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, ng.upper(), nm))
                db.commit(); st.rerun()
            except: st.error("El curso ya existe")

# ====================== 2. GESTIONAR ESTUDIANTES ======================
elif menu == "2. Gestionar Estudiantes":
    st.header("👥 Gestión de Estudiantes")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if df_c.empty: st.warning("Crea un curso primero")
    else:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        # CORRECCIÓN DEL ERROR EN MÓVIL: Procesamiento directo
        archivo = st.file_uploader("Subir Excel (.xlsx) con: estudiante_id, nombre, whatsapp", type=["xlsx", "csv"])
        if archivo:
            if st.button("💾 Cargar Lista al Sistema"):
                try:
                    # Leemos el archivo y limpiamos memoria inmediatamente después
                    df_temp = pd.read_excel(archivo) if archivo.name.endswith('.xlsx') else pd.read_csv(archivo)
                    df_temp.columns = [c.lower().strip() for c in df_temp.columns]
                    
                    for _, r in df_temp.iterrows():
                        eid = str(r['estudiante_id']).split('.')[0]
                        ws = str(r.get('whatsapp', '')).split('.')[0] if 'whatsapp' in df_temp.columns else ""
                        db.execute("INSERT OR REPLACE INTO estudiantes VALUES (?,?,?,?,?,?)", 
                                  (profesor, grado, materia, eid, str(r['nombre']), ws))
                    db.commit()
                    st.success(f"✅ Se cargaron {len(df_temp)} estudiantes.")
                    del df_temp # Liberamos memoria RAM
                except Exception as e:
                    st.error(f"Error al leer el archivo: {e}")
        
        if st.button("📄 Generar PDF con QR"):
            alumnos = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre", db, params=(profesor, grado, materia))
            if not alumnos.empty:
                pdf_buf = BytesIO(); c = canvas.Canvas(pdf_buf, pagesize=A4)
                x, y = 50, 750
                for _, alu in alumnos.iterrows():
                    qr_img = generar_qr(str(alu['estudiante_id']))
                    c.drawImage(ImageReader(qr_img), x, y-100, width=100, height=100)
                    c.setFont("Helvetica-Bold", 8); c.drawCentredString(x+50, y-112, abreviar_nombre(alu['nombre']))
                    c.setFont("Helvetica", 7); c.drawCentredString(x+50, y-122, f"{grado} - {materia}")
                    x += 180
                    if x > 500: x = 50; y -= 160
                    if y < 150: c.showPage(); y = 750
                c.save(); st.download_button("⬇️ Descargar PDF", pdf_buf.getvalue(), f"QR_{grado}.pdf")

# ====================== 3. ESCANEAR ASISTENCIA ======================
elif menu == "3. Escanear Asistencia":
    st.header("📸 Escáner")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("Escanee el código QR")
        if foto:
            decoded = decode(np.array(Image.open(foto)))
            if decoded:
                eid = decoded[0].data.decode("utf-8").strip()
                alu = db.execute("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND estudiante_id=?", (profesor, g, m, eid)).fetchone()
                if alu:
                    hoy, ahora = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")
                    try:
                        db.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g, m, eid, hoy, ahora))
                        db.commit(); st.success(f"✅ ASISTENCIA: {alu[0]}")
                    except: st.warning("Ya registrado hoy.")
                else: st.error("Estudiante no pertenece a este curso")
        
        st.markdown("---")
        if st.button("🏁 PROCESO FINALIZADO", type="primary", use_container_width=True):
            hoy = datetime.now().strftime("%Y-%m-%d")
            total = pd.read_sql("SELECT estudiante_id, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", db, params=(profesor, g, m))
            asistieron = pd.read_sql("SELECT estudiante_id FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", db, params=(profesor, g, m, hoy))
            ausentes = total[~total['estudiante_id'].isin(asistieron['id_estudiante'] if 'id_estudiante' in asistieron else asistieron['estudiante_id'])]
            
            if ausentes.empty: st.success("¡Asistencia completa!")
            else:
                st.subheader(f"⚠️ Ausentes ({len(ausentes)})")
                for _, r in ausentes.iterrows():
                    tel = str(r['whatsapp']).strip()
                    if tel and tel != "nan":
                        msg = urllib.parse.quote(f"Hola, el estudiante {r['nombre']} no asistió hoy a la clase de {m}.")
                        st.markdown(f"❌ {r['nombre']} - [📲 Notificar WhatsApp](https://wa.me/{tel}?text={msg})")
                    else: st.write(f"❌ {r['nombre']} (Sin número)")

# ====================== 4. REPORTES ======================
elif menu == "4. Reportes":
    st.header("📊 Reportes")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        data = pd.read_sql("""SELECT e.nombre, a.fecha FROM asistencias a JOIN estudiantes e 
                              ON a.estudiante_id = e.estudiante_id AND a.profesor = e.profesor
                              WHERE a.profesor=? AND a.grado=? AND a.materia=?""", db, params=(profesor, g, m))
        if not data.empty:
            piv = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: 'P', 0: 'A'})
            st.dataframe(piv, use_container_width=True)
            out = BytesIO(); piv.to_excel(out); st.download_button("📥 Descargar Excel", out.getvalue(), "Reporte.xlsx")
