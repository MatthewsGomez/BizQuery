-- =============================================================================
-- BizQuery - Esquema de Base de Datos SQL
-- =============================================================================
-- Descripción: Esquema para el sistema de ventas e inventario de una empresa
--              de electrodomésticos. Incluye tablas para categorías, productos,
--              inventario, clientes, ventas, detalle de ventas y descuentos.
-- =============================================================================

-- Limpiar tablas existentes (en orden inverso de dependencias)
DROP TABLE IF EXISTS discounts CASCADE;
DROP TABLE IF EXISTS sale_items CASCADE;
DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS inventory CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;

-- =============================================================================
-- Tabla: categories
-- Categorías de productos (ej: refrigeradores, lavadoras, televisores)
-- =============================================================================
CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT
);

-- =============================================================================
-- Tabla: products
-- Productos (electrodomésticos) con SKU único y precio unitario
-- =============================================================================
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    sku         VARCHAR(50) UNIQUE NOT NULL,
    name        VARCHAR(200) NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    brand       VARCHAR(100),
    unit_price  DECIMAL(10, 2) NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Tabla: inventory
-- Niveles de stock por producto con umbral mínimo configurable
-- =============================================================================
CREATE TABLE inventory (
    id                  SERIAL PRIMARY KEY,
    product_id          INTEGER REFERENCES products(id) UNIQUE,
    quantity_available  INTEGER NOT NULL DEFAULT 0,
    min_stock_threshold INTEGER NOT NULL DEFAULT 5,
    last_updated        TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Tabla: customers
-- Clientes de la empresa
-- =============================================================================
CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    email      VARCHAR(200) UNIQUE,
    phone      VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Tabla: sales
-- Cabecera de ventas (una venta puede tener múltiples ítems)
-- =============================================================================
CREATE TABLE sales (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(id),
    sale_date       DATE NOT NULL,
    total_amount    DECIMAL(10, 2) NOT NULL,
    discount_amount DECIMAL(10, 2) DEFAULT 0,
    final_amount    DECIMAL(10, 2) NOT NULL,
    status          VARCHAR(20) DEFAULT 'completed',
    created_at      TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Tabla: sale_items
-- Detalle de líneas de cada venta
-- =============================================================================
CREATE TABLE sale_items (
    id           SERIAL PRIMARY KEY,
    sale_id      INTEGER REFERENCES sales(id),
    product_id   INTEGER REFERENCES products(id),
    quantity     INTEGER NOT NULL,
    unit_price   DECIMAL(10, 2) NOT NULL,
    discount_pct DECIMAL(5, 2) DEFAULT 0,
    subtotal     DECIMAL(10, 2) NOT NULL
);

-- =============================================================================
-- Tabla: discounts
-- Descuentos y ofertas aplicables a productos o categorías completas.
-- Un descuento aplica a producto O categoría, nunca a ambos simultáneamente.
-- =============================================================================
CREATE TABLE discounts (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    product_id   INTEGER REFERENCES products(id),
    category_id  INTEGER REFERENCES categories(id),
    discount_pct DECIMAL(5, 2) NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT NOW(),
    -- Un descuento aplica a producto O categoría, no ambos
    CONSTRAINT chk_discount_scope CHECK (
        (product_id IS NOT NULL AND category_id IS NULL) OR
        (product_id IS NULL AND category_id IS NOT NULL)
    )
);

-- =============================================================================
-- Índices de optimización para queries frecuentes
-- =============================================================================

-- Optimiza consultas de ventas por rango de fechas (query_sales)
CREATE INDEX idx_sales_date ON sales(sale_date);

-- Optimiza joins de sale_items con products (top productos, ventas por categoría)
CREATE INDEX idx_sale_items_product ON sale_items(product_id);

-- Optimiza joins de inventory con products (consultas de stock)
CREATE INDEX idx_inventory_product ON inventory(product_id);

-- Optimiza filtrado de descuentos vigentes (is_active + end_date)
CREATE INDEX idx_discounts_active ON discounts(is_active, end_date);

-- Optimiza búsqueda de descuentos por producto específico
CREATE INDEX idx_discounts_product ON discounts(product_id);
