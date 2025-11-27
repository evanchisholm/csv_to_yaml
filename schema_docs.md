# Database Schema Documentation

<h2 id="table-list">Entity Overview</h2>

This schema contains **9** table(s):

- [`addresses`](#addresses) (PK: address_id)
- [`categories`](#categories) (PK: category_id)
- [`discounts`](#discounts) (PK: discount_id)
- [`inventory`](#inventory) (PK: inventory_id)
- [`order_items`](#order-items) (PK: order_item_id)
- [`orders`](#orders) (PK: order_id)
- [`products`](#products) (PK: product_id)
- [`reviews`](#reviews) (PK: review_id)
- [`users`](#users) (PK: user_id)

## Tables

<a name="addresses"></a>

### addresses

[↑ Back to Table List](#table-list)


*User shipping and billing addresses*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `address_id` | `SERIAL` | Yes | - | PK |
| `user_id` | `UUID` | No | - | NOT NULL |
| `label` | `VARCHAR(50)` | No | - | NOT NULL |
| `street_address` | `VARCHAR(255)` | No | - | NOT NULL |
| `city` | `VARCHAR(100)` | No | - | NOT NULL |
| `state` | `VARCHAR(50)` | No | - | NOT NULL |
| `postal_code` | `VARCHAR(20)` | No | - | NOT NULL |
| `country` | `VARCHAR(50)` | No | USA | NOT NULL |
| `is_default` | `BOOLEAN` | No | BOOLEAN | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Table CHECK Constraints:**

- `chk_address_valid`: `postal_code ~ '^[0-9]+$' OR LENGTH(postal_code) >= 5`

**Foreign Keys:**

- `user_id` → `users.user_id` (constraint: `fk_address_user`)

---

<a name="categories"></a>

### categories

[↑ Back to Table List](#table-list)


*Hierarchical product categories with self-referencing parent relationship*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `category_id` | `SERIAL` | Yes | - | PK |
| `name` | `VARCHAR(100)` | No | - | UNIQUE, NOT NULL |
| `description` | `TEXT` | Yes | - | - |
| `parent_category_id` | `INTEGER` | Yes | - | - |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Foreign Keys:**

- `parent_category_id` → `categories.category_id` (constraint: `fk_parent_category`)

---

<a name="discounts"></a>

### discounts

[↑ Back to Table List](#table-list)


*Discount codes with complex table-level validation rules*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `discount_id` | `SERIAL` | Yes | - | PK |
| `code` | `VARCHAR(50)` | No | - | UNIQUE, NOT NULL |
| `discount_type` | `VARCHAR(20)` | No | - | NOT NULL |
| `discount_value` | `DECIMAL(10, 2)` | No | - | NOT NULL |
| `minimum_purchase` | `DECIMAL(10, 2)` | Yes | 0 | - |
| `maximum_discount` | `DECIMAL(10, 2)` | Yes | - | - |
| `start_date` | `DATE` | No | - | NOT NULL |
| `end_date` | `DATE` | No | - | NOT NULL |
| `usage_limit` | `INTEGER` | Yes | - | - |

**Table CHECK Constraints:**

- `chk_discount_type`: `discount_type IN ('percentage', 'fixed_amount')`
- `chk_discount_percentage`: `(discount_type = 'percentage' AND discount_value >= 0 AND discount_value <= 100) OR (discount_type = 'fixed_amount' AND discount_value > 0)`
- `chk_discount_dates`: `end_date >= start_date`
- `chk_discount_amounts`: `minimum_purchase >= 0 AND (maximum_discount IS NULL OR maximum_discount > 0)`

---

<a name="inventory"></a>

### inventory

[↑ Back to Table List](#table-list)


*Product inventory with table-level validation constraints*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `inventory_id` | `SERIAL` | Yes | - | PK |
| `product_id` | `INTEGER` | No | - | NOT NULL |
| `warehouse_location` | `VARCHAR(100)` | No | - | NOT NULL |
| `quantity_on_hand` | `INTEGER` | No | - | NOT NULL |
| `quantity_reserved` | `INTEGER` | No | 0 | NOT NULL |
| `reorder_level` | `INTEGER` | No | - | NOT NULL |
| `max_stock_level` | `INTEGER` | No | - | NOT NULL |
| `last_count_date` | `DATE` | Yes | - | - |

**Table CHECK Constraints:**

- `chk_inventory_quantities`: `quantity_on_hand >= 0 AND quantity_reserved >= 0`
- `chk_inventory_reserved`: `quantity_reserved <= quantity_on_hand`
- `chk_reorder_levels`: `reorder_level > 0 AND max_stock_level > reorder_level`

**Foreign Keys:**

- `product_id` → `products.product_id` (constraint: `fk_inventory_product`)

**Indexes:**

- `idx_inventory_location_btree (warehouse_location) USING btree`

---

<a name="order-items"></a>

### order_items

[↑ Back to Table List](#table-list)


*Individual line items within an order*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `order_item_id` | `SERIAL` | Yes | - | PK |
| `order_id` | `INTEGER` | No | - | NOT NULL |
| `product_id` | `INTEGER` | No | - | NOT NULL |
| `quantity` | `INTEGER` | No | - | NOT NULL |
| `unit_price` | `DECIMAL(10, 2)` | No | - | NOT NULL |
| `subtotal` | `DECIMAL(10, 2)` | No | - | NOT NULL |

**Column CHECK Constraints:**

- `quantity`: `quantity > 0`
- `unit_price`: `unit_price >= 0`

**Foreign Keys:**

- `order_id` → `orders.order_id` (constraint: `fk_order_item_order`)
- `product_id` → `products.product_id` (constraint: `fk_order_item_product`)

---

<a name="orders"></a>

### orders

[↑ Back to Table List](#table-list)


*Customer orders with status tracking*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `order_id` | `SERIAL` | Yes | - | PK |
| `user_id` | `UUID` | No | - | NOT NULL |
| `order_number` | `VARCHAR(50)` | No | - | UNIQUE, NOT NULL |
| `status` | `VARCHAR(20)` | No | pending | NOT NULL |
| `total_amount` | `DECIMAL(10, 2)` | No | - | NOT NULL |
| `shipping_address` | `TEXT` | No | - | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Column CHECK Constraints:**

- `status`: `status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled')`
- `total_amount`: `total_amount >= 0`

**Foreign Keys:**

- `user_id` → `users.user_id` (constraint: `fk_order_user`)

**Indexes:**

- `idx_orders_shipping_address_gist (shipping_address) USING gist`

---

<a name="products"></a>

### products

[↑ Back to Table List](#table-list)


*Product catalog with inventory tracking*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `product_id` | `SERIAL` | Yes | - | PK |
| `name` | `VARCHAR(255)` | No | - | NOT NULL |
| `description` | `TEXT` | Yes | - | - |
| `sku` | `VARCHAR(100)` | No | - | UNIQUE, NOT NULL |
| `price` | `DECIMAL(10, 2)` | No | - | NOT NULL |
| `stock_quantity` | `INTEGER` | No | 0 | NOT NULL |
| `category_id` | `INTEGER` | No | - | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Column CHECK Constraints:**

- `price`: `price >= 0`
- `stock_quantity`: `stock_quantity >= 0`

**Foreign Keys:**

- `category_id` → `categories.category_id` (constraint: `fk_product_category`)

**Indexes:**

- `idx_products_description_fulltext (to_tsvector('english', description)) USING gin`

---

<a name="reviews"></a>

### reviews

[↑ Back to Table List](#table-list)


*Product reviews and ratings from users*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `review_id` | `SERIAL` | Yes | - | PK |
| `product_id` | `INTEGER` | No | - | NOT NULL |
| `user_id` | `UUID` | No | - | NOT NULL |
| `rating` | `INTEGER` | No | - | NOT NULL |
| `title` | `VARCHAR(200)` | Yes | - | - |
| `comment` | `TEXT` | Yes | - | - |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Column CHECK Constraints:**

- `rating`: `rating >= 1 AND rating <= 5`

**Foreign Keys:**

- `product_id` → `products.product_id` (constraint: `fk_review_product`)
- `user_id` → `users.user_id` (constraint: `fk_review_user`)

**Indexes:**

- `idx_reviews_comment_fulltext (to_tsvector('english', comment)) USING gin`

---

<a name="users"></a>

### users

[↑ Back to Table List](#table-list)


*User accounts table storing authentication and profile information*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `user_id` | `UUID` | Yes | uuid_generate_v4() | PK |
| `username` | `VARCHAR(50)` | No | - | UNIQUE, NOT NULL |
| `email` | `VARCHAR(255)` | No | - | UNIQUE, NOT NULL |
| `password_hash` | `VARCHAR(255)` | No | - | NOT NULL |
| `first_name` | `VARCHAR(100)` | Yes | - | - |
| `last_name` | `VARCHAR(100)` | Yes | - | - |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `is_active` | `BOOLEAN` | No | TRUE | NOT NULL |
| `last_login` | `TIMESTAMP WITH TIME ZONE` | Yes | - | - |

**Table CHECK Constraints:**

- `chk_email_format`: `email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'`

---

## Relationships

### Foreign Key Relationships

| From Table | From Columns | To Table | To Columns |
|------------|--------------|----------|------------|
| `addresses` | `user_id` | `users` | `user_id` |
| `categories` | `parent_category_id` | `categories` | `category_id` |
| `inventory` | `product_id` | `products` | `product_id` |
| `order_items` | `order_id` | `orders` | `order_id` |
| `order_items` | `product_id` | `products` | `product_id` |
| `orders` | `user_id` | `users` | `user_id` |
| `products` | `category_id` | `categories` | `category_id` |
| `reviews` | `product_id` | `products` | `product_id` |
| `reviews` | `user_id` | `users` | `user_id` |

### Relationship Diagram


Parent-to-Child Relationships:

```

categories
    ├── categories (parent_category_id → category_id)
│   ... (see above)
    └── products (category_id → category_id)
    products
    ├── inventory (product_id → product_id)
    ├── order_items (product_id → product_id)
    └── reviews (product_id → product_id)

users
    ├── addresses (user_id → user_id)
    ├── orders (user_id → user_id)
│   orders
│   │   └── order_items (order_id → order_id)
    └── reviews (user_id → user_id)

Standalone tables (no relationships):
discounts
```
