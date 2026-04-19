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
from pyzbar.pyzbar import decode
import numpy as np

# ====================== CONFIGURACIÓN ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
def inicializar_db():
    conn = sqlite3.connect("asistencia.db", check_same_thread=False)
    cursor = conn.cursor()
    # Crear tablas una por una con commit explícito
    cursor.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
    cursor.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id, fecha))")
    conn.commit()
    return conn

conn = inicializar_db()

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
    if len(partes) <= 2:
        return nombre
    iniciales = [p[0].upper() + "." for p in partes[:-1]]
    return " ".join(iniciales) + " " + partes[-1]

# ====================== INTERFAZ ======================
st.set_page_config(page_title=APP_NAME, layout="wide")

col_escudo, col_titulo = st.columns([1, 4])
with col_escudo:
    try:
        escudo = Image.open(ESCUDO_PATH)
        st.image(escudo, width=130)
    except:
        st.write("📌") # Icono si no hay escudo

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
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar", type="primary"):
            if username and password:
                password_hash = hash_password(password)
                res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", 
                                  (username, password_hash)).fetchone()
                if res:
                    st.session_state.profesor_actual = username
                    st.session_state.nombre_docente = res[0]
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")
    with tab2:
        nuevo_user = st.text_input("Usuario", key="reg_user")
        nuevo_nombre = st.text_input("Nombre completo", key="reg_nombre")
        nueva_pass = st.text_input("Contraseña", type="password", key="reg_pass")
        if st.button("Registrarse", type="primary"):
            if nuevo_user and nuevo_nombre and nueva_pass:
                try:
                    conn.execute("INSERT INTO profesores VALUES (?, ?, ?)", 
                                (nuevo_user.strip(), hash_password(nueva_pass), nuevo_nombre.strip()))
                    conn.commit()
                    st.success("Registro exitoso. Ahora inicia sesión.")
                except:
                    st.error("Ese usuario ya existe")
    st.stop()

profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

st.sidebar.success(f"✅ Docente: {nombre_docente}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.profesor_actual = None
    st.rerun()

menu = st.sidebar.selectbox("Menú principal:", [
    "1. Mis Cursos (Agregar / Eliminar)",
    "2. Gestionar Estudiantes y Generar PDF",
    "3. Escanear Asistencia con Cámara",
    "4. Reporte y Descargar Excel",
    "5. Reiniciar mis datos"
])

# 1. MIS CURSOS
if menu == "1. Mis Cursos (Agregar / Eliminar)":
    st.header("📚 Mis Cursos")
    # Corrección de parámetros para Pandas
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=? ORDER BY grado, materia", conn, params=[profesor])

    if not df_cursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(df_cursos, use_container_width=True)
        
        st.subheader("🗑️ Eliminar Curso")
        curso_elim = st.selectbox("Selecciona para eliminar", [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()])
        if st.button("Eliminar curso seleccionado"):
            if st.checkbox("Confirmar eliminación"):
                g, m = [x.strip() for x in curso_elim.split(" - ")]
                conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                conn.commit()
                st.success("Curso eliminado")
                st.rerun()
    else:
        st.info("No hay cursos registrados.")

    st.subheader("Agregar nuevo curso")
    c1, c2 = st.columns(2)
    ng = c1.text_input("Grado (Ej: 6-1)")
    nm = c2.text_input("Materia")
    if st.button("Guardar Curso"):
        if ng and nm:
            try:
                conn.execute("INSERT INTO docentes_cursos VALUES (?, ?, ?)", (profesor, ng.upper(), nm))
                conn.commit()
                st.success("Curso guardado")
                st.rerun()
            except:
                st.error("Error: El curso ya existe")

# 2. GESTIONAR ESTUDIANTES
elif menu == "2. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Estudiantes y QR")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=[profesor])
    
    if df_cursos.empty:
        st.warning("Primero crea un curso")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Curso:", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]

        archivo = st.file_uploader("Subir Excel/CSV (ID y Nombre)", type=["xlsx", "csv"])
        if archivo:
            df_subido = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
            df_subido.columns = [c.lower().strip() for c in df_subido.columns]
            
            if st.button("Importar Estudiantes"):
                for _, r in df_subido.iterrows():
                    try:
                        conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)", 
                                    (profesor, grado, materia, str(r['id']), r['nombre']))
                    except: pass
                conn.commit()
                st.success("Estudiantes importados")

        if st.button("📄 Generar PDF de Carnets QR"):
            df_pdf = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", 
                                 conn, params=[profesor, grado, materia])
            if not df_pdf.empty:
                buffer = BytesIO()
                can = canvas.Canvas(buffer, pagesize=A4)
                # Lógica simplificada de dibujo QR
                for i, row in df_pdf.iterrows():
                    qr = generar_qr(row['estudiante_id'])
                    can.drawImage(ImageReader(qr), 50, 700 - (i*120), width=100, height=100)
                    can.drawString(160, 750 - (i*120), f"Estudiante: {row['nombre']}")
                    can.drawString(160, 735 - (i*120), f"Grado: {grado} - {materia}")
                    if i > 0 and i % 5 == 0: can.showPage()
                can.save()
                st.download_button("Descargar PDF", buffer.getvalue(), "listado_qr.pdf")

# 3. ESCANEAR ASISTENCIA
elif menu == "3. Escanear Asistencia con Cámara":
    st.header("📸 Escáner en Tiempo Real")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=[profesor])
    
    if not df_cursos.empty:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Curso actual:", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]
        
        img_file = st.camera_input("Capturar QR")
        if img_file:
            img = Image.open(img_file)
            detalles = decode(img)
            if detalles:
                est_id = detalles[0].data.decode('utf-8')
                fecha = datetime.now().strftime("%Y-%m-%d")
                hora = datetime.now().strftime("%H:%M:%S")
                try:
                    conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", 
                                (profesor, grado, materia, est_id, fecha, hora))
                    conn.commit()
                    st.success(f"Asistencia registrada: {est_id}")
                    st.balloons()
                except:
                    st.warning("Ya registrado hoy")
            else:
                st.error("No se detectó código QR")

# 4. REPORTE
elif menu == "4. Reporte y Descargar Excel":
    st.header("📊 Reportes")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=[profesor])
    if not df_cursos.empty:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Ver curso:", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]
        
        df_asist = pd.read_sql("""
            SELECT e.nombre, a.fecha, a.hora_registro 
            FROM asistencias a JOIN estudiantes e ON a.estudiante_id = e.estudiante_id
            WHERE a.profesor=? AND a.grado=? AND a.materia=?
        """, conn, params=[profesor, grado, materia])
        
        st.dataframe(df_asist, use_container_width=True)
        
        # Exportar Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_asist.to_excel(writer, index=False)
        st.download_button("📥 Descargar Excel", output.getvalue(), "asistencia.xlsx")

# 5. REINICIAR
elif menu == "5. Reiniciar mis datos":
    st.header("⚠️ Zona de Peligro")
    if st.checkbox("Borrar todos mis datos permanentemente"):
        if st.button("Eliminar Todo"):
            conn.execute("DELETE FROM docentes_cursos WHERE profesor=?", [profesor])
            conn.execute("DELETE FROM estudiantes WHERE profesor=?", [profesor])
            conn.execute("DELETE FROM asistencias WHERE profesor=?", [profesor])
            conn.commit()
            st.success("Datos eliminados correctamente")
            st.rerun()

st.caption(f"{APP_NAME} • Desarrollado por {CREADOR}")
