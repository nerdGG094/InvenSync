@echo off
title INV.ALMOX Flask Service
cd /d "C:\Users\Administrador\Desktop\python\2025 - FLASK_ALMOX\InventarioAlmox"
echo Iniciando servidor Flask...
python run.py >> flask_output.log 2>&1
