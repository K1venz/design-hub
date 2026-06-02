"""监控装配（WP-监控/ISSUE-0008）：HTTP 指标 + /metrics 暴露 + Sentry 异常接入。

- instrument_app：prometheus-fastapi-instrumentator 采集 QPS/时延/状态码/在途请求，
  暴露 GET /metrics（直接加路由，不经 include_router，故不被 WP-G 鉴权拦，供 Prometheus 裸抓）。
- init_sentry：DSN 为空则 no-op（本地/CI 无需 Sentry）。
"""

import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def instrument_app(app: FastAPI) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def init_sentry(dsn: str) -> None:
    if dsn:
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
