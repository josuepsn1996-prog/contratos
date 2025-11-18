import streamlit as st
import streamlit_authenticator as stauth
from openai import OpenAI
import base64
import tempfile
import fitz  # PyMuPDF

# --- Configuración de usuarios y contraseñas ---
config = {
    'credentials': {
        'usernames': {
            'usuario1': {
                'name': 'Usuario Uno',
                'password': '$2b$12$O8LiBWotBYppE6OcqJQvFe87a6xw7snhTTlfNgQ7tT1QmepRNxB16'
            },
            'usuario2': {
                'name': 'Usuario Dos',
                'password': '$2b$12$KIXQ0GCXAP5T4n.tzYQyyOjvO7VCM7HeONpSHz5s7aK3O1r4F7r1K'
            }
        }
    },
    'cookie': {
        'expiry_days': 7,
        'key': 'cookie_firma_unica',
        'name': 'mi_app_streamlit'
    },
    'preauthorized': {
        'emails': []
    }
}

# --- Autenticación ---
authenticator = stauth.Authenticate(
    config['credentials'],
    'mi_app_streamlit',
    'cookie_firma_unica',
    7
)

name, authentication_status, username = authenticator.login('Iniciar sesión', 'main')

if authentication_status:
    st.sidebar.success(f"Bienvenido/a: {name}")
    authenticator.logout("Cerrar sesión", "sidebar")

    st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
    st.title("📄 Análisis Inteligente de Contratos de la Administración Pública")

    st.markdown("""
    Carga tu contrato público (PDF, escaneado o digital).  
    La IA extrae y consolida los **elementos legales más importantes** del contrato.
    """)

    api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
    uploaded_file = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

    if uploaded_file and api_key:

        client = OpenAI(api_key=api_key)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        st.info("Detectando tipo de PDF...")

        doc = fitz.open(tmp_path)
        is_digital = True
        digital_texts = []

        for page in doc:
            page_text = page.get_text("text")
            digital_texts.append(page_text)
            if len(page_text.strip()) < 30:
                is_digital = False

        st.success(f"Tipo de PDF detectado: {'Digital (texto seleccionable)' if is_digital else 'Escaneado (imagen)'}")

        all_texts = []
        progress_bar = st.progress(0)

        # ---------------------------------------
        # OCR DIGITAL O IMAGEN
        # ---------------------------------------

        if is_digital:
            st.info("Extrayendo texto directamente...")
            for i, page_text in enumerate(digital_texts):
                all_texts.append(page_text)
                progress_bar.progress((i + 1) / len(doc))

        else:
            st.info("Realizando OCR con GPT-5.1...")

            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                response = client.responses.create(
                    model="gpt-5.1",
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "Extrae TODO el texto del contrato en la imagen. "
                                        "Incluye partes, objeto, montos, plazos, garantías, penalizaciones, firmas, anexos, etc. "
                                        "Devuelve solo texto limpio."
                                    )
                                },
                                {
                                    "type": "input_image",
                                    "image": {"base64": img_base64}
                                }
                            ]
                        }
                    ],
                    max_output_tokens=2048
                )

                texto = response.output_text
                all_texts.append(texto)
                progress_bar.progress((i + 1) / len(doc))

        st.success("¡Extracción completada!")

        with st.expander("Ver texto extraído"):
            for idx, txt in enumerate(all_texts):
                st.markdown(f"### Página {idx+1}\n{txt}\n---")

        # ---------------------------------------
        # CONSOLIDACIÓN LEGAL
        # ---------------------------------------

        full_text = "\n\n".join(all_texts)

        prompt_final = (
            "Eres un analista legal experto en contratos públicos. "
            "DEBES LLENAR ESTA TABLA, SIN CAMBIAR EL FORMATO, SIN OMITIR CAMPOS:\n\n"
            "| Campo | Respuesta |\n"
            "|-------|-----------|\n"
            "| Partes | Por la Secretaría: [...]. Por el Proveedor: [...]. |\n"
            "| Objeto | [...] |\n"
            "| Monto antes de IVA | [...] |\n"
            "| IVA | [...] |\n"
            "| Monto total | [...] |\n"
            "| Fecha de inicio | [...] |\n"
            "| Fecha de fin | [...] |\n"
            "| Vigencia/Plazo | [...] |\n"
            "| Garantía(s) | [...] |\n"
            "| Obligaciones proveedor | [...] |\n"
            "| Supervisión | [...] |\n"
            "| Penalizaciones | [...] |\n"
            "| Penalización máxima | [...] |\n"
            "| Modificaciones | [...] |\n"
            "| Normatividad aplicable | [...] |\n"
            "| Resolución de controversias | [...] |\n"
            "| Firmas | [...] |\n"
            "| Anexos | [...] |\n"
            "| No localizado | [...] |\n"
            "| Áreas de mejora | [...] |\n\n"
            "Llena la tabla con información literal del contrato. Si algo no aparece, escribe 'NO LOCALIZADO'.\n\n"
            f"Texto del contrato:\n{full_text}"
        )

        response_final = client.responses.create(
            model="gpt-5.1",
            input=[
                {"role": "system", "content": "Eres un experto legal en contratos públicos."},
                {"role": "user", "content": prompt_final}
            ],
            max_output_tokens=4096
        )

        resultado = response_final.output_text

        st.success("¡Análisis general completado!")
        st.markdown("### Ficha estandarizada del contrato:")
        st.markdown(resultado)

        st.download_button(
            "Descargar ficha (Markdown)",
            data=resultado,
            file_name="ficha_contrato_publico.md",
            mime="text/markdown"
        )

elif authentication_status is False:
    st.error("Usuario o contraseña incorrectos")

elif authentication_status is None:
    st.info("Por favor ingresa tus credenciales")






