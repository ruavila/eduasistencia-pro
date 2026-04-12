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

# ====================== CONFIG ======================
APP_NAME = "EduAsistencia Pro"
APP_SUBTITLE = "Sistema Inteligente de Asistencia con Código QR"
CREADOR = "Rubén Darío Ávila Sandoval"
COLEGIO = "Institución Educativa San Antonio de Padua"
ESCUDO_PATH = "escudo.png"

# ====================== DB ======================
conn = sqlite3.connect("asistencia.db", check_same_thread=False)

conn.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS docentes_cursos (grado TEXT, materia TEXT, PRIMARY KEY (grado, materia))")
conn.execute("CREATE TABLE IF NOT EXISTS estudiantes (grado TEXT, materia TEXT, estudiante_id TEXT, nombre TEXT, PRIMARY KEY (grado, materia, estudiante_id))")
conn.execute("CREATE TABLE IF NOT EXISTS asistencias (grado TEXT, materia TEXT, estudiante_id TEXT, fecha TEXT, hora_registro TEXT, PRIMARY KEY (grado, materia, estudiante_id, fecha))")

# ====================== FUNCIONES ======================
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

# ====================== UI ======================
st.set_page_config(page_title=APP_NAME, layout="wide")

st.markdown("""
<style>
@media (max-width: 768px) {
    h1 {font-size: 24px !important;}
    h3 {font-size: 18px !important;}
}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1,4])

with col1:
    try:
        st.image(Image.open(ESCUDO_PATH), use_container_width=True)
    except:
        pass

with col2:
    st.markdown(f"""
    <h1>{APP_NAME}</h1>
    <h3>{APP_SUBTITLE}</h3>
    <p>{COLEGIO} • {CREADOR}</p>
    """, unsafe_allow_html=True)

st.markdown("---")

if obtener_nombre_docente():
    st.success(f"Docente: {obtener_nombre_docente()}")

menu = st.sidebar.selectbox("Menú", [
    "Docente",
    "Cursos",
    "Estudiantes y PDF",
    "Reiniciar"
])

# ====================== DOCENTE ======================
if menu == "Docente":
    nombre = st.text_input("Nombre docente", value=obtener_nombre_docente())
    if st.button("Guardar"):
        guardar_nombre_docente(nombre)
        st.success("Guardado")
        st.rerun()

# ====================== CURSOS ======================
elif menu == "Cursos":
    df = pd.read_sql("SELECT * FROM docentes_cursos", conn)

    st.subheader("Cursos registrados")
    st.dataframe(df, use_container_width=True)

    if not df.empty:
        curso = st.selectbox("Eliminar curso", [f"{r.grado}-{r.materia}" for _, r in df.iterrows()])
        confirmar = st.checkbox("Confirmar eliminación")

        if st.button("Eliminar curso"):
            if confirmar:
                g, m = curso.split("-")
                conn.execute("DELETE FROM docentes_cursos WHERE grado=? AND materia=?", (g,m))
                conn.execute("DELETE FROM estudiantes WHERE grado=? AND materia=?", (g,m))
                conn.execute("DELETE FROM asistencias WHERE grado=? AND materia=?", (g,m))
                conn.commit()
                st.success("Curso eliminado con éxito")
                st.rerun()
            else:
                st.warning("Confirma primero")

    st.subheader("Agregar curso")
    g = st.text_input("Grado")
    m = st.text_input("Materia")

    if st.button("Agregar"):
        try:
            conn.execute("INSERT INTO docentes_cursos VALUES (?,?)",(g.upper(),m))
            conn.commit()
            st.success("Curso agregado")
            st.rerun()
        except:
            st.warning("Ya existe")

# ====================== ESTUDIANTES ======================
elif menu == "Estudiantes y PDF":

    cursos = pd.read_sql("SELECT * FROM docentes_cursos", conn)

    if cursos.empty:
        st.warning("Primero crea un curso")
    else:
        sel = st.selectbox("Curso", [f"{r.grado}-{r.materia}" for _,r in cursos.iterrows()])
        grado, materia = sel.split("-")

        # 📥 plantilla
        plantilla = pd.DataFrame({
            "estudiante_id": ["1001","1002"],
            "nombre": ["Juan Perez","Maria Gomez"]
        })

        st.download_button("Descargar plantilla CSV", plantilla.to_csv(index=False), "plantilla.csv")

        st.warning("📱 Usa CSV si estás en celular")

        archivo = st.file_uploader("Subir archivo", type=["csv","xlsx"])

        if archivo:
            try:
                if archivo.name.endswith(".csv"):
                    df = pd.read_csv(archivo)
                else:
                    df = pd.read_excel(archivo, engine="openpyxl")

                df.columns = [c.lower().strip() for c in df.columns]

                if "estudiante_id" not in df.columns or "nombre" not in df.columns:
                    st.error("Debe tener columnas estudiante_id y nombre")
                else:
                    for _, row in df.iterrows():
                        try:
                            conn.execute("INSERT INTO estudiantes VALUES (?,?,?,?)",
                                (grado, materia, row["estudiante_id"], row["nombre"]))
                            conn.commit()
                        except:
                            pass

                    st.success("Estudiantes cargados")

                    if st.button("Generar PDF"):
                        buffer = BytesIO()
                        c = canvas.Canvas(buffer, pagesize=A4)

                        x, y = 50, 750

                        for _, row in df.iterrows():
                            qr = generar_qr(row["estudiante_id"])
                            img = ImageReader(qr)
                            c.drawImage(img, x, y, 100, 100)

                            c.drawString(x, y-10, abreviar_nombre(row["nombre"]))
                            y -= 120

                            if y < 100:
                                c.showPage()
                                y = 750

                        c.save()
                        buffer.seek(0)

                        st.download_button("Descargar PDF", buffer, "qr.pdf")

            except Exception as e:
                st.error("Error leyendo archivo")
                st.text(str(e))

# ====================== REINICIAR ======================
elif menu == "Reiniciar":
    if st.checkbox("Confirmar reinicio"):
        if st.button("Reiniciar"):
            conn.execute("DELETE FROM docentes_cursos")
            conn.execute("DELETE FROM estudiantes")
            conn.execute("DELETE FROM asistencias")
            conn.commit()
            st.success("App reiniciada")
            st.rerun()

st.caption(f"{APP_NAME} - {COLEGIO}")
