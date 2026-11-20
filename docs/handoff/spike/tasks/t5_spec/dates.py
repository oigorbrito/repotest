def to_iso(s):
    d, m, y = s.split("/")
    return f"{y}-{m}-{d}"
