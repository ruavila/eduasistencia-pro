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

# ====================== CONFIGURACIÓN DEL SISTEMA ======================
st.set_page_config(page_title="EduAsistencia Pro", layout="centered")

# Estilo CSS para mejorar la visibilidad en móviles
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; }
    .stTextInput>div>div>input { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Mantener la sesión activa
if 'profesor_id' not in st.session_state:
    st.session_state.profesor_id = None
if 'nombre_profesor' not in st.session_state:
    st.session_state.nombre_profesor = None

# ====================== CONEXIÓN A BASE DE DATOS ======================
@st.cache_resource
def iniciar_db():
    conn = sqlite3.connect("asistencia_escolar.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS profesores (usuario TEXT PRIMARY KEY, clave TEXT, nombre TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS cursos (profesor TEXT, grado TEXT, materia TEXT, PRIMARY KEY (profesor, grado, materia))")
    c.execute("CREATE TABLE IF NOT EXISTS estudiantes (profesor TEXT, grado TEXT, materia TEXT, id_estudiante TEXT, nombre TEXT, whatsapp TEXT, PRIMARY KEY (profesor, grado, materia, id_estudiante))")
    c.execute("CREATE TABLE IF NOT EXISTS asistencias (profesor TEXT, grado TEXT, materia TEXT, id_estudiante TEXT, fecha TEXT, hora TEXT, PRIMARY KEY (profesor, grado, materia, id_estudiante, fecha))")
    conn.commit()
    return conn

db = iniciar_db()

def encriptar(texto):
    return hashlib.sha256(texto.encode()).hexdigest()

# ====================== LÓGICA DE LOGIN ======================
if st.session_state.profesor_id is None:
    st.title("🍎 EduAsistencia Pro")
    st.subheader("Bienvenido, por favor identifíquese")
    
    opcion = st.radio("Seleccione una opción", ["Iniciar Sesión", "Registrarse"], horizontal=True)
    
    if opcion == "Iniciar Sesión":
        user = st.text_input("Usuario")
        pw = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            res = db.execute("SELECT nombre FROM profesores WHERE usuario=? AND clave=?", (user, encriptar(pw))).fetchone()
            if res:
                st.session_state.profesor_id = user
                st.session_state.nombre_profesor = res[0]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    else:
        new_user = st.text_input("Crear Usuario")
        new_name = st.text_input("Nombre Completo")
        new_pw = st.text_input("Crear Contraseña", type="password")
        if st.button("Registrar"):
            try:
                db.execute("INSERT INTO profesores VALUES (?,?,?)", (new_user, encriptar(new_pw), new_name))
                db.commit()
                st.success("¡Registro exitoso! Ahora inicie sesión.")
            except:
                st.error("El usuario ya existe")
    st.stop()

# ====================== INTERFAZ PRINCIPAL ======================
profesor = st.session_state.profesor_id
st.sidebar.title(f"👨‍🏫 {st.session_state.nombre_profesor}")
menu = st.sidebar.selectbox("Menú", ["Mis Cursos", "Cargar Estudiantes", "Pasar Asistencia", "Ver Reportes", "Cerrar Sesión"])

if menu == "Cerrar Sesión":
    st.session_state.profesor_id = None
    st.rerun()

# --- 1. MIS CURSOS ---
if menu == "Mis Cursos":
    st.header("📚 Mis Cursos y Materias")
    
    # Mostrar tabla de cursos actuales
    cursos_actuales = pd.read_sql("SELECT grado AS Grado, materia AS Materia FROM cursos WHERE profesor=?", db, params=(profesor,))
    if not cursos_actuales.empty:
        st.write("Cursos que estás trabajando actualmente:")
        st.table(cursos_actuales)
    else:
        st.info("Aún no has agregado cursos.")

    with st.expander("➕ Agregar Nuevo Curso"):
        grado = st.text_input("Grado (ej: 10-01)")
        materia = st.text_input("Materia (ej: Matemáticas)")
        if st.button("Guardar Curso"):
            if grado and materia:
                db.execute("INSERT INTO cursos VALUES (?,?,?)", (profesor, grado.upper(), materia))
                db.commit()
                st.rerun()

# --- 2. CARGAR ESTUDIANTES ---
elif menu == "Cargar Estudiantes":
    st.header("👥 Gestión de Estudiantes")
    df_cursos = pd.read_sql("SELECT grado, materia FROM cursos WHERE profesor=?", db, params=(profesor,))
    
    if df_cursos.empty:
        st.warning("Debe crear un curso primero.")
    else:
        opciones_c = [f"{r.grado} | {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Seleccione el curso para cargar alumnos:", opciones_c)
        g_sel, m_sel = seleccion.split(" | ")

        archivo = st.file_uploader("Subir Excel (.xlsx) con columnas: estudiante_id, nombre, whatsapp", type=["xlsx", "csv"])
        
        if archivo:
            if st.button("💾 Procesar y Guardar Lista"):
                try:
                    df = pd.read_excel(archivo) if archivo.name.endswith('.xlsx') else pd.read_csv(archivo)
                    df.columns = [c.lower().strip() for c in df.columns]
                    
                    for _, r in df.iterrows():
                        # Limpieza de datos para el celular
                        id_e = str(r['estudiante_id']).split('.')[0]
                        ws = str(r.get('whatsapp', '')).split('.')[0] if 'whatsapp' in r else ""
                        db.execute("INSERT OR REPLACE INTO estudiantes VALUES (?,?,?,?,?,?)", 
                                  (profesor, g_sel, m_sel, id_e, str(r['nombre']), ws))
                    db.commit()
                    st.success(f"✅ Se cargaron {len(df)} estudiantes correctamente.")
                except Exception as e:
                    st.error(f"Error al leer el archivo: {e}")

        st.markdown("---")
        if st.button("📄 Generar PDF de Códigos QR"):
            estudiantes = pd.read_sql("SELECT id_estudiante, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", db, params=(profesor, g_sel, m_sel))
            if not estudiantes.empty:
                pdf_buf = BytesIO()
                can = canvas.Canvas(pdf_buf, pagesize=A4)
                x, y = 50, 750
                for _, est in estudiantes.iterrows():
                    # Generar QR
                    qr_buf = BytesIO()
                    qrcode.make(est['id_estudiante']).save(qr_buf, format="PNG")
                    can.drawImage(ImageReader(qr_buf), x, y-100, width=100, height=100)
                    can.setFont("Helvetica-Bold", 8)
                    can.drawCentredString(x+50, y-112, str(est['nombre'])[:20])
                    can.setFont("Helvetica", 7)
                    can.drawCentredString(x+50, y-122, f"{g_sel} - {m_sel}")
                    x += 180
                    if x > 500: x = 50; y -= 160
                    if y < 100: can.showPage(); y = 750
                can.save()
                st.download_button("⬇️ Descargar PDF", pdf_buf.getvalue(), f"QRs_{g_sel}.pdf")

# --- 3. PASAR ASISTENCIA (ESCÁNER + BOTÓN FINALIZAR) ---
elif menu == "Pasar Asistencia":
    st.header("📸 Escáner de Asistencia")
    df_cursos = pd.read_sql("SELECT grado, materia FROM cursos WHERE profesor=?", db, params=(profesor,))
    
    if not df_cursos.empty:
        opciones_c = [f"{r.grado} | {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Curso actual:", opciones_c)
        g_sel, m_sel = seleccion.split(" | ")
        
        foto = st.camera_input("Enfoque el código QR")
        
        if foto:
            img = Image.open(foto)
            codigos = decode(np.array(img))
            if codigos:
                id_leido = codigos[0].data.decode("utf-8").strip()
                # Verificar si el estudiante existe en este curso
                est = db.execute("SELECT nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? AND id_estudiante=?", (profesor, g_sel, m_sel, id_leido)).fetchone()
                if est:
                    hoy = datetime.now().strftime("%Y-%m-%d")
                    hora = datetime.now().strftime("%H:%M:%S")
                    try:
                        db.execute("INSERT INTO asistencias VALUES (?,?,?,?,?,?)", (profesor, g_sel, m_sel, id_leido, hoy, hora))
                        db.commit()
                        st.success(f"✅ REGISTRADO: {est[0]}")
                        st.balloons()
                    except:
                        st.warning(f"El estudiante {est[0]} ya fue registrado hoy.")
                else:
                    st.error("El código no pertenece a ningún estudiante de este curso.")
            else:
                st.error("No se detectó ningún código QR.")

        st.markdown("---")
        if st.button("🏁 PROCESO FINALIZADO", type="primary"):
            hoy = datetime.now().strftime("%Y-%m-%d")
            # Obtener lista completa vs los que asistieron
            lista_total = pd.read_sql("SELECT id_estudiante, nombre, whatsapp FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", db, params=(profesor, g_sel, m_sel))
            lista_asistio = pd.read_sql("SELECT id_estudiante FROM asistencias WHERE profesor=? AND grado=? AND materia=? AND fecha=?", db, params=(profesor, g_sel, m_sel, hoy))
            
            ausentes = lista_total[~lista_total['id_estudiante'].isin(lista_asistio['id_estudiante'])]
            
            if ausentes.empty:
                st.success("¡Excelente! Todos los estudiantes asistieron hoy.")
            else:
                st.subheader(f"📢 Estudiantes Ausentes: {len(ausentes)}")
                for _, aus in ausentes.iterrows():
                    nombre = aus['nombre']
                    telefono = str(aus['whatsapp']).strip()
                    if telefono and telefono != "nan":
                        msg = f"Hola, notificamos que el estudiante {nombre} no asistió a la clase de {m_sel} hoy {hoy}."
                        link = f"https://wa.me/{telefono}?text={urllib.parse.quote(msg)}"
                        col1, col2 = st.columns([3, 1])
                        col1.write(f"❌ {nombre}")
                        col2.markdown(f"[📲 Notificar]({link})")
                    else:
                        st.write(f"❌ {nombre} (Sin número de WhatsApp)")

# --- 4. VER REPORTES ---
elif menu == "Ver Reportes":
    st.header("📊 Reportes de Asistencia")
    df_cursos = pd.read_sql("SELECT grado, materia FROM cursos WHERE profesor=?", db, params=(profesor,))
    
    if not df_cursos.empty:
        opciones_c = [f"{r.grado} | {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Seleccione Curso:", opciones_c)
        g_sel, m_sel = seleccion.split(" | ")
        
        datos = pd.read_sql("""SELECT e.nombre, a.fecha 
                               FROM asistencias a 
                               JOIN estudiantes e ON a.id_estudiante = e.id_estudiante 
                               AND a.profesor = e.profesor AND a.grado = e.grado AND a.materia = e.materia
                               WHERE a.profesor=? AND a.grado=? AND a.materia=?""", db, params=(profesor, g_sel, m_sel))
        
        if not datos.empty:
            reporte = datos.pivot_table(index='nombre', columns='fecha', aggfunc='size', fill_value=0).replace({1: 'P', 0: 'A'})
            st.dataframe(reporte, use_container_width=True)
            
            output = BytesIO()
            reporte.to_excel(output)
            st.download_button("📥 Descargar Reporte en Excel", output.getvalue(), f"Reporte_{g_sel}.xlsx")
        else:
            st.info("No hay registros de asistencia para este curso.")

st.sidebar.markdown("---")
st.sidebar.caption(f"Versión Móvil Optimizada | {datetime.now().year}")
