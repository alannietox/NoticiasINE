"""Interfaz gráfica de NoticiasINE."""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from dotenv import load_dotenv

from core.engine import *

class VentanaSeleccionNoticias(ctk.CTkToplevel):
    def __init__(self, parent, noticias, callback_confirmar):
        super().__init__(parent)
        self.title("Revisión de Noticias Seleccionadas")
        # Abrir en una ventana grande pero no maximizada a la fuerza
        self.geometry("1280x800")
        self.transient(parent)
        self.grab_set()
        
        self.noticias = noticias
        self.callback_confirmar = callback_confirmar
        self.vars_seleccion = []

        # Vincular scroll global al entrar/salir de la ventana
        self.bind("<Enter>", lambda e: self.bind_global_scroll())
        self.bind("<Leave>", lambda e: self.unbind_global_scroll())

        # Si el usuario cierra con la 'X', se cierra todo el programa
        self.protocol("WM_DELETE_WINDOW", parent.destroy)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.configure(fg_color="#0F0F0F")

        # Header con info y controles
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, pady=(20, 10), padx=20, sticky="ew")
        self.header_frame.columnconfigure(0, weight=1)

        self.lbl_info = ctk.CTkLabel(self.header_frame, text="Revisión de Noticias", 
                                font=("Inter", 16, "bold"), text_color="#3A86FF")
        self.lbl_info.grid(row=0, column=0, sticky="w")

        # Buscador (Nuevo)
        self.entry_search = ctk.CTkEntry(self.header_frame, placeholder_text="Filtrar por título...", 
                                        width=200, height=28, font=("Inter", 11))
        self.entry_search.grid(row=0, column=1, padx=10, sticky="e")
        self.entry_search.bind("<KeyRelease>", lambda e: self.filtrar_noticias())

        self.btn_show_all = ctk.CTkButton(self.header_frame, text="Ver Descartadas", 
                                         fg_color="#333333", height=28, font=("Inter", 11),
                                         command=self.mostrar_descartadas)
        
        self.descartadas = [n for n in self.noticias if not n.get("ai_selected")]
        if self.descartadas:
            self.btn_show_all.grid(row=0, column=2, sticky="e")
            self.btn_show_all.configure(text=f"Rescatar ({len(self.descartadas)})", state="disabled") # Deshabilitar hasta que cargue

        # Scrollable Frame para las noticias
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="#050505", border_width=1, border_color="#222222")
        self.scroll_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.scroll_frame.columnconfigure(0, weight=1)
        self.scroll_frame.columnconfigure(1, weight=1)

        self.cards_widgets = []
        self.ver_descartadas = False
        self._spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self._spinner_idx = 0
        self._spinner_running = True

        # Overlay de carga que cubre el scroll_frame
        self.overlay = ctk.CTkFrame(self, fg_color="#050505", corner_radius=0)
        self.overlay.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.overlay.grid_columnconfigure(0, weight=1)
        self.overlay.grid_rowconfigure(0, weight=1)

        frame_centro = ctk.CTkFrame(self.overlay, fg_color="transparent")
        frame_centro.grid(row=0, column=0)

        self.lbl_spinner = ctk.CTkLabel(frame_centro, text="⠋", font=("Courier", 48, "bold"), text_color="#3A86FF")
        self.lbl_spinner.grid(row=0, column=0, pady=(0, 10))

        self.lbl_cargando = ctk.CTkLabel(frame_centro, text="Cargando noticias...", font=("Inter", 13), text_color="#FFFFFF")
        self.lbl_cargando.grid(row=1, column=0)

        # Animar el spinner
        self._animar_spinner()

        # Construir todo en segundo plano y mostrar de golpe
        self.after(100, self.cargar_noticias_inicial)

        # Footer con botones
        self.frame_buttons = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_buttons.grid(row=2, column=0, pady=20, padx=20, sticky="e")

        self.btn_cancel = ctk.CTkButton(self.frame_buttons, text="Cancelar", fg_color="#333333", command=self.destroy)
        self.btn_cancel.grid(row=0, column=0, padx=10)

        self.btn_ok = ctk.CTkButton(self.frame_buttons, text="Generar Boletín PDF/RTF", fg_color="#3A86FF", 
                                     hover_color="#2A76EF", command=self.confirmar)
        self.btn_ok.grid(row=0, column=1, padx=10)

    def filtrar_noticias(self, callback_final=None):
        busqueda = self.entry_search.get().lower()
        self._filtrar_por_lote(0, busqueda, callback_final)

    def _filtrar_por_lote(self, idx, busqueda, callback_final):
        TAMANO_LOTE = 20
        for i in range(TAMANO_LOTE):
            current = idx + i
            if current < len(self.cards_widgets):
                card, n = self.cards_widgets[current]
                es_recomendada = n.get("ai_selected", False)
                match_busqueda = busqueda in n['titulo'].lower()
                
                if self.ver_descartadas:
                    visible = match_busqueda
                else:
                    visible = es_recomendada and match_busqueda
                
                if visible:
                    card.grid()
                else:
                    card.grid_remove()
            else:
                if callback_final:
                    callback_final()
                return
        
        # Siguiente lote de filtrado para no bloquear el spinner
        self.after(5, lambda: self._filtrar_por_lote(idx + TAMANO_LOTE, busqueda, callback_final))

    def mostrar_descartadas(self):
        # Mostrar el overlay de carga de nuevo para dar feedback
        self.lbl_cargando.configure(text="Procesando lista completa...")
        self.overlay.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self._spinner_running = True
        self._animar_spinner()
        
        def proceso():
            self.ver_descartadas = not self.ver_descartadas
            texto = "Ocultar Descartadas" if self.ver_descartadas else f"Rescatar ({len(self.descartadas_lista)})"
            self.btn_show_all.configure(text=texto, fg_color="#238636" if self.ver_descartadas else "#333333")
            # Llamar al filtrado por lotes y ocultar overlay al final
            self.filtrar_noticias(callback_final=lambda: self.after(300, self._revelar_contenido))

        self.after(100, proceso)

    def _animar_spinner(self):
        if self._spinner_running:
            self.lbl_spinner.configure(text=self._spinner_chars[self._spinner_idx % len(self._spinner_chars)])
            self._spinner_idx += 1
            self.after(80, self._animar_spinner)

    def cargar_noticias_inicial(self):
        self.recomendadas = [n for n in self.noticias if n.get("ai_selected")]
        self.descartadas_lista = [n for n in self.noticias if not n.get("ai_selected")]

        # Cargar recomendadas en pequeños lotes para no congelar el spinner
        self._cargar_lote_recomendadas(0)

    def _cargar_lote_recomendadas(self, idx):
        TAMANO_LOTE = 5
        for i in range(TAMANO_LOTE):
            current = idx + i
            if current < len(self.recomendadas):
                self.crear_tarjeta(self.recomendadas[current], current)
            else:
                # Terminado recomendadas, empezar descartadas
                self.after(10, lambda: self._cargar_lote_descartadas(0))
                return
        
        # Siguiente lote de recomendadas
        self.after(5, lambda: self._cargar_lote_recomendadas(idx + TAMANO_LOTE))

    def _cargar_lote_descartadas(self, idx):
        TAMANO_LOTE = 10
        start_row = len(self.recomendadas)
        for i in range(TAMANO_LOTE):
            current = idx + i
            if current < len(self.descartadas_lista):
                self.crear_tarjeta(self.descartadas_lista[current], start_row + current)
            else:
                # Terminado todo
                self.after(50, self._revelar_contenido)
                return
        
        # Siguiente lote de descartadas
        self.after(5, lambda: self._cargar_lote_descartadas(idx + TAMANO_LOTE))

    def _cargar_lote_y_revelar(self, start_idx):
        # Este método ya no se usa, pero lo mantenemos por si acaso o lo borramos
        pass

    def _revelar_contenido(self):
        """Oculta el overlay y revela el scroll_frame."""
        self._spinner_running = False
        self.overlay.grid_remove()
        recomendadas_count = len(self.recomendadas)
        self.lbl_info.configure(text=f"Revisión: {recomendadas_count} recomendadas / {len(self.descartadas_lista)} descartadas")
        self.btn_show_all.configure(state="normal") # Ya se puede usar el botón
        self.bind_global_scroll()


    def crear_tarjeta(self, n, i):
        var = tk.BooleanVar(value=n.get("ai_selected", False))
        self.vars_seleccion.append(var)
        
        es_ia_ok = n.get("ai_selected", False)
        
        # Tarjeta completa (Restaurada según petición)
        card_bg = "#161B22" if es_ia_ok else "#0D1117"
        border_color = "#238636" if es_ia_ok else "#30363D"
        text_color = "#E6EDF3" if es_ia_ok else "#8B949E"
        
        card = ctk.CTkFrame(self.scroll_frame, fg_color=card_bg, border_color=border_color, border_width=1, corner_radius=8)
        
        # Nueva disposición en dos columnas para evitar el límite de 32k píxeles de Tkinter
        row_idx = i // 2
        col_idx = i % 2
        
        # Si no es recomendada y no estamos viendo descartadas, ocultar de inicio
        if es_ia_ok or self.ver_descartadas:
            card.grid(row=row_idx, column=col_idx, sticky="ew", padx=10, pady=6)
        else:
            card.grid(row=row_idx, column=col_idx, sticky="ew", padx=10, pady=6)
            card.grid_remove()
            
        card.grid_columnconfigure(1, weight=1)

        cb = ctk.CTkCheckBox(card, text="", variable=var, width=24, checkbox_width=20, checkbox_height=20, 
                             border_color="#238636" if es_ia_ok else "#555555", fg_color="#238636", hover_color="#2EA043")
        cb.grid(row=0, column=0, rowspan=2, padx=(15, 10), pady=15, sticky="nw")
        
        hora = n.get("hora", "")
        dt_hora = parse_date_safe(hora)
        hora_txt = dt_hora.strftime("%H:%M") if dt_hora != datetime.min else "--:--"
        
        title_text = f"[{hora_txt}] {n['titulo']}"
        lbl_title = ctk.CTkLabel(card, text=title_text, font=("Inter", 11, "bold" if es_ia_ok else "normal"), 
                                 text_color=text_color, wraplength=340, justify="left")
        lbl_title.grid(row=0, column=1, padx=(5, 10), pady=(10, 0), sticky="w")
        
        frame_tags = ctk.CTkFrame(card, fg_color="transparent")
        frame_tags.grid(row=1, column=1, padx=(5, 15), pady=(6, 12), sticky="w")
        
        ai_badge_color = "#1F4A2C" if es_ia_ok else "#21262D"
        ai_badge_text = "IA: RECOMENDADA" if es_ia_ok else "IA: DESCARTADA"
        ai_badge_text_color = "#3FB950" if es_ia_ok else "#8B949E"
        
        lbl_badge = ctk.CTkLabel(frame_tags, text=ai_badge_text, font=("Inter", 10, "bold"), 
                                 fg_color=ai_badge_color, text_color=ai_badge_text_color, corner_radius=4, padx=8, pady=2)
        lbl_badge.grid(row=0, column=0, sticky="w", padx=(0, 10))

        reason = n.get("ai_razon", "")
        if reason:
            lbl_reason = ctk.CTkLabel(frame_tags, text=f"• {reason}", font=("Inter", 10), text_color="#7A8490", wraplength=280, justify="left")
            lbl_reason.grid(row=0, column=1, sticky="w")
            
        self.cards_widgets.append((card, n))

    def _on_mousewheel(self, event):
        # En Linux Button-4 es scroll up (4) y Button-5 es scroll down (5)
        # Usamos self.scroll_frame._parent_canvas que es el canvas interno de CTK
        canvas = self.scroll_frame._parent_canvas
        if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
            canvas.yview_scroll(-3, "units")
        elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            canvas.yview_scroll(3, "units")
        return "break"

    def bind_global_scroll(self):
        # Vincular el ratón a toda la ventana de nivel superior para que funcione siempre
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    def unbind_global_scroll(self, event=None):
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")
        self.unbind_all("<MouseWheel>")

    def confirmar(self):
        # Mapear los BooleanVars a sus noticias correspondientes
        # Como ahora las tarjetas se crean bajo demanda, necesitamos asegurar el mapeo correcto
        seleccionadas = []
        # En la VentanaSeleccionNoticias, las tarjetas se crean y añaden vars_seleccion en el orden en que se crean.
        # Para evitar líos con el orden, guardaremos la referencia en la propia tarjeta o usaremos un diccionario.
        # Pero para simplificar, si el usuario solo usa las recomendadas, funciona.
        # Vamos a mejorar el mapeo:
        for i, var in enumerate(self.vars_seleccion):
            if var.get():
                # Buscamos la noticia que corresponde a este var. 
                # Como self.vars_seleccion se llena en el orden de creación de tarjetas:
                # 1. Recomendadas
                # 2. Descartadas (si se pulsa el botón)
                if i < len(self.recomendadas):
                    seleccionadas.append(self.recomendadas[i])
                else:
                    seleccionadas.append(self.descartadas_lista[i - len(self.recomendadas)])
        
        self.callback_confirmar(seleccionadas)
        self.destroy()

class VentanaOpcionesAvanzadas(ctk.CTkToplevel):
    def __init__(self, parent, api_key_actual, prompt_actual, callback_guardar):
        super().__init__(parent)
        self.title("Configuración Avanzada")
        self.geometry("800x650")
        self.transient(parent)
        self.grab_set()
        
        self.callback_guardar = callback_guardar
        self.configure(fg_color="#0F0F0F")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        
        # 1. API Key
        lbl_api = ctk.CTkLabel(self, text="Clave API (OpenRouter):", font=("Inter", 11, "bold"), text_color="#3A86FF")
        lbl_api.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        
        self.entry_api = ctk.CTkEntry(self, width=760, height=35, fg_color="#050505", border_color="#222222")
        self.entry_api.insert(0, api_key_actual)
        self.entry_api.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
        
        # 2. Prompt Editable
        frame_prompt_header = ctk.CTkFrame(self, fg_color="transparent")
        frame_prompt_header.grid(row=2, column=0, padx=20, pady=(5, 5), sticky="ew")
        frame_prompt_header.grid_columnconfigure(0, weight=1)
        
        lbl_prompt = ctk.CTkLabel(frame_prompt_header, text="Prompt del Sistema (Filtro IA):", font=("Inter", 11, "bold"), text_color="#3A86FF")
        lbl_prompt.grid(row=0, column=0, sticky="w")
        
        btn_restablecer = ctk.CTkButton(
            frame_prompt_header, 
            text="Restablecer original", 
            font=("Inter", 10, "bold"), 
            height=26, 
            width=130,
            fg_color="#D90429", 
            hover_color="#EF233C", 
            command=self.restablecer_prompt
        )
        btn_restablecer.grid(row=0, column=1, sticky="e")
        
        self.txt_prompt = ctk.CTkTextbox(self, font=("JetBrains Mono", 11), fg_color="#050505", border_color="#222222", border_width=1)
        self.txt_prompt.insert("1.0", prompt_actual)
        self.txt_prompt.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
        # 3. Botones Guardar / Cancelar
        frame_buttons = ctk.CTkFrame(self, fg_color="transparent")
        frame_buttons.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="e")
        
        btn_cancelar = ctk.CTkButton(frame_buttons, text="Cancelar", fg_color="#333333", command=self.destroy)
        btn_cancelar.grid(row=0, column=0, padx=10)
        
        btn_guardar = ctk.CTkButton(frame_buttons, text="Guardar Cambios", fg_color="#3A86FF", hover_color="#2A76EF", command=self.guardar)
        btn_guardar.grid(row=0, column=1, padx=10)
        
    def restablecer_prompt(self):
        confirmar = messagebox.askyesno(
            "Restablecer Prompt", 
            "¿Está seguro de que desea restablecer el prompt al valor original de fábrica?\n\n(Perderá cualquier modificación no guardada)"
        )
        if confirmar:
            self.txt_prompt.delete("1.0", "end")
            self.txt_prompt.insert("1.0", DEFAULT_PROMPT_SYSTEM)

    def guardar(self):
        confirmar = messagebox.askyesno("Confirmar Cambios", "¿Está seguro de que desea guardar los cambios en el prompt del sistema y la configuración?")
        if confirmar:
            new_api = self.entry_api.get().strip()
            new_prompt = self.txt_prompt.get("1.0", "end-1c").strip()
            self.callback_guardar(new_api, new_prompt)
            self.destroy()

# =========================================================
# --- GUI
# =========================================================
class AppExtractorNoticias(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("News Extract AI - Pro Dashboard")
        
        # Iniciar en ventana grande (no maximizada forzosamente)
        self.geometry("1280x800")
        self.minsize(900, 650)
        ctk.set_appearance_mode("dark")
        
        # Grid Principal: 2 Columnas (Panel de Control | Terminal Pro)
        self.grid_columnconfigure(0, weight=0, minsize=420) 
        self.grid_columnconfigure(1, weight=1)             
        self.grid_rowconfigure(0, weight=1)
        self.configure(fg_color="#0A0A0A")

        # --- PANEL IZQUIERDO (PASOS Y CONFIGURACIÓN) ---
        self.frame_left = ctk.CTkFrame(self, fg_color="#0F0F0F", corner_radius=0)
        self.frame_left.grid(row=0, column=0, sticky="nsew")
        self.frame_left.grid_columnconfigure(0, weight=1)

        # Header con logo/título
        self.lbl_logo = ctk.CTkLabel(self.frame_left, text="📡 NEWS EXTRACT AI", 
                                    font=("Inter", 26, "bold"), text_color="#FFFFFF")
        self.lbl_logo.grid(row=0, column=0, pady=(40, 30))

        # --- PASO 1: ORIGEN ---
        self.frame_step1 = self.crear_seccion(self.frame_left, "1. ORIGEN DE DATOS", "📂")
        self.frame_step1.grid(row=1, column=0, padx=25, pady=10, sticky="ew")
        
        self.str_carpeta = tk.StringVar(value=os.path.join(ROOT_DIR, "xml-ftp"))
        
        self.frame_path_row = ctk.CTkFrame(self.frame_step1, fg_color="transparent")
        self.frame_path_row.grid(row=1, column=0, padx=15, pady=(5, 15), sticky="ew")
        self.frame_path_row.grid_columnconfigure(0, weight=1)
        
        self.entry_folder = ctk.CTkEntry(self.frame_path_row, textvariable=self.str_carpeta, height=35, fg_color="#050505", border_color="#222222")
        self.entry_folder.grid(row=0, column=0, sticky="ew")
        self.btn_browse = ctk.CTkButton(self.frame_path_row, text="...", command=self.seleccionar_carpeta, width=45, height=35, fg_color="#333333")
        self.btn_browse.grid(row=0, column=1, padx=(10, 0))

        # --- PASO 2: INTELIGENCIA ---
        self.frame_step2 = self.crear_seccion(self.frame_left, "2. CEREBRO IA", "🧠")
        self.frame_step2.grid(row=2, column=0, padx=25, pady=10, sticky="ew")
        
        self.var_ia = tk.StringVar(value="(Online) Gemini 2.0 Flash")
        self.combo_ia = ctk.CTkOptionMenu(self.frame_step2, values=["(Online) Gemini 2.0 Flash", "(Online) Llama 3.1 8B"], 
                                         variable=self.var_ia, fg_color="#151515", button_color="#222222", height=35)
        self.combo_ia.grid(row=1, column=0, padx=15, pady=(5, 5), sticky="ew")

        # Variables internas de configuración avanzada (Cargar persistencia o por defecto)
        self.cargar_configuracion()

        # Botón de opciones avanzadas
        self.btn_advanced = ctk.CTkButton(self.frame_step2, text="OPCIONES AVANZADAS", height=35, fg_color="#151515", border_color="#222222", border_width=1, hover_color="#222222", command=self.abrir_opciones_avanzadas)
        self.btn_advanced.grid(row=2, column=0, padx=15, pady=(5, 10), sticky="ew")

        self.lbl_limit_title = ctk.CTkLabel(self.frame_step2, text="Límite caracteres noticia:", font=("Inter", 10, "bold"), text_color="#555555")
        self.lbl_limit_title.grid(row=3, column=0, padx=15, pady=(5, 0), sticky="w")

        self.entry_limit = ctk.CTkEntry(self.frame_step2, height=35, fg_color="#050505", border_color="#222222")
        self.entry_limit.insert(0, "1000")
        self.entry_limit.grid(row=4, column=0, padx=15, pady=(5, 15), sticky="ew")

        # --- PANEL DE ESTADO / RESULTADOS ---
        self.frame_results = self.crear_seccion(self.frame_left, "ESTADO Y RESULTADOS", "📊")
        self.frame_results.grid(row=3, column=0, padx=25, pady=10, sticky="ew")
        
        self.lbl_status = ctk.CTkLabel(self.frame_results, text="Sistema listo para comenzar", font=("Inter", 12), text_color="#888888")
        self.lbl_status.grid(row=1, column=0, padx=15, pady=(10, 15))
        
        self.progress = ctk.CTkProgressBar(self.frame_results, height=4, progress_color="#3A86FF", fg_color="#000000")
        self.progress.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.progress.set(0)

        # Botón de Acción (Footer)
        self.btn_run = ctk.CTkButton(self.frame_left, text="🚀 INICIAR EXTRACCIÓN", command=self.iniciar, 
                                     height=70, corner_radius=0, fg_color="#3A86FF", hover_color="#2A76EF", font=("Inter", 16, "bold"))
        self.btn_run.grid(row=4, column=0, sticky="ew", pady=(30, 0))

        # --- PANEL DERECHO (TERMINAL) ---
        self.frame_right = ctk.CTkFrame(self, fg_color="#050505", corner_radius=0)
        self.frame_right.grid(row=0, column=1, sticky="nsew")
        self.frame_right.grid_columnconfigure(0, weight=1)
        self.frame_right.grid_rowconfigure(0, weight=1)

        self.console = ctk.CTkTextbox(self.frame_right, font=("JetBrains Mono", 12), 
                                     fg_color="#050505", border_width=0, corner_radius=0)
        self.console.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.console.configure(state="disabled")

        self.grid_rowconfigure(0, weight=1)

    def crear_seccion(self, parent, titulo, icono):
        frame = ctk.CTkFrame(parent, fg_color="#181818", corner_radius=12, border_width=1, border_color="#222222")
        frame.grid_columnconfigure(0, weight=1)
        lbl = ctk.CTkLabel(frame, text=f"{icono} {titulo}", font=("Inter", 11, "bold"), text_color="#3A86FF")
        lbl.grid(row=0, column=0, padx=15, pady=(12, 8), sticky="w")
        return frame

    def cargar_configuracion(self):
        # Valores por defecto
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.prompt_system = DEFAULT_PROMPT_SYSTEM
        
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "api_key" in data:
                        self.api_key = data["api_key"]
                    if "prompt_system" in data:
                        self.prompt_system = data["prompt_system"]
            except Exception as e:
                print(f"Error al cargar configuración: {e}")

    def guardar_configuracion(self):
        try:
            data = {
                "api_key": self.api_key,
                "prompt_system": self.prompt_system
            }
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Ocultar el archivo en Windows para no molestar en la carpeta principal
            if os.name == 'nt':
                import ctypes
                # FILE_ATTRIBUTE_HIDDEN = 0x02
                ctypes.windll.kernel32.SetFileAttributesW(CONFIG_FILE_PATH, 0x02)
        except Exception as e:
            print(f"Error al guardar configuración: {e}")

    def abrir_opciones_avanzadas(self):
        VentanaOpcionesAvanzadas(self, self.api_key, self.prompt_system, self.guardar_opciones_avanzadas)

    def guardar_opciones_avanzadas(self, nueva_api, nuevo_prompt):
        self.api_key = nueva_api
        self.prompt_system = nuevo_prompt
        self.guardar_configuracion()
        self.log("Configuración avanzada guardada con éxito.")

    def seleccionar_carpeta(self):
        p = filedialog.askdirectory(initialdir=self.str_carpeta.get())
        if p: self.str_carpeta.set(p)

    def log(self, m):
        self.after(0, lambda: self._log(m))

    def _log(self, m):
        self.console.configure(state="normal")
        # Colores simples según el prefijo
        color = "#a6adc8" # Default
        if "❌" in m or "⚠️" in m: color = "#f38ba8"
        elif "✨" in m: color = "#a6e3a1"
        elif "🧠" in m or "📡" in m or "🦙" in m: color = "#cba6f7"
        elif "📊" in m: color = "#89b4fa"

        self.console.insert("end", m + "\n")
        # En CTK Textbox no es trivial aplicar tags línea a línea sin heredar, 
        # pero para logs simples la inserción estándar es suficiente.
        self.console.see("end")
        self.console.configure(state="disabled")

    def progress_update(self, val, msg):
        self.after(0, lambda: self._progress_update(val, msg))

    def _progress_update(self, val, msg):
        self.progress.set(val)
        self.lbl_status.configure(text=msg)

    def iniciar(self):
        self.btn_run.configure(state="disabled", text="PROCESANDO...", fg_color="#222222", text_color="#888888")
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        
        self.progress.set(0)
        self.lbl_status.configure(text="INICIANDO MOTOR...")

        provider = self.var_ia.get()
        # Esto lee el archivo .env oculto y carga las contraseñas en memoria
        load_dotenv()
        # Datos de los servidores FTP
        FTP_SOURCES = [
            {"host": os.getenv("FTP_EPRESS_HOST"), "user": os.getenv("FTP_EPRESS_USER"), "pass": os.getenv("FTP_EPRESS_PASS"), "path": "/"},
            {"host": os.getenv("FTP_EFE_HOST"), "user": os.getenv("FTP_EFE_USER"), "pass": os.getenv("FTP_EFE_PASS"), "path": "/efe.coonic.com"}
        ]

        def job():
            ruta_seleccionada = self.str_carpeta.get().rstrip("/\\")
            
            # DETERMINAR SI HACEMOS SYNC FTP O SOLO LECTURA
            # Si la ruta es la raíz del proyecto o la carpeta xml-ftp del proyecto, hacemos el ciclo completo
            if ruta_seleccionada == ROOT_DIR or ruta_seleccionada == os.path.join(ROOT_DIR, "xml-ftp"):
                carpeta_xml = os.path.join(ROOT_DIR, "xml-ftp")
                if not os.path.exists(carpeta_xml): os.makedirs(carpeta_xml)
                
                # 1. Limpieza y 2. Descarga (Solo en modo automático)
                limpiar_carpeta_local(carpeta_xml, self.log)
                for src in FTP_SOURCES:
                    descargar_desde_ftp(src["host"], src["user"], src["pass"], src["path"], carpeta_xml, self.log)
            else:
                # MODO MANUAL: Solo leer lo que haya en la carpeta seleccionada
                carpeta_xml = ruta_seleccionada
                self.log(f"📂 Modo manual: Extrayendo solo de {carpeta_xml} (Sin FTP ni limpieza)")

            # Obtener el límite de caracteres del entry con fallback a 1000 si está vacío o no es un número
            try:
                limite_caracteres_val = int(self.entry_limit.get().strip())
            except ValueError:
                limite_caracteres_val = 1000

            # 3. Motor Extractor común
            motor_extractor(
                carpeta_xml, 
                provider, 
                self.api_key, 
                self.log, 
                self.done,
                self.progress_update,
                self.abrir_ventana_seleccion,
                limite_caracteres=limite_caracteres_val,
                prompt_system=self.prompt_system
            )

        threading.Thread(target=job, daemon=True).start()

    def abrir_ventana_seleccion(self, noticias):
        # Ejecutar en el hilo principal
        self.after(0, lambda: self._abrir_ventana_seleccion(noticias))

    def _abrir_ventana_seleccion(self, noticias):
        if not noticias:
            self.log("⚠️ No se encontraron noticias que pasaran los filtros.")
            self.done()
            messagebox.showinfo("Sin resultados", "No hay noticias seleccionadas por la IA para revisar.")
            return
            
        # NUEVA LÓGICA: Solo abrir rescate si hay MENOS de 5 recomendadas
        recomendadas = [n for n in noticias if n.get("ai_selected")]
        if len(recomendadas) >= 5:
            self.log(f"✅ {len(recomendadas)} noticias recomendadas. Generando boletín directamente...")
            self.finalizar_con_seleccion(recomendadas)
        else:
            self.log(f"⚠️ Solo hay {len(recomendadas)} recomendadas. Abriendo ventana de rescate...")
            VentanaSeleccionNoticias(self, noticias, self.finalizar_con_seleccion)

    def finalizar_con_seleccion(self, noticias_finales):
        if not noticias_finales:
            self.log("❌ Generación cancelada: No se seleccionó ninguna noticia.")
            self.done()
            return

        # Ahora sí, generamos los archivos con lo que el usuario eligió
        self.log(f"📄 Generando boletín final con {len(noticias_finales)} noticias...")
        
        resultados_dir = os.path.join(ROOT_DIR, "resultados")
        if not os.path.exists(resultados_dir):
            os.makedirs(resultados_dir)
            
        try:
            generar_pdf(noticias_finales, resultados_dir, self.log)
            generar_rtf(noticias_finales, resultados_dir, self.log)
            
            # Notificar al usuario dónde están los archivos
            self.log(f"📂 Archivos guardados en: {resultados_dir}")
            if os.name == 'nt': # Windows
                os.startfile(resultados_dir)
            elif os.name == 'posix': # Linux
                import subprocess
                subprocess.Popen(['xdg-open', resultados_dir])
        except Exception as e:
            self.log(f"❌ Error al guardar archivos: {e}")
            messagebox.showerror("Error", f"No se pudo generar el boletín: {e}")
        
        self.progress_update(1.0, "✨ ¡Proceso completado!")
        self.log(f"✨ ¡Proceso completado con éxito! Se han incluido {len(noticias_finales)} noticias.")
        self.done()

    def done(self):
        self.after(0, lambda: self.btn_run.configure(state="normal", text="INICIAR EXTRACCIÓN", fg_color="#3A86FF", text_color="#FFFFFF"))

