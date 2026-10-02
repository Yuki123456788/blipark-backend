# Blipark Backend

Django／GeoDjango backend 與 TDX parking-data ingestion service 的初始骨架。

目前已包含可執行的 Django project、PostGIS 設定、health endpoints、container 設定與品質檢查；尚未假設未驗證的 TDX schema，因此 parking models 與 sync pipeline 會在取得真實 fixture 後實作。

## 技術版本

- Python 3.13
- Django 6.0
- PostgreSQL 17 + PostGIS 3.5
- uv
- Pydantic 2、httpx、psycopg 3
- pytest、Ruff

架構背景與決策位於 [`../wiki/README.md`](../wiki/README.md)。開始 domain／TDX 工作前，先讀 [`../wiki/CONTEXT.md`](../wiki/CONTEXT.md)。

## 最快啟動：全部使用 Docker Compose

需要 Docker 與 Docker Compose：

```bash
cp .env.example .env
# Edit .env and replace both replace-me values before continuing.
chmod 600 .env
docker compose up --build
```

可分別用以下指令產生本機 secret，再貼入 `.env`：

```bash
openssl rand -base64 48  # DJANGO_SECRET_KEY
openssl rand -hex 32     # POSTGRES_PASSWORD
```

TDX credentials 尚未使用時可以保持空白；開始串接 TDX 後，再將 console 提供的 ID／secret 寫入本機 `.env`。

啟動後可檢查：

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

- `/health/live`：process 可回應即可成功，不檢查 database。
- `/health/ready`：會執行 `SELECT 1`，database 無法使用時回傳 HTTP 503。
- `/admin/`：Django Admin；先建立 superuser 才能登入。

建立管理員：

```bash
docker compose exec backend python manage.py createsuperuser
```

關閉服務：

```bash
docker compose down
```

`docker compose down` 不會刪除 database volume。只有明確要丟棄本機資料時才使用 `docker compose down --volumes`。

## 本機使用 uv，database 使用 Docker

本機執行 GeoDjango 仍需要 GDAL、GEOS 與 PROJ。若 macOS 尚未安裝，可以用 Homebrew：

```bash
brew install gdal geos proj
```

專案要求 Python 3.13；uv 會依 `.python-version` 選擇或下載相容 Python：

```bash
cp .env.example .env
docker compose up -d db
uv sync
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py runserver
```

注意：Django 本身不會自動讀取 `.env`。Docker Compose 會自動讀取；直接使用 uv 時，透過 `--env-file .env` 載入。Makefile 中需要 runtime configuration 的指令也已包含這個參數。

## 常用指令

```bash
make check       # Django system checks
make test        # pytest
make lint        # Ruff lint + format check
make format      # 自動修正 lint 與格式
make db-up       # 只啟動 PostGIS
make migrate     # 執行 migrations
make run         # Django development server
```

不使用 `make` 時，等價指令都是 `uv run ...`。

## Settings

| Module | 用途 |
| --- | --- |
| `config.settings.development` | 本機與目前 Compose 開發環境 |
| `config.settings.test` | pytest |
| `config.settings.production` | production；強制要求環境提供 secret、DB password 與 allowed hosts |

主要環境變數見 [`.env.example`](.env.example)：

- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`
- `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_CONN_MAX_AGE`
- 未來使用的 `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`

`.env.example` 只包含欄位名稱與無效 placeholder，因此可以進 Git。真實 `.env`、`.env.local`、`.env.production` 與 `.secrets/` 都已被 `.gitignore` 排除，也不會被複製進 Docker image。可以這樣確認：

```bash
git check-ignore -v .env
```

Production 不應把 `.env` 打包進 image；由 deployment platform、Docker secret 或 VM 上權限受限的環境檔注入。不要把 secret 放進 `compose.yaml`、Django settings、Dockerfile、GitHub Actions YAML 或指令列參數。

## 專案邊界

```text
config/             Django runtime 與 settings
parking/            Blipark parking domain／application services
integrations/tdx/   TDX auth、HTTP、DTO、mapper adapter
tests/              跨 app 與 runtime tests
```

依賴規則：

- `parking` 不 import raw TDX response 或 TDX-specific DTO。
- TDX JSON 先經 Pydantic validation 與 mapper，才交給 domain／ORM。
- Management command、未來 API 與 Admin action 只作為 trigger；同步邏輯放在 `ParkingSyncService`。
- API 與 sync 可用不同 process 執行，但目前共享 code、schema 與 database。

## 下一個實作 milestone

1. 確認 TDX 台南 parking endpoints、認證、pagination、quota 與真實 response。
2. 保存移除敏感資訊的 fixtures，驗證 ID scope、nullability、geometry 與 relationships。
3. 建立 Pydantic DTO 與 schema-drift tests。
4. 建立最小 parking／source reference／SyncRun models 與 migrations。
5. 實作 mapper、idempotent upsert、`ParkingSyncService` 與 `sync_tdx` command。
6. 把 models 與 sync observability 註冊到 Django Admin。

詳細順序見 [TDX ingestion 設計](../wiki/architecture/data-ingestion.md)。
