#!/bin/bash
set -e

echo "======================================================="
echo "  Instalador - NoticiasINE"
echo "======================================================="

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python 3 no esta instalado."
    echo "Instalalo con el gestor de paquetes de tu distribucion."
    exit 1
fi

echo "[OK] Python encontrado: $(python3 --version)"

if ! command -v apt-get >/dev/null 2>&1; then
    echo "[INFO] No se detecto apt-get; asegurate de tener python3-venv y python3-tk."
else
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-tk
fi

echo "[1/3] Creando entorno virtual..."
python3 -m venv venv

echo "[2/3] Instalando dependencias..."
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[3/3] Verificando instalacion..."
python -m compileall -q app.py

cat > iniciar.sh <<'EOF'
#!/bin/bash
set -e
source venv/bin/activate
python app.py
EOF
chmod +x iniciar.sh

echo
echo "======================================================="
echo "  Instalacion completada correctamente."
echo "  Ejecuta ./iniciar.sh para abrir NoticiasINE."
echo "======================================================="
