import sys; sys.path.insert(0, ".")
import pytest, calc
def test_values(): assert calc.discount_a(100, 15) == 85.0
def test_others(): assert calc.discount_b(50, 10) == 45.0 and calc.discount_c(20, 50) == 10.0
def test_err():
    with pytest.raises(ValueError): calc.discount_c(1, 101)
def test_no_duplicated_validation():
    src = open("calc.py", encoding="utf-8").read()
    assert src.count("bad pct") == 1, "validation must live in one place"
