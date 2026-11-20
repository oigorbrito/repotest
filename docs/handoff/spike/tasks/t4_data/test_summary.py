import csv, os
def test_summary_csv():
    assert os.path.exists("summary.csv"), "summary.csv missing"
    rows = list(csv.DictReader(open("summary.csv", encoding="utf-8")))
    got = {r["region"]: float(r["total"]) for r in rows}
    assert got == {"north": 13.0, "south": 4.0, "east": 7.0}
    assert [r["region"] for r in rows] == ["east", "north", "south"]
