
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



# ==================================================
# 3. FUNCIONES DE LIMPIEZA
# ==================================================

def clean_text(text):
    """Elimina saltos de línea y espacios repetidos."""
    if not isinstance(text, str):
        return ""

    return " ".join(text.split())


def normalize_text(text):
    """Convierte a minúsculas y elimina tildes."""
    text = unicodedata.normalize(
        "NFD", text.lower()
    )

    return "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )


def identify_keywords(text):
    """Identifica categorías mediante palabras clave."""
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


def get_primary_text(items):
    """Obtiene texto e idioma de la variante principal."""
    if not isinstance(items, list) or not items:
        return "", "unknown"

    valid_items = [
        item for item in items
        if isinstance(item, dict)
    ]

    if not valid_items:
        return "", "unknown"

    selected = next(
        (
            item for item in valid_items
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
    """Extrae subvaloraciones cuando existen."""

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

raw_files = sorted(
    RAW_DIR.glob("reviews_*.json")
)

# Incluimos el primer archivo del Riu Plaza España.
legacy_file = RAW_DIR / "riu_plaza_madrid_reviews.json"

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

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    location_id = data.get("location_id")
    establishment = data.get("establishment_name")
    destination = data.get("destination", "Madrid")

    reviews = data.get("reviews", [])

    print(f"{establishment}: {len(reviews)} reseñas")

    for review in reviews:

        user = review.get("user") or {}
        if not isinstance(user, dict):
            user = {}

        title, title_language = get_primary_text(
            review.get("title")
        )

        text, text_language = get_primary_text(
            review.get("text")
        )

        # No conservamos comentarios sin texto.
        if not text:
            continue

        language = (
            text_language
            if text_language != "unknown"
            else title_language
        )

        trip_type = review.get("trip_type")

        if not trip_type or trip_type == "NONE":
            trip_type = "UNKNOWN"

        origin = user.get("geo")

        if isinstance(origin, dict):
            origin = (
                origin.get("name")
                or origin.get("value")
            )

        row = {
            "source": data.get("source", "tripadvisor"),
            "location_id": location_id,
            "establishment_name": establishment,
            "destination": destination,
            "review_id": review.get("id"),
            "published_at": review.get("publish_ts"),
            "travel_date": review.get("travel_date"),
            "username": user.get("username"),
            "user_origin": origin,
            "trip_type": trip_type,
            "rating": review.get("rating"),
            "review_title": title,
            "review_text": text,
            "language": language,
            "keywords": identify_keywords(
                title + " " + text
            ),
            "review_url": review.get("url"),
            "extracted_at": data.get("extracted_at")
        }

        row.update(get_subratings(review))
        rows.append(row)


# ==================================================
# 7. CONSTRUIR Y VALIDAR DATAFRAME
# ==================================================

if not rows:
    raise ValueError("No hay reseñas para transformar.")

df = pd.DataFrame(rows)

initial_count = len(df)

# Eliminar reseñas duplicadas.
df = df.drop_duplicates(
    subset=["source", "review_id"]
).copy()

# Fechas de publicación con zona horaria UTC.
df["published_at"] = pd.to_datetime(
    df["published_at"],
    errors="coerce",
    utc=True
)

# Mantener travel_date como YYYY-MM cuando exista.
# Mantener extracted_at original: los JSON antiguos
# pueden contener fechas sin zona horaria explícita.

numeric_columns = [
    "rating",
    *SUBRATING_MAP.values()
]

for column in numeric_columns:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )

# Orden de columnas.
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
    "review_url",
    "extracted_at"
]

df = df[columns]

# ==================================================
# 8. EXPORTAR Y MOSTRAR RESULTADOS
# ==================================================

df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)

print("\n" + "=" * 60)
print("RESULTADOS")

print("Reseñas originales:", initial_count)
print("Reseñas finales:", len(df))
print("Duplicados eliminados:", initial_count - len(df))
print("Establecimientos:", df["location_id"].nunique())
print("Reseñas con fecha de viaje:", df["travel_date"].notna().sum())
print("Reseñas con subvaloraciones:", df[
    list(SUBRATING_MAP.values())
].notna().any(axis=1).sum())
print("Reseñas sin keywords:", df["keywords"].eq("").sum())
print("Idiomas:", df["language"].value_counts().to_dict())

print("\nArchivo generado:")
print(OUTPUT_FILE)

print("\nVista previa:")
print(df[
    [
        "establishment_name",
        "rating",
        "language",
        "keywords"
    ]
].to_string(index=False))
