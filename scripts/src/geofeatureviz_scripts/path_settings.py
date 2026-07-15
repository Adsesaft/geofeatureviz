"""Path settings for geofeatureviz-scripts.

This can be used to conveniently access all relevant file paths in this sub-package.

Examples:
    # in most cases, you should import the instantiated settings class
    from geofeatureviz_scripts.path_settings import path_settings

    # and the use its paths
    print(path_settings.data_dir)
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from geofeatureviz.io import helpers


class _PathSettings(BaseSettings):
    """Settings for geofeatureviz_scripts paths.

    No .env file is expected for this sub-package, but values can still be overridden
    via environment variables prefixed with GEOFEATUREVIZ_SCRIPTS_, e.g.:
    GEOFEATUREVIZ_SCRIPTS_PROJECT_ROOT=/some/other/path.
    """

    model_config = SettingsConfigDict(env_prefix="GEOFEATUREVIZ_SCRIPTS_")

    project_root: Path = Field(default_factory=helpers.get_top_directory)

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
    def data_reference_dir(self) -> Path:
        """Directory for reference data."""
        return self.data_dir / "reference"

    @property
    def results_dir(self) -> Path:
        """Directory for results."""
        return self.project_root / "results"

    @property
    def country_translation(self) -> Path:
        """File path to CSV-file containing country translations."""
        return self.data_reference_dir / "country_translations.csv"


path_settings = _PathSettings()
