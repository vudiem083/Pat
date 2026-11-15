# BAT — Bedrock Agent Toolkit

**BAT** là bộ công cụ giúp các tác nhân AI (AI agent) tạo, xem, sửa, kiểm tra hợp lệ, đóng gói,
chạy thử và chẩn đoán các dự án **Minecraft Bedrock Edition** thông qua hai giao diện dùng chung
một tầng nghiệp vụ:

- **MCP server** (FastMCP) để tích hợp với tác nhân AI, và
- **REST API** (FastAPI, `/api/v1`) cho ứng dụng, hệ thống tự động hoá và các client khác.

[Tài liệu tiếng Anh](README.md) · Tài liệu tiếng Việt (tệp này)

---

## 1. Tầm nhìn sản phẩm

Tác nhân AI tạo ra JSON trông giống một pack Bedrock thì dễ. Nhưng biết chắc Minecraft có tải được
hay không, manifest có đúng với phiên bản mục tiêu hay không, hay vì sao server sập sau khi cài
pack — đó mới là vấn đề khó.

BAT giải quyết khoảng trống đó. Nguyên tắc cốt lõi:

> BAT phải giúp tác nhân AI làm việc với dự án Minecraft Bedrock **thật**, không chỉ tạo ra những
> tệp trông có vẻ hợp lệ.

Nguyên tắc này được thực thi trong mã nguồn, không chỉ ghi trong tài liệu:

- Mỗi tính năng BAT nhận là hỗ trợ đều có bản ghi theo phiên bản kèm bằng chứng. Điều chưa được
  kiểm chứng được báo là **NOT_TESTED**; điều chưa có bằng chứng là **UNKNOWN**.
- Kết quả chạy thử runtime là `PASS`, `FAIL`, `NOT_SUPPORTED` hoặc `NOT_TESTED` — không bao giờ báo
  đạt khi chưa thực sự quan sát được.
- Tiến trình sập được ghi nhận là sập kèm sự cố (incident), không bị hạ cấp thành "quá thời gian".
- Mã lỗi là một không gian tên cố định, có tài liệu; BAT từ chối phát ra mã chưa đăng ký.
- Khi bằng chứng không đủ, chẩn đoán nói rõ "chưa xác định được nguyên nhân gốc".

## 2. Phạm vi nền tảng

| | |
|---|---|
| Phiên bản | **Minecraft Bedrock Edition** (bao gồm Minecraft PE) |
| Ngoài phạm vi | Minecraft Java Edition |
| Phiên bản mục tiêu hỗ trợ | **1.19.0 – 1.21.80** |
| Mục tiêu mặc định | 1.21.80 |

BAT không tự mở rộng phạm vi phiên bản và không tự nâng phiên bản mục tiêu của dự án. Phiên bản
ngoài phạm vi bị từ chối với mã `BAT-COMPAT-001`. Trong phạm vi, từng tính năng vẫn có thể là
`UNSUPPORTED`, `NOT_TESTED` hoặc `UNKNOWN` — xem §8.

## 3. Các loại dự án

| Loại | BAT quản lý những gì |
|---|---|
| `ADDON` | Gói hành vi (Behavior Pack) + gói tài nguyên (Resource Pack): manifest, entity, block, item, recipe, loot table, spawn rule, animation, animation controller, particle, attachable, script module. |
| `WORLD` | Thế giới độc lập: siêu dữ liệu `level.dat`, `levelname.txt`, liên kết pack, structure, kiểm tra hợp lệ, ảnh chụp (snapshot) và xuất `.mcworld`. |
| `COMBINED` | Thế giới **cùng các pack đi kèm**, có liên kết pack–thế giới thật, theo dõi phụ thuộc, kiểm tra hợp lệ kết hợp, đóng gói kết hợp và chạy thử kết hợp. |

`COMBINED` không phải là một thư mục chứa các tệp rời rạc: hai tệp
`world_behavior_packs.json` / `world_resource_packs.json` được sinh từ chính các pack của dự án, và
khi đóng gói sẽ tạo cả `.mcaddon` lẫn `.mcworld`.

Cấu trúc trên đĩa:

```text
<workspace>/projects/<project_id>/
  project.json                  bản ghi dự án chuẩn
  files/                        gốc nội dung được sandbox (chỉ đường dẫn tương đối)
    behavior_packs/<pack>/manifest.json + nội dung
    resource_packs/<pack>/manifest.json + nội dung
    world/level.dat, levelname.txt, world_*_packs.json, structures/, db/
```

## 4. Năng lực chính

**Dự án** — tạo, xem, liệt kê, xoá, cây tệp, đọc/ghi/xoá tệp (ghi nguyên tử, tự tạo `.bak` khi ghi
đè, giới hạn dung lượng, chặn path traversal và symlink).

**Add-on** — sinh manifest và tài liệu nội dung theo phiên bản; item dùng định dạng component và từ
chối phiên bản dưới 1.20.50 thay vì tạo nội dung không thể tải.

**Thế giới** — đọc/ghi `level.dat` NBT little-endian thật (header 8 byte), sửa siêu dữ liệu sau khi
tạo snapshot và kiểm tra lại bằng cách đọc tệp sau khi ghi, liên kết pack, tạo/nhập/xuất
`.mcstructure`, xuất `.mcworld`.

**Kiểm tra hợp lệ** — cú pháp JSON (kèm số dòng), manifest (trường bắt buộc, UUID, trùng lặp,
`min_engine_version` so với phiên bản mục tiêu, tệp entry của script), cấu trúc pack, tài liệu nội
dung (entity/block/item/recipe), texture (chữ ký PNG + IHDR, texture được tham chiếu nhưng thiếu),
animation và controller, dữ liệu thế giới và liên kết pack. Kết quả là `ValidationReport` được lưu
lại với phát hiện, mã lỗi, thông tin tương thích và bằng chứng.

**Đóng gói** — `.mcpack`, `.mcaddon`, `.mcworld` với thứ tự ZIP ổn định, checksum SHA-256, kiểm tra
cấu trúc bên trong tệp nén và báo cáo build.

**Runtime** — lớp adapter trừu tượng với adapter Bedrock Dedicated Server (dùng tệp nhị phân do
người vận hành cung cấp), môi trường cách ly, vòng đời server, thu thập log tăng dần, heartbeat, gửi
lệnh console, phát hiện trạng thái sẵn sàng, phân loại sập/không phản hồi một cách trung thực.

**Tác vụ nền (jobs)** — lưu trong SQLite với các trạng thái `QUEUED → STARTING → RUNNING →
COMPLETED | FAILED | CRASHED | TIMED_OUT | CANCELLED`, log được lưu bền, heartbeat, chờ có giới hạn
thời gian nhưng **không** huỷ job, huỷ tường minh và phục hồi job mồ côi khi khởi động.

**Chẩn đoán** — sự cố kèm bằng chứng được sao lưu, phân tích theo chữ ký (signature), điểm tin cậy
và báo cáo chẩn đoán có liên kết dự án → job → session → sự cố.

## 5. Kiến trúc

```text
MCP tools / resources / prompts        REST /api/v1 routes
             \                        /
              v                      v
        services.BatServices (một container dịch vụ duy nhất)
             |
  +----------+-----------+-----------+-----------+----------+---------+
  |          |           |           |           |          |         |
projects  generators  validators   builders   runtime    jobs   diagnostics
  |          |           |           |           |          |         |
  +----------+-----------+-----------+-----------+----------+---------+
                              |
                SQLite (projects, jobs, artifacts, reports,
                        sessions, incidents, environments)
                Hệ thống tệp (workspace data/, runtime/)
```

Hai giao diện gọi cùng một hàm và trả về cùng một mô hình dữ liệu, nên REST và MCP không thể lệch
nhau. Sự tương đồng này có kiểm thử tích hợp riêng.

### Cấu trúc kho mã

```text
src/bat/
  config.py            cấu hình từ biến môi trường (bất biến)
  services.py          container dịch vụ + đăng ký job (dùng chung cho MCP và REST)
  cli.py               dòng lệnh `bat`
  core/                mô hình, sổ mã lỗi, hệ thống tệp an toàn, dự án, bộ mã hoá NBT
  compatibility/       phiên bản, registry, component/script registry, ma trận, checker
  generators/          addon, entity, block, item, recipe, loot, spawn, animation,
                       particle, attachable, script, world, structure
  validators/          json, manifest, pack, documents, texture, animation, world, engine
  builders/            mcpack, mcaddon, mcworld, packaging, inspection, engine
  runtime/             adapter, environment manager, server manager, log parser, tester, report
  jobs/                máy trạng thái, manager, worker context, heartbeat, scheduler
  diagnostics/         evidence, classifier, analyzer, incidents, correlation, report
  observability/       log JSON có cấu trúc (che bí mật, xoay vòng), health, metrics
  storage/             cơ sở dữ liệu SQLite, bố cục runtime
  api/                 ứng dụng FastAPI, dependencies, schemas, routes
  mcp/                 FastMCP server, tools, resources, prompts
tests/
  unit/  integration/  compatibility/  runtime/
docs/                  kiến trúc, tương thích, mã lỗi, runtime
examples/              script chạy lát cắt đầu tiên, cấu hình MCP client
runtime/               bố cục runtime đã được phê duyệt (environments, sessions,
                       incidents, snapshots, cache) — xem docs/runtime.md
```

## 6. Cài đặt

Yêu cầu: **Python 3.10+** (đã kiểm thử với 3.12), `pip`, shell POSIX. Để chạy thử runtime bạn cần
tệp nhị phân Minecraft Bedrock Dedicated Server của riêng bạn — BAT không tải, không đóng gói và
không phân phối lại tệp này.

```bash
git clone <url-kho-rieng-cua-ban> bedrock-agent-toolkit
cd bedrock-agent-toolkit
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # sau đó chỉnh sửa
bat doctor                    # kiểm tra cấu hình
```

`bat doctor` in ra đường dẫn thực tế, trạng thái cơ sở dữ liệu, khả năng sẵn sàng của runtime
adapter và các loại job đã đăng ký. Trên máy không có tệp nhị phân server, kết quả là
`runtime_available: false` — đây là trạng thái bình thường và nghĩa là các bài kiểm thử runtime sẽ
là `NOT_TESTED`.

## 7. Cấu hình

Toàn bộ cấu hình qua biến môi trường (xem `.env.example`). Các biến chính:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BAT_WORKSPACE` | `./data` | Dữ liệu dự án, artifact, SQLite, log của job |
| `BAT_RUNTIME_ROOT` | `./runtime` | Environments, sessions, incidents, snapshots, cache |
| `BAT_DATABASE` | `$BAT_WORKSPACE/bat.db` | Tệp cơ sở dữ liệu SQLite |
| `BAT_API_KEY` | *(rỗng)* | Khi đặt, `/api/v1` yêu cầu `X-API-Key` hoặc `Authorization: Bearer` |
| `BAT_RUNTIME_ADAPTER` | `auto` | `auto`, `bds` hoặc `none` |
| `BAT_BEDROCK_SERVER` | *(rỗng)* | Đường dẫn tới `bedrock_server` **của bạn** |
| `BAT_SERVER_START_TIMEOUT` | `120` | Số giây chờ server sẵn sàng |
| `BAT_HEARTBEAT_INTERVAL` | `5` | Chu kỳ ghi heartbeat |
| `BAT_UNRESPONSIVE_SECONDS` | `90` | Ngưỡng không có output trước khi tạo sự cố `UNRESPONSIVE` |
| `BAT_MAX_FILE_BYTES` | `10485760` | Giới hạn dung lượng tệp dự án |
| `BAT_LOG_MAX_BYTES` / `BAT_LOG_BACKUP_COUNT` | `2097152` / `5` | Xoay vòng log của BAT |
| `BAT_JOB_WORKERS` | `4` | Số luồng worker nền |
| `BAT_DEFAULT_WAIT_SECONDS` / `BAT_MAX_WAIT_SECONDS` | `30` / `300` | Giới hạn thời gian chờ job |

## 8. Tương thích phiên bản

Tương thích là một hệ thống con thực sự, không phải ghi chú phụ. `get_compatibility(<phiên bản>)`
trả về ma trận, mỗi mục gồm:

```json
{
  "feature": "item.components",
  "category": "item",
  "status": "UNSUPPORTED",
  "min_version": "1.20.50",
  "evidence": "Tài liệu component item của Bedrock 1.20.50",
  "notes": "Định dạng item dựa trên component. Các dự án cũ dùng định dạng legacy ..."
}
```

Trạng thái: `SUPPORTED` (BAT đã thực sự chạy), `UNSUPPORTED` (phiên bản quá cũ/mới, hoặc ngoài phạm
vi), `NOT_TESTED` (có tài liệu nhưng chưa chạy với runtime thật), `UNKNOWN` (không có bằng chứng —
BAT không đoán). Chi tiết: [docs/compatibility.md](docs/compatibility.md).

## 9. Chạy REST API

```bash
export BAT_WORKSPACE=./data BAT_RUNTIME_ROOT=./runtime
bat serve-api --host 127.0.0.1 --port 8000
# hoặc: python -m uvicorn "bat.api.app:create_app" --factory --port 8000
```

- Giao diện OpenAPI: <http://127.0.0.1:8000/docs> (`/openapi.json` cho schema)
- Sức khoẻ hệ thống: `GET /api/v1/health` → `{"status": "OK" | "DEGRADED", ...}`
- Thông tin phiên bản: `GET /api/v1/version`

Ví dụ phiên làm việc (đã kiểm chứng với kho mã này):

```bash
BASE=http://127.0.0.1:8000/api/v1

# 1. tạo dự án add-on
PID=$(curl -s -X POST $BASE/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"My Addon","project_type":"ADDON","target_version":"1.21.80"}' \
  | python -c 'import json,sys;print(json.load(sys.stdin)["project"]["project_id"])')

# 2. ghi tệp (đường dẫn tương đối, nằm trong dự án)
curl -s -X PUT $BASE/projects/$PID/files/resource_packs/readme.txt \
  -H 'Content-Type: application/json' -d '{"content":"hello"}'

# 3. kiểm tra hợp lệ
curl -s -X POST $BASE/projects/$PID/validate | python -m json.tool | head -20

# 4. đóng gói và tải về
AID=$(curl -s -X POST $BASE/projects/$PID/build -H 'Content-Type: application/json' -d '{}' \
  | python -c 'import json,sys;print(json.load(sys.stdin)["artifacts"][0]["artifact_id"])')
curl -s -o myaddon.mcaddon $BASE/artifacts/$AID/download
```

Xác thực: khi đặt `BAT_API_KEY`, gửi khoá qua `X-API-Key: <key>` hoặc
`Authorization: Bearer <key>`. Hai endpoint health/version luôn công khai. Nếu không đặt khoá thì
xác thực bị tắt — chỉ nên mở API trên localhost.

Tác vụ bất đồng bộ: `POST /api/v1/jobs` trả `202` kèm id job; theo dõi bằng
`GET /api/v1/jobs/{id}` hoặc gọi `POST /api/v1/jobs/{id}/wait` với thời gian chờ có giới hạn.
**Hết thời gian chờ KHÔNG huỷ job.** Huỷ bằng `POST /api/v1/jobs/{id}/cancel`.

## 10. Chạy MCP server

```bash
bat serve-mcp            # transport stdio (mặc định)
bat serve-mcp --transport sse
bat serve-mcp --transport streamable-http
```

Ví dụ cấu hình MCP client (xem `examples/mcp-client.json`):

```json
{
  "mcpServers": {
    "bat": {
      "command": "/duong/dan/tuyet/doi/.venv/bin/bat",
      "args": ["serve-mcp"],
      "env": {
        "BAT_WORKSPACE": "/duong/dan/tuyet/doi/data",
        "BAT_RUNTIME_ROOT": "/duong/dan/tuyet/doi/runtime"
      }
    }
  }
}
```

### Quy ước công cụ

Mọi công cụ trả về một phong bì (envelope) để tác nhân rẽ nhánh theo `ok`:

```json
{"ok": true, "result": { ... }}
{"ok": false, "error": {"error_code": "BAT-COMPAT-001", "message": "...", "details": {}, "severity": "ERROR", "retryable": false}}
```

Có 65 công cụ: dự án (8), sinh nội dung add-on (12), thế giới (8), kiểm tra hợp lệ (8), đóng gói
(7), runtime (11), job/sức khoẻ (8), chẩn đoán (3). Tài nguyên (resources):
`bat://docs/bedrock/{versions,manifest,entities,blocks,items,scripts,worlds}`,
`bat://projects/{project_id}/tree`, `bat://projects/{project_id}/report`. Prompt:
`create_addon_prompt`, `create_world_prompt`, `debug_addon_prompt`,
`fix_validation_errors_prompt`, `analyze_runtime_logs_prompt`.

## 11. Lát cắt hoạt động đầu tiên

```text
Tác nhân AI → create_project → write_project_file / generators → validate_project
            → build_project → artifact (.mcaddon) → inspect_artifact
```

Phiên bản chạy được (tạo dự án thật, kiểm tra, đóng gói và soi artifact):

```bash
python examples/example_workflow.py
```

Lát cắt mở rộng (cần tệp nhị phân server của bạn):

```text
run_game_test → job → môi trường cách ly → server khởi động → log + heartbeat
              → báo cáo runtime / sự cố
```

## 12. Chạy thử runtime và chẩn đoán

```bash
# nếu chưa có server, lệnh này thất bại với BAT-RUNTIME-003 và test_status = NOT_TESTED
curl -s -X POST $BASE/jobs -H 'Content-Type: application/json' \
  -d "{\"job_type\":\"RUNTIME_TEST\",\"project_id\":\"$PID\"}"
```

Khi đã có server:

```bash
export BAT_RUNTIME_ADAPTER=bds
export BAT_BEDROCK_SERVER=/duong/dan/bedrock_server   # tệp nhị phân của bạn
```

BAT tạo môi trường cách ly trong `runtime/environments/<env_id>/`, sao chép pack và thế giới vào
(không bao giờ dùng liên kết tượng trưng), ghi `server.properties`, chọn cổng UDP trống, khởi động
tiến trình, phát hiện trạng thái sẵn sàng từ log, thu log tăng dần, ghi heartbeat rồi dừng server.

Kết quả tách rõ phần đã kiểm chứng và phần chưa:

```json
{
  "test_status": "PASS",
  "scope": "SERVER_SIDE",
  "verified": ["Tiến trình Bedrock server đã khởi động và báo sẵn sàng.", "..."],
  "not_verified": [
    "Giao diện, texture, UI và attachable là phía client — server không kiểm chứng được.",
    "Hành vi gameplay, cân bằng và trải nghiệm người chơi không được khẳng định.",
    "GameTest là NOT_TESTED trừ khi bản server của bạn hỗ trợ và có harness chạy tường minh.",
    "Luồng nhập trên mobile/console không được kiểm thử."
  ]
}
```

Truy xuất bằng chứng:

| Nội dung | REST | MCP |
|---|---|---|
| Trạng thái / log / báo cáo job | `/jobs/{id}`, `/jobs/{id}/logs`, `/jobs/{id}/report` | `get_job_status`, `get_job_logs`, `get_job_report` |
| Trạng thái / log / heartbeat / báo cáo session | `/runtime/sessions/{id}/...` | `get_runtime_status`, `get_runtime_logs`, `get_runtime_heartbeat`, `get_runtime_report` |
| Sự cố | `/incidents`, `/incidents/{id}`, `/incidents/{id}/diagnose` | `get_incidents`, `get_incident_details`, `diagnose_incident` |

Khi tiến trình thoát bất thường, BAT tạo `runtime/incidents/<incident_id>/` gồm `incident.json`,
`diagnosis.json` và thư mục `evidence/` (log console/error/runtime của session, báo cáo session,
log job). Huỷ môi trường hoặc xoá dự án **không** xoá sự cố, session hay snapshot.

## 13. Hạn chế đã biết

Đây là những hạn chế thật và hiện tại. Chúng cũng được mã hoá trong chương trình để BAT báo cáo
thay vì che giấu.

1. **Chưa kiểm chứng với Minecraft thật trong kho mã này.** Phần giám sát runtime được kiểm thử
   bằng một tiến trình server *mô phỏng* (sẵn sàng, log, heartbeat, lệnh console, dừng êm, phân
   loại sập, phát hiện không phản hồi). Việc chạy Bedrock Dedicated Server thực tế là **NOT_TESTED**
   ở đây vì không kèm tệp nhị phân server. Muốn kiểm chứng thật, bạn phải cung cấp tệp đó.
2. **Tính năng phía client không thể kiểm chứng bằng adapter server.** Texture, rendering,
   attachable, particle, UI và luồng nhập trên mobile chỉ được kiểm tra cấu trúc; trạng thái là
   `NOT_TESTED`.
3. **Không có bộ đọc LevelDB.** `get_world_chunks` báo có/không có dữ liệu chunk và nói rõ BAT
   không liệt kê chunk.
4. **Tạo thế giới ở mức siêu dữ liệu.** BAT ghi `level.dat` hợp lệ và bộ khung thế giới; địa hình và
   chunk do Minecraft sinh ra khi tải lần đầu. Tệp `.mcworld` xuất trước khi tải lần nào sẽ không có
   dữ liệu chunk (được ghi trong báo cáo build).
5. **Registry tương thích là danh mục chọn lọc, không đầy đủ.** Tính năng lạ là `UNKNOWN`; BAT không
   ghim phiên bản phụ của Script API.
6. **Chỉ chạy một máy.** SQLite + hệ thống tệp cục bộ; không có worker phân tán, Redis hay PostgreSQL.
7. **Xác thực chỉ là API key tĩnh.** Không có tài khoản người dùng, phân quyền hay cách ly đa tổ chức.
8. **Chỉ hỗ trợ định dạng item từ 1.20.50.** Tài liệu item legacy bị báo là không hỗ trợ sinh tự
   động thay vì tạo ra nội dung không kiểm chứng được.
9. **Huỷ job là hợp tác (cooperative).** Job được đánh dấu `CANCELLED`/`TIMED_OUT` và phát tín hiệu;
   handler đang kẹt trong lời gọi hệ điều hành sẽ dừng ở điểm kiểm tra kế tiếp.
10. **Chưa có adapter cách ly bằng Docker.** Giao diện adapter cho phép bổ sung, nhưng hiện chỉ có
    adapter tiến trình con BDS. `Dockerfile` đóng gói chính BAT, không đóng gói Minecraft.
11. **Chạy thử runtime không khẳng định gameplay.** `PASS` chỉ có nghĩa "server tải được với các
    pack đã cài và không báo lỗi pack/script", không hơn.

## 14. Kiểm thử

```bash
pytest                                   # toàn bộ (142 bài)
pytest tests/unit tests/integration       # bộ nhanh
pytest tests/runtime -m simulated         # giám sát tiến trình server mô phỏng
pytest -m "not simulated"                 # loại trừ bài dùng tiến trình mô phỏng
```

Từ vựng kết quả: `PASS`, `FAIL`, `NOT_SUPPORTED`, `NOT_TESTED`. Không bài kiểm thử nào bị bỏ qua
hoặc làm yếu để có bộ test xanh, và không bài nào tuyên bố đã kiểm chứng Minecraft thật.
Server mô phỏng trong `tests/runtime` chỉ là một script Python nhỏ, dùng để kiểm tra phần giám sát
tiến trình của BAT.

Phạm vi kiểm thử: unit (phiên bản, an toàn hệ thống tệp, vòng lặp NBT, dự án, generator, validator,
builder, structure, máy trạng thái job/hết giờ/huỷ/phục hồi job mồ côi, chẩn đoán, mã lỗi),
compatibility (trạng thái, ma trận, tính năng không hỗ trợ), integration (REST
tạo→ghi tệp→kiểm tra→đóng gói→tải về, job, sự cố, API key, MCP registry/lỗi/resources/prompts/
tương đồng với REST), runtime (sẵn sàng, log tăng dần, lệnh console, dừng êm, sập → sự cố, không
phản hồi ≠ sập, thiếu tệp nhị phân → `NOT_TESTED`, cách ly môi trường và cam kết dọn dẹp).

## 15. Bảo mật

Xem [SECURITY.md](SECURITY.md). Điểm chính: mọi đường dẫn từ bên ngoài đều qua `resolve_within`
(từ chối đường dẫn tuyệt đối, `..` và symlink); tệp dự án được ghi nguyên tử với giới hạn dung
lượng; môi trường runtime được sao chép, không liên kết, và đường dẫn được kiểm tra nằm trong gốc
runtime; tiến trình server nhận môi trường tối thiểu và thư mục session riêng; log che các bí mật rõ
ràng; không cần bí mật nào trong tệp dự án; API key được so sánh theo thời gian hằng. BAT không
chạy chuỗi shell: nó chạy đúng một tệp thực thi đã cấu hình với `shell=False`.

Xoá dữ liệu: `delete_project` giữ lại sự cố, session và artifact trừ khi bạn truyền
`purge_artifacts=true`; `destroy_test_environment` giữ lại sự cố, session và snapshot.

## 16. Đóng góp

Xem [CONTRIBUTING.md](CONTRIBUTING.md). Tóm tắt: giữ cả hai giao diện trên cùng tầng dịch vụ, đăng
ký mã lỗi mới trước khi phát ra, thêm kiểm thử cho hành vi bạn tuyên bố, và không bao giờ báo một
trạng thái mà BAT chưa quan sát được.

## 17. Giấy phép

MIT — xem [LICENSE](LICENSE). Minecraft là thương hiệu của Mojang Synergies AB. BAT không liên kết
và không được Mojang hay Microsoft bảo trợ; BAT không phân phối lại tệp nhị phân hay tài nguyên của
Minecraft.
