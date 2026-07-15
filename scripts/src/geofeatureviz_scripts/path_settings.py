"""Path settings for geofeatureviz-scripts.

This can be used to conveniently access all relevant file paths in this sub-package.

Examples:
    # in most cases, you should import the instantiated settings class
    from geofeatureviz_scripts.path_settings import path_settings

    # and the use its paths
    print(path_settings.data_dir)
"""

from pathlib import Path

from geofeatureviz.io.path_settings import _PathSettings as Base_PathSettings


class _PathSettings(Base_PathSettings):
    """Settings for geofeatureviz_scripts paths."""

    @property
    def country_translation(self) -> Path:
        """File path to CSV-file containing country translations."""
        return self.data_reference_dir / "country_translations.csv"

    @property
    def regional_groups(self) -> Path:
        """File path to YAML-file with information about regional groups."""
        return self.data_reference_dir / "regional_groups.yaml"


path_settings = _PathSettings()
