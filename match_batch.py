
import os
import re
import json
import time
import hashlib
import unicodedata

from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# 1. CONFIGURACIÓN
# ============================================================

BASE = Path(__file__).resolve().parent

load_dotenv(BASE / ".env")

API_KEY = os.getenv("TRIPADVISOR_API_KEY")

CATALOGO = BASE / "data/clean/madrid_hotel_candidates.csv"
CACHE = BASE / "data/raw/matching"
SALIDA = BASE / "data/clean/tripadvisor_matches.csv"

CACHE.mkdir(parents=True, exist_ok=True)
SALIDA.parent.mkdir(parents=True, exist_ok=True)

URL = "https://terra.tripadvisor.com/api/catalog/locations/search"

# IMPORTANTE:
# 0 = utilizar únicamente las respuestas guardadas.
# 5 = permitir hasta 5 búsquedas nuevas.
MAX_NEW_CALLS = 0

# Hoteles consultados anteriormente fuera de este script.
YA_PROBADOS = {
    "NH ALONSO MARTINEZ",
    "HOTEL BARCELO EMPERATRIZ",
    "VINCCI CAPITOL"
}


# ============================================================
# 2. NORMALIZACIÓN DE TEXTO
# ============================================================

def normalizar(texto):
    """
    Convierte texto a minúsculas, elimina tildes,
    puntuación y espacios repetidos.
    """

    texto = unicodedata.normalize(
        "NFD",
        str(texto).lower()
    )

    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def normalizar_hotel(nombre):
    """
    Elimina el prefijo HOTEL cuando está al inicio.

    Ejemplos:
    HOTEL SANCHO -> sancho
    Hotel Sancho -> sancho
    """

    nombre = normalizar(nombre)

    return re.sub(
        r"^hotel\s+",
        "",
        nombre
    )


def normalizar_direccion(direccion):
    """
    Elimina artículos y preposiciones que pueden
    variar entre las fuentes.

    Ejemplos:
    de las Delicias -> delicias
    de San Bernardo -> san bernardo
    """

    direccion = normalizar(direccion)

    direccion = re.sub(
        r"\b(de|del|la|las|el|los)\b",
        " ",
        direccion
    )

    return " ".join(direccion.split())


# ============================================================
# 3. EXTRAER INFORMACIÓN DE TRIPADVISOR
# ============================================================

def nombre_principal(location):

    nombres = location.get("names") or []

    if not nombres:
        return ""

    elegido = next(
        (
            nombre
            for nombre in nombres
            if nombre.get("primary") is True
        ),
        nombres[0]
    )

    return elegido.get("value") or ""


def direccion_principal(location):

    direcciones = location.get("addresses") or []

    if not direcciones:
        return ""

    return direcciones[0].get("formatted") or ""


def url_principal(location):

    return (
        location.get("urls", {})
        .get("tripadvisor", {})
        .get("main", "")
    ) or ""


# ============================================================
# 4. VALIDAR COINCIDENCIAS
# ============================================================

def evaluar_candidato(fila, location):
    """
    Compara un hotel del catálogo oficial con
    un establecimiento encontrado en Tripadvisor.

    Se comprueban:
    - Similitud de nombres.
    - Inclusión del nombre dentro de otro más largo.
    - Calle.
    - Número de portal.
    - Código postal.
    - Tipo de establecimiento.
    """

    nombre_api = nombre_principal(location)
    direccion_api = direccion_principal(location)

    # --------------------------------------------------------
    # 4.1 COMPARACIÓN DE NOMBRES
    # --------------------------------------------------------

    nombre_oficial = normalizar_hotel(
        fila["denominacion"]
    )

    nombre_tripadvisor = normalizar_hotel(
        nombre_api
    )

    similitud = SequenceMatcher(
        None,
        nombre_oficial,
        nombre_tripadvisor
    ).ratio()

    # Reconocer nombres que aparecen dentro de
    # denominaciones comerciales más largas.
    #
    # Ejemplos:
    # CARLTON -> AC Hotel Carlton Madrid
    # EMPERADOR -> Emperador Hotel Madrid

    palabras_oficial = set(
        nombre_oficial.split()
    )

    palabras_tripadvisor = set(
        nombre_tripadvisor.split()
    )

    nombre_contenido = (
        bool(palabras_oficial)
        and palabras_oficial.issubset(
            palabras_tripadvisor
        )
        and any(
            len(palabra) >= 4
            for palabra in palabras_oficial
        )
    )

    # Palabras distintivas que comparten ambos nombres.
    # Evitamos palabras demasiado genéricas.

    PALABRAS_GENERICAS = {
        "hotel", "hostal", "madrid",
        "apartamentos", "apartments",
        "boutique", "resort"
    }

    palabras_comunes = (
        palabras_oficial
        & palabras_tripadvisor
    ) - PALABRAS_GENERICAS

    nombre_parcial_coincide = any(
        len(palabra) >= 5
        for palabra in palabras_comunes
    )

    nombre_coincide = (
        similitud >= 0.85
        or nombre_contenido
        or nombre_parcial_coincide
    )

    # --------------------------------------------------------
    # 4.2 COMPARACIÓN DE CALLES
    # --------------------------------------------------------

    calle_oficial = normalizar_direccion(
        fila["via_nombre"]
    )

    direccion_tripadvisor = normalizar_direccion(
        direccion_api
    )

    calle_coincide = bool(
        calle_oficial
        and calle_oficial in direccion_tripadvisor
    )

    # --------------------------------------------------------
    # 4.3 COMPARACIÓN DEL NÚMERO
    # --------------------------------------------------------

    numero = normalizar(
        fila["numero"]
    )

    numero_coincide = bool(
        numero
        and re.search(
            rf"\b{re.escape(numero)}\b",
            direccion_tripadvisor
        )
    )

    # Permite reconocer:
    # Número oficial 29
    # Dirección Tripadvisor 29-31

    # --------------------------------------------------------
    # 4.4 COMPARACIÓN DEL CÓDIGO POSTAL
    # --------------------------------------------------------

    codigo_postal = str(
        fila["cdpostal"]
    ).strip()

    if codigo_postal:
        # Si el catálogo tiene código postal,
        # exigimos que coincida con Tripadvisor.
        postal_coincide = bool(
            re.search(
                rf"\b{re.escape(codigo_postal)}\b",
                direccion_tripadvisor
            )
        )
    else:
        # Si falta en el catálogo, no rechazamos
        # automáticamente el establecimiento.
        # La calle, el número y el nombre
        # siguen siendo obligatorios.
        postal_coincide = True

    # --------------------------------------------------------
    # 4.5 COMPROBAR QUE SEA ALOJAMIENTO
    # --------------------------------------------------------

    url = url_principal(location)

    es_alojamiento = "Hotel_Review" in url

    # --------------------------------------------------------
    # 4.6 DECISIÓN
    # --------------------------------------------------------

    valido = (
        nombre_coincide
        and calle_coincide
        and numero_coincide
        and postal_coincide
        and es_alojamiento
        and location.get("id") is not None
    )


    # Cambios de nombre confirmados en la web oficial de NH.
    # Son excepciones documentadas, no reglas generales.

    NOMBRES_HISTORICOS = {
        "NH SUR": "NH Madrid Atocha",
        "NH SANVY": "NH Collection Madrid Colón"
    }

    nombre_oficial_original = fila["denominacion"].strip().upper()

    nombre_actual_confirmado = NOMBRES_HISTORICOS.get(
        nombre_oficial_original
    )

    if nombre_actual_confirmado:
        if (
            normalizar(nombre_api)
            == normalizar(nombre_actual_confirmado)
            and postal_coincide
            and es_alojamiento
            and location.get("id") is not None
        ):
            valido = True


    return {
        "location_id": location.get("id"),
        "nombre_tripadvisor": nombre_api,
        "direccion_tripadvisor": direccion_api,
        "similitud": round(similitud, 3),
        "nombre_coincide": nombre_coincide,
        "calle_coincide": calle_coincide,
        "numero_coincide": numero_coincide,
        "postal_coincide": postal_coincide,
        "es_alojamiento": es_alojamiento,
        "valido": valido
    }


# ============================================================
# 5. CARGAR CATÁLOGO OFICIAL
# ============================================================

df = pd.read_csv(
    CATALOGO,
    dtype=str
).fillna("")

print("\nEMPAREJAMIENTO AUTOMÁTICO")
print("=" * 65)

print("Hoteles en el catálogo:", len(df))
print("Máximo de nuevas llamadas API:", MAX_NEW_CALLS)


# ============================================================
# 6. RECUPERAR RESULTADOS ANTERIORES
# ============================================================

resultados = {}

if SALIDA.exists():

    anteriores = pd.read_csv(
        SALIDA,
        dtype=str
    ).fillna("")

    for _, fila_anterior in anteriores.iterrows():

        clave = (
            fila_anterior["hotel_oficial"]
            .strip()
            .upper()
        )

        resultados[clave] = fila_anterior.to_dict()

    print(
        "Resultados anteriores recuperados:",
        len(resultados)
    )


# Conservar Vincci Capitol, verificado en
# nuestra primera prueba de búsqueda.

resultados.setdefault(
    "VINCCI CAPITOL",
    {
        "hotel_oficial": "VINCCI CAPITOL",
        "location_id": "228509",
        "nombre_tripadvisor": "Vincci Capitol",
        "direccion_tripadvisor": "Calle Gran Via 41, Madrid",
        "estado": "verificado"
    }
)


# ============================================================
# 7. FUNCIÓN PARA GUARDAR LOS RESULTADOS
# ============================================================

def guardar_resultados():

    if not resultados:
        return

    salida = pd.DataFrame(
        list(resultados.values())
    )

    columnas = [
        "hotel_oficial",
        "location_id",
        "nombre_tripadvisor",
        "direccion_tripadvisor",
        "estado"
    ]

    salida = salida.reindex(
        columns=columnas
    )

    # Guardar los identificadores como enteros,
    # evitando valores como 228509.0

    salida["location_id"] = pd.to_numeric(
        salida["location_id"],
        errors="coerce"
    ).astype("Int64")

    salida = salida.sort_values(
        ["estado", "hotel_oficial"]
    )

    # Archivo temporal para evitar que una
    # escritura interrumpida dañe el CSV principal.

    temporal = SALIDA.with_suffix(".tmp")

    salida.to_csv(
        temporal,
        index=False,
        encoding="utf-8-sig"
    )

    temporal.replace(SALIDA)

    return salida


# ============================================================
# 8. RECORRER HOTELES DEL CATÁLOGO
# ============================================================

llamadas = 0
cache_utilizada = 0
sin_cache = 0

for _, fila in df.iterrows():

    nombre = fila["denominacion"].strip()

    if not nombre:
        continue

    clave_nombre = nombre.upper()

    # Evitar consultas ya realizadas fuera del script.
    if clave_nombre in YA_PROBADOS:
        continue

    # --------------------------------------------------------
    # 8.1 PARÁMETROS DE BÚSQUEDA
    # --------------------------------------------------------

    params = {
        "version": 1,
        "query": nombre,
        "search_type": "NAME",
        "geo_name": "Madrid",
        "country_code": "ES",
        "category": "HOTEL",
        "size": 5
    }

    # La clave depende de los parámetros.
    # Así reutilizamos las respuestas anteriores.

    clave_cache = hashlib.sha256(
        json.dumps(
            params,
            sort_keys=True
        ).encode()
    ).hexdigest()[:20]

    archivo_cache = CACHE / f"{clave_cache}.json"

    # --------------------------------------------------------
    # 8.2 UTILIZAR CACHÉ
    # --------------------------------------------------------

    if archivo_cache.exists():

        with open(
            archivo_cache,
            "r",
            encoding="utf-8"
        ) as archivo:

            respuesta = json.load(archivo)

        origen = "CACHE"
        cache_utilizada += 1

    # --------------------------------------------------------
    # 8.3 REALIZAR CONSULTA NUEVA
    # --------------------------------------------------------

    else:

        if llamadas >= MAX_NEW_CALLS:

            sin_cache += 1
            continue

        if not API_KEY:

            raise ValueError(
                "Falta TRIPADVISOR_API_KEY en .env"
            )

        if llamadas > 0:
            time.sleep(1.2)

        print(f"\nConsultando: {nombre}")

        try:

            response = requests.get(
                URL,
                headers={
                    "X-API-Key": API_KEY,
                    "Accept": "application/json"
                },
                params=params,
                timeout=30
            )

        except requests.RequestException as error:

            print("Error de conexión:", error)
            break

        llamadas += 1

        print("HTTP:", response.status_code)

        if not response.ok:

            print("Error:", response.text[:500])
            print("Deteniendo las nuevas consultas.")
            break

        try:
            respuesta = response.json()

        except ValueError:
            print("La API no devolvió JSON válido.")
            break

        # Guardar inmediatamente la respuesta RAW.

        with open(
            archivo_cache,
            "w",
            encoding="utf-8"
        ) as archivo:

            json.dump(
                respuesta,
                archivo,
                ensure_ascii=False,
                indent=2
            )

        origen = "API"

    # --------------------------------------------------------
    # 8.4 EVALUAR CANDIDATOS
    # --------------------------------------------------------

    candidatos = []

    for item in respuesta.get("data", []):

        location = item.get(
            "location",
            item
        )

        candidatos.append(
            evaluar_candidato(
                fila,
                location
            )
        )

    validos = [
        candidato
        for candidato in candidatos
        if candidato["valido"]
    ]

    # Evitar contar dos veces el mismo location_id.

    validos_unicos = {
        str(candidato["location_id"]): candidato
        for candidato in validos
    }

    # --------------------------------------------------------
    # 8.5 DECISIÓN FINAL
    # --------------------------------------------------------

    if len(validos_unicos) == 1:

        elegido = next(
            iter(validos_unicos.values())
        )

        estado = "verificado"

    elif candidatos:

        elegido = max(
            candidatos,
            key=lambda candidato: candidato["similitud"]
        )

        estado = "revisar"

    else:

        elegido = {}
        estado = "sin_resultados"

    # Solo guardamos el ID si ha sido verificado.

    resultados[clave_nombre] = {
        "hotel_oficial": nombre,

        "location_id": (
            elegido.get("location_id")
            if estado == "verificado"
            else None
        ),

        "nombre_tripadvisor": elegido.get(
            "nombre_tripadvisor", ""
        ),

        "direccion_tripadvisor": elegido.get(
            "direccion_tripadvisor", ""
        ),

        "estado": estado
    }

    print(
        f"{origen} | {nombre} -> {estado}"
    )

    # Guardar después de cada hotel procesado.
    # Así no perdemos resultados si detenemos
    # el programa antes de terminar.

    guardar_resultados()


# ============================================================
# 9. RESUMEN FINAL
# ============================================================

salida = pd.DataFrame(list(resultados.values()))

print("\n" + "=" * 65)
print("RESULTADOS")
print("=" * 65)

print("Llamadas nuevas:", llamadas)
print("Respuestas reutilizadas de caché:", cache_utilizada)

print(
    "Hoteles verificados:",
    (salida["estado"] == "verificado").sum()
)

print(
    "Pendientes de revisión:",
    (salida["estado"] == "revisar").sum()
)

print(
    "Sin resultados:",
    (salida["estado"] == "sin_resultados").sum()
)

print(
    "Hoteles sin caché que no se consultaron:",
    sin_cache
)

print("\nArchivo generado:")
print(SALIDA)

print("\nDetalle:")
print(
    salida.to_string(index=False)
)
