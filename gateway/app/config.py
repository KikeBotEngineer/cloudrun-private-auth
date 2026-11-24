import os
from dataclasses import dataclass


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
    api_keys = {}
    for item in _required(env, "API_KEYS").split(","):
        name, _, digest = item.strip().partition(":")
        if not name or len(digest) != 64:
            # Nunca se imprime el valor: solo el nombre del consumidor.
            raise RuntimeError(f"API_KEYS mal formado para el consumidor {name!r}")
        api_keys[name] = digest.lower()

    routes = set()
    for item in env.get("ALLOWED_ROUTES", "").split(","):
        method, _, path = item.strip().partition(" ")
        if method:
            routes.add((method.upper(), path.strip()))

    return Settings(
        upstream_url=_required(env, "UPSTREAM_URL").rstrip("/"),
        api_keys=api_keys,
        allowed_routes=frozenset(routes),
        timeout=float(env.get("UPSTREAM_TIMEOUT_SECONDS", "10")),
    )
