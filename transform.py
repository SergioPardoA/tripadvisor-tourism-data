
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


# ==================================================
# 1. RUTAS
# ==================================================

BASE = Path(__file__).resolve().parent

RAW_DIR = BASE / "data" / "raw"
CLEAN_DIR = BASE / "data" / "clean"

CLEAN_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = CLEAN_DIR / "tripadvisor_reviews.csv"


# ==================================================
# 2. PALABRAS CLAVE
# ==================================================

# Categorías generales relacionadas con la
# experiencia de los clientes en alojamientos.
#
# El objetivo es identificar TEMAS, no determinar
# si el comentario sobre ellos es positivo o negativo.

KEYWORDS = {

    "limpieza": [
        # Español
        "limpieza", "limpio", "limpia",
        "limpios", "limpias", "sucio",
        "sucia", "suciedad",

        # Inglés
        "clean", "cleanliness", "dirty",
        "filthy", "spotless"
    ],

    "servicio": [
        # Español
        "servicio", "personal", "atencion",
        "recepcion", "recepcionista",
        "empleado", "empleados",
        "trato", "amabilidad",

        # Inglés
        "service", "staff", "reception",
        "receptionist", "employee",
        "employees", "friendly",
        "helpful", "rude"
    ],

    "precio": [
        # Español
        "precio", "precios", "caro",
        "cara", "barato", "barata",
        "coste", "tarifa",

        # Inglés
        "price", "prices", "expensive",
        "cheap", "cost", "overpriced",
        "affordable"
    ],

    "ubicacion": [
        # Español
        "ubicacion", "localizacion",
        "centrico", "centrica",
        "centro", "cerca",
        "distancia",

        # Inglés
        "location", "located",
        "central", "near", "nearby",
        "close", "downtown",
        "distance"
    ],

    "habitacion": [
        # Español
        "habitacion", "habitaciones",
        "cuarto", "cama", "camas",
        "bano", "ducha", "colchon",

        # Inglés
        "room", "rooms", "bed",
        "beds", "bathroom", "shower",
        "mattress"
    ],

    "ruido": [
        # Español
        "ruido", "ruidoso", "ruidosa",
        "silencio", "insonorizacion",

        # Inglés
        "noise", "noisy", "loud",
        "quiet", "soundproof"
    ],

    "desayuno": [
        # Español
        "desayuno", "desayunos",

        # Inglés
        "breakfast", "breakfasts"
    ]
}


# Idiomas para los que hemos definido
# un diccionario de palabras clave.

IDIOMAS_CUBIERTOS = {"es", "en"}


# ==================================================
# 3. FUNCIONES DE LIMPIEZA
# ==================================================

def clean_text(text):
    """
    Elimina saltos de línea y espacios repetidos.
    """

    if not isinstance(text, str):
        return ""

    return " ".join(text.split())


def normalize_text(text):
    """
    Convierte el texto a minúsculas y elimina tildes.

    Ejemplo:
    'Ubicación' -> 'ubicacion'
    """

    text = unicodedata.normalize(
        "NFD",
        text.lower()
    )

    return "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )


def identify_keywords(text):
    """
    Identifica categorías mediante un diccionario.

    Busca palabras completas y permite asignar
    varias categorías a una misma reseña.

    No realiza análisis de sentimiento.
    """

    normalized = normalize_text(text)

    found = []

    for category, words in KEYWORDS.items():

        for word in words:

            pattern = (
                r"\b"
                + re.escape(normalize_text(word))
                + r"\b"
            )

            if re.search(pattern, normalized):

                found.append(category)

                break

    return ", ".join(found)


def get_keyword_analysis(title, text, language):
    """
    Analiza palabras clave únicamente si el
    idioma está incluido en IDIOMAS_CUBIERTOS.

    Devuelve:
        keywords, keyword_status

    Estados:
        detectado
        sin_coincidencias
        idioma_no_cubierto
    """

    # Convertir códigos como 'en-US' o 'es-ES'
    # a sus idiomas base.

    idioma_base = (
        str(language)
        .strip()
        .lower()
        .replace("_", "-")
        .split("-")[0]
    )

    # No clasificar comentarios en idiomas
    # sin cobertura lingüística definida.

    if idioma_base not in IDIOMAS_CUBIERTOS:

        return "", "idioma_no_cubierto"

    # Analizar tanto el título como el comentario.

    combined_text = title + " " + text

    keywords = identify_keywords(combined_text)

    if keywords:

        return keywords, "detectado"

    return "", "sin_coincidencias"


def get_primary_text(items):
    """
    Obtiene texto e idioma de la variante principal
    devuelta por la API de Tripadvisor.
    """

    if not isinstance(items, list) or not items:

        return "", "unknown"

    valid_items = [
        item
        for item in items
        if isinstance(item, dict)
    ]

    if not valid_items:

        return "", "unknown"

    selected = next(
        (
            item
            for item in valid_items
            if item.get("primary") is True
        ),
        valid_items[0]
    )

    return (
        clean_text(selected.get("value")),
        selected.get("language") or "unknown"
    )


# ==================================================
# 4. SUBVALORACIONES
# ==================================================

SUBRATING_MAP = {

    "RATE_CLEANLINESS": "rating_cleanliness",

    "RATE_LOCATION": "rating_location",

    "RATE_ROOM": "rating_room",

    "RATE_SERVICE": "rating_service",

    "RATE_SLEEP": "rating_sleep",

    "RATE_VALUE": "rating_value"
}


def get_subratings(review):
    """
    Extrae subvaloraciones cuando existen.

    Si alguna no está disponible, se conserva
    como valor nulo, sin inventar puntuaciones.
    """

    result = {
        column: None
        for column in SUBRATING_MAP.values()
    }

    for item in review.get("subratings") or []:

        if not isinstance(item, dict):
            continue

        rating_type = (
            item.get("rating_type")
            or item.get("type")
        )

        if isinstance(rating_type, dict):

            rating_type = (
                rating_type.get("value")
                or rating_type.get("name")
            )

        column = SUBRATING_MAP.get(rating_type)

        if column:

            value = item.get("rating")

            if isinstance(value, dict):

                value = value.get("value")

            result[column] = value

    return result


# ==================================================
# 5. IDENTIFICAR LOS ARCHIVOS RAW
# ==================================================

# Leer todos los archivos descargados automáticamente.

raw_files = sorted(
    RAW_DIR.glob("reviews_*.json")
)

# Incluir el primer archivo del Hotel Riu Plaza España,
# que se guardó con un nombre diferente.

legacy_file = (
    RAW_DIR / "riu_plaza_madrid_reviews.json"
)

if legacy_file.exists():

    raw_files.append(legacy_file)


if not raw_files:

    raise FileNotFoundError(
        "No se encontraron archivos de reseñas en data/raw/"
    )


# ==================================================
# 6. TRANSFORMAR JSON A REGISTROS
# ==================================================

rows = []

print("\nTRANSFORMACIÓN DE RESEÑAS")
print("=" * 60)


for file_path in raw_files:

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    location_id = data.get("location_id")

    establishment = data.get("establishment_name")

    destination = data.get(
        "destination",
        "Madrid"
    )

    reviews = data.get("reviews", [])

    print(
        f"{establishment}: {len(reviews)} reseñas"
    )

    for review in reviews:

        # ------------------------------------------
        # 6.1 INFORMACIÓN DEL USUARIO
        # ------------------------------------------

        user = review.get("user") or {}

        if not isinstance(user, dict):

            user = {}

        # ------------------------------------------
        # 6.2 TÍTULO Y COMENTARIO
        # ------------------------------------------

        title, title_language = get_primary_text(
            review.get("title")
        )

        text, text_language = get_primary_text(
            review.get("text")
        )

        # No conservar reseñas sin comentario.

        if not text:
            continue

        # ------------------------------------------
        # 6.3 IDIOMA
        # ------------------------------------------

        language = (
            text_language
            if text_language != "unknown"
            else title_language
        )

        # ------------------------------------------
        # 6.4 PALABRAS CLAVE
        # ------------------------------------------

        keywords, keyword_status = (
            get_keyword_analysis(
                title,
                text,
                language
            )
        )

        # ------------------------------------------
        # 6.5 TIPO DE VIAJE
        # ------------------------------------------

        trip_type = review.get("trip_type")

        if not trip_type or trip_type == "NONE":

            trip_type = "UNKNOWN"

        # ------------------------------------------
        # 6.6 ORIGEN DEL USUARIO
        # ------------------------------------------

        origin = user.get("geo")

        if isinstance(origin, dict):

            origin = (
                origin.get("name")
                or origin.get("value")
            )

        # ------------------------------------------
        # 6.7 CONSTRUIR REGISTRO
        # ------------------------------------------

        row = {

            "source": data.get(
                "source",
                "tripadvisor"
            ),

            "location_id": location_id,

            "establishment_name": establishment,

            "destination": destination,

            "review_id": review.get("id"),

            "published_at": review.get(
                "publish_ts"
            ),

            "travel_date": review.get(
                "travel_date"
            ),

            "username": user.get("username"),

            "user_origin": origin,

            "trip_type": trip_type,

            "rating": review.get("rating"),

            "review_title": title,

            "review_text": text,

            "language": language,

            "keywords": keywords,

            "keyword_status": keyword_status,

            "review_url": review.get("url"),

            "extracted_at": data.get(
                "extracted_at"
            )
        }

        # Añadir las subvaloraciones disponibles.

        row.update(
            get_subratings(review)
        )

        rows.append(row)


# ==================================================
# 7. CONSTRUIR Y VALIDAR DATAFRAME
# ==================================================

if not rows:

    raise ValueError(
        "No hay reseñas para transformar."
    )


df = pd.DataFrame(rows)

initial_count = len(df)


# --------------------------------------------------
# 7.1 ELIMINAR DUPLICADOS
# --------------------------------------------------

df = df.drop_duplicates(
    subset=["source", "review_id"]
).copy()


# --------------------------------------------------
# 7.2 NORMALIZAR FECHAS
# --------------------------------------------------

# Fecha de publicación con zona horaria UTC.

df["published_at"] = pd.to_datetime(
    df["published_at"],
    errors="coerce",
    utc=True
)

# Mantener travel_date como YYYY-MM
# cuando esté disponible.

# Mantener extracted_at con su valor original:
# los archivos RAW antiguos pueden contener fechas
# sin zona horaria explícita.


# --------------------------------------------------
# 7.3 NORMALIZAR VALORES NUMÉRICOS
# --------------------------------------------------

numeric_columns = [
    "rating",
    *SUBRATING_MAP.values()
]

for column in numeric_columns:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


# --------------------------------------------------
# 7.4 ORDEN DEFINITIVO DE COLUMNAS
# --------------------------------------------------

columns = [

    "source",

    "location_id",

    "establishment_name",

    "destination",

    "review_id",

    "published_at",

    "travel_date",

    "username",

    "user_origin",

    "trip_type",

    "rating",

    "rating_cleanliness",

    "rating_location",

    "rating_room",

    "rating_service",

    "rating_sleep",

    "rating_value",

    "review_title",

    "review_text",

    "language",

    "keywords",

    "keyword_status",

    "review_url",

    "extracted_at"
]

df = df[columns]


# ==================================================
# 8. EXPORTAR DATASET
# ==================================================

df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


# ==================================================
# 9. RESUMEN DE RESULTADOS
# ==================================================

print("\n" + "=" * 60)

print("RESULTADOS")

print("Reseñas originales:", initial_count)

print("Reseñas finales:", len(df))

print(
    "Duplicados eliminados:",
    initial_count - len(df)
)

print(
    "Establecimientos:",
    df["location_id"].nunique()
)

print(
    "Reseñas con fecha de viaje:",
    df["travel_date"].notna().sum()
)

print(
    "Reseñas con subvaloraciones:",
    df[list(SUBRATING_MAP.values())]
    .notna()
    .any(axis=1)
    .sum()
)

print(
    "Reseñas sin keywords:",
    df["keywords"].eq("").sum()
)

print(
    "Estado de detección de keywords:",
    df["keyword_status"].value_counts().to_dict()
)

print(
    "Idiomas:",
    df["language"].value_counts().to_dict()
)

print(
    "Columnas:",
    len(df.columns)
)

print("\nArchivo generado:")
print(OUTPUT_FILE)


# ==================================================
# 10. VISTA PREVIA
# ==================================================

print("\nVista previa:")

print(
    df[
        [
            "establishment_name",
            "rating",
            "language",
            "keywords",
            "keyword_status"
        ]
    ].head(20).to_string(index=False)
)
