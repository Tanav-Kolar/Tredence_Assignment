"""
Application configuration using Pydantic Settings.

Loads environment variables from .env file and provides typed access.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        postgres_user: PostgreSQL username.
        postgres_password: PostgreSQL password.
        postgres_db: PostgreSQL database name.
        postgres_host: PostgreSQL host address.
        postgres_port: PostgreSQL port number.
        database_url: Full async database connection URL.
        debug: Enable debug mode (verbose logging).
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # PostgreSQL Configuration
    postgres_user: str = "workflow_user"
    postgres_password: str = "workflow_pass"
    postgres_db: str = "workflow_engine"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    
    # Computed database URL (can be overridden by DATABASE_URL env var)
    database_url: str = ""
    
    # Debug mode
    debug: bool = False
    
    def model_post_init(self, __context) -> None:
        """Construct database URL if not explicitly set."""
        if not self.database_url:
            object.__setattr__(
                self,
                "database_url",
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )


# Global settings instance
settings = Settings()
