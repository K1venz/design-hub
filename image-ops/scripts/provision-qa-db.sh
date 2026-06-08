#!/usr/bin/env bash
# provision-qa-db.sh — create the isolated :8002 QA write-test database on the
# LOCAL MySQL (/usr/local/mysql), so listing 验收 write tests never touch prod.
#
# Why a dedicated local MySQL db (not SQLite): A4 验收要测 n=3/5/7 的真并发，
# SQLite 单写锁会让并发结果失真（假失败/假通过）。必须真 MySQL。
#
# ops does NOT hold the local MySQL root password by default. Provide it via env:
#   MYSQL_ROOT_PWD='...' ./provision-qa-db.sh
#
# Creates: database design_hub_qa (utf8mb4) + user dh_qa scoped to it, then
# prints the DB_URL for QA's :8002 backend. First run: `alembic upgrade head`
# from image-code/ builds the 15 tables (migration chain smoke-tested by dev).
set -euo pipefail

MYSQL="${MYSQL_BIN:-/usr/local/mysql/bin/mysql}"
QA_DB="${QA_DB:-design_hub_qa}"
QA_USER="${QA_USER:-dh_qa}"
QA_PWD="${QA_PWD:-dh_qa_local}"          # local throwaway test cred, override as needed
ROOT_PWD="${MYSQL_ROOT_PWD:?set MYSQL_ROOT_PWD to the local MySQL root password}"

"$MYSQL" -uroot -p"$ROOT_PWD" <<SQL
CREATE DATABASE IF NOT EXISTS \`${QA_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${QA_USER}'@'localhost' IDENTIFIED BY '${QA_PWD}';
CREATE USER IF NOT EXISTS '${QA_USER}'@'127.0.0.1' IDENTIFIED BY '${QA_PWD}';
GRANT ALL PRIVILEGES ON \`${QA_DB}\`.* TO '${QA_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${QA_DB}\`.* TO '${QA_USER}'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

echo "[provision-qa-db] OK: database '${QA_DB}' + user '${QA_USER}' ready on local MySQL."
echo "[provision-qa-db] put this in QA's :8002 env (口诀 GPT留 / TOS清 / DB换独立MySQL):"
echo "  DB_URL=mysql+aiomysql://${QA_USER}:${QA_PWD}@127.0.0.1:3306/${QA_DB}?charset=utf8mb4"
echo "[provision-qa-db] then from image-code/:  alembic upgrade head   # builds 15 tables"
