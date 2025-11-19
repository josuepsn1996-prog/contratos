import streamlit as st
import streamlit_authenticator as stauth
from openai import OpenAI, RateLimitError
import tempfile
import fitz
import time
import re
import requests
from io import BytesIO
import pandas as pd

# ===============================================================
# CONFIGURACIÓN BÁSICA DE LA APP
# ===============================================================

st.set_page_config(page_title="Análisis de Contratos Públicos (IA)", page_icon="📄")

# ===============================================================
# FUNCIÓN DE REINTENTOS ANTI RATE LIMIT (OPENAI)
# ===============================================================

def safe_gpt(client, model, input_data, max_output_tokens=4000, retries=5):
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
    raise Exception("Rate limit persistente. Intenta de nuevo más tarde.")

# ===============================================================
# CONFIGURACIÓN LOGIN STREAMLIT (USUARIOS)
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
    'preauthorized': {'emails': []}
}

authenticator = stauth.Authenticate(
    config['credentials'],
    'mi_app_streamlit',
    'cookie_firma_unica',
    7
)

name, authentication_status, username = authenticator.login("Iniciar sesión", "main")

# ===============================================================
# CONFIGURACIÓN GOOGLE SHEETS (CONSTANTES)
# ===============================================================

SPREADSHEET_ID = "1wCVD_3Ph7yrv1Nxu-ck3Hf4wBbohtsfcvPQhW2hrz64"
SHEET_RANGE = "Contratos!A:Z"  # asume que la hoja se llama "Contratos"

HEADERS_CONTRATO = [
    "Partes",
    "Objeto",
    "Monto antes de IVA",
    "IVA",
    "Monto total",
    "Fecha de inicio",
    "Fecha de fin",
    "Vigencia/Plazo",
    "Garantía(s)",
    "Obligaciones proveedor",
    "Supervisión",
    "Penalizaciones",
    "Penalización máxima",
    "Modificaciones",
    "Normatividad aplicable",
    "Resolución de controversias",
    "Firmas",
    "Anexos",
    "No localizado",
    "Áreas de mejora"
]

# ===============================================================
# FUNCIONES AUXILIARES: GOOGLE OAUTH + SHEETS
# ===============================================================

def get_google_oauth_config():
    cfg = st.secrets["google_oauth"]
    return {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"]
    }

def get_google_auth_url():
    cfg = get_google_oauth_config()
    base = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "access_type": "offline",
        "prompt": "consent"
    }
    from urllib.parse import urlencode
    return f"{base}?{urlencode(params)}"

def exchange_code_for_tokens(code: str):
    cfg = get_google_oauth_config()
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
        "grant_type": "authorization_code"
    }
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    return resp.json()  # incluye access_token, refresh_token, expires_in, etc.

def refresh_access_token(refresh_token: str):
    cfg = get_google_oauth_config()
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    return resp.json()

def append_row_to_sheet(access_token: str, values_row):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SHEET_RANGE}:append"
    params = {
        "valueInputOption": "USER_ENTERED"
    }
    body = {
        "majorDimension": "ROWS",
        "values": [values_row]
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, params=params, json=body, headers=headers)
    if resp.status_code == 401:
        raise PermissionError("No autorizado o token expirado")
    resp.raise_for_status()
    return resp.json()

def ensure_google_token():
    """
    Se asegura de que tengamos un access_token válido en st.session_state["google_token"].
    Si no lo hay:
      - intenta leer ?code= de la URL y hacer el intercambio
      - si no hay code, muestra link de autorización
    Devuelve access_token (str) o None si aún no se ha autorizado.
    """
    if "google_token" not in st.session_state:
        st.session_state["google_token"] = {}

    token_data = st.session_state["google_token"]

    # Si ya hay access_token y no manejamos expiración detallada, lo usamos
    if "access_token" in token_data and "refresh_token" in token_data:
        return token_data["access_token"]

    # Revisar si hay "code" en la URL (primer intercambio)
    query_params = st.experimental_get_query_params()
    code = query_params.get("code", [None])[0]

    if code:
        # Intercambiamos el code por tokens
        try:
            tokens = exchange_code_for_tokens(code)
            # Guardamos tokens en sesión
            st.session_state["google_token"] = {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in"),
                "scope": tokens.get("scope"),
                "token_type": tokens.get("token_type")
            }
            # Limpiar parámetros de la URL (opcional, pero Streamlit no lo hace nativo)
            st.success("Google autorizado correctamente. Ya puedes exportar a Sheets.")
            return st.session_state["google_token"]["access_token"]
        except Exception as e:
            st.error(f"Error al intercambiar código de Google OAuth: {e}")
            return None
    else:
        # No hay token ni code -> mostrar link de autorización
        auth_url = get_google_auth_url()
        st.warning("Para exportar a Google Sheets, primero autoriza el acceso con tu cuenta de Google.")
        st.markdown(f"[Haz clic aquí para autorizar con Google]({auth_url})")
        return None

def get_or_refresh_access_token():
    """
    Devuelve un access_token válido.
    Si falla con 401 al escribir en Sheets, se intenta refrescar.
    """
    if "google_token" not in st.session_state:
        st.session_state["google_token"] = {}

    token_data = st.session_state["google_token"]

    # Si no tenemos tokens aún, intentar obtenerlos
    if "access_token" not in token_data or "refresh_token" not in token_data:
        access = ensure_google_token()
        return access

    # Intentamos usar el access_token actual; si luego Sheets responde 401, refrescamos.
    return token_data["access_token"]

def exportar_a_google_sheets(campos_dict):
    """
    Toma el diccionario {Campo: Respuesta} y lo envía como nueva fila al Sheet.
    """
    access_token = get_or_refresh_access_token()
    if not access_token:
        # ensure_google_token ya mostró link/mensaje
        return

    # Ordenar los valores según HEADERS_CONTRATO
    row = [campos_dict.get(col, "") for col in HEADERS_CONTRATO]

    try:
        append_row_to_sheet(access_token, row)
        st.success("Ficha exportada correctamente a Google Sheets.")
    except PermissionError:
        # Intentamos refrescar el token y reintentar una vez
        token_data = st.session_state.get("google_token", {})
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            st.error("No se encontró refresh_token. Vuelve a autorizar con Google.")
            ensure_google_token()
            return
        try:
            new_tokens = refresh_access_token(refresh_token)
            st.session_state["google_token"]["access_token"] = new_tokens.get("access_token")
            # Reintentar
            append_row_to_sheet(st.session_state["google_token"]["access_token"], row)
            st.success("Ficha exportada correctamente a Google Sheets (tras refrescar token).")
        except Exception as e:
            st.error(f"No se pudo refrescar el token ni exportar a Sheets: {e}")
    except Exception as e:
        st.error(f"Error al exportar a Google Sheets: {e}")

# ===============================================================
# FUNCIONES AUXILIARES: PARSEAR TABLA MARKDOWN Y DESCARGA LOCAL
# ===============================================================

def parse_markdown_table(tabla_markdown: str):
    """
    Recibe la tabla en formato Markdown (la que genera el modelo)
    y devuelve un dict {Campo: Respuesta}
    """
    campos = {}
    lines = tabla_markdown.splitlines()

    # Filtrar solo líneas que empiezan con '|'
    lines = [l.strip() for l in lines if l.strip().startswith("|")]

    if len(lines) < 3:
        return campos  # algo raro

    # Saltamos encabezado y separador
    data_lines = lines[2:]

    for line in data_lines:
        # | Campo | Respuesta |
        partes = [c.strip() for c in line.strip("|").split("|")]
        if len(partes) < 2:
            continue
        campo, respuesta = partes[0], partes[1]
        campos[campo] = respuesta

    return campos

def crear_excel_ficha(campos_dict):
    """
    Crea un archivo Excel en memoria con una sola fila que corresponde a la ficha del contrato.
    Devuelve BytesIO listo para usar en st.download_button.
    """
    data = {col: [campos_dict.get(col, "")] for col in HEADERS_CONTRATO}
    df = pd.DataFrame(data)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="FichaContrato")
    buffer.seek(0)
    return buffer

# ===============================================================
# APP PRINCIPAL (LÓGICA DE ANÁLISIS DE CONTRATO)
# ===============================================================

if authentication_status:

    st.sidebar.success(f"Bienvenido/a: {name}")
    authenticator.logout("Cerrar sesión", "sidebar")

    st.title("📄 Análisis Inteligente de Contratos de Obra Pública (IA + Exportación)")

    api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
    archivo = st.file_uploader("Sube tu contrato PDF", type=["pdf"])

    if archivo and api_key:

        client = OpenAI(api_key=api_key)

        # Guardar archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(archivo.read())
            tmp_path = tmp.name

        st.info("Extrayendo texto del PDF...")

        # 1) Extraer texto con PyMuPDF
        doc = fitz.open(tmp_path)
        full_text = ""
        for page in doc:
            page_text = page.get_text("text")
            full_text += page_text + "\n\n"

        # 2) Limpiar texto
        def limpiar_texto(t):
            t = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", t)
            t = re.sub(r"\n(?!\n)", " ", t)
            t = re.sub(r"\s{2,}", " ", t)
            t = t.replace("�", "").replace("●", "").replace("•", "")
            return t.strip()

        texto_limpio = limpiar_texto(full_text)

        with st.expander("Mostrar texto extraído (debug)", expanded=False):
            st.text_area("Texto limpio:", texto_limpio, height=300)

        # 3) Prompt EXACTO que definiste
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
{texto_limpio}

RECUERDA:
- Devuelve ÚNICAMENTE la tabla Markdown.
- No incluyas explicaciones, notas ni texto adicional.
"""

        # Llamada a GPT-5.1 para generar la tabla
        respuesta = safe_gpt(
            client,
            model="gpt-5.1",
            input_data=[{"role": "user", "content": tabla_prompt}],
            max_output_tokens=3500
        )

        tabla = respuesta.output_text

        st.success("¡Análisis completado!")
        st.markdown("### Ficha estandarizada del contrato:")
        st.markdown(tabla)

        # Parsear la tabla Markdown a dict
        campos_dict = parse_markdown_table(tabla)

        # Botones de exportación
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("📤 Exportar a Google Sheets"):
                exportar_a_google_sheets(campos_dict)

        with col2:
            buffer_excel = crear_excel_ficha(campos_dict)
            st.download_button(
                "💾 Descargar ficha (Excel)",
                data=buffer_excel,
                file_name="ficha_contrato.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

else:
    if authentication_status is False:
        st.error("Usuario o contraseña incorrectos")
    else:
        st.info("Ingresa tus credenciales para comenzar.")
