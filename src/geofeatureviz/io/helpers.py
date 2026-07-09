"""Provide helper functions that are useful throughout projects."""

from pathlib import Path


def get_top_directory() -> Path:
    """Find the path to the project's top-level directory.

    Returns:
        The path to the top-level directory.
    """
    # use the relative location of this file
    top_path = Path(__file__).parent.parent.parent.parent.absolute()
    # check that we're in the top directory
    if (top_path / "tests").exists() and (top_path / "src").exists():
        return top_path
    else:
        raise ValueError(f"Couldn't find correct project directory; found {top_path}.")
