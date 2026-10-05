"""Interfaz Flet: vistas de Productos y Vender (punto de venta de bazar)."""
import flet as ft
import datos

# Compatibilidad entre versiones de Flet
Option = getattr(ft, "DropdownOption", None) or ft.dropdown.Option
Boton = getattr(ft, "ElevatedButton", None) or ft.Button


def abrir(page, ctrl):
    page.show_dialog(ctrl) if hasattr(page, "show_dialog") else page.open(ctrl)


def cerrar(page, ctrl):
    page.pop_dialog() if hasattr(page, "pop_dialog") else page.close(ctrl)


def aviso(page, msg, error=False):
    abrir(page, ft.SnackBar(ft.Text(msg), bgcolor="red" if error else "green"))


def texto_error(ex):
    """Extrae el mensaje legible de un error de MySQL (incluye los SIGNAL de procedimientos)."""
    return str(ex.args[1]) if len(ex.args) > 1 else str(ex)


def confirmar(page, mensaje, on_si):
    def si(e):
        cerrar(page, dlg)
        on_si()
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Confirmar"),
        content=ft.Text(mensaje),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: cerrar(page, dlg)),
            ft.TextButton("Confirmar", on_click=si),
        ],
    )
    abrir(page, dlg)


def acciones(on_editar, on_eliminar):
    return ft.Row([
        ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar", on_click=on_editar),
        ft.IconButton(icon=ft.Icons.DELETE, tooltip="Eliminar", on_click=on_eliminar),
    ])


def etiqueta_unidad(unidad_medida):
    return "kg" if unidad_medida == "kg" else "uds"


def fmt_cant(valor, unidad_medida):
    return f"{float(valor):g} {etiqueta_unidad(unidad_medida)}"


# ======================= PRODUCTOS =======================
def vista_productos(page):
    buscador = ft.TextField(label="Buscar por nombre o categoría", expand=True,
                            on_change=lambda e: cargar())
    tabla = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in
                                  ["ID", "Nombre", "Categoría", "Precio", "Stock", "Acciones"]], rows=[])

    def cargar():
        try:
            filas = datos.listar_productos(buscador.value or "")
        except Exception as ex:
            return aviso(page, f"Error al cargar: {texto_error(ex)}", True)
        tabla.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(p["id_producto"]))),
                ft.DataCell(ft.Text(p["nombre"])),
                ft.DataCell(ft.Text(p["categoria"])),
                ft.DataCell(ft.Text(f"${p['precio']:,.0f} / {'kg' if p['unidad_medida']=='kg' else 'c/u'}")),
                ft.DataCell(ft.Text(fmt_cant(p["stock"], p["unidad_medida"]))),
                ft.DataCell(acciones(lambda e, p=p: formulario(p), lambda e, p=p: eliminar(p))),
            ]) for p in filas
        ]
        page.update()

    def eliminar(p):
        def hacer():
            try:
                datos.eliminar_producto(p["id_producto"])
                aviso(page, "Producto eliminado")
            except Exception:
                aviso(page, "No se puede eliminar: el producto tiene ventas asociadas", True)
            cargar()
        confirmar(page, f"¿Eliminar '{p['nombre']}'?", hacer)

    def formulario(p=None):
        nombre = ft.TextField(label="Nombre", value=p["nombre"] if p else "")
        precio = ft.TextField(label="Precio", value=str(int(p["precio"])) if p else "")
        stock = ft.TextField(label="Stock", value=(f"{p['stock']:g}" if p else ""))
        unidad = ft.Dropdown(
            label="Se vende por", value=p["unidad_medida"] if p else "unidad",
            options=[Option(key="unidad", text="Unidad"), Option(key="kg", text="Kilo (kg)")],
        )
        cat = ft.Dropdown(
            label="Categoría",
            options=[Option(key=str(c["id_categoria"]), text=c["nombre"]) for c in datos.listar_categorias()],
            value=str(p["id_categoria"]) if p else None,
        )

        def guardar(e):
            if not nombre.value.strip():
                return aviso(page, "El nombre es obligatorio", True)
            try:
                pr = float(precio.value.replace(",", "."))
                st = float(stock.value.replace(",", "."))
            except ValueError:
                return aviso(page, "Precio y stock deben ser numéricos", True)
            if pr <= 0 or st < 0:
                return aviso(page, "El precio debe ser mayor a 0 y el stock no negativo", True)
            if not cat.value:
                return aviso(page, "Selecciona una categoría", True)
            try:
                if p:
                    datos.actualizar_producto(p["id_producto"], nombre.value.strip(), pr, st, unidad.value, int(cat.value))
                else:
                    datos.crear_producto(nombre.value.strip(), pr, st, unidad.value, int(cat.value))
            except Exception as ex:
                return aviso(page, texto_error(ex), True)
            cerrar(page, dlg)
            aviso(page, "Producto guardado")
            cargar()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Editar producto" if p else "Nuevo producto"),
            content=ft.Column([nombre, precio, unidad, stock, cat], tight=True, width=350),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: cerrar(page, dlg)),
                     ft.TextButton("Guardar", on_click=guardar)],
        )
        abrir(page, dlg)

    vista = ft.Column([
        ft.Text("Productos en venta", size=24, weight=ft.FontWeight.BOLD),
        ft.Row([buscador, Boton("Nuevo producto", icon=ft.Icons.ADD, on_click=lambda e: formulario())]),
        ft.Row([tabla], scroll=ft.ScrollMode.AUTO),
    ])
    return vista, cargar


# ======================= VENDER (punto de venta de mostrador) =======================
def vista_vender(page):
    buscar = ft.TextField(label="Escribe el nombre del producto", expand=True)
    sugerencias = ft.Column(spacing=0)
    cantidad = ft.TextField(label="Cantidad", value="1", width=110)
    info_txt = ft.Text("", size=12, color=ft.Colors.GREY)
    seleccionado = {"producto": None}
    carrito = {}  # id (str) -> {"nombre","precio","unidad_medida","cantidad"}

    tabla_carrito = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in
                                          ["Producto", "Cantidad", "Precio", "Subtotal", ""]], rows=[])
    IVA = 0.19
    neto_txt = ft.Text("Neto: $0", size=13, color=ft.Colors.GREY)
    iva_txt = ft.Text("IVA (19%): $0", size=13, color=ft.Colors.GREY)
    total_txt = ft.Text("Total: $0", size=20, weight=ft.FontWeight.BOLD)

    def desglose_iva(total):
        """El precio cargado ya incluye IVA (como en una boleta); esto solo lo desglosa."""
        neto = total / (1 + IVA)
        return neto, total - neto
    metodo = ft.Dropdown(label="Medio de pago", value="EFECTIVO", width=200,
                         options=[Option(key="EFECTIVO", text="Efectivo"), Option(key="TARJETA", text="Tarjeta")])
    monto_recibido = ft.TextField(label="Monto recibido", width=180)
    vuelto_txt = ft.Text("", size=16, weight=ft.FontWeight.BOLD)

    tabla_hist = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in
                                       ["Venta", "Fecha", "Pago", "Total", "Recibido", "Vuelto", "Estado", "Acciones"]], rows=[])

    def calcular_total():
        return sum(it["precio"] * it["cantidad"] for it in carrito.values())

    def num(txt, default=0.0):
        try:
            return float((txt or "").replace(",", "."))
        except ValueError:
            return default

    def actualizar_vuelto(e=None):
        monto_recibido.visible = metodo.value == "EFECTIVO"
        if metodo.value == "EFECTIVO":
            vuelto = num(monto_recibido.value) - calcular_total()
            vuelto_txt.value = f"Vuelto: ${vuelto:,.0f}" if vuelto >= 0 else f"Falta: ${-vuelto:,.0f}"
            vuelto_txt.color = "green" if vuelto >= 0 else "red"
        else:
            vuelto_txt.value = ""
        page.update()

    metodo.on_change = actualizar_vuelto
    monto_recibido.on_change = actualizar_vuelto

    def refrescar_carrito():
        tabla_carrito.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(it["nombre"])),
                ft.DataCell(ft.Text(fmt_cant(it["cantidad"], it["unidad_medida"]))),
                ft.DataCell(ft.Text(f"${it['precio']:,.0f}")),
                ft.DataCell(ft.Text(f"${it['precio'] * it['cantidad']:,.0f}")),
                ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE, tooltip="Quitar",
                                          on_click=lambda e, k=k: quitar(k))),
            ]) for k, it in carrito.items()
        ]
        total = calcular_total()
        neto, iva = desglose_iva(total)
        neto_txt.value = f"Neto: ${neto:,.0f}"
        iva_txt.value = f"IVA 0.19%: ${iva:,.0f}"
        total_txt.value = f"Total: ${total:,.0f}"
        actualizar_vuelto()

    def buscar_cambio(e):
        texto = buscar.value or ""
        seleccionado["producto"] = None
        info_txt.value = ""
        if len(texto) < 2:
            sugerencias.controls = []
            page.update()
            return
        try:
            resultados = datos.buscar_productos_venta(texto)
        except Exception as ex:
            return aviso(page, f"Error al buscar: {texto_error(ex)}", True)
        if not resultados:
            sugerencias.controls = [ft.Text("Sin coincidencias", italic=True, size=12, color=ft.Colors.GREY)]
        else:
            sugerencias.controls = [
                ft.TextButton(
                    f"{p['nombre']} — ${p['precio']:,.0f}/{etiqueta_unidad(p['unidad_medida'])}  (stock: {fmt_cant(p['stock'], p['unidad_medida'])})",
                    on_click=lambda e, p=p: elegir(p),
                ) for p in resultados
            ]
        page.update()

    def elegir(p):
        seleccionado["producto"] = p
        buscar.value = p["nombre"]
        info_txt.value = f"${p['precio']:,.0f} por {etiqueta_unidad(p['unidad_medida'])} — stock disponible: {fmt_cant(p['stock'], p['unidad_medida'])}"
        sugerencias.controls = []
        cantidad.value = "1"
        page.update()

    def agregar(e):
        p = seleccionado["producto"]
        if not p:
            return aviso(page, "Escribe el nombre del producto y elígelo de la lista", True)
        cant = num(cantidad.value, -1)
        if cant <= 0:
            return aviso(page, "La cantidad debe ser mayor a 0", True)
        k = str(p["id_producto"])
        ya = carrito[k]["cantidad"] if k in carrito else 0
        if ya + cant > float(p["stock"]):
            return aviso(page, f"Stock insuficiente: quedan {fmt_cant(p['stock'], p['unidad_medida'])} de {p['nombre']}", True)
        carrito[k] = {"nombre": p["nombre"], "precio": float(p["precio"]),
                     "unidad_medida": p["unidad_medida"], "cantidad": ya + cant}
        buscar.value = ""
        info_txt.value = ""
        cantidad.value = "1"
        seleccionado["producto"] = None
        refrescar_carrito()
        page.update()

    def quitar(k):
        carrito.pop(k, None)
        refrescar_carrito()
        page.update()

    def registrar(e):
        if not carrito:
            return aviso(page, "Agrega al menos un producto", True)
        total = calcular_total()
        recibido = None
        if metodo.value == "EFECTIVO":
            recibido = num(monto_recibido.value, -1)
            if recibido < total:
                return aviso(page, f"El monto recibido es menor al total (${total:,.0f})", True)
        items = [{"id_producto": int(k), "cantidad": it["cantidad"]} for k, it in carrito.items()]
        try:
            resultado = datos.registrar_venta(items, metodo.value, recibido)
        except Exception as ex:
            return aviso(page, texto_error(ex), True)
        if metodo.value == "EFECTIVO" and resultado:
            aviso(page, f"Venta registrada. Vuelto: ${float(resultado['vuelto']):,.0f}")
        else:
            aviso(page, "Venta registrada")
        carrito.clear()
        monto_recibido.value = ""
        cargar()

    def ver_detalle(r):
        try:
            items = datos.listar_detalle(r["id_pedido"])
        except Exception as ex:
            return aviso(page, f"Error al cargar el detalle: {texto_error(ex)}", True)
        tabla_det = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c)) for c in ["Producto", "Cantidad", "Precio", "Subtotal"]],
            rows=[ft.DataRow(cells=[
                ft.DataCell(ft.Text(i["nombre"])),
                ft.DataCell(ft.Text(fmt_cant(i["cantidad"], i["unidad_medida"]))),
                ft.DataCell(ft.Text(f"${i['precio_unitario']:,.0f}")),
                ft.DataCell(ft.Text(f"${i['subtotal']:,.0f}"))]) for i in items])
        neto, iva = desglose_iva(float(r["total"]))
        extra = [ft.Text(f"Neto: ${neto:,.0f}   IVA (19%): ${iva:,.0f}", size=12, color=ft.Colors.GREY)]
        if r["metodo_pago"] == "EFECTIVO":
            extra.append(ft.Text(f"Recibido: ${float(r['monto_recibido'] or 0):,.0f}   Vuelto: ${float(r['vuelto']):,.0f}"))
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Venta #{r['id_pedido']}"),
            content=ft.Column([tabla_det, ft.Text(f"Total: ${r['total']:,.0f}", weight=ft.FontWeight.BOLD)] + extra,
                              tight=True, scroll=ft.ScrollMode.AUTO, width=480),
            actions=[ft.TextButton("Cerrar", on_click=lambda e: cerrar(page, dlg))],
        )
        abrir(page, dlg)

    def anular(r):
        def hacer():
            try:
                datos.anular_venta(r["id_pedido"])
                aviso(page, f"Venta #{r['id_pedido']} anulada; el stock fue repuesto")
            except Exception as ex:
                aviso(page, texto_error(ex), True)
            cargar()
        confirmar(page, f"¿Anular la venta #{r['id_pedido']}? Se repondrá el stock vendido.", hacer)

    def cargar():
        try:
            filas = datos.listar_pedidos()
        except Exception as ex:
            return aviso(page, f"Error al cargar: {texto_error(ex)}", True)
        tabla_hist.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(r["id_pedido"]))),
                ft.DataCell(ft.Text(str(r["fecha"]))),
                ft.DataCell(ft.Text(r["metodo_pago"])),
                ft.DataCell(ft.Text(f"${r['total']:,.0f}")),
                ft.DataCell(ft.Text(f"${float(r['monto_recibido']):,.0f}" if r["metodo_pago"] == "EFECTIVO" else "—")),
                ft.DataCell(ft.Text(f"${float(r['vuelto']):,.0f}" if r["metodo_pago"] == "EFECTIVO" else "—")),
                ft.DataCell(ft.Text(r["estado"])),
                ft.DataCell(ft.Row([
                    ft.IconButton(icon=ft.Icons.VISIBILITY, tooltip="Ver qué se vendió",
                                  on_click=lambda e, r=r: ver_detalle(r)),
                    ft.IconButton(icon=ft.Icons.UNDO, tooltip="Anular venta", disabled=r["estado"] == "ANULADO",
                                  on_click=lambda e, r=r: anular(r)),
                ])),
            ]) for r in filas
        ]
        refrescar_carrito()
        page.update()

    buscar.on_change = buscar_cambio

    vista = ft.Column([
        ft.Text("Vender", size=24, weight=ft.FontWeight.BOLD),
        ft.Row([buscar, cantidad, Boton("Agregar", icon=ft.Icons.ADD_SHOPPING_CART, on_click=agregar)]),
        info_txt,
        sugerencias,
        ft.Row([tabla_carrito], scroll=ft.ScrollMode.AUTO),
        neto_txt,
        iva_txt,
        total_txt,
        ft.Row([metodo, monto_recibido, vuelto_txt]),
        Boton("Registrar venta", icon=ft.Icons.CHECK, on_click=registrar),
        ft.Divider(),
        ft.Text("Últimas ventas", size=18),
        ft.Row([tabla_hist], scroll=ft.ScrollMode.AUTO),
    ])
    return vista, cargar
