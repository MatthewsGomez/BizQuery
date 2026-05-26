-- =============================================================================
-- BizQuery - Datos de Prueba (Seed)
-- =============================================================================
-- Descripción: Datos representativos para pruebas y desarrollo.
--              Incluye 5 categorías, 20 productos, 15 clientes, 50+ ventas,
--              registros de inventario para todos los productos y descuentos
--              activos y vencidos.
-- =============================================================================

-- =============================================================================
-- Categorías (5 categorías de electrodomésticos)
-- =============================================================================
INSERT INTO categories (id, name, description) VALUES
    (1, 'Refrigeradores',       'Refrigeradores y congeladores para el hogar y uso comercial'),
    (2, 'Lavadoras',            'Lavadoras automáticas, semiautomáticas y secadoras'),
    (3, 'Televisores',          'Televisores LED, OLED, QLED y Smart TV de todas las pulgadas'),
    (4, 'Aires Acondicionados', 'Equipos de aire acondicionado split, portátiles y de ventana'),
    (5, 'Microondas',           'Hornos microondas de uso doméstico y semiprofesional');

-- Reiniciar secuencia después de inserts con ID explícito
SELECT setval('categories_id_seq', (SELECT MAX(id) FROM categories));

-- =============================================================================
-- Productos (20 productos distribuidos entre las 5 categorías)
-- =============================================================================
INSERT INTO products (id, sku, name, category_id, brand, unit_price) VALUES
    -- Refrigeradores (4 productos)
    (1,  'REF-SAM-400L',  'Refrigerador Samsung No Frost 400L',         1, 'Samsung',  1299.99),
    (2,  'REF-LG-350L',   'Refrigerador LG Side by Side 350L',          1, 'LG',       1599.99),
    (3,  'REF-MBE-300L',  'Refrigerador Mabe Frío Seco 300L',           1, 'Mabe',      799.99),
    (4,  'REF-WHI-500L',  'Refrigerador Whirlpool French Door 500L',    1, 'Whirlpool', 1899.99),

    -- Lavadoras (4 productos)
    (5,  'LAV-SAM-15KG',  'Lavadora Samsung Carga Frontal 15kg',        2, 'Samsung',   899.99),
    (6,  'LAV-LG-12KG',   'Lavadora LG TurboWash 12kg',                 2, 'LG',        749.99),
    (7,  'LAV-MBE-10KG',  'Lavadora Mabe Carga Superior 10kg',          2, 'Mabe',      499.99),
    (8,  'LAV-WHI-14KG',  'Lavadora Whirlpool Cabrio 14kg',             2, 'Whirlpool', 829.99),

    -- Televisores (4 productos)
    (9,  'TV-SAM-65Q',    'Televisor Samsung QLED 65" 4K Smart TV',     3, 'Samsung',  1499.99),
    (10, 'TV-LG-55O',     'Televisor LG OLED 55" 4K Smart TV',         3, 'LG',       1799.99),
    (11, 'TV-TCL-50L',    'Televisor TCL LED 50" 4K Android TV',        3, 'TCL',       599.99),
    (12, 'TV-HAI-43S',    'Televisor Hisense 43" Full HD Smart TV',     3, 'Hisense',   399.99),

    -- Aires Acondicionados (4 productos)
    (13, 'AC-SAM-12K',    'Aire Acondicionado Samsung Split 12000 BTU', 4, 'Samsung',   699.99),
    (14, 'AC-LG-18K',     'Aire Acondicionado LG Dual Inverter 18000 BTU', 4, 'LG',    899.99),
    (15, 'AC-MBE-9K',     'Aire Acondicionado Mabe 9000 BTU Portátil', 4, 'Mabe',      449.99),
    (16, 'AC-CAR-24K',    'Aire Acondicionado Carrier 24000 BTU Split', 4, 'Carrier',  1099.99),

    -- Microondas (4 productos)
    (17, 'MIC-SAM-32L',   'Microondas Samsung 32L con Grill',           5, 'Samsung',   249.99),
    (18, 'MIC-LG-28L',    'Microondas LG NeoChef 28L',                  5, 'LG',        219.99),
    (19, 'MIC-MBE-20L',   'Microondas Mabe 20L Digital',                5, 'Mabe',      149.99),
    (20, 'MIC-PAN-25L',   'Microondas Panasonic Inverter 25L',          5, 'Panasonic', 199.99);

SELECT setval('products_id_seq', (SELECT MAX(id) FROM products));

-- =============================================================================
-- Inventario (registro para cada uno de los 20 productos)
-- =============================================================================
INSERT INTO inventory (product_id, quantity_available, min_stock_threshold) VALUES
    -- Refrigeradores
    (1,  25, 5),   -- Samsung 400L: stock normal
    (2,  12, 5),   -- LG Side by Side: stock normal
    (3,   3, 5),   -- Mabe 300L: BAJO STOCK (3 < 5)
    (4,  18, 5),   -- Whirlpool 500L: stock normal

    -- Lavadoras
    (5,  30, 8),   -- Samsung 15kg: stock normal
    (6,  22, 8),   -- LG 12kg: stock normal
    (7,   4, 8),   -- Mabe 10kg: BAJO STOCK (4 < 8)
    (8,  15, 8),   -- Whirlpool 14kg: stock normal

    -- Televisores
    (9,  20, 5),   -- Samsung QLED 65": stock normal
    (10,  8, 5),   -- LG OLED 55": stock normal
    (11, 35, 10),  -- TCL 50": stock normal
    (12, 50, 10),  -- Hisense 43": stock alto

    -- Aires Acondicionados
    (13, 40, 10),  -- Samsung 12K: stock normal
    (14, 18, 10),  -- LG 18K: stock normal
    (15,  6, 10),  -- Mabe 9K Portátil: BAJO STOCK (6 < 10)
    (16, 10, 10),  -- Carrier 24K: en umbral exacto

    -- Microondas
    (17, 60, 15),  -- Samsung 32L: stock alto
    (18, 45, 15),  -- LG 28L: stock normal
    (19,  2, 15),  -- Mabe 20L: BAJO STOCK (2 < 15)
    (20, 28, 15);  -- Panasonic 25L: stock normal

-- =============================================================================
-- Clientes (15 clientes)
-- =============================================================================
INSERT INTO customers (id, name, email, phone) VALUES
    (1,  'María González',      'maria.gonzalez@email.com',   '555-0101'),
    (2,  'Carlos Rodríguez',    'carlos.rodriguez@email.com', '555-0102'),
    (3,  'Ana Martínez',        'ana.martinez@email.com',     '555-0103'),
    (4,  'Luis Hernández',      'luis.hernandez@email.com',   '555-0104'),
    (5,  'Patricia López',      'patricia.lopez@email.com',   '555-0105'),
    (6,  'Roberto García',      'roberto.garcia@email.com',   '555-0106'),
    (7,  'Carmen Díaz',         'carmen.diaz@email.com',      '555-0107'),
    (8,  'Miguel Torres',       'miguel.torres@email.com',    '555-0108'),
    (9,  'Laura Sánchez',       'laura.sanchez@email.com',    '555-0109'),
    (10, 'Fernando Ramírez',    'fernando.ramirez@email.com', '555-0110'),
    (11, 'Isabel Flores',       'isabel.flores@email.com',    '555-0111'),
    (12, 'Alejandro Morales',   'alejandro.morales@email.com','555-0112'),
    (13, 'Sofía Jiménez',       'sofia.jimenez@email.com',    '555-0113'),
    (14, 'Diego Vargas',        'diego.vargas@email.com',     '555-0114'),
    (15, 'Valentina Castro',    'valentina.castro@email.com', '555-0115');

SELECT setval('customers_id_seq', (SELECT MAX(id) FROM customers));

-- =============================================================================
-- Ventas (55 ventas distribuidas en los últimos 6 meses)
-- Incluye ventas en Q1 y Q2 del año actual para comparativas de períodos
-- =============================================================================
INSERT INTO sales (id, customer_id, sale_date, total_amount, discount_amount, final_amount, status) VALUES
    -- Enero (10 ventas)
    (1,   3,  '2025-01-05', 1299.99,    0.00, 1299.99, 'completed'),
    (2,   7,  '2025-01-08', 1599.99,  160.00, 1439.99, 'completed'),
    (3,   1,  '2025-01-10',  899.99,    0.00,  899.99, 'completed'),
    (4,  12,  '2025-01-12',  749.99,   75.00,  674.99, 'completed'),
    (5,   5,  '2025-01-15', 1499.99,    0.00, 1499.99, 'completed'),
    (6,   9,  '2025-01-18',  699.99,    0.00,  699.99, 'completed'),
    (7,   2,  '2025-01-20',  249.99,    0.00,  249.99, 'completed'),
    (8,  14,  '2025-01-22', 1899.99,  190.00, 1709.99, 'completed'),
    (9,   6,  '2025-01-25',  599.99,    0.00,  599.99, 'completed'),
    (10,  4,  '2025-01-28',  449.99,   45.00,  404.99, 'completed'),

    -- Febrero (10 ventas)
    (11,  8,  '2025-02-02',  829.99,    0.00,  829.99, 'completed'),
    (12, 11,  '2025-02-05', 1799.99,  180.00, 1619.99, 'completed'),
    (13, 15,  '2025-02-07',  499.99,    0.00,  499.99, 'completed'),
    (14,  1,  '2025-02-10',  899.99,   90.00,  809.99, 'completed'),
    (15, 10,  '2025-02-12', 1099.99,    0.00, 1099.99, 'completed'),
    (16,  3,  '2025-02-14',  219.99,    0.00,  219.99, 'completed'),
    (17, 13,  '2025-02-17',  399.99,   40.00,  359.99, 'completed'),
    (18,  7,  '2025-02-19',  799.99,    0.00,  799.99, 'completed'),
    (19,  2,  '2025-02-21', 1299.99,  130.00, 1169.99, 'completed'),
    (20,  5,  '2025-02-25',  149.99,    0.00,  149.99, 'completed'),

    -- Marzo (10 ventas)
    (21,  6,  '2025-03-03',  899.99,    0.00,  899.99, 'completed'),
    (22,  9,  '2025-03-06', 1499.99,  150.00, 1349.99, 'completed'),
    (23, 12,  '2025-03-08',  699.99,    0.00,  699.99, 'completed'),
    (24, 14,  '2025-03-11',  749.99,   75.00,  674.99, 'completed'),
    (25,  4,  '2025-03-13', 1899.99,    0.00, 1899.99, 'completed'),
    (26,  8,  '2025-03-15',  249.99,    0.00,  249.99, 'completed'),
    (27, 11,  '2025-03-18',  599.99,   60.00,  539.99, 'completed'),
    (28, 15,  '2025-03-20', 1299.99,    0.00, 1299.99, 'completed'),
    (29,  1,  '2025-03-22',  449.99,    0.00,  449.99, 'completed'),
    (30, 10,  '2025-03-26',  829.99,   83.00,  746.99, 'completed'),

    -- Abril (10 ventas)
    (31,  2,  '2025-04-01', 1799.99,    0.00, 1799.99, 'completed'),
    (32,  7,  '2025-04-04',  499.99,   50.00,  449.99, 'completed'),
    (33, 13,  '2025-04-07',  899.99,    0.00,  899.99, 'completed'),
    (34,  3,  '2025-04-09', 1099.99,  110.00,  989.99, 'completed'),
    (35,  6,  '2025-04-11',  219.99,    0.00,  219.99, 'completed'),
    (36,  5,  '2025-04-14',  399.99,    0.00,  399.99, 'completed'),
    (37,  9,  '2025-04-16', 1299.99,  130.00, 1169.99, 'completed'),
    (38, 14,  '2025-04-18',  799.99,    0.00,  799.99, 'completed'),
    (39, 12,  '2025-04-21',  149.99,    0.00,  149.99, 'completed'),
    (40,  4,  '2025-04-24', 1499.99,  150.00, 1349.99, 'completed'),

    -- Mayo (10 ventas)
    (41,  8,  '2025-05-02',  699.99,    0.00,  699.99, 'completed'),
    (42, 11,  '2025-05-05',  749.99,   75.00,  674.99, 'completed'),
    (43, 15,  '2025-05-07', 1899.99,    0.00, 1899.99, 'completed'),
    (44,  1,  '2025-05-09',  249.99,    0.00,  249.99, 'completed'),
    (45, 10,  '2025-05-12',  599.99,   60.00,  539.99, 'completed'),
    (46,  2,  '2025-05-14', 1299.99,    0.00, 1299.99, 'completed'),
    (47, 13,  '2025-05-16',  449.99,   45.00,  404.99, 'completed'),
    (48,  7,  '2025-05-19',  829.99,    0.00,  829.99, 'completed'),
    (49,  3,  '2025-05-21', 1799.99,  180.00, 1619.99, 'completed'),
    (50,  6,  '2025-05-24',  499.99,    0.00,  499.99, 'completed'),

    -- Junio (5 ventas recientes)
    (51,  9,  '2025-06-02',  899.99,    0.00,  899.99, 'completed'),
    (52, 14,  '2025-06-05', 1099.99,  110.00,  989.99, 'completed'),
    (53,  5,  '2025-06-08',  219.99,    0.00,  219.99, 'completed'),
    (54, 12,  '2025-06-10',  399.99,   40.00,  359.99, 'completed'),
    (55,  4,  '2025-06-12', 1499.99,    0.00, 1499.99, 'completed');

SELECT setval('sales_id_seq', (SELECT MAX(id) FROM sales));

-- =============================================================================
-- Detalle de Ventas (sale_items)
-- Cada venta tiene al menos un ítem; algunas tienen múltiples productos
-- =============================================================================
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, discount_pct, subtotal) VALUES
    -- Enero
    (1,   1, 1, 1299.99,  0.00, 1299.99),  -- Refrigerador Samsung 400L
    (2,   2, 1, 1599.99, 10.00, 1439.99),  -- Refrigerador LG (10% desc)
    (3,   5, 1,  899.99,  0.00,  899.99),  -- Lavadora Samsung 15kg
    (4,   6, 1,  749.99, 10.00,  674.99),  -- Lavadora LG (10% desc)
    (5,   9, 1, 1499.99,  0.00, 1499.99),  -- TV Samsung QLED 65"
    (6,  13, 1,  699.99,  0.00,  699.99),  -- AC Samsung 12K
    (7,  17, 1,  249.99,  0.00,  249.99),  -- Microondas Samsung 32L
    (8,   4, 1, 1899.99, 10.00, 1709.99),  -- Refrigerador Whirlpool (10% desc)
    (9,  11, 1,  599.99,  0.00,  599.99),  -- TV TCL 50"
    (10, 15, 1,  449.99, 10.00,  404.99),  -- AC Mabe 9K (10% desc)

    -- Febrero
    (11,  8, 1,  829.99,  0.00,  829.99),  -- Lavadora Whirlpool 14kg
    (12, 10, 1, 1799.99, 10.00, 1619.99),  -- TV LG OLED (10% desc)
    (13,  7, 1,  499.99,  0.00,  499.99),  -- Lavadora Mabe 10kg
    (14,  5, 1,  899.99, 10.00,  809.99),  -- Lavadora Samsung (10% desc)
    (15, 16, 1, 1099.99,  0.00, 1099.99),  -- AC Carrier 24K
    (16, 18, 1,  219.99,  0.00,  219.99),  -- Microondas LG 28L
    (17, 12, 1,  399.99, 10.00,  359.99),  -- TV Hisense 43" (10% desc)
    (18,  3, 1,  799.99,  0.00,  799.99),  -- Refrigerador Mabe 300L
    (19,  1, 1, 1299.99, 10.00, 1169.99),  -- Refrigerador Samsung (10% desc)
    (20, 19, 1,  149.99,  0.00,  149.99),  -- Microondas Mabe 20L

    -- Marzo
    (21,  5, 1,  899.99,  0.00,  899.99),  -- Lavadora Samsung 15kg
    (22,  9, 1, 1499.99, 10.00, 1349.99),  -- TV Samsung QLED (10% desc)
    (23, 13, 1,  699.99,  0.00,  699.99),  -- AC Samsung 12K
    (24,  6, 1,  749.99, 10.00,  674.99),  -- Lavadora LG (10% desc)
    (25,  4, 1, 1899.99,  0.00, 1899.99),  -- Refrigerador Whirlpool
    (26, 17, 1,  249.99,  0.00,  249.99),  -- Microondas Samsung 32L
    (27, 11, 1,  599.99, 10.00,  539.99),  -- TV TCL 50" (10% desc)
    (28,  1, 1, 1299.99,  0.00, 1299.99),  -- Refrigerador Samsung 400L
    (29, 15, 1,  449.99,  0.00,  449.99),  -- AC Mabe 9K
    (30,  8, 1,  829.99, 10.00,  746.99),  -- Lavadora Whirlpool (10% desc)

    -- Abril
    (31, 10, 1, 1799.99,  0.00, 1799.99),  -- TV LG OLED 55"
    (32,  7, 1,  499.99, 10.00,  449.99),  -- Lavadora Mabe (10% desc)
    (33,  5, 1,  899.99,  0.00,  899.99),  -- Lavadora Samsung 15kg
    (34, 16, 1, 1099.99, 10.00,  989.99),  -- AC Carrier (10% desc)
    (35, 18, 1,  219.99,  0.00,  219.99),  -- Microondas LG 28L
    (36, 12, 1,  399.99,  0.00,  399.99),  -- TV Hisense 43"
    (37,  1, 1, 1299.99, 10.00, 1169.99),  -- Refrigerador Samsung (10% desc)
    (38,  3, 1,  799.99,  0.00,  799.99),  -- Refrigerador Mabe 300L
    (39, 19, 1,  149.99,  0.00,  149.99),  -- Microondas Mabe 20L
    (40,  9, 1, 1499.99, 10.00, 1349.99),  -- TV Samsung QLED (10% desc)

    -- Mayo
    (41, 13, 1,  699.99,  0.00,  699.99),  -- AC Samsung 12K
    (42,  6, 1,  749.99, 10.00,  674.99),  -- Lavadora LG (10% desc)
    (43,  4, 1, 1899.99,  0.00, 1899.99),  -- Refrigerador Whirlpool
    (44, 17, 1,  249.99,  0.00,  249.99),  -- Microondas Samsung 32L
    (45, 11, 1,  599.99, 10.00,  539.99),  -- TV TCL 50" (10% desc)
    (46,  1, 1, 1299.99,  0.00, 1299.99),  -- Refrigerador Samsung 400L
    (47, 15, 1,  449.99, 10.00,  404.99),  -- AC Mabe 9K (10% desc)
    (48,  8, 1,  829.99,  0.00,  829.99),  -- Lavadora Whirlpool 14kg
    (49, 10, 1, 1799.99, 10.00, 1619.99),  -- TV LG OLED (10% desc)
    (50,  7, 1,  499.99,  0.00,  499.99),  -- Lavadora Mabe 10kg

    -- Junio
    (51,  5, 1,  899.99,  0.00,  899.99),  -- Lavadora Samsung 15kg
    (52, 16, 1, 1099.99, 10.00,  989.99),  -- AC Carrier (10% desc)
    (53, 18, 1,  219.99,  0.00,  219.99),  -- Microondas LG 28L
    (54, 12, 1,  399.99, 10.00,  359.99),  -- TV Hisense 43" (10% desc)
    (55,  9, 1, 1499.99,  0.00, 1499.99);  -- TV Samsung QLED 65"

-- Ventas con múltiples ítems (para probar queries de agregación)
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, discount_pct, subtotal) VALUES
    -- Venta 3: cliente compró lavadora + microondas
    (3,  17, 1,  249.99,  0.00,  249.99),  -- Microondas Samsung 32L adicional
    -- Venta 11: cliente compró lavadora + AC
    (11, 14, 1,  899.99,  0.00,  899.99),  -- AC LG 18K adicional
    -- Venta 25: cliente compró refrigerador + TV
    (25, 12, 1,  399.99,  0.00,  399.99),  -- TV Hisense 43" adicional
    -- Venta 43: cliente compró refrigerador + lavadora
    (43,  5, 1,  899.99,  0.00,  899.99);  -- Lavadora Samsung adicional

-- =============================================================================
-- Descuentos (activos, próximos a vencer y vencidos para pruebas)
-- =============================================================================
INSERT INTO discounts (name, product_id, category_id, discount_pct, start_date, end_date, is_active) VALUES
    -- Descuentos ACTIVOS por producto
    ('Oferta Verano - Refrigerador Samsung 400L',
        1, NULL, 15.00, '2025-06-01', '2025-07-31', TRUE),
    ('Promoción Especial - TV LG OLED 55"',
        10, NULL, 20.00, '2025-06-10', '2025-06-30', TRUE),
    ('Descuento Liquidación - Microondas Mabe 20L',
        19, NULL, 25.00, '2025-06-01', '2025-06-20', TRUE),

    -- Descuentos ACTIVOS por categoría
    ('Temporada Frío - Categoría Aires Acondicionados',
        NULL, 4, 10.00, '2025-05-15', '2025-08-15', TRUE),
    ('Promo Hogar - Categoría Lavadoras',
        NULL, 2, 12.00, '2025-06-01', '2025-06-30', TRUE),

    -- Descuentos PRÓXIMOS A VENCER (dentro de 7 días desde fecha de referencia)
    ('Oferta Flash - Refrigerador LG Side by Side',
        2, NULL, 18.00, '2025-06-10', '2025-06-19', TRUE),
    ('Descuento Fin de Temporada - Microondas LG 28L',
        18, NULL, 10.00, '2025-06-05', '2025-06-18', TRUE),

    -- Descuentos VENCIDOS (para probar filtrado de vigentes)
    ('Black Friday 2024 - Televisores',
        NULL, 3, 30.00, '2024-11-29', '2024-12-01', FALSE),
    ('Navidad 2024 - Refrigeradores',
        NULL, 1, 20.00, '2024-12-20', '2024-12-31', FALSE),
    ('Año Nuevo 2025 - Microondas Panasonic',
        20, NULL, 15.00, '2025-01-01', '2025-01-07', FALSE),

    -- Descuento INACTIVO (is_active = FALSE pero fecha vigente)
    ('Campaña Pausada - AC Carrier 24K',
        16, NULL, 8.00, '2025-06-01', '2025-07-31', FALSE);
