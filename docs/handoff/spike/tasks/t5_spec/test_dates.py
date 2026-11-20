import sys; sys.path.insert(0, ".")
import pytest
from dates import to_iso
def test_ok(): assert to_iso("05/03/2024") == "2024-03-05"
def test_spaces(): assert to_iso("  31/12/1999 ") == "1999-12-31"
def test_invalid():
    with pytest.raises(ValueError): to_iso("31/02/2024")
    with pytest.raises(ValueError): to_iso("nope")
