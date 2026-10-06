# KhoSlide - bản 100% FREE

## Kiến trúc
- Render Free: chạy Flask/Gunicorn.
- Supabase Free: PostgreSQL + Private Storage.
- SePay: webhook thanh toán.

Không dùng SQLite hoặc thư mục local của Render để lưu dữ liệu lâu dài.

## Environment Variables trên Render

Bắt buộc:
- KHOSLIDE_PUBLIC=1
- KHOSLIDE_COOKIE_SECURE=1
- KHOSLIDE_SECRET_KEY=<chuoi-ngau-nhien-dai>
- KHOSLIDE_ADMIN_USERNAME=<tai-khoan-admin>
- KHOSLIDE_ADMIN_PASSWORD=<mat-khau-manh>
- DATABASE_URL=<Supabase connection string>
- SUPABASE_URL=https://<project-ref>.supabase.co
- SUPABASE_SERVICE_ROLE_KEY=<service_role_key>
- SUPABASE_BUCKET=khoslide-files
- SEPAY_API_KEY=<SePay API key>
- KHOSLIDE_BANK_CODE=MB
- KHOSLIDE_BANK_ACCOUNT=04919512345555
- KHOSLIDE_BANK_OWNER=NGUYEN LE THE AN
- KHOSLIDE_PAYMENT_PREFIX=KSL

## Lưu ý bảo mật
Không commit `SUPABASE_SERVICE_ROLE_KEY`, `SEPAY_API_KEY`, secret key hoặc mật khẩu admin vào GitHub. Chỉ đặt chúng trong Render Environment Variables.

## Storage
App tự tạo private bucket `khoslide-files` nếu bucket chưa tồn tại. File tải xuống được cấp signed URL ngắn hạn sau khi đơn đã PAID.

## Giới hạn FREE
Render Free có thể ngủ sau 15 phút không có request và mất khoảng một phút để thức dậy. Render Free filesystem là ephemeral, vì vậy app không lưu database/file ở local filesystem.
Supabase Free hiện có 500 MB database, 1 GB Storage và 5 GB egress; file Storage Free tối đa 50 MB/file.
