#!/usr/bin/env python3
"""Sistema Kiosco Digital v2.0 Professional - Sin dependencias externas"""
import sqlite3, json, os, webbrowser, threading, csv, io
from datetime import datetime, date, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kiosco.db")
PORT = 8080

# ═══════════════════════════════════════════════════════════
# BASE DE DATOS
# ═══════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT);
        INSERT OR IGNORE INTO config VALUES ('nombre_negocio','Kiosco Digital');
        INSERT OR IGNORE INTO config VALUES ('direccion','');
        INSERT OR IGNORE INTO config VALUES ('telefono','');

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            precio_costo REAL DEFAULT 0,
            precio_venta REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 5,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT (date('now','localtime')),
            hora TEXT DEFAULT (time('now','localtime')),
            total REAL NOT NULL,
            descuento REAL DEFAULT 0,
            metodo_pago TEXT DEFAULT 'efectivo',
            observaciones TEXT,
            cajero TEXT DEFAULT 'Admin',
            anulada INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ventas_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL,
            producto_id INTEGER,
            producto_nombre TEXT NOT NULL,
            codigo TEXT,
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY(venta_id) REFERENCES ventas(id)
        );

        CREATE TABLE IF NOT EXISTS movimientos_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            producto_nombre TEXT,
            tipo TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            stock_anterior INTEGER,
            stock_nuevo INTEGER,
            motivo TEXT,
            fecha TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            saldo REAL DEFAULT 0,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS cuenta_corriente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            monto REAL NOT NULL,
            descripcion TEXT,
            fecha TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );

        CREATE TABLE IF NOT EXISTS caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT (date('now','localtime')),
            tipo TEXT NOT NULL,
            monto_inicial REAL DEFAULT 0,
            total_efectivo REAL DEFAULT 0,
            total_mp REAL DEFAULT 0,
            total_ventas REAL DEFAULT 0,
            cantidad_ventas INTEGER DEFAULT 0,
            observaciones TEXT,
            hora TEXT DEFAULT (time('now','localtime'))
        );
    """)

    c.execute("SELECT COUNT(*) FROM productos")
    if c.fetchone()[0] == 0:
        prods = [
            ("7790040153993","Coca Cola 500ml","Bebidas",350,650,24,6),
            ("7790040150114","Coca Cola 1.5L","Bebidas",550,950,12,4),
            ("7798000008537","Agua Villavicencio 500ml","Bebidas",200,400,18,6),
            ("7790070010013","Sprite 500ml","Bebidas",350,650,15,6),
            ("7790040018234","Fanta Naranja 500ml","Bebidas",350,650,10,4),
            ("7794000012208","Papas Fritas Lays","Snacks",280,550,20,8),
            ("7792222052101","Oreo Original","Snacks",320,620,8,4),
            ("7793190003802","Alfajor Jorgito","Golosinas",180,380,30,10),
            ("7790580007706","Chicle Beldent","Golosinas",150,300,15,6),
            ("7791813010215","Cigarrillos Marlboro","Tabaco",1800,2800,8,3),
            ("7793540000044","Yerba Taragui 500g","Almacen",650,1100,6,2),
            ("7791813000032","Cigarrillos Camel","Tabaco",1800,2800,5,3),
            ("7792361000016","Leche La Serenisima 1L","Lacteos",450,750,10,4),
            ("7790580021408","Chiclets Adams","Golosinas",100,200,25,8),
            ("7790580007119","Mentitas","Golosinas",120,250,20,6),
        ]
        c.executemany("INSERT INTO productos (codigo,nombre,categoria,precio_costo,precio_venta,stock,stock_minimo) VALUES (?,?,?,?,?,?,?)", prods)
        today = date.today().isoformat()
        demo = [
            (1300,"efectivo",[(1,2,650),(8,1,380)]),
            (950,"mp",[(2,1,950)]),
            (1650,"efectivo",[(6,3,550)]),
            (400,"mp",[(3,1,400)]),
            (2800,"efectivo",[(10,1,2800)]),
            (1240,"mp",[(7,2,620)]),
            (650,"efectivo",[(4,1,650)]),
            (760,"efectivo",[(8,2,380)]),
        ]
        for total, metodo, items in demo:
            c.execute("INSERT INTO ventas (fecha,total,metodo_pago) VALUES (?,?,?)", (today,total,metodo))
            vid = c.lastrowid
            for pid, cant, precio in items:
                row = c.execute("SELECT nombre,codigo FROM productos WHERE id=?", (pid,)).fetchone()
                if row:
                    c.execute("INSERT INTO ventas_items (venta_id,producto_id,producto_nombre,codigo,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?,?,?)",
                              (vid,pid,row[0],row[1],cant,precio,precio*cant))
                    c.execute("UPDATE productos SET stock=stock-? WHERE id=?", (cant,pid))
    conn.commit()
    conn.close()
    print(f"Base de datos: {DB_PATH}")

# ═══════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════
def db_dashboard():
    conn = get_db()
    today = date.today().isoformat()
    hoy = dict(conn.execute("""
        SELECT COUNT(*) transacciones, COALESCE(SUM(total),0) total_hoy,
        COALESCE(SUM(CASE WHEN metodo_pago='mp' THEN total ELSE 0 END),0) mp_hoy,
        COALESCE(SUM(CASE WHEN metodo_pago='efectivo' THEN total ELSE 0 END),0) efectivo_hoy
        FROM ventas WHERE fecha=? AND anulada=0
    """, (today,)).fetchone())
    semana = [dict(r) for r in conn.execute("""
        SELECT fecha, COALESCE(SUM(total),0) total, COUNT(*) ventas
        FROM ventas WHERE fecha >= date('now','-6 days','localtime') AND anulada=0
        GROUP BY fecha ORDER BY fecha
    """).fetchall()]
    top = [dict(r) for r in conn.execute("""
        SELECT vi.producto_nombre, SUM(vi.cantidad) unidades, SUM(vi.subtotal) monto
        FROM ventas_items vi JOIN ventas v ON v.id=vi.venta_id
        WHERE v.fecha=? AND v.anulada=0
        GROUP BY vi.producto_nombre ORDER BY monto DESC LIMIT 5
    """, (today,)).fetchall()]
    bajo_stock = [dict(r) for r in conn.execute("""
        SELECT nombre, stock, stock_minimo, categoria FROM productos
        WHERE stock <= stock_minimo AND activo=1 ORDER BY stock ASC
    """).fetchall()]
    ganancia = conn.execute("""
        SELECT COALESCE(SUM(vi.subtotal-(p.precio_costo*vi.cantidad)),0) g
        FROM ventas_items vi JOIN productos p ON p.id=vi.producto_id
        JOIN ventas v ON v.id=vi.venta_id WHERE v.fecha=? AND v.anulada=0
    """, (today,)).fetchone()["g"]
    total_prods = conn.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0]
    conn.close()
    return {"hoy":hoy,"semana":semana,"top_productos":top,"bajo_stock":bajo_stock,
            "ganancia_hoy":ganancia,"total_productos":total_prods,"fecha":today}

def db_productos(q="", cat=""):
    conn = get_db()
    sql = "SELECT * FROM productos WHERE activo=1"
    params = []
    if q:
        sql += " AND (lower(nombre) LIKE ? OR codigo LIKE ?)"
        params += [f"%{q.lower()}%", f"%{q}%"]
    if cat:
        sql += " AND categoria=?"
        params.append(cat)
    sql += " ORDER BY nombre"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

def db_producto_codigo(codigo):
    conn = get_db()
    row = conn.execute("SELECT * FROM productos WHERE codigo=? AND activo=1", (codigo,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_crear_producto(d):
    conn = get_db()
    try:
        conn.execute("INSERT INTO productos (codigo,nombre,categoria,precio_costo,precio_venta,stock,stock_minimo) VALUES (:codigo,:nombre,:categoria,:precio_costo,:precio_venta,:stock,:stock_minimo)", d)
        conn.commit()
        return {"ok":True,"msg":"Producto creado"}
    except sqlite3.IntegrityError:
        return {"ok":False,"msg":"El codigo ya existe"}
    finally:
        conn.close()

def db_editar_producto(pid, d):
    conn = get_db()
    conn.execute("""UPDATE productos SET nombre=:nombre,categoria=:categoria,
        precio_costo=:precio_costo,precio_venta=:precio_venta,
        stock_minimo=:stock_minimo,updated_at=datetime('now','localtime') WHERE id=:id""",
        {**d,"id":pid})
    conn.commit()
    conn.close()
    return {"ok":True,"msg":"Producto actualizado"}

def db_eliminar_producto(pid):
    conn = get_db()
    conn.execute("UPDATE productos SET activo=0 WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return {"ok":True,"msg":"Producto eliminado"}

def db_venta(data):
    conn = get_db()
    try:
        items = data.get("items",[])
        if not items:
            return {"ok":False,"msg":"El carrito esta vacio"}
        total = 0
        detalles = []
        for it in items:
            p = conn.execute("SELECT * FROM productos WHERE id=? AND activo=1",(it["producto_id"],)).fetchone()
            if not p:
                return {"ok":False,"msg":f"Producto no encontrado"}
            if p["stock"] < it["cantidad"]:
                return {"ok":False,"msg":f"Stock insuficiente: {p['nombre']} (disponible: {p['stock']})"}
            sub = p["precio_venta"] * it["cantidad"]
            total += sub
            detalles.append({"p":dict(p),"cant":it["cantidad"],"precio":p["precio_venta"],"sub":sub})
        desc = float(data.get("descuento",0))
        total_final = total - desc
        metodo = data.get("metodo_pago","efectivo")
        conn.execute("INSERT INTO ventas (total,descuento,metodo_pago,observaciones) VALUES (?,?,?,?)",
                     (total_final,desc,metodo,data.get("observaciones","")))
        vid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for d2 in detalles:
            p = d2["p"]
            conn.execute("INSERT INTO ventas_items (venta_id,producto_id,producto_nombre,codigo,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?,?,?)",
                         (vid,p["id"],p["nombre"],p["codigo"],d2["cant"],d2["precio"],d2["sub"]))
            s_ant = p["stock"]; s_new = s_ant - d2["cant"]
            conn.execute("UPDATE productos SET stock=? WHERE id=?", (s_new,p["id"]))
            conn.execute("INSERT INTO movimientos_stock (producto_id,producto_nombre,tipo,cantidad,stock_anterior,stock_nuevo,motivo) VALUES (?,?,'salida',?,?,?,'Venta #'||?)",
                         (p["id"],p["nombre"],d2["cant"],s_ant,s_new,vid))
        conn.commit()
        return {"ok":True,"venta_id":vid,"total":total_final,"msg":f"Venta #{vid} registrada - ${total_final:,.0f}"}
    except Exception as e:
        conn.rollback()
        return {"ok":False,"msg":str(e)}
    finally:
        conn.close()

def db_anular_venta(vid):
    conn = get_db()
    v = conn.execute("SELECT * FROM ventas WHERE id=? AND anulada=0",(vid,)).fetchone()
    if not v:
        conn.close()
        return {"ok":False,"msg":"Venta no encontrada o ya anulada"}
    for it in conn.execute("SELECT * FROM ventas_items WHERE venta_id=?",(vid,)).fetchall():
        conn.execute("UPDATE productos SET stock=stock+? WHERE id=?", (it["cantidad"],it["producto_id"]))
    conn.execute("UPDATE ventas SET anulada=1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    return {"ok":True,"msg":f"Venta #{vid} anulada"}

def db_ventas(desde="", hasta="", metodo="", limit=100):
    conn = get_db()
    sql = """SELECT v.*,
        (SELECT GROUP_CONCAT(vi.producto_nombre||' x'||vi.cantidad,', ') FROM ventas_items vi WHERE vi.venta_id=v.id) items
        FROM ventas v WHERE 1=1"""
    params = []
    if desde: sql += " AND v.fecha>=?"; params.append(desde)
    if hasta: sql += " AND v.fecha<=?"; params.append(hasta)
    if metodo: sql += " AND v.metodo_pago=?"; params.append(metodo)
    sql += " ORDER BY v.id DESC LIMIT ?"; params.append(limit)
    rows = [dict(r) for r in conn.execute(sql,params).fetchall()]
    conn.close()
    return rows

def db_stock_entrada(pid, cant, motivo="Compra proveedor"):
    conn = get_db()
    p = conn.execute("SELECT * FROM productos WHERE id=?",(pid,)).fetchone()
    if not p:
        conn.close()
        return {"ok":False,"msg":"Producto no encontrado"}
    s_ant = p["stock"]; s_new = s_ant + cant
    conn.execute("UPDATE productos SET stock=? WHERE id=?", (s_new,pid))
    conn.execute("INSERT INTO movimientos_stock (producto_id,producto_nombre,tipo,cantidad,stock_anterior,stock_nuevo,motivo) VALUES (?,?,'entrada',?,?,?,?)",
                 (pid,p["nombre"],cant,s_ant,s_new,motivo))
    conn.commit()
    conn.close()
    return {"ok":True,"nuevo_stock":s_new,"msg":f"Ingresadas {cant} unidades. Stock: {s_new}"}

def db_reportes(periodo="mes"):
    conn = get_db()
    today = date.today()
    if periodo=="hoy": fd=fh=today.isoformat()
    elif periodo=="semana": fd=(today-timedelta(days=7)).isoformat(); fh=today.isoformat()
    elif periodo=="mes": fd=today.replace(day=1).isoformat(); fh=today.isoformat()
    else: fd=(today-timedelta(days=30)).isoformat(); fh=today.isoformat()

    resumen = dict(conn.execute("""
        SELECT COUNT(*) transacciones, COALESCE(SUM(total),0) total_ventas,
        COALESCE(SUM(CASE WHEN metodo_pago='efectivo' THEN total ELSE 0 END),0) efectivo,
        COALESCE(SUM(CASE WHEN metodo_pago='mp' THEN total ELSE 0 END),0) mp,
        COUNT(DISTINCT fecha) dias_activos
        FROM ventas WHERE fecha BETWEEN ? AND ? AND anulada=0
    """, (fd,fh)).fetchone())
    por_dia = [dict(r) for r in conn.execute("""
        SELECT fecha, SUM(total) total, COUNT(*) ventas
        FROM ventas WHERE fecha BETWEEN ? AND ? AND anulada=0 GROUP BY fecha ORDER BY fecha
    """, (fd,fh)).fetchall()]
    por_producto = [dict(r) for r in conn.execute("""
        SELECT vi.producto_nombre, SUM(vi.cantidad) unidades, SUM(vi.subtotal) monto,
        SUM(vi.subtotal-(p.precio_costo*vi.cantidad)) ganancia
        FROM ventas_items vi JOIN ventas v ON v.id=vi.venta_id
        LEFT JOIN productos p ON p.id=vi.producto_id
        WHERE v.fecha BETWEEN ? AND ? AND v.anulada=0
        GROUP BY vi.producto_nombre ORDER BY monto DESC LIMIT 15
    """, (fd,fh)).fetchall()]
    ganancia = conn.execute("""
        SELECT COALESCE(SUM(vi.subtotal-(p.precio_costo*vi.cantidad)),0) g
        FROM ventas_items vi JOIN productos p ON p.id=vi.producto_id
        JOIN ventas v ON v.id=vi.venta_id WHERE v.fecha BETWEEN ? AND ? AND v.anulada=0
    """, (fd,fh)).fetchone()["g"]
    conn.close()
    return {"resumen":resumen,"por_dia":por_dia,"por_producto":por_producto,
            "ganancia_total":ganancia,"fd":fd,"fh":fh}

def db_rentabilidad_cat(fd, fh):
    conn = get_db()
    rows = [dict(r) for r in conn.execute("""
        SELECT p.categoria,
               SUM(vi.subtotal) monto,
               SUM(vi.subtotal - p.precio_costo * vi.cantidad) ganancia,
               SUM(vi.cantidad) unidades
        FROM ventas_items vi
        JOIN productos p ON p.id = vi.producto_id
        JOIN ventas v ON v.id = vi.venta_id
        WHERE v.fecha BETWEEN ? AND ? AND v.anulada=0
        GROUP BY p.categoria ORDER BY monto DESC
    """, (fd, fh)).fetchall()]
    conn.close()
    return rows

def db_config():
    conn = get_db()
    rows = conn.execute("SELECT * FROM config").fetchall()
    conn.close()
    return {r["clave"]:r["valor"] for r in rows}

def db_set_config(data):
    conn = get_db()
    for k,v in data.items():
        conn.execute("INSERT OR REPLACE INTO config VALUES (?,?)",(k,v))
    conn.commit()
    conn.close()
    return {"ok":True}

def db_caja():
    conn = get_db()
    today = date.today().isoformat()
    last = conn.execute("SELECT * FROM caja WHERE fecha=? ORDER BY id DESC LIMIT 1",(today,)).fetchone()
    ap = conn.execute("SELECT * FROM caja WHERE fecha=? AND tipo='apertura' ORDER BY id DESC LIMIT 1",(today,)).fetchone()
    ci = conn.execute("SELECT * FROM caja WHERE fecha=? AND tipo='cierre' ORDER BY id DESC LIMIT 1",(today,)).fetchone()
    conn.close()
    abierta = last is not None and last["tipo"] == "apertura"
    return {"apertura":dict(ap) if ap else None,"cierre":dict(ci) if ci else None,"abierta":abierta}

def db_abrir_caja(monto, obs=""):
    conn = get_db()
    conn.execute("INSERT INTO caja (tipo,monto_inicial,observaciones) VALUES ('apertura',?,?)",(monto,obs))
    conn.commit()
    conn.close()
    return {"ok":True,"msg":"Caja abierta"}

def db_cerrar_caja(obs=""):
    conn = get_db()
    today = date.today().isoformat()
    t = dict(conn.execute("""
        SELECT COALESCE(SUM(total),0) tv,
        COALESCE(SUM(CASE WHEN metodo_pago='efectivo' THEN total ELSE 0 END),0) ef,
        COALESCE(SUM(CASE WHEN metodo_pago='mp' THEN total ELSE 0 END),0) mp,
        COUNT(*) cant FROM ventas WHERE fecha=? AND anulada=0
    """, (today,)).fetchone())
    conn.execute("INSERT INTO caja (tipo,total_efectivo,total_mp,total_ventas,cantidad_ventas,observaciones) VALUES ('cierre',?,?,?,?,?)",
                 (t["ef"],t["mp"],t["tv"],t["cant"],obs))
    conn.commit()
    conn.close()
    return {"ok":True,"totales":t}

def db_clientes(q=""):
    conn = get_db()
    sql = "SELECT * FROM clientes WHERE activo=1"
    params = []
    if q:
        sql += " AND lower(nombre) LIKE ?"
        params.append(f"%{q.lower()}%")
    sql += " ORDER BY nombre"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

def db_crear_cliente(data):
    conn = get_db()
    conn.execute("INSERT INTO clientes (nombre, telefono) VALUES (:nombre, :telefono)", data)
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "Cliente creado"}

def db_fiado(cliente_id, monto, desc="Fiado"):
    conn = get_db()
    cl = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
    if not cl:
        conn.close()
        return {"ok": False, "msg": "Cliente no encontrado"}
    conn.execute("UPDATE clientes SET saldo=saldo+? WHERE id=?", (monto, cliente_id))
    conn.execute("INSERT INTO cuenta_corriente (cliente_id,tipo,monto,descripcion) VALUES (?,'cargo',?,?)",
                 (cliente_id, monto, desc))
    conn.commit()
    nuevo = conn.execute("SELECT saldo FROM clientes WHERE id=?", (cliente_id,)).fetchone()["saldo"]
    conn.close()
    return {"ok": True, "saldo": nuevo, "msg": f"Fiado registrado. Saldo: ${nuevo:,.0f}"}

def db_pago_cliente(cliente_id, monto, desc="Pago"):
    conn = get_db()
    cl = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
    if not cl:
        conn.close()
        return {"ok": False, "msg": "Cliente no encontrado"}
    conn.execute("UPDATE clientes SET saldo=saldo-? WHERE id=?", (monto, cliente_id))
    conn.execute("INSERT INTO cuenta_corriente (cliente_id,tipo,monto,descripcion) VALUES (?,'pago',?,?)",
                 (cliente_id, monto, desc))
    conn.commit()
    nuevo = conn.execute("SELECT saldo FROM clientes WHERE id=?", (cliente_id,)).fetchone()["saldo"]
    conn.close()
    return {"ok": True, "saldo": nuevo, "msg": f"Pago registrado. Saldo: ${nuevo:,.0f}"}

def db_cuenta_cliente(cliente_id):
    conn = get_db()
    cl = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
    if not cl:
        conn.close()
        return None
    movs = [dict(r) for r in conn.execute(
        "SELECT * FROM cuenta_corriente WHERE cliente_id=? ORDER BY id DESC LIMIT 30", (cliente_id,)).fetchall()]
    result = dict(cl)
    result["movimientos"] = movs
    conn.close()
    return result

def db_movimientos(limit=30):
    conn = get_db()
    rows = [dict(r) for r in conn.execute("""
        SELECT * FROM movimientos_stock ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()]
    conn.close()
    return rows

def db_import_precios_csv(csv_text):
    import csv as csvmod, io
    reader = csvmod.DictReader(io.StringIO(csv_text))
    conn = get_db()
    ok, errores = 0, []
    for row in reader:
        codigo = (row.get("codigo") or row.get("Codigo") or "").strip()
        precio_venta = row.get("precio_venta") or row.get("Precio Venta") or row.get("precio") or ""
        precio_costo = row.get("precio_costo") or row.get("Precio Costo") or row.get("costo") or ""
        if not codigo:
            continue
        try:
            updates, params = [], []
            if precio_venta:
                updates.append("precio_venta=?"); params.append(float(precio_venta))
            if precio_costo:
                updates.append("precio_costo=?"); params.append(float(precio_costo))
            if updates:
                params.append(codigo)
                r = conn.execute(f"UPDATE productos SET {','.join(updates)},updated_at=datetime('now','localtime') WHERE codigo=? AND activo=1", params)
                if r.rowcount > 0: ok += 1
                else: errores.append(f"{codigo}: no encontrado")
        except Exception as e:
            errores.append(f"{codigo}: {e}")
    conn.commit()
    conn.close()
    return {"ok": True, "actualizados": ok, "errores": errores}

def db_export_csv(fd, fh):
    conn = get_db()
    rows = conn.execute("""
        SELECT v.id,v.fecha,v.hora,vi.producto_nombre,vi.cantidad,vi.precio_unitario,vi.subtotal,v.metodo_pago,v.total
        FROM ventas v JOIN ventas_items vi ON vi.venta_id=v.id
        WHERE v.fecha BETWEEN ? AND ? AND v.anulada=0 ORDER BY v.id
    """, (fd,fh)).fetchall()
    conn.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["#Venta","Fecha","Hora","Producto","Cantidad","Precio Unit.","Subtotal","Metodo Pago","Total Venta"])
    for r in rows: w.writerow(list(r))
    return out.getvalue()

# ═══════════════════════════════════════════════════════════
# HTTP HANDLER
# ═══════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*a): pass

    def send_json(self,data,st=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(st)
        self.send_header("Content-Type","application/json;charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self,html):
        body=html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","text/html;charset=utf-8")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self,data,fn):
        body=data.encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type","text/csv;charset=utf-8")
        self.send_header("Content-Disposition",f"attachment;filename={fn}")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def body(self):
        n=int(self.headers.get("Content-Length",0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        parsed=urlparse(self.path); p=parsed.path
        qs=parse_qs(parsed.query); g=lambda k,d="":qs.get(k,[d])[0]
        if p in("/","index.html"): self.send_html(get_html())
        elif p=="/api/dashboard": self.send_json(db_dashboard())
        elif p=="/api/productos": self.send_json(db_productos(g("q"),g("cat")))
        elif p.startswith("/api/producto/"):
            pr=db_producto_codigo(p.split("/")[-1])
            self.send_json(pr or {"error":"No encontrado"},200 if pr else 404)
        elif p=="/api/ventas": self.send_json(db_ventas(g("desde"),g("hasta"),g("metodo"),int(g("limit","100"))))
        elif p=="/api/reportes": self.send_json(db_reportes(g("periodo","mes")))
        elif p=="/api/config": self.send_json(db_config())
        elif p=="/api/caja": self.send_json(db_caja())
        elif p=="/api/clientes":
            self.send_json(db_clientes(g("q")))
        elif p.startswith("/api/clientes/") and p.split("/")[-1].isdigit():
            self.send_json(db_cuenta_cliente(int(p.split("/")[-1])) or {"error":"No encontrado"})
        elif p=="/api/rentabilidad":
            fd=g("desde",date.today().replace(day=1).isoformat()); fh=g("hasta",date.today().isoformat())
            self.send_json(db_rentabilidad_cat(fd,fh))
        elif p=="/api/movimientos":
            self.send_json(db_movimientos(int(g("limit","50"))))
        elif p=="/api/backup":
            import shutil, tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
            tmp.close()
            shutil.copy2(DB_PATH, tmp.name)
            with open(tmp.name, "rb") as f:
                body = f.read()
            os.unlink(tmp.name)
            fn = f"kiosco_backup_{date.today().isoformat()}.db"
            self.send_response(200)
            self.send_header("Content-Type","application/octet-stream")
            self.send_header("Content-Disposition",f"attachment;filename={fn}")
            self.send_header("Content-Length",len(body))
            self.end_headers()
            self.wfile.write(body)
        elif p=="/api/export/csv":
            fd=g("desde",date.today().replace(day=1).isoformat()); fh=g("hasta",date.today().isoformat())
            self.send_csv(db_export_csv(fd,fh),f"ventas_{fd}_{fh}.csv")
        else: self.send_json({"error":"404"},404)

    def do_POST(self):
        b=self.body(); p=urlparse(self.path).path
        if p=="/api/clientes":
            self.send_json(db_crear_cliente(b))
        elif p=="/api/clientes/fiado":
            self.send_json(db_fiado(b["cliente_id"], b["monto"], b.get("desc","Fiado")))
        elif p=="/api/clientes/pago":
            self.send_json(db_pago_cliente(b["cliente_id"], b["monto"], b.get("desc","Pago")))
        elif p=="/api/import/precios":
            csv_text = b.get("csv","")
            self.send_json(db_import_precios_csv(csv_text))
        elif p=="/api/productos": self.send_json(db_crear_producto(b))
        elif p=="/api/venta": self.send_json(db_venta(b))
        elif p=="/api/stock/entrada": self.send_json(db_stock_entrada(b["producto_id"],b["cantidad"],b.get("motivo","Compra proveedor")))
        elif p=="/api/caja/abrir": self.send_json(db_abrir_caja(b.get("monto_inicial",0),b.get("obs","")))
        elif p=="/api/caja/cerrar": self.send_json(db_cerrar_caja(b.get("obs","")))
        elif p=="/api/config": self.send_json(db_set_config(b))
        else: self.send_json({"error":"404"},404)

    def do_PUT(self):
        b=self.body(); parts=urlparse(self.path).path.split("/")
        if len(parts)>=4 and parts[2]=="productos" and parts[3].isdigit():
            self.send_json(db_editar_producto(int(parts[3]),b))
        else: self.send_json({"error":"404"},404)

    def do_DELETE(self):
        parts=urlparse(self.path).path.split("/")
        if len(parts)>=4 and parts[2]=="productos" and parts[3].isdigit():
            self.send_json(db_eliminar_producto(int(parts[3])))
        elif len(parts)>=4 and parts[2]=="ventas" and parts[3].isdigit():
            self.send_json(db_anular_venta(int(parts[3])))
        else: self.send_json({"error":"404"},404)

# ═══════════════════════════════════════════════════════════
# FRONTEND
# ═══════════════════════════════════════════════════════════
def get_html():
    return r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Kiosco Digital</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;900&family=Archivo+Narrow:wght@400;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#f5f0e8;--dark:#1a1200;--yellow:#f5c800;--yellow-d:#c9a100;
  --blue:#0057ff;--blue-l:#e8eeff;--mp:#009ee3;--mp-l:#e6f6fc;
  --green:#00c566;--green-l:#e6fff3;--red:#ff3b30;--red-l:#fff0ef;
  --surface:#fff;--border:#e0d8c8;--muted:#8a7d60;--text:#1a1200;
  --sidebar:250px;--radius:12px;
}
[data-theme="dark"]{
  --bg:#0f0d0a;--surface:#1a1611;--border:#2e2820;--muted:#6b5e48;--text:#f0e8d8;
  --blue-l:#0a1433;--mp-l:#021520;--green-l:#061a0f;--red-l:#1a0604;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Archivo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
a{text-decoration:none;color:inherit}

/* LAYOUT */
.app{display:flex;min-height:100vh}
.sidebar{width:var(--sidebar);background:var(--dark);display:flex;flex-direction:column;position:fixed;height:100vh;z-index:200;transition:width .2s}
.main{margin-left:var(--sidebar);flex:1;display:flex;flex-direction:column;min-height:100vh}
.content{flex:1;padding:28px;max-width:1400px}

/* SIDEBAR */
.logo{padding:22px 20px 18px;border-bottom:1px solid rgba(255,255,255,.08)}
.logo-mark{font-size:1.35rem;font-weight:900;color:#fff;letter-spacing:-.02em}
.logo-mark em{color:var(--yellow);font-style:normal}
.logo-sub{font-size:.58rem;color:rgba(255,255,255,.3);letter-spacing:.12em;text-transform:uppercase;margin-top:2px;font-family:'Archivo Narrow',sans-serif}
nav{flex:1;padding:10px 0;overflow-y:auto}
.nav-section{font-size:.52rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:rgba(255,255,255,.2);padding:16px 20px 6px}
.nav-item{display:flex;align-items:center;gap:11px;padding:10px 20px;cursor:pointer;transition:all .15s;border-left:3px solid transparent;color:rgba(255,255,255,.45);font-size:.8rem;font-weight:500;user-select:none}
.nav-item:hover{background:rgba(255,255,255,.05);color:rgba(255,255,255,.8)}
.nav-item.active{background:rgba(245,200,0,.1);border-left-color:var(--yellow);color:var(--yellow)}
.nav-icon{font-size:.95rem;width:18px;text-align:center;flex-shrink:0}
.nav-badge{margin-left:auto;background:var(--red);color:#fff;font-size:.5rem;font-weight:700;padding:2px 6px;border-radius:10px;min-width:18px;text-align:center}
.sidebar-footer{padding:14px 20px;border-top:1px solid rgba(255,255,255,.08)}
.version{font-size:.58rem;color:rgba(255,255,255,.18);font-family:'Archivo Narrow',sans-serif;line-height:1.5}

/* STATUS BAR */
.statusbar{background:var(--dark);color:rgba(255,255,255,.4);font-size:.65rem;font-family:'Archivo Narrow',sans-serif;padding:6px 28px;display:flex;align-items:center;gap:20px;border-top:1px solid rgba(255,255,255,.06)}
.sb-item{display:flex;align-items:center;gap:5px}
.sb-dot{width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0}
.sb-dot.off{background:var(--red)}

/* PAGES */
.page{display:none;animation:fadeIn .2s ease}
.page.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.page-header{margin-bottom:22px;display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px}
.page-title{font-size:1.55rem;font-weight:900;letter-spacing:-.02em}
.page-sub{font-family:'Archivo Narrow',sans-serif;color:var(--muted);font-size:.8rem;margin-top:3px}

/* CARDS */
.card{background:var(--surface);border:1.5px solid var(--border);border-radius:var(--radius);padding:20px}
.card+.card{margin-top:14px}
.card-title{font-size:.62rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:14px}

/* STAT CARDS */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat{background:var(--surface);border:1.5px solid var(--border);border-radius:var(--radius);padding:18px 16px;position:relative;overflow:hidden;transition:transform .15s,box-shadow .15s}
.stat:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.08)}
.stat::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:var(--radius) var(--radius) 0 0}
.stat.yellow::after{background:var(--yellow)}
.stat.blue::after{background:var(--blue)}
.stat.green::after{background:var(--green)}
.stat.red::after{background:var(--red)}
.stat-icon{font-size:1.4rem;margin-bottom:10px}
.stat-val{font-size:1.35rem;font-weight:900;letter-spacing:-.02em;line-height:1}
.stat-label{font-family:'Archivo Narrow',sans-serif;font-size:.68rem;color:var(--muted);margin-top:4px}

/* GRIDS */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px}

/* TABLE */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{font-size:.58rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);padding:9px 12px;text-align:left;border-bottom:2px solid var(--border);white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafaf7}
.td-muted{font-family:'Archivo Narrow',sans-serif;font-size:.7rem;color:var(--muted)}

/* BADGES */
.badge{display:inline-flex;align-items:center;font-size:.6rem;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.badge-cat{background:var(--blue-l);color:var(--blue)}
.badge-mp{background:var(--mp-l);color:var(--mp)}
.badge-ef{background:var(--green-l);color:var(--green)}
.badge-warn{background:#fff8e6;color:#c47d00}
.badge-danger{background:var(--red-l);color:var(--red)}
.badge-ok{background:var(--green-l);color:var(--green)}
.badge-anulada{background:#f0f0f0;color:#999;text-decoration:line-through}

/* FORMS */
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.form-full{grid-column:span 2}
label{display:block;font-size:.62rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-bottom:5px}
input,select,textarea{width:100%;padding:9px 12px;border:1.5px solid var(--border);border-radius:9px;font-size:.85rem;font-family:'Archivo',sans-serif;outline:none;transition:border-color .15s;background:#fff;color:var(--text)}
input:focus,select:focus,textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(0,87,255,.08)}
input[type=number]{-moz-appearance:textfield}
input::-webkit-outer-spin-button,input::-webkit-inner-spin-button{-webkit-appearance:none}

/* BUTTONS */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:10px 18px;border-radius:9px;font-size:.8rem;font-weight:700;cursor:pointer;border:none;transition:all .15s;font-family:'Archivo',sans-serif;white-space:nowrap}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:var(--dark);color:#fff}
.btn-primary:hover:not(:disabled){background:#2d2200}
.btn-yellow{background:var(--yellow);color:var(--dark)}
.btn-yellow:hover:not(:disabled){background:var(--yellow-d)}
.btn-green{background:var(--green);color:#fff}
.btn-green:hover:not(:disabled){background:#00a854}
.btn-mp{background:var(--mp);color:#fff}
.btn-mp:hover:not(:disabled){background:#007ab8}
.btn-red{background:var(--red-l);color:var(--red);border:1.5px solid var(--red)}
.btn-red:hover:not(:disabled){background:var(--red);color:#fff}
.btn-ghost{background:transparent;color:var(--muted);border:1.5px solid var(--border)}
.btn-ghost:hover:not(:disabled){border-color:var(--dark);color:var(--dark)}
.btn-sm{padding:6px 12px;font-size:.7rem}
.btn-icon{padding:7px;border-radius:8px}
.btn-full{width:100%}
.btn-xl{padding:14px 24px;font-size:.95rem}

/* SCAN HEADER */
.scan-header{background:var(--dark);border-radius:var(--radius);padding:22px 24px;margin-bottom:14px}
.scan-header-title{font-size:.75rem;font-weight:700;color:rgba(255,255,255,.5);letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}
.scan-row{display:flex;gap:10px}
.scan-input{background:rgba(255,255,255,.07);border:2px solid rgba(255,255,255,.12);border-radius:9px;color:#fff;font-size:1rem;font-weight:700;text-align:center;letter-spacing:.04em;padding:11px 14px;transition:all .15s}
.scan-input:focus{border-color:var(--yellow);background:rgba(255,255,255,.1);box-shadow:none}
.scan-input::placeholder{color:rgba(255,255,255,.2);font-weight:400}

/* POS LAYOUT */
.pos-wrap{display:grid;grid-template-columns:1fr 360px;gap:16px;align-items:start}
.pos-product-card{background:var(--green-l);border:2px solid var(--green);border-radius:var(--radius);padding:18px;display:none;margin-bottom:14px}
.pos-product-card.show{display:block}
.pos-product-card.notfound{background:var(--red-l);border-color:var(--red)}
.pos-pname{font-size:1.05rem;font-weight:900;margin-bottom:3px}
.pos-pinfo{font-family:'Archivo Narrow',sans-serif;font-size:.75rem;color:var(--muted)}
.pos-pprice{font-size:1.3rem;font-weight:900;color:var(--green);margin-top:6px}

/* CART */
.cart-card{background:var(--surface);border:1.5px solid var(--border);border-radius:var(--radius);position:sticky;top:20px}
.cart-header{padding:16px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.cart-title{font-size:.75rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.cart-items{min-height:120px;max-height:320px;overflow-y:auto;padding:10px 0}
.cart-item{display:flex;align-items:center;gap:10px;padding:8px 16px;border-bottom:1px solid var(--border)}
.cart-item:last-child{border-bottom:none}
.cart-item-name{flex:1;font-size:.8rem;font-weight:600}
.cart-item-qty{font-size:.72rem;color:var(--muted);font-family:'Archivo Narrow',sans-serif}
.cart-item-price{font-size:.82rem;font-weight:700;color:var(--dark)}
.cart-empty{padding:32px;text-align:center;color:var(--muted);font-family:'Archivo Narrow',sans-serif;font-size:.8rem}
.cart-footer{padding:16px 18px;border-top:2px solid var(--border)}
.cart-line{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:.82rem}
.cart-line.total{font-size:1.1rem;font-weight:900;margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}
.cart-methods{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}
.method-btn{padding:10px;border-radius:9px;border:2px solid var(--border);cursor:pointer;text-align:center;transition:all .15s;font-size:.75rem;font-weight:700;background:#fff}
.method-btn.active.ef{border-color:var(--green);background:var(--green-l);color:var(--green)}
.method-btn.active.mp{border-color:var(--mp);background:var(--mp-l);color:var(--mp)}
.method-btn:hover{border-color:var(--dark)}

/* STOCK BAR */
.stock-bar-wrap{width:60px;height:5px;background:var(--bg);border-radius:3px;overflow:hidden;flex-shrink:0}
.stock-bar{height:100%;border-radius:3px}
.stock-visual{display:flex;align-items:center;gap:8px}
.s-ok{color:var(--green);font-weight:700}
.s-warn{color:#c47d00;font-weight:700}
.s-low{color:var(--red);font-weight:700}

/* TOAST */
.toast{position:fixed;bottom:60px;right:24px;background:var(--dark);color:#fff;padding:13px 18px;border-radius:11px;font-size:.8rem;font-weight:600;z-index:999;transform:translateY(80px);opacity:0;transition:all .3s ease;max-width:320px;border-left:4px solid var(--yellow);pointer-events:none}
.toast.show{transform:translateY(0);opacity:1}
.toast.ok{border-left-color:var(--green)}
.toast.err{border-left-color:var(--red)}

/* MODAL */
.modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:500;display:none;align-items:center;justify-content:center}
.modal-bg.show{display:flex}
.modal{background:#fff;border-radius:16px;padding:28px;width:100%;max-width:540px;max-height:90vh;overflow-y:auto;animation:fadeIn .2s ease}
.modal-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
.modal-title{font-size:1.1rem;font-weight:900}
.modal-close{background:none;border:none;cursor:pointer;font-size:1.2rem;color:var(--muted);line-height:1}

/* ALERT */
.alert{padding:12px 16px;border-radius:9px;font-size:.78rem;margin-bottom:12px;display:flex;align-items:flex-start;gap:8px;line-height:1.4}
.alert-warn{background:#fff8e6;border:1px solid var(--yellow-d);color:#7a5c00}
.alert-info{background:var(--blue-l);border:1px solid var(--blue);color:var(--blue)}
.alert-ok{background:var(--green-l);border:1px solid var(--green);color:#006633}

/* VENTA RESULT */
.venta-ok{background:var(--green-l);border:2px solid var(--green);border-radius:var(--radius);padding:24px;text-align:center;display:none}
.venta-ok.show{display:block;animation:fadeIn .3s ease}
.venta-total{font-size:2.2rem;font-weight:900;color:var(--green)}

/* CHIP FILTERS */
.chip-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.chip{padding:5px 14px;border-radius:20px;border:1.5px solid var(--border);font-size:.72rem;font-weight:600;cursor:pointer;transition:all .15s;background:#fff}
.chip:hover{border-color:var(--dark)}
.chip.active{background:var(--dark);color:#fff;border-color:var(--dark)}

/* CAJA */
.caja-status{border-radius:var(--radius);padding:28px;text-align:center;margin-bottom:16px}
.caja-status.abierta{background:var(--green-l);border:2px solid var(--green)}
.caja-status.cerrada{background:var(--red-l);border:2px solid var(--red)}
.caja-icon{font-size:2.5rem;margin-bottom:10px}
.caja-label{font-size:1.1rem;font-weight:900;margin-bottom:4px}
.caja-sub{font-family:'Archivo Narrow',sans-serif;font-size:.78rem;color:var(--muted)}

/* KEYBOARD HINTS */
.kbd{display:inline-block;background:var(--bg);border:1px solid var(--border);border-radius:5px;padding:2px 6px;font-size:.6rem;font-family:'Archivo Narrow',sans-serif;color:var(--muted);vertical-align:middle}

/* TOP LIST */
.top-item{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.top-item:last-child{border-bottom:none}
.top-num{font-size:.62rem;font-weight:700;color:var(--muted);width:16px;flex-shrink:0}
.top-name{flex:1;font-size:.78rem;font-weight:600}
.top-bar-wrap{width:50px;height:4px;background:var(--bg);border-radius:2px;overflow:hidden}
.top-bar{height:100%;background:var(--yellow);border-radius:2px}
.top-val{font-size:.75rem;font-weight:700;color:var(--green);white-space:nowrap}

/* SEARCHBAR */
.searchbar{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.searchbar input{flex:1;min-width:200px}
.searchbar select{min-width:150px}

/* SHORTCUTS PANEL */
.shortcuts{background:rgba(0,0,0,.03);border:1px solid var(--border);border-radius:9px;padding:12px 16px;font-size:.7rem;color:var(--muted);font-family:'Archivo Narrow',sans-serif;margin-bottom:14px}
.shortcuts span{margin-right:16px;white-space:nowrap}
</style>
</head>
<body>
<div class="app">

<!-- SIDEBAR -->
<aside class="sidebar">
  <div class="logo">
    <div class="logo-mark">&#127978; <em>Kiosco</em></div>
    <div class="logo-sub">Sistema Digital v2.0</div>
  </div>
  <nav>
    <div class="nav-section">Operaciones</div>
    <div class="nav-item active" data-page="dashboard" onclick="nav(this)">
      <span class="nav-icon">&#128202;</span><span>Dashboard</span>
    </div>
    <div class="nav-item" data-page="pos" onclick="nav(this)">
      <span class="nav-icon">&#128176;</span><span>Nueva Venta</span>
      <span class="kbd" style="margin-left:auto">F2</span>
    </div>
    <div class="nav-item" data-page="ingreso" onclick="nav(this)">
      <span class="nav-icon">&#128229;</span><span>Ingreso Stock</span>
    </div>
    <div class="nav-section">Inventario</div>
    <div class="nav-item" data-page="stock" onclick="nav(this)">
      <span class="nav-icon">&#128230;</span><span>Stock</span>
    </div>
    <div class="nav-item" data-page="productos" onclick="nav(this)">
      <span class="nav-icon">&#127991;</span><span>Productos</span>
    </div>
    <div class="nav-section">Reportes</div>
    <div class="nav-item" data-page="historial" onclick="nav(this)">
      <span class="nav-icon">&#128203;</span><span>Historial Ventas</span>
    </div>
    <div class="nav-item" data-page="reportes" onclick="nav(this)">
      <span class="nav-icon">&#128200;</span><span>Reportes</span>
    </div>
    <div class="nav-item" data-page="fiados" onclick="nav(this)">
      <span class="nav-icon">&#128101;</span><span>Fiados / Clientes</span>
    </div>
    <div class="nav-section">Sistema</div>
    <div class="nav-item" data-page="caja" onclick="nav(this)">
      <span class="nav-icon">&#128181;</span><span>Caja</span>
    </div>
    <div class="nav-item" data-page="config" onclick="nav(this)">
      <span class="nav-icon">&#9881;</span><span>Configuracion</span>
    </div>
  </nav>
  <div class="sidebar-footer">
    <button onclick="toggleDark()" style="width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;color:rgba(255,255,255,.5);padding:7px;font-size:.72rem;cursor:pointer;font-family:'Archivo',sans-serif;margin-bottom:8px" id="dark-btn">&#9790; Modo oscuro</button>
    <div class="version">Kiosco Digital v2.0<br>Python + SQLite</div>
  </div>
</aside>

<!-- MAIN -->
<main class="main">
<div class="content">

<!-- DASHBOARD -->
<div id="page-dashboard" class="page active">
  <div class="page-header">
    <div><div class="page-title">Dashboard</div><div class="page-sub" id="dash-fecha">Cargando...</div></div>
    <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">&#8635; Actualizar</button>
  </div>
  <div class="stats-row">
    <div class="stat yellow"><div class="stat-icon">&#128176;</div><div class="stat-val" id="s-total">-</div><div class="stat-label">Ventas hoy</div></div>
    <div class="stat blue"><div class="stat-icon">&#129534;</div><div class="stat-val" id="s-transac">-</div><div class="stat-label">Transacciones</div></div>
    <div class="stat green"><div class="stat-icon">&#128200;</div><div class="stat-val" id="s-ganancia">-</div><div class="stat-label">Ganancia estimada</div></div>
    <div class="stat red"><div class="stat-icon">&#9888;</div><div class="stat-val" id="s-stock-bajo">-</div><div class="stat-label">Stock bajo</div></div>
  </div>
  <div class="g2">
    <div class="card">
      <div class="card-title">&#128200; Ventas ultimos 7 dias</div>
      <canvas id="chart-semana" height="120"></canvas>
    </div>
    <div class="card">
      <div class="card-title">&#127942; Top productos hoy</div>
      <div id="top-hoy"><div style="color:var(--muted);font-size:.78rem;text-align:center;padding:24px">Sin ventas hoy</div></div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">&#9888;&#65039; Productos con stock bajo</div>
    <div id="bajo-stock-list"></div>
  </div>
</div>

<!-- POS - NUEVA VENTA -->
<div id="page-pos" class="page">
  <div class="page-header">
    <div><div class="page-title">Nueva Venta</div><div class="page-sub">Escaneá o buscá el producto y agregalo al carrito</div></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="resetPOS()">&#10060; Limpiar <span class="kbd">F5</span></button>
    </div>
  </div>
  <div class="shortcuts">
    <span><span class="kbd">Enter</span> Buscar / Agregar</span>
    <span><span class="kbd">F5</span> Limpiar carrito</span>
    <span><span class="kbd">F10</span> Confirmar venta</span>
    <span><span class="kbd">Esc</span> Cancelar</span>
  </div>
  <div class="scan-header">
    <div class="scan-header-title">&#128247; Escanear o buscar producto</div>
    <div class="scan-row">
      <input id="pos-cod" type="text" class="scan-input" style="flex:1" placeholder="Codigo de barras o nombre del producto..." autocomplete="off" onkeydown="posKeydown(event)">
      <button class="btn btn-yellow" onclick="posBuscar()">&#128269; Buscar</button>
    </div>
  </div>
  <div class="pos-wrap">
    <div>
      <div id="pos-result"></div>
      <div id="pos-prod-card" class="pos-product-card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
          <div>
            <div class="pos-pname" id="pos-pname">-</div>
            <div class="pos-pinfo">Cod: <span id="pos-pcod">-</span> &middot; Stock: <span id="pos-pstock">-</span> u &middot; Cat: <span id="pos-pcat">-</span></div>
            <div class="pos-pprice" id="pos-pprice">$0</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:10px;min-width:180px">
            <div>
              <label>Cantidad</label>
              <input type="number" id="pos-cant" value="1" min="1" style="text-align:center" onkeydown="if(event.key==='Enter'){agregarCarrito();event.preventDefault()}">
            </div>
            <button class="btn btn-green btn-full" onclick="agregarCarrito()">&#43; Agregar al carrito</button>
          </div>
        </div>
      </div>
      <div id="pos-notfound" class="pos-product-card notfound" style="display:none">
        <strong style="color:var(--red)">&#10060; Producto no encontrado.</strong>
        <span style="font-size:.8rem;color:var(--muted);margin-left:8px">Verificá el codigo o registralo en Productos.</span>
      </div>
    </div>
    <!-- CART -->
    <div class="cart-card">
      <div class="cart-header">
        <span class="cart-title">&#128722; Carrito</span>
        <span id="cart-count" style="font-size:.7rem;font-weight:700;color:var(--muted)">0 items</span>
      </div>
      <div class="cart-items" id="cart-items">
        <div class="cart-empty">El carrito esta vacio<br>Escaneá un producto para empezar</div>
      </div>
      <div class="cart-footer">
        <div class="cart-line"><span>Subtotal</span><span id="cart-sub">$0</span></div>
        <div class="cart-line">
          <span>Descuento</span>
          <input type="number" id="cart-desc" value="0" min="0" style="width:90px;text-align:right;padding:4px 8px;font-size:.8rem" oninput="recalcTotal()">
        </div>
        <div class="cart-line total"><span>TOTAL</span><span id="cart-total" style="color:var(--green)">$0</span></div>
        <div class="cart-methods">
          <div class="method-btn ef active" id="method-ef" onclick="setMetodo('efectivo')">&#128181; Efectivo</div>
          <div class="method-btn mp" id="method-mp" onclick="setMetodo('mp')">&#128241; Mercado Pago</div>
        </div>
        <button class="btn btn-green btn-full btn-xl" onclick="confirmarVenta()" id="btn-confirmar" style="font-size:.9rem">
          &#10003; CONFIRMAR VENTA <span class="kbd" style="color:rgba(255,255,255,.5)">F10</span>
        </button>
      </div>
    </div>
  </div>
  <div id="venta-ok" class="venta-ok">
    <div style="font-size:2rem;margin-bottom:8px">&#10003;</div>
    <div class="venta-total" id="vok-total">$0</div>
    <div style="font-family:'Archivo Narrow',sans-serif;font-size:.8rem;color:var(--muted);margin-top:4px" id="vok-detalle">-</div>
    <div style="display:flex;gap:10px;justify-content:center;margin-top:16px;flex-wrap:wrap">
      <button class="btn btn-ghost" onclick="nuevaVenta()">&#43; Nueva Venta</button>
      <button class="btn btn-primary" onclick="imprimirTicket()">&#128438; Imprimir Ticket</button>
    </div>
  </div>
</div>

<!-- STOCK -->
<div id="page-stock" class="page">
  <div class="page-header">
    <div><div class="page-title">Estado del Stock</div><div class="page-sub">Inventario actualizado en tiempo real</div></div>
  </div>
  <div class="searchbar">
    <input type="text" id="stock-q" placeholder="&#128269;  Buscar producto..." oninput="cargarStock()">
    <select id="stock-cat" onchange="cargarStock()">
      <option value="">Todas las categorias</option>
      <option>Bebidas</option><option>Snacks</option><option>Golosinas</option>
      <option>Tabaco</option><option>Almacen</option><option>Lacteos</option>
    </select>
    <select id="stock-filtro" onchange="cargarStock()">
      <option value="">Todo el stock</option>
      <option value="bajo">Stock bajo</option>
      <option value="sin">Sin stock</option>
    </select>
  </div>
  <div class="card">
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Codigo</th><th>Producto</th><th>Categoria</th>
          <th>P. Costo</th><th>P. Venta</th><th>Margen</th><th>Stock</th><th>Estado</th>
        </tr></thead>
        <tbody id="stock-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- INGRESO MERCADERIA -->
<div id="page-ingreso" class="page">
  <div class="page-header">
    <div><div class="page-title">Ingreso de Mercaderia</div><div class="page-sub">Registra la mercaderia que entra al kiosco</div></div>
  </div>
  <div class="scan-header">
    <div class="scan-header-title">&#128229; Escanear para ingresar</div>
    <div class="scan-row">
      <input id="ing-cod" type="text" class="scan-input" style="flex:1" placeholder="Codigo de barras..." autocomplete="off" onkeydown="if(event.key==='Enter')ingrBuscar()">
      <button class="btn btn-yellow" onclick="ingrBuscar()">&#128269; Buscar</button>
    </div>
  </div>
  <div id="ingr-prod" class="pos-product-card" style="display:none">
    <div class="pos-pname" id="ingr-nombre">-</div>
    <div class="pos-pinfo">Stock actual: <strong id="ingr-stock">-</strong> unidades</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:14px">
      <div><label>Cantidad a ingresar</label><input type="number" id="ingr-cant" value="1" min="1"></div>
      <div><label>Motivo</label>
        <select id="ingr-motivo">
          <option value="Compra proveedor">Compra al proveedor</option>
          <option value="Devolucion">Devolucion</option>
          <option value="Ajuste manual">Ajuste manual</option>
        </select>
      </div>
      <div style="display:flex;align-items:flex-end">
        <button class="btn btn-green btn-full" onclick="ingrConfirmar()">&#128229; Confirmar Ingreso</button>
      </div>
    </div>
  </div>
  <div id="ingr-notfound" class="pos-product-card notfound" style="display:none">
    <strong style="color:var(--red)">&#10060; Producto no encontrado.</strong>
  </div>
  <div class="card" style="margin-top:14px">
    <div class="card-title">&#128203; Ultimos ingresos registrados</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Fecha</th><th>Producto</th><th>Tipo</th><th>Cantidad</th><th>Stock Anterior</th><th>Stock Nuevo</th><th>Motivo</th></tr></thead>
        <tbody id="mov-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- PRODUCTOS -->
<div id="page-productos" class="page">
  <div class="page-header">
    <div><div class="page-title">Productos</div><div class="page-sub">Gestioná el catalogo completo</div></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-ghost btn-sm" onclick="toggleImportCSV()">&#128196; Importar precios CSV</button>
      <button class="btn btn-yellow" onclick="openModal()">&#43; Nuevo Producto</button>
    </div>
  </div>
  <div id="import-csv-panel" style="display:none" class="card" style="margin-bottom:14px">
    <div class="card-title">&#128196; Importar precios desde CSV</div>
    <div class="alert alert-info" style="margin-bottom:12px;font-size:.72rem">
      El archivo debe tener columnas: <strong>codigo</strong>, <strong>precio_venta</strong> (y opcionalmente <strong>precio_costo</strong>).
      La primera fila debe ser el encabezado. Solo se actualizan productos existentes.
    </div>
    <textarea id="csv-input" rows="6" style="font-family:monospace;font-size:.75rem;resize:vertical" placeholder="codigo,precio_venta,precio_costo&#10;7790040153993,700,380&#10;7790040150114,1050,580"></textarea>
    <div style="display:flex;gap:10px;margin-top:10px;align-items:center;flex-wrap:wrap">
      <button class="btn btn-primary" onclick="importarCSV()">&#10003; Importar y actualizar precios</button>
      <label style="text-transform:none;font-size:.8rem;cursor:pointer;color:var(--blue)">
        &#128196; O cargar archivo .csv
        <input type="file" accept=".csv" style="display:none" onchange="leerCSV(this)">
      </label>
    </div>
    <div id="import-result" style="margin-top:10px"></div>
  </div>
  <div class="searchbar">
    <input type="text" id="prod-q" placeholder="&#128269;  Buscar producto..." oninput="cargarProductos()">
    <select id="prod-cat" onchange="cargarProductos()">
      <option value="">Todas las categorias</option>
      <option>Bebidas</option><option>Snacks</option><option>Golosinas</option>
      <option>Tabaco</option><option>Almacen</option><option>Lacteos</option>
    </select>
  </div>
  <div class="card">
    <div class="table-wrap">
      <table>
        <thead><tr><th>Codigo</th><th>Producto</th><th>Categoria</th><th>P. Costo</th><th>P. Venta</th><th>Margen</th><th>Stock</th><th>Min.</th><th>Acciones</th></tr></thead>
        <tbody id="prod-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- HISTORIAL -->
<div id="page-historial" class="page">
  <div class="page-header">
    <div><div class="page-title">Historial de Ventas</div><div class="page-sub">Todas las transacciones registradas</div></div>
    <button class="btn btn-ghost btn-sm" onclick="exportarCSV()">&#128190; Exportar CSV</button>
  </div>
  <div class="searchbar">
    <input type="date" id="hist-desde">
    <input type="date" id="hist-hasta">
    <select id="hist-metodo">
      <option value="">Todos los metodos</option>
      <option value="efectivo">Efectivo</option>
      <option value="mp">Mercado Pago</option>
    </select>
    <button class="btn btn-primary" onclick="cargarHistorial()">Filtrar</button>
  </div>
  <div class="card">
    <div class="table-wrap">
      <table>
        <thead><tr><th>#</th><th>Fecha</th><th>Hora</th><th>Items</th><th>Total</th><th>Pago</th><th>Estado</th><th></th></tr></thead>
        <tbody id="hist-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- REPORTES -->
<div id="page-reportes" class="page">
  <div class="page-header">
    <div><div class="page-title">Reportes</div><div class="page-sub">Analisis de ventas y rentabilidad</div></div>
    <button class="btn btn-ghost btn-sm" onclick="exportarCSV()">&#128190; Exportar CSV</button>
  </div>
  <div class="chip-row">
    <div class="chip active" data-periodo="hoy" onclick="setPeriodo(this)">Hoy</div>
    <div class="chip" data-periodo="semana" onclick="setPeriodo(this)">Ultimos 7 dias</div>
    <div class="chip active2" data-periodo="mes" onclick="setPeriodo(this)">Este mes</div>
    <div class="chip" data-periodo="30dias" onclick="setPeriodo(this)">Ultimos 30 dias</div>
  </div>
  <div class="stats-row" id="rep-stats">
    <div class="stat yellow"><div class="stat-icon">&#128176;</div><div class="stat-val" id="r-total">-</div><div class="stat-label">Total ventas</div></div>
    <div class="stat blue"><div class="stat-icon">&#129534;</div><div class="stat-val" id="r-transac">-</div><div class="stat-label">Transacciones</div></div>
    <div class="stat green"><div class="stat-icon">&#128200;</div><div class="stat-val" id="r-ganancia">-</div><div class="stat-label">Ganancia estimada</div></div>
    <div class="stat red"><div class="stat-icon">&#128197;</div><div class="stat-val" id="r-dias">-</div><div class="stat-label">Dias con ventas</div></div>
  </div>
  <div class="g2">
    <div class="card">
      <div class="card-title">&#128200; Ventas por dia</div>
      <canvas id="chart-rep" height="120"></canvas>
    </div>
    <div class="card">
      <div class="card-title">&#128181; Metodos de pago</div>
      <canvas id="chart-metodos" height="120"></canvas>
    </div>
  </div>
  <div class="card" style="margin-bottom:14px">
    <div class="card-title">&#127981; Rentabilidad por categoria</div>
    <canvas id="chart-categorias" height="80"></canvas>
  </div>
  <div class="card">
    <div class="card-title">&#127942; Productos mas vendidos</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>#</th><th>Producto</th><th>Unidades</th><th>Monto vendido</th><th>Ganancia</th><th>% del total</th></tr></thead>
        <tbody id="rep-prod-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- FIADOS / CUENTA CORRIENTE -->
<div id="page-fiados" class="page">
  <div class="page-header">
    <div><div class="page-title">Fiados y Clientes</div><div class="page-sub">Cuenta corriente por cliente</div></div>
    <button class="btn btn-yellow" onclick="toggleNuevoCliente()">&#43; Nuevo Cliente</button>
  </div>
  <div id="nuevo-cliente-form" style="display:none" class="card" style="margin-bottom:14px">
    <div class="card-title">Nuevo cliente</div>
    <div class="form-grid">
      <div><label>Nombre *</label><input type="text" id="nc-nombre" placeholder="Juan Garcia"></div>
      <div><label>Telefono</label><input type="text" id="nc-tel" placeholder="+54 9 11..."></div>
    </div>
    <div style="display:flex;gap:10px;margin-top:12px">
      <button class="btn btn-primary" onclick="crearCliente()">&#10003; Guardar</button>
      <button class="btn btn-ghost" onclick="toggleNuevoCliente()">Cancelar</button>
    </div>
  </div>
  <div class="searchbar"><input type="text" id="cl-q" placeholder="&#128269; Buscar cliente..." oninput="cargarClientes()"></div>
  <div class="g2">
    <div class="card">
      <div class="card-title">&#128101; Clientes</div>
      <div id="clientes-list"></div>
    </div>
    <div class="card" id="cuenta-detalle" style="display:none">
      <div class="card-title" id="cuenta-titulo">Cuenta</div>
      <div id="cuenta-saldo-box" style="text-align:center;padding:16px 0;border-bottom:1px solid var(--border);margin-bottom:14px">
        <div style="font-size:.7rem;color:var(--muted);margin-bottom:4px">SALDO DEUDOR</div>
        <div id="cuenta-saldo" style="font-size:2rem;font-weight:900;color:var(--red)">$0</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
        <div>
          <label>Cargar fiado ($)</label>
          <input type="number" id="fiado-monto" placeholder="0" min="0">
          <input type="text" id="fiado-desc" placeholder="Descripcion (opcional)" style="margin-top:6px;font-size:.78rem">
        </div>
        <div>
          <label>Registrar pago ($)</label>
          <input type="number" id="pago-monto" placeholder="0" min="0">
          <input type="text" id="pago-desc" placeholder="Descripcion (opcional)" style="margin-top:6px;font-size:.78rem">
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
        <button class="btn btn-red btn-full" onclick="registrarFiado()">&#43; Cargar fiado</button>
        <button class="btn btn-green btn-full" onclick="registrarPago()">&#10003; Registrar pago</button>
      </div>
      <div class="card-title">Ultimos movimientos</div>
      <div id="cuenta-movs" style="max-height:250px;overflow-y:auto"></div>
    </div>
  </div>
</div>

<!-- CAJA -->
<div id="page-caja" class="page">
  <div class="page-header">
    <div><div class="page-title">Caja</div><div class="page-sub">Apertura y cierre de caja diario</div></div>
  </div>
  <div id="caja-status-card"></div>
  <div id="caja-form-apertura" style="display:none" class="card">
    <div class="card-title">Abrir caja</div>
    <div class="form-grid">
      <div><label>Monto inicial en efectivo ($)</label><input type="number" id="caja-monto" value="0" min="0" placeholder="0"></div>
      <div><label>Observaciones</label><input type="text" id="caja-obs-abr" placeholder="Opcional..."></div>
    </div>
    <button class="btn btn-green" style="margin-top:14px" onclick="abrirCaja()">&#128181; Abrir Caja</button>
  </div>
  <div id="caja-form-cierre" style="display:none" class="card">
    <div class="card-title">Cerrar caja</div>
    <div id="caja-resumen-cierre"></div>
    <div style="margin-top:14px"><label>Observaciones</label><input type="text" id="caja-obs-cie" placeholder="Opcional..."></div>
    <button class="btn btn-red" style="margin-top:14px" onclick="cerrarCaja()">&#128274; Cerrar Caja</button>
  </div>
</div>

<!-- CONFIG -->
<div id="page-config" class="page">
  <div class="page-header">
    <div><div class="page-title">Configuracion</div><div class="page-sub">Datos del negocio</div></div>
  </div>
  <div class="card">
    <div class="card-title">Datos del negocio</div>
    <div class="form-grid">
      <div><label>Nombre del negocio</label><input type="text" id="cfg-nombre" placeholder="Mi Kiosco"></div>
      <div><label>Telefono</label><input type="text" id="cfg-tel" placeholder="+54 9 11 ..."></div>
      <div class="form-full"><label>Direccion</label><input type="text" id="cfg-dir" placeholder="Calle, numero, ciudad..."></div>
    </div>
    <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
      <button class="btn btn-primary" onclick="guardarConfig()">&#10003; Guardar Cambios</button>
      <button class="btn btn-ghost" onclick="descargarBackup()">&#128190; Descargar Backup (.db)</button>
    </div>
  </div>
  <div class="card" style="margin-top:14px">
    <div class="card-title">&#128274; Informacion del sistema</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:.8rem">
      <div><span style="color:var(--muted)">Version:</span> <strong>Kiosco Digital v2.0</strong></div>
      <div><span style="color:var(--muted)">Motor:</span> <strong>Python + SQLite</strong></div>
      <div><span style="color:var(--muted)">Base de datos:</span> <strong>kiosco.db (local)</strong></div>
      <div><span style="color:var(--muted)">Requiere internet:</span> <strong>No (solo para fuentes/graficos)</strong></div>
    </div>
    <div class="alert alert-info" style="margin-top:12px;font-size:.72rem">
      &#128161; El backup descarga una copia exacta de tu base de datos. Guardala en un pendrive o Google Drive como respaldo.
    </div>
  </div>
</div>

</div><!-- /content -->

<!-- STATUS BAR -->
<div class="statusbar">
  <div class="sb-item"><div class="sb-dot"></div><span>Sistema activo</span></div>
  <div class="sb-item" id="sb-negocio">Kiosco Digital</div>
  <div class="sb-item" style="margin-left:auto" id="sb-fecha">-</div>
  <div class="sb-item" id="sb-caja-status">Caja: -</div>
</div>
</main>
</div>

<!-- BUSCADOR GLOBAL F3 -->
<div class="modal-bg" id="search-bg" onclick="if(event.target===this)closeSearch()">
  <div class="modal" style="max-width:600px">
    <div style="display:flex;gap:10px;margin-bottom:14px">
      <input id="global-q" type="text" placeholder="Buscar productos, ventas..." style="flex:1;font-size:1rem" oninput="globalSearch()" autocomplete="off">
      <button class="modal-close" onclick="closeSearch()">&#10005;</button>
    </div>
    <div id="global-results" style="max-height:400px;overflow-y:auto"></div>
  </div>
</div>

<!-- MODAL PRODUCTO -->
<div class="modal-bg" id="modal-bg">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-title" id="modal-title">Nuevo Producto</div>
      <button class="modal-close" onclick="closeModal()">&#10005;</button>
    </div>
    <div class="form-grid">
      <div><label>Codigo de barras *</label><input type="text" id="m-cod" placeholder="7790040153993" autocomplete="off"></div>
      <div><label>Nombre *</label><input type="text" id="m-nombre" placeholder="Coca Cola 500ml"></div>
      <div><label>Categoria</label>
        <select id="m-cat">
          <option>Bebidas</option><option>Snacks</option><option>Golosinas</option>
          <option>Tabaco</option><option>Almacen</option><option>Lacteos</option><option>General</option>
        </select>
      </div>
      <div><label>Precio costo ($)</label><input type="number" id="m-costo" placeholder="0" min="0"></div>
      <div><label>Precio venta ($) *</label><input type="number" id="m-venta" placeholder="0" min="0"></div>
      <div><label>Stock inicial</label><input type="number" id="m-stock" value="0" min="0"></div>
      <div><label>Stock minimo alerta</label><input type="number" id="m-minimo" value="5" min="0"></div>
    </div>
    <div style="display:flex;gap:10px;margin-top:18px">
      <button class="btn btn-primary" onclick="guardarProducto()" id="modal-save-btn">&#10003; Guardar</button>
      <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    </div>
  </div>
</div>

<!-- TOAST -->
<div class="toast" id="toast"></div>

<script>
// ── STATE ─────────────────────────────────────────────────
let cart = [];
let posProducto = null;
let metodoActual = 'efectivo';
let modalMode = 'new';
let editId = null;
let periodoActual = 'mes';
let chartSemana = null, chartRep = null, chartMetodos = null, chartCats = null;
let ingrProducto = null;

// ── UTILS ─────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const pesos = n => '$' + Number(n||0).toLocaleString('es-AR',{minimumFractionDigits:0,maximumFractionDigits:0});
const fmt = n => Number(n||0).toLocaleString('es-AR');

function toast(msg, type='') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 3500);
}

function nav(el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  const pg = el.dataset.page;
  $('page-' + pg).classList.add('active');
  if(pg==='dashboard') loadDashboard();
  else if(pg==='stock') cargarStock();
  else if(pg==='productos') cargarProductos();
  else if(pg==='historial') initHistorial();
  else if(pg==='reportes') cargarReportes();
  else if(pg==='fiados') { cargarClientes(); }
  else if(pg==='caja') cargarCaja();
  else if(pg==='config') cargarConfig();
  else if(pg==='ingreso') cargarMovimientos();
  else if(pg==='pos') { setTimeout(()=>$('pos-cod').focus(), 100); }
}

function navTo(page) {
  const el = document.querySelector(`[data-page="${page}"]`);
  if(el) nav(el);
}

// ── STATUS BAR ────────────────────────────────────────────
function updateStatusBar() {
  const now = new Date();
  const dias = ['Domingo','Lunes','Martes','Miercoles','Jueves','Viernes','Sabado'];
  const meses = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  $('sb-fecha').textContent = `${dias[now.getDay()]} ${now.getDate()} ${meses[now.getMonth()]} ${now.getFullYear()} ${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;
}
setInterval(updateStatusBar, 30000);
updateStatusBar();

fetch('/api/config').then(r=>r.json()).then(cfg => {
  if(cfg.nombre_negocio) $('sb-negocio').textContent = cfg.nombre_negocio;
});

// ── KEYBOARD SHORTCUTS ─────────────────────────────────────
document.addEventListener('keydown', e => {
  // Selección rápida de producto en lista POS con teclas 1-8
  if(posListaActual.length && !e.ctrlKey && !e.altKey && e.target.tagName!=='INPUT') {
    const n = parseInt(e.key);
    if(n >= 1 && n <= posListaActual.length) { posShowProd(posListaActual[n-1]); return; }
  }
  if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT'||e.target.tagName==='TEXTAREA') {
    if(e.key==='F5') { e.preventDefault(); resetPOS(); }
    if(e.key==='F10') { e.preventDefault(); confirmarVenta(); }
    return;
  }
  if(e.key==='F2') { e.preventDefault(); navTo('pos'); }
  if(e.key==='F3') { e.preventDefault(); openSearch(); }
  if(e.key==='F5') { e.preventDefault(); resetPOS(); }
  if(e.key==='F10') { e.preventDefault(); confirmarVenta(); }
  if(e.key==='F11') { e.preventDefault(); toggleFullscreen(); }
  if(e.key==='Escape') { closeModal(); posListaActual=[]; $('pos-result').innerHTML=''; }
});

function toggleDark() {
  const isDark = document.documentElement.getAttribute('data-theme')==='dark';
  document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
  $('dark-btn').textContent = isDark ? '🌙 Modo oscuro' : '☀️ Modo claro';
  localStorage.setItem('kiosco-theme', isDark ? 'light' : 'dark');
}
// Restaurar tema al cargar
(()=>{ const t=localStorage.getItem('kiosco-theme'); if(t==='dark'){document.documentElement.setAttribute('data-theme','dark');} })();

function toggleFullscreen() {
  if(!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(()=>{}); }
  else { document.exitFullscreen(); }
}

// ── DASHBOARD ─────────────────────────────────────────────
async function loadDashboard() {
  const d = await fetch('/api/dashboard').then(r=>r.json());
  const h = d.hoy;
  $('dash-fecha').textContent = '📅 ' + new Date().toLocaleDateString('es-AR',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
  $('s-total').textContent = pesos(h.total_hoy);
  $('s-transac').textContent = fmt(h.transacciones);
  $('s-ganancia').textContent = pesos(d.ganancia_hoy);
  $('s-stock-bajo').textContent = d.bajo_stock.length;

  // Chart semana
  const dias7 = [], totales7 = [], labels7 = [];
  const dayNames = ['Dom','Lun','Mar','Mie','Jue','Vie','Sab'];
  const semMap = {};
  d.semana.forEach(s => semMap[s.fecha] = s.total);
  const todayKey = new Date().toISOString().split('T')[0];
  for(let i=6;i>=0;i--) {
    const dd = new Date(); dd.setDate(dd.getDate()-i);
    const k = dd.toISOString().split('T')[0];
    labels7.push(i===0 ? 'HOY' : dayNames[dd.getDay()]);
    totales7.push(semMap[k]||0);
    dias7.push(i===0);
  }
  if(chartSemana) chartSemana.destroy();
  chartSemana = new Chart($('chart-semana'), {
    type:'bar',
    data:{
      labels:labels7,
      datasets:[{
        data:totales7,
        backgroundColor:dias7.map(t=>t?'#0057ff':'#f5c800'),
        borderRadius:6,borderSkipped:false
      }]
    },
    options:{responsive:true,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>pesos(c.raw)}}},
      scales:{y:{ticks:{callback:v=>pesos(v)},grid:{color:'rgba(0,0,0,.05)'}},x:{grid:{display:false}}}}
  });

  // Top productos
  const topEl = $('top-hoy');
  if(!d.top_productos.length) {
    topEl.innerHTML = '<div style="color:var(--muted);font-size:.78rem;text-align:center;padding:24px">Sin ventas hoy</div>';
  } else {
    const max = d.top_productos[0].monto;
    topEl.innerHTML = d.top_productos.map((p,i) => `
      <div class="top-item">
        <div class="top-num">${i+1}</div>
        <div class="top-name">${p.producto_nombre}</div>
        <div class="top-bar-wrap"><div class="top-bar" style="width:${(p.monto/max*100).toFixed(0)}%"></div></div>
        <div class="top-val">${pesos(p.monto)}</div>
      </div>`).join('');
  }

  // Bajo stock
  const bsEl = $('bajo-stock-list');
  if(!d.bajo_stock.length) {
    bsEl.innerHTML = '<div class="alert alert-ok">✅ Todo el stock esta en orden</div>';
  } else {
    bsEl.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Producto</th><th>Categoria</th><th>Stock actual</th><th>Minimo</th><th>Accion</th></tr></thead>
      <tbody>${d.bajo_stock.map(p=>`<tr>
        <td><strong>${p.nombre}</strong></td>
        <td><span class="badge badge-cat">${p.categoria}</span></td>
        <td class="s-${p.stock<=0?'low':'warn'}">⚠️ ${p.stock}</td>
        <td>${p.stock_minimo}</td>
        <td><button class="btn btn-sm btn-ghost" onclick="navTo('ingreso')">Reponer</button></td>
      </tr>`).join('')}</tbody></table></div>`;
  }
}

// ── POS ───────────────────────────────────────────────────
function posKeydown(e) {
  if(e.key==='Enter') { e.preventDefault(); posBuscar(); }
}

async function posBuscar() {
  const q = $('pos-cod').value.trim();
  if(!q) return;
  $('pos-prod-card').classList.remove('show');
  $('pos-notfound').style.display='none';
  $('venta-ok').classList.remove('show');
  const prod = await fetch('/api/producto/'+encodeURIComponent(q)).then(r=>r.json());
  if(prod.error) {
    // Try name search
    const lista = await fetch('/api/productos?q='+encodeURIComponent(q)).then(r=>r.json());
    if(lista.length===1) { posShowProd(lista[0]); }
    else if(lista.length>1) { posShowList(lista); }
    else { $('pos-notfound').style.display='block'; }
    return;
  }
  posShowProd(prod);
}

let posListaActual = [];
function posShowList(lista) {
  posListaActual = lista.slice(0,8);
  $('pos-result').innerHTML = `<div class="card" style="margin-bottom:14px">
    <div class="card-title">Selecciona un producto <span style="font-weight:400;color:var(--muted)">(presioná 1-${posListaActual.length} para elegir)</span></div>
    ${posListaActual.map((p,i)=>`<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick='posShowProd(${JSON.stringify(p).replace(/'/g,"&#39;")})'>
      <div style="width:22px;height:22px;border-radius:6px;background:var(--yellow);color:var(--dark);font-size:.7rem;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0">${i+1}</div>
      <div style="flex:1"><strong>${p.nombre}</strong> <span class="td-muted">${p.codigo}</span></div>
      <div style="display:flex;align-items:center;gap:12px"><span style="font-weight:700">${pesos(p.precio_venta)}</span><span class="badge ${p.stock>p.stock_minimo?'badge-ok':p.stock>0?'badge-warn':'badge-danger'}">${p.stock} u</span></div>
    </div>`).join('')}
  </div>`;
}

function posShowProd(prod) {
  $('pos-result').innerHTML = '';
  posProducto = prod;
  $('pos-pname').textContent = prod.nombre;
  $('pos-pcod').textContent = prod.codigo;
  $('pos-pstock').textContent = prod.stock;
  $('pos-pcat').textContent = prod.categoria;
  $('pos-pprice').textContent = pesos(prod.precio_venta);
  $('pos-cant').value = 1;
  $('pos-prod-card').classList.add('show');
  setTimeout(()=>$('pos-cant').focus(), 50);
}

function agregarCarrito() {
  if(!posProducto) return;
  const cant = parseInt($('pos-cant').value)||1;
  if(cant < 1) { toast('Cantidad invalida','err'); return; }
  const stockDisp = posProducto.stock - cart.filter(i=>i.id===posProducto.id).reduce((a,i)=>a+i.cant,0);
  if(cant > stockDisp) { toast(`Stock insuficiente. Disponible: ${stockDisp}`,'err'); return; }
  const exist = cart.find(i=>i.id===posProducto.id);
  if(exist) { exist.cant += cant; exist.sub = exist.cant * exist.precio; }
  else { cart.push({id:posProducto.id,nombre:posProducto.nombre,cant,precio:posProducto.precio_venta,sub:cant*posProducto.precio_venta}); }
  renderCart();
  $('pos-cod').value='';
  $('pos-cod').focus();
  $('pos-prod-card').classList.remove('show');
  $('pos-result').innerHTML='';
  posProducto=null;
  toast(`✓ ${cant}x ${exist?exist.nombre:cart[cart.length-1].nombre} agregado`,'ok');
}

function quitarItem(id) {
  cart = cart.filter(i=>i.id!==id);
  renderCart();
}

function cambiarCantCart(id, val) {
  const n = parseInt(val);
  if(!n || n < 1) return;
  const item = cart.find(i=>i.id===id);
  if(!item) return;
  item.cant = n;
  item.sub = n * item.precio;
  recalcTotal();
}

function renderCart() {
  const el = $('cart-items');
  $('cart-count').textContent = `${cart.length} item${cart.length!==1?'s':''}`;
  if(!cart.length) {
    el.innerHTML = '<div class="cart-empty">El carrito esta vacio<br>Escaneá un producto para empezar</div>';
    $('cart-sub').textContent='$0'; $('cart-total').textContent='$0';
    return;
  }
  el.innerHTML = cart.map(i=>`
    <div class="cart-item">
      <div style="flex:1">
        <div class="cart-item-name">${i.nombre}</div>
        <div class="cart-item-qty">${pesos(i.precio)} c/u</div>
      </div>
      <input type="number" min="1" value="${i.cant}"
        style="width:52px;text-align:center;padding:4px 6px;font-size:.8rem;font-weight:700;border:1.5px solid var(--border);border-radius:7px;margin:0 6px"
        onchange="cambiarCantCart(${i.id},this.value)" onclick="this.select()">
      <div class="cart-item-price" style="min-width:64px;text-align:right">${pesos(i.sub)}</div>
      <button class="btn btn-icon btn-ghost" style="font-size:.75rem;margin-left:6px;flex-shrink:0" onclick="quitarItem(${i.id})">✕</button>
    </div>`).join('');
  recalcTotal();
}

function recalcTotal() {
  const sub = cart.reduce((a,i)=>a+i.sub,0);
  const desc = parseFloat($('cart-desc').value)||0;
  $('cart-sub').textContent = pesos(sub);
  $('cart-total').textContent = pesos(sub-desc);
}

function setMetodo(m) {
  metodoActual = m;
  $('method-ef').classList.toggle('active',m==='efectivo');
  $('method-mp').classList.toggle('active',m==='mp');
}

async function confirmarVenta() {
  if(!cart.length) { toast('El carrito está vacío','err'); return; }
  const desc = parseFloat($('cart-desc').value)||0;
  const r = await fetch('/api/venta',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({items:cart.map(i=>({producto_id:i.id,cantidad:i.cant})),metodo_pago:metodoActual,descuento:desc})}).then(r=>r.json());
  if(r.ok) {
    lastTicketData = {items:[...cart], total:r.total, desc, metodo:metodoActual, vid:r.venta_id, negocio:$('sb-negocio').textContent};
    $('vok-total').textContent = pesos(r.total);
    $('vok-detalle').textContent = `${cart.length} producto${cart.length!==1?'s':''} · ${metodoActual==='mp'?'Mercado Pago':'Efectivo'} · Venta #${r.venta_id}`;
    $('venta-ok').classList.add('show');
    $('pos-prod-card').classList.remove('show');
    cart=[]; renderCart();
    toast(r.msg,'ok');
  } else {
    toast(r.msg,'err');
  }
}

function nuevaVenta() {
  $('venta-ok').classList.remove('show');
  resetPOS();
}

let lastTicketData = null;

function imprimirTicket() {
  if(!lastTicketData) return;
  const {items, total, desc, metodo, vid, negocio} = lastTicketData;
  const ahora = new Date();
  const fecha = ahora.toLocaleDateString('es-AR');
  const hora = ahora.toLocaleTimeString('es-AR', {hour:'2-digit',minute:'2-digit'});
  const sep = '─'.repeat(32);
  const lineas = items.map(i=>{
    const nom = i.nombre.length>20 ? i.nombre.slice(0,19)+'.' : i.nombre.padEnd(20);
    const pr = pesos(i.sub).padStart(10);
    return `${nom}${pr}\n  ${i.cant} x ${pesos(i.precio)}`;
  }).join('\n');
  const win = window.open('','_blank','width=400,height=600');
  win.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8">
  <title>Ticket #${vid}</title>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Courier New',monospace;font-size:12px;width:72mm;padding:4mm;color:#000}
    .center{text-align:center} .bold{font-weight:700} .line{border-top:1px dashed #000;margin:6px 0}
    .row{display:flex;justify-content:space-between;margin:2px 0}
    .total-row{display:flex;justify-content:space-between;font-size:15px;font-weight:700;margin:4px 0}
    @media print{@page{margin:0;size:72mm auto}body{padding:2mm}}
  </style></head><body>
  <div class="center bold" style="font-size:15px;margin-bottom:2px">${negocio}</div>
  <div class="center" style="font-size:10px">Ticket de venta</div>
  <div class="line"></div>
  <div class="row"><span>Fecha: ${fecha}</span><span>Hora: ${hora}</span></div>
  <div class="row"><span>Venta #${vid}</span><span>${metodo==='mp'?'Mercado Pago':'Efectivo'}</span></div>
  <div class="line"></div>
  ${items.map(i=>`<div class="row"><span>${i.nombre.slice(0,22)}</span><span>${pesos(i.sub)}</span></div>
  <div style="font-size:10px;color:#555;margin-bottom:3px;padding-left:4px">${i.cant} x ${pesos(i.precio)}</div>`).join('')}
  <div class="line"></div>
  ${desc>0?`<div class="row"><span>Subtotal</span><span>${pesos(total+desc)}</span></div>
  <div class="row"><span>Descuento</span><span>-${pesos(desc)}</span></div>`:''}
  <div class="total-row"><span>TOTAL</span><span>${pesos(total)}</span></div>
  <div class="line"></div>
  <div class="center" style="font-size:10px;margin-top:6px">¡Gracias por su compra!</div>
  <script>window.onload=()=>{window.print();}<\/script>
  </body></html>`);
  win.document.close();
}

function resetPOS() {
  cart=[]; posProducto=null;
  $('pos-cod').value='';
  $('pos-result').innerHTML='';
  $('pos-prod-card').classList.remove('show');
  $('pos-notfound').style.display='none';
  $('venta-ok').classList.remove('show');
  $('cart-desc').value='0';
  renderCart();
  $('pos-cod').focus();
}

// ── STOCK ─────────────────────────────────────────────────
async function cargarStock() {
  const q=$('stock-q')?.value||'', cat=$('stock-cat')?.value||'', fil=$('stock-filtro')?.value||'';
  let prods = await fetch(`/api/productos?q=${encodeURIComponent(q)}&cat=${encodeURIComponent(cat)}`).then(r=>r.json());
  if(fil==='bajo') prods=prods.filter(p=>p.stock<=p.stock_minimo&&p.stock>0);
  else if(fil==='sin') prods=prods.filter(p=>p.stock<=0);
  const tbody=$('stock-tbody');
  if(!prods.length){tbody.innerHTML='<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:28px">Sin productos</td></tr>';return;}
  tbody.innerHTML=prods.map(p=>{
    const pct=Math.min((p.stock/Math.max(p.stock_minimo*3,1))*100,100);
    const color=p.stock<=0?'var(--red)':p.stock<=p.stock_minimo?'#c47d00':'var(--green)';
    const cls=p.stock<=0?'s-low':p.stock<=p.stock_minimo?'s-warn':'s-ok';
    const margen=p.precio_costo>0?((p.precio_venta-p.precio_costo)/p.precio_venta*100).toFixed(0):'—';
    return `<tr>
      <td class="td-muted">${p.codigo}</td>
      <td><strong>${p.nombre}</strong></td>
      <td><span class="badge badge-cat">${p.categoria}</span></td>
      <td class="td-muted">${pesos(p.precio_costo)}</td>
      <td><strong>${pesos(p.precio_venta)}</strong></td>
      <td>${p.precio_costo>0?`<span style="color:var(--green);font-weight:700">${margen}%</span>`:'—'}</td>
      <td><div class="stock-visual"><div class="stock-bar-wrap"><div class="stock-bar" style="width:${pct}%;background:${color}"></div></div><span class="${cls}">${p.stock}</span></div></td>
      <td>${p.stock<=0?'<span class="badge badge-danger">SIN STOCK</span>':p.stock<=p.stock_minimo?'<span class="badge badge-warn">⚠️ BAJO</span>':'<span class="badge badge-ok">✓ OK</span>'}</td>
    </tr>`;
  }).join('');
}

// ── INGRESO ───────────────────────────────────────────────
async function ingrBuscar() {
  const cod=$('ing-cod').value.trim();
  if(!cod) return;
  $('ingr-prod').style.display='none'; $('ingr-notfound').style.display='none';
  const prod = await fetch('/api/producto/'+encodeURIComponent(cod)).then(r=>r.json());
  if(prod.error) { $('ingr-notfound').style.display='block'; return; }
  ingrProducto=prod;
  $('ingr-nombre').textContent=prod.nombre;
  $('ingr-stock').textContent=prod.stock;
  $('ingr-prod').style.display='block';
}

async function ingrConfirmar() {
  if(!ingrProducto) return;
  const cant=parseInt($('ingr-cant').value)||1;
  const motivo=$('ingr-motivo').value;
  const r=await fetch('/api/stock/entrada',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({producto_id:ingrProducto.id,cantidad:cant,motivo})}).then(r=>r.json());
  if(r.ok){
    toast(r.msg,'ok');
    $('ingr-stock').textContent=r.nuevo_stock;
    $('ingr-cant').value=1;
    $('ing-cod').value='';
    $('ingr-prod').style.display='none';
    ingrProducto=null;
    cargarMovimientos();
  } else toast(r.msg,'err');
}

async function cargarMovimientos() {
  const movs = await fetch('/api/movimientos?limit=50').then(r=>r.json());
  const tbody=$('mov-tbody');
  if(!tbody) return;
  if(!movs.length){tbody.innerHTML='<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:16px">Sin movimientos registrados</td></tr>';return;}
  tbody.innerHTML = movs.map(m=>`<tr>
    <td class="td-muted">${m.fecha?.slice(0,16)||'-'}</td>
    <td><strong>${m.producto_nombre}</strong></td>
    <td><span class="badge ${m.tipo==='entrada'?'badge-ok':'badge-danger'}">${m.tipo==='entrada'?'▲ Entrada':'▼ Salida'}</span></td>
    <td style="text-align:center;font-weight:700">${m.tipo==='entrada'?'+':'−'}${m.cantidad}</td>
    <td class="td-muted">${m.stock_anterior??'-'}</td>
    <td style="font-weight:700">${m.stock_nuevo??'-'}</td>
    <td class="td-muted">${m.motivo||'-'}</td>
  </tr>`).join('');
}

// ── PRODUCTOS ─────────────────────────────────────────────
async function cargarProductos() {
  const q=$('prod-q')?.value||'', cat=$('prod-cat')?.value||'';
  const prods=await fetch(`/api/productos?q=${encodeURIComponent(q)}&cat=${encodeURIComponent(cat)}`).then(r=>r.json());
  const tbody=$('prod-tbody');
  if(!prods.length){tbody.innerHTML='<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:28px">Sin productos</td></tr>';return;}
  tbody.innerHTML=prods.map(p=>{
    const margen=p.precio_costo>0?((p.precio_venta-p.precio_costo)/p.precio_venta*100).toFixed(0)+'%':'—';
    const cls=p.stock<=0?'s-low':p.stock<=p.stock_minimo?'s-warn':'s-ok';
    return `<tr>
      <td class="td-muted">${p.codigo}</td>
      <td><strong>${p.nombre}</strong></td>
      <td><span class="badge badge-cat">${p.categoria}</span></td>
      <td class="td-muted">${pesos(p.precio_costo)}</td>
      <td><strong>${pesos(p.precio_venta)}</strong></td>
      <td>${margen}</td>
      <td class="${cls}">${p.stock}</td>
      <td class="td-muted">${p.stock_minimo}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm btn-ghost" onclick='openModal(${JSON.stringify(p).replace(/'/g,"&#39;")})'>✏️ Editar</button>
        <button class="btn btn-sm btn-red" style="margin-left:6px" onclick="eliminarProducto(${p.id},'${p.nombre.replace(/'/g,"\\'")}')">🗑</button>
      </td>
    </tr>`;
  }).join('');
}

function openModal(prod=null) {
  modalMode = prod ? 'edit' : 'new';
  editId = prod ? prod.id : null;
  $('modal-title').textContent = prod ? 'Editar Producto' : 'Nuevo Producto';
  $('modal-save-btn').textContent = prod ? '✓ Guardar Cambios' : '✓ Guardar';
  $('m-cod').value=prod?.codigo||''; $('m-cod').disabled=!!prod;
  $('m-nombre').value=prod?.nombre||'';
  $('m-cat').value=prod?.categoria||'Bebidas';
  $('m-costo').value=prod?.precio_costo||'';
  $('m-venta').value=prod?.precio_venta||'';
  $('m-stock').value=prod?.stock||'0';
  $('m-minimo').value=prod?.stock_minimo||'5';
  $('modal-bg').classList.add('show');
  setTimeout(()=>(prod?$('m-nombre'):$('m-cod')).focus(),100);
}

function closeModal() { $('modal-bg').classList.remove('show'); }

async function guardarProducto() {
  const d = {
    codigo:$('m-cod').value.trim(), nombre:$('m-nombre').value.trim(),
    categoria:$('m-cat').value,
    precio_costo:parseFloat($('m-costo').value)||0,
    precio_venta:parseFloat($('m-venta').value)||0,
    stock:parseInt($('m-stock').value)||0,
    stock_minimo:parseInt($('m-minimo').value)||5
  };
  if(!d.nombre||!d.precio_venta){toast('Completá nombre y precio de venta','err');return;}
  if(modalMode==='new'&&!d.codigo){toast('Ingresá el codigo de barras','err');return;}
  const url=modalMode==='edit'?`/api/productos/${editId}`:'/api/productos';
  const method=modalMode==='edit'?'PUT':'POST';
  const r=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');closeModal();cargarProductos();}
  else toast(r.msg,'err');
}

async function eliminarProducto(id, nombre) {
  if(!confirm(`¿Eliminár "${nombre}"? Esta accion no se puede deshacer.`)) return;
  const r=await fetch(`/api/productos/${id}`,{method:'DELETE'}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');cargarProductos();}
  else toast(r.msg,'err');
}

// ── HISTORIAL ─────────────────────────────────────────────
function initHistorial() {
  const hoy=new Date().toISOString().split('T')[0];
  const mesInicio=new Date(); mesInicio.setDate(1);
  if(!$('hist-desde').value) $('hist-desde').value=mesInicio.toISOString().split('T')[0];
  if(!$('hist-hasta').value) $('hist-hasta').value=hoy;
  cargarHistorial();
}

async function cargarHistorial() {
  const desde=$('hist-desde').value, hasta=$('hist-hasta').value, metodo=$('hist-metodo').value;
  const ventas=await fetch(`/api/ventas?desde=${desde}&hasta=${hasta}&metodo=${metodo}&limit=200`).then(r=>r.json());
  const tbody=$('hist-tbody');
  if(!ventas.length){tbody.innerHTML='<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:28px">Sin ventas en el periodo</td></tr>';return;}
  tbody.innerHTML=ventas.map(v=>`<tr style="opacity:${v.anulada?'.45':'1'}">
    <td class="td-muted">#${v.id}</td>
    <td>${v.fecha}</td>
    <td class="td-muted">${v.hora?.slice(0,5)||'-'}</td>
    <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${v.items||''}">${v.items||'-'}</td>
    <td><strong>${pesos(v.total)}</strong></td>
    <td><span class="badge ${v.metodo_pago==='mp'?'badge-mp':'badge-ef'}">${v.metodo_pago==='mp'?'📱 MP':'💵 Efectivo'}</span></td>
    <td>${v.anulada?'<span class="badge badge-danger">ANULADA</span>':'<span class="badge badge-ok">OK</span>'}</td>
    <td>${!v.anulada?`<button class="btn btn-sm btn-red" onclick="anularVenta(${v.id})">Anular</button>`:''}</td>
  </tr>`).join('');
}

async function anularVenta(id) {
  if(!confirm(`¿Anular venta #${id}? Se restaurará el stock.`)) return;
  const r=await fetch(`/api/ventas/${id}`,{method:'DELETE'}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');cargarHistorial();}
  else toast(r.msg,'err');
}

function exportarCSV() {
  const desde=$('hist-desde')?.value||new Date().toISOString().slice(0,7)+'-01';
  const hasta=$('hist-hasta')?.value||new Date().toISOString().split('T')[0];
  window.location.href=`/api/export/csv?desde=${desde}&hasta=${hasta}`;
}

// ── REPORTES ──────────────────────────────────────────────
function setPeriodo(el) {
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  periodoActual=el.dataset.periodo;
  cargarReportes();
}

async function cargarReportes() {
  const d=await fetch(`/api/reportes?periodo=${periodoActual}`).then(r=>r.json());
  const r=d.resumen;
  $('r-total').textContent=pesos(r.total_ventas);
  $('r-transac').textContent=fmt(r.transacciones);
  $('r-ganancia').textContent=pesos(d.ganancia_total);
  $('r-dias').textContent=fmt(r.dias_activos);

  // Chart por dia
  if(chartRep) chartRep.destroy();
  chartRep=new Chart($('chart-rep'),{
    type:'bar',
    data:{
      labels:d.por_dia.map(x=>x.fecha.slice(5)),
      datasets:[{data:d.por_dia.map(x=>x.total),backgroundColor:'#f5c800',borderRadius:6,borderSkipped:false}]
    },
    options:{responsive:true,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>pesos(c.raw)}}},
      scales:{y:{ticks:{callback:v=>pesos(v)},grid:{color:'rgba(0,0,0,.05)'}},x:{grid:{display:false}}}}
  });

  // Chart metodos
  if(chartMetodos) chartMetodos.destroy();
  chartMetodos=new Chart($('chart-metodos'),{
    type:'doughnut',
    data:{
      labels:['Efectivo','Mercado Pago'],
      datasets:[{data:[r.efectivo,r.mp],backgroundColor:['#00c566','#009ee3'],borderWidth:0}]
    },
    options:{responsive:true,cutout:'65%',plugins:{legend:{position:'bottom'},tooltip:{callbacks:{label:c=>pesos(c.raw)}}}}
  });

  // Chart categorias
  const cats = await fetch(`/api/rentabilidad?desde=${d.fd}&hasta=${d.fh}`).then(r=>r.json());
  if(cats.length && $('chart-categorias')) {
    if(chartCats) chartCats.destroy();
    const COLORES = ['#f5c800','#0057ff','#00c566','#ff3b30','#009ee3','#9c27b0','#ff9800'];
    chartCats = new Chart($('chart-categorias'), {
      type:'bar',
      data:{
        labels: cats.map(c=>c.categoria),
        datasets:[
          {label:'Ventas',data:cats.map(c=>c.monto),backgroundColor:'#f5c800',borderRadius:5,borderSkipped:false},
          {label:'Ganancia',data:cats.map(c=>Math.max(c.ganancia,0)),backgroundColor:'#00c566',borderRadius:5,borderSkipped:false}
        ]
      },
      options:{responsive:true,plugins:{legend:{position:'top'},tooltip:{callbacks:{label:c=>c.dataset.label+': '+pesos(c.raw)}}},
        scales:{y:{ticks:{callback:v=>pesos(v)},grid:{color:'rgba(0,0,0,.05)'}},x:{grid:{display:false}}}}
    });
  }

  // Tabla productos
  const total=r.total_ventas||1;
  $('rep-prod-tbody').innerHTML=d.por_producto.map((p,i)=>`<tr>
    <td class="td-muted">${i+1}</td>
    <td><strong>${p.producto_nombre}</strong></td>
    <td>${fmt(p.unidades)}</td>
    <td>${pesos(p.monto)}</td>
    <td style="color:var(--green);font-weight:700">${pesos(p.ganancia)}</td>
    <td><div style="display:flex;align-items:center;gap:8px">
      <div style="flex:1;height:5px;background:var(--bg);border-radius:3px;min-width:60px">
        <div style="width:${(p.monto/total*100).toFixed(0)}%;height:100%;background:var(--yellow);border-radius:3px"></div>
      </div>
      <span class="td-muted">${(p.monto/total*100).toFixed(1)}%</span>
    </div></td>
  </tr>`).join('');
}

// ── FIADOS / CLIENTES ────────────────────────────────────
let clienteActual = null;

function toggleNuevoCliente() {
  const f=$('nuevo-cliente-form'); f.style.display=f.style.display==='none'?'block':'none';
}

async function crearCliente() {
  const nombre=$('nc-nombre').value.trim(), tel=$('nc-tel').value.trim();
  if(!nombre){toast('Ingresá el nombre del cliente','err');return;}
  const r=await fetch('/api/clientes',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({nombre,telefono:tel})}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');toggleNuevoCliente();$('nc-nombre').value='';$('nc-tel').value='';cargarClientes();}
  else toast(r.msg,'err');
}

async function cargarClientes() {
  const q=$('cl-q')?.value||'';
  const cls=await fetch(`/api/clientes?q=${encodeURIComponent(q)}`).then(r=>r.json());
  const el=$('clientes-list');
  if(!cls.length){el.innerHTML='<div style="color:var(--muted);font-size:.8rem;text-align:center;padding:24px">Sin clientes registrados</div>';return;}
  el.innerHTML=cls.map(c=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="verCuenta(${c.id})">
    <div>
      <div style="font-weight:700;font-size:.85rem">${c.nombre}</div>
      ${c.telefono?`<div style="font-size:.7rem;color:var(--muted)">${c.telefono}</div>`:''}
    </div>
    <span class="badge ${c.saldo>0?'badge-danger':c.saldo<0?'badge-ok':'badge-cat'}">${c.saldo>0?'Debe '+pesos(c.saldo):c.saldo<0?'A favor '+pesos(-c.saldo):'Sin deuda'}</span>
  </div>`).join('');
}

async function verCuenta(id) {
  const d=await fetch(`/api/clientes/${id}`).then(r=>r.json());
  if(!d||d.error) return;
  clienteActual=d;
  $('cuenta-titulo').textContent=`Cuenta: ${d.nombre}`;
  $('cuenta-saldo').textContent=pesos(d.saldo);
  $('cuenta-saldo').style.color=d.saldo>0?'var(--red)':d.saldo<0?'var(--green)':'var(--muted)';
  $('cuenta-detalle').style.display='block';
  $('cuenta-movs').innerHTML=!d.movimientos.length?'<div style="color:var(--muted);font-size:.78rem;text-align:center;padding:16px">Sin movimientos</div>':
    d.movimientos.map(m=>`<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border);font-size:.78rem">
      <div><span class="badge ${m.tipo==='cargo'?'badge-danger':'badge-ok'}" style="margin-right:6px">${m.tipo==='cargo'?'Fiado':'Pago'}</span>${m.descripcion||'-'}</div>
      <div style="font-weight:700">${m.tipo==='cargo'?'+':'-'}${pesos(m.monto)}</div>
    </div>`).join('');
}

async function registrarFiado() {
  if(!clienteActual) return;
  const monto=parseFloat($('fiado-monto').value)||0;
  if(!monto){toast('Ingresá el monto','err');return;}
  const r=await fetch('/api/clientes/fiado',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({cliente_id:clienteActual.id,monto,desc:$('fiado-desc').value||'Fiado'})}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');$('fiado-monto').value='';$('fiado-desc').value='';verCuenta(clienteActual.id);cargarClientes();}
  else toast(r.msg,'err');
}

async function registrarPago() {
  if(!clienteActual) return;
  const monto=parseFloat($('pago-monto').value)||0;
  if(!monto){toast('Ingresá el monto','err');return;}
  const r=await fetch('/api/clientes/pago',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({cliente_id:clienteActual.id,monto,desc:$('pago-desc').value||'Pago'})}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');$('pago-monto').value='';$('pago-desc').value='';verCuenta(clienteActual.id);cargarClientes();}
  else toast(r.msg,'err');
}

// ── CAJA ──────────────────────────────────────────────────
async function cargarCaja() {
  const d=await fetch('/api/caja').then(r=>r.json());
  const sc=$('caja-status-card');
  const fa=$('caja-form-apertura'), fc=$('caja-form-cierre');

  if(d.abierta) {
    const ap=d.apertura;
    sc.innerHTML=`<div class="caja-status abierta">
      <div class="caja-icon">🟢</div>
      <div class="caja-label">Caja ABIERTA</div>
      <div class="caja-sub">Abierta a las ${ap.hora?.slice(0,5)} con ${pesos(ap.monto_inicial)} de fondo inicial</div>
    </div>`;
    fa.style.display='none';
    // Load today totals for closing
    const rep=await fetch('/api/reportes?periodo=hoy').then(r=>r.json());
    const rs=rep.resumen;
    $('caja-resumen-cierre').innerHTML=`
      <div class="g2">
        <div class="stat yellow" style="margin:0"><div class="stat-icon">💰</div><div class="stat-val">${pesos(rs.total_ventas)}</div><div class="stat-label">Total vendido</div></div>
        <div class="stat blue" style="margin:0"><div class="stat-icon">🧾</div><div class="stat-val">${rs.transacciones}</div><div class="stat-label">Transacciones</div></div>
        <div class="stat green" style="margin:0"><div class="stat-icon">💵</div><div class="stat-val">${pesos(rs.efectivo)}</div><div class="stat-label">En efectivo</div></div>
        <div class="stat red" style="margin:0"><div class="stat-icon">📱</div><div class="stat-val">${pesos(rs.mp)}</div><div class="stat-label">Mercado Pago</div></div>
      </div>
    `;
    fc.style.display='block';
    $('sb-caja-status').textContent='Caja: Abierta ✓';
  } else if(d.cierre) {
    const ci=d.cierre;
    sc.innerHTML=`<div class="caja-status cerrada">
      <div class="caja-icon">🔴</div>
      <div class="caja-label">Caja CERRADA</div>
      <div class="caja-sub">Cerrada a las ${ci.hora?.slice(0,5)} · Total: ${pesos(ci.total_ventas)} · ${ci.cantidad_ventas} ventas</div>
      <button class="btn btn-green" style="margin-top:16px" onclick="reabrirCaja()">🟢 Reabrir Caja</button>
    </div>`;
    fa.style.display='none'; fc.style.display='none';
    $('sb-caja-status').textContent='Caja: Cerrada';
  } else {
    sc.innerHTML=`<div class="caja-status cerrada">
      <div class="caja-icon">⚪</div>
      <div class="caja-label">Caja no abierta hoy</div>
      <div class="caja-sub">Abri la caja para comenzar a registrar ventas del dia</div>
    </div>`;
    fa.style.display='block'; fc.style.display='none';
    $('sb-caja-status').textContent='Caja: Sin abrir';
  }
}

function reabrirCaja() {
  $('caja-form-apertura').style.display='block';
}

async function abrirCaja() {
  const monto=parseFloat($('caja-monto').value)||0;
  const obs=$('caja-obs-abr').value;
  const r=await fetch('/api/caja/abrir',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({monto_inicial:monto,obs})}).then(r=>r.json());
  if(r.ok){toast(r.msg,'ok');cargarCaja();}
  else toast(r.msg,'err');
}

async function cerrarCaja() {
  if(!confirm('¿Cerrar la caja del dia?')) return;
  const obs=$('caja-obs-cie').value;
  const r=await fetch('/api/caja/cerrar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({obs})}).then(r=>r.json());
  if(r.ok){toast('Caja cerrada correctamente','ok');cargarCaja();}
  else toast(r.msg,'err');
}

// ── CONFIG ────────────────────────────────────────────────
async function cargarConfig() {
  const c=await fetch('/api/config').then(r=>r.json());
  $('cfg-nombre').value=c.nombre_negocio||'';
  $('cfg-tel').value=c.telefono||'';
  $('cfg-dir').value=c.direccion||'';
}

async function guardarConfig() {
  const data={nombre_negocio:$('cfg-nombre').value,telefono:$('cfg-tel').value,direccion:$('cfg-dir').value};
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json());
  if(r.ok){toast('Configuracion guardada','ok');$('sb-negocio').textContent=data.nombre_negocio;}
  else toast('Error al guardar','err');
}

// ── BUSCADOR GLOBAL ──────────────────────────────────────
function openSearch() {
  $('search-bg').classList.add('show');
  setTimeout(()=>$('global-q').focus(),100);
}
function closeSearch() { $('search-bg').classList.remove('show'); $('global-q').value=''; $('global-results').innerHTML=''; }

async function globalSearch() {
  const q = $('global-q').value.trim();
  if(q.length < 2) { $('global-results').innerHTML=''; return; }
  const prods = await fetch(`/api/productos?q=${encodeURIComponent(q)}`).then(r=>r.json());
  let html = '';
  if(prods.length) {
    html += `<div style="font-size:.6rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);padding:6px 0 4px">Productos (${prods.length})</div>`;
    html += prods.slice(0,6).map(p=>`<div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="closeSearch();navTo('pos');setTimeout(()=>{$('pos-cod').value='${p.codigo}';posBuscar()},200)">
      <span class="badge badge-cat">${p.categoria}</span>
      <span style="flex:1;font-weight:600">${p.nombre}</span>
      <span style="font-weight:700">${pesos(p.precio_venta)}</span>
      <span class="badge ${p.stock>p.stock_minimo?'badge-ok':p.stock>0?'badge-warn':'badge-danger'}">${p.stock} u</span>
    </div>`).join('');
  }
  if(!html) html = '<div style="text-align:center;color:var(--muted);padding:24px;font-size:.82rem">Sin resultados para "'+q+'"</div>';
  $('global-results').innerHTML = html;
}

// ── IMPORTADOR CSV ────────────────────────────────────────
function toggleImportCSV() {
  const p = $('import-csv-panel');
  p.style.display = p.style.display==='none' ? 'block' : 'none';
}

function leerCSV(input) {
  const f = input.files[0];
  if(!f) return;
  const reader = new FileReader();
  reader.onload = e => { $('csv-input').value = e.target.result; };
  reader.readAsText(f, 'UTF-8');
}

async function importarCSV() {
  const csv = $('csv-input').value.trim();
  if(!csv) { toast('Pegá o cargá un archivo CSV primero','err'); return; }
  const r = await fetch('/api/import/precios',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({csv})}).then(r=>r.json());
  const resEl = $('import-result');
  if(r.ok) {
    resEl.innerHTML = `<div class="alert alert-ok">✅ <strong>${r.actualizados} productos actualizados.</strong>${r.errores.length?` ${r.errores.length} con error: ${r.errores.slice(0,3).join(', ')}`:''}</div>`;
    if(r.actualizados > 0) cargarProductos();
    toast(`${r.actualizados} precios actualizados`,'ok');
  } else {
    resEl.innerHTML = `<div class="alert alert-warn">❌ Error al importar</div>`;
  }
}

// ── BACKUP ───────────────────────────────────────────────
function descargarBackup() {
  window.location.href='/api/backup';
  toast('Descargando backup...','ok');
}

// ── NOTIFICACIÓN STOCK BAJO AL INICIO ────────────────────
async function checkStockAlInicio() {
  const d = await fetch('/api/dashboard').then(r=>r.json());
  if(d.bajo_stock && d.bajo_stock.length > 0) {
    const lista = d.bajo_stock.map(p=>`• ${p.nombre} — ${p.stock} unidad${p.stock!==1?'es':''}${p.stock===0?' (SIN STOCK)':''}`).join('\n');
    const modal = document.createElement('div');
    modal.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    modal.innerHTML=`<div style="background:#fff;border-radius:16px;padding:28px;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2)">
      <div style="font-size:1.5rem;margin-bottom:6px">⚠️</div>
      <div style="font-size:1rem;font-weight:900;margin-bottom:4px;color:#1a1200">Stock bajo al iniciar</div>
      <div style="font-size:.75rem;color:#8a7d60;margin-bottom:14px">${d.bajo_stock.length} producto${d.bajo_stock.length!==1?'s':''} necesitan reposición</div>
      <div style="background:#fff8e6;border:1px solid #f5c800;border-radius:9px;padding:12px;font-size:.75rem;font-family:'Courier New',monospace;white-space:pre;line-height:1.8">${lista}</div>
      <div style="display:flex;gap:10px;margin-top:16px">
        <button onclick="this.closest('[style]').remove();navTo('ingreso')" style="flex:1;padding:10px;background:#1a1200;color:#fff;border:none;border-radius:9px;font-weight:700;cursor:pointer;font-size:.82rem">Ir a Ingreso</button>
        <button onclick="this.closest('[style]').remove()" style="padding:10px 16px;background:#f5f0e8;border:1.5px solid #e0d8c8;border-radius:9px;font-weight:700;cursor:pointer;font-size:.82rem">Cerrar</button>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }
}

// ── INIT ──────────────────────────────────────────────────
loadDashboard();
setTimeout(checkStockAlInicio, 1500);
// Init historial dates
const hoy=new Date().toISOString().split('T')[0];
const mesInicio=new Date(); mesInicio.setDate(1);
$('hist-desde').value=mesInicio.toISOString().split('T')[0];
$('hist-hasta').value=hoy;
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def run():
    init_db()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"""
╔══════════════════════════════════════════╗
║     KIOSCO DIGITAL v2.0 Professional    ║
╠══════════════════════════════════════════╣
║  Sistema corriendo en: {url:<19}║
║  Base de datos: kiosco.db               ║
║  Ctrl+C para detener                    ║
╚══════════════════════════════════════════╝
""")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSistema detenido.")
        server.server_close()

if __name__ == "__main__":
    run()
