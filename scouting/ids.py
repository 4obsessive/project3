"""Conversión de identificadores de Steam a account_id (SteamID3 sin [U:1:])."""
import re

STEAM64_BASE = 76561197960265728

_U1 = re.compile(r"\[?U:1:(\d+)\]?", re.I)
_PROFILE = re.compile(r"steamcommunity\.com/profiles/(\[?U:1:\d+\]?|\d+)", re.I)


def to_account_id(token):
    """Acepta número, [U:1:N], steam64 o URL de perfil. Devuelve int o None.

    Un ID válido tiene al menos 5 dígitos (así "100 Thieves" no se toma por ID)."""
    if token is None:
        return None
    t = str(token).strip().strip(",;")
    m = _PROFILE.search(t)
    if m:
        t = m.group(1)
    m = _U1.fullmatch(t)
    if m:
        return int(m.group(1))
    if t.isdigit() and len(t) >= 5:
        n = int(t)
        if n >= STEAM64_BASE:
            n -= STEAM64_BASE
        return n if 0 < n < (1 << 32) else None
    return None


def steam_profile_url(account_id):
    return f"https://steamcommunity.com/profiles/[U:1:{int(account_id)}]"
