"""Estadística compartida (resúmenes, análisis e informe): intervalos de Wilson, encogimiento
bayesiano hacia la media de la población y niveles de fiabilidad. Funciones puras."""
import math

Z95 = 1.96
Z90 = 1.645
Z80 = 1.2816


def wilson(k, n, z=Z95):
    """Intervalo de Wilson para una proporción k/n. n == 0 -> (0, 1)."""
    if not n:
        return 0.0, 1.0
    p = k / n
    z2 = z * z
    d = 1 + z2 / n
    c = (p + z2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def shrink_rate(k, n, prior_mean, prior_n):
    """Tasa encogida hacia prior_mean con prior_n partidas ficticias."""
    return (k + prior_mean * prior_n) / (n + prior_n) if (n + prior_n) else prior_mean


def beta_prior(pairs, min_n=20, default=(0.5, 30), clamp=(15, 200)):
    """Prior Beta (media, fuerza) por método de momentos a partir de [(k, n)].

    Solo cuentan los pares con n >= min_n; con menos de 8 se devuelve `default`.
    La varianza observada se corrige restando la varianza binomial esperada (ruido de muestreo)."""
    pairs = [(k, n) for k, n in pairs if n and n >= min_n]
    if len(pairs) < 8:
        return default
    tk = sum(k for k, _ in pairs)
    tn = sum(n for _, n in pairs)
    m = tk / tn
    v_obs = sum(n * (k / n - m) ** 2 for k, n in pairs) / tn
    v_noise = sum(m * (1 - m) / n for _, n in pairs) / len(pairs)
    v = max(v_obs - v_noise, 1e-6)
    prior_n = m * (1 - m) / v - 1
    prior_n = min(max(prior_n, clamp[0]), clamp[1])
    return m, prior_n


def shrink_ratio(x, n, prior=1.0, prior_n=15):
    """Encoge un índice (1.0 = media) hacia `prior` con prior_n partidas ficticias."""
    if x is None:
        return prior
    return (n * x + prior_n * prior) / (n + prior_n) if (n + prior_n) else prior


RELIABILITY = [(150, "High"), (60, "Medium"), (20, "Low"), (0, "Insufficient")]


def reliability(n):
    """Nivel según la semianchura de Wilson a p=0.5: Alta ±8pp, Media ±12pp, Baja ±20pp."""
    n = n or 0
    for lim, label in RELIABILITY:
        if n >= lim:
            return label
    return "Insufficient"


def percentile_fn(values):
    """Devuelve f(x) -> percentil 0..1 de x dentro de `values` (empates: posición inferior)."""
    v = sorted(x for x in values if x is not None)

    def f(x):
        if x is None or not v:
            return None
        lo, hi = 0, len(v)
        while lo < hi:
            mid = (lo + hi) // 2
            if v[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo / (len(v) - 1) if len(v) > 1 else 1.0
    return f


def evidence(k, n, baseline=0.5, z=Z90):
    """Fuerza de un hallazgo k/n frente a una tasa base: strong | moderate | hint."""
    lo, hi = wilson(k, n, z)
    if n >= 8 and lo > baseline:
        ev = "strong"
    elif n >= 5 and lo > baseline:
        ev = "moderate"
    else:
        ev = "hint"
    return {"lo": lo, "hi": hi, "evidence": ev}


def intervals_overlap(a, b):
    return not (a[1] < b[0] or b[1] < a[0])
