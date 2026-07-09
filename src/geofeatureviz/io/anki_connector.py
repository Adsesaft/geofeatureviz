"""Connect to the local Anki collection."""

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pandas as pd
from anki.collection import Collection

from geofeatureviz.io import path_settings


@contextmanager
def open_collection(path: Path | str) -> Generator[Collection, None, None]:
    """Open an anki collection as a context manager to ensure it is properly closed.

    Args:
        path: Path to the Anki collection file. This should never be the original file,
            but a copy.

    Yields:
        An open Anki collection to access decks, notes, note types, etc.
    """
    path = str(path)
    if path == str(path_settings.anki_collection_path):
        raise ValueError(
            "The opened Anki collection should never be the original file! Please "
            "provide a copy."
        )
    col = Collection(path)
    try:
        yield col
    finally:
        col.close()


def deck_to_df(deck_name: str) -> pd.DataFrame:
    """Return an Anki deck in the local collection as a pandas DataFrame.

    When exporting Anki decks to csv, it is not possible to include the field names in
    of note type, making it very cumbersome to work with it. This function loads the
    local Anki collection and returns the notes in the deck, including the names of the
    fields of the note type, as well as a column called "NoteType" with the name of the
    note type.

    Args:
        deck_name: Name of the deck to get the notes from. The deck has to exist in the
            local Anki collection with exactly the same name.

    Raises:
        ValueError: When a deck name is given that does not exist in the collection.

    Returns:
        A dataframe with the field names of the note types as columns.
    """
    # copy the original file to avoid any modifications or interference with anki
    src_col_path = path_settings.anki_collection_path
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        tmp_col_path = tmp_dir_path / src_col_path.name
        shutil.copy2(src_col_path, tmp_col_path)

        with open_collection(tmp_col_path) as col:
            # dict mapping note type names to the fields of the note type
            note_type_to_fields = {}
            for model in col.models.all():
                note_type_name = model["name"]
                fields = [field["name"] for field in model["flds"]]
                note_type_to_fields[note_type_name] = fields

            # get the deck
            deck_id = col.decks.id(deck_name)
            if deck_id is None:
                raise ValueError(
                    f"The deck '{deck_name}' could not be found in the Anki collection."
                )
            # get cards in the deck
            card_ids = col.decks.cids(deck_id)
            # get note of card ids
            note_ids = set([col.get_card(cid).nid for cid in card_ids])
            notes = [col.get_note(nid) for nid in note_ids]
            assert notes != [], f"There are no notes in the deck '{deck_name}'."

            # create the pandas dataframe
            notes_with_type = []
            for note in notes:
                note_type = note.note_type()
                assert note_type is not None, (
                    f"The note {note} does not have a note type."
                )
                note_type_name = note_type["name"]
                fields = note_type_to_fields[note_type_name]
                values = note.values()
                result = dict(zip(fields, values))
                result["NoteType"] = note_type_name
                notes_with_type.append(result)
    return pd.DataFrame(notes_with_type)
