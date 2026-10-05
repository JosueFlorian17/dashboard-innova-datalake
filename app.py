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

# Ahora busca dinámicamente la carpeta "shapefiles" en el mismo directorio de app.py
SHAPEFILE_DIR = Path(os.getenv("SHAPEFILE_DIR", BASE_DIR / "shapefiles"))

app = Flask(__name__, static_folder=str(BASE_DIR))
GEOJSON_CACHE = {}

CATALOG = {
    "mortalidad": {
        "label": "Mortalidad (SINADEF)",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": True,
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
        "tiene_anios": False,
        "indicadores": [
            {"id": "dengue_total", "label": "Dengue - Casos Acumulados"},
            {"id": "malaria_total", "label": "Malaria - Casos Acumulados"},
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
            {"id": "NO_EDUCATION_NOR_EMPLOYMENT", "label": "Población NINI (No estudia ni trabaja) (%)"},
            {"id": "NO_EDUCATION_NOR_EMPLOYMENT_F", "label": "Población NINI - Mujeres (%)"},
            {"id": "NO_EDUCATION_NOR_EMPLOYMENT_M", "label": "Población NINI - Hombres (%)"},
            {"id": "SCHOOL_ATTENDANCE_15_17", "label": "Asistencia Escolar 15-17 años Total (%)"},
            {"id": "SCHOOL_ATTENDANCE_15_17_F", "label": "Asistencia Escolar 15-17 - Mujeres (%)"},
            {"id": "SCHOOL_ATTENDANCE_15_17_M", "label": "Asistencia Escolar 15-17 - Hombres (%)"},
            {"id": "EDUCATION_PRIMARY_COMPLETED", "label": "Primaria Completa (%)"},
            {"id": "EDUCATION_SECONDARY_COMPLETED", "label": "Secundaria Completa (%)"},
            {"id": "EDUCATION_UNIVERSITY_COMPLETED", "label": "Superior Universitaria Completa (%)"},
            {"id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED", "label": "Ratio Educativo Mujer/Hombre"},
            {"id": "POP_CENSADA_REDATAM", "label": "Población Censada (Redatam)"},
            {"id": "POP_TOTAL_REDATAM", "label": "Población Total Estimada (Redatam)"},
        ],
    },
    "endes": {
        "label": "ENDES - Vacunación Infantil",
        "niveles": ["departamento"],
        "tiene_anios": True,
        "min_anio": 2020,
        "max_anio": 2023,
        "indicadores": [
            {"id": "vac_influenza_p", "label": "Vacuna Influenza (1ª Dosis %)"},
            {"id": "vac_influenza_2d_p", "label": "Vacuna Influenza (2ª Dosis %)"},
            {"id": "vac_rotavirus_p", "label": "Vacuna Rotavirus (1ª Dosis %)"},
            {"id": "vac_rotavirus_2d_p", "label": "Vacuna Rotavirus (2ª Dosis %)"},
            {"id": "vac_neumococo_p", "label": "Vacuna Neumococo (1ª Dosis %)"},
            {"id": "vac_neumococo_2d_p", "label": "Vacuna Neumococo (2ª Dosis %)"},
            {"id": "vac_neumococo_3d_p", "label": "Vacuna Neumococo (3ª Dosis %)"},
            {"id": "vac_pentavalente_p", "label": "Vacuna Pentavalente (1ª Dosis %)"},
            {"id": "vac_pentavalente_2d_p", "label": "Vacuna Pentavalente (2ª Dosis %)"},
            {"id": "vac_pentavalente_3d_p", "label": "Vacuna Pentavalente (3ª Dosis %)"},
        ],
    },
    "endes_vivienda": {
        "label": "ENDES - Vivienda y Saneamiento",
        "niveles": ["departamento"],
        "tiene_anios": False,
        "indicadores": [
            {"id": "pared_noble", "label": "Paredes de Material Noble (%)"},
            {"id": "pared_rustica", "label": "Paredes de Material Rústico (%)"},
            {"id": "pared_natural", "label": "Paredes de Material Natural (%)"},
            {"id": "piso_acabado", "label": "Pisos Acabados (Cerámica/Cemento) (%)"},
            {"id": "piso_tierra", "label": "Pisos de Tierra / Natural (%)"},
            {"id": "piso_rustico", "label": "Pisos Rústicos (%)"},
            {"id": "agua_red_publica", "label": "Conexión a Red Pública de Agua (%)"},
            {"id": "agua_pozo", "label": "Abastecimiento por Pozo (%)"},
            {"id": "agua_superficial", "label": "Agua de Río / Manantial (%)"},
            {"id": "desague_alcantarillado", "label": "Conexión a Red de Alcantarillado (%)"},
            {"id": "letrina_pozo", "label": "Letrina / Pozo Ciego (%)"},
            {"id": "sin_servicio_higienico", "label": "Sin Servicio Higiénico (%)"},
        ],
    },
    "endes_sifilis": {
        "label": "ENDES - Sífilis en Gestantes",
        "niveles": ["departamento"],
        "tiene_anios": True,
        "min_anio": 2010,
        "max_anio": 2022,
        "indicadores": [
            {"id": "sifilis_gestantes", "label": "Casos de Sífilis en Gestantes (2010-2022)"},
        ],
    },
    "travel_time": {
        "label": "Infraestructura - Tiempos de Viaje",
        "niveles": ["departamento", "provincia", "distrito"],
        "tiene_anios": False,
        "indicadores": [
            {"id": "primary_hcf", "label": "Minutos a Centro Salud Nivel 1"},
            {"id": "secondary_hcf", "label": "Minutos a Centro Salud Nivel 2"},
            {"id": "tertiary_hcf", "label": "Minutos a Hospital Nivel 3"},
        ],
    },
}

INVENTORY = [
    # 1. Población Proyectada (INEI)
    {
        "id": "POP_YYYY",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Total",
        "descripcion": "Total de la población en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_F",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Femenina",
        "descripcion": "Población femenina total en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_M",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Masculina",
        "descripcion": "Población masculina total en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_F_0_50",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Femenina (0 a 50 años)",
        "descripcion": "Población femenina entre 0 y 50 años en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_F_>50",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Femenina (>50 años)",
        "descripcion": "Población femenina mayor de 50 años en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_M_0_50",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Masculina (0 a 50 años)",
        "descripcion": "Población masculina entre 0 y 50 años en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_M_>50",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Masculina (>50 años)",
        "descripcion": "Población masculina mayor de 50 años en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_<1",
        "base_key": "poblacion",
        "grupo": "Población Proyectada",
        "indicador": "Población Estimada <1 año",
        "descripcion": "Poblacion objetivo estimada de personas de hasta 1 año en YYYY: poblacion proyectada multiplicada por la proporcion censal de hasta 1 año.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },

    # 2. Clima y Ambiente (SENAMHI / Satelital)
    {
        "id": "T_PROM_YYYY",
        "base_key": "clima",
        "grupo": "Clima",
        "indicador": "Temperatura Promedio Anual",
        "descripcion": "Temperatura promedio registrada en el año YYYY.",
        "resolucion_temporal": "1990-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SENAMHI / NASA MODIS",
        "unidad": "°C",
    },
    {
        "id": "PREC_PROM_YYYY",
        "base_key": "clima",
        "grupo": "Clima",
        "indicador": "Precipitación Promedio Anual",
        "descripcion": "Precipitación promedio registrada en el año YYYY.",
        "resolucion_temporal": "1990-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SENAMHI / CHIRPS",
        "unidad": "mm/año",
    },
    {
        "id": "PM2_5_PROM_YYYY",
        "base_key": "clima",
        "grupo": "Clima",
        "indicador": "Material Particulado PM2.5",
        "descripcion": "Nivel promedio de material particulado PM2.5 registrado en el año YYYY.",
        "resolucion_temporal": "1990-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "NASA / SEDAC / Venter et al.",
        "unidad": "µg/m³",
    },
    {
        "id": "NO2_PROM_YYYY",
        "base_key": "clima",
        "grupo": "Clima",
        "indicador": "Dióxido de Nitrógeno (NO2)",
        "descripcion": "Nivel promedio de dióxido de nitrógeno (NO2) registrado en el año YYYY.",
        "resolucion_temporal": "1990-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "ESA Sentinel-5P / TROPOMI",
        "unidad": "µmol/m²",
    },

    # 3. Salud y Epidemiología (MINSA / CDC / SINADEF)
    {
        "id": "DEATHS_YYYY",
        "base_key": "mortalidad",
        "grupo": "Salud",
        "indicador": "Mortalidad Total",
        "descripcion": "Número total de muertes en el año indicado.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DEATHS_YYYY_SEX",
        "base_key": "mortalidad",
        "grupo": "Salud",
        "indicador": "Mortalidad por Sexo",
        "descripcion": "Número total de muertes en el año indicado, desagregado por sexo.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DEATHS_YYYY_TIER1_COM_MAT",
        "base_key": "mortalidad",
        "grupo": "Salud",
        "indicador": "Muertes Comunicables, Maternas y Nutricionales",
        "descripcion": "Número total de muertes comunicables, maternas, perinatales y nutricionales en el año indicado.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DEATHS_YYYY_TIER1_INJURIES",
        "base_key": "mortalidad",
        "grupo": "Salud",
        "indicador": "Muertes por Injurias",
        "descripcion": "Número total de muertes por injurias en el año indicado.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DEATHS_YYYY_TIER1_NCD",
        "base_key": "mortalidad",
        "grupo": "Salud",
        "indicador": "Muertes por Enfermedades No Transmisibles",
        "descripcion": "Número total de muertes por enfermedades no comunicables en el año indicado.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DENGUE_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Dengue",
        "descripcion": "Total de casos de dengue en el año YYYY.",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "LEISHMANIOSIS_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Leishmaniosis",
        "descripcion": "Total de casos de leishmaniosis registrados en el año YYYY.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "LEPTOSPIROSIS_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Leptospirosis",
        "descripcion": "Total de casos de leptospirosis registrados en el año YYYY.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Malaria Total",
        "descripcion": "Total de casos de malaria en el año.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_PF_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Malaria Plasmodium falciparum",
        "descripcion": "Total de casos de malaria por Plasmodium falciparum en el año.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_PV_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Malaria Plasmodium vivax",
        "descripcion": "Total de casos de malaria por Plasmodium vivax en el año.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "ZIKA_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Zika",
        "descripcion": "Total de casos de zika registrados en el año YYYY.",
        "resolucion_temporal": "2016-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "CHIKUNGUNYA_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Chikungunya",
        "descripcion": "Total de casos de chikungunya registrados en el año YYYY.",
        "resolucion_temporal": "2015-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "SIFILIS_CASES_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Sífilis",
        "descripcion": "Total de casos de sifilis en el año YYYY.",
        "resolucion_temporal": "2010-2022",
        "resolucion_espacial": ["Departamento"],
        "fuente": "MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "NACIMIENTOS_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Nacimientos",
        "descripcion": "Número total de nacimientos en el año indicado.",
        "resolucion_temporal": "2014-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINSA / RENIEC",
        "unidad": "Nacimientos",
    },
    {
        "id": "ESQUISTOSOMIASIS_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Esquistosomiasis",
        "descripcion": "Total de casos de esquistosomiasis registrados en el año YYYY.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINSA / REUNIS",
        "unidad": "Casos Notificados",
    },
    {
        "id": "VACUNADOS_[ENFERMEDAD]_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Personas Vacunadas",
        "descripcion": "Total de personas vacunadas registradas en el año YYYY.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINSA",
        "unidad": "Personas Vacunadas",
    },
    {
        "id": "CANCER_YYYY",
        "base_key": "salud_vectores",
        "grupo": "Salud",
        "indicador": "Casos de Cáncer",
        "descripcion": "Total de casos nuevos de cáncer registrados en el año YYYY.",
        "resolucion_temporal": "2000-2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINSA",
        "unidad": "Casos Registrados",
    },

    # 4. ENDES (Encuesta Demográfica y de Salud Familiar)
    {
        "id": "ENDES_POP_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Población ENDES",
        "descripcion": "Población total por unidad de análisis",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Habitantes",
    },
    {
        "id": "HH_PIPED_WATER_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Agua Potable Fuera de Vivienda (%)",
        "descripcion": "Proporción de hogares con agua potable entubada fuera de la vivienda, pero dentro del edificio.",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_PIPED_WATER_INSIDE_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Agua Potable Dentro de Vivienda (%)",
        "descripcion": "Proporción de hogares con agua potable entubada dentro de la vivienda.",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_WATER_PUBLIC_NETWORK_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Conexión a Red Pública de Agua (%)",
        "descripcion": "Proporción de hogares con conexión a una red pública de agua.",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_SEWAGE_CONNECTED_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Conexión a Alcantarillado (%)",
        "descripcion": "Proporción de hogares con conexión a algún sistema de alcantarillado.",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_PUBLIC_SEWAGE_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Red Pública de Alcantarillado (%)",
        "descripcion": "Proporción de hogares con conexión a una red pública de alcantarillado.",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_MASONRY_WALLS_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Paredes de Material Noble (%)",
        "descripcion": "Proporción de hogares con paredes de material noble (albañilería).",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_FINISHED_FLOORS_YYYY_Yes_percent",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Pisos Acabados (%)",
        "descripcion": "Proporción de hogares con pisos acabados (cemento pulido, cerámica, madera fina, etc.).",
        "resolucion_temporal": "2019-2021",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_INFLUENZA_1D_YYYY_Yes_P",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Vacunación Influenza 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna contra influenza en el año YYYY.",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_PENTAVALENTE_1D_YYYY_Yes_P",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Vacunación Pentavalente 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna pentavalente en el año YYYY.",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_NEUMOCOCO_1D_YYYY_Yes_P",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Vacunación Neumococo 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna neumocócica en el año YYYY.",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_ROTAVIRUS_1D_YYYY_Yes_P",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Vacunación Rotavirus 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna contra rotavirus en el año YYYY.",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_ANEMIA_YYYY_Yes_P",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Prevalencia de Anemia (%)",
        "descripcion": "Proporción de personas que SÍ presentaron anemia en el año YYYY.",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_HTA_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Hipertensión Arterial (%)",
        "descripcion": "Proporción de población con hipertension",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_DM2_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Diabetes Mellitus (%)",
        "descripcion": "Proporción de población con diabetes mellitus",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_DEPRESION_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Depresión (%)",
        "descripcion": "Proporción de población con depresión",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_ANSIEDAD_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Ansiedad (%)",
        "descripcion": "Proporción de población con ansiedad",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_SOBREPRESO_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Sobrepeso (%)",
        "descripcion": "Proporción de población con sobrepeso",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_OBESIDAD_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Obesidad (%)",
        "descripcion": "Proporción de población con obesidad",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_SIND_METABOLICO_YYYY",
        "base_key": "endes",
        "grupo": "ENDES",
        "indicador": "Síndrome Metabólico (%)",
        "descripcion": "Proporción de población con sindrome metabólico",
        "resolucion_temporal": "2020-2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },

    # 5. CENSO (Censo Nacional de Población y Vivienda)
    {
        "id": "UNEMPLOYMENT_RATE",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Tasa de Desempleo (%)",
        "descripcion": "Tasa de desempleo entre la población total de 15 años o más en la fuerza laboral.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "LABOR_FORCE_PARTICIPATION",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Participación en Fuerza Laboral (%)",
        "descripcion": "Tasa de participación en la fuerza laboral de la población total de 15 años o más.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "SCHOOL_ATTENDANCE_15_17",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Asistencia Escolar 15-17 años (%)",
        "descripcion": "Proporción de la población de 15 a 17 años que asiste a la escuela.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_PRIMARY_COMPLETED_YYYY",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Primaria Completa (%)",
        "descripcion": "Proporción de la población de 25 años o más que completó la educación primaria o superior.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_SECONDARY_COMPLETED",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Secundaria Completa (%)",
        "descripcion": "Proporción de la población de 25 años o más que completó la educación secundaria o superior.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_UNIVERSITY_COMPLETED",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Superior Universitaria Completa (%)",
        "descripcion": "Proporción de la población de 25 años o más que completó la educación universitaria o superior.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Ratio Educativo Mujer/Hombre",
        "descripcion": "Relación entre la proporción de mujeres y hombres de 25 años o más que completaron la educación secundaria o superior.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Ratio",
    },
    {
        "id": "NO_EDUCATION_NOR_EMPLOYMENT_YYYY",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población NINI (%)",
        "descripcion": "Proporción de la población de 15 años a 24 años que no estudia ni trabaja",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "LOCATION_RESIDENCIA_PERMANENTE_prop_interno",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Residencia Permanente en Mismo Dpto (%)",
        "descripcion": "Proporción de personas cuya residencia permanente actual coincide con el departamento de su domicilio registrado.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "LOCATION_RESIDENCIA_CENTRO_LABORAL_prop_interno",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Centro Laboral en Mismo Dpto (%)",
        "descripcion": "Proporción de personas cuyo centro laboral se sitúa en el mismo departamento que su domicilio registrado.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "LOCATION_RESIDENCIA_HACE_5Y_prop_interno",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Residencia Hace 5 Años en Mismo Dpto (%)",
        "descripcion": "Proporción de personas cuya residencia hace cinco años coincidía con el departamento de su domicilio actual.",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "P_URBANO_area",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población Urbana (%)",
        "descripcion": "Proporción de residencia urbana (area)",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "P_RURAL_area",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población Rural (%)",
        "descripcion": "Proporción de residencia rural (area)",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "P_POB_ASEGURADA_SIS",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población Afiliada al SIS (%)",
        "descripcion": "Proporción de población afiliada al SIS",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "P_POB_ASEGURADA_ESSALUD",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población Afiliada a EsSalud (%)",
        "descripcion": "Proporción de población afiliada a EsSalud",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "P_POB_SIN_SEGURO",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población Sin Seguro (%)",
        "descripcion": "Proporción de población sin afiliación a ningún seguro",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },
    {
        "id": "P_POB_SABE_LEER",
        "base_key": "censo",
        "grupo": "CENSO",
        "indicador": "Población que Sabe Leer (%)",
        "descripcion": "Proporción de población que sabe leer y escribir",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Proporción",
    },

    # 6. Misceláneo (Tiempo de Viaje, IDH, Pobreza)
    {
        "id": "TIEMPO_VIAJE_CCPP_PRIMARY",
        "base_key": "travel_time",
        "grupo": "Misceláneo",
        "indicador": "Tiempo a CCSS Nivel 1 (min)",
        "descripcion": "Promedio de tiempo de viaje de los CCPP de ese distrito a su CCSS de primer nivel mas cercano",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SUSALUD / OSM (Modelo Friccional)",
        "unidad": "Minutos",
    },
    {
        "id": "TIEMPO_VIAJE_CCPP_SECONDARY",
        "base_key": "travel_time",
        "grupo": "Misceláneo",
        "indicador": "Tiempo a CCSS Nivel 2 (min)",
        "descripcion": "Promedio de tiempo de viaje de los CCPP de ese distrito a su CCSS de segundo nivel mas cercano",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SUSALUD / OSM",
        "unidad": "Minutos",
    },
    {
        "id": "TIEMPO_VIAJE_CCPP_TERTIARY",
        "base_key": "travel_time",
        "grupo": "Misceláneo",
        "indicador": "Tiempo a Hospital Nivel 3 (min)",
        "descripcion": "Promedio de tiempo de viaje de los CCPP de ese distrito a su CCSS de tercer nivel mas cercano",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SUSALUD / OSM",
        "unidad": "Minutos",
    },
    {
        "id": "INDICE_DESARROLLO_HUMANO_YYYY",
        "base_key": "miscelaneo",
        "grupo": "Misceláneo",
        "indicador": "Índice de Desarrollo Humano (IDH)",
        "descripcion": "Indice de desarrollo humano",
        "resolucion_temporal": "2017 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "PNUD / INEI",
        "unidad": "Índice (0-1)",
    },
    {
        "id": "INDICE_DESARROLLO_HUMANO_AJUSTADO_YYYY",
        "base_key": "miscelaneo",
        "grupo": "Misceláneo",
        "indicador": "IDH Ajustado por Desigualdad",
        "descripcion": "Indice de desarrollo humano ajustado por distrito",
        "resolucion_temporal": "2017 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "PNUD / INEI",
        "unidad": "Índice (0-1)",
    },
    {
        "id": "NECESIDADES_BASICAS_INSATISFECHAS_1_YYYY",
        "base_key": "miscelaneo",
        "grupo": "Misceláneo",
        "indicador": "NBI: Al Menos 1 Necesidad (%)",
        "descripcion": "Proporción de la población  con al menos una necesidad basica insatisfecha",
        "resolucion_temporal": "1993, 2007, 2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "POBREZA MONETARIA",
        "base_key": "miscelaneo",
        "grupo": "Misceláneo",
        "indicador": "Pobreza Monetaria (%)",
        "descripcion": "Proporción de la población en pobreza para el año XXXX",
        "resolucion_temporal": "2018",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ESPERANZA DE VIDA_YYYY-YYYY",
        "base_key": "miscelaneo",
        "grupo": "Misceláneo",
        "indicador": "Esperanza de Vida al Nacer",
        "descripcion": "Esperanza de vida en rango de años",
        "resolucion_temporal": "2000-2020",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI / MINSA",
        "unidad": "Años",
    },

    # 7. Datos Abiertos (Educación / Docentes / Lectura / Ambiente)
    {
        "id": "DOCENTES_TOTAL",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Total de Docentes en IE Públicas",
        "descripcion": "Total de docentes en instituciones educativas públicas.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "DOCENTES_HOMBRES",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Docentes Hombres",
        "descripcion": "Total de docentes hombres en IE públicas.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "DOCENTES_MUJERES",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Docentes Mujeres",
        "descripcion": "Total de docentes mujeres en IE públicas.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "DOCENTES_NOMBRADOS",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Docentes Nombrados",
        "descripcion": "Total de docentes nombrados.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "DOCENTES_CONTRATADOS",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Docentes Contratados",
        "descripcion": "Total de docentes contratados.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "DOCENTES_CON_TITULO",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Docentes con Título",
        "descripcion": "Docentes que cuentan con título profesional.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "DOCENTES_SIN_TITULO",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Docentes sin Título",
        "descripcion": "Docentes que no cuentan con título profesional.",
        "resolucion_temporal": "2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINEDU - Datos Abiertos",
        "unidad": "Docentes",
    },
    {
        "id": "AREA_VERDE",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Área Verde Total",
        "descripcion": "Área verde total",
        "resolucion_temporal": "Estático",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINAM - Datos Abiertos",
        "unidad": "m²",
    },
    {
        "id": "SIN_ALUMBRADO_ELECTRICO",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Sin Alumbrado Eléctrico (%)",
        "descripcion": "Proporción de personas que no cuentan alumbrado electrico",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "P_ASMA",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Prevalencia de Asma (%)",
        "descripcion": "Proporción de personas que tienen asma",
        "resolucion_temporal": "2017",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "MINSA",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "LITERACY_SPANISH",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Alfabetismo en Castellano (%)",
        "descripcion": "Proporción de personas que saben leer y escribir en castellano",
        "resolucion_temporal": "2022",
        "resolucion_espacial": ["Departamento"],
        "fuente": "Encuesta Nacional de Lectura / INEI",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "READ_LAST_12M",
        "base_key": "datos_abiertos",
        "grupo": "Datos Abiertos",
        "indicador": "Lectura en Últimos 12 Meses (%)",
        "descripcion": "Proporción de personas que han leído algún contenido impreso o digital en los últimos 12 meses",
        "resolucion_temporal": "2022",
        "resolucion_espacial": ["Departamento"],
        "fuente": "Encuesta Nacional de Lectura / INEI",
        "unidad": "Porcentaje (%)",
    },

    # 8. VACUNAS (Inmunizaciones MINSA)
    {
        "id": "YYYY_AMA",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Fiebre Amarilla",
        "descripcion": "Número de dosis aplicadas de vacuna contra la fiebre amarilla en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_BCG",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna BCG",
        "descripcion": "Número de dosis aplicadas de vacuna BCG en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_DPT_1_GRADO_REFUERZO",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna DPT (1er Refuerzo)",
        "descripcion": "Número de primeros refuerzos aplicados de vacuna DPT en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_HVA",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Hepatitis A",
        "descripcion": "Número de dosis aplicadas de vacuna contra la hepatitis A en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_HVB",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Hepatitis B",
        "descripcion": "Número de dosis aplicadas de vacuna contra la hepatitis B en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_INFLUENZA_1_GRADO_DOSIS",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Influenza (1ª Dosis)",
        "descripcion": "Número de primeras dosis aplicadas de vacuna contra la influenza en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_NEUMO_1_GRADO_DOSIS",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Neumococo (1ª Dosis)",
        "descripcion": "Número de primeras dosis aplicadas de vacuna antineumocócica en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_PENTA_1_GRADO_DOSIS",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Pentavalente (1ª Dosis)",
        "descripcion": "Número de primeras dosis aplicadas de vacuna pentavalente en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_POLIO_1_GRADO_DOSIS",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Polio (1ª Dosis)",
        "descripcion": "Número de primeras dosis aplicadas de vacuna contra la poliomielitis en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_ROTAVIRUS_1_GRADO_DOSIS",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Rotavirus (1ª Dosis)",
        "descripcion": "Número de primeras dosis aplicadas de vacuna contra el rotavirus en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_SPR_1_GRADO_DOSIS",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna SPR (1ª Dosis)",
        "descripcion": "Número de primeras dosis aplicadas de vacuna SPR en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_TDAP",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Tdap",
        "descripcion": "Número de dosis aplicadas de vacuna Tdap en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_VARICELA",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna Varicela",
        "descripcion": "Número de dosis aplicadas de vacuna contra la varicela en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
    {
        "id": "YYYY_VPH_DOSIS_UNICA",
        "base_key": "vacunas",
        "grupo": "VACUNAS",
        "indicador": "Vacuna VPH (Dosis Única)",
        "descripcion": "Número de dosis únicas aplicadas de vacuna contra el VPH en el año YYYY",
        "resolucion_temporal": "2000-2025",
        "resolucion_espacial": ["Distrito"],
        "fuente": "MINSA - HIS / REUNIS",
        "unidad": "Dosis Aplicadas",
    },
]

def get_db():
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

def with_names(df, conn):
    if df.empty or "ubigeo" not in df.columns:
        return df
    names = pd.read_sql_query(
        "SELECT ubigeo, nombre FROM dim_geografia",
        conn,
    )
    return df.merge(names, on="ubigeo", how="left")

def temporal_response(df, prefix, conn):
    if df.empty:
        return jsonify({"columns": ["ubigeo", "nombre"], "rows": []})
    df = with_names(df, conn)
    df = df.pivot_table(
        index=["ubigeo", "nombre"],
        columns="anio",
        values="valor",
        aggfunc="mean",
    ).reset_index()
    df.columns = [f"{prefix}{column}" if isinstance(column, int) else column for column in df.columns]
    df = df.fillna("")
    return jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})

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
            "SELECT ubigeo, anio, defunciones AS valor FROM fact_mortality WHERE nivel_geo = ? AND mes = 'Total' AND sexo = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, sexo, anio_min, anio_max),
        )
        result = temporal_response(df, "DEATHS_", conn)
    elif base == "poblacion":
        sexo = "F" if indicador == "poblacion_f" else "M" if indicador == "poblacion_m" else "Total"
        grupo = "0-50" if indicador == "poblacion_0_50" else ">50" if indicador == "poblacion_mayor_50" else "Total"
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, poblacion AS valor FROM fact_population WHERE nivel_geo = ? AND sexo = ? AND grupo_edad = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, sexo, grupo, anio_min, anio_max),
        )
        result = temporal_response(df, "POP_", conn)
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
        result = temporal_response(df, prefix, conn)
    elif base == "salud_vectores":
        disease = "DENGUE" if indicador == "dengue_total" else "MALARIA"
        df = pd.read_sql_query(
            "SELECT ubigeo, SUM(casos) AS valor FROM fact_disease WHERE nivel_geo = ? AND enfermedad = ? GROUP BY ubigeo",
            conn, params=(nivel, disease),
        )
        df = with_names(df, conn).rename(columns={"valor": f"CASOS_{disease}_TOTAL"}).fillna("")
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    elif base == "censo":
        df = pd.read_sql_query(
            "SELECT ubigeo, valor FROM fact_census WHERE nivel_geo = ? AND variable = ?",
            conn, params=(nivel, indicador),
        )
        df = with_names(df, conn).rename(columns={"valor": indicador}).fillna("")
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    elif base == "endes":
        parts = indicador.split("_")
        vaccine = parts[1].upper()
        dose = parts[2].upper() if len(parts) >= 3 and parts[2].upper() in ("1D", "2D", "3D") else "1D"
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, proporcion * 100 AS valor FROM fact_endes_vacuna WHERE vacuna = ? AND dosis = ? AND respuesta = 'Yes' AND anio BETWEEN ? AND ?",
            conn, params=(vaccine, dose, anio_min, anio_max),
        )
        result = temporal_response(df, f"VAC_{vaccine}_{dose}_", conn)
    elif base == "endes_vivienda":
        col_map = {
            "pared_noble": "EXTERIOR_WALL_MATERIAL_EXTERIOR_WALL_WELL_CONSTRUCTED_P_2023",
            "pared_rustica": "EXTERIOR_WALL_MATERIAL_EXTERIOR_WALL_RUSTIC_P_2023",
            "pared_natural": "EXTERIOR_WALL_MATERIAL_EXTERIOR_WALL_NATURAL_P_2023",
            "piso_acabado": "FLOOR_MATERIAL_FINISHED_FLOOR_P_2023",
            "piso_tierra": "FLOOR_MATERIAL_NATURAL_FLOOR_P_2023",
            "piso_rustico": "FLOOR_MATERIAL_RUSTIC_FLORR_P_2023",
            "agua_red_publica": "WATER_SOURCE_PUBLIC_WATER_NETWORK_P_2023",
            "agua_pozo": "WATER_SOURCE_WELL_WATER_P_2023",
            "agua_superficial": "WATER_SOURCE_SURFACE_WATER_P_2023",
            "desague_alcantarillado": "SANITARY_FACILITY_TOILET_CONNECTED_TO_PUBLIC_SEWER_SYSTEM_P_2023",
            "letrina_pozo": "SANITARY_FACILITY_PIT_LATRINE_P_2023",
            "sin_servicio_higienico": "SANITARY_FACILITY_NO_SERVICE_SANITARY_FACILITY_P_2023",
        }
        col = col_map.get(indicador, "FLOOR_MATERIAL_FINISHED_FLOOR_P_2023")
        df = pd.read_sql_query(f"SELECT ubigeo, {col} AS valor FROM dim_endes_vivienda", conn)
        df = with_names(df, conn).rename(columns={"valor": indicador.upper()}).fillna("")
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    elif base == "endes_sifilis":
        df = pd.read_sql_query("SELECT * FROM fact_endes_sifilis", conn)
        df = with_names(df, conn)
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
        result = jsonify({"columns": cols, "rows": df[cols].fillna("").to_dict(orient="records")})
    else:
        column = indicador
        if column not in {"primary_hcf", "secondary_hcf", "tertiary_hcf"}:
            conn.close()
            return jsonify({"error": "Indicador no válido"}), 400
        df = pd.read_sql_query(
            f"SELECT ubigeo, {column} AS valor FROM dim_travel_time WHERE nivel_geo = ?",
            conn, params=(nivel,),
        )
        df = with_names(df, conn).rename(columns={"valor": column.upper()}).fillna("")
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    conn.close()
    return result

# --- AQUÍ ESTABA EL ERROR: AGREGADO EL
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