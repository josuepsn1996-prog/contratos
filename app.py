import streamlit as st
import streamlit_authenticator as stauth
import openai
import base64
import tempfile
import fitz  # PyMuPDF

# --- Configuración de usuarios y contraseñas (hashes ya generados para '1234') ---
names = ['Usuario Uno', 'Usuario Dos']
usernames = ['usuario1', 'usuario2']
passwords = [
    '$2b$12$WrEB8mTcBlJKMlhBQSi2K.g6w86H17OIM1Aj8J6rwWtThvP5r99Ji',  # 1234
    '$2b$12$WrEB8mTcBlJKMlhBQSi2K.g6w86H17OIM1Aj8J6rwWtThvP5r99Ji',  # 1234
]

authenticator = stauth.Authenticate(
    names, usernames, passwords,
    'mi_app_streamlit', 'cookie_firma_unica', cookie_expiry_days=7
)

name, authentication_status, username = authenticator.login('Iniciar sesión', 'main')

if authentication_status:
    st.sidebar.success(f"Bienvenido/a: {name}")
    authenticator.logout("Cerrar sesión", "sidebar")
    
    # --- App principal (igual que tu código original) ---
    st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
    st.title("📄 Análisis Inteligente de Contratos de la Administración Pública")

    st.markdown("""
    Carga tu contrato público (PDF, escaneado o digital).  
    La IA extrae y consolida los **elementos legales más importantes** del contrato, en formato estandarizado y comparativo para todos los casos.

    **Necesitas tu clave de API de [OpenAI](https://platform.openai.com/api-keys)**
    """)

    st.warning(
        "⚠️ Esta app funciona con contratos PDF digitales (texto seleccionable) o escaneados (imagen). "
        "Si el PDF es digital, el análisis será mucho más rápido y barato. "
        "La extracción de cifras y porcentajes es textual, sin modificar el formato, para máxima precisión."
    )

    api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
    uploaded_file = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

    if uploaded_file and api_key:
        openai.api_key = api_key

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

        if is_digital:
            st.info("Extrayendo texto directamente (rápido y barato)...")
            for i, page_text in enumerate(digital_texts):
                st.write(f"Procesando página {i + 1} de {len(doc)} (digital)...")
                all_texts.append(page_text)
                progress_bar.progress((i+1)/len(doc))
        else:
            st.info("Convirtiendo páginas a imagen y usando IA Vision para OCR...")
            for i, page in enumerate(doc):
                st.write(f"Procesando página {i + 1} de {len(doc)} (imagen)...")
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                messages = [
                    {"role": "system", "content": "Eres un experto en contratos públicos y OCR legal."},
                    {"role": "user", "content": [
                        {"type": "text", "text": (
                            "Lee la imagen adjunta de un contrato, extrae todo el texto útil y, si detectas información de partes, objeto, monto, plazo, garantías, "
                            "obligaciones, penalizaciones, modificaciones, normatividad aplicable, resolución de controversias, firmas o anexos, indícalo claramente. "
                            "No agregues explicaciones, solo texto estructurado."
                        )},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                    ]}
                ]
                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    max_tokens=2048,
                )
                page_text = response.choices[0].message.content
                all_texts.append(page_text)
                progress_bar.progress((i+1)/len(doc))

        st.success("¡Extracción completada!")

        with st.expander("Ver texto extraído de cada página"):
            for idx, txt in enumerate(all_texts):
                st.markdown(f"**Página {idx+1}:**\n\n{txt}\n---")

        st.info("Consolidando elementos legales con IA...")

        full_text = "\n\n".join(all_texts)

        prompt_final = (
            "Eres un analista legal experto en contratos públicos. Recibiste el texto extraído de un contrato de la administración pública mexicana. "
            "DEBES LLENAR CADA CAMPO DE LA SIGUIENTE TABLA (presenta solo la tabla, formato markdown, nada más) con la información literal del texto, sin explicar, resumir, interpretar, fusionar, ni reorganizar datos. "
            "NO inventes, NO omitas, NO combines, NO uses frases generales. Si no encuentras el dato, escribe 'NO LOCALIZADO' exactamente así, sin adornos. "
            "NO repitas el texto del contrato ni des contexto fuera de la tabla. NO elimines ningún campo aunque esté vacío. "
            "SIEMPRE utiliza el mismo orden y formato."
            "\n\n"
            "| Campo                       | Respuesta                                                         |\n"
            "|-----------------------------|--------------------------------------------------------------------|\n"
            "| Partes                      | Por la Secretaría: [Nombres y cargos literales]. Por el Proveedor: [Nombres, cargos, razón social literal]. |\n"
            "| Objeto                      | [Todos los servicios, bienes u obras, uno por renglón literal].    |\n"
            "| Monto antes de IVA          | $[####,###.##] MXN (literal).                                      |\n"
            "| IVA                         | $[####,###.##] MXN (literal).                                      |\n"
            "| Monto total                 | $[####,###.##] MXN (literal).                                      |\n"
            "| Fecha de inicio             | [Fecha literal].                                                   |\n"
            "| Fecha de fin                | [Fecha literal].                                                   |\n"
            "| Vigencia/Plazo              | [Literal].                                                        |\n"
            "| Garantía(s)                 | [Tipo, porcentaje y condiciones de cada garantía, literal].        |\n"
            "| Obligaciones proveedor      | [Cada obligación textual, en renglón aparte].                     |\n"
            "| Supervisión                 | [Cargo(s), nombre(s) responsable(s) textual(es)].                  |\n"
            "| Penalizaciones              | [Cada penalización, monto y condición, renglón aparte, literal].   |\n"
            "| Penalización máxima         | [Literal].                                                        |\n"
            "| Modificaciones              | [Procedimiento, máximo permitido, fundamento legal, renglón aparte, literal]. |\n"
            "| Normatividad aplicable      | [Cada ley, reglamento, NOM o código textual, renglón aparte].      |\n"
            "| Resolución de controversias | [Literal. Si no hay procedimiento, inicia con 'NO LOCALIZADO.'].   |\n"
            "| Firmas                      | Por la Secretaría: [Nombres y cargos]. Por el Proveedor: [Nombres, cargos, razón social]. |\n"
            "| Anexos                      | Número, nombre y descripción literal de cada anexo.                |\n"
            "| No localizado               | [Lista concreta de todo campo importante, dato o requisito legal que falte o esté incompleto. Si todo está, pon 'Ninguno.'] |\n"
            "| Áreas de mejora             | [Cada área de posible subjetividad, ambigüedad o riesgo de controversia. Si no hay, pon 'Ninguna.'] |\n"
            "\n"
            "LLENA CADA CAMPO CON SOLO LA INFORMACIÓN LITERAL DEL CONTRATO. NO CAMBIES EL FORMATO DE LA TABLA. "
            "Aquí está el texto del contrato:\n\n"
            + full_text
        )

        response_final = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Eres un experto en contratos públicos. Devuelve solo la tabla, siguiendo exactamente el formato y campos indicados, sin texto extra, sin contexto ni interpretaciones."},
                {"role": "user", "content": prompt_final}
            ],
            max_tokens=4096,
        )
        resultado = response_final.choices[0].message.content

        st.success("¡Análisis general completado!")
        st.markdown("### Ficha estandarizada de contrato de administración pública:")
        st.markdown(resultado)

        st.download_button(
            "Descargar ficha (Markdown)",
            data=resultado,
            file_name="ficha_contrato_publico.md",
            mime="text/markdown"
        )
    else:
        st.info("Sube un PDF y tu clave de OpenAI para comenzar.")

elif authentication_status is False:
    st.error("Usuario o contraseña incorrectos")
elif authentication_status is None:
    st.info("Por favor ingresa tus credenciales")
