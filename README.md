# Tripadvisor Tourism Data

**Proyecto académico — Ciclo del Dato**

## 1. Descripción del proyecto

Este proyecto desarrolla un proceso de extracción, transformación y almacenamiento de datos turísticos utilizando Python y PostgreSQL.

La fuente principal es la API Terra de Tripadvisor, que proporciona información sobre establecimientos turísticos y sus reseñas.

El objetivo es construir un conjunto de datos estructurado y consultable que pueda integrarse posteriormente con otras fuentes de información turística.

## 2. Fuentes de datos

**Catálogo de alojamientos de la Comunidad de Madrid**

Se utiliza para obtener un listado inicial de establecimientos y sus datos identificativos.

**Tripadvisor Terra API**

Se utiliza para localizar establecimientos y obtener sus reseñas, valoraciones, fechas y otros atributos disponibles.

## 3. Arquitectura del proceso

El proyecto sigue las siguientes etapas:

1. **Descubrimiento:** obtención del catálogo oficial de alojamientos.
2. **Identificación:** búsqueda y correspondencia de establecimientos con Tripadvisor.
3. **Extracción:** descarga de reseñas en formato JSON.
4. **Transformación:** limpieza, normalización y clasificación temática de las reseñas.
5. **Almacenamiento:** importación de establecimientos y reseñas a PostgreSQL.
6. **Consulta:** utilización de SQL para analizar los datos almacenados.

Los archivos originales se conservan separadamente de los datos transformados para permitir la trazabilidad del proceso.

## 4. Scripts principales

| Archivo | Función |
|---|---|
| `discover_hotels.py` | Descarga y prepara los establecimientos candidatos de Madrid. |
| `match_batch.py` | Busca y verifica correspondencias entre el catálogo oficial y Tripadvisor. |
| `download_reviews.py` | Descarga reseñas mediante la API Terra y conserva los JSON obtenidos. |
| `transform.py` | Limpia las reseñas y genera un CSV estructurado. |
| `schema.sql` | Define las tablas y relaciones de PostgreSQL. |
| `import_to_postgres.py` | Importa los datos transformados a PostgreSQL y evita duplicados. |

## 5. Datos obtenidos

La primera versión del proyecto contiene:

| Indicador | Resultado |
|---|---:|
| Hoteles candidatos en Madrid | 366 |
| Hoteles identificados en Tripadvisor | 60 |
| Establecimientos almacenados en PostgreSQL | 64 |
| Establecimientos con reseñas | 63 |
| Reseñas almacenadas | 188 |
| Columnas del CSV de reseñas | 24 |

Los 64 establecimientos incluyen cuatro alojamientos procedentes de las pruebas iniciales que no forman parte de los 60 hoteles identificados en el catálogo.

## 6. Tratamiento de las reseñas

El proceso de transformación conserva la información disponible sobre:

- Identificadores de establecimientos y reseñas.
- Fechas de publicación, viaje y extracción.
- Usuario y origen, cuando están disponibles.
- Texto y título de la reseña.
- Idioma y valoración general.
- Subvaloraciones específicas, cuando existen.
- Categorías temáticas y estado de clasificación.

### Clasificación temática

Se utiliza un diccionario de palabras clave en español e inglés con siete categorías: limpieza, servicio, precio, ubicación, habitación, ruido y desayuno.

La columna `keyword_status` distingue tres situaciones:

| Estado | Significado |
|---|---|
| `detectado` | Se encontró al menos una categoría en español o inglés. |
| `sin_coincidencias` | No se identificaron categorías en un idioma cubierto. |
| `idioma_no_cubierto` | La reseña está en un idioma fuera del alcance del diccionario. |

Esta clasificación identifica temas mencionados. **No constituye un análisis de sentimiento ni garantiza la precisión de todas las categorías asignadas.**

## 7. Base de datos PostgreSQL

La base de datos local se denomina `turismo_madrid` y contiene dos tablas principales:

**`establecimientos`**

Almacena el identificador de Tripadvisor, nombre, dirección y procedencia del registro.

**`resenas`**

Almacena los comentarios, fechas, valoraciones, usuarios y palabras clave.

Ambas tablas se relacionan mediante `location_id`, que identifica al establecimiento en Tripadvisor.

La base de datos utiliza claves primarias y una clave foránea para evitar duplicados y mantener la integridad referencial.

## 8. Instalación y configuración

El proyecto utiliza Python 3.12, PostgreSQL y las dependencias incluidas en `requirements.txt`.

Para instalar las dependencias de Python:

`python -m pip install -r requirements.txt`

Es necesario disponer de PostgreSQL Server y crear una base de datos denominada `turismo_madrid`.

El archivo `schema.sql` puede ejecutarse en pgAdmin para generar las tablas necesarias.

### Variables de entorno

La configuración privada se almacena en un archivo `.env` situado en la raíz del proyecto.

Variables utilizadas:

| Variable | Finalidad |
|---|---|
| `TRIPADVISOR_API_KEY` | Credencial de acceso a Terra API. |
| `PGHOST` | Servidor de PostgreSQL. |
| `PGPORT` | Puerto de conexión. |
| `PGDATABASE` | Nombre de la base de datos. |
| `PGUSER` | Usuario de PostgreSQL. |
| `PGPASSWORD` | Contraseña del usuario. |

El archivo `.env` no debe publicarse ni incorporarse al repositorio.

## 9. Ejecución del proyecto

Los scripts se ejecutan desde la carpeta raíz del proyecto, con el entorno virtual activado.

**Extracción y transformación:**

1. `python discover_hotels.py`
2. `python match_batch.py`
3. `python download_reviews.py`
4. `python transform.py`

Las nuevas llamadas a Terra están limitadas mediante `MAX_NEW_CALLS` en los scripts correspondientes. En la versión actual se han detenido las nuevas consultas para evitar consumos accidentales.

La reproducción de una extracción nueva requiere acceso válido a la API, disponibilidad del servicio y cuota suficiente.

**Almacenamiento en PostgreSQL:**

Una vez creadas las tablas mediante `schema.sql` y disponibles los CSV transformados:

`python import_to_postgres.py`

La importación utiliza `ON CONFLICT DO NOTHING` para evitar que una segunda ejecución inserte nuevamente los mismos establecimientos y reseñas.

## 10. Verificaciones realizadas

La versión inicial ha superado las siguientes comprobaciones:

| Verificación | Resultado |
|---|---|
| Reseñas duplicadas en CSV | 0 |
| Identificadores duplicados de hoteles verificados | 0 |
| Valoraciones generales inválidas | 0 |
| Comentarios vacíos | 0 |
| Fechas de publicación inválidas | 0 |
| Fechas de extracción inválidas | 0 |
| Reseñas sin establecimiento relacionado en PostgreSQL | 0 |
| Registros duplicados al repetir la importación | 0 |

También se ha comprobado que PostgreSQL permite consultar conjuntamente los establecimientos y las reseñas mediante SQL.

## 11. Limitaciones

La API Terra, bajo las condiciones de acceso utilizadas, ha proporcionado un máximo de tres reseñas por establecimiento consultado. Por tanto, el dataset no representa la totalidad de las opiniones publicadas en Tripadvisor.

Los datos se consideran adecuados para demostrar el proceso técnico de extracción, transformación y almacenamiento, pero no para establecer conclusiones estadísticamente representativas sobre todos los hoteles de Madrid.

Las coincidencias entre establecimientos se basan en identificadores, nombres y direcciones, con revisión manual de determinados cambios de denominación comercial.

El análisis de palabras clave se limita al español y al inglés. Las reseñas en otros idiomas se conservan, pero no se clasifican temáticamente de forma fiable.

Las palabras clave se aplican sobre las reseñas recuperadas; no constituyen una búsqueda libre sobre todas las reseñas de Tripadvisor.

## 12. Disponibilidad y reproducción de los datos

Por razones de seguridad y para respetar las condiciones aplicables a los datos de terceros, los archivos JSON y CSV no se publican en este repositorio.

Las carpetas `data/raw/` y `data/clean/` están excluidas de Git.

Para ejecutar la importación es necesario disponer previamente de los CSV generados por el proceso o regenerarlos mediante las fuentes autorizadas. Una instalación limpia del repositorio no produce automáticamente los mismos 188 comentarios.

La base PostgreSQL local tampoco se publica en GitHub. El archivo `schema.sql` permite recrear su estructura.

## 13. Integración con otras fuentes

El proyecto constituye el componente Tripadvisor de un trabajo grupal sobre el ciclo del dato en turismo.

La integración futura con otras fuentes requerirá definir identificadores y dimensiones comunes, como establecimientos, territorios o períodos temporales. La utilización de una misma base de datos no implica que todas las fuentes sean directamente relacionables.