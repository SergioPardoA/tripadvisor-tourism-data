
-- ==========================================
-- PROYECTO: CICLO DEL DATO
-- FUENTE: TRIPADVISOR
-- BASE DE DATOS: turismo_madrid
-- ==========================================

-- TABLA 1: ESTABLECIMIENTOS

CREATE TABLE IF NOT EXISTS public.establecimientos (

    location_id BIGINT PRIMARY KEY,

    nombre_tripadvisor TEXT NOT NULL,

    nombre_oficial TEXT,

    direccion_tripadvisor TEXT,

    origen_registro TEXT NOT NULL

);


-- TABLA 2: RESEÑAS

CREATE TABLE IF NOT EXISTS public.resenas (

    source TEXT NOT NULL,

    location_id BIGINT NOT NULL,

    establishment_name TEXT,

    destination TEXT,

    review_id TEXT NOT NULL,

    published_at TIMESTAMPTZ,

    travel_date VARCHAR(7),

    username TEXT,

    user_origin TEXT,

    trip_type TEXT,

    rating NUMERIC(3,1),

    rating_cleanliness NUMERIC(3,1),

    rating_location NUMERIC(3,1),

    rating_room NUMERIC(3,1),

    rating_service NUMERIC(3,1),

    rating_sleep NUMERIC(3,1),

    rating_value NUMERIC(3,1),

    review_title TEXT,

    review_text TEXT NOT NULL,

    language TEXT,

    keywords TEXT,

    keyword_status TEXT,

    review_url TEXT,

    extracted_at TIMESTAMPTZ,

    CONSTRAINT pk_resenas
        PRIMARY KEY (source, location_id, review_id),

    CONSTRAINT fk_resenas_establecimiento
        FOREIGN KEY (location_id)
        REFERENCES public.establecimientos(location_id),

    CONSTRAINT chk_rating
        CHECK (rating BETWEEN 1 AND 5),

    CONSTRAINT chk_keyword_status
        CHECK (
            keyword_status IN (
                'detectado',
                'sin_coincidencias',
                'idioma_no_cubierto'
            )
        )
);
