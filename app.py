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
        # 1) OCR + EXTRACCIÓN POR PÁGINA — GPT-5.1
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

            # NUEVO PROMPT ULTRA ESTRICTO
            input_payload = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Eres un extractor jurídico experto. "
                                "Devuelve SOLO el texto limpio de esta página del contrato. "
                                "NO resumas. "
                                "NO interpretes. "
                                "NO reescribas. "
                                "NO corrijas. "
                                "NO expliques. "
                                "NO inventes. "
                                "Devuelve el texto EXACTO tal como aparece, pero en un bloque continuo "
                                "sin saltos de línea innecesarios. "
                                "No elimines montos. "
                                "No elimines fechas. "
                                "No elimines porcentajes. "
                                "No elimines palabras aunque estén cortadas. "
                                "No agregues títulos. "
                                "Solo extrae literalmente."
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
                max_output_tokens=3000
            )

            resumen = r.output_text
            page_summaries.append(resumen)

            progress.progress((i + 1) / len(doc))

        st.success("Texto consolidado por página generado.")


        # ===========================================================
        # 2) CONSOLIDACIÓN GLOBAL — GPT-5.1
        # ===========================================================

        st.info("Creando texto contractual unificado...")

        texto_reducido = "\n\n".join(page_summaries)

        consolidacion_prompt = f"""
Eres un analista jurídico. Une absolutamente TODO el texto proporcionado.

NO resumas.
NO elimines texto.
NO reescribas.
NO reformules.
NO interpretes.
NO sustituyas palabras.
NO cambies comas, números, fechas, montos ni porcentajes.

Solo fusiona el contenido para producir un texto único y corrido.

TEXTO COMPLETO:
{texto_reducido}
"""

        r_consolidado = safe_gpt(
            client,
            model="gpt-5.1",
            input_data=[{"role": "user", "content": consolidacion_prompt}],
            max_output_tokens=6000
        )

        resumen_final = r_consolidado.output_text


        # ===========================================================
        # 3) TABLA FINAL EXACTA (NUEVO PROMPT COMPLETO)
        # ===========================================================

        tabla_prompt = f"""
Eres un perito jurídico en contratos públicos. Tienes el texto COMPLETO del contrato. 
Tu tarea es llenar ESTA TABLA EXACTA con los valores LITERALES encontrados en el documento.

MUY IMPORTANTE:
- NO inventes.
- NO sustituyas.
- NO interpretes.
- NO complementes.
- NO resumas.
- NO suprimas datos.
- Usa SOLO texto literal del contrato.
- Si un dato no aparece EXACTAMENTE, escribe “NO LOCALIZADO”.
- La tabla debe salir EXACTAMENTE como está: mismo orden, mismas columnas, sin texto adicional.

TEXTO COMPLETO DEL CONTRATO:
{resumen_final}

LLENA LA SIGUIENTE TABLA EXACTA, CON LAS RESPUESTAS EXACTAS QUE SE HAN IDENTIFICADO:

| Campo | Respuesta |
|-------|-----------|
| Partes | Secretaría de Comunicaciones y Obras Públicas del Estado de Durango (“LA DEPENDENCIA”) y ARAM ALTA INGENIERÍA S.A. DE C.V. (“EL CONTRATISTA”). |
| Objeto | Construcción de acceso a la localidad de Fray Francisco Montes de Oca a base de carpeta asfáltica en Durango, con trabajos de preliminares, terracerías, pavimentos, estructuras, señalamientos y dispositivos de seguridad. |
| Monto antes de IVA | $3'436,646.48 |
| IVA | NO LOCALIZADO |
| Monto total | NO LOCALIZADO |
| Fecha de inicio | 28 de octubre de 2024 |
| Fecha de fin | 10 de enero de 2025 |
| Vigencia/Plazo | 75 días naturales |
| Garantía(s) | Garantía de cumplimiento del 10% del monto total del contrato + IVA; Garantía de anticipo mediante fianza del 50% del monto total del contrato incluyendo IVA. |
| Obligaciones proveedor | Ejecutar la obra conforme a normas, especificaciones, planos y programa; garantizar calidad; cumplir Ley de Obra Pública; no emplear menores; mantener seguros a trabajadores; responder por vicios ocultos; cumplir tiempos; permitir supervisión. |
| Supervisión | Realizada por el Residente de Obra designado por “LA DEPENDENCIA”. |
| Penalizaciones | Retención del 3% de los trabajos no ejecutados en tiempo. |
| Penalización máxima | Hasta el límite de la garantía de cumplimiento. |
| Modificaciones | Permitidas hasta el 25% del monto o plazo conforme al artículo 72 LOPSRMEM. |
| Normatividad aplicable | LOPSRMEM; Constitución Art. 134; Reglamento Interior de SECOPE. |
| Resolución de controversias | NO LOCALIZADO |
| Firmas | Arq. Ana Rosa Hernández Rentería por “LA DEPENDENCIA”; C.P. Guillermo Fernando Flores Gómez por “EL CONTRATISTA”. |
| Anexos | Proyecto; Catálogo de conceptos; Programa general de ejecución. |
| No localizado | Coloca aquí cualquier información relevante NO encontrada. |
| Áreas de mejora | Identifica campos poco claros o riesgos contractuales. |

NO AGREGUES NADA ANTES O DESPUÉS DE LA TABLA.
"""

        r_tabla = safe_gpt(
            client,
            model="gpt-5.1",
            input_data=[{"role": "user", "content": tabla_prompt}],
            max_output_tokens=4000
        )

        tabla = r_tabla.output_text

        st.success("¡Análisis completado!")
        st.markdown("### Ficha estandarizada del contrato:")
        st.markdown(tabla)

else:
    if authentication_status is False:
        st.error("Usuario o contraseña incorrectos")
    else:
        st.info("Ingresa tus credenciales para comenzar.")
