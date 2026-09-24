# Hướng dẫn tích hợp Tricount API Adapter

Tài liệu này mô tả API FastAPI để một dịch vụ khác gọi vào. Adapter bọc private API không chính thức của Tricount; API upstream có thể đổi mà không báo trước.

## Kết nối

- Chạy từ máy host: `http://localhost:43765` theo cấu hình Compose hiện tại.
- Dịch vụ ở cùng Docker Compose network: `http://tricount-api:8000`.
- Swagger UI: `/docs`.
- OpenAPI JSON: `/openapi.json`.

Adapter hiện chưa yêu cầu API key ở phía service. Chỉ cho dịch vụ tin cậy trong mạng nội bộ gọi vào; không đưa share token hoặc các route ghi ra trình duyệt hay mạng công cộng.

## Luồng tích hợp khuyến nghị

1. Khi thêm tricount chia sẻ mới, gửi một hoặc nhiều share token tới `POST /tricounts/sync`.
2. Lấy `id` và `name` trong `items` để hiển thị/chọn tricount.
3. Lấy thành viên bằng `GET /tricounts/{registry_id}/members`; dùng `uuid` của thành viên cho entry.
4. Lấy category hợp lệ từ `GET /metadata/categories`.
5. Đọc, thêm, sửa hoặc xóa entry bằng các route dưới `/tricounts/{registry_id}/entries`.

Adapter đồng bộ tricount chia sẻ với session trước khi lấy member hoặc ghi entry. Việc này có thể thêm tricount vào session Tricount hiện tại.

## Danh sách routes

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/health` | Kiểm tra adapter đang chạy |
| `POST` | `/tricounts/sync` | Đồng bộ một hoặc nhiều tricount bằng share token |
| `GET` | `/tricounts` | Danh sách registry đầy đủ |
| `GET` | `/tricounts/summary` | Danh sách registry rút gọn |
| `GET` | `/tricounts/{registry_id}` | Chi tiết registry |
| `GET` | `/tricounts/{registry_id}/members` | Thành viên của registry |
| `GET` | `/tricounts/{registry_id}/entries` | Entries của registry |
| `GET` | `/tricounts/{registry_id}/entries/{entry_id}` | Một entry |
| `POST` | `/tricounts/{registry_id}/entries` | Tạo entry |
| `PUT` | `/tricounts/{registry_id}/entries/{entry_id}` | Thay thế/cập nhật entry |
| `DELETE` | `/tricounts/{registry_id}/entries/{entry_id}` | Xóa entry |
| `GET` | `/metadata/categories` | Các category mà adapter biết |
| `GET` | `/exchange-rates?currency=USD` | Tỷ giá theo currency nguồn |
| `GET` | `/profile` | User của session adapter |

## Đồng bộ share token

Gửi token trong JSON body, không gửi token trong URL:

```http
POST /tricounts/sync
Content-Type: application/json
```

```json
{
  "share_tokens": [
    "tShareTokenOne",
    "tShareTokenTwo"
  ]
}
```

Response mẫu:

```json
{
  "items": [
    {
      "id": 118548258,
      "name": "Trip",
      "currency": "VND",
      "emoji": "💴",
      "status": "READ_WRITE"
    }
  ],
  "errors": [
    {
      "index": 1,
      "status_code": 404,
      "message": "Could not sync share token"
    }
  ]
}
```

`errors[].index` là vị trí token trong mảng request, bắt đầu từ `0`. Token không được trả lại trong response. Các token trùng nhau được xử lý một lần; các token thành công vẫn được trả trong `items` dù token khác lỗi.

Chỉ cần gọi route này một lần cho mỗi tricount chia sẻ mới. Các tricount đã gắn với session sẽ xuất hiện trong `GET /tricounts` và không cần gửi token lại. Request cũ với một token vẫn được hỗ trợ:

```json
{"share_token": "tShareTokenOne"}
```

Request dạng đơn trả về một metadata object thay vì object `{ "items": [...], "errors": [...] }`.

## Danh sách registry

`GET /tricounts/summary` trả dữ liệu gọn cho danh sách hoặc dropdown:

```json
[
  {
    "id": 118548258,
    "name": "Trip",
    "currency": "VND",
    "emoji": "💴",
    "status": "READ_WRITE"
  }
]
```

`id` là `registry_id` dùng trong các URL. `name` được adapter lấy từ trường upstream `title`. `GET /tricounts` và `GET /tricounts/{registry_id}` trả dữ liệu đầy đủ hơn, có thể gồm members, entries và attachment metadata.

## Thành viên và category

`GET /tricounts/{registry_id}/members` trả danh sách member. Các trường quan trọng khi tạo entry:

```json
[
  {
    "id": 497163173,
    "uuid": "ad63c6f0-4145-41f3-ba9d-36074d43e492",
    "alias": {
      "display_name": "Alex"
    },
    "status": "ACTIVE"
  }
]
```

Dùng `uuid` cho `membership_uuid_owner` và `allocations[].membership_uuid`. `id` của member là ID riêng, không dùng thay cho UUID trong entry.

`GET /metadata/categories` trả hai nhóm category tĩnh theo các giá trị quan sát được:

```json
{
  "registry": ["GENERAL", "OTHER", "TRAVEL", "FOOD_AND_DRINK", "TRANSPORT", "SHOPPING", "ENTERTAINMENT", "GROCERIES"],
  "entry": ["TRAVEL", "ENTERTAINMENT", "GROCERIES", "HEALTHCARE", "INSURANCE", "RENT_AND_UTILITIES", "FOOD_AND_DRINK", "SHOPPING", "TRANSPORT", "OTHER", "UNCATEGORIZED"],
  "custom_entry_category_field": "category_custom"
}
```

Đây là metadata trong adapter, không phải API upstream để liệt kê category. Có thể gửi `category_custom` khi cần tên category riêng.

## CRUD entries

### Tạo

```http
POST /tricounts/118548258/entries
Content-Type: application/json
```

```json
{
  "description": "Dinner",
  "amount": {"value": "-100000", "currency": "VND"},
  "membership_uuid_owner": "<payer-member-uuid>",
  "allocations": [
    {
      "membership_uuid": "<member-uuid>",
      "amount": {"value": "-100000", "currency": "VND"},
      "type": "AMOUNT"
    }
  ],
  "date": "2026-09-24 20:30:00.000000",
  "category": "FOOD_AND_DRINK"
}
```

`uuid` được adapter tự sinh nếu bỏ qua. `type_transaction` mặc định là `NORMAL`; `status` mặc định là `ACTIVE`. Response thường là `{"id": 2074034054}`. `id` này là `entry_id`, khác với `registry_id`.

### Đọc

```text
GET /tricounts/118548258/entries
GET /tricounts/118548258/entries/2074034054
```

List trả về entries đã bỏ wrapper upstream `RegistryEntry`. Detail đọc bằng cách tìm `entry_id` trong registry response.

### Cập nhật

`PUT /tricounts/{registry_id}/entries/{entry_id}` yêu cầu toàn bộ transaction object, không phải partial update. Gửi lại các trường như `description`, `amount`, `membership_uuid_owner`, `allocations`, `type_transaction`, `status`, `date`; `uuid` có thể bỏ qua.

### Xóa

```text
DELETE /tricounts/118548258/entries/2074034054
```

Response thường có ID upstream; nếu upstream trả body rỗng, adapter trả `{"id": 2074034054, "deleted": true}`.

### Quy ước amount

- Gửi `amount.value` và `allocations[].amount.value` dưới dạng chuỗi thập phân, ví dụ `"-100000"`.
- Expense dùng số âm; income/refund dùng số dương.
- `type_transaction`: `NORMAL` (expense), `INCOME` (income/refund), `BALANCE` (transfer).
- `currency` là mã ba ký tự như `VND`, `JPY`, `USD`.
- Với split theo tỷ lệ, `allocations[].type` là `RATIO` và gửi thêm `share_ratio`.

## Tỷ giá và profile

`GET /exchange-rates?currency=USD` trả danh sách tỷ giá. Mỗi object có `currency_source`, `currency_target` và `rate`; diễn giải theo tài liệu upstream là `1 source = rate × target`.

`GET /profile` trả user object của session adapter, ví dụ `id`, `display_name`, `public_uuid`, `status` và `language`.

## Lỗi và giới hạn

- Lỗi từ adapter theo dạng FastAPI `{"detail": "..."}`. Các lỗi 4xx upstream giữ status; lỗi upstream 5xx được map thành 502. Timeout upstream trả 504.
- Adapter tự đăng ký session và thử tạo session lại một lần nếu upstream trả 401.
- Amount, alias và một số object upstream có thể có thêm trường; client nên bỏ qua trường không dùng và không giả định response luôn có schema cố định.
- API Tricount là private/unofficial. Endpoint settlement hiện được tài liệu ghi nhận là không khả dụng; không dựa vào endpoint đó để tính số dư.
- Share token là credential có thể cấp quyền truy cập tricount. Không lưu trong URL, browser storage hoặc log. Adapter hiện chưa có xác thực service-to-service.
