
import csv
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv


# ==================================================
# 1. CONFIGURACIÓN
# ==================================================

BASE = Path(__file__).resolve().parent

MATCHES_FILE = (
    BASE / "data" / "clean" / "tripadvisor_matches.csv"
)

REVIEWS_FILE = (
    BASE / "data" / "clean" / "tripadvisor_reviews.csv"
)

load_dotenv(BASE / ".env")


# ==================================================
# 2. FUNCIONES AUXILIARES
# ==================================================

def leer_csv(ruta):
    """Lee un CSV conservando los identificadores como texto."""

    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encuentra el archivo: {ruta}"
        )

    with open(
        ruta,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as archivo:

        return list(csv.DictReader(archivo))


def valor(fila, columna):
    """Convierte los campos vacíos en valores nulos."""

    dato = fila.get(columna)

    if dato is None:
        return None

    dato = dato.strip()

    return dato if dato else None


def convertir_fecha(dato):
    """Convierte fechas a objetos con zona horaria UTC."""

    if dato is None:
        return None

    fecha = datetime.fromisoformat(
        dato.replace("Z", "+00:00")
    )

    if fecha.tzinfo is None:
        # Convención para fechas antiguas sin zona horaria.
        fecha = fecha.replace(tzinfo=timezone.utc)

    return fecha.astimezone(timezone.utc)


# ==================================================
# 3. LEER LOS ARCHIVOS
# ==================================================

matches = leer_csv(MATCHES_FILE)
reviews = leer_csv(REVIEWS_FILE)

print("\nIMPORTACIÓN A POSTGRESQL")
print("=" * 55)

print("Registros de coincidencias:", len(matches))
print("Reseñas del CSV:", len(reviews))


# ==================================================
# 4. PREPARAR ESTABLECIMIENTOS
# ==================================================

establecimientos = {}

for hotel in matches:

    if valor(hotel, "estado") != "verificado":
        continue

    location_id = int(
        valor(hotel, "location_id")
    )

    establecimientos[location_id] = (
        location_id,
        valor(hotel, "nombre_tripadvisor"),
        valor(hotel, "hotel_oficial"),
        valor(hotel, "direccion_tripadvisor"),
        "catalogo_verificado"
    )


# Añadir alojamientos presentes en las reseñas
# que no estaban en el catálogo verificado.

for review in reviews:

    location_id = int(
        valor(review, "location_id")
    )

    if location_id not in establecimientos:

        establecimientos[location_id] = (
            location_id,
            valor(review, "establishment_name"),
            None,
            None,
            "resenas_iniciales"
        )


print(
    "Establecimientos preparados:",
    len(establecimientos)
)


# ==================================================
# 5. COLUMNAS DE RESEÑAS
# ==================================================

REVIEW_COLUMNS = [
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

NUMERIC_COLUMNS = {
    "rating",
    "rating_cleanliness",
    "rating_location",
    "rating_room",
    "rating_service",
    "rating_sleep",
    "rating_value"
}

DATE_COLUMNS = {
    "published_at",
    "extracted_at"
}


# ==================================================
# 6. CONECTAR E IMPORTAR
# ==================================================

with psycopg.connect(
    host=os.getenv("PGHOST"),
    port=os.getenv("PGPORT"),
    dbname=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD")
) as conexion:

    with conexion.cursor() as cursor:

        # Comprobar que trabajamos en la base correcta.
        cursor.execute("SELECT current_database()")

        nombre_bd = cursor.fetchone()[0]

        if nombre_bd != "turismo_madrid":
            raise RuntimeError(
                f"Base de datos incorrecta: {nombre_bd}"
            )

        cursor.execute("SET TIME ZONE 'UTC'")

        # ------------------------------------------
        # 6.1 INSERTAR ESTABLECIMIENTOS
        # ------------------------------------------

        sql_establecimiento = """
            INSERT INTO public.establecimientos (
                location_id,
                nombre_tripadvisor,
                nombre_oficial,
                direccion_tripadvisor,
                origen_registro
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (location_id) DO NOTHING
        """

        nuevos_establecimientos = 0

        for hotel in establecimientos.values():

            cursor.execute(
                sql_establecimiento,
                hotel
            )

            nuevos_establecimientos += cursor.rowcount

        print(
            "Establecimientos nuevos insertados:",
            nuevos_establecimientos
        )

        # ------------------------------------------
        # 6.2 INSERTAR RESEÑAS
        # ------------------------------------------

        nombres_columnas = ", ".join(REVIEW_COLUMNS)

        marcadores = ", ".join(
            ["%s"] * len(REVIEW_COLUMNS)
        )

        sql_resena = f"""
            INSERT INTO public.resenas (
                {nombres_columnas}
            )
            VALUES ({marcadores})
            ON CONFLICT (source, location_id, review_id)
            DO NOTHING
        """

        nuevas_resenas = 0

        for review in reviews:

            datos = []

            for columna in REVIEW_COLUMNS:

                dato = valor(review, columna)

                if columna == "location_id":

                    dato = int(dato)

                elif columna in NUMERIC_COLUMNS:

                    dato = (
                        Decimal(dato)
                        if dato is not None
                        else None
                    )

                elif columna in DATE_COLUMNS:

                    dato = convertir_fecha(dato)

                datos.append(dato)

            cursor.execute(
                sql_resena,
                datos
            )

            nuevas_resenas += cursor.rowcount

        print(
            "Reseñas nuevas insertadas:",
            nuevas_resenas
        )

        # ------------------------------------------
        # 6.3 VERIFICAR LOS TOTALES
        # ------------------------------------------

        cursor.execute(
            "SELECT COUNT(*) FROM public.establecimientos"
        )

        total_establecimientos = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM public.resenas"
        )

        total_resenas = cursor.fetchone()[0]

        print("\nRESULTADO EN POSTGRESQL")
        print("=" * 55)

        print(
            "Total establecimientos:",
            total_establecimientos
        )

        print(
            "Total reseñas:",
            total_resenas
        )

        print("\nImportación completada correctamente.")

# La transacción se confirma al salir del bloque
# si no se ha producido ningún error.
