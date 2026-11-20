import sys; sys.path.insert(0, ".")
import pkg.core as core
from pkg.report import render
def test_new_name():
    assert core.calculate_total([{"price": 2}, {"price": 3}]) == 5
def test_old_gone():
    assert not hasattr(core, "compute_total")
def test_report():
    assert render([{"price": 4}]) == "TOTAL=4"
