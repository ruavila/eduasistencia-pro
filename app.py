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
conn = sqlite3.connect("asistencia.db", check_same_thread=False)

conn.execute("CREATE TABLE IF NOT EXISTS profesores (username TEXT PRIMARY KEY, password_hash TEXT, nombre_completo TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (profesor, grado, materia, estudiante_id))")
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
        pass

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
            res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", 
                              (username, hash_password(password))).fetchone()
            if res:
                st.session_state.profesor_actual = username
                st.session_state.nombre_docente = res[0]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    with tab2:
        nuevo_user = st.text_input("Nuevo Usuario", key="reg_user")
        nuevo_nombre = st.text_input("Nombre completo", key="reg_nombre")
        nueva_pass = st.text_input("Nueva Contraseña", type="password", key="reg_pass")
        if st.button("Registrarse"):
            if nuevo_user and nuevo_nombre and nueva_pass:
                try:
                    conn.execute("INSERT INTO profesores VALUES (?, ?, ?)", 
                                (nuevo_user.strip(), hash_password(nueva_pass), nuevo_nombre.strip()))
                    conn.commit()
                    st.success("Registro exitoso. Inicia sesión.")
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
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    
    if not df_cursos.empty:
        st.subheader("Eliminar un curso")
        opciones = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        curso_sel = st.selectbox("Selecciona curso a borrar", opciones)
        confirmar = st.checkbox(f"Confirmar eliminación de {curso_sel}")
        
        if st.button("🗑️ Eliminar Definitivamente", disabled=not confirmar):
            g, m = [x.strip() for x in curso_sel.split(" - ")]
            conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
            conn.commit()
            st.rerun()
            
    st.subheader("Añadir nuevo curso")
    c1, c2 = st.columns(2)
    ng = c1.text_input("Grado (ej: 10-01)")
    nm = c2.text_input("Materia (ej: Matemáticas)")
    if st.button("➕ Agregar"):
        if ng and nm:
            try:
                conn.execute("INSERT INTO docentes_cursos VALUES (?, ?, ?)", (profesor, ng.upper(), nm))
                conn.commit()
                st.rerun()
            except: st.error("Ya tienes ese curso.")

# 2. GESTIONAR ESTUDIANTES
elif menu == "2. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Estudiantes")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if df_c.empty: st.warning("Crea un curso primero")
    else:
        sel = st.selectbox("Curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        grado, materia = [x.strip() for x in sel.split(" - ")]
        
        archivo = st.file_uploader("Subir Excel/CSV (columnas: estudiante_id, nombre)", type=["xlsx", "csv"])
        if archivo and st.button("💾 Guardar Estudiantes"):
            df = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
            df.columns = [c.strip().lower() for c in df.columns]
            if 'estudiante_id' in df.columns and 'nombre' in df.columns:
                for _, r in df.iterrows():
                    try:
                        conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)", 
                                    (profesor, grado, materia, str(r['estudiante_id']), str(r['nombre'])))
                    except: pass
                conn.commit()
                st.success("Lista cargada.")
        
        if st.button("📄 Generar PDF de Códigos QR"):
            alumnos = pd.read_sql("SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", 
                                 conn, params=(profesor, grado, materia))
            if not alumnos.empty:
                pdf_buf = BytesIO()
                c = canvas.Canvas(pdf_buf, pagesize=A4)
                # Configuración de rejilla para los QR (simplificada para eficiencia)
                x, y = 50, 750
                for _, alu in alumnos.iterrows():
                    qr_img = generar_qr(str(alu['estudiante_id']))
                    c.drawImage(ImageReader(qr_img), x, y-100, width=100, height=100)
                    c.setFont("Helvetica-Bold", 8)
                    c.drawCentredString(x+50, y-115, abreviar_nombre(alu['nombre']))
                    x += 180
                    if x > 500: x = 50; y -= 160
                    if y < 100: c.showPage(); y = 750
                c.save()
                st.download_button("⬇️ Descargar PDF", pdf_buf.getvalue(), f"QRs_{grado}.pdf")

# 3. ESCANEAR
elif menu == "3. Escanear Asistencia con Cámara":
    st.header("📸 Escáner en Vivo")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Curso actual:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split(" - ")]
        
        foto = st.camera_input("Enfoque el código QR")
        if foto:
            img = Image.open(foto)
            decoded = decode(np.array(img))
            if decoded:
                eid = decoded[0].data.decode("utf-8").strip()
                alu = conn.execute("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND estudiante_id=?", 
                                  (profesor, g, m, eid)).fetchone()
                if alu:
                    fecha = datetime.now().strftime("%Y-%m-%d")
                    hora = datetime.now().strftime("%H:%M:%S")
                    try:
                        conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g, m, eid, fecha, hora))
                        conn.commit()
                        st.success(f"✅ {alu[0]} registrado.")
                        st.balloons()
                    except: st.warning("Ya registrado hoy.")
                else: st.error("Estudiante no encontrado en este curso.")
            else: st.error("No se detecta QR.")

# 4. REPORTE
elif menu == "4. Reporte y Descargar Excel":
    st.header("📊 Reporte de Asistencia")
    df_c = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
    if not df_c.empty:
        sel = st.selectbox("Ver curso:", [f"{r.grado} - {r.materia}" for _, r in df_c.iterrows()])
        g, m = [x.strip() for x in sel.split(" - ")]
        
        # JOIN Corregido para evitar duplicados de otros profesores
        query = """
            SELECT e.nombre, a.fecha 
            FROM asistencias a
            JOIN estudiantes e ON a.estudiante_id = e.estudiante_id 
                AND a.profesor = e.profesor 
                AND a.grado = e.grado 
                AND a.materia = e.materia
            WHERE a.profesor=? AND a.grado=? AND a.materia=?
        """
        data = pd.read_sql(query, conn, params=(profesor, g, m))
        if not data.empty:
            df_pivot = data.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0)
            df_pivot = df_pivot.replace({1: "P", 0: "A"})
            st.dataframe(df_pivot)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='openpyxl') as w:
                df_pivot.to_excel(w)
            st.download_button("📥 Descargar Reporte", out.getvalue(), f"Asistencia_{g}.xlsx")
        else: st.info("Sin registros aún.")

# 5. REINICIAR
elif menu == "5. Reiniciar mis datos":
    st.header("⚠️ Zona de Peligro")
    if st.checkbox("BORRAR TODOS MIS CURSOS Y ASISTENCIAS"):
        if st.button("CONFIRMAR ELIMINACIÓN TOTAL"):
            conn.execute("DELETE FROM docentes_cursos WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM estudiantes WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM asistencias WHERE profesor=?", (profesor,))
            conn.commit()
            st.success("Datos borrados.")
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(f"v2.1 • {COLEGIO}")
