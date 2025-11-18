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
    """
    Wrapper para llamar a OpenAI Responses con reintentos automáticos
    ante errores de rate limit.
    """
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

        # Guardar PDF temporalmente
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

        page_texts = []
        progress = st.progress(0)

        # ===========================================================
        # 1) EXTRACCIÓN POR PÁGINA — GPT-5.1 (sin resumen)
        # ===========================================================

        st.info("Extrayendo contenido página por página...")

        for i, page in enumerate(doc if not is_digital else digital_pages):

            if is_digital:
                text = page
                img_base64 = None
            else:
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

            # Prompt para extraer texto literal de la página
            input_payload = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Eres un extractor jurídico experto. "
                                "Devuelve SOLO el texto de esta página del contrato. "
                                "NO resumas. "
                                "NO interpretes. "
                                "NO reescribas. "
                                "NO corrijas ortografía. "
                                "NO comentes nada. "
                                "NO inventes. "
                                "Devuelve el texto tal cual, pero en un solo bloque continuo, "
                                "uniendo palabras cortadas por saltos de línea cuando sea obvio. "
                                "No elimines montos, no elimines fechas, no elimines porcentajes."
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
                max_output_tokens=4000
            )

            texto_pagina = r.output_text
            page_texts.append(texto_pagina)

            progress.progress((i + 1) / len(doc))

        st.success("Texto extraído página por página.")

        # ===========================================================
        # 2) TEXTO CONTRACTUAL UNIFICADO (SIN GPT)
        # ===========================================================

        st.info("Uniendo texto de todas las páginas...")

        # Aquí ya NO usamos GPT para consolidar, solo concatenamos en Python
        texto_contrato_completo = "\n\n".join(page_texts)

        # Puedes mostrarlo en un expander para debug:
        with st.expander("Ver texto completo extraído (debug)", expanded=False):
            st.text_area("Texto consolidado", value=texto_contrato_completo, height=300)

        # ===========================================================
        # 3) TABLA FINAL — GPT-5.1 (EXTRACCIÓN ESTRICTA CAMPO POR CAMPO)
        # ===========================================================

        st.info("Generando ficha estandarizada del contrato...")

        tabla_prompt = f"""
Eres un perito jurídico experto en contratos de obra pública y adquisiciones del gobierno.

Tienes el texto COMPLETO de un contrato de obra pública. Debes llenar UNA TABLA en formato Markdown
con dos columnas: "Campo" y "Respuesta", siguiendo EXACTAMENTE esta estructura:

| Campo | Respuesta |
|-------|-----------|
| Partes | ... |
| Objeto | ... |
| Monto antes de IVA | ... |
| IVA | ... |
| Monto total | ... |
| Fecha de inicio | ... |
| Fecha de fin | ... |
| Vigencia/Plazo | ... |
| Garantía(s) | ... |
| Obligaciones proveedor | ... |
| Supervisión | ... |
| Penalizaciones | ... |
| Penalización máxima | ... |
| Modificaciones | ... |
| Normatividad aplicable | ... |
| Resolución de controversias | ... |
| Firmas | ... |
| Anexos | ... |
| No localizado | ... |
| Áreas de mejora | ... |

REGLAS GENERALES:
- Usa SOLO información que esté en el texto del contrato.
- NO inventes nada.
- Si un dato NO aparece claramente en el texto, escribe exactamente: NO LOCALIZADO.
- NO agregues texto antes ni después de la tabla.
- Usa SIEMPRE la sintaxis de tabla Markdown (con | y la fila de separación ---).

REGLAS ESPECÍFICAS POR CAMPO:

1) Partes:
   - Identifica a la dependencia o entidad pública y a la empresa contratista.
   - Devuelve una sola oración, por ejemplo:
     Secretaría de Comunicaciones y Obras Públicas del Estado de Durango (“LA DEPENDENCIA”) y ARAM ALTA INGENIERÍA S.A. DE C.V. (“EL CONTRATISTA”).

2) Objeto:
   - Localiza la cláusula “OBJETO DEL CONTRATO” o similar.
   - Devuelve una frase que describa la obra, limpia, en una sola oración.
   - Ejemplo de estilo:
     Construcción de acceso a la localidad de Fray Francisco Montes de Oca a base de carpeta asfáltica en el municipio de Durango, con trabajos de preliminares, terracerías, pavimentos, estructuras, señalamientos y dispositivos de seguridad.

3) Monto antes de IVA:
   - Busca el párrafo donde se indique algo como: “El monto total del presente contrato es la cantidad de $ X ... Más el impuesto al valor agregado”.
   - Devuelve SOLO la cantidad numérica con signo de pesos, tal como aparece en el contrato.
   - Por ejemplo: $3'436,646.48
   - NO incluyas el texto en letras, solo el número.

4) IVA:
   - Si dice literalmente “Más el impuesto al valor agregado”, devuelve exactamente esa frase.
   - Si se especifica un porcentaje de IVA, escríbelo.
   - Si no se menciona el IVA, escribe: NO LOCALIZADO.

5) Monto total:
   - SOLO llena este campo si el contrato indica explícitamente el monto total con IVA desglosado.
   - Si NO aparece expresado el monto total ya con IVA, escribe: NO LOCALIZADO.

6) Fecha de inicio:
   - Busca en la cláusula de plazo algo como: “El inicio de la ejecución de los trabajos será el día XX de mes de AAAA”.
   - Devuelve SOLO la fecha en formato texto, por ejemplo: 28 de octubre de 2024.
   - NO incluyas frases como “El inicio de la ejecución será el día...”, solo la fecha.

7) Fecha de fin:
   - Igual que la anterior, pero con la frase “se concluirá a más tardar el día...”.
   - Devuelve SOLO la fecha, por ejemplo: 10 de enero de 2025.

8) Vigencia/Plazo:
   - Devuelve SOLO el plazo en forma compacta, por ejemplo: 75 días naturales.

9) Garantía(s):
   - Busca las cláusulas de “Garantía de Cumplimiento”, “Garantía de Anticipo” y “Vicios Ocultos”.
   - Resume en UNA ORACIÓN clara los tipos de garantía y sus porcentajes.
   - Ejemplo de estilo (sólo como referencia de forma, no lo copies si no aplica):
     Garantía de cumplimiento del 10% del monto total del contrato más IVA y garantía de anticipo mediante fianza del 50% del monto total del contrato incluyendo IVA.

10) Obligaciones proveedor:
   - Identifica las obligaciones principales de “EL CONTRATISTA”: ejecutar la obra conforme a proyectos y especificaciones, calidad, plazos, cumplimiento de leyes laborales y fiscales, no emplear menores, responder por vicios ocultos, etc.
   - Devuelve una sola oración que las resuma.

11) Supervisión:
   - Localiza la referencia al Residente de Obra o figura encargada de revisar y autorizar estimaciones y trabajos.
   - Devuelve una frase del tipo:
     La supervisión y autorización de los trabajos y estimaciones está a cargo del Residente de Obra designado por la dependencia.

12) Penalizaciones:
   - Busca la cláusula de “RETENCIONES Y PENAS CONVENCIONALES” o similar.
   - Extrae las penalizaciones principales, por ejemplo el 3% de trabajos no ejecutados en tiempo.
   - Devuelve una oración breve mencionando porcentaje y condición.

13) Penalización máxima:
   - Si el contrato indica que las penas no pueden exceder cierto límite (por ejemplo, el monto de la garantía de cumplimiento), escríbelo.
   - Si no se menciona límite máximo, escribe: NO LOCALIZADO.

14) Modificaciones:
   - Busca la cláusula de modificaciones al contrato (referencias al artículo 72 de la LOPSRMEM, 25% del monto o plazo, etc.).
   - Devuelve una oración clara del tipo:
     Modificaciones permitidas hasta el 25% del monto o plazo, conforme al artículo 72 de la LOPSRMEM, sin cambiar la naturaleza del objeto.

15) Normatividad aplicable:
   - Enumera las principales normas citadas: Constitución, LOPSRMEM, Reglamento Interior, etc.
   - Escríbelas separadas por punto y coma en una sola línea.

16) Resolución de controversias:
   - Si el contrato menciona mecanismos específicos (tribunales, sede, ley aplicable), descríbelos brevemente.
   - Si no se menciona nada, escribe: NO LOCALIZADO.

17) Firmas:
   - Identifica quién firma por la dependencia y quién firma por el contratista.
   - Devuelve una sola frase mencionando ambos nombres y cargos.
   - Si no está claramente en el texto proporcionado, escribe: NO LOCALIZADO.

18) Anexos:
   - Enumera los anexos que el contrato menciona expresamente (proyecto, catálogo de conceptos, programa de ejecución, etc.).
   - Escríbelos en una sola línea.

19) No localizado:
   - En este campo, enumera TODOS los campos de la tabla que hayan quedado como “NO LOCALIZADO”.
   - Si todos los campos fueron localizados, escribe: Ninguno.

20) Áreas de mejora:
   - Señala en una o dos frases aspectos del contrato que podrían estar poco claros, ser riesgosos o susceptibles de controversia (por ejemplo: falta de monto total con IVA, falta de detalle en penalizaciones, etc.).
   - Si no detectas nada relevante, escribe: NO LOCALIZADO.

TEXTO COMPLETO DEL CONTRATO:
{texto_contrato_completo}

RECUERDA:
- Devuelve ÚNICAMENTE la tabla Markdown.
- No incluyas explicaciones, notas ni texto adicional.
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
