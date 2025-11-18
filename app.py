import streamlit as st
import streamlit_authenticator as stauth
from openai import OpenAI, RateLimitError
import base64
import tempfile
import fitz
import time


# ===============================================================
# FUNCIÓN DE REINTENTOS (ANTI RATE LIMIT)
# ===============================================================

def safe_gpt(client, model, input_data, max_output_tokens=2000, retries=5):
    while retries > 0:
        try:
            return client.responses.create(
                model=model,
                input=input_data,
                max_output_tokens=max_output_tokens
            )
        except RateLimitError as e:
            wait = getattr(e, "retry_after", 3)
            time.sleep(wait)
            retries -= 1
    raise Exception("Rate limit persistente. Reduce el tamaño del contrato.")


# ===============================================================
# CONFIGURACIÓN LOGIN
# ===============================================================

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


authenticator = stauth.Authenticate(
    config['credentials'],
    'mi_app_streamlit',
    'cookie_firma_unica',
    7
)

name, authentication_status, username = authenticator.login('Iniciar sesión', 'main')


# ===============================================================
# APP PRINCIPAL
# ===============================================================

if authentication_status:
    st.sidebar.success(f"Bienvenido/a: {name}")
    authenticator.logout("Cerrar sesión", "sidebar")

    st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
    st.title("📄 Análisis Inteligente de Contratos Públicos (GPT-5)")

    api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
    archivo = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

    if archivo and api_key:

        client = OpenAI(api_key=api_key)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(archivo.read())
            tmp_path = tmp.name

        st.info("Detectando tipo de PDF...")
        doc = fitz.open(tmp_path)

        # Detección de PDF digital vs imagen
        is_digital = True
        digital_pages = []

        for p in doc:
            t = p.get_text("text")
            digital_pages.append(t)
            if len(t.strip()) < 30:
                is_digital = False

        st.success("Tipo: " + ("Digital (texto seleccionable)" if is_digital else "Escaneado / Imagen"))

        all_texts = []
        progress = st.progress(0)


        # ===========================================================
        # 1) OCR — GPT-5.1 (máxima precisión de visión)
        # ===========================================================

        if is_digital:
            for i, t in enumerate(digital_pages):
                all_texts.append(t)
                progress.progress((i+1)/len(doc))
        else:
            for i, page in enumerate(doc):

                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                response = safe_gpt(
                    client,
                    model="gpt-5.1",
                    input_data=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Realiza OCR completo del contrato. Devuelve solo texto plano."
                                },
                                {
                                    "type": "input_image",
                                    "image": {"base64": img_base64}
                                }
                            ]
                        }
                    ],
                    max_output_tokens=2000
                )

                texto = response.output_text
                all_texts.append(texto)
                progress.progress((i+1)/len(doc))


        st.success("OCR completado")

        with st.expander("Ver texto extraído"):
            for idx, txt in enumerate(all_texts):
                st.markdown(f"### Página {idx+1}\n\n{txt}\n\n---")


        # ===========================================================
        # 2) ANÁLISIS LEGAL — GPT-5-mini (500,000 TPM)
        # ===========================================================

        full_text = "\n\n".join(all_texts)

        prompt_tabla = f"""
Eres un analista legal experto en contratos públicos.

Llena esta TABLA EXACTA, sin cambiar el formato:

| Campo | Respuesta |
|-------|-----------|
| Partes | [...] |
| Objeto | [...] |
| Monto antes de IVA | [...] |
| IVA | [...] |
| Monto total | [...] |
| Fecha de inicio | [...] |
| Fecha de fin | [...] |
| Vigencia/Plazo | [...] |
| Garantía(s) | [...] |
| Obligaciones proveedor | [...] |
| Supervisión | [...] |
| Penalizaciones | [...] |
| Penalización máxima | [...] |
| Modificaciones | [...] |
| Normatividad aplicable | [...] |
| Resolución de controversias | [...] |
| Firmas | [...] |
| Anexos | [...] |
| No localizado | [...] |
| Áreas de mejora | [...] |

Reglas:
- Usa SOLO información literal del contrato.
- Si un dato no aparece, escribe: **NO LOCALIZADO**.
- No expliques nada fuera de la tabla.

TEXTO COMPLETO DEL CONTRATO:
{full_text}
"""

        response_final = safe_gpt(
            client,
            model="gpt-5-mini",              # 🌟 SIN RATE LIMIT
            input_data=[
                {"role": "system", "content": "Eres un experto legal en contratos públicos."},
                {"role": "user", "content": prompt_tabla}
            ],
            max_output_tokens=2500
        )

        resultado = response_final.output_text

        st.success("¡Análisis completado!")
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
    st.info("Ingresa tus credenciales para comenzar.")
