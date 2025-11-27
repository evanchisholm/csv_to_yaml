--
-- PostgreSQL database schema for sample application
-- Generated for testing document_schema.py script
-- This file demonstrates the pattern where all tables are created first,
-- then all foreign keys are added via ALTER TABLE, then all indexes are created
--

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CREATE TABLE statements - all tables defined first
-- ============================================================================

-- Table: users
-- Stores user account information
CREATE TABLE public.users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE public.users IS 'User accounts table storing authentication and profile information';

-- Table: categories
-- Product categories
CREATE TABLE public.categories (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_category_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_parent_category FOREIGN KEY (parent_category_id) REFERENCES public.categories(category_id) ON DELETE SET NULL
);

COMMENT ON TABLE public.categories IS 'Hierarchical product categories with self-referencing parent relationship';

-- Table: products
-- Product catalog
CREATE TABLE public.products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    sku VARCHAR(100) UNIQUE NOT NULL,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    category_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE public.products IS 'Product catalog with inventory tracking';

-- Table: orders
-- Customer orders
CREATE TABLE public.orders (
    order_id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    order_number VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled')),
    total_amount DECIMAL(10, 2) NOT NULL CHECK (total_amount >= 0),
    shipping_address TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE public.orders IS 'Customer orders with status tracking';

-- Table: order_items
-- Items within an order
CREATE TABLE public.order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL CHECK (unit_price >= 0),
    subtotal DECIMAL(10, 2) NOT NULL GENERATED ALWAYS AS (quantity * unit_price) STORED,
    CONSTRAINT uk_order_product UNIQUE (order_id, product_id)
);

COMMENT ON TABLE public.order_items IS 'Individual line items within an order';

-- Table: reviews
-- Product reviews by users
CREATE TABLE public.reviews (
    review_id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    user_id UUID NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    title VARCHAR(200),
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_user_product_review UNIQUE (user_id, product_id)
);

COMMENT ON TABLE public.reviews IS 'Product reviews and ratings from users';

-- Table: addresses
-- User shipping addresses
CREATE TABLE public.addresses (
    address_id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    label VARCHAR(50) NOT NULL,
    street_address VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(50) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country VARCHAR(50) NOT NULL DEFAULT 'USA',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_address_valid CHECK (postal_code ~ '^[0-9]+$' OR LENGTH(postal_code) >= 5)
);

COMMENT ON TABLE public.addresses IS 'User shipping and billing addresses';

-- Table: inventory
-- Product inventory tracking with table-level CHECK constraints
CREATE TABLE public.inventory (
    inventory_id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    warehouse_location VARCHAR(100) NOT NULL,
    quantity_on_hand INTEGER NOT NULL,
    quantity_reserved INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL,
    max_stock_level INTEGER NOT NULL,
    last_count_date DATE,
    CONSTRAINT chk_inventory_quantities CHECK (quantity_on_hand >= 0 AND quantity_reserved >= 0),
    CONSTRAINT chk_inventory_reserved CHECK (quantity_reserved <= quantity_on_hand),
    CONSTRAINT chk_reorder_levels CHECK (reorder_level > 0 AND max_stock_level > reorder_level)
);

COMMENT ON TABLE public.inventory IS 'Product inventory with table-level validation constraints';

-- Table: discounts
-- Discount codes and promotions with complex CHECK constraints
CREATE TABLE public.discounts (
    discount_id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    discount_type VARCHAR(20) NOT NULL,
    discount_value DECIMAL(10, 2) NOT NULL,
    minimum_purchase DECIMAL(10, 2) DEFAULT 0,
    maximum_discount DECIMAL(10, 2),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    usage_limit INTEGER,
    CONSTRAINT chk_discount_type CHECK (discount_type IN ('percentage', 'fixed_amount')),
    CONSTRAINT chk_discount_percentage CHECK (
        (discount_type = 'percentage' AND discount_value >= 0 AND discount_value <= 100) OR
        (discount_type = 'fixed_amount' AND discount_value > 0)
    ),
    CONSTRAINT chk_discount_dates CHECK (end_date >= start_date),
    CONSTRAINT chk_discount_amounts CHECK (
        minimum_purchase >= 0 AND
        (maximum_discount IS NULL OR maximum_discount > 0)
    )
);

COMMENT ON TABLE public.discounts IS 'Discount codes with complex table-level validation rules';

-- ============================================================================
-- ALTER TABLE statements - all foreign key constraints added after table creation
-- ============================================================================

-- Foreign key constraints for products table
ALTER TABLE public.products
    ADD CONSTRAINT fk_product_category
    FOREIGN KEY (category_id) REFERENCES public.categories(category_id) ON DELETE RESTRICT;

-- Foreign key constraints for orders table
ALTER TABLE public.orders
    ADD CONSTRAINT fk_order_user
    FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;

-- Foreign key constraints for order_items table
ALTER TABLE public.order_items
    ADD CONSTRAINT fk_order_item_order
    FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;

ALTER TABLE public.order_items
    ADD CONSTRAINT fk_order_item_product
    FOREIGN KEY (product_id) REFERENCES public.products(product_id) ON DELETE RESTRICT;

-- Foreign key constraints for reviews table
ALTER TABLE public.reviews
    ADD CONSTRAINT fk_review_product
    FOREIGN KEY (product_id) REFERENCES public.products(product_id) ON DELETE CASCADE;

ALTER TABLE public.reviews
    ADD CONSTRAINT fk_review_user
    FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;

-- Foreign key constraints for addresses table
ALTER TABLE public.addresses
    ADD CONSTRAINT fk_address_user
    FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;

-- Additional constraint examples
ALTER TABLE public.users 
    ADD CONSTRAINT chk_email_format 
    CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');

-- ============================================================================
-- CREATE INDEX statements - all indexes created at the end
-- ============================================================================

-- Indexes for products table
CREATE INDEX idx_products_category ON public.products(category_id);
CREATE INDEX idx_products_category_price ON public.products(category_id, price);

-- Indexes for orders table
CREATE INDEX idx_orders_user ON public.orders(user_id);
CREATE INDEX idx_orders_status ON public.orders(status);
CREATE INDEX idx_orders_created ON public.orders(created_at DESC);

-- Indexes for order_items table
CREATE INDEX idx_order_items_order ON public.order_items(order_id);
CREATE INDEX idx_order_items_product ON public.order_items(product_id);

-- Indexes for reviews table
CREATE INDEX idx_reviews_product ON public.reviews(product_id);
CREATE INDEX idx_reviews_user ON public.reviews(user_id);

-- Indexes for addresses table
CREATE INDEX idx_addresses_user ON public.addresses(user_id);

-- Indexes for users table
CREATE UNIQUE INDEX idx_users_email_lower ON public.users(LOWER(email));
