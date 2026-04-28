from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json, os, uuid
from datetime import datetime

app = FastAPI(title="Retro.me")

# Static files aur Templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DB_FILE = "database/store.json"

def load_db():
    if not os.path.exists(DB_FILE):
        default = {
            "products": [],
            "orders": [],
            "settings": {"store_name":"Retro.me","currency":"PKR","admin_password":"admin123"}
        }
        save_db(default)
        return default
    with open(DB_FILE) as f:
        return json.load(f)

def save_db(data):
    os.makedirs("database", exist_ok=True)
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── PUBLIC ROUTES ─────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, category: str = None, search: str = None):
    db = load_db()
    products = db["products"]
    if category:
        products = [p for p in products if p["category"].lower() == category.lower()]
    if search:
        products = [p for p in products if search.lower() in p["name"].lower()]
    categories = list(set(p["category"] for p in db["products"]))
    return templates.TemplateResponse("index.html", {
        "request": request, "products": products,
        "categories": categories, "settings": db["settings"],
        "selected_category": category, "search": search
    })

# --- FIXED CART ROUTES (Missing Tags Added Here) ---
@app.get("/cart", response_class=HTMLResponse)
@app.get("/cart/", response_class=HTMLResponse)
async def cart_page(request: Request):
    db = load_db()
    # Ye line confirm karti hai ke cart.html templates folder se uthayi jaye
    return templates.TemplateResponse("cart.html", {
        "request": request, 
        "settings": db["settings"]
    })

@app.get("/track", response_class=HTMLResponse)
async def track_order_page(request: Request, order_id: str = None, phone: str = None):
    db = load_db()
    order_result = None
    if order_id and phone:
        order_result = next((o for o in db["orders"] if o["id"] == order_id.upper() and o["customer_phone"] == phone), None)
    return templates.TemplateResponse("track_order.html", {
        "request": request, "order": order_result, "settings": db["settings"], "searched": (order_id is not None)
    })

@app.get("/product/{pid}", response_class=HTMLResponse)
async def product_detail(request: Request, pid: str):
    db = load_db()
    product = next((p for p in db["products"] if p["id"] == pid), None)
    if not product:
        raise HTTPException(404, "Product not found")
    return templates.TemplateResponse("product_detail.html", {
        "request": request, "product": product, "settings": db["settings"]
    })

@app.post("/order", response_class=HTMLResponse)
async def place_order(request: Request,
    product_id: str = Form(...), customer_name: str = Form(...),
    customer_phone: str = Form(...), customer_address: str = Form(...),
    quantity: int = Form(...)):
    db = load_db()
    product = next((p for p in db["products"] if p["id"] == product_id), None)
    if not product:
        raise HTTPException(404)
    order = {
        "id": str(uuid.uuid4())[:8].upper(),
        "product_id": product_id, "product_name": product["name"],
        "product_price": product["price"], "quantity": quantity,
        "total_price": product["price"] * quantity,
        "customer_name": customer_name, "customer_phone": customer_phone,
        "customer_address": customer_address, "status": "pending",
        "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    }
    for p in db["products"]:
        if p["id"] == product_id:
            p["stock"] = max(0, p["stock"] - quantity)
    db["orders"].append(order)
    save_db(db)
    return templates.TemplateResponse("order_success.html", {
        "request": request, "order": order, "settings": db["settings"]
    })

# ── ADMIN ROUTES ──────────────────────────────────────────

def is_admin(request: Request):
    return request.cookies.get("admin_ok") == "yes"

@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    db = load_db()
    return templates.TemplateResponse("admin_login.html", {
        "request": request, "settings": db["settings"]
    })

@app.post("/admin/login")
async def admin_login(password: str = Form(...)):
    db = load_db()
    if password == db["settings"]["admin_password"]:
        res = RedirectResponse("/admin/dashboard", 302)
        res.set_cookie("admin_ok", "yes")
        return res
    return RedirectResponse("/admin?error=1", 302)

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_admin(request):
        return RedirectResponse("/admin")
    db = load_db()
    revenue = sum(o["total_price"] for o in db["orders"] if o["status"] != "cancelled")
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, "products": db["products"], "orders": db["orders"],
        "settings": db["settings"], "total_products": len(db["products"]),
        "total_orders": len(db["orders"]), "total_revenue": revenue,
        "pending_orders": len([o for o in db["orders"] if o["status"] == "pending"])
    })

@app.get("/admin/products/add", response_class=HTMLResponse)
async def add_product_page(request: Request):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    return templates.TemplateResponse("admin_product_form.html", {
        "request": request, "product": None, "settings": db["settings"]
    })

@app.post("/admin/products/add")
async def add_product(request: Request,
    name: str = Form(...), price: float = Form(...), category: str = Form(...),
    description: str = Form(...), stock: int = Form(...), image: str = Form(...)):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    db["products"].append({
        "id": str(uuid.uuid4())[:8], "name": name, "price": price,
        "category": category, "description": description,
        "stock": stock, "image": image,
        "created_at": datetime.now().strftime("%d %b %Y")
    })
    save_db(db)
    return RedirectResponse("/admin/dashboard", 302)

@app.get("/admin/products/edit/{pid}", response_class=HTMLResponse)
async def edit_product_page(request: Request, pid: str):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    product = next((p for p in db["products"] if p["id"] == pid), None)
    return templates.TemplateResponse("admin_product_form.html", {
        "request": request, "product": product, "settings": db["settings"]
    })

@app.post("/admin/products/edit/{pid}")
async def edit_product(request: Request, pid: str,
    name: str = Form(...), price: float = Form(...), category: str = Form(...),
    description: str = Form(...), stock: int = Form(...), image: str = Form(...)):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    for p in db["products"]:
        if p["id"] == pid:
            p.update({"name":name,"price":price,"category":category,
                      "description":description,"stock":stock,"image":image})
    save_db(db)
    return RedirectResponse("/admin/dashboard", 302)

@app.post("/admin/products/delete/{pid}")
async def delete_product(request: Request, pid: str):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    db["products"] = [p for p in db["products"] if p["id"] != pid]
    save_db(db)
    return RedirectResponse("/admin/dashboard", 302)

@app.post("/admin/orders/update/{oid}")
async def update_order(request: Request, oid: str, status: str = Form(...)):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    for o in db["orders"]:
        if o["id"] == oid:
            o["status"] = status
    save_db(db)
    return RedirectResponse("/admin/dashboard", 302)

@app.post("/admin/settings/update")
async def update_settings(request: Request,
    store_name: str = Form(...), currency: str = Form(...), admin_password: str = Form(...)):
    if not is_admin(request): return RedirectResponse("/admin")
    db = load_db()
    db["settings"].update({"store_name":store_name,"currency":currency,"admin_password":admin_password})
    save_db(db)
    return RedirectResponse("/admin/dashboard", 302)

@app.get("/admin/logout")
async def logout():
    res = RedirectResponse("/admin")
    res.delete_cookie("admin_ok")
    return res

if __name__ == "__main__":
    import uvicorn
    # Yahan app ko string ki bajaye object pass kiya hai taake reload sahi ho
    uvicorn.run(app, host="0.0.0.0", port=8000)
