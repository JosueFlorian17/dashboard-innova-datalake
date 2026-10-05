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
    # 1. POBLACIÓN PROYECTADA (INEI)
    {
        "id": "POP_YYYY",
        "base_key": "poblacion",
        "indicador_id": "poblacion_total",
        "grupo": "Población Proyectada",
        "indicador": "Población Total (Ambos Sexos)",
        "descripcion": "Total de la población en el año YYYY.",
        "resolucion_temporal": "2000 - 2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_F",
        "base_key": "poblacion",
        "indicador_id": "poblacion_f",
        "grupo": "Población Proyectada",
        "indicador": "Población Femenina (Mujeres)",
        "descripcion": "Población femenina total en el año YYYY.",
        "resolucion_temporal": "2000 - 2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_M",
        "base_key": "poblacion",
        "indicador_id": "poblacion_m",
        "grupo": "Población Proyectada",
        "indicador": "Población Masculina (Hombres)",
        "descripcion": "Población masculina total en el año YYYY.",
        "resolucion_temporal": "2000 - 2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_0_50",
        "base_key": "poblacion",
        "indicador_id": "poblacion_0_50",
        "grupo": "Población Proyectada",
        "indicador": "Población - Edad 0 a 50 años",
        "descripcion": "Población estimada en el grupo etario de 0 a 50 años en el año YYYY.",
        "resolucion_temporal": "2000 - 2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_YYYY_>50",
        "base_key": "poblacion",
        "indicador_id": "poblacion_mayor_50",
        "grupo": "Población Proyectada",
        "indicador": "Población - Edad >50 años",
        "descripcion": "Población estimada en el grupo etario de más de 50 años en el año YYYY.",
        "resolucion_temporal": "2000 - 2025",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
    },

    # 2. SALUD Y MORTALIDAD (MINSA / SINADEF / CDC)
    {
        "id": "DEATHS_YYYY",
        "base_key": "mortalidad",
        "indicador_id": "mortalidad_total",
        "grupo": "Salud",
        "indicador": "Defunciones Anuales - Total",
        "descripcion": "Número total de muertes en el año indicado.",
        "resolucion_temporal": "2003 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DEATHS_YYYY_F",
        "base_key": "mortalidad",
        "indicador_id": "mortalidad_femenino",
        "grupo": "Salud",
        "indicador": "Defunciones Anuales - Mujeres (F)",
        "descripcion": "Número total de muertes en mujeres en el año indicado.",
        "resolucion_temporal": "2003 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DEATHS_YYYY_M",
        "base_key": "mortalidad",
        "indicador_id": "mortalidad_masculino",
        "grupo": "Salud",
        "indicador": "Defunciones Anuales - Hombres (M)",
        "descripcion": "Número total de muertes en hombres en el año indicado.",
        "resolucion_temporal": "2003 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
    },
    {
        "id": "DENGUE_YYYY",
        "base_key": "salud_vectores",
        "indicador_id": "dengue_total",
        "grupo": "Salud",
        "indicador": "Casos de Dengue - Total Anual",
        "descripcion": "Total de casos notificados de dengue en el año YYYY (con desglose mensual disponible).",
        "resolucion_temporal": "2000 - 2024 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "DENGUE_YYYY_F",
        "base_key": "salud_vectores",
        "indicador_id": "dengue_f",
        "grupo": "Salud",
        "indicador": "Casos de Dengue - Mujeres (F)",
        "descripcion": "Total de casos notificados de dengue en mujeres en el año YYYY.",
        "resolucion_temporal": "2000 - 2024 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "DENGUE_YYYY_M",
        "base_key": "salud_vectores",
        "indicador_id": "dengue_m",
        "grupo": "Salud",
        "indicador": "Casos de Dengue - Hombres (M)",
        "descripcion": "Total de casos notificados de dengue en hombres en el año YYYY.",
        "resolucion_temporal": "2000 - 2024 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "DENGUE_YYYY_0_19",
        "base_key": "salud_vectores",
        "indicador_id": "dengue_0_19",
        "grupo": "Salud",
        "indicador": "Casos de Dengue - Edad 0 a 19 años",
        "descripcion": "Total de casos notificados de dengue en población de 0 a 19 años en el año YYYY.",
        "resolucion_temporal": "2000 - 2024 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "DENGUE_YYYY_>20",
        "base_key": "salud_vectores",
        "indicador_id": "dengue_mayor_20",
        "grupo": "Salud",
        "indicador": "Casos de Dengue - Edad >20 años",
        "descripcion": "Total de casos notificados de dengue en población mayor de 20 años en el año YYYY.",
        "resolucion_temporal": "2000 - 2024 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_YYYY",
        "base_key": "salud_vectores",
        "indicador_id": "malaria_total",
        "grupo": "Salud",
        "indicador": "Casos de Malaria - Total Anual",
        "descripcion": "Total de casos notificados de malaria en el año YYYY (con desglose mensual disponible).",
        "resolucion_temporal": "2000 - 2023 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_PF_YYYY",
        "base_key": "salud_vectores",
        "indicador_id": "malaria_falciparum",
        "grupo": "Salud",
        "indicador": "Casos de Malaria - P. Falciparum (PF)",
        "descripcion": "Total de casos notificados de malaria por Plasmodium Falciparum en el año YYYY.",
        "resolucion_temporal": "2000 - 2023 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_PV_YYYY",
        "base_key": "salud_vectores",
        "indicador_id": "malaria_vivax",
        "grupo": "Salud",
        "indicador": "Casos de Malaria - P. Vivax (PV)",
        "descripcion": "Total de casos notificados de malaria por Plasmodium Vivax en el año YYYY.",
        "resolucion_temporal": "2000 - 2023 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_YYYY_F",
        "base_key": "salud_vectores",
        "indicador_id": "malaria_f",
        "grupo": "Salud",
        "indicador": "Casos de Malaria - Mujeres (F)",
        "descripcion": "Total de casos notificados de malaria en mujeres en el año YYYY.",
        "resolucion_temporal": "2000 - 2023 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },
    {
        "id": "MALARIA_YYYY_M",
        "base_key": "salud_vectores",
        "indicador_id": "malaria_m",
        "grupo": "Salud",
        "indicador": "Casos de Malaria - Hombres (M)",
        "descripcion": "Total de casos notificados de malaria en hombres en el año YYYY.",
        "resolucion_temporal": "2000 - 2023 (Anual y Mensual)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
    },

    # 3. CLIMA Y MEDIO AMBIENTE (SENAMHI / NASA / CHIRPS / ESA)
    {
        "id": "PM2_5_PROM_YYYY",
        "base_key": "clima",
        "indicador_id": "clima_pm25",
        "grupo": "Clima",
        "indicador": "Material Particulado PM2.5",
        "descripcion": "Nivel promedio de material particulado PM2.5 registrado en el año YYYY.",
        "resolucion_temporal": "2001 - 2022",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "NASA / SEDAC / Venter et al.",
        "unidad": "µg/m³",
    },
    {
        "id": "NO2_PROM_YYYY",
        "base_key": "clima",
        "indicador_id": "clima_no2",
        "grupo": "Clima",
        "indicador": "Dióxido de Nitrógeno (NO2)",
        "descripcion": "Nivel promedio de dióxido de nitrógeno (NO2) registrado en el año YYYY.",
        "resolucion_temporal": "2019 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "ESA Sentinel-5P / TROPOMI",
        "unidad": "µmol/m²",
    },
    {
        "id": "PREC_PROM_YYYY",
        "base_key": "clima",
        "indicador_id": "clima_pp",
        "grupo": "Clima",
        "indicador": "Precipitación Promedio Anual",
        "descripcion": "Precipitación promedio registrada en el año YYYY.",
        "resolucion_temporal": "2001 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SENAMHI / CHIRPS",
        "unidad": "mm/año",
    },
    {
        "id": "T_PROM_YYYY",
        "base_key": "clima",
        "indicador_id": "clima_lst",
        "grupo": "Clima",
        "indicador": "Temperatura Superficial (LST)",
        "descripcion": "Temperatura promedio registrada en el año YYYY.",
        "resolucion_temporal": "2001 - 2024",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "NASA MODIS (MOD11A2)",
        "unidad": "°C",
    },

    # 4. CENSO NACIONAL 2017 (INEI / REDATAM)
    {
        "id": "UNEMPLOYMENT_RATE",
        "base_key": "censo",
        "indicador_id": "UNEMPLOYMENT_RATE",
        "grupo": "CENSO",
        "indicador": "Tasa de Desempleo Total (%)",
        "descripcion": "Tasa de desempleo entre la población total de 15 años o más en la fuerza laboral.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "UNEMPLOYMENT_RATE_F",
        "base_key": "censo",
        "indicador_id": "UNEMPLOYMENT_RATE_F",
        "grupo": "CENSO",
        "indicador": "Tasa de Desempleo - Mujeres (%)",
        "descripcion": "Tasa de desempleo entre la población femenina de 15 años o más en la fuerza laboral.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "UNEMPLOYMENT_RATE_M",
        "base_key": "censo",
        "indicador_id": "UNEMPLOYMENT_RATE_M",
        "grupo": "CENSO",
        "indicador": "Tasa de Desempleo - Hombres (%)",
        "descripcion": "Tasa de desempleo entre la población masculina de 15 años o más en la fuerza laboral.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "UNEMPLOYMENT_RATIO_F_TO_M",
        "base_key": "censo",
        "indicador_id": "UNEMPLOYMENT_RATIO_F_TO_M",
        "grupo": "CENSO",
        "indicador": "Ratio de Desempleo Mujer/Hombre",
        "descripcion": "Relación entre la tasa de desempleo de mujeres y hombres (15 años o más).",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Ratio",
    },
    {
        "id": "LABOR_FORCE_PARTICIPATION",
        "base_key": "censo",
        "indicador_id": "LABOR_FORCE_PARTICIPATION",
        "grupo": "CENSO",
        "indicador": "Participación en Fuerza Laboral Total (%)",
        "descripcion": "Tasa de participación en la fuerza laboral de la población total de 15 años o más.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "LABOR_FORCE_PARTICIPATION_F",
        "base_key": "censo",
        "indicador_id": "LABOR_FORCE_PARTICIPATION_F",
        "grupo": "CENSO",
        "indicador": "Participación Laboral - Mujeres (%)",
        "descripcion": "Tasa de participación en la fuerza laboral de las mujeres de 15 años o más.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "LABOR_FORCE_PARTICIPATION_M",
        "base_key": "censo",
        "indicador_id": "LABOR_FORCE_PARTICIPATION_M",
        "grupo": "CENSO",
        "indicador": "Participación Laboral - Hombres (%)",
        "descripcion": "Tasa de participación en la fuerza laboral de los hombres de 15 años o más.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "FEMALE_LABOR_FORCE_RATIO",
        "base_key": "censo",
        "indicador_id": "FEMALE_LABOR_FORCE_RATIO",
        "grupo": "CENSO",
        "indicador": "Proporción de Mujeres en Fuerza Laboral (%)",
        "descripcion": "Proporción de la fuerza laboral total que son mujeres (15 años o más).",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "NO_EDUCATION_NOR_EMPLOYMENT",
        "base_key": "censo",
        "indicador_id": "NO_EDUCATION_NOR_EMPLOYMENT",
        "grupo": "CENSO",
        "indicador": "Población NINI (No estudia ni trabaja) (%)",
        "descripcion": "Proporción de la población de 15 años a 24 años que no estudia ni trabaja",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "NO_EDUCATION_NOR_EMPLOYMENT_F",
        "base_key": "censo",
        "indicador_id": "NO_EDUCATION_NOR_EMPLOYMENT_F",
        "grupo": "CENSO",
        "indicador": "Población NINI - Mujeres (%)",
        "descripcion": "Proporción de las mujeres de 15 años a 24 años que no estudia ni trabaja",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "NO_EDUCATION_NOR_EMPLOYMENT_M",
        "base_key": "censo",
        "indicador_id": "NO_EDUCATION_NOR_EMPLOYMENT_M",
        "grupo": "CENSO",
        "indicador": "Población NINI - Hombres (%)",
        "descripcion": "Proporción de los hombres de 15 años a 24 años que no estudia ni trabaja",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "SCHOOL_ATTENDANCE_15_17",
        "base_key": "censo",
        "indicador_id": "SCHOOL_ATTENDANCE_15_17",
        "grupo": "CENSO",
        "indicador": "Asistencia Escolar 15-17 años Total (%)",
        "descripcion": "Proporción de la población de 15 a 17 años que asiste a la escuela.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "SCHOOL_ATTENDANCE_15_17_F",
        "base_key": "censo",
        "indicador_id": "SCHOOL_ATTENDANCE_15_17_F",
        "grupo": "CENSO",
        "indicador": "Asistencia Escolar 15-17 - Mujeres (%)",
        "descripcion": "Proporción de la población femenina de 15 a 17 años que asiste a la escuela.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "SCHOOL_ATTENDANCE_15_17_M",
        "base_key": "censo",
        "indicador_id": "SCHOOL_ATTENDANCE_15_17_M",
        "grupo": "CENSO",
        "indicador": "Asistencia Escolar 15-17 - Hombres (%)",
        "descripcion": "Proporción de la población masculina de 15 a 17 años que asiste a la escuela.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_PRIMARY_COMPLETED",
        "base_key": "censo",
        "indicador_id": "EDUCATION_PRIMARY_COMPLETED",
        "grupo": "CENSO",
        "indicador": "Primaria Completa (%)",
        "descripcion": "Proporción de la población de 25 años o más que completó la educación primaria o superior.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_SECONDARY_COMPLETED",
        "base_key": "censo",
        "indicador_id": "EDUCATION_SECONDARY_COMPLETED",
        "grupo": "CENSO",
        "indicador": "Secundaria Completa (%)",
        "descripcion": "Proporción de la población de 25 años o más que completó la educación secundaria o superior.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_UNIVERSITY_COMPLETED",
        "base_key": "censo",
        "indicador_id": "EDUCATION_UNIVERSITY_COMPLETED",
        "grupo": "CENSO",
        "indicador": "Superior Universitaria Completa (%)",
        "descripcion": "Proporción de la población de 25 años o más que completó la educación universitaria o superior.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED",
        "base_key": "censo",
        "indicador_id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED",
        "grupo": "CENSO",
        "indicador": "Ratio Educativo Mujer/Hombre",
        "descripcion": "Relación entre la proporción de mujeres y hombres de 25 años o más que completaron la educación secundaria o superior.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Ratio",
    },
    {
        "id": "POP_CENSADA_REDATAM",
        "base_key": "censo",
        "indicador_id": "POP_CENSADA_REDATAM",
        "grupo": "CENSO",
        "indicador": "Población Censada (Redatam)",
        "descripcion": "(29 millones) Total de población efectivamente censada según los registros disponibles en Redatam.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Habitantes",
    },
    {
        "id": "POP_TOTAL_REDATAM",
        "base_key": "censo",
        "indicador_id": "POP_TOTAL_REDATAM",
        "grupo": "CENSO",
        "indicador": "Población Total Estimada (Redatam)",
        "descripcion": "(31 millones) Total de población estimada según los registros por Redatam, incluyendo proyecciones o ajustes post-censales.",
        "resolucion_temporal": "2017 (Censal)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Habitantes",
    },

    # 5. ENDES - VACUNACIÓN INFANTIL (INEI - ENDES)
    {
        "id": "ENDES_VAC_INFLUENZA_1D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_influenza_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Influenza 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna contra influenza en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_INFLUENZA_2D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_influenza_2d_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Influenza 2ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 2ª dosis de vacuna contra influenza en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_ROTAVIRUS_1D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_rotavirus_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Rotavirus 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna contra rotavirus en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_ROTAVIRUS_2D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_rotavirus_2d_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Rotavirus 2ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 2ª dosis de vacuna contra rotavirus en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_NEUMOCOCO_1D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_neumococo_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Neumococo 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna neumocócica en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_NEUMOCOCO_2D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_neumococo_2d_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Neumococo 2ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 2ª dosis de vacuna neumocócica en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_NEUMOCOCO_3D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_neumococo_3d_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Neumococo 3ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 3ª dosis de vacuna neumocócica en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_PENTAVALENTE_1D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_pentavalente_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Pentavalente 1ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 1ª dosis de vacuna pentavalente en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_PENTAVALENTE_2D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_pentavalente_2d_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Pentavalente 2ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 2ª dosis de vacuna pentavalente en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "ENDES_VAC_PENTAVALENTE_3D_YYYY_Yes_P",
        "base_key": "endes",
        "indicador_id": "vac_pentavalente_3d_p",
        "grupo": "ENDES",
        "indicador": "Vacunación Pentavalente 3ª Dosis (%)",
        "descripcion": "Proporción de personas que SÍ recibieron la 3ª dosis de vacuna pentavalente en el año YYYY.",
        "resolucion_temporal": "2020 - 2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },

    # 6. ENDES - CARACTERÍSTICAS DE VIVIENDA Y SANEAMIENTO (INEI - ENDES)
    {
        "id": "HH_MASONRY_WALLS_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "pared_noble",
        "grupo": "ENDES",
        "indicador": "Paredes de Material Noble (%)",
        "descripcion": "Proporción de hogares con paredes de material noble (albañilería).",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_RUSTIC_WALLS_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "pared_rustica",
        "grupo": "ENDES",
        "indicador": "Paredes de Material Rústico (%)",
        "descripcion": "Proporción de hogares con paredes de material rústico (adobe/quincha).",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_NATURAL_WALLS_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "pared_natural",
        "grupo": "ENDES",
        "indicador": "Paredes de Material Natural (%)",
        "descripcion": "Proporción de hogares con paredes de material natural (madera/estera).",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_FINISHED_FLOORS_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "piso_acabado",
        "grupo": "ENDES",
        "indicador": "Pisos Acabados (%)",
        "descripcion": "Proporción de hogares con pisos acabados (cemento pulido, cerámica, madera fina, etc.).",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_NATURAL_FLOORS_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "piso_tierra",
        "grupo": "ENDES",
        "indicador": "Pisos de Tierra / Natural (%)",
        "descripcion": "Proporción de hogares con pisos de tierra o arena.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_RUSTIC_FLOORS_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "piso_rustico",
        "grupo": "ENDES",
        "indicador": "Pisos Rústicos (%)",
        "descripcion": "Proporción de hogares con pisos rústicos (tablas/madera sin pulir).",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_WATER_PUBLIC_NETWORK_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "agua_red_publica",
        "grupo": "ENDES",
        "indicador": "Conexión a Red Pública de Agua (%)",
        "descripcion": "Proporción de hogares con conexión a una red pública de agua.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_WATER_WELL_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "agua_pozo",
        "grupo": "ENDES",
        "indicador": "Abastecimiento de Agua por Pozo (%)",
        "descripcion": "Proporción de hogares con abastecimiento de agua por pozo.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_WATER_SURFACE_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "agua_superficial",
        "grupo": "ENDES",
        "indicador": "Agua de Río / Manantial (%)",
        "descripcion": "Proporción de hogares con abastecimiento de agua de río, acequia o manantial.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_PUBLIC_SEWAGE_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "desague_alcantarillado",
        "grupo": "ENDES",
        "indicador": "Conexión a Red de Alcantarillado (%)",
        "descripcion": "Proporción de hogares con conexión a una red pública de alcantarillado.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_PIT_LATRINE_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "letrina_pozo",
        "grupo": "ENDES",
        "indicador": "Letrina / Pozo Ciego (%)",
        "descripcion": "Proporción de hogares con letrina o pozo ciego.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },
    {
        "id": "HH_NO_SANITARY_SERVICE_YYYY_Yes_percent",
        "base_key": "endes_vivienda",
        "indicador_id": "sin_servicio_higienico",
        "grupo": "ENDES",
        "indicador": "Sin Servicio Higiénico (%)",
        "descripcion": "Proporción de hogares sin ningún servicio higiénico.",
        "resolucion_temporal": "2023",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
    },

    # 7. ENDES - SÍFILIS EN GESTANTES (MINSA / ENDES)
    {
        "id": "SIFILIS_CASES_YYYY",
        "base_key": "endes_sifilis",
        "indicador_id": "sifilis_gestantes",
        "grupo": "ENDES",
        "indicador": "Sífilis en Gestantes (Casos)",
        "descripcion": "Total de casos de sífilis en gestantes en el año YYYY.",
        "resolucion_temporal": "2010 - 2022",
        "resolucion_espacial": ["Departamento"],
        "fuente": "MINSA / ENDES",
        "unidad": "Casos Notificados",
    },

    # 8. MISCELÁNEO - TIEMPOS DE VIAJE (SUSALUD / OSM)
    {
        "id": "TIEMPO_VIAJE_CCPP_PRIMARY",
        "base_key": "travel_time",
        "indicador_id": "primary_hcf",
        "grupo": "Misceláneo",
        "indicador": "Tiempo a Centro Salud Nivel 1 (min)",
        "descripcion": "Promedio de tiempo de viaje de los CCPP de ese distrito a su CCSS de primer nivel mas cercano",
        "resolucion_temporal": "2017 (Estático)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SUSALUD / OpenStreetMap (Modelo Friccional)",
        "unidad": "Minutos",
    },
    {
        "id": "TIEMPO_VIAJE_CCPP_SECONDARY",
        "base_key": "travel_time",
        "indicador_id": "secondary_hcf",
        "grupo": "Misceláneo",
        "indicador": "Tiempo a Centro Salud Nivel 2 (min)",
        "descripcion": "Promedio de tiempo de viaje de los CCPP de ese distrito a su CCSS de segundo nivel mas cercano",
        "resolucion_temporal": "2017 (Estático)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SUSALUD / OpenStreetMap",
        "unidad": "Minutos",
    },
    {
        "id": "TIEMPO_VIAJE_CCPP_TERTIARY",
        "base_key": "travel_time",
        "indicador_id": "tertiary_hcf",
        "grupo": "Misceláneo",
        "indicador": "Tiempo a Hospital Nivel 3 (min)",
        "descripcion": "Promedio de tiempo de viaje de los CCPP de ese distrito a su CCSS de tercer nivel mas cercano",
        "resolucion_temporal": "2017 (Estático)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SUSALUD / OpenStreetMap",
        "unidad": "Minutos",
    },
]

DB_GZ_PATH = BASE_DIR / "dashboard_data_completo.db.gz"

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
    full = full.fillna("")
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
        sexo = "F" if indicador == "poblacion_f" else "M" if indicador == "poblacion_m" else "Total"
        grupo = "0-50" if indicador == "poblacion_0_50" else ">50" if indicador == "poblacion_mayor_50" else "Total"
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, poblacion AS valor FROM fact_population WHERE nivel_geo = ? AND sexo = ? AND grupo_edad = ? AND anio BETWEEN ? AND ?",
            conn, params=(nivel, sexo, grupo, anio_min, anio_max),
        )
        result = temporal_response(df, "POP_", conn, nivel=nivel)
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
        df = with_names(df, conn, nivel=nivel).rename(columns={"valor": indicador}).fillna("")
        result = jsonify({"columns": list(df.columns), "rows": df.to_dict(orient="records")})
    elif base == "endes":
        parts = indicador.split("_")
        vaccine = parts[1].upper()
        dose = parts[2].upper() if len(parts) >= 3 and parts[2].upper() in ("1D", "2D", "3D") else "1D"
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, proporcion * 100 AS valor FROM fact_endes_vacuna WHERE vacuna = ? AND dosis = ? AND respuesta = 'Yes' AND anio BETWEEN ? AND ?",
            conn, params=(vaccine, dose, anio_min, anio_max),
        )
        result = temporal_response(df, f"VAC_{vaccine}_{dose}_", conn, nivel=nivel)
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