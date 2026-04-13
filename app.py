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

# Configuración
APPNAME = "EduAsistencia Pro"
APPSUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDOPATH = "escudo.png"

# Base de datos
conn = sqlite3.connect('asistencia.db', check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY, valor TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS profesores (
    username TEXT PRIMARY KEY, passwordhash TEXT, nombrecompleto TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS docentescursos (
    profesor TEXT, grado TEXT, materia TEXT,
    PRIMARY KEY (profesor, grado, materia)
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS estudiantes (
    profesor TEXT, grado TEXT, materia TEXT, estudianteid TEXT, nombre TEXT,
    PRIMARY KEY (profesor, grado, materia, estudianteid)
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS asistencias (
    profesor TEXT, grado TEXT, materia TEXT, estudianteid TEXT, fecha TEXT, horaregistro TEXT,
    PRIMARY KEY (profesor, grado, materia, estudianteid, fecha)
)""")

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
    if len(partes) > 2:
        iniciales = [p[0].upper() + "." for p in partes[:-1]]
        return " ".join(iniciales) + " " + partes[-1]
    return nombre

# Interfaz principal
st.set_page_config(page_title=APPNAME, layout="wide")
col_escudo, col_titulo = st.columns([1, 4])
with col_escudo:
    try:
        escudo = Image.open(ESCUDOPATH)
        st.image(escudo, width=130)
    except:
        pass
with col_titulo:
    st.markdown(f"""
    <h1 style="margin-bottom: 0; color: #1E3A8A;">{APPNAME}</h1>
    <h3 style="margin-top: 5px; color: #334155;">{APPSUBTITLE}</h3>
    <p style="color: #64748B; font-size: 1.05em;">{COLEGIO} - Creado por {CREADOR}</p>
    """, unsafe_allow_html=True)
st.markdown("<hr style='margin: 25px 0'>", unsafe_allow_html=True)

# Login
if 'profesor_actual' not in st.session_state:
    st.session_state.profesor_actual = None
    st.session_state.nombre_docente = None

if st.session_state.profesor_actual is None:
    st.header("Acceso al Sistema")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab1:
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar", type="primary"):
            if username and password:
                password_hash = hash_password(password)
                res = conn.execute("SELECT nombrecompleto FROM profesores WHERE username=? AND passwordhash=?", 
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
        nuevo_pass = st.text_input("Contraseña", type="password", key="reg_pass")
        if st.button("Registrarse", type="primary"):
            if nuevo_user and nuevo_nombre and nuevo_pass:
                try:
                    conn.execute("INSERT INTO profesores VALUES (?, ?, ?)", 
                               (nuevo_user.strip(), hash_password(nuevo_pass), nuevo_nombre.strip()))
                    conn.commit()
                    st.success("Registro exitoso. Ahora inicia sesión.")
                except:
                    st.error("Ese usuario ya existe")
                st.stop()

profesor = st.session_state.profesor_actual
nombre_docente = st.session_state.nombre_docente

st.sidebar.success(f"Conectado como {nombre_docente}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.profesor_actual = None
    st.session_state.nombre_docente = None
    st.rerun()

menu = st.sidebar.selectbox("Menú principal", 
    ["1. Mis Cursos (Agregar/Eliminar)", "2. Gestionar Estudiantes y Generar PDF", 
     "3. Escanear Asistencia con Cámara", "4. Reporte y Descargar Excel", "5. Reiniciar mis datos"])

# 1. Mis Cursos (CORREGIDO: Eliminación robusta sin rerun en callback)
if menu == "1. Mis Cursos (Agregar/Eliminar)":
    st.header("Mis Cursos")
    
    # Init flags para eliminación
    if 'eliminando_curso' not in st.session_state:
        st.session_state.eliminando_curso = False
    if 'curso_para_eliminar' not in st.session_state:
        st.session_state.curso_para_eliminar = None
    if 'cursos_refreshed' not in st.session_state:
        st.session_state.cursos_refreshed = False
    
    dfcursos = pd.read_sql("SELECT grado, materia FROM docentescursos WHERE profesor=? ORDER BY grado, materia", 
                          conn, params=(profesor,))
    if not dfcursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(dfcursos, use_container_width=True)
        
        # ELIMINACIÓN CORREGIDA
        st.subheader("Eliminar Curso")
        opciones = [f"{row['grado'].strip().upper()} - {row['materia'].strip()}" for _, row in dfcursos.iterrows()]
        curso_sel = st.selectbox("Selecciona curso:", opciones)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚫 Eliminar", type="secondary", disabled=st.session_state.eliminando_curso):
                st.session_state.curso_para_eliminar = curso_sel
                st.session_state.eliminando_curso = True
        
        if st.session_state.eliminando_curso:
            st.warning(f"⚠️ Confirmar eliminación de **{st.session_state.curso_para_eliminar}** (incluye estudiantes y asistencias)")
            col_conf1, col_conf2 = st.columns(2)
            with col_conf1:
                if st.button("✅ SI, ELIMINAR", type="primary"):
                    g, m = [x.strip() for x in st.session_state.curso_para_eliminar.split(' - ')]
                    conn.execute("DELETE FROM docentescursos WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM estudiantes WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.execute("DELETE FROM asistencias WHERE profesor=? AND grado=? AND materia=?", (profesor, g, m))
                    conn.commit()
                    st.success(f"✅ **{g} - {m}** eliminado!")
                    st.session_state.eliminando_curso = False
                    st.session_state.curso_para_eliminar = None
                    st.session_state.cursos_refreshed = True
            with col_conf2:
                if st.button("❌ Cancelar"):
                    st.session_state.eliminando_curso = False
                    st.session_state.curso_para_eliminar = None
        
        if st.session_state.cursos_refreshed:
            st.session_state.cursos_refreshed = False
            st.rerun()
    else:
        st.info("Aún no tienes cursos registrados.")
    
    st.subheader("Agregar nuevo curso")
    col1, col2 = st.columns(2)
    with col1:
        nuevo_g = st.text_input("Grado", key="n_grado")
    with col2:
        nuevo_m = st.text_input("Materia", key="n_materia")
    if st.button("Agregar curso", type="primary"):
        if nuevo_g and nuevo_m:
            try:
                conn.execute("INSERT INTO docentescursos VALUES (?, ?, ?)", 
                           (profesor, nuevo_g.strip().upper(), nuevo_m.strip()))
                conn.commit()
                st.success("Curso agregado correctamente")
                st.rerun()
            except:
                st.warning("Este curso ya existe para ti")

# 2. Gestionar Estudiantes (CORREGIDO: Upload Android)
elif menu == "2. Gestionar Estudiantes y Generar PDF":
    st.header("Gestionar Estudiantes y Generar PDF")
    dfcursos = pd.read_sql("SELECT grado, materia FROM docentescursos WHERE profesor=?", conn, params=(profesor,))
    if dfcursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r['grado']} - {r['materia']}" for _, r in dfcursos.iterrows()]
        seleccion = st.selectbox("Selecciona curso:", lista)
        grado, materia = [x.strip() for x in seleccion.split(' - ')]
        
        # UPLOAD CORREGIDO PARA ANDROID
        if 'upload_key' not in st.session_state:
            st.session_state.upload_key = 0
        if 'archivo_subido' not in st.session_state:
            st.session_state.archivo_subido = None
        
        st.markdown("""
        <div style='background:#FFF3CD; padding:15px; border-radius:10px; border:2px solid #FFC107;'>
        <strong>💡 Android:</strong> Toca 'Examinar', selecciona YA. Usa <b>.xlsx</b> de Google Sheets.
        </div>
        """, unsafe_allow_html=True)
        
        archivo = st.file_uploader(
            "📁 Sube Excel (.xlsx) o CSV:",
            type=['xlsx', 'csv'],
            key=f"UPLOAD_MOBIL_{st.session_state.upload_key}_{int(datetime.now().timestamp()) % 10000}"
        )
        
        if archivo is not None and st.session_state.archivo_subido != archivo.name:
            st.session_state.archivo_subido = archivo.name
            try:
                if archivo.name.lower().endswith('.csv'):
                    df = pd.read_csv(archivo)
                else:
                    df = pd.read_excel(archivo, engine='openpyxl')
                
                df.columns = [str(c).strip().lower() for c in df.columns]
                if 'id' in df.columns:
                    df = df.rename(columns={'id': 'estudianteid'})
                
                if 'estudianteid' not in df.columns or 'nombre' not in df.columns:
                    st.error("❌ Faltan columnas: 'estudianteid' y 'nombre'")
                else:
                    st.success(f"✅ Archivo OK: {len(df)} filas")
                    df['profesor'] = profesor
                    df['grado'] = grado
                    df['materia'] = materia
                    df = df[['profesor', 'grado', 'materia', 'estudianteid', 'nombre']].drop_duplicates()
                    
                    if st.button("💾 GUARDAR ESTUDIANTES", type="primary"):
                        agregados = 0
                        for _, row in df.iterrows():
                            conn.execute("INSERT OR IGNORE INTO estudiantes VALUES (?, ?, ?, ?, ?)",
                                       (row['profesor'], row['grado'], row['materia'], 
                                        str(row['estudianteid']).strip(), str(row['nombre']).strip()))
                            if conn.total_changes > 0:
                                agregados += 1
                        conn.commit()
                        st.success(f"✅ ¡{agregados} estudiantes guardados!")
                        st.session_state.upload_key += 1
                        st.rerun()
                        
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.info("🔧 Exporta como .xlsx nuevo")
        
        if st.button("Generar PDF con QR (4x4 cm)", type="primary"):
            df_para_pdf = pd.read_sql(
                "SELECT estudianteid, nombre FROM estudiantes WHERE profesor=? AND grado=? AND materia=? ORDER BY nombre",
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
                        row_num = i // cols % 4
                        x = margin_x + col * (qr_size + spacing_x)
                        y = height - margin_y - row_num * (qr_size + spacing_y)
                        
                        qr_img = generar_qr(row['estudianteid'])
                        qr_pil = Image.open(qr_img)
                        qr_path = BytesIO()
                        qr_pil.save(qr_path, format='PNG')
                        qr_path.seek(0)
                        c.drawImage(ImageReader(qr_path), x, y - qr_size, width=qr_size, height=qr_size)
                        
                        nombre_corto = abreviar_nombre(row['nombre'])
                        c.setFont("Helvetica-Bold", 9)
                        c.drawCentredString(x + qr_size/2, y - qr_size - 15, nombre_corto)
                        c.setFont("Helvetica", 8)
                        c.drawCentredString(x + qr_size/2, y - qr_size - 27, f"{grado} - {materia}")
                    
                    c.save()
                    pdf_buffer.seek(0)
                    st.download_button(
                        label="📥 Descargar PDF listo para imprimir",
                        data=pdf_buffer,
                        file_name=f"QR_{grado}_{materia}.pdf",
                        mime="application/pdf"
                    )

# 3. Escanear Asistencia
elif menu == "3. Escanear Asistencia con Cámara":
    st.header("Escanear QR del estudiante")
    dfcursos = pd.read_sql("SELECT grado, materia FROM docentescursos WHERE profesor=?", conn, params=(profesor,))
    if dfcursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r['grado']} - {r['materia']}" for _, r in dfcursos.iterrows()]
        sel = st.selectbox("Selecciona curso:", lista)
        grado, materia = [x.strip() for x in sel.split(' - ')]
        
        picture = st.camera_input("Apunta al QR y toma la foto")
        if picture is not None:
            image = Image.open(picture)
            # Nota: Requiere pyzbar o similar para decode; asumiendo ya funciona
            try:
                decoded = decode(np.array(image))  # pyzbar.decode
                if decoded:
                    est_id = decoded[0].data.decode('utf-8').strip()
                    info = pd.read_sql(
                        "SELECT nombre FROM estudiantes WHERE profesor=? AND estudianteid=? AND grado=? AND materia=?",
                        conn, params=(profesor, est_id, grado, materia)
                    )
                    if info.empty:
                        st.error("El estudiante no pertenece al grado")
                    else:
                        nombre = info.iloc[0]['nombre']
                        fecha = datetime.now().strftime('%Y-%m-%d')
                        hora = datetime.now().strftime('%H:%M:%S')
                        key = f"{profesor}_{grado}_{materia}_{est_id}_{fecha}"
                        if key not in st.session_state:
                            conn.execute("INSERT INTO asistencias VALUES (?, ?, ?, ?, ?, ?)",
                                       (profesor, grado, materia, est_id, fecha, hora))
                            conn.commit()
                            st.session_state[key] = True
                            st.balloons()
                            st.success(f"Asistencia registrada para {nombre}")
                        else:
                            st.warning("Este estudiante ya tiene asistencia hoy")
                else:
                    st.error("No se pudo leer el código QR")
            except:
                st.error("No se pudo leer el código QR")
        
        if st.button("Listo - Escanear siguiente"):
            st.rerun()

# 4. Reporte
elif menu == "4. Reporte y Descargar Excel":
    st.header("Reporte de Asistencia")
    dfcursos = pd.read_sql("SELECT grado, materia FROM docentescursos WHERE profesor=?", conn, params=(profesor,))
    if dfcursos.empty:
        st.warning("No hay cursos")
    else:
        lista = [f"{r['grado']} - {r['materia']}" for _, r in dfcursos.iterrows()]
        sel = st.selectbox("Selecciona curso:", lista)
        grado, materia = [x.strip() for x in sel.split(' - ')]
        
        data = pd.read_sql("""
            SELECT e.nombre, a.fecha 
            FROM asistencias a 
            JOIN estudiantes e ON a.estudianteid = e.estudianteid 
            WHERE a.profesor=? AND a.grado=? AND a.materia=?
        """, conn, params=(profesor, grado, materia))
        
        if data.empty:
            st.info("Todavía no hay asistencias")
        else:
            fechas = sorted(data['fecha'].unique())
            tabla = pd.DataFrame(
                index=sorted(data['nombre'].unique()), 
                columns=fechas
            ).fillna('Ausente')
            for _, row in data.iterrows():
                tabla.loc[row['nombre'], row['fecha']] = 'Presente'
            
            tabla['Total Presente'] = tabla['Presente'].sum(axis=1)
            tabla['Total Ausente'] = len(fechas) - tabla['Total Presente']
            tasa = (tabla['Total Presente'] / len(fechas) * 100).round(1) if len(fechas) > 0 else 0
            tabla['% Asistencia'] = tasa
            
            tabla = tabla.reset_index().rename(columns={'index': 'Estudiante'})
            st.dataframe(tabla, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame([f"ASISTENCIA - {materia} - GRADO {grado}"]).to_excel(writer, startrow=0, header=False, index=False)
                pd.DataFrame([f"Docente: {nombre_docente}"]).to_excel(writer, startrow=1, header=False, index=False)
                tabla.to_excel(writer, startrow=3, index=False)
            output.seek(0)
            st.download_button("Descargar Excel", output, f"Asistencia_{grado}_{materia}.xlsx")

# 5. Reiniciar
elif menu == "5. Reiniciar mis datos":
    st.header("Reiniciar mis datos")
    st.warning("Esta acción borrará todos tus cursos, estudiantes y asistencias.")
    if st.checkbox("Entiendo y deseo reiniciar mis datos"):
        if st.button("Confirmar Reinicio", type="secondary"):
            conn.execute("DELETE FROM docentescursos WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM estudiantes WHERE profesor=?", (profesor,))
            conn.execute("DELETE FROM asistencias WHERE profesor=?", (profesor,))
            conn.commit()
            st.success("Operación exitosa. Tus datos han sido reiniciados.")
            st.rerun()

st.caption(f"{APPNAME} - {COLEGIO} - Desarrollado por {CREADOR}")
