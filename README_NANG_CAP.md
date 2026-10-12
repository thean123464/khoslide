# KhoSlide — bản nâng cấp đồng bộ

## Bao gồm
- Backend Flask dựa trên bản Render/Supabase hiện có, giữ thanh toán SePay, QR, tải file signed URL và quản trị.
- Supabase Auth OAuth PKCE cho Google/Facebook; bình luận yêu cầu đăng nhập.
- Zalo 0355915884 ở footer.
- Mô tả sản phẩm, duyệt đơn miễn phí, bật miễn phí thủ công hoặc tự mở khi đạt ngưỡng đơn trả phí.
- Tự chạy ALTER TABLE an toàn khi khởi động để thêm cột/bảng.

## Biến môi trường cần có trên Render
Giữ nguyên các biến đang dùng: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`, `KHOSLIDE_PUBLIC`, `KHOSLIDE_COOKIE_SECURE`, `KHOSLIDE_SECRET_KEY`, `KHOSLIDE_ADMIN_USERNAME`, `KHOSLIDE_ADMIN_PASSWORD`, thông tin ngân hàng và `SEPAY_API_KEY`.
Thêm `SUPABASE_ANON_KEY` (Supabase Dashboard → Project Settings → API → anon/public key) và `APP_BASE_URL=https://khoslide.onrender.com`. Không dùng service-role key làm anon key.

## Bật Google/Facebook
Supabase Dashboard → Authentication → Providers: bật Google và Facebook, điền thông tin OAuth Client ID/Secret do từng nhà cung cấp cấp. Trong Authentication → URL Configuration, thêm `https://khoslide.onrender.com/auth/callback` vào Redirect URLs; Site URL đặt `https://khoslide.onrender.com`. Callback phải trùng chính xác. Google/Facebook vẫn cần cấu hình thông tin ứng dụng tại trang developer tương ứng.

## Cách triển khai
Giải nén ZIP, tải toàn bộ nội dung bên trong lên đúng thư mục gốc repo GitHub `thean123464/khoslide`, ghi đè `app.py`, `templates/`, `static/`, `requirements.txt` nếu có. Giữ `Procfile` và `render.yaml` đang dùng. Render sẽ deploy lại. Không tải `shop.db` lên thay database Supabase.

## Lưu ý hành vi
- Ngưỡng miễn phí đếm các đơn đã thanh toán thật, không đếm đơn được duyệt miễn phí. Khi đạt ngưỡng, giá hiển thị/chốt đơn chuyển thành 0 và đơn mới được cấp quyền tải ngay.
- Duyệt miễn phí chỉ tác động đơn đang chờ; đơn đã thanh toán không bị đổi.
- Bình luận được lưu trong PostgreSQL; admin có thể ẩn/hiện.
- Nếu đăng nhập OAuth báo lỗi, kiểm tra `SUPABASE_ANON_KEY`, provider đã bật, URL callback và `APP_BASE_URL`.
