import flet as ft
import db
import vistas


def main(page: ft.Page):
    page.title = "Bazar - Punto de Venta"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    try:
        info = db.probar_conexion()
    except Exception as ex:
        page.add(ft.Text(f"❌ No se pudo conectar a la base de datos: {ex}", color="red"),
                 ft.Text("Revisa tu archivo .env (host, puerto, usuario, contraseña y DB_NAME)."))
        return

    contenido = ft.Container()
    secciones = {
        "Productos": vistas.vista_productos(page),
        "Vender": vistas.vista_vender(page),
    }
    versiones = {}
    actual = {"nombre": "Vender"}

    def mostrar(nombre, forzar=False):
        """Cambia de sección. Solo recarga los datos si algo cambió desde la última vez."""
        actual["nombre"] = nombre
        vista, cargar = secciones[nombre]
        contenido.content = vista
        page.update()
        if forzar or versiones.get(nombre) != db.VERSION:
            versiones[nombre] = db.VERSION
            cargar()

    menu = ft.Row(
        [vistas.Boton(n, on_click=lambda e, n=n: mostrar(n)) for n in secciones]
        + [ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar datos (por si cambiaron en DBeaver)",
                         on_click=lambda e: mostrar(actual["nombre"], forzar=True))]
    )
    page.add(ft.Text("🏪 Bazar", size=30, weight=ft.FontWeight.BOLD),
             menu, ft.Divider(), contenido)
    mostrar("Vender")


if hasattr(ft, "run"):
    ft.run(main)
else:
    ft.app(target=main)
