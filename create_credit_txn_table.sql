-- Create credit transactions table for purchase history
CREATE TABLE IF NOT EXISTS credit_txn (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    product_id VARCHAR(255) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    credits_purchased INT NOT NULL,
    payment_status ENUM('pending', 'completed', 'failed', 'refunded') DEFAULT 'pending',
    stripe_payment_intent_id VARCHAR(255),
    stripe_session_id VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    paid_date TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_product_id (product_id),
    INDEX idx_payment_status (payment_status),
    INDEX idx_stripe_payment_intent (stripe_payment_intent_id),
    INDEX idx_stripe_session (stripe_session_id),
    INDEX idx_paid_date (paid_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
);