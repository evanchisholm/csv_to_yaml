# Database Schema Documentation

## Entity Overview

This schema contains **7** table(s):

- `addresses` (PK: address_id)
- `categories` (PK: category_id)
- `order_items` (PK: order_item_id)
- `orders` (PK: order_id)
- `products` (PK: product_id)
- `reviews` (PK: review_id)
- `users` (PK: user_id)

## Tables

### addresses

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
| `is_default` | `BOOLEAN` | No | BOOLEAN NOT NULL DEFAULT FALSE | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Foreign Keys:**

- `user_id` → `users.user_id` (constraint: `fk_address_user`)

**Indexes:**

- `idx_addresses_user (user_id)`

---

### categories

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

### order_items

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

**Foreign Keys:**

- `order_id` → `orders.order_id` (constraint: `fk_order_item_order`)
- `product_id` → `products.product_id` (constraint: `fk_order_item_product`)

**Indexes:**

- `idx_order_items_order (order_id)`
- `idx_order_items_product (product_id)`

---

### orders

*Customer orders with status tracking*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `order_id` | `SERIAL` | Yes | - | PK |
| `user_id` | `UUID` | No | - | NOT NULL |
| `order_number` | `VARCHAR(50)` | No | - | UNIQUE, NOT NULL |
| `status` | `VARCHAR(20)` | No | pending' CHECK (status IN ('pending | NOT NULL |
| `total_amount` | `DECIMAL(10, 2)` | No | - | NOT NULL |
| `shipping_address` | `TEXT` | No | - | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Foreign Keys:**

- `user_id` → `users.user_id` (constraint: `fk_order_user`)

**Indexes:**

- `idx_orders_user (user_id)`
- `idx_orders_status (status)`
- `idx_orders_created (created_at DESC)`

---

### products

*Product catalog with inventory tracking*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `product_id` | `SERIAL` | Yes | - | PK |
| `name` | `VARCHAR(255)` | No | - | NOT NULL |
| `description` | `TEXT` | Yes | - | - |
| `sku` | `VARCHAR(100)` | No | - | UNIQUE, NOT NULL |
| `price` | `DECIMAL(10, 2)` | No | - | NOT NULL |
| `stock_quantity` | `INTEGER` | No | 0 CHECK (stock_quantity >= 0 | NOT NULL |
| `category_id` | `INTEGER` | No | - | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |

**Foreign Keys:**

- `category_id` → `categories.category_id` (constraint: `fk_product_category`)

**Indexes:**

- `idx_products_category (category_id)`
- `idx_products_category_price (category_id, price)`

---

### reviews

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

**Foreign Keys:**

- `product_id` → `products.product_id` (constraint: `fk_review_product`)
- `user_id` → `users.user_id` (constraint: `fk_review_user`)

**Indexes:**

- `idx_reviews_product (product_id)`
- `idx_reviews_user (user_id)`

---

### users

*User accounts table storing authentication and profile information*

**Columns:**

| Column Name | Data Type | Nullable | Default | Constraints |
|-------------|-----------|----------|---------|-------------|
| `user_id` | `UUID` | Yes | uuid_generate_v4( | PK |
| `username` | `VARCHAR(50)` | No | - | UNIQUE, NOT NULL |
| `email` | `VARCHAR(255)` | No | - | UNIQUE, NOT NULL |
| `password_hash` | `VARCHAR(255)` | No | - | NOT NULL |
| `first_name` | `VARCHAR(100)` | Yes | - | - |
| `last_name` | `VARCHAR(100)` | Yes | - | - |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | No | CURRENT_TIMESTAMP | NOT NULL |
| `is_active` | `BOOLEAN` | No | TRUE | NOT NULL |
| `last_login` | `TIMESTAMP WITH TIME ZONE` | Yes | - | - |

**Indexes:**

- `idx_users_email_lower (LOWER(email)`

---

## Relationships

### Foreign Key Relationships

| From Table | From Columns | To Table | To Columns |
|------------|--------------|----------|------------|
| `addresses` | `user_id` | `users` | `user_id` |
| `categories` | `parent_category_id` | `categories` | `category_id` |
| `order_items` | `order_id` | `orders` | `order_id` |
| `order_items` | `product_id` | `products` | `product_id` |
| `orders` | `user_id` | `users` | `user_id` |
| `products` | `category_id` | `categories` | `category_id` |
| `reviews` | `product_id` | `products` | `product_id` |
| `reviews` | `user_id` | `users` | `user_id` |

### Relationship Diagram

```

addresses (user_id) --> users (user_id)
categories (parent_category_id) --> categories (category_id)
order_items (order_id) --> orders (order_id)
order_items (product_id) --> products (product_id)
orders (user_id) --> users (user_id)
products (category_id) --> categories (category_id)
reviews (product_id) --> products (product_id)
reviews (user_id) --> users (user_id)
```
