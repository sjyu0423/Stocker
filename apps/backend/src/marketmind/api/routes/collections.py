import uuid

from fastapi import APIRouter, HTTPException, Query, status

from marketmind.api.dependencies import QueryServiceDependency
from marketmind.api.schemas import CollectionRunResponse

router = APIRouter(tags=["collections"])


@router.get("/collection-runs", response_model=list[CollectionRunResponse])
def list_collection_runs(
    service: QueryServiceDependency, limit: int = Query(default=50, ge=1, le=200)
) -> list[CollectionRunResponse]:
    return [
        CollectionRunResponse.model_validate(item) for item in service.collection_runs(limit=limit)
    ]


@router.get("/collection-runs/{run_id}", response_model=CollectionRunResponse)
def get_collection_run(run_id: uuid.UUID, service: QueryServiceDependency) -> CollectionRunResponse:
    item = service.collection_run(run_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection run not found"
        )
    return CollectionRunResponse.model_validate(item)
