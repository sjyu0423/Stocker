from fastapi import APIRouter

from marketmind.api.dependencies import QueryServiceDependency
from marketmind.api.schemas import CompanyResponse, DataSourceResponse

router = APIRouter(tags=["catalog"])


@router.get("/data-sources", response_model=list[DataSourceResponse])
def list_data_sources(service: QueryServiceDependency) -> list[DataSourceResponse]:
    return [DataSourceResponse.model_validate(item) for item in service.data_sources()]


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(service: QueryServiceDependency) -> list[CompanyResponse]:
    return [CompanyResponse.model_validate(item) for item in service.companies()]
