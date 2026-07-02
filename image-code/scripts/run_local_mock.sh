#!/usr/bin/env bash
# 本地 mock /chat 后端随起脚本（前端联调用）。
# 零 API 成本、不触 prod：mock 文本 LLM(TEXT_LLM 未配) + mock 图像(REAL_GPT_IMAGE=false)
# + sqlite + 本地存储(TOS 置空)。默认 http://127.0.0.1:8000（VITE_API_TARGET 指这里）。
# 用法：bash scripts/run_local_mock.sh   [PORT=8000] [MOCK_DB=<path>]
set -euo pipefail
cd "$(dirname "$0")/.."  # -> image-code/

DBFILE="${MOCK_DB:-${TMPDIR:-/tmp}/design_hub_mock.db}"
PORT="${PORT:-8000}"
export DB_URL="sqlite+aiosqlite:///${DBFILE}"
export REAL_GPT_IMAGE=false
export TEXT_LLM_API_KEY="" TEXT_LLM_BASE_URL="" TEXT_LLM_MODEL=""
export TOS_ACCESS_KEY="" TOS_SECRET_KEY="" TOS_GENERATE_BUCKET="" TOS_UPLOAD_BUCKET="" TOS_REGION="" TOS_ENDPOINT=""
export DOCS_ENABLED=true
export JWT_SECRET="${JWT_SECRET:-local-mock-liantiao-secret-min-32-bytes-xxxx}"

# 建表（idempotent：create_all 只补缺表）
uv run python - <<'PY'
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from design_hub.infrastructure.db.base import Base
import design_hub.infrastructure.db.models  # noqa: F401  registers tables on Base.metadata

async def main() -> None:
    engine = create_async_engine(os.environ["DB_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(main())
PY

echo "mock backend -> http://127.0.0.1:${PORT}  (mock text+image, sqlite=${DBFILE})"
echo "  登录 token 字段=jwt；VITE_API_TARGET=http://127.0.0.1:${PORT}"
exec uv run uvicorn design_hub.interface.api.asgi:app --host 127.0.0.1 --port "${PORT}"
