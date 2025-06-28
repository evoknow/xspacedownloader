-- Add product image field to products table
ALTER TABLE products 
ADD COLUMN image_url VARCHAR(500) DEFAULT NULL AFTER description,
ADD INDEX idx_image_url (image_url);