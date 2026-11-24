import os
from dataclasses import dataclass
from string import hexdigits

# Métodos que el gateway enruta; una ruta con otro método nunca podría coincidir.
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


@dataclass(frozen=True)
class Settings:
    upstream_url: str
    api_keys: dict[str, str]  # consumidor -> sha256 hex de su key
    allowed_routes: frozenset[tuple[str, str]]  # (MÉTODO, /ruta)
    timeout: float = 10.0


def _required(env, name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}")
    return value


def load_settings(env=os.environ) -> Settings:
    """Falla al arrancar ante cualquier configuración que dejaría el gateway inútil o ambiguo."""
    api_keys = {}
    for item in _required(env, "API_KEYS").split(","):
        name, _, digest = item.strip().partition(":")
        digest = digest.lower()
        # Nunca se imprime el hash: solo el nombre del consumidor.
        if not name or len(digest) != 64 or not set(digest) <= set(hexdigits):
            raise RuntimeError(f"API_KEYS mal formado para el consumidor {name!r}")
        if name in api_keys:
            raise RuntimeError(f"API_KEYS repite el consumidor {name!r}")
        api_keys[name] = digest
    if len(set(api_keys.values())) != len(api_keys):
        raise RuntimeError("API_KEYS repite la misma key en dos consumidores")

    routes = set()
    for item in _required(env, "ALLOWED_ROUTES").split(","):
        method, _, path = item.strip().partition(" ")
        if not method:
            continue  # tolera comas sobrantes
        method, path = method.upper(), path.strip()
        if method not in METHODS or not path.startswith("/"):
            raise RuntimeError(f"ALLOWED_ROUTES: ruta inválida {item.strip()!r} (MÉTODO /ruta)")
        routes.add((method, path))
    if not routes:
        raise RuntimeError("ALLOWED_ROUTES no tiene ninguna ruta")

    return Settings(
        upstream_url=_required(env, "UPSTREAM_URL").rstrip("/"),
        api_keys=api_keys,
        allowed_routes=frozenset(routes),
        timeout=float(env.get("UPSTREAM_TIMEOUT_SECONDS", "10")),
    )
