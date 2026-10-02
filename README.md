# Blipark Backend

Django／GeoDjango backend 與 TDX parking-data ingestion service 的初始骨架。

目前已包含可執行的 Django project、PostGIS 設定、health endpoints、TDX Parking v1 validation／mapping／sync pipeline、container 設定與品質檢查。Phase 0 只同步台南靜態停車資料，trigger 限 manual CLI。

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
make sync        # 同步全部台南靜態 TDX parking datasets
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
- `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`
- `TDX_TIMEOUT_SECONDS`、`TDX_PAGE_SIZE`、`TDX_MAX_ATTEMPTS`

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

## 執行 TDX parking sync

先完成 migration 並確認 `.env` 有有效的 `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`：

```bash
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py sync_tdx
```

如果 host 沒有 GDAL／GEOS／PROJ，使用 Compose：

```bash
docker compose run --rm backend python manage.py sync_tdx
```

只同步部分 datasets 時可重複使用 `--dataset`：

```bash
uv run --env-file .env python manage.py sync_tdx \
  --dataset car_parks \
  --dataset parking_entrance_exits
```

可用值：`car_parks`、`parking_entrance_exits`、`off_street_spots`、`parking_segments`、`on_street_spots`。預設依 parent dependency 順序執行全部 datasets。

每次執行都建立 `SyncRun` 與 per-dataset results；CLI 印出 fetched／valid／invalid／inserted／updated／unchanged／failed counters。所有 datasets 成功才回傳 exit code 0；partial 或 failed 以非零結束，但已成功且各自完成 transaction 的 entities 不回滾。到 `/admin/` 可查看 entity、provenance、run 與 issue。

目前不因單次 missing source record 自動停用或刪除 entity。只有所有 pages 完整取得後才有資格做 missing-set 判斷，而 inactive threshold 尚待 Phase 1 資料觀察決定。

## 測試

預設 suite 不需要 database，但 host 仍需能載入 GeoDjango native libraries；缺少時使用 backend container：

```bash
docker compose build backend
docker compose run --rm --entrypoint sh \
  -e DJANGO_SETTINGS_MODULE=config.settings.test backend \
  -c 'uv sync --locked && pytest'
```

Repository tests 需要真實 PostGIS，且必須明確 opt in，避免 unit test 意外連開發資料庫：

```bash
docker compose up -d db
docker compose run --rm --entrypoint sh \
  -e DJANGO_SETTINGS_MODULE=config.settings.test \
  -e TEST_WITH_POSTGIS=true backend \
  -c 'uv sync --locked && pytest tests/integration'
```

測試設定會使用 Django 的獨立 test database，不應指向 production credentials。

TDX contract、schema 正規化理由與同步流程見 [Wiki](../wiki/architecture/tdx-parking-contract.md)。
