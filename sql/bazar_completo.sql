-- BAZAR — Base de datos completa en un solo archivo

USE daniel_arellano_prod;


-- 1) TABLAS
CREATE TABLE categorias (
  id_categoria INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(60) NOT NULL UNIQUE
);

CREATE TABLE productos (
  id_producto INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  precio DECIMAL(10,2) NOT NULL,
  stock DECIMAL(10,3) NOT NULL DEFAULT 0,
  unidad_medida ENUM('unidad','kg') NOT NULL DEFAULT 'unidad',
  activo TINYINT(1) NOT NULL DEFAULT 1,
  id_categoria INT NOT NULL,
  CONSTRAINT fk_prod_cat FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria),
  CONSTRAINT ck_prod_stock CHECK (stock >= 0),
  CONSTRAINT ck_prod_precio CHECK (precio > 0)
);

CREATE TABLE pedidos (
  id_pedido INT AUTO_INCREMENT PRIMARY KEY,
  fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado ENUM('PAGADO','ANULADO') NOT NULL DEFAULT 'PAGADO',
  metodo_pago ENUM('EFECTIVO','TARJETA') NOT NULL DEFAULT 'EFECTIVO',
  monto_recibido DECIMAL(10,2) NULL,
  vuelto DECIMAL(10,2) NOT NULL DEFAULT 0,
  total DECIMAL(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE detalle_pedido (
  id_detalle INT AUTO_INCREMENT PRIMARY KEY,
  id_pedido INT NOT NULL,
  id_producto INT NOT NULL,
  cantidad DECIMAL(10,3) NOT NULL,
  precio_unitario DECIMAL(10,2) NOT NULL,
  CONSTRAINT fk_det_ped FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido) ON DELETE CASCADE,
  CONSTRAINT fk_det_prod FOREIGN KEY (id_producto) REFERENCES productos(id_producto),
  CONSTRAINT ck_det_cant CHECK (cantidad > 0)
);

-- VISTA
CREATE OR REPLACE VIEW v_pedidos_resumen AS
SELECT id_pedido, fecha, metodo_pago, estado, total, monto_recibido, vuelto
FROM pedidos;

-- PROCEDIMIENTO 1: registra una venta completa y calcula el vuelto. Si algo falla, no se guarda nada.
CREATE PROCEDURE sp_registrar_venta(IN p_items JSON, IN p_metodo_pago VARCHAR(20), IN p_monto_recibido DECIMAL(10,2))
BEGIN
  DECLARE i INT DEFAULT 0;
  DECLARE n INT DEFAULT 0;
  DECLARE v_id INT;
  DECLARE v_prod INT;
  DECLARE v_cant DECIMAL(10,3);
  DECLARE v_stock DECIMAL(10,3);
  DECLARE v_precio DECIMAL(10,2);
  DECLARE v_activo TINYINT;
  DECLARE v_nombre VARCHAR(100);
  DECLARE v_total DECIMAL(10,2) DEFAULT 0;
  DECLARE v_vuelto DECIMAL(10,2) DEFAULT 0;
  DECLARE v_msg VARCHAR(200);
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  IF p_metodo_pago NOT IN ('EFECTIVO','TARJETA') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Medio de pago no válido';
  END IF;

  SET n = IFNULL(JSON_LENGTH(p_items), 0);
  IF n = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Debes agregar al menos un producto';
  END IF;

  START TRANSACTION;
    INSERT INTO pedidos (metodo_pago, estado) VALUES (p_metodo_pago, 'PAGADO');
    SET v_id = LAST_INSERT_ID();

    WHILE i < n DO
      SET v_prod = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_items, CONCAT('$[', i, '].id_producto'))) AS UNSIGNED);
      SET v_cant = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_items, CONCAT('$[', i, '].cantidad'))) AS DECIMAL(10,3));
      SET v_activo = NULL;

      SELECT nombre, stock, precio, activo INTO v_nombre, v_stock, v_precio, v_activo
        FROM productos WHERE id_producto = v_prod FOR UPDATE;

      IF v_activo IS NULL OR v_activo = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un producto de la venta no está disponible';
      END IF;
      IF v_cant IS NULL OR v_cant <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La cantidad debe ser mayor a 0';
      END IF;
      IF v_stock < v_cant THEN
        SET v_msg = CONCAT('Stock insuficiente para: ', v_nombre);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
      END IF;

      INSERT INTO detalle_pedido (id_pedido, id_producto, cantidad, precio_unitario)
        VALUES (v_id, v_prod, v_cant, v_precio);
      UPDATE productos SET stock = stock - v_cant WHERE id_producto = v_prod;
      SET v_total = v_total + (v_cant * v_precio);
      SET i = i + 1;
    END WHILE;

    IF p_metodo_pago = 'EFECTIVO' THEN
      IF p_monto_recibido IS NULL OR p_monto_recibido < v_total THEN
        SET v_msg = CONCAT('Monto insuficiente. Total: $', v_total);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
      END IF;
      SET v_vuelto = p_monto_recibido - v_total;
    ELSE
      SET v_vuelto = 0;
    END IF;

    UPDATE pedidos SET total = v_total, monto_recibido = p_monto_recibido, vuelto = v_vuelto
      WHERE id_pedido = v_id;
  COMMIT;

  SELECT v_id AS id_pedido, v_total AS total, v_vuelto AS vuelto;
END$$


-- PROCEDIMIENTO: anula una venta y repone el stock
CREATE PROCEDURE sp_anular_venta(IN p_id_pedido INT)
BEGIN
  DECLARE v_estado VARCHAR(20);
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  SELECT estado INTO v_estado FROM pedidos WHERE id_pedido = p_id_pedido FOR UPDATE;
  IF v_estado IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La venta no existe';
  END IF;
  IF v_estado = 'ANULADO' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Esa venta ya estaba anulada';
  END IF;

  START TRANSACTION;
    UPDATE productos p
      JOIN detalle_pedido d ON d.id_producto = p.id_producto
      SET p.stock = p.stock + d.cantidad
      WHERE d.id_pedido = p_id_pedido;
    UPDATE pedidos SET estado = 'ANULADO' WHERE id_pedido = p_id_pedido;
  COMMIT;
END$$
DELIMITER ;

-- PROCEDIMIENTO 2  : desactiva productos sin stock
DELIMITER $$
CREATE PROCEDURE sp_desactivar_sin_stock()
BEGIN
  UPDATE productos SET activo = 0 WHERE stock = 0 AND activo = 1;
  SELECT ROW_COUNT() AS productos_desactivados;
END$$
DELIMITER ;

-- PROCEDIMIENTO 3 (reporte parametrizado): ventas por categoría en un rango de fechas
DELIMITER $$
CREATE PROCEDURE sp_reporte_ventas(IN p_desde DATE, IN p_hasta DATE)
BEGIN
  SELECT c.nombre AS categoria,
         SUM(d.cantidad) AS unidades_vendidas,
         SUM(d.cantidad * d.precio_unitario) AS total_vendido
  FROM detalle_pedido d
  JOIN pedidos p    ON p.id_pedido = d.id_pedido
  JOIN productos pr ON pr.id_producto = d.id_producto
  JOIN categorias c ON c.id_categoria = pr.id_categoria
  WHERE DATE(p.fecha) BETWEEN p_desde AND p_hasta
  GROUP BY c.nombre
  ORDER BY total_vendido DESC;
END$$
DELIMITER ;
