def discount_a(price, pct):
    if pct < 0 or pct > 100:
        raise ValueError("bad pct")
    return round(price - price * pct / 100, 2)
def discount_b(price, pct):
    if pct < 0 or pct > 100:
        raise ValueError("bad pct")
    return round(price - price * pct / 100, 2)
def discount_c(price, pct):
    if pct < 0 or pct > 100:
        raise ValueError("bad pct")
    return round(price - price * pct / 100, 2)
