# Tricount FastAPI adapter

Adapter thử nghiệm cho private API của Tricount. Adapter đọc tricounts, thành viên, tỷ giá, profile, metadata category và hỗ trợ CRUD entry; tài khoản thiết bị, session và share token được giữ ở backend. API gốc là API riêng tư, có thể thay đổi mà không báo trước.

Hướng dẫn tích hợp cho dịch vụ khác: [INTEGRATION_API.md](INTEGRATION_API.md).

## Chạy bằng Docker Compose

```bash
cp .env.example .env
```

Share token không cần cấu hình trong `.env`. Gửi token động qua `POST /tricounts/sync` khi muốn thêm tricount chia sẻ vào session. Sau đó chạy:

```bash
docker compose up --build
```

Compose mount toàn bộ thư mục dự án vào container và bật Uvicorn reload. Khi sửa file Python, ứng dụng tự nạp lại mà không cần build image. Chỉ cần build lại khi thay đổi dependency hoặc Dockerfile.

Mở Swagger UI tại <http://localhost:43765/docs>.

## Endpoints

- `GET /health` — kiểm tra adapter.
- `GET /profile` — thông tin user của session hiện tại.
- `GET /metadata/categories` — danh sách category registry và entry được adapter biết.
- `GET /exchange-rates?currency=USD` — tỷ giá theo currency nguồn.
- `GET /tricounts` — liệt kê các tricount đã gắn với session.
- `POST /tricounts/sync` — đồng bộ một hoặc nhiều tricount bằng share token gửi trong request body, không cần sửa `.env`.
- `GET /tricounts/summary` — danh sách gọn gồm `id`, `name`, `currency`, `emoji`, `status`.
- `GET /tricounts/{registry_id}` — đọc một tricount.
- `GET /tricounts/{registry_id}/members` — danh sách thành viên và UUID trong tricount.
- `GET /tricounts/{registry_id}/entries` — đọc giao dịch trong tricount.
- `GET /tricounts/{registry_id}/entries/{entry_id}` — đọc một entry.
- `POST /tricounts/{registry_id}/entries` — thêm expense vào tricount.
- `PUT /tricounts/{registry_id}/entries/{entry_id}` — cập nhật entry bằng toàn bộ transaction object.
- `DELETE /tricounts/{registry_id}/entries/{entry_id}` — xóa entry.

Để thêm tricount bằng token động, gọi `POST /tricounts/sync` với body:

```json
{
  "share_tokens": [
    "tShareTokenOne",
    "tShareTokenTwo"
  ]
}
```

Response có `items` với metadata gọn (`id`, `name`, `currency`, `emoji`, `status`) và `errors` cho token không đồng bộ được. `errors[].index` trỏ về vị trí token trong request; token không được lặp lại trong response. Dùng `id` trong `items` cho các route tricount/entry. Body cũ `{ "share_token": "..." }` vẫn được hỗ trợ cho một token và trả về một metadata object. Share token là credential, gửi trong body thay vì query string.

Payload tối thiểu cho `POST /tricounts/{registry_id}/entries`:

```json
{
  "description": "Dinner",
  "amount": {"value": "-1200", "currency": "JPY"},
  "membership_uuid_owner": "<payer-member-uuid>",
  "allocations": [
    {
      "membership_uuid": "<member-uuid>",
      "amount": {"value": "-1200", "currency": "JPY"},
      "type": "AMOUNT"
    }
  ],
  "date": "2026-09-23 20:30:00.000000"
}
```

Adapter tự tạo `uuid`, mặc định `type_transaction` là `NORMAL` và `status` là `ACTIVE`. Amount của expense theo convention trong tài liệu Tricount là số âm; các giá trị tiền gửi dạng chuỗi.

`PUT` yêu cầu đầy đủ `description`, `amount`, `membership_uuid_owner`, `allocations`, `type_transaction`, `status`, và `date`, tương tự payload `POST`. `uuid` có thể bỏ qua khi cập nhật.

Khi đọc members hoặc ghi entry vào tricount được chia sẻ, adapter đồng bộ tricount bằng share token trước thao tác đầu tiên trong vòng đời process. Việc đồng bộ có thể thêm tricount vào session Tricount hiện tại.

Lần gọi đầu tiên tự đăng ký session với Tricount. UUID thiết bị và RSA private key được lưu trong Docker volume `tricount-data` để dùng lại sau khi restart.

Port được publish tại `43765`. Để xóa danh tính thiết bị thử nghiệm, chạy `docker compose down -v`; lệnh này cũng xóa volume dữ liệu của adapter.
