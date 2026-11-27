"""Configuración leída de variables de entorno (ver .env.example)."""
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes de la aplicación.

    Cada campo se llena desde la variable de entorno del mismo nombre (en mayúsculas), o desde `.env`
    si existe; si no está definida se usa el valor por defecto de aquí. Los nombres de host por
    defecto (`postgres`) es el nombre del servicio en docker-compose.yml.
    """

    # `extra="ignore"`: el .env trae variables que esta clase no declara (JWT_*, ESM_*, NEXT_PUBLIC_API_URL...);
    # sin esto Pydantic las trataría como error.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_env: str = "development"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "sirfa"
    postgres_user: str = "sirfa"
    postgres_password: str = "cambiar"

    # Carpeta (volumen Docker) donde se guardan los FASTA subidos, con el SHA-256 como nombre.
    genomas_dir: str = "/data/genomas"

    # Seguridad (SRS RNF-01 a RNF-05). La clave por defecto solo sirve en desarrollo: fuera de él, `main.py` se niega a arrancar con ella.
    jwt_secret_key: str = "cambiar-por-un-valor-generado"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15  # el SRS pide 60 o menos
    login_max_intentos: int = 5  # intentos fallidos antes de bloquear la cuenta
    login_bloqueo_minutos: int = 15
    # Mínimo de casos para mostrar un grupo en el tablero (RF-59); los grupos más pequeños se suprimen.
    tablero_minimo_grupo: int = 5
    # Carpeta de los modelos entrenados (ml/models) y puntaje desde el cual un fago cuenta como candidato en las brechas (RF-56).
    modelo_dir: str = "/app/ml/models"
    umbral_candidato: float = 0.5

    @property
    def postgres_url(self) -> str:
        """URL de conexión de SQLAlchemy (driver psycopg 3)."""
        # quote_plus: si la clave trae caracteres como @ o /, romperían la URL sin escapar.
        usuario, clave = quote_plus(self.postgres_user), quote_plus(self.postgres_password)
        return f"postgresql+psycopg://{usuario}:{clave}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache
def get_settings() -> Settings:
    """Devuelve siempre la misma instancia: el entorno se lee una sola vez por proceso."""
    return Settings()
