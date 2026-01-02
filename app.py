from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime, date
import secrets
import shutil
from flask import send_file
import os
import atexit
import shutil
import time

import sys
import os

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(".")

app = Flask(
    __name__,
    template_folder=os.path.join(base_path, "templates"),
    static_folder=os.path.join(base_path, "static")
)
app.secret_key = secrets.token_hex(16)  # Secure session key
import sys
import os

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB = os.path.join(BASE_DIR, "pharmacy.db")

def auto_backup():
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"pharmacy_auto_backup_{ts}.db"
        shutil.copy(DB, backup_name)
        print(f"[AUTO-BACKUP] Saved: {backup_name}")

        # --- keep only last 5 backups ---
        backups = sorted(
            [f for f in os.listdir(".") if f.startswith("pharmacy_auto_backup_") and f.endswith(".db")]
        )

        while len(backups) > 5:
            old = backups.pop(0)
            os.remove(old)
            print(f"[AUTO-BACKUP] Deleted old backup: {old}")

    except Exception as e:
        print("[AUTO-BACKUP FAILED]", e)

atexit.register(auto_backup)

SHOP = {
    "name": "NEW A-ONE MEDICAL & GENERAL STORE",
    "address": "SADAK FALIYA, KACHERI ROAD, KALOL, PANCHMAHAL, GUJARAT-389330",
    "phone": "8238848282"
}

# ---------------- DB ----------------
def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        qty INTEGER,
        username TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS drug_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        drug_name TEXT,
        batch TEXT,
        expiry TEXT,
        mrp REAL,
        stock INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        qty INTEGER,
        username TEXT
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        subtotal REAL,
        discount REAL,
        total REAL,
        invoice_no TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        invoice_id INTEGER,
        drug_name TEXT,
        batch TEXT,
        expiry TEXT,
        qty INTEGER,
        mrp REAL,
        total REAL
    )
    """)

    con.commit()
    con.close()

def create_admin():
    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("AONE123"), "admin")
        )
        con.commit()
    con.close()

# ---------------- EXPIRY ----------------
def expiry_status(exp):
    try:
        if len(exp) == 7:
            exp_date = datetime.strptime(exp + "-01", "%Y-%m-%d").date()
        else:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
    except:
        return "UNKNOWN"

    days = (exp_date - date.today()).days
    if days < 0:
        return "EXPIRED"
    elif days <= 90:
        return "NEAR"
    return "OK"

# ---------------- LOGIN REQUIRED ----------------
def login_required(f):
    def wrap(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# ---------------- ROUTES ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["user"]
        password = request.form["pass"]

        con = get_db()
        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()
        con.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    con = get_db()
    q = request.args.get("q", "")

    show_expired = request.args.get("show_expired") == "1"

    products_query = "SELECT * FROM products"
    params = []
    conditions = []

    if q:
        conditions.append("drug_name LIKE ?")
        params.append(f"%{q}%")

    if not show_expired:
        conditions.append("stock > 0")
        conditions.append("expiry >= date('now')")

    if conditions:
        products_query += " WHERE " + " AND ".join(conditions)

    products = con.execute(products_query, tuple(params)).fetchall()

    cart = con.execute("""
        SELECT c.id as cart_id, p.id as product_id, p.*, c.qty
        FROM cart c
        JOIN products p ON p.id = c.product_id
        WHERE c.username = ?
    """, (session["user"],)).fetchall()


    subtotal = sum(i["qty"] * i["mrp"] for i in cart)
    con.close()

    return render_template(
        "index.html",
        products=products,
        cart=cart,
        subtotal=subtotal,
        shop=SHOP,
        expiry_status=expiry_status,
        q=q
    )

@app.route("/expiry_dashboard")
@login_required
def expiry_dashboard():
    con = get_db()

    expired = con.execute("""
        SELECT * FROM products
        WHERE expiry < date('now')
    """).fetchall()

    near = con.execute("""
        SELECT * FROM products
        WHERE expiry >= date('now')
          AND expiry <= date('now','+60 days')
    """).fetchall()

    con.close()

    return render_template(
        "expiry_dashboard.html",
        expired=expired,
        near=near
    )

@app.route("/adjust_stock/<int:id>", methods=["GET", "POST"])
@login_required
def adjust_stock(id):
    con = get_db()
    cur = con.cursor()

    if request.method == "POST":
        new_stock = int(request.form["stock"])
        cur.execute(
            "UPDATE products SET stock=? WHERE id=?",
            (new_stock, id)
        )
        con.commit()
        con.close()
        return redirect(url_for("index"))

    product = cur.execute(
        "SELECT * FROM products WHERE id=?",
        (id,)
    ).fetchone()

    con.close()
    return render_template("adjust_stock.html", p=product)

@app.route("/add_to_cart", methods=["POST"])
@login_required
def add_to_cart():
    pid = int(request.form["product_id"])
    qty = int(request.form["qty"])
    user = session["user"]

    con = get_db()
    cur = con.cursor()

    stock = cur.execute(
        "SELECT stock FROM products WHERE id=?",
        (pid,)
    ).fetchone()["stock"]

    if qty > stock or qty <= 0:
        con.close()
        return redirect(url_for("index"))

    cur.execute("""
        UPDATE cart
        SET qty = qty + ?
        WHERE product_id = ? AND username = ?
    """, (qty, pid, user))

    if cur.rowcount == 0:
        cur.execute("""
            INSERT INTO cart (product_id, qty, username)
            VALUES (?, ?, ?)
        """, (pid, qty, user))

    con.commit()
    con.close()
    return redirect(url_for("index"))

@app.route("/remove_from_cart/<int:pid>")
@login_required
def remove_from_cart(pid):
    con = get_db()
    con.execute(
        "DELETE FROM cart WHERE product_id=? AND username=?",
        (pid, session["user"])
    )
    con.commit()
    con.close()
    return redirect(url_for("index"))

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    discount_pct = float(request.form.get("discount", 0))
    customer_name = request.form.get("customer_name", "").strip().title()
    con = get_db()
    cur = con.cursor()

    # Get last invoice number
    last = cur.execute(
        "SELECT invoice_no FROM invoices ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if last and last["invoice_no"]:
        last_no = int(last["invoice_no"].split("-")[1])
        new_no = last_no + 1
    else:
        new_no = 1

    invoice_no = f"AONE-{new_no:06d}"

    cart = cur.execute("""
    SELECT p.*, c.qty
    FROM cart c
    JOIN products p ON p.id = c.product_id
    WHERE c.username = ?
""", (session["user"],)).fetchall()

    subtotal = sum(i["qty"] * i["mrp"] for i in cart)
    discount_amt = round(subtotal * discount_pct / 100, 2)
    total = round(subtotal - discount_amt, 2)

    invoice_date = datetime.now().strftime("%d-%m-%Y %I:%M %p")

    cur.execute("""
        INSERT INTO invoices (invoice_no, date, subtotal, discount, total, customer_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (invoice_no, invoice_date, subtotal, discount_amt, total, customer_name))


    invoice_id = cur.lastrowid

    for i in cart:
        cur.execute("""
            INSERT INTO invoice_items
            (invoice_id, drug_name, batch, expiry, qty, mrp, total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            i["drug_name"],
            i["batch"],
            i["expiry"],
            i["qty"],
            i["mrp"],
            i["qty"] * i["mrp"]
        ))

        # Reduce stock
        cur.execute(
            "UPDATE products SET stock = stock - ? WHERE id = ?",
            (i["qty"], i["id"])
        )

    cur.execute(
    "DELETE FROM cart WHERE username=?",
    (session["user"],)
    )
    con.commit()
    con.close()

    return redirect(url_for("invoice", id=invoice_id))

@app.route("/backup")
@login_required
def backup():
    backup_file = "pharmacy_backup.db"
    shutil.copy(DB, backup_file)
    return send_file(
        backup_file,
        as_attachment=True,
        download_name="pharmacy_backup.db"
    )

@app.route("/restore", methods=["POST"])
@login_required
def restore():
    file = request.files["backup"]
    if file and file.filename.endswith(".db"):
        file.save(DB)
    return redirect(url_for("index"))

@app.route("/invoice/<int:id>")
def invoice(id):
    con = get_db()
    items = con.execute(
        "SELECT rowid, * FROM invoice_items WHERE invoice_id=?", (id,)
    ).fetchall()
    inv = con.execute(
        "SELECT * FROM invoices WHERE id=?", (id,)
    ).fetchone()
    con.close()

    if not inv:
        return "Invoice not found", 404

    # Render lightweight digital receipt

    return render_template(
    "invoice.html",
    items=items,
    inv=inv,
    shop=SHOP
)

@app.route("/invoices")
@login_required
def invoices():
    con = get_db()
    invs = con.execute("SELECT * FROM invoices ORDER BY id DESC").fetchall()
    con.close()
    return render_template("invoices.html", invs=invs, shop=SHOP)

@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    con = get_db()
    drugs = con.execute("SELECT name FROM drug_master ORDER BY name").fetchall()

    if request.method == "POST":
        con.execute("""
            INSERT INTO products (drug_name, batch, expiry, mrp, stock, low_stock_limit)
            VALUES (?,?,?,?,?,?)
        """, (
    request.form["drug"],
    request.form["batch"],
    request.form["expiry"],
    float(request.form["mrp"]),
    int(request.form["stock"]),
    int(request.form["low_stock_limit"])
))
        con.commit()
        con.close()
        return redirect(url_for("index"))

    con.close()
    return render_template("add_product.html", drugs=drugs)

@app.route("/update_invoice/<int:id>", methods=["POST"])
@login_required
def update_invoice(id):
    customer_name = request.form.get("customer_name", "").strip().title()
    discount = float(request.form.get("discount", 0))

    con = get_db()
    cur = con.cursor()

    # Recalculate totals
    items = cur.execute(
        "SELECT qty, mrp FROM invoice_items WHERE invoice_id=?", (id,)
    ).fetchall()

    subtotal = sum(i["qty"] * i["mrp"] for i in items)
    discount_amt = round(subtotal * discount / 100, 2)
    total = round(subtotal - discount_amt, 2)

    cur.execute("""
        UPDATE invoices
        SET customer_name=?, discount=?, total=?
        WHERE id=?
    """, (customer_name, discount_amt, total, id))

    con.commit()
    con.close()

    return redirect(url_for("invoice", id=id))

@app.route("/update_item/<int:item_id>/<int:invoice_id>", methods=["POST"])
@login_required
def update_item(item_id, invoice_id):
    qty = int(request.form["qty"])

    con = get_db()
    cur = con.cursor()

    if qty <= 0:
        cur.execute("DELETE FROM invoice_items WHERE rowid=?", (item_id,))
    else:
        cur.execute("""
            UPDATE invoice_items
            SET qty=?, total=qty*mrp
            WHERE rowid=?
        """, (qty, item_id))

    # Recalculate invoice totals
    items = cur.execute(
        "SELECT qty, mrp FROM invoice_items WHERE invoice_id=?", (invoice_id,)
    ).fetchall()

    subtotal = sum(i["qty"] * i["mrp"] for i in items)
    inv = cur.execute(
        "SELECT discount FROM invoices WHERE id=?", (invoice_id,)
    ).fetchone()

    total = round(subtotal - inv["discount"], 2)

    cur.execute("""
        UPDATE invoices
        SET subtotal=?, total=?
        WHERE id=?
    """, (subtotal, total, invoice_id))

    con.commit()
    con.close()

    return redirect(url_for("invoice", id=invoice_id))

@app.route("/drug_master", methods=["GET", "POST"])
@login_required
def drug_master():
    con = get_db()
    if request.method == "POST":
        name = request.form["name"].strip().title()
        if name:
            con.execute("INSERT OR IGNORE INTO drug_master (name) VALUES (?)", (name,))
            con.commit()
    drugs = con.execute("SELECT * FROM drug_master ORDER BY name").fetchall()
    con.close()
    return render_template("drug_master.html", drugs=drugs)

# ---------------- START ----------------
import os

if __name__ == "__main__":
    init_db()
    create_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
