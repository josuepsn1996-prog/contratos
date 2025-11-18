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

def safe_gpt(client, model, input_data, max_output_tokens=1500, retries=5):
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
    st.title("📄 Análisis Inteligente de Contratos Públicos (GPT-5.1)")

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

        page_summaries = []
        progress = st.progress(0)

        # ===========================================================
        # 1) OCR + RESUMEN POR PÁGINA — GPT-5.1
        # ===========================================================

        st.info("Extrayendo y normalizando contenido página por página...")

        for i, page in enumerate(doc if not is_digital else digital_pages):

            if is_digital:
                text = page
                img_base64 = None
            else:
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

            # Prompt para extraer solo información útil
            input_payload = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Extrae solo la información útil legal de esta página de contrato "
                                "(partes, objeto, montos, plazos, obligaciones, garantías, firmas, penalizaciones, anexos). "
                                "Devuelve texto ordenado. No inventes."
                            )
                        }
                    ]
                }
            ]

            if img_base64:
                input_payload[0]["content"].append({
                    "type": "input_image",
                    "image": {"base64": img_base64}
                })
            else:
                input_payload[0]["content"].append({
                    "type": "input_text",
                    "text": text
                })

            r = safe_gpt(
                client,
                model="gpt-5.1",
                input_data=input_payload,
                max_output_tokens=1200
            )

            resumen = r.output_text
            page_summaries.append(resumen)

            progress.progress((i + 1) / len(doc))

        st.success("Texto consolidado por página generado.")


        # ===========================================================
        # 2) CONSOLIDACIÓN GLOBAL — GPT-5.1
        # ===========================================================

        st.info("Creando resumen legal consolidado...")

        texto_reducido = "\n\n".join(page_summaries)

        consolidacion_prompt = f"""
Eres un analista legal experto en contratos públicos.
Consolida toda esta información legal en una sola versión limpia:

{texto_reducido}

Devuelve el texto consolidado, sin tabla todavía.
"""

        r_consolidado = safe_gpt(
            client,
            model="gpt-5.1",
            input_data=[{"role": "user", "content": consolidacion_prompt}],
            max_output_tokens=2000
        )

        resumen_final = r_consolidado.output_text


        # ===========================================================
        # 3) TABLA FINAL — GPT-5.1 (FORMATO SIEMPRE ESTABLE)
        # ===========================================================

        tabla_prompt = f"""
Usa la siguiente información consolidada de un contrato público para llenar ESTA TABLA EXACTA:

INFORMACIÓN:
{resumen_final}

TABLA A LLENAR (NO CAMBIES NADA):

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

REGLAS:
- Usa SOLO información literal encontrada.
- Si falta un dato, usa "NO LOCALIZADO".
- No agregues texto fuera de la tabla.
"""

        r_tabla = safe_gpt(
            client,
            model="gpt-5.1",
            input_data=[{"role": "user", "content": tabla_prompt}],
            max_output_tokens=2500
        )

        tabla = r_tabla.output_text

        st.success("¡Análisis completado!")
        st.markdown("### Ficha estandarizada del contrato:")
        st.markdown(tabla)

else:
    if authentication_status is False:
        st.error("Usuario o contraseña incorrectos")
    else:
        st.info("Ingresa tus credenciales par
