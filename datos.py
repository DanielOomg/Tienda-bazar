"""Acceso a datos: todas las consultas SQL del bazar."""
import json
import db


# ---------- Categorías ----------
def listar_categorias():
    return db.consultar("SELECT id_categoria, nombre FROM categorias ORDER BY nombre")


# ---------- Productos ----------
def listar_productos(busqueda=""):
    return db.consultar(
        """SELECT p.id_producto, p.nombre, p.precio, p.stock, p.unidad_medida, p.activo,
                  p.id_categoria, c.nombre AS categoria
           FROM productos p JOIN categorias c ON c.id_categoria = p.id_categoria
           WHERE p.nombre LIKE %s OR c.nombre LIKE %s
           ORDER BY p.id_producto""",
        (f"%{busqueda}%", f"%{busqueda}%"),
    )


def buscar_productos_venta(texto, limite=8):
    """Productos activos que coinciden con lo escrito, para elegir en la venta."""
    if not texto:
        return []
    return db.consultar(
        """SELECT id_producto, nombre, precio, stock, unidad_medida
           FROM productos WHERE activo = 1 AND nombre LIKE %s
           ORDER BY nombre LIMIT %s""",
        (f"%{texto}%", limite),
    )


def crear_producto(nombre, precio, stock, unidad_medida, id_categoria):
    return db.ejecutar(
        "INSERT INTO productos (nombre, precio, stock, unidad_medida, id_categoria) VALUES (%s,%s,%s,%s,%s)",
        (nombre, precio, stock, unidad_medida, id_categoria),
    )


def actualizar_producto(id_producto, nombre, precio, stock, unidad_medida, id_categoria):
    return db.ejecutar(
        "UPDATE productos SET nombre=%s, precio=%s, stock=%s, unidad_medida=%s, id_categoria=%s WHERE id_producto=%s",
        (nombre, precio, stock, unidad_medida, id_categoria, id_producto),
    )


def eliminar_producto(id_producto):
    return db.ejecutar("DELETE FROM productos WHERE id_producto=%s", (id_producto,))


# ---------- Ventas ----------
def registrar_venta(items, metodo_pago, monto_recibido):
    """items: [{"id_producto": 1, "cantidad": 1.5}, ...]. monto_recibido es None si es tarjeta."""
    resultado = db.llamar_procedimiento(
        "sp_registrar_venta", (json.dumps(items), metodo_pago, monto_recibido)
    )
    return resultado[0] if resultado else None


def anular_venta(id_pedido):
    return db.llamar_procedimiento("sp_anular_venta", (id_pedido,))


def listar_pedidos():
    return db.consultar("SELECT * FROM v_pedidos_resumen ORDER BY id_pedido DESC LIMIT 50")


def listar_detalle(id_pedido):
    return db.consultar(
        """SELECT pr.nombre, d.cantidad, pr.unidad_medida, d.precio_unitario,
                  d.cantidad * d.precio_unitario AS subtotal
           FROM detalle_pedido d JOIN productos pr ON pr.id_producto = d.id_producto
           WHERE d.id_pedido = %s ORDER BY d.id_detalle""",
        (id_pedido,),
    )
