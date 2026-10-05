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
            {"id": "UNEMPLOYMENT_RATE", "label": "Tasa de Desempleo (%)"},
            {"id": "EDUCATION_PRIMARY_COMPLETED", "label": "Primaria Completa (%)"},
            {"id": "EDUCATION_SECONDARY_COMPLETED", "label": "Secundaria Completa (%)"},
            {"id": "EDUCATION_UNIVERSITY_COMPLETED", "label": "Superior Universitaria Completa (%)"},
            {"id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED", "label": "Ratio Educativo Mujer/Hombre"},
        ],
    },
    "endes": {
        "label": "ENDES - Vacunación Infantil",
        "niveles": ["departamento"],
        "tiene_anios": True,
        "min_anio": 2020,
        "max_anio": 2023,
        "indicadores": [
            {"id": "vac_influenza_p", "label": "Vacuna Influenza (Proporción %)"},
            {"id": "vac_rotavirus_p", "label": "Vacuna Rotavirus (Proporción %)"},
            {"id": "vac_neumococo_p", "label": "Vacuna Neumococo (Proporción %)"},
            {"id": "vac_pentavalente_p", "label": "Vacuna Pentavalente (Proporción %)"},
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
    # 1. Mortalidad (SINADEF)
    {
        "id": "mortalidad_total",
        "base_key": "mortalidad",
        "grupo": "Salud y Mortalidad",
        "indicador": "Defunciones Anuales - Total",
        "descripcion": "Conteo total anual de defunciones registradas a nivel nacional por el Sistema Informático Nacional de Defunciones.",
        "resolucion_temporal": "Anual (2003 - 2024)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / Ministerio de Salud (MINSA)",
        "unidad": "Defunciones",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "mortalidad_femenino",
        "base_key": "mortalidad",
        "grupo": "Salud y Mortalidad",
        "indicador": "Defunciones Anuales - Mujeres (F)",
        "descripcion": "Conteo anual de defunciones correspondientes al sexo femenino.",
        "resolucion_temporal": "Anual (2003 - 2024)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "mortalidad_masculino",
        "base_key": "mortalidad",
        "grupo": "Salud y Mortalidad",
        "indicador": "Defunciones Anuales - Hombres (M)",
        "descripcion": "Conteo anual de defunciones correspondientes al sexo masculino.",
        "resolucion_temporal": "Anual (2003 - 2024)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "SINADEF / MINSA",
        "unidad": "Defunciones",
        "tipo_dato": "Numérico (Entero)",
    },
    # 2. Demografía y Población (INEI)
    {
        "id": "poblacion_total",
        "base_key": "poblacion",
        "grupo": "Demografía y Población",
        "indicador": "Población Total (Ambos Sexos)",
        "descripcion": "Estimaciones y proyecciones oficiales de población total desagregadas por área geográfica.",
        "resolucion_temporal": "Anual (2000 - 2025)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "Instituto Nacional de Estadística e Informática (INEI)",
        "unidad": "Habitantes",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "poblacion_f",
        "base_key": "poblacion",
        "grupo": "Demografía y Población",
        "indicador": "Población - Mujeres (F)",
        "descripcion": "Estimaciones y proyecciones de población femenina anual.",
        "resolucion_temporal": "Anual (2000 - 2025)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "poblacion_m",
        "base_key": "poblacion",
        "grupo": "Demografía y Población",
        "indicador": "Población - Hombres (M)",
        "descripcion": "Estimaciones y proyecciones de población masculina anual.",
        "resolucion_temporal": "Anual (2000 - 2025)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "poblacion_0_50",
        "base_key": "poblacion",
        "grupo": "Demografía y Población",
        "indicador": "Población - Edad 0 a 50",
        "descripcion": "Población estimada en el grupo etario de 0 a 50 años (niños, jóvenes y adultos jóvenes).",
        "resolucion_temporal": "Anual (2000 - 2025)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "poblacion_mayor_50",
        "base_key": "poblacion",
        "grupo": "Demografía y Población",
        "indicador": "Población - Edad >50",
        "descripcion": "Población estimada en el grupo etario de más de 50 años (adultos mayores).",
        "resolucion_temporal": "Anual (2000 - 2025)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI",
        "unidad": "Habitantes",
        "tipo_dato": "Numérico (Entero)",
    },
    # 3. Clima y Calidad del Aire
    {
        "id": "clima_pm25",
        "base_key": "clima",
        "grupo": "Clima y Medio Ambiente",
        "indicador": "Material Particulado PM2.5",
        "descripcion": "Concentración media anual de partículas finas inhalables con diámetro aerodinámico ≤ 2.5 µm derivadas de modelos y sensores satelitales.",
        "resolucion_temporal": "Anual (2001 - 2022)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "NASA / SEDAC / Venter et al. (Modelos Satelitales)",
        "unidad": "µg/m³",
        "tipo_dato": "Numérico (Continuo)",
    },
    {
        "id": "clima_no2",
        "base_key": "clima",
        "grupo": "Clima y Medio Ambiente",
        "indicador": "Dióxido de Nitrógeno NO2",
        "descripcion": "Densidad de columna troposférica de dióxido de nitrógeno, indicador clave de emisiones industriales y vehiculares.",
        "resolucion_temporal": "Anual (2019 - 2024)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "ESA Sentinel-5P / TROPOMI",
        "unidad": "µmol/m²",
        "tipo_dato": "Numérico (Continuo)",
    },
    {
        "id": "clima_pp",
        "base_key": "clima",
        "grupo": "Clima y Medio Ambiente",
        "indicador": "Precipitación Media Anual",
        "descripcion": "Acumulado de precipitación pluvial promedio anual calculado a partir de sensores térmicos infrarrojos y estaciones meteorológicas.",
        "resolucion_temporal": "Anual (2001 - 2024)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CHIRPS / Climate Hazards Center / UCSB",
        "unidad": "mm/año",
        "tipo_dato": "Numérico (Continuo)",
    },
    {
        "id": "clima_lst",
        "base_key": "clima",
        "grupo": "Clima y Medio Ambiente",
        "indicador": "Temperatura Superficial LST",
        "descripcion": "Temperatura media anual de la superficie terrestre (Land Surface Temperature) medida por sensores térmicos MODIS.",
        "resolucion_temporal": "Anual (2001 - 2024)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "NASA MODIS (MOD11A2 / MYD11A2)",
        "unidad": "°C",
        "tipo_dato": "Numérico (Continuo)",
    },
    # 4. Salud - Enfermedades Metaxénicas (Vectores)
    {
        "id": "dengue_total",
        "base_key": "salud_vectores",
        "grupo": "Salud y Epidemiología",
        "indicador": "Dengue - Casos Acumulados",
        "descripcion": "Número total de casos acumulados de dengue notificados (sin signos de alarma, con signos de alarma y dengue grave).",
        "resolucion_temporal": "Acumulado Multianual",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "Centro Nacional de Epidemiología (CDC Perú / MINSA)",
        "unidad": "Casos Notificados",
        "tipo_dato": "Numérico (Entero)",
    },
    {
        "id": "malaria_total",
        "base_key": "salud_vectores",
        "grupo": "Salud y Epidemiología",
        "indicador": "Malaria - Casos Acumulados",
        "descripcion": "Número total de casos confirmados de malaria acumulados (Plasmodium vivax y Plasmodium falciparum).",
        "resolucion_temporal": "Acumulado Multianual",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "CDC Perú / MINSA",
        "unidad": "Casos Notificados",
        "tipo_dato": "Numérico (Entero)",
    },
    # 5. Censo Nacional y Socioeconómico (REDATAM)
    {
        "id": "UNEMPLOYMENT_RATE",
        "base_key": "censo",
        "grupo": "Socioeconómico y Empleo",
        "indicador": "Tasa de Desempleo (%)",
        "descripcion": "Porcentaje de la Población Económicamente Activa (PEA) de 14 años a más que se encuentra en condición de desocupación abierta.",
        "resolucion_temporal": "Censal (Censo Nacional 2017)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional XII de Población / REDATAM",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "EDUCATION_PRIMARY_COMPLETED",
        "base_key": "censo",
        "grupo": "Educación y Capital Humano",
        "indicador": "Primaria Completa (%)",
        "descripcion": "Porcentaje de la población de 15 a más años que alcanzó como máximo nivel educativo la educación primaria completa.",
        "resolucion_temporal": "Censal (Censo Nacional 2017)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "EDUCATION_SECONDARY_COMPLETED",
        "base_key": "censo",
        "grupo": "Educación y Capital Humano",
        "indicador": "Secundaria Completa (%)",
        "descripcion": "Porcentaje de la población de 15 a más años con educación secundaria completa concluida.",
        "resolucion_temporal": "Censal (Censo Nacional 2017)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "EDUCATION_UNIVERSITY_COMPLETED",
        "base_key": "censo",
        "grupo": "Educación y Capital Humano",
        "indicador": "Superior Universitaria Completa (%)",
        "descripcion": "Porcentaje de la población de 15 a más años con estudios superiores universitarios culminados.",
        "resolucion_temporal": "Censal (Censo Nacional 2017)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "EDUCATION_SECONDARY_RATIO_F_TO_M_COMPLETED",
        "base_key": "censo",
        "grupo": "Educación y Género",
        "indicador": "Ratio Educativo Mujer/Hombre",
        "descripcion": "Razón entre el porcentaje de mujeres con secundaria completa y el porcentaje de hombres con secundaria completa (paridad educativa).",
        "resolucion_temporal": "Censal (Censo Nacional 2017)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "INEI - Censo Nacional 2017",
        "unidad": "Ratio / Índice",
        "tipo_dato": "Numérico (Índice)",
    },
    # 6. ENDES - Inmunización y Vacunación Infantil
    {
        "id": "vac_influenza_p",
        "base_key": "endes",
        "grupo": "Salud Materno-Infantil",
        "indicador": "Vacuna Influenza (Proporción %)",
        "descripcion": "Proporción de niñas y niños de 6 a 35 meses de edad con esquema de vacunación contra la influenza estacional.",
        "resolucion_temporal": "Anual (2020 - 2023)",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - Encuesta Demográfica y de Salud Familiar (ENDES)",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "vac_rotavirus_p",
        "base_key": "endes",
        "grupo": "Salud Materno-Infantil",
        "indicador": "Vacuna Rotavirus (Proporción %)",
        "descripcion": "Proporción de niñas y niños con esquema de vacunación contra el rotavirus (prevención de diarreas agudas).",
        "resolucion_temporal": "Anual (2020 - 2023)",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "vac_neumococo_p",
        "base_key": "endes",
        "grupo": "Salud Materno-Infantil",
        "indicador": "Vacuna Neumococo (Proporción %)",
        "descripcion": "Proporción de niñas y niños con vacunación contra neumococo (prevención de infecciones respiratorias agudas y neumonía).",
        "resolucion_temporal": "Anual (2020 - 2023)",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    {
        "id": "vac_pentavalente_p",
        "base_key": "endes",
        "grupo": "Salud Materno-Infantil",
        "indicador": "Vacuna Pentavalente (Proporción %)",
        "descripcion": "Proporción de niñas y niños menores de 1 año con 3 dosis de vacuna pentavalente (difteria, tos ferina, tétanos, hepatitis B y Hib).",
        "resolucion_temporal": "Anual (2020 - 2023)",
        "resolucion_espacial": ["Departamento"],
        "fuente": "INEI - ENDES",
        "unidad": "Porcentaje (%)",
        "tipo_dato": "Numérico (Proporción)",
    },
    # 7. Infraestructura y Tiempos de Viaje
    {
        "id": "primary_hcf",
        "base_key": "travel_time",
        "grupo": "Infraestructura y Accesibilidad",
        "indicador": "Minutos a Centro Salud Nivel 1",
        "descripcion": "Tiempo estimado promedio de viaje (minutos) hacia el establecimiento de salud de primer nivel de atención (puesto/centro de salud) más próximo.",
        "resolucion_temporal": "Estático (Modelo Friccional)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "Modelo de Accesibilidad Friccional / SUSALUD / OpenStreetMap",
        "unidad": "Minutos",
        "tipo_dato": "Numérico (Continuo)",
    },
    {
        "id": "secondary_hcf",
        "base_key": "travel_time",
        "grupo": "Infraestructura y Accesibilidad",
        "indicador": "Minutos a Centro Salud Nivel 2",
        "descripcion": "Tiempo estimado de viaje hacia el establecimiento de salud de segundo nivel (hospitales generales / policlínicos) más cercano.",
        "resolucion_temporal": "Estático (Modelo Friccional)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "Modelo de Accesibilidad Friccional / SUSALUD / OSM",
        "unidad": "Minutos",
        "tipo_dato": "Numérico (Continuo)",
    },
    {
        "id": "tertiary_hcf",
        "base_key": "travel_time",
        "grupo": "Infraestructura y Accesibilidad",
        "indicador": "Minutos a Hospital Nivel 3",
        "descripcion": "Tiempo estimado de viaje hacia hospitales de tercer nivel de atención (alta complejidad e institutos especializados).",
        "resolucion_temporal": "Estático (Modelo Friccional)",
        "resolucion_espacial": ["Departamento", "Provincia", "Distrito"],
        "fuente": "Modelo de Accesibilidad Friccional / SUSALUD / OSM",
        "unidad": "Minutos",
        "tipo_dato": "Numérico (Continuo)",
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
        vaccine = indicador.split("_")[1].upper()
        df = pd.read_sql_query(
            "SELECT ubigeo, anio, proporcion * 100 AS valor FROM fact_endes_vacuna WHERE vacuna = ? AND respuesta = 'Yes' AND anio BETWEEN ? AND ?",
            conn, params=(vaccine, anio_min, anio_max),
        )
        result = temporal_response(df, f"VAC_{vaccine}_", conn)
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