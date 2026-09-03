"""Standalone checks of the multibagger v1 maths — no DB, no pandas import from the app."""
MB_WEIGHTS = {
    "growth": 0.25, "capital_efficiency": 0.20, "earnings_stability": 0.15,
    "margin_expansion": 0.15, "dilution": 0.10, "momentum": 0.10,
    "insider_alignment": 0.05,
}
MB_MIN_VALID_WEIGHT = 0.70


def dilution_curve(d):
    if d >= 25:  return 0.0
    if d >= 10:  return 40.0 * (25 - d) / 15
    if d >= 3:   return 40 + 35.0 * (10 - d) / 7
    if d >= 0:   return 75 + 15.0 * (3 - d) / 3
    if d >= -10: return 90 + 10.0 * (-d) / 10
    return 100.0


def insider_curve(p):
    if p <= 0:  return 40.0
    if p <= 5:  return 40 + 20.0 * p / 5
    if p <= 15: return 60 + 20.0 * (p - 5) / 10
    if p <= 25: return 80 + 15.0 * (p - 15) / 10
    return 95.0


def score(components):
    valid_w = sum(w for k, w in MB_WEIGHTS.items() if components.get(k) is not None)
    eligible = (
        components.get("growth") is not None
        and (components.get("capital_efficiency") is not None
             or components.get("earnings_stability") is not None)
        and valid_w >= MB_MIN_VALID_WEIGHT
    )
    if not eligible:
        return None, round(valid_w * 100, 1)
    weighted = sum(components[k] * w for k, w in MB_WEIGHTS.items() if components.get(k) is not None)
    return round(weighted / valid_w, 1), round(valid_w * 100, 1)


def band(s):
    for floor, label in [(85, "Exceptional compounding characteristics"), (75, "Strong"),
                         (65, "Above Average"), (50, "Moderate"), (35, "Weak"), (0, "Very Weak")]:
        if s >= floor:
            return label


print("1. Your worked example — expected ~82")
ex = dict(growth=88, capital_efficiency=82, earnings_stability=76,
          margin_expansion=91, dilution=85, momentum=69, insider_alignment=72)
s, vw = score(ex)
print(f"   score={s}  valid_weight={vw}%  band={band(s)}")
assert 81 <= s <= 83, s

print("\n2. Weights sum to 1.0:", abs(sum(MB_WEIGHTS.values()) - 1.0) < 1e-9)

print("\n3. Dilution is asymmetric (share change % -> component)")
for d in (30, 20, 10, 5, 0, -5, -20):
    label = "heavy dilution" if d >= 10 else "moderate" if d >= 3 else "stable" if d >= 0 else "buyback"
    print(f"   {d:+4}%  -> {dilution_curve(d):5.1f}   {label}")
assert dilution_curve(30) < dilution_curve(5) < dilution_curve(0) <= dilution_curve(-5)
assert dilution_curve(-20) == 100.0, "buyback benefit must be capped"
assert dilution_curve(-20) - dilution_curve(0) <= 15, "buybacks must not dominate"

print("\n4. Insider curve saturates, low ownership is neutral not damning")
for p in (0, 2, 5, 15, 25, 60):
    print(f"   {p:3}%  -> {insider_curve(p):5.1f}")
assert insider_curve(2) >= 40, "2% insiders should not be punished"
assert insider_curve(60) == insider_curve(25) == 95.0, "should saturate"

print("\n5. Eligibility rules")
cases = [
    ("only momentum+dilution+insiders (the 85/100 trap)",
     dict(momentum=95, dilution=95, insider_alignment=95)),
    ("growth missing, everything else present",
     dict(capital_efficiency=80, earnings_stability=80, margin_expansion=80,
          dilution=80, momentum=80, insider_alignment=80)),
    ("growth present but no capital-quality component",
     dict(growth=90, margin_expansion=80, dilution=80, momentum=80, insider_alignment=80)),
    ("growth + capital efficiency + dilution = 55% of weight (below threshold)",
     dict(growth=90, capital_efficiency=85, dilution=80)),
    ("growth + capital efficiency + stability + margins = 75% valid",
     dict(growth=90, capital_efficiency=85, earnings_stability=70, margin_expansion=80)),
]
for name, comp in cases:
    s, vw = score(comp)
    verdict = "published" if s is not None else "NULL (correctly withheld)"
    print(f"   {name:<58} {verdict}  (valid {vw}%)")

assert score(cases[0][1])[0] is None
assert score(cases[1][1])[0] is None
assert score(cases[2][1])[0] is None
assert score(cases[3][1])[0] is None
assert score(cases[4][1])[0] is not None

print("\n6. Momentum cannot dominate — a hot stock with weak fundamentals")
hot = dict(growth=30, capital_efficiency=25, earnings_stability=30,
           margin_expansion=0, dilution=40, momentum=100, insider_alignment=50)
s, _ = score(hot)
print(f"   momentum=100 but weak business -> {s} ({band(s)})")
assert s < 50, "momentum at 10% must not carry a weak business"

print("\n7. Strong business with weak momentum still scores well")
cold = dict(growth=90, capital_efficiency=88, earnings_stability=85,
            margin_expansion=100, dilution=90, momentum=10, insider_alignment=70)
s, _ = score(cold)
print(f"   excellent business, momentum=10 -> {s} ({band(s)})")
assert s >= 75, "a compounder with weak price action should still rank Strong+"

print("\nALL CHECKS PASSED")
