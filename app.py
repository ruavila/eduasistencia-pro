import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import sqlite3
from PIL import Image
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ====================== CONFIGURACIÓN ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== BASE DE DATOS ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)

conn.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (grado TEXT, materia TEXT, PRIMARY KEY (grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (grado, materia, estudiante_id))")
conn.execute("CREATE TABLE IF NOT EXISTS asistencias (grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (grado, materia, estudiante_id, fecha))")

def generar_qr(texto):
    qr = qrcode.make(texto)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def obtener_nombre_docente():
    res = conn.execute("SELECT valor FROM config WHERE clave='nombre_docente'").fetchone()
    return res[0] if res else ""

def guardar_nombre_docente(nombre):
    conn.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('nombre_docente', ?)", (nombre,))
    conn.commit()

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

if obtener_nombre_docente():
    st.markdown(f"**Docente:** {obtener_nombre_docente()}")

menu = st.sidebar.selectbox("Menú principal:", [
    "1. Nombre del Docente",
    "2. Mis Cursos (Agregar / Eliminar)",
    "3. Gestionar Estudiantes y Generar PDF",
    "4. Escanear Asistencia con Cámara",
    "5. Reporte y Descargar Excel",
    "6. Reiniciar Aplicación (Nuevo año lectivo)"
])

# 1. NOMBRE DEL DOCENTE
if menu == "1. Nombre del Docente":
    st.header("👨‍🏫 Nombre del Docente")
    nuevo = st.text_input("Tu nombre completo", value=obtener_nombre_docente())
    if st.button("Guardar nombre", type="primary"):
        if nuevo.strip():
            guardar_nombre_docente(nuevo.strip())
            st.success("✅ Nombre guardado correctamente")
            st.rerun()

# 2. MIS CURSOS
elif menu == "2. Mis Cursos (Agregar / Eliminar)":
    st.header("📚 Mis Cursos")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos ORDER BY grado, materia", conn)
    
    if not df_cursos.empty:
        st.subheader("Cursos registrados")
        st.dataframe(df_cursos, use_container_width=True)

        st.subheader("🗑️ Eliminar Curso")
        curso_elim = st.selectbox("Selecciona el curso a eliminar", 
                                  [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()], 
                                  key="curso_eliminar")
        
        if st.button("🗑️ Eliminar curso seleccionado", type="secondary"):
            if st.checkbox("Confirmo que deseo eliminar este curso y todos sus estudiantes"):
                g, m = [x.strip() for x in curso_elim.split(" - ")]
                conn.execute("DELETE FROM docentes_cursos WHERE grado=? AND materia=?", (g, m))
                conn.execute("DELETE FROM estudiantes WHERE grado=? AND materia=?", (g, m))
                conn.execute("DELETE FROM asistencias WHERE grado=? AND materia=?", (g, m))
                conn.commit()
                st.success(f"✅ Operación exitosa. Curso **{g} - {m}** eliminado correctamente")
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
                conn.execute("INSERT INTO docentes_cursos VALUES (?, ?)", 
                            (nuevo_g.strip().upper(), nuevo_m.strip()))
                conn.commit()
                st.success("✅ Curso agregado correctamente")
                st.rerun()
            except:
                st.warning("Este curso ya existe")

# 3. GESTIONAR ESTUDIANTES + PDF
elif menu == "3. Gestionar Estudiantes y Generar PDF":
    st.header("👥 Gestionar Estudiantes y Generar PDF")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)
    if df_cursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        seleccion = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in seleccion.split(" - ")]

        archivo = st.file_uploader("Sube lista de estudiantes (Excel o CSV)", type=["xlsx", "csv"])
        if archivo:
            if archivo.name.endswith(".csv"):
                df = pd.read_csv(archivo)
            else:
                df = pd.read_excel(archivo)

            df.columns = [c.strip().lower() for c in df.columns]
            if "id" in df.columns:
                df = df.rename(columns={"id": "estudiante_id"})

            if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                st.error("El archivo debe tener columnas: **estudiante_id** y **nombre**")
            else:
                df["grado"] = grado
                df["materia"] = materia
                df = df[["grado", "materia", "estudiante_id", "nombre"]].drop_duplicates()

                agregados = 0
                for _, row in df.iterrows():
                    try:
                        conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?)", 
                                    (row["grado"], row["materia"], row["estudiante_id"], row["nombre"]))
                        conn.commit()
                        agregados += 1
                    except:
                        pass
                st.success(f"✅ Se agregaron {agregados} estudiantes.")

                if st.button("📄 Generar PDF con QR (4x4 cm)", type="primary"):
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

                        for i, (_, row) in enumerate(df.iterrows()):
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

                    st.download_button(
                        label="⬇️ Descargar PDF listo para imprimir",
                        data=pdf_buffer,
                        file_name=f"QR_{grado}_{materia}.pdf",
                        mime="application/pdf"
                    )

# 4. ESCANEAR (Versión simplificada sin pyzbar)
elif menu == "4. Escanear Asistencia con Cámara":
    st.header("📸 Escanear QR del estudiante")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)
    if df_cursos.empty:
        st.warning("Agrega cursos primero")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]

        picture = st.camera_input("Apunta al QR y toma la foto", key="cam_key")

        if picture is not None:
            st.info("📸 Foto tomada. Procesando QR...")
            # Nota: En esta versión simplificada, el escaneo con pyzbar está desactivado.
            # Te recomiendo usar la cámara del celular para escanear y luego ingresar manualmente el ID por ahora.
            st.warning("⚠️ Función de escaneo automático temporalmente desactivada por problemas de compatibilidad en la nube.\n\nPor favor, usa la cámara de tu celular para escanear el QR y luego ingresa manualmente el ID del estudiante.")

            est_id_manual = st.text_input("Ingresa manualmente el ID del estudiante (del QR)")
            if est_id_manual and st.button("Registrar Asistencia"):
                info = pd.read_sql("SELECT nombre FROM estudiantes WHERE estudiante_id=? AND grado=? AND materia=?", 
                                   conn, params=(est_id_manual, grado, materia))
                if info.empty:
                    st.error("🚫 El estudiante no pertenece al grado")
                else:
                    nombre = info.iloc[0]["nombre"]
                    fecha = datetime.now().strftime("%Y-%m-%d")
                    hora = datetime.now().strftime("%H:%M:%S")
                    try:
                        conn.execute("INSERT INTO asistencias VALUES (?,?,?,?,?)", (grado, materia, est_id_manual, fecha, hora))
                        conn.commit()
                        st.success(f"✅ Asistencia registrada para {nombre}")
                    except:
                        st.warning("Este estudiante ya tiene asistencia hoy")

# 5. REPORTE
elif menu == "5. Reporte y Descargar Excel":
    st.header("📊 Reporte de Asistencia")
    df_cursos = pd.read_sql("SELECT grado, materia FROM docentes_cursos", conn)
    if df_cursos.empty:
        st.warning("No hay cursos")
    else:
        lista = [f"{r.grado} - {r.materia}" for _, r in df_cursos.iterrows()]
        sel = st.selectbox("Selecciona curso", lista)
        grado, materia = [x.strip() for x in sel.split(" - ")]

        data = pd.read_sql("""
            SELECT e.nombre, a.fecha 
            FROM asistencias a
            JOIN estudiantes e ON a.estudiante_id = e.estudiante_id
            WHERE a.grado = ? AND a.materia = ?
        """, conn, params=(grado, materia))

        if data.empty:
            st.info("Todavía no hay asistencias")
        else:
            fechas = sorted(data['fecha'].unique())
            tabla = pd.DataFrame(index=sorted(data['nombre'].unique()), columns=fechas).fillna("Ausente")
            for _, row in data.iterrows():
                tabla.loc[row['nombre'], row['fecha']] = "Presente"

            tabla['Total Presente'] = (tabla == "Presente").sum(axis=1)
            tabla['Total Ausente'] = len(fechas) - tabla['Total Presente']
            tabla['% Asistencia'] = ((tabla['Total Presente'] / len(fechas)) * 100).round(1) if len(fechas) > 0 else 0

            tabla = tabla.reset_index().rename(columns={'index': 'Estudiante'})
            st.dataframe(tabla, use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame([[f"ASISTENCIA - {materia} - GRADO {grado}"]]).to_excel(writer, startrow=0, header=False, index=False)
                pd.DataFrame([[f"Colegio: {COLEGIO}"]]).to_excel(writer, startrow=1, header=False, index=False)
                pd.DataFrame([[f"Docente: {obtener_nombre_docente() or 'No registrado'}"]]).to_excel(writer, startrow=2, header=False, index=False)
                tabla.to_excel(writer, startrow=4, index=False)
            output.seek(0)
            st.download_button("📥 Descargar Excel", output, f"Asistencia_{grado}_{materia}.xlsx")

# 6. REINICIAR
elif menu == "6. Reiniciar Aplicación (Nuevo año lectivo)":
    st.header("⚠️ Reiniciar Aplicación")
    st.warning("""
        **¡Atención importante!**  
        Esta acción borrará **todos** los cursos, estudiantes y registros de asistencia.  
        Solo se mantendrá el nombre del docente.  
        Esta operación **no se puede deshacer**.
    """)
    
    if st.checkbox("Entiendo las consecuencias y deseo reiniciar la aplicación"):
        if st.button("🔄 Confirmar Reinicio Completo", type="secondary"):
            conn.execute("DELETE FROM docentes_cursos")
            conn.execute("DELETE FROM estudiantes")
            conn.execute("DELETE FROM asistencias")
            conn.commit()
            st.success("✅ Operación exitosa. La aplicación ha sido reiniciada correctamente.")
            st.rerun()

st.caption(f"{APP_NAME} • {COLEGIO} • Desarrollado por {CREADOR}")
