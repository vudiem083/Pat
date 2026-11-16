<div align="center">

# BAT — Bedrock Agent Toolkit

**Cho AI agent làm việc với Minecraft Bedrock thật — không chỉ sinh ra JSON trông có vẻ đúng.**

MCP server · REST API · Python 3.12 · Minecraft Bedrock 1.19 – 1.21.80 · MIT

[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](#cài-đặt)
[![Tests](https://img.shields.io/badge/tests-142%20passed-2ea44f)](#trạng-thái-thực-tế)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-65-6f42c1)](#bên-trong-bat)
[![REST](https://img.shields.io/badge/REST%20endpoints-51-009688)](#bên-trong-bat)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

## Vấn đề

Một AI agent có thể viết ra một `manifest.json`, một entity, một recipe trong vài giây. Nhưng nó
thường không biết:

- Minecraft có **tải được** gói đó không?
- Manifest có đúng với **phiên bản mục tiêu** (1.20.50? 1.21.80?) không?
- Tại sao server **sập** ngay sau khi cài pack — và bằng chứng nằm ở đâu?
- Tính năng này có thực sự tồn tại ở phiên bản đó, hay chỉ là ảo giác của mô hình?

Kết quả là những vòng lặp mò mẫm: agent viết, người dùng mở Minecraft, thấy lỗi, dán log lại, agent
đoán nguyên nhân, sửa sai hướng.

**BAT lấp khoảng trống đó.** Đây là bộ công cụ chạy thật, có kiểm thử, biến "viết file" thành một
quy trình có kiểm chứng: tạo → kiểm tra hợp lệ → đóng gói → chạy thử → chẩn đoán.

## BAT là gì

Một lõi nghiệp vụ duy nhất, hai giao diện:

| Giao diện | Dùng cho |
|---|---|
| **MCP server** (FastMCP) | Agent AI: 65 công cụ, 7 tài nguyên tài liệu, 2 resource template, 5 prompt |
| **REST API** (FastAPI, `/api/v1`) | Ứng dụng, CI, script: 51 endpoint có OpenAPI |

Cả hai gọi **cùng một** tầng nghiệp vụ (`bat.services.BatServices`) và trả về **cùng một** model
Pydantic. Không có chuyện REST và MCP "lệch nhau" — có hẳn một test tích hợp canh điều đó.

## Điều làm BAT khác những "máy sinh JSON"

> **Nguyên tắc:** BAT chỉ báo những gì nó thực sự quan sát được.

Cụ thể trong mã nguồn:

- **Không đoán phiên bản.** Mọi tính năng có bản ghi phiên bản kèm bằng chứng. Chưa kiểm chứng →
  `NOT_TESTED`. Không có dữ liệu → `UNKNOWN`. Không bao giờ mặc định là "hỗ trợ".
- **Không báo PASS khống.** Kết quả chạy thử chỉ có `PASS`, `FAIL`, `NOT_SUPPORTED`, `NOT_TESTED`.
  Không có server? Bạn nhận `NOT_TESTED`, không phải một dấu tích xanh giả.
- **Sập là sập.** Tiến trình chết được ghi `CRASHED` kèm incident và bằng chứng, không bị hạ cấp
  thành "timeout" cho dễ xử lý.
- **Không bịa mã lỗi.** 48 mã `BAT-*` đã đăng ký; `make_error` từ chối mã lạ.
- **Không bịa nguyên nhân.** Khi bằng chứng không đủ, chẩn đoán nói thẳng "chưa xác định".

## Bắt đầu trong 60 giây

```bash
git clone <repo-url> && cd Pat
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

bat doctor                    # kiểm tra môi trường, đường dẫn, adapter runtime
bat serve-api --port 8000     # REST: http://127.0.0.1:8000/docs
bat serve-mcp                 # MCP qua stdio cho agent
```

Chạy trọn quy trình mà không cần server Minecraft:

```bash
python examples/example_workflow.py
```

Kết quả thật từ máy (rút gọn):

```text
BAT 0.1.0 | runtime adapter: unavailable
1. project created: dd050b66-1ca9-4517-8d1e-c4ccdb41efcf
   generated item: behavior_packs/example_gem_addon/items/example_gem.json
   generated block: behavior_packs/example_gem_addon/blocks/example_ore.json
   ...
2. validation: WARN (3 findings)
   WARNING BAT-TEXTURE-001 [.../blocks/example_ore.json]: references texture 'textures/bat_...'
3. artifacts:
   MCPACK example_gem_addon_behavior.mcpack (2731 bytes, integrity_ok=True)
4. compatibility for items on 1.19.80: UNSUPPORTED (min 1.20.50)
5. runtime test: job=FAILED error=BAT-RUNTIME-003 test_status=NOT_TESTED
```

Chú ý dòng cuối: không có server thì BAT nói **NOT_TESTED** kèm mã lỗi rõ ràng — đó chính là điểm
mạnh, không phải lỗi.

## Nó làm được gì

**Dự án** — `ADDON`, `WORLD`, `COMBINED`. `COMBINED` giữ quan hệ thật giữa thế giới và pack:
`world_behavior_packs.json` / `world_resource_packs.json` được sinh từ chính các pack của dự án,
đóng gói ra cả `.mcaddon` lẫn `.mcworld`.

**Nội dung** — entity, block, item, recipe, loot table, spawn rule, animation, animation controller,
particle, attachable, script module, structure. Sinh theo phiên bản: item dùng định dạng component và
**từ chối** mục tiêu dưới 1.20.50 thay vì viết ra thứ không tải được.

**Thế giới** — đọc/ghi `level.dat` bằng codec NBT little-endian tự viết (header 8 byte), sửa metadata
có snapshot trước và đọc lại để xác minh, liên kết pack, xuất/nhập `.mcstructure`, xuất `.mcworld`.

**Kiểm tra hợp lệ** — cú pháp JSON (có số dòng), manifest (trường, UUID trùng, `min_engine_version`
so với mục tiêu), cấu trúc pack, tài liệu nội dung, texture (chữ ký PNG + IHDR + tham chiếu thiếu),
animation, dữ liệu thế giới. Kết quả là `ValidationReport` lưu lại được, có mã lỗi và bằng chứng.

**Đóng gói** — ZIP tất định, SHA-256, kiểm tra cấu trúc bên trong gói, kèm build report.

**Runtime** — adapter trừu tượng (BDS do bạn cung cấp), môi trường cách ly (sao chép, không symlink),
vòng đời server, log tăng dần, heartbeat, gửi lệnh console, phát hiện sẵn sàng, phân loại sập/treo
trung thực.

**Job** — hàng đợi SQLite: `QUEUED → STARTING → RUNNING → COMPLETED | FAILED | CRASHED | TIMED_OUT |
CANCELLED`, log/heartbeat/report lưu bền, chờ có giới hạn nhưng **không** huỷ job, huỷ tường minh,
khôi phục job mồ côi khi khởi động.

**Chẩn đoán** — incident có bản sao bằng chứng, phân tích theo chữ ký, điểm tin cậy, báo cáo tương
quan project → job → session → incident. Xoá môi trường **không** xoá bằng chứng.

## Bên trong BAT

```text
MCP tools / resources / prompts        REST /api/v1
             \                        /
              v                      v
        services.BatServices  (một object graph duy nhất)
             |
  projects · generators · validators · builders · runtime · jobs · diagnostics
             |
   SQLite  +  workspace (data/, runtime/{environments,sessions,incidents,snapshots,cache})
```

| Thành phần | Nội dung |
|---|---|
| Mã nguồn | 109 module Python, ~15.400 dòng (gồm test) |
| Kiểm thử | 142 test: unit, compatibility, integration, runtime (tiến trình mô phỏng) |
| Mã lỗi | 48 mã `BAT-*` có tài liệu, tra cứu qua `bat errors` / `GET /api/v1/error-codes` |
| Tài liệu | [Kiến trúc](docs/architecture.md) · [Tương thích](docs/compatibility.md) · [Mã lỗi](docs/error-codes.md) · [Runtime](docs/runtime.md) |
| Triển khai | [Dockerfile](Dockerfile) + [docker-compose.yml](docker-compose.yml) |

## Trạng thái thực tế

Bảng này cố tình không tô hồng:

| Hạng mục | Trạng thái |
|---|---|
| Tạo/đọc/sửa dự án, sinh nội dung, kiểm tra hợp lệ, đóng gói | **PASS** (có test) |
| Codec `level.dat` (NBT LE) và `.mcstructure` | **PASS** (round-trip, test dữ liệu hỏng) |
| Job, timeout, huỷ, khôi phục job mồ côi | **PASS** (SQLite + test) |
| Giám sát tiến trình runtime | **PASS trên tiến trình mô phỏng**; BDS thật = **NOT_TESTED** |
| Render texture/model/animation trên client | **NOT_TESTED** (cần Minecraft client) |
| Đọc chunk LevelDB | **Chưa hỗ trợ** — báo rõ, không giả vờ |
| Sinh địa hình/thế giới | **Không hỗ trợ** (Minecraft sinh, không phải BAT) |

**Giới hạn đã biết:** xem [mục 13 trong tài liệu đầy đủ](README.vi.md#13-giới-hạn-đã-biết).

## Tài liệu

- **Tiếng Việt đầy đủ (17 mục):** [README.vi.md](README.vi.md)
- **Full English reference:** [README.en.md](README.en.md)
- [Kiến trúc](docs/architecture.md) · [Tương thích phiên bản](docs/compatibility.md) ·
  [Mã lỗi](docs/error-codes.md) · [Thiết kế runtime](docs/runtime.md)
- [Bảo mật](SECURITY.md) · [Đóng góp](CONTRIBUTING.md) · [Lịch sử thay đổi](CHANGELOG.md) ·
  [Giấy phép MIT](LICENSE)

## Giấy phép và tuyên bố

MIT — xem [LICENSE](LICENSE). Minecraft là thương hiệu của Mojang Synergies AB. BAT không liên kết,
không được Mojang/Microsoft bảo trợ, và **không** phân phối lại tệp nhị phân hay tài nguyên của
Minecraft: bạn tự cung cấp `bedrock_server` nếu muốn chạy thử runtime thật.
