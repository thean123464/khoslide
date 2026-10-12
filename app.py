from flask import Flask, render_template, request, redirect, url_for, abort, session, jsonify
from functools import wraps
from werkzeug.utils import secure_filename
import os, secrets, re, time, sqlite3, json, uuid
from urllib.parse import quote
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

BASE = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# FREE DEPLOYMENT ARCHITECTURE
# Render Free = Flask app only
# Supabase Free = PostgreSQL database + private file storage
# ============================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "khoslide-files")

if not DATABASE_URL or not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    # Keep import friendly for local editing/compile, but refuse to start a
    # deployed app without its persistent free services configured.
    if os.environ.get("KHOSLIDE_PUBLIC", "0") == "1":
        raise RuntimeError(
            "Thiếu DATABASE_URL, SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY. "
            "KhoSlide bản Free dùng Supabase cho database + file storage."
        )

app = Flask(__name__)

# ============================================================
# SECURITY
# ============================================================
SECRET_KEY = os.environ.get("KHOSLIDE_SECRET_KEY")
ADMIN_USERNAME = os.environ.get("KHOSLIDE_ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("KHOSLIDE_ADMIN_PASSWORD")
PUBLIC_MODE = os.environ.get("KHOSLIDE_PUBLIC", "0") == "1"
COOKIE_SECURE = os.environ.get("KHOSLIDE_COOKIE_SECURE", "1" if PUBLIC_MODE else "0") == "1"

if PUBLIC_MODE and (not SECRET_KEY or not ADMIN_USERNAME or not ADMIN_PASSWORD):
    raise RuntimeError(
        "KHOSLIDE_PUBLIC=1 yêu cầu KHOSLIDE_SECRET_KEY, "
        "KHOSLIDE_ADMIN_USERNAME và KHOSLIDE_ADMIN_PASSWORD."
    )

if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)
if not ADMIN_USERNAME:
    ADMIN_USERNAME = "admin"
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = "KhoSlide@2026!"

app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=1800,
)

LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_MAX_FAILURES = 5
_login_failures = {}


def _client_ip():
    return request.remote_addr or "unknown"


def _login_locked(ip):
    now = time.time()
    item = _login_failures.get(ip)
    if not item:
        return False, 0
    first, failures = item
    if now - first >= LOGIN_WINDOW_SECONDS:
        _login_failures.pop(ip, None)
        return False, 0
    return failures >= LOGIN_MAX_FAILURES, max(0, int(LOGIN_WINDOW_SECONDS - (now - first)))


def _record_login_failure(ip):
    now = time.time()
    item = _login_failures.get(ip)
    if not item or now - item[0] >= LOGIN_WINDOW_SECONDS:
        _login_failures[ip] = [now, 1]
    else:
        item[1] += 1


def _clear_login_failures(ip):
    _login_failures.pop(ip, None)


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def check_csrf():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        abort(403, description="Yêu cầu không hợp lệ (CSRF).")


@app.context_processor
def inject_security_helpers():
    return {"csrf_token": csrf_token}


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    if PUBLIC_MODE:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# ============================================================
# PAYMENT
# ============================================================
BANK_CODE = os.environ.get("KHOSLIDE_BANK_CODE", "MB")
BANK_ACCOUNT = os.environ.get("KHOSLIDE_BANK_ACCOUNT", "04919512345555")
BANK_OWNER = os.environ.get("KHOSLIDE_BANK_OWNER", "NGUYEN LE THE AN")
PAYMENT_PREFIX = os.environ.get("KHOSLIDE_PAYMENT_PREFIX", "KSL")
SEPAY_API_KEY = os.environ.get("SEPAY_API_KEY", "")

CATEGORIES = ["Tất cả", "Báo cáo", "Công nghệ", "Giáo dục", "Marketing", "Kêu gọi đầu tư", "Sự kiện", "Kinh doanh"]

# ============================================================
# DATABASE - SUPABASE POSTGRES
# ============================================================

def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL chưa được cấu hình.")
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)


def init_db():
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS products(
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                preview TEXT,
                filename TEXT,
                category TEXT DEFAULT 'Kinh doanh',
                slides INTEGER DEFAULT 10,
                format TEXT DEFAULT 'PPTX',
                badge TEXT DEFAULT ''
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS orders(
                id BIGSERIAL PRIMARY KEY,
                product_id BIGINT NOT NULL REFERENCES products(id),
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                payment_code TEXT UNIQUE,
                download_token TEXT UNIQUE,
                paid_at TIMESTAMPTZ,
                sepay_transaction_id BIGINT UNIQUE,
                payment_reference TEXT,
                paid_amount INTEGER
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS sepay_transactions(
                sepay_id BIGINT PRIMARY KEY,
                gateway TEXT,
                transaction_date TEXT,
                account_number TEXT,
                code TEXT,
                content TEXT,
                transfer_amount INTEGER,
                reference_code TEXT,
                raw_body TEXT
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS free_enabled BOOLEAN NOT NULL DEFAULT FALSE")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS free_after_orders INTEGER")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS free_unlocked_at TIMESTAMPTZ")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS auth_user_id TEXT")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_free BOOLEAN NOT NULL DEFAULT FALSE")
            cur.execute("CREATE TABLE IF NOT EXISTS product_comments( id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE, user_id TEXT NOT NULL, user_name TEXT NOT NULL, user_email TEXT NOT NULL DEFAULT '', body TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), is_hidden BOOLEAN NOT NULL DEFAULT FALSE )")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_product ON product_comments(product_id, created_at DESC)")

            # Seed the existing bundled product catalog once. Orders are not
            # copied because old local pending orders have no value in a new
            # online deployment; payment orders are created fresh.
            cur.execute("SELECT COUNT(*) AS n FROM products")
            if cur.fetchone()["n"] == 0:
                sqlite_path = os.path.join(BASE, "shop.db")
                if os.path.exists(sqlite_path):
                    s = sqlite3.connect(sqlite_path)
                    s.row_factory = sqlite3.Row
                    try:
                        rows = s.execute("SELECT name,description,price,preview,filename,category,slides,format,badge FROM products ORDER BY id").fetchall()
                    finally:
                        s.close()
                    if rows:
                        cur.executemany("""INSERT INTO products
                            (name,description,price,preview,filename,category,slides,format,badge)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            [tuple(r) for r in rows])
        con.commit()
    finally:
        con.close()

# ============================================================
# SUPABASE PRIVATE STORAGE
# ============================================================

def storage_headers(content_type=None):
    h = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def ensure_storage_bucket():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    url = f"{SUPABASE_URL}/storage/v1/bucket"
    try:
        r = requests.post(
            url,
            headers={**storage_headers("application/json"), "Content-Type": "application/json"},
            json={"id": SUPABASE_BUCKET, "name": SUPABASE_BUCKET, "public": False},
            timeout=15,
        )
        
        
            raise RuntimeError(f"Không tạo được Supabase Storage bucket: {r.status_code} {r.text[:300]}")
    except requests.RequestException as e:
        raise RuntimeError(f"Không kết nối được Supabase Storage: {e}")


def storage_upload(file_storage, storage_path):
    content_type = file_storage.mimetype or "application/octet-stream"
    url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(storage_path, safe='/') }"
    file_storage.stream.seek(0)
    r = requests.post(url, headers=storage_headers(content_type), data=file_storage.stream, timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload file thất bại: {r.status_code} {r.text[:500]}")


def storage_delete(storage_path):
    url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(storage_path, safe='/')}"
    try:
        requests.delete(url, headers=storage_headers(), timeout=30)
    except requests.RequestException:
        pass


def storage_signed_url(storage_path, expires=300):
    url = f"{SUPABASE_URL}/storage/v1/object/sign/{quote(SUPABASE_BUCKET)}/{quote(storage_path, safe='/')}"
    r = requests.post(
        url,
        headers={**storage_headers("application/json"), "Content-Type": "application/json"},
        json={"expiresIn": expires},
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Không tạo được link tải: {r.status_code} {r.text[:500]}")
    data = r.json()
    signed = data.get("signedURL") or data.get("signedUrl")
    if not signed:
        raise RuntimeError("Supabase không trả về signed URL.")
    if signed.startswith("http://") or signed.startswith("https://"):
        return signed
    return SUPABASE_URL + "/storage/v1" + signed

# ============================================================
# PUBLIC SHOP
# ============================================================
# ============================================================
# SUPABASE AUTH (OAuth PKCE)
# Set SUPABASE_ANON_KEY and enable Google/Facebook in Supabase Auth.
# Add https://khoslide.onrender.com/auth/callback to Supabase redirect URLs.
# ============================================================
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

def public_product_price(p):
    if p.get("free_enabled") or (p.get("free_after_orders") and p.get("paid_order_count", 0) >= p["free_after_orders"]):
        return 0
    return int(p.get("price") or 0)

def product_with_count(cur, product_id):
    cur.execute("SELECT p.*, (SELECT COUNT(*) FROM orders o WHERE o.product_id=p.id AND o.status='PAID' AND COALESCE(o.is_free,FALSE)=FALSE) AS paid_order_count FROM products p WHERE p.id=%s", (product_id,))
    return cur.fetchone()

def supabase_auth_headers():
    return {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}

@app.route("/auth/login/<provider>")
def auth_login(provider):
    if provider not in ("google", "facebook"):
        abort(404)
    if not SUPABASE_ANON_KEY or not SUPABASE_URL:
        return "Chưa cấu hình SUPABASE_ANON_KEY / SUPABASE_URL.", 503
    verifier = secrets.token_urlsafe(48)
    import hashlib, base64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(24)
    session["oauth_verifier"] = verifier; session["oauth_state"] = state; session["oauth_next"] = request.args.get("next", "")
    callback = (APP_BASE_URL or request.url_root.rstrip("/")) + url_for("auth_callback")
    from urllib.parse import urlencode
    params = urlencode({"provider": provider, "redirect_to": callback, "code_challenge": challenge, "code_challenge_method": "s256", "state": state})
    return redirect(f"{SUPABASE_URL}/auth/v1/authorize?{params}")

@app.route("/auth/callback")
def auth_callback():
    err = request.args.get("error_description") or request.args.get("error")
    code = request.args.get("code", "")
    if err or not code:
        session.pop("oauth_verifier", None); session.pop("oauth_state", None); session.pop("oauth_next", None)
        return redirect(url_for("index"))
    verifier = session.pop("oauth_verifier", None); session.pop("oauth_state", None); next_url = session.pop("oauth_next", "")
    try:
        r = requests.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=pkce", headers=supabase_auth_headers(), json={"auth_code": code, "code_verifier": verifier}, timeout=15)
        r.raise_for_status(); data = r.json(); user = data.get("user") or {}
        if not user.get("id"): raise ValueError("Supabase không trả về user")
        session["user"] = {"id": str(user["id"]), "email": user.get("email", ""), "name": (user.get("user_metadata") or {}).get("full_name") or (user.get("user_metadata") or {}).get("name") or user.get("email", "Khách hàng")}
        session.permanent = True
    except Exception:
        return "Đăng nhập Supabase thất bại. Kiểm tra provider, callback URL và SUPABASE_ANON_KEY.", 502
    return redirect(next_url if next_url.startswith("/") else url_for("index"))

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    check_csrf(); session.pop("user", None); return redirect(url_for("index"))

@app.context_processor
def inject_user_context():
    return {"current_user": session.get("user"), "zalo_url": "https://zalo.me/0355915884"}

@app.route("/product/<int:product_id>/comment", methods=["POST"])
def add_comment(product_id):
    check_csrf(); user = session.get("user")
    if not user: return redirect(url_for("auth_login", provider="google", next=url_for("product", product_id=product_id)))
    body = request.form.get("body", "").strip()
    if not body or len(body) > 2000: abort(400, description="Bình luận phải từ 1 đến 2000 ký tự.")
    con=db()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM products WHERE id=%s",(product_id,))
            if not cur.fetchone(): abort(404)
            cur.execute("INSERT INTO product_comments(product_id,user_id,user_name,user_email,body) VALUES(%s,%s,%s,%s,%s)",(product_id,user["id"],user["name"],user.get("email", ""),body))
        con.commit()
    finally: con.close()
    return redirect(url_for("product",product_id=product_id)+"#comments")

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

@app.route("/admin/product/<int:product_id>/free", methods=["POST"])
@admin_required
def admin_free_toggle(product_id):
    check_csrf(); enabled=request.form.get("free_enabled")=="1"
    con=db()
    try:
        with con.cursor() as cur: cur.execute("UPDATE products SET free_enabled=%s, free_unlocked_at=CASE WHEN %s THEN NOW() ELSE NULL END, updated_at=NOW() WHERE id=%s",(enabled,enabled,product_id))
        con.commit()
    finally: con.close()
    return redirect(url_for("admin"))

@app.route("/admin/product/<int:product_id>/threshold", methods=["POST"])
@admin_required
def admin_free_threshold(product_id):
    check_csrf(); raw=request.form.get("free_after_orders", "").strip()
    try: threshold=int(raw) if raw else None
    except ValueError: abort(400, description="Ngưỡng đơn hàng không hợp lệ.")
    if threshold is not None and threshold < 1: abort(400, description="Ngưỡng phải từ 1 đơn trở lên.")
    con=db()
    try:
        with con.cursor() as cur: cur.execute("UPDATE products SET free_after_orders=%s, updated_at=NOW() WHERE id=%s",(threshold,product_id))
        con.commit()
    finally: con.close()
    return redirect(url_for("admin"))

@app.route("/admin/order/<int:order_id>/free-approve", methods=["POST"])
@admin_required
def admin_free_approve(order_id):
    check_csrf(); con=db()
    try:
        with con.cursor() as cur:
            cur.execute("UPDATE orders SET status='PAID', is_free=TRUE, paid_at=NOW(), paid_amount=0, download_token=COALESCE(download_token,%s) WHERE id=%s AND status<>'PAID' RETURNING id",(secrets.token_urlsafe(32),order_id))
            if not cur.fetchone(): con.rollback(); return "Đơn không tồn tại hoặc đã hoàn tất.", 400
        con.commit()
    finally: con.close()
    return redirect(url_for("admin"))

@app.route("/admin/comment/<int:comment_id>/toggle", methods=["POST"])
@admin_required
def admin_comment_toggle(comment_id):
    check_csrf(); con=db()
    try:
        with con.cursor() as cur: cur.execute("UPDATE product_comments SET is_hidden=NOT is_hidden WHERE id=%s",(comment_id,))
        con.commit()
    finally: con.close()
    return redirect(url_for("admin"))

@app.route("/")
def index():
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT p.*, (SELECT COUNT(*) FROM orders o WHERE o.product_id=p.id AND o.status='PAID' AND COALESCE(o.is_free,FALSE)=FALSE) AS paid_order_count FROM products p ORDER BY p.id DESC")
            products = cur.fetchall()
    finally:
        con.close()
    return render_template("index.html", products=products, categories=CATEGORIES)


@app.route("/templates")
def templates():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "Tất cả")
    sort = request.args.get("sort", "new")
    con = db()
    try:
        with con.cursor() as cur:
            sql = "SELECT * FROM products WHERE 1=1"
            args = []
            if q:
                sql += " AND (name ILIKE %s OR description ILIKE %s OR category ILIKE %s)"
                args += [f"%{q}%", f"%{q}%", f"%{q}%"]
            if category != "Tất cả":
                sql += " AND category=%s"
                args.append(category)
            if sort == "price_asc":
                sql += " ORDER BY price ASC"
            elif sort == "price_desc":
                sql += " ORDER BY price DESC"
            else:
                sql += " ORDER BY id DESC"
            cur.execute(sql, args)
            products = cur.fetchall()
    finally:
        con.close()
    return render_template("templates.html", products=products, categories=CATEGORIES, q=q, category=category, sort=sort)


@app.route("/product/<int:product_id>")
def product(product_id):
    con = db()
    try:
        with con.cursor() as cur:
            p = product_with_count(cur, product_id)
            if p:
                cur.execute("SELECT * FROM products WHERE category=%s AND id!=%s ORDER BY id DESC LIMIT 3", (p["category"], product_id))
                related = cur.fetchall()
                cur.execute("SELECT * FROM product_comments WHERE product_id=%s AND is_hidden=FALSE ORDER BY created_at DESC", (product_id,))
                comments = cur.fetchall()
            else:
                related = []; comments = []
    finally:
        con.close()
    if not p:
        abort(404)
    return render_template("product.html", p=p, related=related, comments=comments, effective_price=public_product_price(p))


@app.route("/buy/<int:product_id>", methods=["GET", "POST"])
def buy(product_id):
    con=db()
    try:
        with con.cursor() as cur:
            p=product_with_count(cur,product_id)
            if not p: abort(404)
            effective_price=public_product_price(p)
            if request.method=="POST":
                check_csrf(); user=session.get("user")
                name=(request.form.get("name","").strip() or (user or {}).get("name", ""))
                email=(request.form.get("email","").strip() or (user or {}).get("email", ""))
                if not name or not email: return render_template("buy.html",p=p,error="Vui lòng nhập đầy đủ thông tin.",effective_price=effective_price)
                status='PAID' if effective_price==0 else 'PENDING'
                token=secrets.token_urlsafe(32); code=f"{PAYMENT_PREFIX}{uuid.uuid4().hex[:10].upper()}"
                cur.execute("INSERT INTO orders(product_id,customer_name,customer_email,status,payment_code,download_token,paid_at,paid_amount,auth_user_id,is_free) VALUES(%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN NOW() ELSE NULL END,%s,%s,%s) RETURNING id",(product_id,name,email,status,code,token,status=='PAID',0 if status=='PAID' else None,(user or {}).get('id'),status=='PAID'))
                oid=cur.fetchone()["id"]; con.commit()
                if status=='PAID': return redirect(url_for("success",order_id=oid,token=token))
                return redirect(url_for("payment",order_id=oid))
    finally: con.close()
    return render_template("buy.html",p=p,effective_price=effective_price)


def qr_url_for_order(o):
    params = (
        f"acc={quote(BANK_ACCOUNT)}"
        f"&bank={quote(BANK_CODE)}"
        f"&amount={int(o['price'])}"
        f"&des={quote(o['payment_code'])}"
        f"&template=compact"
        f"&download=false"
        f"&showinfo=true"
        f"&fullacc=true"
        f"&holder={quote(BANK_OWNER)}"
        f"&store={quote('KhoSlide')}"
    )
    return "https://vietqr.app/img?" + params


@app.route("/payment/<int:order_id>")
def payment(order_id):
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("""SELECT orders.*,products.name,products.price FROM orders
                         JOIN products ON products.id=orders.product_id WHERE orders.id=%s""", (order_id,))
            o = cur.fetchone()
    finally:
        con.close()
    if not o:
        abort(404)
    if o["status"] == "PAID":
        return redirect(url_for("success", order_id=order_id, token=o["download_token"]))
    return render_template("payment.html", o=o, qr_url=qr_url_for_order(o), bank_code=BANK_CODE,
                           bank_account=BANK_ACCOUNT, bank_owner=BANK_OWNER)


@app.route("/payment-status/<int:order_id>")
def payment_status(order_id):
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id,status,download_token FROM orders WHERE id=%s", (order_id,))
            o = cur.fetchone()
    finally:
        con.close()
    if not o:
        return jsonify({"ok": False}), 404
    return jsonify({
        "ok": True,
        "paid": o["status"] == "PAID",
        "success_url": url_for("success", order_id=order_id, token=o["download_token"]) if o["status"] == "PAID" else None
    })


@app.route("/success/<int:order_id>")
def success(order_id):
    token = request.args.get("token", "")
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("""SELECT orders.*,products.name,products.filename FROM orders
                         JOIN products ON products.id=orders.product_id WHERE orders.id=%s""", (order_id,))
            o = cur.fetchone()
    finally:
        con.close()
    if not o:
        abort(404)
    if o["status"] != "PAID":
        return redirect(url_for("payment", order_id=order_id))
    if not secrets.compare_digest(token, o["download_token"] or ""):
        abort(403)
    return render_template("success.html", o=o)


@app.route("/download/<int:order_id>/<token>")
def download(order_id, token):
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("""SELECT orders.*,products.filename FROM orders
                         JOIN products ON products.id=orders.product_id WHERE orders.id=%s""", (order_id,))
            o = cur.fetchone()
    finally:
        con.close()
    if not o or o["status"] != "PAID":
        abort(403)
    if not secrets.compare_digest(token, o["download_token"] or ""):
        abort(403)
    if not o["filename"]:
        return "Mẫu này chưa có file tải xuống.", 404
    try:
        signed = storage_signed_url(o["filename"], expires=300)
    except RuntimeError as e:
        return str(e), 503
    return redirect(signed)

# ============================================================
# SEPAY WEBHOOK
# ============================================================
@app.route("/webhooks/sepay", methods=["POST"])
def sepay_webhook():
    if not SEPAY_API_KEY:
        return jsonify({"success": False, "message": "SEPAY_API_KEY chưa được cấu hình."}), 503
    auth = request.headers.get("Authorization", "")
    expected = "Apikey " + SEPAY_API_KEY
    if not secrets.compare_digest(auth, expected):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "JSON không hợp lệ"}), 400

    sepay_id = data.get("id")
    transfer_type = str(data.get("transferType") or "").lower()
    try:
        amount = int(float(data.get("transferAmount") or 0))
    except (TypeError, ValueError):
        amount = 0
    account_number = str(data.get("accountNumber") or "")
    code = str(data.get("code") or "").strip().upper()
    content = str(data.get("content") or "")
    reference_code = str(data.get("referenceCode") or "")

    if not sepay_id:
        return jsonify({"success": False, "message": "Thiếu id giao dịch"}), 400
    if transfer_type != "in":
        return jsonify({"success": True, "message": "Bỏ qua giao dịch tiền ra"}), 200
    if account_number and account_number != BANK_ACCOUNT:
        return jsonify({"success": True, "message": "Bỏ qua tài khoản khác"}), 200
    if not code:
        m = re.search(rf"\b{re.escape(PAYMENT_PREFIX)}\d{{6,}}\b", content.upper())
        code = m.group(0) if m else ""

    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT 1 FROM sepay_transactions WHERE sepay_id=%s", (int(sepay_id),))
            if cur.fetchone():
                con.rollback()
                return jsonify({"success": True, "message": "Giao dịch đã xử lý"}), 200

            cur.execute("SELECT o.*, p.price AS product_price FROM orders o JOIN products p ON p.id=o.product_id WHERE o.payment_code=%s FOR UPDATE OF o", (code,)) if code else None
            order = cur.fetchone() if code else None

            if not order:
                con.commit()
                return jsonify({"success": True, "message": "Không tìm thấy đơn hàng"}), 200

            if amount < int(order["product_price"]):
                con.rollback()
                return jsonify({"success": False, "message": "Số tiền thanh toán chưa đủ"}), 400

            # Record the transaction only after the amount has passed validation.
            cur.execute("""INSERT INTO sepay_transactions
                (sepay_id,gateway,transaction_date,account_number,code,content,transfer_amount,reference_code,raw_body)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (int(sepay_id), str(data.get("gateway") or ""), str(data.get("transactionDate") or ""),
                 account_number, code, content, amount, reference_code, json.dumps(data, ensure_ascii=False)))

            cur.execute("""UPDATE orders SET status='PAID', paid_at=NOW(),
                         sepay_transaction_id=%s, payment_reference=%s, paid_amount=%s WHERE id=%s""",
                        (int(sepay_id), reference_code, amount, order["id"]))
        con.commit()
        return jsonify({"success": True}), 200
    except psycopg2.IntegrityError:
        con.rollback()
        return jsonify({"success": True, "message": "Giao dịch đã được ghi nhận"}), 200
    finally:
        con.close()

# ============================================================
# ADMIN
# ============================================================


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    error = None
    if request.method == "POST":
        check_csrf()
        ip = _client_ip()
        locked, seconds = _login_locked(ip)
        if locked:
            error = f"Bạn thử đăng nhập quá nhiều lần. Vui lòng chờ khoảng {max(1, seconds // 60 + 1)} phút."
            return render_template("admin_login.html", error=error)
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        valid_user = secrets.compare_digest(username, ADMIN_USERNAME)
        valid_pass = secrets.compare_digest(password, ADMIN_PASSWORD)
        if valid_user and valid_pass:
            _clear_login_failures(ip)
            session.clear()
            session["csrf_token"] = secrets.token_urlsafe(32)
            session["admin_logged_in"] = True
            session["admin_username"] = username
            session.permanent = True
            return redirect(url_for("admin"))
        _record_login_failure(ip)
        error = "Tên đăng nhập hoặc mật khẩu không đúng."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():
    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT p.*, (SELECT COUNT(*) FROM orders o WHERE o.product_id=p.id AND o.status='PAID' AND COALESCE(o.is_free,FALSE)=FALSE) AS paid_order_count FROM products p ORDER BY p.id DESC")
            products = cur.fetchall()
            cur.execute("""SELECT orders.*,products.name FROM orders JOIN products ON products.id=orders.product_id ORDER BY orders.id DESC""")
            orders = cur.fetchall()
            cur.execute("SELECT c.*,p.name AS product_name FROM product_comments c JOIN products p ON p.id=c.product_id ORDER BY c.created_at DESC LIMIT 100")
            comments = cur.fetchall()
    finally:
        con.close()
    return render_template("admin.html", products=products, orders=orders, comments=comments, categories=CATEGORIES[1:])


@app.route("/admin/add", methods=["POST"])
@admin_required
def admin_add():
    check_csrf()
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    try:
        price = int(request.form.get("price", "0"))
        slides = int(request.form.get("slides", "10"))
    except ValueError:
        return "Giá hoặc số slide không hợp lệ.", 400
    category = request.form.get("category", "Kinh doanh")
    badge = request.form.get("badge", "")
    free_enabled = request.form.get("free_enabled") == "1"
    raw_threshold = request.form.get("free_after_orders", "").strip()
    try: free_after_orders = int(raw_threshold) if raw_threshold else None
    except ValueError: return "Ngưỡng đơn hàng không hợp lệ.", 400
    if free_after_orders is not None and free_after_orders < 1: return "Ngưỡng phải từ 1 đơn trở lên.", 400
    file = request.files.get("file")
    if not name or price < 0:
        return "Thiếu tên sản phẩm hoặc giá không hợp lệ.", 400

    storage_path = ""
    if file and file.filename:
        safe = secure_filename(file.filename)
        if not safe:
            return "Tên file không hợp lệ.", 400
        ext = os.path.splitext(safe)[1].lower()
        if ext not in {".ppt", ".pptx", ".pdf", ".zip"}:
            return "Chỉ nhận PPT, PPTX, PDF hoặc ZIP.", 400
        storage_path = f"products/{uuid.uuid4().hex}_{safe}"
        try:
            storage_upload(file, storage_path)
        except RuntimeError as e:
            return str(e), 502

    con = db()
    try:
        with con.cursor() as cur:
            cur.execute("""INSERT INTO products(name,description,price,preview,filename,category,slides,format,badge,free_enabled,free_after_orders,free_unlocked_at)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN NOW() ELSE NULL END) RETURNING id""",
                        (name, description, price, "custom", storage_path, category, slides, "PPTX", badge, free_enabled, free_after_orders, free_enabled))
        con.commit()
    except Exception:
        con.rollback()
        if storage_path:
            storage_delete(storage_path)
        raise
    finally:
        con.close()
    return redirect(url_for("admin"))

# ============================================================
# STARTUP
# ============================================================
if DATABASE_URL and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    init_db()
    ensure_storage_bucket()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=not PUBLIC_MODE)

