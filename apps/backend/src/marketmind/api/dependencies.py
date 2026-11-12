from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from marketmind.application.queries import QueryService
from marketmind.infrastructure.db.session import get_db

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_query_service(session: DatabaseSession) -> QueryService:
    return QueryService(session)


QueryServiceDependency = Annotated[QueryService, Depends(get_query_service)]
