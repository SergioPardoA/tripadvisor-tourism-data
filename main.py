import os
from dotenv import load_dotenv

# Carga las variables guardadas en el archivo .env
load_dotenv()

# Lee la API key sin mostrarla
api_key = os.getenv("TRIPADVISOR_API_KEY")

if api_key:
    print("API key cargada correctamente.")
else:
    print("ERROR: no se encontró la API key.")