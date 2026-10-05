"""Conexión a MySQL (una sola conexión reutilizable). `python db.py` prueba la conexión."""
import threading
import time
import pymysql
from pymysql.cursors import DictCursor
from config import DB_CONFIG

# Códigos de error de conexión perdida / rechazada (no confundir con errores de SQL o de triggers)
ERRORES_CONEXION = (2003, 2006, 2013, 2055)

_lock = threading.RLock()   # Flet puede atender eventos en hilos distintos
_conn = None                # conexión compartida
VERSION = 0                 # sube cada vez que se modifican datos (para saber cuándo recargar pantallas)


def _es_error_conexion(ex):
    return isinstance(ex, (pymysql.err.OperationalError, pymysql.err.InterfaceError)) and (
        not ex.args or ex.args[0] in ERRORES_CONEXION
    )


def conectar(intentos=3):
    """Abre una conexión nueva; reintenta si el servidor la rechaza o la corta al inicio."""
    for n in range(1, intentos + 1):
        try:
            return pymysql.connect(
                **DB_CONFIG,
                charset="utf8mb4",
                cursorclass=DictCursor,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30,
                autocommit=True,  # cada consulta ve datos actualizados; los procedimientos manejan su transacción
            )
        except Exception as ex:
            if n == intentos or not _es_error_conexion(ex):
                raise
            time.sleep(1)


def _descartar():
    global _conn
    try:
        if _conn is not None:
            _conn.close()
    except Exception:
        pass
    _conn = None


def _conexion():
    """Devuelve la conexión compartida; si el servidor la cerró, abre una nueva."""
    global _conn
    if _conn is not None:
        try:
            _conn.ping(reconnect=True)
            return _conn
        except Exception:
            _descartar()
    _conn = conectar()
    return _conn


def consultar(sql, params=None):
    """SELECT: devuelve lista de diccionarios. Reintenta una vez si se pierde la conexión."""
    with _lock:
        for intento in (1, 2):
            try:
                with _conexion().cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()
            except Exception as ex:
                perdida = _es_error_conexion(ex)
                if perdida:
                    _descartar()
                if intento == 2 or not perdida:
                    raise


def ejecutar(sql, params=None):
    """INSERT / UPDATE / DELETE: devuelve filas afectadas.
    No se reintenta automáticamente para no duplicar escrituras."""
    global VERSION
    with _lock:
        try:
            with _conexion().cursor() as cur:
                filas = cur.execute(sql, params)
            VERSION += 1
            return filas
        except Exception as ex:
            if _es_error_conexion(ex):
                _descartar()
            raise


def llamar_procedimiento(nombre, args=()):
    """CALL de un procedimiento almacenado; devuelve sus resultados (si los hay).
    No se reintenta automáticamente: el pedido podría haberse guardado antes del corte."""
    global VERSION
    with _lock:
        try:
            with _conexion().cursor() as cur:
                cur.callproc(nombre, args)
                resultado = cur.fetchall()
                while cur.nextset():  # vacía los resultados pendientes del procedimiento
                    pass
            VERSION += 1
            return resultado
        except Exception as ex:
            if _es_error_conexion(ex):
                _descartar()
            raise


def probar_conexion():
    return consultar("SELECT DATABASE() AS bd, VERSION() AS version")[0]


if __name__ == "__main__":
    try:
        info = probar_conexion()
        print("✅ Conexión exitosa:", info)
    except Exception as ex:
        print("❌ Error de conexión:", ex)
