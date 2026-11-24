import logging

import requests
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.auth import identify
from app.config import METHODS, Settings, load_settings
from identity_token import get_session

log = logging.getLogger("gateway")

# Lo único que se reenvía del cliente. Authorization y X-API-Key quedan fuera.
FORWARDED_HEADERS = ("content-type", "accept", "x-request-id")
# ponytail: límite fijo; pasarlo a Settings si alguna ruta necesita subir archivos.
MAX_BODY_BYTES = 1024 * 1024


async def _read_body(request: Request) -> bytes | None:
    """Lee el body por streaming; None si supera MAX_BODY_BYTES (cubre también chunked)."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            return None
    return bytes(body)


def _location(upstream: requests.Response, upstream_url: str) -> dict[str, str]:
    """Reenvía Location; si apunta a la API privada, la deja relativa para no exponer su URL."""
    loc = upstream.headers.get("location")
    if not loc:
        return {}
    if loc == upstream_url or loc.startswith(upstream_url + "/"):
        loc = loc[len(upstream_url) :] or "/"
    return {"location": loc}


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def create_app(settings: Settings | None = None, session: requests.Session | None = None):
    """Factory: `uvicorn app.main:create_app --factory`. Los tests inyectan settings y sesión."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = settings or load_settings()
    session = session or get_session(settings.upstream_url)
    app = FastAPI(title="api-key-gateway", docs_url=None, redoc_url=None, openapi_url=None)

    # El body se lee solo después de validar key y ruta: sin key no se acepta ni un byte.
    @app.api_route("/{path:path}", methods=list(METHODS))
    async def proxy(path: str, request: Request):
        consumer = identify(request.headers.get("x-api-key"), settings.api_keys)
        if consumer is None:
            # path y request_id los controla el cliente: %.200r escapa saltos de línea
            # y recorta, así no pueden inyectar líneas falsas en los logs.
            log.warning("API key faltante o inválida method=%s path=%.200r", request.method, path)
            return _error(401, "API key faltante o inválida")

        route = f"/{path}"
        if (request.method, route) not in settings.allowed_routes:
            return _error(404, "Not Found")

        body = await _read_body(request)
        if body is None:
            return _error(413, "Body demasiado grande")

        headers = {h: request.headers[h] for h in FORWARDED_HEADERS if h in request.headers}
        try:
            # `requests` es bloqueante: se corre en el threadpool para no bloquear el loop.
            upstream = await run_in_threadpool(
                session.request,
                request.method,
                settings.upstream_url + route,
                params=request.query_params.multi_items(),
                data=body,
                headers=headers,
                timeout=settings.timeout,
                # Un 3xx se devuelve al cliente; el gateway no sigue redirecciones por su cuenta.
                allow_redirects=False,
            )
        except requests.Timeout:
            log.error("Timeout hacia la API consumer=%s %s %s", consumer, request.method, route)
            return _error(504, "Timeout hacia la API")
        except requests.RequestException as exc:
            log.error("Error hacia la API consumer=%s: %s", consumer, type(exc).__name__)
            return _error(502, "No se pudo contactar la API")

        log.info(
            "consumer=%s %s %s -> %s request_id=%.200r",
            consumer,
            request.method,
            route,
            upstream.status_code,
            headers.get("x-request-id", "-"),
        )
        # ponytail: se asume que todo 401/403 viene del IAM de Cloud Run (la sample-api no
        # tiene autorización propia). Si la API empieza a devolver 403 de negocio, distinguirlo
        # por el cuerpo: el rechazo de IAM llega en HTML desde Google, no en el JSON de la API.
        if upstream.status_code in (401, 403):
            log.error("La API rechazó al gateway: ¿falta roles/run.invoker a su service account?")
            return _error(502, "El gateway no está autorizado en la API")

        # Un 5xx puede traer trazas o detalles internos: se conserva el código, no el cuerpo.
        if upstream.status_code >= 500:
            log.error(
                "La API respondió %s consumer=%s %s %s",
                upstream.status_code,
                consumer,
                request.method,
                route,
            )
            return _error(upstream.status_code, "Error en la API")

        return Response(
            upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
            headers=_location(upstream, settings.upstream_url),
        )

    return app
