from fastapi import APIRouter

from marketmind import __version__
from marketmind.api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="marketmind-api", version=__version__)
