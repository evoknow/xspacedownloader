-- Create products table
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(255) PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    description TEXT,
    status ENUM('active', 'inactive') DEFAULT 'active',
    credits INT NOT NULL,
    recurring_credits ENUM('yes', 'no') DEFAULT 'no',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sku (sku),
    INDEX idx_status (status),
    INDEX idx_price (price)
);

-- Insert product data
INSERT INTO products (id, sku, name, price, description, status, credits, recurring_credits) VALUES
('prod_SZv5bRmgWKThHM_1', 'CR-10', '100 credits for $10', 10.00, '100 credits that do not expire. You can use these credits for compute (MP3, MP4) or AI tasks such as transcription, translation, summary and text to speech tools within our site.', 'active', 100, 'no'),
('prod_SZv5bRmgWKThHM_2', 'CR-20', '500 credits for $20', 20.00, '500 credits that do not expire. You can use these credits for compute (MP3, MP4) or AI tasks such as transcription, translation, summary and text to speech tools within our site.', 'active', 500, 'no'),
('prod_SZv5bRmgWKThHM_3', 'CR-30', '1000 credits for $30', 30.00, '1000 credits that do not expire. You can use these credits for compute (MP3, MP4) or AI tasks such as transcription, translation, summary and text to speech tools within our site.', 'active', 1000, 'no'),
('prod_SZv5bRmgWKThHM_4', 'CR-99', '1000 credits per month for $99', 99.00, '1000 credits per month. Credits reset to 1000 every month for as long as we are in business. You can use these credits for compute (MP3, MP4) or AI tasks such as transcription, translation, summary and text to speech tools within our site.', 'active', 1000, 'yes');