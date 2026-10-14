
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv


# ==================================================
# 1. CONFIGURACIÓN
# ==================================================

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

API_KEY = os.getenv("TRIPADVISOR_API_KEY")

MATCHES_FILE = (
    BASE / "data/clean/tripadvisor_matches.csv"
)

RAW_DIR = BASE / "data/raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 0 = comprobar todo sin consultar Tripadvisor.
# Más adelante podremos poner 3, 5 o 10.
MAX_NEW_CALLS = 0


# ==================================================
# 2. LEER HOTELES VERIFICADOS
# ==================================================

if not MATCHES_FILE.exists():
    raise FileNotFoundError(
        f"No existe el archivo: {MATCHES_FILE}"
    )

df = pd.read_csv(
    MATCHES_FILE,
    dtype=str
).fillna("")

required_columns = {
    "hotel_oficial",
    "location_id",
    "estado"
}

if not required_columns.issubset(df.columns):
    raise ValueError(
        "Faltan columnas en tripadvisor_matches.csv"
    )

hotels = df[
    df["estado"].str.strip().str.lower()
    == "verificado"
].copy()

hotels["location_id"] = (
    hotels["location_id"].str.strip()
)

hotels = hotels[
    hotels["location_id"].str.fullmatch(r"\d+")
].copy()

hotels = hotels.drop_duplicates(
    subset=["location_id"]
)

if hotels.empty:
    raise ValueError(
        "No hay hoteles verificados con un ID válido."
    )


# ==================================================
# 3. VARIABLES DE CONTROL
# ==================================================

new_calls = 0
cached_hotels = 0
downloaded_hotels = 0
pending_hotels = 0
total_new_reviews = 0

print("\nEXTRACCIÓN DE RESEÑAS DE TRIPADVISOR")
print("=" * 65)
print("Hoteles verificados:", len(hotels))
print("Máximo de llamadas nuevas:", MAX_NEW_CALLS)


# ==================================================
# 4. RECORRER ESTABLECIMIENTOS
# ==================================================

for _, hotel in hotels.iterrows():

    location_id = hotel["location_id"]

    hotel_name = (
        hotel.get("nombre_tripadvisor")
        or hotel["hotel_oficial"]
    )

    raw_file = (
        RAW_DIR / f"reviews_{location_id}.json"
    )

    print(f"\n{hotel_name} (ID: {location_id})")

    # ----------------------------------------------
    # 4.1 COMPROBAR SI YA ESTÁ DESCARGADO
    # ----------------------------------------------

    if raw_file.exists():

        try:
            with open(
                raw_file,
                encoding="utf-8"
            ) as file:
                cached_data = json.load(file)

            if not isinstance(
                cached_data.get("reviews"),
                list
            ):
                raise ValueError(
                    "Formato RAW incorrecto"
                )

        except (ValueError, OSError) as error:
            print("  Archivo RAW inválido:", error)
            print("  Revisar manualmente.")
            continue

        cached_hotels += 1

        print(
            "  CACHE: reseñas guardadas:",
            len(cached_data["reviews"])
        )

        continue

    # ----------------------------------------------
    # 4.2 CONTROL DEL LÍMITE
    # ----------------------------------------------

    if new_calls >= MAX_NEW_CALLS:

        pending_hotels += 1
        print("  PENDIENTE: no se realiza llamada.")
        continue

    if not API_KEY:
        raise ValueError(
            "Falta TRIPADVISOR_API_KEY en .env"
        )

    # ----------------------------------------------
    # 4.3 CONSULTAR TRIPADVISOR
    # ----------------------------------------------

    if new_calls > 0:
        time.sleep(1.2)

    url = (
        "https://terra.tripadvisor.com/api/"
        f"locations/{location_id}/reviews"
    )

    print("  Descargando reseñas...")

    # Contamos el intento antes de la petición.
    new_calls += 1

    try:
        response = requests.get(
            url,
            headers={
                "X-API-Key": API_KEY,
                "Accept": "application/json"
            },
            params={
                "version": 1,
                "language": "primary",
                "size": 3
            },
            timeout=30
        )

    except requests.RequestException as error:
        print("  Error de conexión:", error)
        print("  Extracción detenida.")
        break

    print("  HTTP:", response.status_code)

    if not response.ok:
        print("  Error:", response.text[:300])
        print("  Extracción detenida.")
        break

    try:
        api_data = response.json()
    except ValueError:
        print("  Respuesta JSON inválida.")
        break

    reviews = api_data.get("data")

    if not isinstance(reviews, list):
        print("  Estructura de reseñas inesperada.")
        break

    # ----------------------------------------------
    # 4.4 GUARDAR JSON ORIGINAL
    # ----------------------------------------------

    output = {
        "source": "tripadvisor",
        "location_id": int(location_id),
        "establishment_name": hotel_name,
        "destination": "Madrid",
        "extracted_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "reviews": reviews
    }

    with open(
        raw_file,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    downloaded_hotels += 1
    total_new_reviews += len(reviews)

    print("  Reseñas obtenidas:", len(reviews))
    print("  Archivo:", raw_file.name)


# ==================================================
# 5. RESUMEN FINAL
# ==================================================

print("\n" + "=" * 65)
print("RESULTADOS")
print("=" * 65)

print("Hoteles verificados:", len(hotels))
print("Hoteles ya descargados:", cached_hotels)
print("Hoteles descargados ahora:", downloaded_hotels)
print("Hoteles pendientes:", pending_hotels)
print("Llamadas nuevas a Terra:", new_calls)
print("Reseñas nuevas:", total_new_reviews)

print("\nLos JSON existentes no se han sobrescrito.")
print("El CSV limpio no se ha modificado.")
