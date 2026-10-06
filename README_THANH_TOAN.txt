K H O S L I D E - THANH TOAN THUC
==================================

Phien ban nay da bo thanh toan DEMO va chuyen sang:
- VietQR dong theo tung don hang
- Tai khoan MB
- Noi dung chuyen khoan rieng cho tung don (KSLxxxxxx)
- SePay Webhook tu dong xac nhan giao dich
- Chi mo khoa nut tai file sau khi don hang duoc PAID
- Chong xu ly trung giao dich SePay
- Link download co token rieng cho tung don

THONG TIN NHAN TIEN
--------------------
Ngan hang: MB
So tai khoan: 04919512345555
Chu tai khoan: NGUYEN LE THE AN
Tien to ma thanh toan: KSL

QUAN TRONG
----------
Chi QR va giao dien da dung tai khoan tren. De tu dong mo khoa sau khi khach chuyen tien,
ban phai ket noi tai khoan MB vao SePay va tao Webhook.

CAU HINH SEPAY
--------------
1. Dang nhap my.sepay.vn.
2. Ket noi tai khoan MB cua ban voi SePay.
3. Tao Webhook moi:
   - Su kien: Co tien vao
   - Tai khoan: chon dung tai khoan MB tren
   - Xac thuc: API Key
   - URL: https://TEN-MIEN-CUA-BAN/webhooks/sepay
   - Neu dung tinh nang nhan dien ma thanh toan, dat tien to KSL.
4. Lay API Key va dat bien moi truong:
   SEPAY_API_KEY=API_KEY_CUA_BAN

WINDOWS (CMD)
-------------
set SEPAY_API_KEY=API_KEY_CUA_BAN
python app.py

WINDOWS (PowerShell)
--------------------
$env:SEPAY_API_KEY="API_KEY_CUA_BAN"
python app.py

KHI DEPLOY
----------
Ngoai SEPAY_API_KEY, nen dat:
KHOSLIDE_SECRET_KEY=<chuoi-bi-mat-dai>
KHOSLIDE_ADMIN_USERNAME=<tai-khoan-admin>
KHOSLIDE_ADMIN_PASSWORD=<mat-khau-admin-manh>

LOCAL TEST
----------
127.0.0.1 khong the nhan webhook tu SePay tren Internet. Muon test tu dong o may local,
can dung mot public HTTPS tunnel (vi du Cloudflare Tunnel) hoac deploy website.
SePay co Test Mode de gia lap giao dich ma khong can chuyen tien that.

LUU Y
-----
Khong dat SEPAY_API_KEY vao GitHub/public code.
Khong dung nut "toi da chuyen khoan" de mo khoa. He thong chi mo khoa khi webhook hop le.

BAO MAT ADMIN
- Khi chạy local (127.0.0.1), hệ thống vẫn cho phép đăng nhập bằng tài khoản mặc định để tiện thử nghiệm.
- Khi đưa website lên Internet, bắt buộc đặt KHOSLIDE_PUBLIC=1 và tự đặt 3 biến:
  KHOSLIDE_SECRET_KEY
  KHOSLIDE_ADMIN_USERNAME
  KHOSLIDE_ADMIN_PASSWORD
- Không dùng lại mật khẩu mặc định.
- Hệ thống đã thêm cookie HttpOnly/SameSite, timeout phiên 30 phút, CSRF cho form admin, chống thử mật khẩu liên tục và no-cache cho khu vực /admin.
- Nếu dùng HTTPS ở môi trường public, đặt KHOSLIDE_COOKIE_SECURE=1 (mặc định tự bật khi KHOSLIDE_PUBLIC=1).
