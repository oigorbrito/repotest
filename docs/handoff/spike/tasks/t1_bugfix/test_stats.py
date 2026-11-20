import sys; sys.path.insert(0, "src")
from stats import mean
def test_mean(): assert mean([1, 2, 3]) == 2.0
def test_empty(): assert mean([]) == 0.0
def test_single(): assert mean([5]) == 5.0
