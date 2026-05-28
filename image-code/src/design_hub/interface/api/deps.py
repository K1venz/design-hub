from typing import Annotated

from fastapi import Depends, Header, Request

from design_hub.composition import Engine


def get_engine(request: Request) -> Engine:
    engine = request.app.state.engine
    assert isinstance(engine, Engine)
    return engine


EngineDep = Annotated[Engine, Depends(get_engine)]
UserIdDep = Annotated[str, Header(alias="X-User-Id")]
