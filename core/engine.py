"""Motor de procesamiento de NoticiasINE.

Contiene descarga, parsing, filtrado, IA y generación de documentos.
La interfaz gráfica vive en ui.py.
"""

import xml.etree.ElementTree as ET
import re
import glob
import os
import time
import threading
import locale
import html
from datetime import datetime, timedelta
import json
import openai
import tkinter as tk
from fpdf import FPDF
from tkinter import messagebox, filedialog
import customtkinter as ctk
from ftplib import FTP
import sys
from dotenv import load_dotenv

# Ruta base del proyecto (donde está el ejecutable o app.py)
if getattr(sys, 'frozen', False):
    # Si estamos ejecutando el binario compilado por PyInstaller
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    # Si estamos ejecutando app.py en entorno de desarrollo
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE_PATH = os.path.join(ROOT_DIR, ".config_ine.json")

# =========================================================
# --- FILTROS POR PALABRAS PROHIBIDAS
# =========================================================

_PALABRAS_PROHIBIDAS = [
    'facturación', 'facturaciones', 'factura', 'facturas', 'facturó', 'facturaron', 
    'ebitda', 'adquiere', 'adquieren', 'fusión', 'fusiones', 'nombra', 'nombran', 
    'premia', 'premian', 'premio', 'premios', 'galardón', 'galardones', 
    'patrocina', 'patrocinan', 'alianza', 'alianzas', 'dimite', 'dimiten', 
    'ceo', 'ceos', 'dividendo', 'dividendos', 'recompra', 'recompras', 
    'salida a bolsa', 'salidas a bolsa', 
    'von der leyen',
    'mercosur', 
    'moda', 'modas', 'publicitaria', 'publicitarias', 
    'campaña', 'campañas', 'lanzamiento', 'lanzamientos', 'juvenil', 'juveniles', 
    'colección', 'colecciones', 'fichaje', 'fichajes', 'marketing', 
    'deportes', 'deporte', 'fútbol', 'baloncesto', 'tenis', 'champions', 
    'cine', 'cines', 'estreno', 'estrenos', 'película', 'películas', 
    'concierto', 'conciertos', 'música', 'artista', 'artistas', 
    'vacaciones', 'actriz', 'actrices', 'vacación', 'viajes', 'viaje', 'cantante', 'cantantes',
    'política', 'políticas', 'partido', 'partidos', 'voto', 'votos', 
    'elecciones', 'elección', 'escaños', 'escaño', 'parlamento', 'parlamentos',
    'multinacional', 'multinacionales', 'corporativo', 'corporativos', 
    'apple', 'macbook', 'macbooks', 'iphone', 'iphones', 'microsoft', 'google', 'amazon', 
    'csic', 'currículo', 'currículos', 'aula', 'aulas', 
    'educación primaria', 'educación secundaria', 'eso','consejo de ministros'  
    # ── Sucesos / Judicial ──
    'asesinato', 'homicidio', 'juzgado', 'audiencia', 'tribunal', 'fiscalía', 'magistrado', 'sentencia', 'cárcel', 'prisión', 'detenido', 'policía', 'guardia civil', 'violencia machista', 'accidente', 'fallecido', 'fallecidos',
    # ── Bolsa / EpData / Ayudas Locales ──
    'ibex', 'bolsa española', 'wall street', 'dow jones', 'epdata', 'ayuntamiento', 'ayuntamientos', 'subvención', 'subvenciones', 'expediente', 'expedientes', 'adif'
]
_RE_PROHIBIDAS = re.compile(r'\b(' + '|'.join(_PALABRAS_PROHIBIDAS) + r')\b', re.IGNORECASE)

# Palabras prohibidas ESTRICTAS (no tienen salvoconducto y se descartan inmediatamente)
_PROHIBIDAS_ESTRICTAS = [
    'bce', 'banco central europeo'
]
_RE_PROHIBIDAS_ESTRICTAS = re.compile(r'\b(' + '|'.join(_PROHIBIDAS_ESTRICTAS) + r')\b', re.IGNORECASE)

# Palabras "salvoconducto": si la noticia contiene alguna de estas,
# se ignoran las palabras prohibidas y pasa directamente a la IA.
# Ejemplo: "apple" está prohibida, pero "apple" + "ere" sí interesa.
_PALABRAS_SALVO = [
    'ere', 'erte', 'empleo', 'empleos', 'política energética',
    'política fiscal', 'políticas fiscales', 'política tributaria', 'políticas tributarias',
    'política económica', 'políticas económicas', 'política monetaria', 'políticas monetarias',
    'política de empleo', 'políticas de empleo', 'política industrial', 'políticas industriales',
    'política comercial', 'políticas comerciales', 'política arancelaria', 'políticas arancelarias',
    'corredor atlántico', 'corredores atlánticos', 'corredor atlantico', 'corredores atlanticos',
    'corredor mediterráneo', 'corredores mediterráneos', 'corredor mediterraneo', 'corredores mediterraneos'
]
_RE_SALVO = re.compile(r'\b(' + '|'.join(_PALABRAS_SALVO) + r')\b', re.IGNORECASE)

# =========================================================
# --- IA CALLS (Con Reintentos y Limpieza de JSON)
# =========================================================
def llamar_ia_con_reintentos(instrucciones, provider, api_key, logger, max_retries=3):
    for intento in range(max_retries):
        try:
            if "Online" in provider:
                # Mapeo de modelos según la selección en la UI
                if "Gemini" in provider:
                    model_id = "google/gemini-2.0-flash-001"
                elif "Llama 3.1" in provider:
                    model_id = "meta-llama/llama-3.1-8b-instruct"
                else:
                    # Por defecto si no es Gemini pero es Online (seguridad)
                    model_id = "google/gemini-2.0-flash-001"

                if intento == 0: logger(f"📡 [AI] Solicitando análisis a {model_id} (OpenRouter)...")
                client = openai.OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                )
                respuesta = client.chat.completions.create(
                    model=model_id,
                    temperature=0.0,
                    messages=[{"role": "user", "content": instrucciones}],
                    stream=True,
                    extra_body={"provider": {"allow_fallbacks": True}}
                )
                
                contenido = ""
                for chunk in respuesta:
                    if chunk.choices and chunk.choices[0].delta.content:
                        contenido += chunk.choices[0].delta.content
                        
                inicio = contenido.find('{')
                fin = contenido.rfind('}') + 1
                if inicio != -1 and fin != -1:
                    contenido = contenido[inicio:fin]
                return json.loads(contenido)
            
                
        except openai.RateLimitError:
            wait_time = (intento + 1) * 12
            logger(f"⏳ [IA] Límite de velocidad (429) alcanzado. Reintentando en {wait_time}s...")
            time.sleep(wait_time)
        except Exception as e:
            wait_time = (intento + 1) * 4
            error_msg = str(e)
            if "invalid_api_key" in error_msg.lower() or "401" in error_msg:
                logger("❌ Error: Clave API no válida o expirada.")
            elif "insufficient_quota" in error_msg.lower() or "402" in error_msg:
                logger("❌ Error: Cuota insuficiente en la cuenta de OpenRouter.")
            else:
                logger(f"⚠️ Intento {intento + 1}/{max_retries} fallido en {provider}: {e}")
            
            if intento < max_retries - 1:
                logger(f"⏳ Reintentando en {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger(f"❌ Error definitivo en IA tras {max_retries} intentos.")
                raise e


# =========================================================
# --- PDF GENERATION
# =========================================================
def limpiar_unicode(texto):
    if not texto: return ""
    # Mapeo de caracteres comunes que no están en Latin-1/Win-1252
    replacements = {
        "–": "-", "—": "-", 
        "“": '"', "”": '"', 
        "‘": "'", "’": "'", 
        "…": "...", "\xa0": " ", 
        "€": "EUR", "•": "*",
        "·": ".", "º": "o", "ª": "a",
        "©": "(c)", "®": "(r)", "™": "(tm)"
    }
    for old, new in replacements.items():
        texto = texto.replace(old, new)
    
    # Forzar a cp1252 (que es lo que suele usar FPDF para fuentes estándar)
    # eliminando cualquier carácter que no sea compatible para evitar el crash.
    try:
        return texto.encode('cp1252', errors='replace').decode('cp1252').replace('?', '')
    except:
        # Fallback total: solo caracteres ASCII básicos si falla lo anterior
        return "".join(c for c in texto if ord(c) < 128)

def formatear_cuerpo_teletipo(texto):
    if not texto: return ""
    
    texto = html.unescape(texto)
    texto = re.sub(r'<[^>]+>', '', texto)
    
    # Eliminar textos promocionales de gráficos e inserciones multimedia y todo lo que le sigue
    texto = re.sub(r'(?i)GRÁFICO:\s*Enlace\s+a\s+gráfico\s+disponible\s+al\s+final\s+del\s+texto\.?', '', texto)
    texto = re.sub(r'(?is)(?:\s*-{3,})?\s*Contenido\s+multimedia:.*$', '', texto)
    texto = re.sub(r'(?is)\beyp\s*/\s*apc\b.*$', '', texto)
    texto = re.sub(r'(?is)\b[a-z]{2,4}\s*/\s*[a-z]{2,4}\b.*$', '', texto)
    
    # Separar subtítulo de la cabecera si vienen juntos en la primera línea con espacios
    patron_separador = r'(\S.*?)\s{3,}([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+,?\s*\d+(?:\s*(?:de\s*)?[A-Za-zÁÉÍÓÚÑáéíóúñ]+\.?)?\s*\([^)]+\))'
    texto = re.sub(patron_separador, r'\1\n\2', texto)

    # 1. Formato de Cabecera (Dateline): Procesar primero para evitar que sea detectada como ladillo
    def estandarizar_cabecera(match):
        ciudad = match.group(1).replace(',', '').strip().upper()
        fecha_raw = match.group(2)
        resto = match.group(3).strip()
        
        # Extraer limpiamente el nombre de la agencia para homogeneizar (EFE).- y (EUROPA PRESS) -
        m_agencia = re.search(r'\(([^)]+)\)', resto)
        if m_agencia:
            agencia = m_agencia.group(1)
            resto = f"({agencia}) -"
        else:
            if not re.search(r'[-–—]$', resto):
                resto += " -"
            
        m_fecha = re.search(r'(\d+)(?:\s*(?:de\s*)?([A-Za-zÁÉÍÓÚÑáéíóúñ]+))?', fecha_raw)
        if m_fecha and m_fecha.group(2):
            dia = m_fecha.group(1)
            mes = m_fecha.group(2).lower()
            mapa_meses = {'enero': 'Ene', 'febrero': 'Feb', 'marzo': 'Mar', 'abril': 'Abr', 'mayo': 'May', 'junio': 'Jun', 'julio': 'Jul', 'agosto': 'Ago', 'septiembre': 'Sep', 'octubre': 'Oct', 'noviembre': 'Nov', 'diciembre': 'Dic'}
            mes_abrev = mapa_meses.get(mes, mes.capitalize()[:3])
            fecha_str = f"{dia} {mes_abrev}."
        elif m_fecha:
            dia = m_fecha.group(1)
            meses_arr = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            mes_actual = meses_arr[datetime.now().month - 1]
            fecha_str = f"{dia} {mes_actual}."
        else:
            fecha_str = fecha_raw.strip()
            
        return f"@@DATELINE@@{ciudad} {fecha_str} {resto}@@ENDDATELINE@@"

    texto = re.sub(r'(?m)^\s*([A-ZÁÉÍÓÚÑa-záéíóúñ \t]+,?\s*)(\d+(?:\s*(?:de\s*)?[A-Za-zÁÉÍÓÚÑáéíóúñ]+\.?)?\s*)(\([^)]+\)\s*\.?\s*[-–—]*)\s*\n*\s*', estandarizar_cabecera, texto)
    
    # Todo lo que esté antes de la cabecera (Dateline) se considera título/subtítulo, así que lo marcamos como ladillo para que salga en negrita
    if "@@DATELINE@@" in texto:
        partes = texto.split("@@DATELINE@@", 1)
        lineas_pre = partes[0].splitlines()
        for i in range(len(lineas_pre)):
            if lineas_pre[i].strip():
                lineas_pre[i] = f"@@LADILLO@@{lineas_pre[i].strip()}@@ENDLADILLO@@"
        partes[0] = "\n".join(lineas_pre) + ("\n" if lineas_pre else "")
        texto = "@@DATELINE@@".join(partes)
    
    # Detectar posibles ladillos sin etiqueta si son líneas cortas todo en mayúsculas
    lineas = texto.splitlines()
    for i in range(len(lineas)):
        l = lineas[i].strip()
        if "@@DATELINE@@" in l or "@@LADILLO@@" in l:
            continue
        if len(l) > 2 and len(l) < 100 and l.isupper():
            lineas[i] = f"@@LADILLO@@{l}@@ENDLADILLO@@"
    texto = "\n".join(lineas)
    
    for char in ["*", "_", "`", "[", "]", "~", ">", "#", "|", "{", "}", "\\"]:
        texto = texto.replace(char, "")
    
    # Reemplazar dobles guiones que causan subrayados en el motor Markdown de FPDF
    texto = texto.replace("--", "-")
    
    texto = "".join(c for c in texto if ord(c) >= 32 or c in "\n\r\t")
    # Colapsar todos los saltos de línea múltiples en uno solo para que sea compacto
    texto = re.sub(r'\n{2,}', '\n', texto).strip()

    # Quitar los tokens temporales de DATELINE
    texto = texto.replace("@@DATELINE@@", "").replace("@@ENDDATELINE@@", "")

    # 2. Formato de Ladillos: negrita y un solo salto de línea (sin espacio extra) con el siguiente párrafo
    texto = re.sub(r'@@LADILLO@@(.*?)@@ENDLADILLO@@\s*\n*', r'**\1**\n', texto)

    patrones = [
        (r'\bInstituto Nacional de Estad[íi]stica \(INE\)\b', 'Instituto Nacional de Estadística (INE)'),
        (r'\bInstituto Nacional de Estad[íi]stica\b', 'Instituto Nacional de Estadística'),
        (r'\bINE\b', 'INE')
    ]
    
    for i, (regex, _) in enumerate(patrones):
        texto = re.sub(regex, f'@@MARK{i}@@', texto, flags=re.IGNORECASE)
    for i, (_, reemplazo) in enumerate(patrones):
        texto = texto.replace(f'@@MARK{i}@@', f'**{reemplazo}**')

    # Eliminar firmas finales típicas de agencias (ej: " EFE\nala/jlm" o solo "ala/jlm")
    # Busca " EFE" (opcional) seguido de iniciales "xxx/yyy" al final del texto.
    texto = re.sub(r'(?:\s+EFE|\s+EUROPA PRESS|\s+EP)?\s*\n*\s*[a-zA-Z]{2,4}/[a-zA-Z]{2,4}\s*$', '', texto)
    # Por si queda un " EFE" suelto justo al final después de un punto
    texto = re.sub(r'\.\s+(?:EFE|EUROPA PRESS|EP)\s*$', '.', texto)
            
    return texto

def obtener_titulo_formateado(n):
    titulo_original = re.sub(r'<[^>]+>', '', n.get('titulo', '')).strip()
    match_cat = re.match(r'^([^/-]+(?:/[^.-]+)?)\.?\s*[-–]\s*(.+)$', titulo_original)
    if match_cat:
        categoria_raw = match_cat.group(1).strip()
        # Tomar la última parte y capitalizarla (ej: "Vivienda" de "Economía/Vivienda" o "Economía" de "Economía")
        cat_base = categoria_raw.split('/')[-1].strip(".- ")
        categoria = cat_base.capitalize()
        titulo_sin_prefijo = match_cat.group(2).strip(".- ")
    else:
        ai_cat = n.get("ai_categoria", "") or ""
        mapeo_cats = {
            "PRECIOS": "Precios",
            "EMPLEO": "Empleo",
            "PIB": "Pib",
            "VIVIENDA": "Vivienda",
            "COMERCIO_EXTERIOR": "Comercio exterior",
            "TURISMO": "Turismo",
            "TRANSPORTE": "Transporte",
            "ENERGIA": "Energía",
            "DEPENDENCIA": "Dependencia",
            "CONSUMO": "Consumo",
            "OTROS": "Otros"
        }
        categoria = mapeo_cats.get(ai_cat.upper(), ai_cat.capitalize()).strip(".- ")
        titulo_sin_prefijo = titulo_original.strip(".- ")

    # Si hay una categoría válida, formatear como "Categoría.- Título", sino sólo Título
    if categoria:
        return f"{categoria}.- {titulo_sin_prefijo}"
    else:
        return titulo_sin_prefijo

def generar_pdf(noticias_finales, carpeta_destino, logger):
    if not noticias_finales:
        logger("❌ No hay noticias para añadir al PDF.")
        return

    logger("📑 Generando el archivo PDF con formato teletipo y negritas...")

    try:
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'esp')
        except locale.Error:
            pass

    mes_actual = datetime.now().strftime("%B").lower()
    fecha_hoy = f"{datetime.now().day} {mes_actual} de {datetime.now().year}"

    pdf = FPDF()
    pdf.MARKDOWN_LINK_UNDERLINE = False
    
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_left_margin(25)
    pdf.set_right_margin(25)

    # Nota: Si quisieras usar fuentes Unicode reales para no tener que limpiar símbolos como el €, 
    # tendrías que descomentar estas líneas y tener los archivos TTF en la carpeta del script:
    # pdf.add_font("DejaVu", "", "DejaVuSansCondensed.ttf")
    # pdf.add_font("DejaVu", "B", "DejaVuSansCondensed-Bold.ttf")
    # fuente_principal = "DejaVu"
    fuente_principal = "Times"

    # --- CABECERA ---
    pdf.set_font(fuente_principal, "B", 14)
    pdf.cell(w=0, h=6, text="RESUMEN DE TELETIPOS", new_x="LMARGIN", new_y="NEXT", align="C")
    
    pdf.set_font(fuente_principal, "B", 12)
    pdf.cell(w=0, h=6, text=fecha_hoy, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(12) 
    
    # --- BUCLE DE NOTICIAS ---
    for n in noticias_finales:
        # Parseo de fecha tolerante para mostrar solo HH:MM h
        hora_raw = n.get("hora", "")
        dt_hora = parse_date_safe(hora_raw)
        hora_texto = dt_hora.strftime("%H:%Mh") if dt_hora != datetime.min else "Hora N/E"
        
        titulo_formateado = obtener_titulo_formateado(n)
        titulo_limpio = limpiar_unicode(titulo_formateado)
        
        # --- Lógica 'Keep Together': Si no queda espacio para hora + título, saltar página ---
        if pdf.get_y() > 230:
            pdf.add_page()

        # 1. Hora
        pdf.set_font(fuente_principal, "B", 12)
        pdf.cell(w=0, h=6, text=hora_texto, new_x="LMARGIN", new_y="NEXT", align="L")
        
        # 2. Título (incluye categoría e.g. "Economía.- Título")
        pdf.set_font(fuente_principal, "B", 12)
        pdf.multi_cell(w=0, h=5, text=titulo_limpio, new_x="LMARGIN", new_y="NEXT", align="J")
        
        # 3. Cuerpo
        pdf.set_font(fuente_principal, "", 12)
        cuerpo_formateado = limpiar_unicode(formatear_cuerpo_teletipo(n['descripcion']))
        
        cuerpo_formateado = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cuerpo_formateado)
        cuerpo_formateado = re.sub(r'http[s]?://\S+', '', cuerpo_formateado)
        cuerpo_formateado = re.sub(r'<[^>]+>', '', cuerpo_formateado)

        pdf.multi_cell(w=0, h=5, text=cuerpo_formateado, new_x="LMARGIN", new_y="NEXT", align="L", markdown=True)
        pdf.ln(8)

    fecha_str = datetime.now().strftime("%Y%m%d")
    archivo_pdf = os.path.join(carpeta_destino, f"resumen_teletipos_{fecha_str}.pdf")
    pdf.output(archivo_pdf)
    logger(f"\n✅ PDF generado con éxito: {archivo_pdf}")

def escape_rtf(texto):
    if not texto: return ""
    # Escapar caracteres de control de RTF
    texto = texto.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
    # Mapa de caracteres ANSI para tildes y eñes (CP1252)
    mapa = {
        'á': r"\'e1", 'é': r"\'e9", 'í': r"\'ed", 'ó': r"\'f3", 'ú': r"\'fa",
        'Á': r"\'c1", 'É': r"\'c9", 'Í': r"\'cd", 'Ó': r"\'d3", 'Ú': r"\'da",
        'ñ': r"\'f1", 'Ñ': r"\'d1", '¿': r"\'bf", '¡': r"\'a1", '€': "EUR"
    }
    for original, escape in mapa.items():
        texto = texto.replace(original, escape)
    # Convertir saltos de línea a formato RTF
    texto = texto.replace("\n", "\\par ")
    return texto

def generar_rtf(noticias_finales, carpeta_destino, logger):
    try:
        ahora = datetime.now()
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha_txt = f"{ahora.day} de {meses[ahora.month-1]} de {ahora.year}"

        # Cabecera RTF (ANSI, Fuente Times New Roman)
        rtf = r"{\rtf1\ansi\deff0 {\fonttbl{\f0 Times New Roman;}}\f0\fs24 "
        rtf += r"\qc\b\fs28 RESUMEN DE TELETIPOS\b0\par "
        rtf += f"\\qc\\b {escape_rtf(fecha_txt)}\\b0\\par\\par\\pard "

        for n in noticias_finales:
            # 1. Hora y Titulo en Negrita
            hora_raw = n.get("hora", "")
            dt_hora = parse_date_safe(hora_raw)
            hora_limpia = dt_hora.strftime("%H:%M h") if dt_hora != datetime.min else "Hora N/E"
            hora = escape_rtf(hora_limpia)
            
            titulo_formateado = obtener_titulo_formateado(n)
            titulo = escape_rtf(titulo_formateado)
            
            rtf += f"\\b {hora}\\b0\\par "
            rtf += f"\\b {titulo}\\b0\\par "

            # 2. Cuerpo con procesamiento de negritas (**)
            cuerpo = formatear_cuerpo_teletipo(n.get("descripcion", ""))
            cuerpo = escape_rtf(cuerpo)
            
            # Convertir **texto** en \b texto \b0
            partes = cuerpo.split("**")
            cuerpo_rtf = ""
            for i, parte in enumerate(partes):
                if i % 2 == 1: # Parte impar = entre asteriscos
                    cuerpo_rtf += f"\\b {parte}\\b0 "
                else:
                    cuerpo_rtf += parte
            
            rtf += f"{cuerpo_rtf}\\par\\par "

        rtf += "}"
        
        fecha_str = datetime.now().strftime("%Y%m%d")
        archivo_rtf = os.path.join(carpeta_destino, f"resumen_teletipos_{fecha_str}.rtf")
        with open(archivo_rtf, "w", encoding="ascii", errors="ignore") as f:
            f.write(rtf)
        
        logger(f"✅ RTF generado con éxito: {archivo_rtf}")
    except Exception as e:
        logger(f"❌ Error generando RTF: {e}")

# =========================================================
# --- UTILIDADES DE FECHA Y ORDENACIÓN
# =========================================================
def parse_date_safe(date_str):
    if not date_str:
        return datetime.min
    try:
        # Extraer solo la hora y minuto sin importar el día
        match_hora = re.search(r'(\d{1,2}):(\d{2})', date_str)
        if match_hora:
            hh, mm = map(int, match_hora.groups())
            # Usamos una fecha fija (año 2000) para que el orden sea ÚNICAMENTE por hora
            return datetime(2000, 1, 1, hh, mm)
        
        # Si es formato ISO pero queremos ignorar el día, también extraemos HH:MM
        d_str = date_str.replace('Z', '+00:00').replace('GMT', '').strip()
        if 'T' in d_str:
            dt = datetime.fromisoformat(d_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            return datetime(2000, 1, 1, dt.hour, dt.minute)
    except: pass
    return datetime.min

# =========================================================
# --- FTP SYNC & CLEANUP
# =========================================================
def limpiar_carpeta_local(carpeta, logger):
    logger(f"🗑️ Limpiando archivos XML antiguos en {carpeta}...")
    # Buscamos archivos .xml tanto en la carpeta principal como en subcarpetas si las hay
    archivos_raw = glob.glob(os.path.join(carpeta, "*.xml")) + glob.glob(os.path.join(carpeta, "*.XML"))
    archivos = list(set(os.path.abspath(f) for f in archivos_raw))
    for f in archivos:
        try:
            os.remove(f)
        except: pass
    logger(f"🧹 Carpeta limpia ({len(archivos)} archivos eliminados).")

def descargar_desde_ftp(host, user, password, carpeta_remota, carpeta_local, logger):
    logger(f"🌐 Conectando a FTP: {host}...")
    try:
        ftp = FTP(host)
        ftp.login(user=user, passwd=password)
        
        if carpeta_remota != "/":
            ftp.cwd(carpeta_remota)
        
        # Obtener lista de archivos
        archivos_remotos = [f for f in ftp.nlst() if f.lower().endswith('.xml')]
        
        # Filtro de fecha (Hoy)
        hoy = datetime.now()
        hoy_str = hoy.strftime("%Y%m%d")
        if "epress.coonic.com" in host:
            archivos_remotos = [f for f in archivos_remotos if f.startswith(hoy_str)]
            logger(f"📅 [{host}] Filtrando Europa Press por fecha hoy ({hoy_str}): {len(archivos_remotos)} archivos restantes.")
        elif "efe.coonic.com" in host:
            # Nuevo formato EFE: BAS-X-NACIONAL_AAAAMMDD_HHMM.XML
            archivos_remotos = [f for f in archivos_remotos if f"_{hoy_str}_" in f.upper()]
            logger(f"📅 [{host}] Filtrando EFE por fecha hoy ({hoy_str}): {len(archivos_remotos)} archivos restantes.")
        else:
            logger(f"📂 [{host}] Encontrados {len(archivos_remotos)} archivos XML.")
        
        descargados = 0
        for archivo in archivos_remotos:
            ruta_local = os.path.join(carpeta_local, archivo)
            with open(ruta_local, 'wb') as f:
                ftp.retrbinary(f'RETR {archivo}', f.write)
            descargados += 1
        
        ftp.quit()
        logger(f"✅ [{host}] Sincronización completada ({descargados} archivos).")
        return True
    except Exception as e:
        logger(f"❌ Error FTP [{host}]: {e}")
        return False

DEFAULT_PROMPT_SYSTEM = """Eres un filtro estricto de noticias para el INE (Instituto Nacional de Estadística) de España.
Tu única misión es identificar noticias con DATOS ESTADÍSTICOS MACROECONÓMICOS REALES que reflejen la evolución de la economía española.

SELECCIONAR (seleccionada: true) si la noticia contiene estadísticas sobre:
- PRECIOS: IPC, inflación, precio vivienda alquiler/compraventa, precio coches segunda mano, precio energía, precio alimentos.
- EMPLEO AGREGADO y ESPECÍFICO: paro nacional, EPA, afiliación Seguridad Social, bajas laborales por sector, absentismo, salarios medios. EREs y ERTEs tanto de empresas concretas como estadísticas nacionales.
- PIB: crecimiento económico, contabilidad nacional.
- DEUDA y DÉFICIT público.
- HIPOTECAS y COMPRAVENTA de vivienda (registradores, notarios, portales).
- COMERCIO EXTERIOR: exportaciones e importaciones de España.
- TURISMO: estadísticas de viajeros, pernoctaciones, gasto turístico en España.
- TRANSPORTE: estadísticas sectoriales de tráfico aéreo, ferroviario, marítimo a nivel nacional (Enaire, AENA, Renfe, Puertos del Estado).
- ENERGÍA: estadísticas de consumo/producción energética nacional (Red Eléctrica, Enagás, CORES).
- DEPENDENCIA y SERVICIOS SOCIALES: estadísticas de personas mayores, dependencia, pensiones.
- CONSUMO de los hogares españoles.

DESCARTAR siempre (seleccionada: false):
- Bolsa, IBEX 35, mercados financieros, cotizaciones bursátiles.
- Startups, venture capital, inversión privada en tecnología.
- Resultados financieros, fusiones, adquisiciones de empresas privadas.
- Informes autopromocionales de consultoras privadas (PwC, Deloitte, South Summit, etc.).
- Noticias corporativas o autopromocionales de empresas privadas de transporte, turismo, energía, etc. (como aerolíneas del tipo Vueling, Iberia, Ryanair o cadenas hoteleras) que hablen sobre sus propios aumentos de plazas, asientos, nuevas rutas, vuelos o planes de negocio propios. Solo interesan estadísticas macroeconómicas del sector general.
- Aprobación de leyes, decretos, reales decretos, reformas legislativas o acuerdos del Consejo de Ministros (ej: "El Gobierno aprueba...").
- Política, elecciones, partidos, declaraciones políticas sin datos económicos.
- Deportes, cultura, ocio, sucesos, tribunales.
- Declaraciones de cargos públicos en ruedas de prensa, desayunos informativos o foros sin datos estadísticos verificables detrás (ej: "el ministro asegura que...", "el secretario de estado afirma que...").
- Nombramientos de directivos, premios empresariales.

CLAVE PARA ENTIDADES: Enaire, AENA, Renfe, Red Eléctrica, Enagás, CORES, Puertos del Estado, Turespaña son organismos públicos que publican ESTADÍSTICAS SECTORIALES → SELECCIONAR.
Vueling, Iberia, Ryanair, Nissan, Meliá, South Summit, PwC, Ancove, Idealista, etc. son entidades privadas → solo SELECCIONAR si sus datos reflejan tendencias del mercado general (ej: precio medio coches segunda mano), no si hablan de sí mismas.

Categorías posibles: PRECIOS, EMPLEO, PIB, VIVIENDA, COMERCIO_EXTERIOR, TURISMO, TRANSPORTE, ENERGIA, DEPENDENCIA, CONSUMO, OTROS.

Responde ÚNICAMENTE con un JSON puro (sin texto adicional):
{
  "0": {"seleccionada": true, "razon": "Estadística tráfico aéreo nacional +3,5%", "categoria": "TRANSPORTE"},
  "1": {"seleccionada": false, "razon": "ERE de empresa privada concreta", "categoria": "OTROS"}
}"""

# =========================================================
# --- MOTOR EXTRACTOR
# =========================================================
def motor_extractor(carpeta_xml, provider, api_key, logger, on_finish, progress_cb, on_selection_ready, limite_caracteres=1000, prompt_system=None):
    try:
        start_time = time.time()
        progress_cb(0.1, "🔍 Fase 1: Escaneando archivos...")
        archivos_raw = glob.glob(os.path.join(carpeta_xml, "*.xml")) + glob.glob(os.path.join(carpeta_xml, "*.XML"))
        # En Windows glob puede ser case-insensitive, así que eliminamos duplicados de rutas
        archivos = list(set(os.path.abspath(f) for f in archivos_raw))
        
        if not archivos:
            logger("❌ No se encontraron archivos XML en la carpeta seleccionada.")
            return

        logger(f"🔍 Fase 1: Leyendo {len(archivos)} archivos XML...")
        noticias_candidatas = []
        for arch in archivos:
            try:
                root = ET.parse(arch).getroot()
                # Buscamos de forma agnóstica para soportar EFE (NewsML) y Europa Press (NOTICIA)
                for item in root.iter():
                    if not isinstance(item.tag, str):
                        continue
                    tag_limpio = item.tag.split('}')[-1].lower()
                    
                    # Detectamos el inicio de una noticia (EFE o Europa Press)
                    if tag_limpio in ["newsitem", "noticia"]:
                        titulo = ""
                        desc = ""
                        fecha_str = ""
                        hora_str = ""
                        
                        # Buscamos campos dentro del bloque de la noticia
                        for sub in item.iter():
                            if not isinstance(sub.tag, str):
                                continue
                            sub_tag = sub.tag.split('}')[-1].lower()
                            
                            # Título (HeadLine en EFE, Titular en EP)
                            if sub_tag in ["headline", "titular"] and not titulo:
                                titulo = "".join(sub.itertext()).strip()
                            # Contenido (DataContent en EFE, Contenido en EP)
                            elif sub_tag in ["datacontent", "contenido"] and not desc:
                                body_content = next((el for el in sub.iter() if isinstance(el.tag, str) and el.tag.split('}')[-1].lower() == "body.content"), None)
                                if body_content is not None:
                                    text_lines = []
                                    for p in body_content.iter():
                                        if isinstance(p.tag, str):
                                            tag_name = p.tag.split('}')[-1].lower()
                                            p_text = "".join(p.itertext()).strip()
                                            if not p_text: continue
                                            
                                            # Detectar ladillos de varias formas: etiqueta <ladillo>, <crosshead>, <subhead>, o <p class="ladillo">
                                            es_ladillo = False
                                            if tag_name in ["ladillo", "crosshead", "subhead"]:
                                                es_ladillo = True
                                            elif tag_name == "p":
                                                clase = p.get("class", "").lower()
                                                if "ladillo" in clase or "subhead" in clase:
                                                    es_ladillo = True
                                                    
                                            if es_ladillo:
                                                text_lines.append(f"@@LADILLO@@{p_text}@@ENDLADILLO@@")
                                            elif tag_name == "p":
                                                text_lines.append(p_text)
                                                
                                    desc = "\n".join(text_lines) if text_lines else "".join(body_content.itertext()).strip()
                                else:
                                    desc = "".join(sub.itertext()).strip()
                            # Fecha/Hora (FirstCreated en EFE, Fecha/Hora en EP)
                            elif sub_tag == "firstcreated":
                                fecha_str = sub.text.strip() if sub.text else ""
                            elif sub_tag == "fecha":
                                fecha_str = sub.text.strip() if sub.text else ""
                            elif sub_tag == "hora":
                                hora_str = sub.text.strip() if sub.text else ""
                        
                        if titulo:
                            if desc:
                                # Limpiar cada línea (quitar espacios iniciales) y quitar líneas vacías
                                lineas = [l.strip() for l in desc.splitlines() if l.strip()]
                                desc = "\n".join(lineas)
                            
                            # Recomponer la hora para la ordenación
                            hora_final = f"{fecha_str} {hora_str}".strip() if hora_str else fecha_str
                            
                            # Fallback de hora general si sigue vacío
                            if not hora_final:
                                for f_root in root.iter():
                                    if isinstance(f_root.tag, str) and f_root.tag.split('}')[-1].lower() == "dateandtime":
                                        hora_final = f_root.text.strip() if f_root.text else ""
                                        break

                            # --- FILTRO DE FECHA (HOY) ---
                            # EFE: YYYYMMDDTHHMMSS...
                            # EP: DD/MM/YYYY
                            hoy = datetime.now()
                            hoy_efe = hoy.strftime("%Y%m%d")
                            hoy_ep = hoy.strftime("%d/%m/%Y")
                            
                            pasa_fecha = False
                            if not hora_final:
                                pasa_fecha = True
                            elif hoy_efe in hora_final:
                                pasa_fecha = True
                            elif hoy_ep in hora_final:
                                pasa_fecha = True
                                
                            if not pasa_fecha:
                                continue
                            
                            # --- DEDUPLICACIÓN POR TÍTULO ---
                            ya_existe = False
                            
                            t_nueva_base = re.sub(r'\s*\([^)]*amp[^)]*\)\s*|\s*-\s*ampliación\s*|\s*\([^)]*avance[^)]*\)\s*', '', titulo.lower()).strip()
                            es_amp_nueva = "(amp" in titulo.lower() or "ampliación" in titulo.lower()
                            nueva_avisa_amp = "habrá ampliación" in desc.lower() or "habra ampliacion" in desc.lower()

                            for n_c in noticias_candidatas:
                                t_exist_base = re.sub(r'\s*\([^)]*amp[^)]*\)\s*|\s*-\s*ampliación\s*|\s*\([^)]*avance[^)]*\)\s*', '', n_c["titulo"].lower()).strip()
                                es_amp_exist = "(amp" in n_c["titulo"].lower() or "ampliación" in n_c["titulo"].lower()
                                exist_avisa_amp = "habrá ampliación" in n_c["descripcion"].lower() or "habra ampliacion" in n_c["descripcion"].lower()
                                
                                if t_nueva_base == t_exist_base and t_nueva_base != "":
                                    # Comparten el título base. Comprobamos si son versiones diferentes.
                                    if es_amp_nueva != es_amp_exist:
                                        continue # Una es ampliación explícita y la otra no. Conservamos ambas.
                                        
                                    if exist_avisa_amp and not nueva_avisa_amp:
                                        continue # La antigua era avance y la nueva no. Conservamos ambas.
                                        
                                    if nueva_avisa_amp and not exist_avisa_amp:
                                        continue # La nueva es avance y la antigua no. Conservamos ambas.
                                        
                                    # Si son exactamente el mismo tipo de versión, sí es un duplicado
                                    ya_existe = True
                                    break
                            
                            if not ya_existe:
                                noticias_candidatas.append({
                                    "titulo": titulo,
                                    "descripcion": desc or "Sin descripción",
                                    "hora": hora_final
                                })
            except Exception as e:
                logger(f"⚠️ Error procesando XML {arch}: {e}")
        # Fase 2: Filtrado por Título
        progress_cb(0.3, "⚡ Fase 2: Filtrando por Título...")

        logger("⚡ Fase 2: Aplicando filtros por palabras clave en el Título...")
        candidatas_fase2 = []
        descartadas_palabras = []
        pasa_directo_ine = []
        for cand in noticias_candidatas:
            t_min = cand["titulo"].lower()
            d_min = cand["descripcion"].lower()
            texto_completo = (cand["titulo"] + "\n" + cand["descripcion"]).lower()
            
            # --- CORTAFUEGOS: Boletines diarios y Agendas de eventos ---
            # 1. Detección por Título/Temática
            terminos_agenda = ["temas del día", "temas del dia", "agenda informativa", "agenda de previsiones", "agenda de previsión", "agenda de prevision", "previsiones del día", "previsiones del dia"]
            contiene_termino_agenda = any(term in t_min for term in terminos_agenda)
            
            # 2. Detección por Exceso de Horas ("Convocatorias")
            # Buscamos horas con formato como 09:00h, 10:30h, 09.00h, etc.
            horas_encontradas = re.findall(r'\b\d{1,2}[:.]\d{2}\s*[hH]\b', texto_completo)
            exceso_horas = len(horas_encontradas) > 3
            
            if contiene_termino_agenda or exceso_horas:
                razon_descarte = []
                if contiene_termino_agenda:
                    razon_descarte.append("Término de boletín/agenda en título")
                if exceso_horas:
                    razon_descarte.append(f"Exceso de horas con formato de agenda ({len(horas_encontradas)} horas)")
                
                cand["ai_selected"] = False
                cand["ai_razon"] = f"Cortafuegos: Descartado por agenda/previsiones ({', '.join(razon_descarte)})"
                cand["ai_categoria"] = "FILTRO"
                descartadas_palabras.append(cand)
                continue
            
            # Paso directo si contiene INE o Instituto Nacional de Estadística
            if re.search(r'\b(ine|instituto nac?ional de estad[ií]stica)\b', t_min) or \
               re.search(r'\b(ine|instituto nac?ional de estad[ií]stica)\b', d_min):
                cand["ai_selected"] = True
                cand["ai_razon"] = "Paso directo por contener INE / Instituto Nacional de Estadística"
                cand["ai_categoria"] = "OTROS"
                pasa_directo_ine.append(cand)
                continue
            
            # Filtro estricto (BCE, FED, etc. se descartan directamente)
            match_estricto = _RE_PROHIBIDAS_ESTRICTAS.search(t_min)
            if match_estricto:
                palabra_detectada = match_estricto.group(0)
                cand["ai_selected"] = False
                cand["ai_razon"] = f"Descartada estrictamente por palabra clave (Título): '{palabra_detectada}'"
                cand["ai_categoria"] = "FILTRO"
                descartadas_palabras.append(cand)
                continue

            # Comprobar salvoconducto: si tiene palabra clave especial, pasa aunque tenga prohibidas
            tiene_salvo = _RE_SALVO.search(t_min) or _RE_SALVO.search(d_min)
            match_p = _RE_PROHIBIDAS.search(t_min)
            if match_p and not tiene_salvo:
                palabra_detectada = match_p.group(0)
                cand["ai_selected"] = False
                cand["ai_razon"] = f"Descartada por palabra clave (Título): '{palabra_detectada}'"
                cand["ai_categoria"] = "FILTRO"
                descartadas_palabras.append(cand)
                continue
            candidatas_fase2.append(cand)
        logger(f"📊 [Estadísticas] Fase 2 (Filtro Título): {len(candidatas_fase2)} noticias pasan el filtro.")

        # Fase 3: Filtrado por Descripción
        progress_cb(0.5, "⚡ Fase 3: Filtrando por Descripción...")
        logger("⚡ Fase 3: Aplicando filtros por palabras clave en la Descripción...")
        candidatas_fase3 = []
        for cand in candidatas_fase2:
            d_min = cand["descripcion"].lower()
            t_min = cand["titulo"].lower()
            
            # Filtro estricto en el cuerpo
            match_estricto_cuerpo = _RE_PROHIBIDAS_ESTRICTAS.search(d_min)
            if match_estricto_cuerpo:
                palabra_detectada = match_estricto_cuerpo.group(0)
                cand["ai_selected"] = False
                cand["ai_razon"] = f"Descartada estrictamente por palabra clave (Cuerpo): '{palabra_detectada}'"
                cand["ai_categoria"] = "FILTRO"
                descartadas_palabras.append(cand)
                continue

            # Misma lógica: el salvoconducto anula el filtro
            tiene_salvo = _RE_SALVO.search(t_min) or _RE_SALVO.search(d_min)
            match_p = _RE_PROHIBIDAS.search(d_min)
            if match_p and not tiene_salvo:
                palabra_detectada = match_p.group(0)
                cand["ai_selected"] = False
                cand["ai_razon"] = f"Descartada por palabra clave (Cuerpo): '{palabra_detectada}'"
                cand["ai_categoria"] = "FILTRO"
                descartadas_palabras.append(cand)
                continue
            candidatas_fase3.append(cand)
        logger(f"📊 [Estadísticas] Fase 3 (Filtro Descripción): {len(candidatas_fase3)} noticias pasan el filtro.")

        # Fase 4: Filtrado por IA (en lotes, primeros 1000 caracteres)
        TAMANO_LOTE = 2
        MAX_WORKERS = 8
        
        progress_cb(0.8, "🧠 Fase 4: Filtrando con IA...")
        logger(f"🧠 Fase 4: Enviando {len(candidatas_fase3)} noticias a la IA en lotes de {TAMANO_LOTE} (con {MAX_WORKERS} hilos en paralelo)...")
        lista_final = []
        
        lotes = [candidatas_fase3[i:i+TAMANO_LOTE] for i in range(0, len(candidatas_fase3), TAMANO_LOTE)]
        from concurrent.futures import ThreadPoolExecutor
        
        def procesar_lote(lote, batch_idx):
            logger(f"   ↳ Analizando lote {batch_idx+1}/{len(lotes)} ({len(lote)} noticias)...")
            texto_evaluar = "{\n"
            for j, cand in enumerate(lote):
                texto_limpio = f"{cand['titulo']}\n{cand['descripcion']}"[:limite_caracteres].replace('"', "'").replace('\n', ' ')
                texto_evaluar += f'  "{j}": "{texto_limpio}",\n'
            texto_evaluar += "}"

            prompt_actual = prompt_system if prompt_system is not None else DEFAULT_PROMPT_SYSTEM
            instrucciones = f"{prompt_actual}\n\nNOTICIAS A EVALUAR:\n{texto_evaluar}"
            
            lote_final = []
            try:
                datos_ia = llamar_ia_con_reintentos(instrucciones, provider, api_key, logger)
                for j, cand in enumerate(lote):
                    idx_str = str(j)
                    item_ia = datos_ia.get(idx_str, {})
                    # Marcamos la decisión de la IA pero no descartamos aún
                    cand["ai_selected"] = item_ia.get("seleccionada", False)
                    cand["ai_razon"] = item_ia.get("razon", "Sin razón")
                    cand["ai_categoria"] = item_ia.get("categoria", "OTROS")
            except Exception as e:
                logger(f"   ⚠️ Fallo en lote IA {batch_idx+1}: {e}")
                # En caso de fallo, por defecto no seleccionada pero visible
                for cand in lote: 
                    cand["ai_selected"] = False
                    cand["ai_razon"] = "Error IA"
            return True

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futuros = [executor.submit(procesar_lote, lote, idx) for idx, lote in enumerate(lotes)]
            # Esperar a que todos los hilos procesen sus lotes
            for futuro in futuros:
                futuro.result()
                
        logger(f"📊 [Estadísticas] Fase 4 (Análisis IA): {len(candidatas_fase3)} noticias analizadas.")

        # Unimos las que pasaron a la IA, las de paso directo por INE y las que se descartaron por palabra clave
        todas_para_revisar = candidatas_fase3 + pasa_directo_ine + descartadas_palabras
        
        # ORDENACIÓN: Primero las recomendadas por la IA, luego el resto por hora
        todas_para_revisar.sort(key=lambda x: (not x.get("ai_selected", False), parse_date_safe(x.get("hora", ""))), reverse=False)
        
        progress_cb(0.95, "📄 Fase final: Abriendo panel de revisión...")
        
        # Pasamos TODAS las candidatas (incluyendo las descartadas por filtro)
        # para que el usuario pueda recuperarlas.
        on_selection_ready(todas_para_revisar)
        
    except Exception as e:
        logger(f"❌ Error fatal: {e}")
        on_finish() # Re-habilitar botón en caso de error

# =========================================================
# --- SELECTION WINDOW
# =========================================================
