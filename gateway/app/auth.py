import hashlib
import hmac


def identify(api_key: str | None, keys: dict[str, str]) -> str | None:
    """Devuelve el nombre del consumidor dueño de la key, o None.

    Se comparan hashes con hmac.compare_digest (tiempo constante) y se recorren
    todas las keys para no filtrar por timing cuál coincidió.
    """
    if not api_key:
        return None
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    consumer = None
    for name, expected in keys.items():
        if hmac.compare_digest(digest, expected):
            consumer = name
    return consumer
