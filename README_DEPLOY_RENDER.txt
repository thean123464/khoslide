KHoSlide - Render deployment

1. Create a PRIVATE GitHub repository and upload this folder.
2. On Render: New -> Web Service -> connect the GitHub repo.
3. Build Command: pip install -r requirements.txt
4. Start Command: gunicorn --bind 0.0.0.0:$PORT app:app
5. Use a PAID web service + Persistent Disk for production because this app uses SQLite and private PPTX files.
   Mount path: /var/data
6. Add environment variables:
   KHOSLIDE_PUBLIC=1
   KHOSLIDE_DATA_DIR=/var/data
   KHOSLIDE_SECRET_KEY=<long-random-secret>
   KHOSLIDE_ADMIN_USERNAME=<your-admin-user>
   KHOSLIDE_ADMIN_PASSWORD=<strong-password>
   KHOSLIDE_COOKIE_SECURE=1
   SEPAY_API_KEY=<your-sepay-api-key>
   KHOSLIDE_BANK_CODE=MB
   KHOSLIDE_BANK_ACCOUNT=04919512345555
   KHOSLIDE_BANK_OWNER=NGUYEN LE THE AN
   KHOSLIDE_PAYMENT_PREFIX=KSL
7. After deploy, set SePay webhook URL to:
   https://YOUR-RENDER-DOMAIN/webhooks/sepay
   Authentication: API Key. Header: Authorization: Apikey <same SEPAY_API_KEY>
8. Test with SePay test/simulated transaction first.

IMPORTANT:
- Do not make the GitHub repository public.
- Do not put SEPAY_API_KEY or production admin password in source code.
- Free Render web services have ephemeral filesystems; SQLite/order data and uploaded PPTX files can disappear after restart/redeploy/spindown. Use persistent storage for production.
