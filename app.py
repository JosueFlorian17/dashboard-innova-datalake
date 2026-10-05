import os
import sqlite3
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_file

try:
    import geopandas as gpd
except ImportError:
    gpd = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DASHBOARD_DB", BASE_DIR / "dashboard_data_completo.db"))
DB_GZ_PATH = BASE_DIR / "dashboard_data_completo.db.gz"

# Ahora busca dinámicamente la carpeta "shapefiles" en el mismo directorio de app.py
SHAPEFILE_DIR = Path(os.getenv("SHAPEFILE_DIR", BASE_DIR / "shapefiles"))

app = Flask(__name__, static_folder=str(BASE_DIR))
GEOJSON_CACHE = {}

CATALOG = {
    "mortalidad": {
        "label": "Mortalidad (SINADEF)",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": True,
        "tiene_meses": True,
        "min_anio": 2003,
        "max_anio": 2024,
        "indicadores": [
            {"id": "mortalidad_total", "label": "Defunciones Anuales - Total"},
            {"id": "mortalidad_femenino", "label": "Defunciones Anuales - Mujeres (F)"},
            {"id": "mortalidad_masculino", "label": "Defunciones Anuales - Hombres (M)"},
        ],
    },
    "poblacion": {
        "label": "Población Proyectada (INEI)",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": True,
        "min_anio": 2000,
        "max_anio": 2025,
        "indicadores": [
            {"id": "poblacion_total", "label": "Población Total (Ambos Sexos)"},
            {"id": "poblacion_f", "label": "Población - Mujeres (F)"},
            {"id": "poblacion_m", "label": "Población - Hombres (M)"},
            {"id": "poblacion_0_50", "label": "Población - Edad 0 a 50"},
            {"id": "poblacion_mayor_50", "label": "Población - Edad >50"},
            {"id": "poblacion_f_0_50", "label": "Población - Mujeres Edad 0 a 50"},
            {"id": "poblacion_f_mayor_50", "label": "Población - Mujeres Edad >50"},
            {"id": "poblacion_m_0_50", "label": "Población - Hombres Edad 0 a 50"},
            {"id": "poblacion_m_mayor_50", "label": "Población - Hombres Edad >50"},
        ],
    },
    "clima": {
        "label": "Clima y Calidad del Aire",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": True,
        "min_anio": 2001,
        "max_anio": 2024,
        "indicadores": [
            {"id": "clima_pm25", "label": "Material Particulado PM2.5 (2001-2022)"},
            {"id": "clima_no2", "label": "Dióxido de Nitrógeno NO2 (2019-2024)"},
            {"id": "clima_pp", "label": "Precipitación Media Anual (2001-2024)"},
            {"id": "clima_lst", "label": "Temperatura Superficial LST (2001-2024)"},
        ],
    },
    "salud_vectores": {
        "label": "Salud - Vectores (Dengue / Malaria)",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": True,
        "tiene_meses": True,
        "min_anio": 2000,
        "max_anio": 2024,
        "indicadores": [
            {"id": "dengue_total", "label": "Dengue - Casos Totales"},
            {"id": "dengue_f", "label": "Dengue - Mujeres (F)"},
            {"id": "dengue_m", "label": "Dengue - Hombres (M)"},
            {"id": "dengue_0_19", "label": "Dengue - Edad 0 a 19 años"},
            {"id": "dengue_mayor_20", "label": "Dengue - Edad >20 años"},
            {"id": "malaria_total", "label": "Malaria - Casos Totales"},
            {"id": "malaria_falciparum", "label": "Malaria - Falciparum (PF)"},
            {"id": "malaria_vivax", "label": "Malaria - Vivax (PV)"},
            {"id": "malaria_f", "label": "Malaria - Mujeres (F)"},
            {"id": "malaria_m", "label": "Malaria - Hombres (M)"},
        ],
    },
    "censo": {
        "label": "Censo / Socioeconómico (REDATAM)",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": False,
        "indicadores": [
            {"id": "UNEMPLOYMENT_RATE", "label": "Tasa de Desempleo Total (%)"},
            {"id": "UNEMPLOYMENT_RATE_F", "label": "Tasa de Desempleo - Mujeres (%)"},
            {"id": "UNEMPLOYMENT_RATE_M", "label": "Tasa de Desempleo - Hombres (%)"},
            {"id": "UNEMPLOYMENT_RATIO_F_TO_M", "label": "Ratio Desempleo Mujer/Hombre"},
            {"id": "LABOR_FORCE_PARTICIPATION", "label": "Participación en Fuerza Laboral Total (%)"},
            {"id": "LABOR_FORCE_PARTICIPATION_F", "label": "Participación Laboral - Mujeres (%)"},
            {"id": "LABOR_FORCE_PARTICIPATION_M", "label": "Participación Laboral - Hombres (%)"},
            {"id": "FEMALE_LABOR_FORCE_RATIO", "label": "Proporción de Mujeres en Fuerza Laboral (%)"},
            {"id": "PARTICIPATION_RATIO_F_TO_M", "label": "Ratio Participación Laboral Mujer/Hombre"},
            {"id": "NO_EDUCATION_NOR_EMPLOYMENT", "label": "Población NINI (No estudia ni trabaja) (%)"},
            {"id": "NO_EDUCATION_NOR_EMPLOYMENT_F", "label": "Población NINI - Mujeres (%)"},
            {"id": "NO_EDUCATION_NOR_EMPLOYMENT_M", "label": "Población NINI - Hombres (%)"},
            {"id": "SCHOOL_ATTENDANCE_15_17", "label": "Asistencia Escolar 15-17 años Total (%)"},
            {"id": "SCHOOL_ATTENDANCE_15_17_F", "label": "Asistencia Escolar 15-17 - Mujeres (%)"},
            {"id": "SCHOOL_ATTENDANCE_15_17_M", "label": "Asistencia Escolar 15-17 - Hombres (%)"},
            {"id": "SCHOOL_RATIO_F_TO_M_15_17", "label": "Ratio Asistencia Escolar Mujer/Hombre 15-17"},
            {"id": "EDUCATION_PRIMARY_COMPLETED", "label": "Primaria Completa Total (%)"},
            {"id": "EDUCATION_PRIMARY_COMPLETED_F", "label": "Primaria Completa - Mujeres (%)"},
            {"id": "EDUCATION_PRIMARY_COMPLETED_M", "label": "Primaria Completa - Hombres (%)"},
            {"id": "EDUCATION_SECONDARY_COMPLETED", "label": "Secundaria Completa Total (%)"},
            {"id": "EDUCATION_SECONDARY_COMPLETED_F", "label": "Secundaria Completa - Mujeres (%)"},
            {"id": "EDUCATION_SECONDARY_COMPLETED_M", "label": "Secundaria Completa - Hombres (%)"},
            {"id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED", "label": "Ratio Secundaria Completa Mujer/Hombre"},
            {"id": "EDUCATION_UNIVERSITY_COMPLETED", "label": "Superior Universitaria Completa Total (%)"},
            {"id": "EDUCATION_UNIVERSITY_COMPLETED_F", "label": "Superior Universitaria Completa - Mujeres (%)"},
            {"id": "EDUCATION_UNIVERSITY_COMPLETED_M", "label": "Superior Universitaria Completa - Hombres (%)"},
            {"id": "POP_CENSADA_REDATAM", "label": "Población Censada Efectiva (Redatam)"},
            {"id": "POP_TOTAL_REDATAM", "label": "Población Total Estimada (Redatam)"},
            {"id": "POP_CENSO_PROCESADA", "label": "Población Procesada en Censo"},
        ],
    },
    "endes": {
        "label": "ENDES - Salud Infantil y Vacunación",
        "niveles": ["departamento"],
        "tiene_anios": True,
        "min_anio": 2020,
        "max_anio": 2023,
        "indicadores": [
            # Anemia
            {"id": "anemia_p", "label": "Anemia Infantil - Prevalencia (%)"},
            {"id": "anemia_low_ci", "label": "Anemia Infantil - IC95% Inferior (%)"},
            {"id": "anemia_high_ci", "label": "Anemia Infantil - IC95% Superior (%)"},
            {"id": "anemia_n", "label": "Anemia Infantil - Tamaño Muestral (N)"},
            # Influenza 1D
            {"id": "vac_influenza_1d_p", "label": "Vacuna Influenza 1ª Dosis (%)"},
            {"id": "vac_influenza_1d_low_ci", "label": "Vacuna Influenza 1ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_influenza_1d_high_ci", "label": "Vacuna Influenza 1ª Dosis - IC95% Superior (%)"},
            {"id": "vac_influenza_1d_n", "label": "Vacuna Influenza 1ª Dosis - Tamaño Muestral (N)"},
            # Influenza 2D
            {"id": "vac_influenza_2d_p", "label": "Vacuna Influenza 2ª Dosis (%)"},
            {"id": "vac_influenza_2d_low_ci", "label": "Vacuna Influenza 2ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_influenza_2d_high_ci", "label": "Vacuna Influenza 2ª Dosis - IC95% Superior (%)"},
            {"id": "vac_influenza_2d_n", "label": "Vacuna Influenza 2ª Dosis - Tamaño Muestral (N)"},
            # Rotavirus 1D
            {"id": "vac_rotavirus_1d_p", "label": "Vacuna Rotavirus 1ª Dosis (%)"},
            {"id": "vac_rotavirus_1d_low_ci", "label": "Vacuna Rotavirus 1ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_rotavirus_1d_high_ci", "label": "Vacuna Rotavirus 1ª Dosis - IC95% Superior (%)"},
            {"id": "vac_rotavirus_1d_n", "label": "Vacuna Rotavirus 1ª Dosis - Tamaño Muestral (N)"},
            # Rotavirus 2D
            {"id": "vac_rotavirus_2d_p", "label": "Vacuna Rotavirus 2ª Dosis (%)"},
            {"id": "vac_rotavirus_2d_low_ci", "label": "Vacuna Rotavirus 2ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_rotavirus_2d_high_ci", "label": "Vacuna Rotavirus 2ª Dosis - IC95% Superior (%)"},
            {"id": "vac_rotavirus_2d_n", "label": "Vacuna Rotavirus 2ª Dosis - Tamaño Muestral (N)"},
            # Neumococo 1D
            {"id": "vac_neumococo_1d_p", "label": "Vacuna Neumococo 1ª Dosis (%)"},
            {"id": "vac_neumococo_1d_low_ci", "label": "Vacuna Neumococo 1ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_neumococo_1d_high_ci", "label": "Vacuna Neumococo 1ª Dosis - IC95% Superior (%)"},
            {"id": "vac_neumococo_1d_n", "label": "Vacuna Neumococo 1ª Dosis - Tamaño Muestral (N)"},
            # Neumococo 2D
            {"id": "vac_neumococo_2d_p", "label": "Vacuna Neumococo 2ª Dosis (%)"},
            {"id": "vac_neumococo_2d_low_ci", "label": "Vacuna Neumococo 2ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_neumococo_2d_high_ci", "label": "Vacuna Neumococo 2ª Dosis - IC95% Superior (%)"},
            {"id": "vac_neumococo_2d_n", "label": "Vacuna Neumococo 2ª Dosis - Tamaño Muestral (N)"},
            # Neumococo 3D
            {"id": "vac_neumococo_3d_p", "label": "Vacuna Neumococo 3ª Dosis (%)"},
            {"id": "vac_neumococo_3d_low_ci", "label": "Vacuna Neumococo 3ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_neumococo_3d_high_ci", "label": "Vacuna Neumococo 3ª Dosis - IC95% Superior (%)"},
            {"id": "vac_neumococo_3d_n", "label": "Vacuna Neumococo 3ª Dosis - Tamaño Muestral (N)"},
            # Pentavalente 1D
            {"id": "vac_pentavalente_1d_p", "label": "Vacuna Pentavalente 1ª Dosis (%)"},
            {"id": "vac_pentavalente_1d_low_ci", "label": "Vacuna Pentavalente 1ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_pentavalente_1d_high_ci", "label": "Vacuna Pentavalente 1ª Dosis - IC95% Superior (%)"},
            {"id": "vac_pentavalente_1d_n", "label": "Vacuna Pentavalente 1ª Dosis - Tamaño Muestral (N)"},
            # Pentavalente 2D
            {"id": "vac_pentavalente_2d_p", "label": "Vacuna Pentavalente 2ª Dosis (%)"},
            {"id": "vac_pentavalente_2d_low_ci", "label": "Vacuna Pentavalente 2ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_pentavalente_2d_high_ci", "label": "Vacuna Pentavalente 2ª Dosis - IC95% Superior (%)"},
            {"id": "vac_pentavalente_2d_n", "label": "Vacuna Pentavalente 2ª Dosis - Tamaño Muestral (N)"},
            # Pentavalente 3D
            {"id": "vac_pentavalente_3d_p", "label": "Vacuna Pentavalente 3ª Dosis (%)"},
            {"id": "vac_pentavalente_3d_low_ci", "label": "Vacuna Pentavalente 3ª Dosis - IC95% Inferior (%)"},
            {"id": "vac_pentavalente_3d_high_ci", "label": "Vacuna Pentavalente 3ª Dosis - IC95% Superior (%)"},
            {"id": "vac_pentavalente_3d_n", "label": "Vacuna Pentavalente 3ª Dosis - Tamaño Muestral (N)"},
        ],
    },
    "endes_vivienda": {
        "label": "ENDES - Vivienda y Saneamiento",
        "niveles": ["departamento"],
        "tiene_anios": False,
        "indicadores": [
            # Paredes
            {"id": "pared_noble_p", "label": "Paredes Material Noble / Adecuadas (%)"},
            {"id": "pared_noble_low_ci", "label": "Paredes Material Noble - IC95% Inferior (%)"},
            {"id": "pared_noble_high_ci", "label": "Paredes Material Noble - IC95% Superior (%)"},
            {"id": "pared_noble_n", "label": "Paredes Material Noble - Tamaño Muestral (N)"},
            {"id": "pared_rustica_p", "label": "Paredes Material Rústico (%)"},
            {"id": "pared_rustica_low_ci", "label": "Paredes Material Rústico - IC95% Inferior (%)"},
            {"id": "pared_rustica_high_ci", "label": "Paredes Material Rústico - IC95% Superior (%)"},
            {"id": "pared_rustica_n", "label": "Paredes Material Rústico - Tamaño Muestral (N)"},
            {"id": "pared_natural_p", "label": "Paredes Material Natural (%)"},
            {"id": "pared_natural_low_ci", "label": "Paredes Material Natural - IC95% Inferior (%)"},
            {"id": "pared_natural_high_ci", "label": "Paredes Material Natural - IC95% Superior (%)"},
            {"id": "pared_natural_n", "label": "Paredes Material Natural - Tamaño Muestral (N)"},
            # Pisos
            {"id": "piso_acabado_p", "label": "Piso Acabado / Pavimentado (%)"},
            {"id": "piso_acabado_low_ci", "label": "Piso Acabado - IC95% Inferior (%)"},
            {"id": "piso_acabado_high_ci", "label": "Piso Acabado - IC95% Superior (%)"},
            {"id": "piso_acabado_n", "label": "Piso Acabado - Tamaño Muestral (N)"},
            {"id": "piso_tierra_p", "label": "Piso de Tierra / Natural (%)"},
            {"id": "piso_tierra_low_ci", "label": "Piso de Tierra - IC95% Inferior (%)"},
            {"id": "piso_tierra_high_ci", "label": "Piso de Tierra - IC95% Superior (%)"},
            {"id": "piso_tierra_n", "label": "Piso de Tierra - Tamaño Muestral (N)"},
            {"id": "piso_rustico_p", "label": "Piso Rústico / Madera no tratada (%)"},
            {"id": "piso_rustico_low_ci", "label": "Piso Rústico - IC95% Inferior (%)"},
            {"id": "piso_rustico_high_ci", "label": "Piso Rústico - IC95% Superior (%)"},
            {"id": "piso_rustico_n", "label": "Piso Rústico - Tamaño Muestral (N)"},
            # Agua
            {"id": "agua_red_publica_p", "label": "Agua de Red Pública (%)"},
            {"id": "agua_red_publica_low_ci", "label": "Agua Red Pública - IC95% Inferior (%)"},
            {"id": "agua_red_publica_high_ci", "label": "Agua Red Pública - IC95% Superior (%)"},
            {"id": "agua_red_publica_n", "label": "Agua Red Pública - Tamaño Muestral (N)"},
            {"id": "agua_pozo_p", "label": "Agua de Pozo subterráneo (%)"},
            {"id": "agua_pozo_low_ci", "label": "Agua de Pozo - IC95% Inferior (%)"},
            {"id": "agua_pozo_high_ci", "label": "Agua de Pozo - IC95% Superior (%)"},
            {"id": "agua_pozo_n", "label": "Agua de Pozo - Tamaño Muestral (N)"},
            {"id": "agua_superficial_p", "label": "Agua Superficial (Río/Acequia/Lago) (%)"},
            {"id": "agua_superficial_low_ci", "label": "Agua Superficial - IC95% Inferior (%)"},
            {"id": "agua_superficial_high_ci", "label": "Agua Superficial - IC95% Superior (%)"},
            {"id": "agua_superficial_n", "label": "Agua Superficial - Tamaño Muestral (N)"},
            {"id": "otra_fuente_agua_p", "label": "Otra Fuente de Agua (%)"},
            {"id": "otra_fuente_agua_low_ci", "label": "Otra Fuente de Agua - IC95% Inferior (%)"},
            {"id": "otra_fuente_agua_high_ci", "label": "Otra Fuente de Agua - IC95% Superior (%)"},
            {"id": "otra_fuente_agua_n", "label": "Otra Fuente de Agua - Tamaño Muestral (N)"},
            # Saneamiento
            {"id": "desague_alcantarillado_p", "label": "Desagüe conectado a Red Pública / Alcantarillado (%)"},
            {"id": "desague_alcantarillado_low_ci", "label": "Desagüe Alcantarillado - IC95% Inferior (%)"},
            {"id": "desague_alcantarillado_high_ci", "label": "Desagüe Alcantarillado - IC95% Superior (%)"},
            {"id": "desague_alcantarillado_n", "label": "Desagüe Alcantarillado - Tamaño Muestral (N)"},
            {"id": "letrina_pozo_p", "label": "Letrina / Pozo ciego (%)"},
            {"id": "letrina_pozo_low_ci", "label": "Letrina / Pozo ciego - IC95% Inferior (%)"},
            {"id": "letrina_pozo_high_ci", "label": "Letrina / Pozo ciego - IC95% Superior (%)"},
            {"id": "letrina_pozo_n", "label": "Letrina / Pozo ciego - Tamaño Muestral (N)"},
            {"id": "sin_servicio_higienico_p", "label": "Sin Servicio Higiénico (%)"},
            {"id": "sin_servicio_higienico_low_ci", "label": "Sin Servicio Higiénico - IC95% Inferior (%)"},
            {"id": "sin_servicio_higienico_high_ci", "label": "Sin Servicio Higiénico - IC95% Superior (%)"},
            {"id": "sin_servicio_higienico_n", "label": "Sin Servicio Higiénico - Tamaño Muestral (N)"},
            {"id": "otro_servicio_higienico_p", "label": "Otro Tipo de Servicio Higiénico (%)"},
            {"id": "otro_servicio_higienico_low_ci", "label": "Otro Servicio Higiénico - IC95% Inferior (%)"},
            {"id": "otro_servicio_higienico_high_ci", "label": "Otro Servicio Higiénico - IC95% Superior (%)"},
            {"id": "otro_servicio_higienico_n", "label": "Otro Servicio Higiénico - Tamaño Muestral (N)"},
        ],
    },
    "endes_sifilis": {
        "label": "ENDES - Sífilis en Gestantes",
        "niveles": ["departamento"],
        "tiene_anios": True,
        "min_anio": 2010,
        "max_anio": 2022,
        "indicadores": [
            {"id": "sifilis_casos", "label": "Sífilis en Gestantes - Casos Notificados (N)"},
        ],
    },
    "travel_time": {
        "label": "Infraestructura - Tiempos de Viaje",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": False,
        "indicadores": [
            {"id": "primary_hcf", "label": "Tiempo a Establecimiento de Salud Nivel I (min)"},
            {"id": "secondary_hcf", "label": "Tiempo a Establecimiento de Salud Nivel II (min)"},
            {"id": "tertiary_hcf", "label": "Tiempo a Establecimiento de Salud Nivel III (min)"},
        ],
    },
}

# Auto-build full inventory from CATALOG and specific definitions
def build_inventory():
    inv = []
    
    # 1. Mortalidad
    inv.extend([
        {
            "id": "DEATHS_YYYY",
            "base_key": "mortalidad",
            "indicador_id": "mortalidad_total",
            "grupo": "Mortalidad",
            "indicador": "Defunciones Anuales - Total",
            "descripcion": "Número total de defunciones registradas en el año YYYY (desagregable por mes).",
            "resolucion_temporal": "2003 - 2024 (Anual y Mensual)",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "SINADEF / MINSA",
            "unidad": "Defunciones",
        },
        {
            "id": "DEATHS_YYYY_F",
            "base_key": "mortalidad",
            "indicador_id": "mortalidad_femenino",
            "grupo": "Mortalidad",
            "indicador": "Defunciones Anuales - Mujeres (F)",
            "descripcion": "Total de defunciones registradas de sexo femenino en el año YYYY.",
            "resolucion_temporal": "2003 - 2024 (Anual y Mensual)",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "SINADEF / MINSA",
            "unidad": "Defunciones",
        },
        {
            "id": "DEATHS_YYYY_M",
            "base_key": "mortalidad",
            "indicador_id": "mortalidad_masculino",
            "grupo": "Mortalidad",
            "indicador": "Defunciones Anuales - Hombres (M)",
            "descripcion": "Total de defunciones registradas de sexo masculino en el año YYYY.",
            "resolucion_temporal": "2003 - 2024 (Anual y Mensual)",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "SINADEF / MINSA",
            "unidad": "Defunciones",
        },
    ])
    
    # 2. Población
    pop_items = [
        ("POP_YYYY", "poblacion_total", "Población Total Estimada", "Población proyectada total para el año YYYY."),
        ("POP_YYYY_F", "poblacion_f", "Población - Mujeres (F)", "Población proyectada de sexo femenino en el año YYYY."),
        ("POP_YYYY_M", "poblacion_m", "Población - Hombres (M)", "Población proyectada de sexo masculino en el año YYYY."),
        ("POP_YYYY_0_50", "poblacion_0_50", "Población - Edad 0 a 50 años", "Población proyectada de 0 a 50 años en el año YYYY."),
        ("POP_YYYY_MAYOR_50", "poblacion_mayor_50", "Población - Edad >50 años", "Población proyectada de más de 50 años en el año YYYY."),
        ("POP_YYYY_F_0_50", "poblacion_f_0_50", "Población - Mujeres Edad 0 a 50", "Población proyectada de mujeres de 0 a 50 años en el año YYYY."),
        ("POP_YYYY_F_MAYOR_50", "poblacion_f_mayor_50", "Población - Mujeres Edad >50", "Población proyectada de mujeres de más de 50 años en el año YYYY."),
        ("POP_YYYY_M_0_50", "poblacion_m_0_50", "Población - Hombres Edad 0 a 50", "Población proyectada de hombres de 0 a 50 años en el año YYYY."),
        ("POP_YYYY_M_MAYOR_50", "poblacion_m_mayor_50", "Población - Hombres Edad >50", "Población proyectada de hombres de más de 50 años en el año YYYY."),
    ]
    for cid, iid, lbl, dsc in pop_items:
        inv.append({
            "id": cid,
            "base_key": "poblacion",
            "indicador_id": iid,
            "grupo": "Demografía",
            "indicador": lbl,
            "descripcion": dsc,
            "resolucion_temporal": "2000 - 2025",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "INEI - Proyecciones Poblacionales",
            "unidad": "Habitantes",
        })

    # 3. Clima
    clim_items = [
        ("PM2_5_PROM_YYYY", "clima_pm25", "Material Particulado PM2.5", "Nivel promedio de material particulado PM2.5 en el año YYYY.", "2001 - 2022", "NASA / SEDAC", "µg/m³"),
        ("NO2_PROM_YYYY", "clima_no2", "Dióxido de Nitrógeno (NO2)", "Nivel promedio de dióxido de nitrógeno en el año YYYY.", "2019 - 2024", "ESA Sentinel-5P", "µmol/m²"),
        ("PREC_PROM_YYYY", "clima_pp", "Precipitación Promedio Anual", "Precipitación promedio acumulada anual en el año YYYY.", "2001 - 2024", "SENAMHI / CHIRPS", "mm/año"),
        ("T_PROM_YYYY", "clima_lst", "Temperatura Superficial (LST)", "Temperatura superficial promedio en el año YYYY.", "2001 - 2024", "MODIS / NASA", "°C"),
    ]
    for cid, iid, lbl, dsc, temp, fue, uni in clim_items:
        inv.append({
            "id": cid,
            "base_key": "clima",
            "indicador_id": iid,
            "grupo": "Clima",
            "indicador": lbl,
            "descripcion": dsc,
            "resolucion_temporal": temp,
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": fue,
            "unidad": uni,
        })

    # 4. Salud Vectores
    vect_items = [
        ("DENGUE_YYYY", "dengue_total", "Casos de Dengue - Total", "Total de casos notificados de dengue en el año YYYY."),
        ("DENGUE_YYYY_F", "dengue_f", "Casos de Dengue - Mujeres (F)", "Total de casos notificados de dengue en mujeres en el año YYYY."),
        ("DENGUE_YYYY_M", "dengue_m", "Casos de Dengue - Hombres (M)", "Total de casos notificados de dengue en hombres en el año YYYY."),
        ("DENGUE_YYYY_0_19", "dengue_0_19", "Casos de Dengue - Edad 0 a 19 años", "Total de casos notificados de dengue en menores de 20 años en el año YYYY."),
        ("DENGUE_YYYY_MAYOR_20", "dengue_mayor_20", "Casos de Dengue - Edad >20 años", "Total de casos notificados de dengue en mayores de 20 años en el año YYYY."),
        ("MALARIA_YYYY", "malaria_total", "Casos de Malaria - Total", "Total de casos notificados de malaria en el año YYYY."),
        ("MALARIA_YYYY_PF", "malaria_falciparum", "Casos de Malaria - P. Falciparum", "Total de casos de malaria por Plasmodium Falciparum en el año YYYY."),
        ("MALARIA_YYYY_PV", "malaria_vivax", "Casos de Malaria - P. Vivax", "Total de casos de malaria por Plasmodium Vivax en el año YYYY."),
        ("MALARIA_YYYY_F", "malaria_f", "Casos de Malaria - Mujeres (F)", "Total de casos notificados de malaria en mujeres en el año YYYY."),
        ("MALARIA_YYYY_M", "malaria_m", "Casos de Malaria - Hombres (M)", "Total de casos notificados de malaria en hombres en el año YYYY."),
    ]
    for cid, iid, lbl, dsc in vect_items:
        inv.append({
            "id": cid,
            "base_key": "salud_vectores",
            "indicador_id": iid,
            "grupo": "Salud",
            "indicador": lbl,
            "descripcion": dsc,
            "resolucion_temporal": "2000 - 2024 (Anual y Mensual)",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "CDC Perú / MINSA",
            "unidad": "Casos Notificados",
        })

    # 5. Censo
    for ind in CATALOG["censo"]["indicadores"]:
        uni = "Porcentaje (%)" if "%" in ind["label"] else "Ratio" if "Ratio" in ind["label"] else "Habitantes"
        inv.append({
            "id": ind["id"],
            "base_key": "censo",
            "indicador_id": ind["id"],
            "grupo": "CENSO",
            "indicador": ind["label"],
            "descripcion": f"Indicador censal de {ind['label']} según registros oficiales del Censo Nacional 2017.",
            "resolucion_temporal": "2017 (Censal)",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "INEI - Censo Nacional 2017",
            "unidad": uni,
        })

    # 6. ENDES Salud & Vacunación
    for ind in CATALOG["endes"]["indicadores"]:
        uni = "Porcentaje (%)" if "%" in ind["label"] else "Conteo (N)"
        inv.append({
            "id": f"ENDES_{ind['id'].upper()}_YYYY",
            "base_key": "endes",
            "indicador_id": ind["id"],
            "grupo": "ENDES",
            "indicador": ind["label"],
            "descripcion": f"Estimación departamental de {ind['label']} en menores de 5 años.",
            "resolucion_temporal": "2020 - 2023",
            "resolucion_espacial": ["Departamento"],
            "fuente": "INEI - ENDES",
            "unidad": uni,
        })

    # 7. ENDES Vivienda
    for ind in CATALOG["endes_vivienda"]["indicadores"]:
        uni = "Porcentaje (%)" if "%" in ind["label"] else "Conteo (N)"
        inv.append({
            "id": f"ENDES_{ind['id'].upper()}_2023",
            "base_key": "endes_vivienda",
            "indicador_id": ind["id"],
            "grupo": "ENDES",
            "indicador": ind["label"],
            "descripcion": f"Estimación departamental de características de la vivienda: {ind['label']}.",
            "resolucion_temporal": "2023",
            "resolucion_espacial": ["Departamento"],
            "fuente": "INEI - ENDES",
            "unidad": uni,
        })

    # 8. ENDES Sífilis
    inv.append({
        "id": "ENDES_SIFILIS_N_YYYY",
        "base_key": "endes_sifilis",
        "indicador_id": "sifilis_casos",
        "grupo": "ENDES",
        "indicador": "Sífilis en Gestantes - Casos Notificados",
        "descripcion": "Casos de sífilis en gestantes notificados por departamento.",
        "resolucion_temporal": "2010 - 2022",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Casos Notificados",
    })

    # 9. Travel Time
    tt_items = [
        ("TRAVEL_TIME_PRIMARY_HCF", "primary_hcf", "Tiempo a Establecimiento Nivel I", "Tiempo medio estimado de viaje a establecimiento de salud de primer nivel de atención."),
        ("TRAVEL_TIME_SECONDARY_HCF", "secondary_hcf", "Tiempo a Establecimiento Nivel II", "Tiempo medio estimado de viaje a hospital de segundo nivel de atención."),
        ("TRAVEL_TIME_TERTIARY_HCF", "tertiary_hcf", "Tiempo a Establecimiento Nivel III", "Tiempo medio estimado de viaje a instituto o hospital especializado de tercer nivel."),
    ]
    for cid, iid, lbl, dsc in tt_items:
        inv.append({
            "id": cid,
            "base_key": "travel_time",
            "indicador_id": iid,
            "grupo": "Misceláneo",
            "indicador": lbl,
            "descripcion": dsc,
            "resolucion_temporal": "2020",
            "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
            "fuente": "Oxford / Malaria Atlas Project",
            "unidad": "Minutos",
        })

    return inv

INVENTORY = build_inventory()

def ensure_sqlite_ready():
    if DB_GZ_PATH.exists():
        if not DB_PATH.exists() or DB_PATH.stat().st_size < 1_000_000:
            print("Extrayendo base de datos optimizada desde dashboard_data_completo.db.gz...")
            import gzip
            import shutil
            with gzip.open(DB_GZ_PATH, 'rb') as f_in, open(DB_PATH, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            print("Base de datos extraida exitosamente.")

ensure_sqlite_ready()

def get_db():
    ensure_sqlite_ready()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No existe la base de datos: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def parse_year(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def with_names(df, conn, nivel=None):
    if nivel:
        names = pd.read_sql_query(
            "SELECT ubigeo, nombre FROM dim_geografia WHERE nivel_geo = ?",
            conn, params=(nivel,)
        )
    else:
        names = pd.read_sql_query(
            "SELECT ubigeo, nombre FROM dim_geografia",
            conn,
        )
    if df.empty or "ubigeo" not in df.columns:
        return names
    return names.merge(df, on="ubigeo", how="left")

def temporal_response(df, prefix, conn, nivel=None):
    if nivel:
        names = pd.read_sql_query("SELECT ubigeo, nombre FROM dim_geografia WHERE nivel_geo = ?", conn, params=(nivel,))
    else:
        names = pd.read_sql_query("SELECT ubigeo, nombre FROM dim_geografia", conn)
    
    if df.empty:
        return jsonify({"columns": ["ubigeo", "nombre"], "rows": names.to_dict(orient="records")})
    
    df = df.merge(names, on="ubigeo", how="left")
    df = df.pivot_table(
        index=["ubigeo", "nombre"],
        columns="anio",
        values="valor",
        aggfunc="mean",
    ).reset_index()
    full = names.merge(df, on=["ubigeo", "nombre"], how="left")
    full.columns = [f"{prefix}{column}" if isinstance(column, int) else column for column in full.columns]
    full = full.fillna(0)
    return jsonify({"columns": list(full.columns), "rows": full.to_dict(orient="records")})

def temporal_monthly_response(df, prefix, conn, anio_min, anio_max, nivel=None):
    if nivel:
        names = pd.read_sql_query("SELECT ubigeo, nombre FROM dim_geografia WHERE nivel_geo = ?", conn, params=(nivel,))
    else:
        names = pd.read_sql_query("SELECT ubigeo, nombre FROM dim_geografia", conn)
        
    if df.empty:
        return jsonify({"columns": ["ubigeo", "nombre"], "rows": names.to_dict(orient="records")})
        
    df = df.merge(names, on="ubigeo", how="left")
    df["periodo"] = df.apply(lambda r: str(r["anio"]) if str(r["mes"]) == "Total" else f"{r['anio']}_{r['mes']}", axis=1)
    piv = df.pivot_table(index=["ubigeo", "nombre"], columns="periodo", values="valor", aggfunc="sum").reset_index()
    
    full = names.merge(piv, on=["ubigeo", "nombre"], how="left")
    
    ordered_cols = ["ubigeo", "nombre"]
    for y in range(anio_min, anio_max + 1):
        ordered_cols.append(str(y))
        for m in range(1, 13):
            ordered_cols.append(f"{y}_{m:02d}")
                
    available_cols = [c for c in ordered_cols if c in full.columns]
    full = full[available_cols]
    full.columns = [f"{prefix}{c}" if c not in ("ubigeo", "nombre") else c for c in full.columns]
    full = full.fillna(0)
    return jsonify({"columns": list(full.columns), "rows": full.to_dict(orient="records")})

@app.route("/")
def home():
    return send_file(BASE_DIR / "index.html")

@app.route("/api/config")
def get_config():
    return jsonify(CATALOG)

@app.route("/api/inventory")
def get_inventory():
    return jsonify(INVENTORY)

@app.route("/api/meta")
def get_meta():
    conn = get_db()
    years = []
    for table in ("fact_population", "fact_mortality", "fact_climate", "fact_endes_vacuna"):
        years.extend(row[0] for row in conn.execute(f"SELECT DISTINCT anio FROM {table}"))
    conn.close()
    years = sorted(set(year for year in years if year is not None))
    return jsonify({"min_anio": min(years) if years else 2000, "max_anio": max(years) if years else 2024, "anios": years})

@app.route("/api/data")
def get_data():
    nivel = request.args.get("nivel", "departamento").lower()
    base = request.args.get("base", "mortalidad")
    indicador = request.args.get("indicador", "mortalidad_total")
    anio_min = parse_year(request.args.get("anio_min"), 2000)
    anio_max = parse_year(request.args.get("anio_max"), 2024)
    if anio_min > anio_max:
        anio_min, anio_max = anio_max, anio_min
    if base not in CATALOG:
        return jsonify({"error": "Nivel o base no válidos"}), 400
    base_config = CATALOG[base]
    valid_indicators = {item["id"] for item in base_config["indicadores"]}
    if nivel not in base_config["niveles"]:
        return jsonify({"error": "Nivel no disponible para esta base"}), 400
    if indicador not in valid_indicators:
        return jsonify({"error": "Indicador no válido para esta base"}), 400

    conn = get_db()
    if base == "mortalidad":
        sexo = "F" if indicador == "mortalidad_femenino" else "M" if indicador == "mortalidad_masculino" else "Total"
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, mes, defunciones AS valor FROM fact_mortality WHERE nivel_geo = ? AND sexo = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, sexo, anio_min, anio_max),
        )
        result = temporal_monthly_response(df, "DEATHS_", conn, anio_min, anio_max, nivel=nivel)
    elif base == "poblacion":
        sexo_map = {
            "poblacion_total": ("Total", "Total", "POP_"),
            "poblacion_f": ("F", "Total", "POP_F_"),
            "poblacion_m": ("M", "Total", "POP_M_"),
            "poblacion_0_50": ("Total", "0-50", "POP_0_50_"),
            "poblacion_mayor_50": ("Total", ">50", "POP_MAYOR_50_"),
            "poblacion_f_0_50": ("F", "0-50", "POP_F_0_50_"),
            "poblacion_f_mayor_50": ("F", ">50", "POP_F_MAYOR_50_"),
            "poblacion_m_0_50": ("M", "0-50", "POP_M_0_50_"),
            "poblacion_m_mayor_50": ("M", ">50", "POP_M_MAYOR_50_"),
        }
        sexo, grupo, prefix = sexo_map.get(indicador, ("Total", "Total", "POP_"))
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, poblacion AS valor FROM fact_population WHERE nivel_geo = ? AND sexo = ? AND grupo_edad = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, sexo, grupo, anio_min, anio_max),
        )
        result = temporal_response(df, prefix, conn, nivel=nivel)
    elif base == "clima":
        variable, prefix = {
            "clima_pm25": ("PM2_5", "PM25_"),
            "clima_no2": ("NO2", "NO2_"),
            "clima_pp": ("PRECIPITATION", "PP_"),
            "clima_lst": ("TEMPERATURE_LST", "LST_"),
        }.get(indicador, ("PM2_5", "PM25_"))
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, valor FROM fact_climate WHERE nivel_geo = ? AND variable = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, variable, anio_min, anio_max),
        )
        result = temporal_response(df, prefix, conn, nivel=nivel)
    elif base == "salud_vectores":
        if indicador == "dengue_total":
            disease, sexo, edad, prefix = "DENGUE", "Total", "Total", "DENGUE_"
        elif indicador == "dengue_f":
            disease, sexo, edad, prefix = "DENGUE", "F", "Total", "DENGUE_F_"
        elif indicador == "dengue_m":
            disease, sexo, edad, prefix = "DENGUE", "M", "Total", "DENGUE_M_"
        elif indicador == "dengue_0_19":
            disease, sexo, edad, prefix = "DENGUE", "Total", "0-19", "DENGUE_0_19_"
        elif indicador == "dengue_mayor_20":
            disease, sexo, edad, prefix = "DENGUE", "Total", ">20", "DENGUE_MAYOR_20_"
        elif indicador == "malaria_total":
            disease, sexo, edad, prefix = "MALARIA", "Total", "Total", "MALARIA_"
        elif indicador == "malaria_falciparum":
            disease, sexo, edad, prefix = "MALARIA_PF", "Total", "Total", "MALARIA_PF_"
        elif indicador == "malaria_vivax":
            disease, sexo, edad, prefix = "MALARIA_PV", "Total", "Total", "MALARIA_PV_"
        elif indicador == "malaria_f":
            disease, sexo, edad, prefix = "MALARIA", "F", "Total", "MALARIA_F_"
        elif indicador == "malaria_m":
            disease, sexo, edad, prefix = "MALARIA", "M", "Total", "MALARIA_M_"
        else:
            disease, sexo, edad, prefix = "DENGUE", "Total", "Total", "DENGUE_"
            
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, mes, casos AS valor FROM fact_disease WHERE nivel_geo = ? AND enfermedad = ? AND sexo = ? AND grupo_edad = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, disease, sexo, edad, anio_min, anio_max),
        )
        result = temporal_monthly_response(df, prefix, conn, anio_min, anio_max, nivel=nivel)
    elif base == "censo":
        df = pd.read_sql_query(
            "SELECT ubigeo, valor FROM fact_census WHERE nivel_geo = ? AND variable = ?",
            conn, params=(nivel, indicador),
        )
        df = with_names(df, conn, nivel=nivel).rename(columns={"valor": indicador}).fillna(0)
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    elif base == "endes":
        # Supports: vac_<vacuna>_<dosis>_<metric> or anemia_<metric>
        # metrics: p, low_ci, high_ci, n
        if indicador.startswith("anemia_"):
            metric = indicador.replace("anemia_", "")
            vacuna, dosis = "ANEMIA", "Total"
            prefix_label = f"ANEMIA_{metric.upper()}_"
        else:
            # e.g. vac_influenza_1d_low_ci
            clean = indicador.replace("vac_", "")
            parts = clean.split("_")
            vacuna = parts[0].upper()
            dosis = parts[1].upper() if len(parts) >= 2 else "1D"
            metric = "_".join(parts[2:]) if len(parts) >= 3 else "p"
            prefix_label = f"VAC_{vacuna}_{dosis}_{metric.upper()}_"

        col_sql = {
            "p": "proporcion * 100",
            "low_ci": "low_ci_95 * 100",
            "high_ci": "high_ci_95 * 100",
            "n": "casos_n",
        }.get(metric, "proporcion * 100")

        df = pd.read_sql_query(
            f"SELECT ubigeo, anio, {col_sql} AS valor FROM fact_endes_vacuna WHERE vacuna = ? AND dosis = ? AND respuesta = 'Yes' AND anio BETWEEN ? AND ?",
            conn, params=(vacuna, dosis, anio_min, anio_max),
        )
        result = temporal_response(df, prefix_label, conn, nivel=nivel)
    elif base == "endes_vivienda":
        # Mapping for vivienda metrics (p, low_ci, high_ci, n)
        # Category -> column prefix in dim_endes_vivienda
        vivienda_map = {
            "pared_noble": "EXTERIOR_WALL_MATERIAL_EXTERIOR_WALL_WELL_CONSTRUCTED",
            "pared_rustica": "EXTERIOR_WALL_MATERIAL_EXTERIOR_WALL_RUSTIC",
            "pared_natural": "EXTERIOR_WALL_MATERIAL_EXTERIOR_WALL_NATURAL",
            "piso_acabado": "FLOOR_MATERIAL_FINISHED_FLOOR",
            "piso_tierra": "FLOOR_MATERIAL_NATURAL_FLOOR",
            "piso_rustico": "FLOOR_MATERIAL_RUSTIC_FLORR",
            "agua_red_publica": "WATER_SOURCE_PUBLIC_WATER_NETWORK",
            "agua_pozo": "WATER_SOURCE_WELL_WATER",
            "agua_superficial": "WATER_SOURCE_SURFACE_WATER",
            "otra_fuente_agua": "WATER_SOURCE_WATER_OTHER_SOURCE",
            "desague_alcantarillado": "SANITARY_FACILITY_TOILET_CONNECTED_TO_PUBLIC_SEWER_SYSTEM",
            "letrina_pozo": "SANITARY_FACILITY_PIT_LATRINE",
            "sin_servicio_higienico": "SANITARY_FACILITY_NO_SERVICE_SANITARY_FACILITY",
            "otro_servicio_higienico": "SANITARY_FACILITY_SANITARY_FACILITY_OTHER",
        }
        
        # Determine cat and metric
        cat = None
        metric = "p"
        for k in vivienda_map:
            if indicador.startswith(k):
                cat = k
                metric = indicador.replace(k, "").strip("_")
                break
        if not cat:
            cat = "piso_acabado"
            metric = "p"

        suffix = {
            "p": "P_2023",
            "low_ci": "LOW_CI_95_2023",
            "high_ci": "HIGH_CI_95_2023",
            "n": "N_2023"
        }.get(metric, "P_2023")

        col_name = f"{vivienda_map[cat]}_{suffix}"
        df = pd.read_sql_query(f"SELECT ubigeo, {col_name} AS valor FROM dim_endes_vivienda", conn)
        df = with_names(df, conn, nivel=nivel).rename(columns={"valor": indicador.upper()}).fillna(0)
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    elif base == "endes_sifilis":
        df = pd.read_sql_query("SELECT * FROM fact_endes_sifilis", conn)
        df = with_names(df, conn, nivel=nivel)
        all_year_cols = [c for c in df.columns if c.startswith("ENDES_SIFILIS_N_")]
        selected_cols = []
        for c in all_year_cols:
            try:
                y = int(c.split("_")[-1])
                if anio_min <= y <= anio_max:
                    selected_cols.append(c)
            except ValueError:
                selected_cols.append(c)
        if not selected_cols:
            selected_cols = all_year_cols
        cols = ["ubigeo", "nombre"] + selected_cols
        result = jsonify({"columns": cols, "rows": df[cols].fillna(0).to_dict(orient="records")})
    else:
        column = indicador
        if column not in {"primary_hcf", "secondary_hcf", "tertiary_hcf"}:
            conn.close()
            return jsonify({"error": "Indicador no válido"}), 400
        df = pd.read_sql_query(
            f"SELECT ubigeo, {column} AS valor FROM dim_travel_time WHERE nivel_geo = ?",
            conn, params=(nivel,),
        )
        df = with_names(df, conn, nivel=nivel).rename(columns={"valor": column.upper()}).fillna(0)
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    conn.close()
    return result

@app.route("/api/geojson/<nivel>")
def get_geojson(nivel):
    nivel = nivel.lower()
    if nivel in GEOJSON_CACHE:
        return app.response_class(GEOJSON_CACHE[nivel], mimetype="application/json")
    if gpd is None:
        return jsonify({"type": "FeatureCollection", "features": []})
    zip_name = {"departamento": "Departamentos.zip", "provincia": "Provincias.zip", "distrito": "Distritos.zip"}.get(nivel)
    if not zip_name:
        return jsonify({"error": "Nivel no válido"}), 400
    zip_path = SHAPEFILE_DIR / zip_name
    if not zip_path.exists():
        return jsonify({"type": "FeatureCollection", "features": []})
    try:
        gdf = gpd.read_file(f"zip://{zip_path}")
        columns = {column.upper(): column for column in gdf.columns}
        if "CCDD" not in columns:
            return jsonify({"type": "FeatureCollection", "features": []})
        cdd = gdf[columns["CCDD"]].astype(str).str.split(".").str[0].str.zfill(2)
        if nivel == "departamento":
            gdf["ubigeo"] = cdd.map(lambda value: str(int(value) * 10000))
        elif nivel == "provincia" and "CCPP" in columns:
            cpp = gdf[columns["CCPP"]].astype(str).str.split(".").str[0].str.zfill(2)
            gdf["ubigeo"] = [str(int(department) * 10000 + int(province) * 100) for department, province in zip(cdd, cpp)]
        elif nivel == "distrito" and "UBIGEO" in columns:
            gdf["ubigeo"] = gdf[columns["UBIGEO"]].astype(str).str.split(".").str[0].str.zfill(6)
        else:
            return jsonify({"type": "FeatureCollection", "features": []})
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        gdf["geometry"] = gdf.geometry.simplify(0.005, preserve_topology=True)
        geojson = gdf[["ubigeo", "geometry"]].to_json()
        GEOJSON_CACHE[nivel] = geojson
        return app.response_class(geojson, mimetype="application/json")
    except Exception:
        return jsonify({"type": "FeatureCollection", "features": []})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
