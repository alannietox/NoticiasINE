# NoticiasINE

**Extractor y clasificador inteligente de noticias para el Instituto Nacional de Estadística (INE).**

NoticiasINE automatiza la recopilación, filtrado y selección de teletipos relevantes para el INE. El sistema combina reglas de filtrado con modelos de IA y genera un boletín final en **PDF y RTF**, preparado para su revisión y uso.

## Características

- Descarga de noticias desde fuentes FTP configuradas.
- Filtrado previo mediante reglas y palabras clave.
- Clasificación y selección mediante IA.
- Compatible con modelos disponibles a través de OpenRouter.
- Interfaz gráfica de escritorio desarrollada con CustomTkinter.
- Generación automática de boletines en PDF y RTF.
- Modo automático mediante FTP y modo manual mediante carpeta local.
- Reintentos ante errores de API y control de errores.
- Instaladores para Windows y Linux.
- Configuración local persistente sin necesidad de modificar el código.

## Flujo de trabajo

```text
Fuentes de noticias
       │
       ▼
Descarga FTP / carpeta local
       │
       ▼
Limpieza y normalización
       │
       ▼
Filtros deterministas
       │
       ▼
Clasificación mediante IA
       │
       ▼
Selección / revisión
       │
       ▼
Generación del boletín
    ┌──┴──┐
    ▼     ▼
   PDF   RTF
```

## Requisitos

- Python 3.12+
- Windows o Linux
- Una API key de OpenRouter para el análisis mediante IA
- Acceso a las fuentes FTP si se utiliza el modo automático

## Instalación

### Windows

Ejecuta:

```text
win_instalador.bat
```

El instalador crea un entorno virtual e instala las dependencias desde `requirements.txt`.

Después, inicia la aplicación con:

```text
iniciar.bat
```

### Linux

Ejecuta:

```bash
chmod +x linux_instalador.sh
./linux_instalador.sh
```

Después:

```bash
./iniciar.sh
```

### Instalación manual

```bash
python -m venv venv
```

Windows:

```bat
venv\Scripts\activate
```

Linux:

```bash
source venv/bin/activate
```

Instala las dependencias:

```bash
python -m pip install -r requirements.txt
```

## Configuración

Crea un archivo `.env` a partir de `.env.example`:

```env
OPENROUTER_API_KEY=tu_clave
```

Las credenciales FTP se configuran también mediante variables de entorno.

**No guardes claves API, contraseñas FTP ni archivos de configuración local en Git.**

## Estructura

```text
NoticiasINE/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── NewsExtractAI.spec
├── win_instalador.bat
├── linux_instalador.sh
├── iniciar.bat
├── CONTRIBUTING.md
└── .github/
    └── workflows/
        └── ci.yml
```

## Calidad y CI

El repositorio incluye GitHub Actions para comprobar automáticamente la sintaxis de Python en cada push y pull request.

También puedes ejecutar la comprobación localmente:

```bash
python -m compileall -q app.py
```

## Rendimiento

En el entorno para el que fue desarrollado, el flujo automatizado redujo un proceso manual de aproximadamente **3 horas a unos 30 segundos**, según las mediciones del proyecto. El resultado depende del volumen de noticias y de los servicios externos utilizados.

## Seguridad

- Las claves se obtienen mediante variables de entorno o configuración local.
- Los archivos de configuración local están excluidos de Git.
- Las credenciales FTP no deben introducirse directamente en el código.
- Las llamadas a servicios de IA incluyen control de errores y reintentos.

## Licencia

Actualmente no se ha definido una licencia de código abierto para el proyecto. Si quieres permitir reutilización por terceros, añade una licencia explícita.
