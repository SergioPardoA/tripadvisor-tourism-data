
from pathlib import Path
import requests
import pandas as pd

URL = (
    "https://datos.comunidad.madrid/dataset/"
    "ef437c50-5b26-4843-92c3-d8eef5507fac/"
    "resource/260e80ac-2062-41f6-9f96-4902675b1078/"
    "download/alojamientos_turisticos.csv"
)

RAW_FILE = Path("data/raw/alojamientos_comunidad_madrid.csv")
OUTPUT = Path("data/clean/madrid_hotel_candidates.csv")

RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# Descargar una sola vez
if not RAW_FILE.exists():
    print("Descargando catálogo oficial de alojamientos...")

    response = requests.get(URL, timeout=60)
    print("Código HTTP:", response.status_code)

    if not response.ok:
        print("Error:", response.text[:300])
        raise SystemExit("No se ha podido descargar el catálogo.")

    RAW_FILE.write_bytes(response.content)
else:
    print("Utilizando catálogo descargado previamente.")

# Leer el CSV
for encoding in ("utf-8-sig", "cp1252", "latin-1"):
    try:
        df = pd.read_csv(
            RAW_FILE,
            sep=None,
            engine="python",
            encoding=encoding,
            dtype=str
        )
        break
    except UnicodeDecodeError:
        continue

df.columns = df.columns.str.strip().str.lower()

print("\nColumnas:", df.columns.tolist())
print("Total de alojamientos:", len(df))

# Seleccionar municipio de Madrid
madrid = df[
    df["localidad"].fillna("").str.strip().str.casefold() == "madrid"
].copy()

# Seleccionar establecimientos de tipo hotel
hotels = madrid[
    madrid["alojamiento_tipo"].fillna("").str.contains(
        "hotel", case=False, regex=False
    )
].copy()

hotels = hotels.dropna(subset=["denominacion"])

hotels.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

print("\nHoteles encontrados en Madrid:", len(hotels))
print("\nPrimeros establecimientos:")
print(
    hotels[
        ["denominacion", "alojamiento_tipo", "via_nombre"]
    ].head(10).to_string(index=False)
)

print("\nArchivo generado:", OUTPUT)
print("No se ha consultado Tripadvisor.")
