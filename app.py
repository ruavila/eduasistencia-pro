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
import cv2
import numpy as np

# ====================== CONFIGURACIÓN ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)
conn.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
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

# ====================== SESSION STATE ======================
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
if 'nombre_docente' not in st.session_state:
    st.session_state.nombre_docente = None
if 'uploaded_students_df' not in st.session_state:
    st.session_state.uploaded_students_df = None
if 'last_uploaded_file_name' not in st.session_state:
    st.session_state.last_uploaded_file_name = None

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
profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

if profesor is None:
    st.header("🔑 Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab1:
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar", type="primary"):
            if username and password:
                password_hash = hash_password(password)
                res = conn.execute("SELECT nombre_completo FROM profesores WHERE username=? AND password_hash=?", 
                                   (username.strip(), password_hash)).fetchone()
                if res:
                    st.session_state.profesor_actual = username.strip()
                    st.session_state.nombre_docente = res[0]
                    st.success(f"✅ Bienvenido, {res[0]}")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
    
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
                    st.success("✅ Registro exitoso. Ahora inicia sesión.")
                except:
                    st.error("❌ Ese usuario ya existe")

else:
    st.sidebar.success(f"✅ Conectado como: {nombre_docente}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.profesor_actual = None
        st.session_state.nombre_docente = None
        st.rerun()

    menu = st.sidebar.selectbox("Menú principal:", [
        "1. Mis Cursos (Agregar / Eliminar)",
        "2. Gestionar Estudiantes y Generar PDF",
        "3. Escanear Asistencia con Cámara",
        "4. Reporte y Descargar Excel",
        "5. Reiniciar mis datos"
    ])

    # 1. MIS CURSOS (sin cambios)
    if menu == "1. Mis Cursos (Agregar / Eliminar)":
        st.header("📚 Mis Cursos")
        df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=? ORDER BY grado, materia", conn, params=(profesor,))
        # ... (el resto del código de la sección 1 se mantiene igual que antes)

        if not df_cursos.empty:
            st.subheader("Cursos registrados")
            st.dataframe(df_cursos, use_container_width=True)
            st.subheader("🗑️ Eliminar Curso")
            curso_elim = st.selectbox("Selecciona el curso a eliminar", [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()], key="curso_eliminar_key")
            if st.button("🗑️ Eliminar curso seleccionado", type="secondary"):
                if st.checkbox("Confirmo que deseo eliminar este curso y todos sus estudiantes"):
                    g, m = [x.strip() for x in curso_elim.split(" - ")]
                    conn.execute("DELETE FROM docentes_cursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.commit()
                    st.success(f"✅ Curso **{g} - {m}** eliminado correctamente")
                    st.rerun()
        else:
            st.info("Aún no tienes cursos registrados.")

        st.subheader("Agregar nuevo curso")
        col1, col2 = st.columns(2)
        with col1: nuevo_g = st.text_input("Grado", key="n_grado")
        with col2: nuevo_m = st.text_input("Materia", key="n_materia")
        if st.button("Agregar curso", type="primary"):
            if nuevo_g and nuevo_m:
                try:
                    conn.execute("INSERT INTO docentes_cursos VALUES (?, ?, ?)", (profesor, nuevo_g.strip().upper(), nuevo_m.strip()))
                    conn.commit()
                    st.success("✅ Curso agregado correctamente")
                    st.rerun()
                except:
                    st.warning("Este curso ya existe para ti")

    # 2. GESTIONAR ESTUDIANTES - VERSIÓN MEJORADA PARA CELULAR (cambio principal)
    elif menu == "2. Gestionar Estudiantes y Generar PDF":
        st.header("👥 Gestionar Estudiantes y Generar PDF")
        
        df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos WHERE profesor=?", conn, params=(profesor,))
        
        if df_cursos.empty:
            st.warning("Agrega cursos primero")
        else:
            lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
            seleccion = st.selectbox("Selecciona curso", lista, key="select_curso_estudiantes")
            grado, materia = [x.strip() for x in seleccion.split(" - ")]

            st.subheader("📁 Subir lista de estudiantes")
            st.markdown(""" 
            <div style='background:#FFF3CD; padding:15px; border-radius:10px; border:2px solid #FFC107;'>
             📱 <strong>Instrucciones para celular:</strong><br>
             1. Toca "Examinar" y selecciona tu archivo Excel<br>
             2. Espera que aparezca el botón "Procesar archivo"<br>
             3. Presiona "Procesar archivo" y luego "Guardar estudiantes"
            </div>
            """, unsafe_allow_html=True)

            uploader_key = f"uploader_{profesor}_{grado}_{materia}"

            archivo = st.file_uploader("Selecciona el archivo Excel o CSV", 
                                       type=["xlsx", "xls", "csv"], 
                                       key=uploader_key)

            # Botón para procesar (importante en móvil)
            if archivo is not None and st.button("🔄 Procesar archivo", type="secondary"):
                try:
                    if archivo.name.lower().endswith('.csv'):
                        df = pd.read_csv(archivo)
                    else:
                        df = pd.read_excel(archivo)

                    df.columns = [str(c).strip().lower() for c in df.columns]
                    if "id" in df.columns:
                        df = df.rename(columns={"id": "estudiante_id"})

                    if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                        st.error("❌ El archivo debe tener las columnas: **estudiante_id** y **nombre**")
                    else:
                        df["profesor"] = profesor
                        df["grado"] = grado
                        df["materia"] = materia
                        df = df[["profesor", "grado", "materia", "estudiante_id", "nombre"]].drop_duplicates()
                        
                        st.session_state.uploaded_students_df = df
                        st.session_state.last_uploaded_file_name = archivo.name
                        
                        st.success(f"✅ Archivo procesado correctamente: **{len(df)} estudiantes**")
                        st.dataframe(df[["estudiante_id", "nombre"]], use_container_width=True)
                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Error al leer el archivo: {str(e)}")

            # Botón Guardar
            if st.session_state.uploaded_students_df is not None:
                if st.button("💾 Guardar estudiantes en la base de datos", type="primary"):
                    df = st.session_state.uploaded_students_df
                    agregados = 0
                    for _, row in df.iterrows():
                        try:
                            conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?,?)", 
                                         (row["profesor"], row["grado"], row["materia"], str(row["estudiante_id"]), str(row["nombre"])))
                            agregados += 1
                        except:
                            pass
                    conn.commit()
                    st.success(f"✅ Se guardaron **{agregados}** estudiantes correctamente")
                    st.session_state.uploaded_students_df = None
                    st.session_state.last_uploaded_file_name = None
                    st.rerun()

            # Generar PDF
            if st.button("📄 Generar PDF con QR (4x4 cm)", type="primary"):
                df_para_pdf = pd.read_sql(
                    "SELECT estudiante_id, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre",
                    conn, params=(profesor, grado, materia)
                )
                if df_para_pdf.empty:
                    st.warning("No hay estudiantes")
                else:
                    with st.spinner("Generando PDF..."):
                        pdf_buffer = BytesIO()
                        c = canvas.Canvas(pdf_buffer, pagesize=A4)
                        width, height = A4
                        qr_size = 113.3858
                        margin_x = 45
                        margin_y = 70
                        spacing_x = 25
                        spacing_y = 65
                        cols = 3
                        
                        for i, (_, row) in enumerate(df_para_pdf.iterrows()):
                            if i % (cols * 4) == 0 and i != 0:
                                c.showPage()
                            col = i % cols
                            row_num = (i // cols) % 4
                            x = margin_x + col * (qr_size + spacing_x)
                            y = height - margin_y - row_num * (qr_size + spacing_y)
                            
                            qr_img = generar_qr(row["estudiante_id"])
                            qr_pil = Image.open(qr_img)
                            qr_path = BytesIO()
                            qr_pil.save(qr_path, format="PNG")
                            qr_path.seek(0)
                            c.drawImage(ImageReader(qr_path), x, y - qr_size, width=qr_size, height=qr_size)
                            
                            nombre_corto = abreviar_nombre(row["nombre"])
                            c.setFont("Helvetica-Bold", 9)
                            c.drawCentredString(x + qr_size/2, y - qr_size - 15, nombre_corto)
                            c.setFont("Helvetica", 8)
                            c.drawCentredString(x + qr_size/2, y - qr_size - 27, f"{grado} - {materia}")
                        
                        c.save()
                        pdf_buffer.seek(0)
                        st.download_button("⬇️ Descargar PDF", pdf_buffer, f"QR_{grado}_{materia}.pdf", mime="application/pdf")

    # Las secciones 3, 4 y 5 se mantienen iguales a la versión anterior (puedes copiarlas del código que te di antes)

    # (Para no hacer el mensaje demasiado largo, las secciones 3,4,5 son las mismas que en mi respuesta anterior. Si las necesitas completas, avísame y te las mando.)

st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")
