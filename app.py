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

if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None

# ====================== BASE DE DATOS (REPARACIÓN FORZADA) ======================
@st.cache_resource
def obtener_conexion():
    conn = sqlite3.connect("asistencia.db", check_same_thread=False)
    # 1. Intentar crear la tabla con todas las columnas desde cero
    conn.execute("""CREATE TABLE IF NOT EXISTS estudiantes (
                    profesor TEXT, grado TEXT, materia TEXT, 
                    estudiante_id TEXT, nombre TEXT, whatsapp TEXT, 
                    PRIMARY KEY (profesor, grado, materia, estudiante_id))""")
    
    # 2. Si la tabla ya existía sin whatsapp, forzar la columna
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(estudiantes)")
    columnas = [col[1] for col in cursor.fetchall()]
    if 'whatsapp' not in columnas:
        try:
            conn.execute("ALTER TABLE estudiantes ADD COLUMN whatsapp TEXT DEFAULT ''")
            conn.commit()
        except Exception as e:
            st.error(f"Error crítico al actualizar base de datos: {e}")
            
    # 3. Crear el resto de tablas
    conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
    conn.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))")
    conn.commit()
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
    st.header("🔑 Acceso Docente")
    tab1, tab2 = st.tabs(["Ingresar", "Registrarse"])
    with tab1:
        u = st.text_input("Usuario", key="u_login")
        p = st.text_input("Contraseña", type="password", key="p_login")
        if st.button("Entrar", type="primary"):
            res = db.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", (u, hash_password(p))).fetchone()
            if res:
                st.session_state.profesor_actual, st.session_state.nombre_docente = u, res[0]
                st.rerun()
            else: st.error("Usuario o clave incorrectos")
    with tab2:
        nu, nn, np = st.text_input("Nuevo Usuario"), st.text_input("Nombre Completo"), st.text_input("Clave", type="password")
        if st.button("Crear Cuenta"):
            try:
                db.execute("INSERT INTO profesores VALUES (?,?,?)", (nu, hash_password(np), nn))
                db.commit(); st.success("Cuenta creada correctamente")
            except: st.error("El usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
menu = st.sidebar.selectbox("Menú:", ["1. Mis Cursos", "2. Cargar Estudiantes", "3. Escanear QR", "4. Reportes", "5. Salir"])

if menu == "5. Salir":
    st.session_state.profesor_actual = None
    st.rerun()

# ====================== 1. MIS CURSOS ======================
if menu == "1. Mis Cursos":
    st.header("📚 Gestión de Cursos")
    df_cursos = pd.read_sql("SELECT grado AS 'GRADO', materia AS 'MATERIA' FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if not df_cursos.empty:
        st.dataframe(df_cursos, use_container_width=True)
        st.subheader("🗑️ Eliminar Curso")
        opc = [f"{r['GRADO']} - {r['MATERIA']}" for _, r in df_cursos.iterrows()]
        sel_del = st.selectbox("Curso a borrar", opc)
        if st.button("Confirmar Eliminación"):
            g, m = [x.strip() for x in sel_del.split("-")]
            db.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            db.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            db.commit(); st.rerun()

    st.subheader("➕ Nuevo Curso")
    c1, c2 = st.columns(2)
    ng, nm = c1.text_input("Grado"), c2.text_input("Materia")
    if st.button("Añadir Curso"):
        if ng and nm:
            db.execute("INSERT INTO docentes_cursos VALUES (?,?,?)", (profesor, ng.upper(), nm))
            db.commit(); st.rerun()

# ====================== 2. CARGAR ESTUDIANTES ======================
elif menu == "2. Cargar Estudiantes":
    st.header("👥 Carga de Alumnos")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso destino:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split("-")]
        
        archivo = st.file_uploader("Subir Excel", type=["xlsx", "csv"])
        if archivo and st.button("🚀 Iniciar Carga"):
            try:
                df = pd.read_excel(archivo) if archivo.name.endswith('.xlsx') else pd.read_csv(archivo)
                df.columns = [c.lower().strip() for c in df.columns]
                
                # Verificamos si la columna existe antes de intentar guardarla
                cursor = db.cursor()
                cursor.execute("PRAGMA table_info(estudiantes)")
                tiene_ws = 'whatsapp' in [col[1] for col in cursor.fetchall()]

                for _, r in df.iterrows():
                    eid = str(r['estudiante_id']).split('.')[0]
                    nom = str(r['nombre']).strip()
                    ws = str(r.get('whatsapp', '')).split('.')[0] if 'whatsapp' in df.columns else ""
                    
                    if tiene_ws:
                        db.execute("""INSERT OR REPLACE INTO estudiantes 
                                   (profesor, grado, materia, estudiante_id, nombre, whatsapp) 
                                   VALUES (?,?,?,?,?,?)""", (profesor, grado, materia, eid, nom, ws))
                    else:
                        db.execute("""INSERT OR REPLACE INTO estudiantes 
                                   (profesor, grado, materia, estudiante_id, nombre) 
                                   VALUES (?,?,?,?,?)""", (profesor, grado, materia, eid, nom))
                db.commit(); st.success("Carga finalizada con éxito")
            except Exception as e: st.error(f"Error al procesar: {e}")
            
        if st.button("📄 Generar PDF de Carnets QR"):
            alumnos = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre", db, params=(profesor, grado, materia))
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

# ====================== 3. ESCANEAR ASISTENCIA ======================
elif menu == "3. Escanear QR":
    st.header("📸 Registro con Cámara")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Clase actual:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        
        foto = st.camera_input("Capturar QR del estudiante")
        if foto:
            dec = decode(np.array(Image.open(foto)))
            if dec:
                eid = dec[0].data.decode("utf-8").strip()
                alu = db.execute("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND estudiante_id=?", (profesor, g, m, eid)).fetchone()
                if alu:
                    hoy, ahora = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")
                    try:
                        db.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g, m, eid, hoy, ahora))
                        db.commit(); st.success(f"✅ REGISTRADO: {alu[0]}")
                    except: st.warning("El estudiante ya tiene registro el día de hoy.")

        st.markdown("---")
        if st.button("🏁 FINALIZAR Y VER AUSENTES", type="primary", use_container_width=True):
            hoy = datetime.now().strftime("%Y-%m-%d")
            total = pd.read_sql("SELECT estudiante_id, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", db, params=(profesor, g, m))
            asist = pd.read_sql("SELECT estudiante_id FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", db, params=(profesor, g, m, hoy))
            aus = total[~total['estudiante_id'].isin(asist['estudiante_id'])]
            
            if aus.empty: st.success("¡Asistencia perfecta! Todos los alumnos están presentes.")
            else:
                st.subheader(f"Estudiantes ausentes ({len(aus)})")
                for _, r in aus.iterrows():
                    tel = str(r['whatsapp']).strip()
                    if tel and tel != "nan":
                        msg = urllib.parse.quote(f"Aviso: El estudiante {r['nombre']} no asistió hoy a {m}.")
                        st.markdown(f"❌ {r['nombre']} - [📲 WhatsApp](https://wa.me/{tel}?text={msg})")

# ====================== 4. REPORTES ======================
elif menu == "4. Reportes":
    st.header("📊 Estadísticas")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", db, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Seleccione Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split("-")]
        data = pd.read_sql("""SELECT e.nombre, a.fecha FROM asistencias a 
                              JOIN estudiantes e ON a.estudiante_id = e.estudiante_id AND a.profesor = e.profesor
                              WHERE a.profesor=? AND a.grado=? AND a.materia=?""", db, params=(profesor, g, m))
        if not data.empty:
            piv = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: 'P', 0: 'A'})
            st.dataframe(piv, use_container_width=True)
            out = BytesIO(); piv.to_excel(out); st.download_button("📥 Descargar Reporte", out.getvalue(), "Asistencia.xlsx")
