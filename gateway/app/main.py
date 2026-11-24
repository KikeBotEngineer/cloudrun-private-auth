import logging

import requests
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.auth import identify
from app.config import Settings, load_settings
from identity_token import get_session

log = logging.getLogger("gateway")

# Lo único que se reenvía del cliente. Authorization y X-API-Key quedan fuera.
FORWARDED_HEADERS = ("content-type", "accept", "x-request-id")
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


async def _body(request: Request) -> bytes:
    return await request.body()


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def create_app(settings: Settings | None = None, session: requests.Session | None = None):
    """Factory: `uvicorn app.main:create_app --factory`. Los tests inyectan settings y sesión."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = settings or load_settings()
    session = session or get_session(settings.upstream_url)
    app = FastAPI(title="api-key-gateway", docs_url=None, redoc_url=None, openapi_url=None)

    # Endpoint `def`: FastAPI lo corre en su threadpool, así `requests` no bloquea el loop.
    @app.api_route("/{path:path}", methods=METHODS)
    def proxy(path: str, request: Request, body: bytes = Depends(_body)):
        consumer = identify(request.headers.get("x-api-key"), settings.api_keys)
        if consumer is None:
            log.warning("API key faltante o inválida method=%s path=/%s", request.method, path)
            return _error(401, "API key faltante o inválida")

        route = f"/{path}"
        if (request.method, route) not in settings.allowed_routes:
            return _error(404, "Not Found")

        headers = {h: request.headers[h] for h in FORWARDED_HEADERS if h in request.headers}
        try:
            upstream = session.request(
                request.method,
                settings.upstream_url + route,
                params=request.query_params.multi_items(),
                data=body,
                headers=headers,
                timeout=settings.timeout,
            )
        except requests.Timeout:
            log.error("Timeout hacia la API consumer=%s %s %s", consumer, request.method, route)
            return _error(504, "Timeout hacia la API")
        except requests.RequestException as exc:
            log.error("Error hacia la API consumer=%s: %s", consumer, type(exc).__name__)
            return _error(502, "No se pudo contactar la API")

        log.info(
            "consumer=%s %s %s -> %s request_id=%s",
            consumer,
            request.method,
            route,
            upstream.status_code,
            headers.get("x-request-id", "-"),
        )
        if upstream.status_code in (401, 403):
            log.error("La API rechazó al gateway: ¿falta roles/run.invoker a su service account?")
            return _error(502, "El gateway no está autorizado en la API")

        return Response(
            upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )

    return app
