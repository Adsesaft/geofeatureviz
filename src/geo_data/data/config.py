"""Configuration settings like paths, environment variables etc."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from geo_data import helpers


class PathSettings(BaseSettings):
    """Configuration settings managed with environment variables and defaults.

    This class centralizes runtime configuration, especially file paths. Values can be
    overridden using the .env file / environment variables. Paths can be accessed as
    properties to ensure consistent path construction across the project.

    Attributes:
        project_root: Root directory of the project.
        anki_dir: Base directory of the local Anki collection. If not set, Anki can not
            be accessed in the project.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    project_root: Path = helpers.get_top_directory()

    anki_dir: Path | None = None
    anki_copy_dir: Path | None = None

    @property
    def data_dir(self) -> Path:
        """Base directory for all data files."""
        return self.project_root / "data"

    @property
    def data_raw_dir(self) -> Path:
        """Directory for raw data."""
        return self.data_dir / "raw"

    @property
    def data_processed_dir(self) -> Path:
        """Directory for preprocessed data."""
        return self.data_dir / "processed"

    @property
    def results_dir(self) -> Path:
        """Directory for results."""
        return self.project_root / "results"

    @property
    def regional_groups_path(self) -> Path:
        """File path to YAML-file with information about regional groups."""
        return self.data_dir / "regional_groups.yaml"

    @property
    def country_translation_path(self) -> Path:
        """File path to CSV-file containing country translations."""
        return self.data_dir / "country_translations.csv"

    @property
    def anki_collection_path(self) -> Path:
        """File path to the local Anki collection database.

        Raises:
            ValueError: If the path to the local anki directory (`anki_dir`) is not set.
        """
        base = self.anki_dir
        if base is None:
            raise ValueError("Anki collection could not be found.")
        return base / "collection.anki2"

    @property
    def anki_collection_copy_path(self) -> Path:
        """File path to where the local Anki collection database is copied."""
        return self.data_dir / "collection.anki2"


path_settings = PathSettings()
