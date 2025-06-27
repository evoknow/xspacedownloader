-- Affiliate System Tables

-- Table to track affiliate visits and conversions
CREATE TABLE IF NOT EXISTS affiliate_tracking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    affiliate_user_id INT NOT NULL,
    visitor_ip VARCHAR(45),
    visitor_user_agent TEXT,
    visit_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    converted_user_id INT DEFAULT NULL,
    conversion_time DATETIME DEFAULT NULL,
    status ENUM('visited', 'registered', 'verified', 'rejected') DEFAULT 'visited',
    FOREIGN KEY (affiliate_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (converted_user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_affiliate_user (affiliate_user_id),
    INDEX idx_converted_user (converted_user_id),
    INDEX idx_visit_time (visit_time),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table to track affiliate earnings
CREATE TABLE IF NOT EXISTS affiliate_earnings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    affiliate_user_id INT NOT NULL,
    referred_user_id INT NOT NULL,
    credits_earned DECIMAL(10,2) DEFAULT 0,
    money_earned DECIMAL(10,2) DEFAULT 0,
    earned_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    credit_status ENUM('pending', 'approved', 'paid', 'rejected') DEFAULT 'pending',
    money_status ENUM('pending', 'approved', 'paid', 'rejected') DEFAULT 'pending',
    credit_approved_date DATETIME DEFAULT NULL,
    money_approved_date DATETIME DEFAULT NULL,
    credit_paid_date DATETIME DEFAULT NULL,
    money_paid_date DATETIME DEFAULT NULL,
    notes TEXT,
    FOREIGN KEY (affiliate_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (referred_user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_affiliate_earnings (affiliate_user_id),
    INDEX idx_referred_user (referred_user_id),
    INDEX idx_earned_date (earned_date),
    INDEX idx_credit_status (credit_status),
    INDEX idx_money_status (money_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table to track affiliate payouts
CREATE TABLE IF NOT EXISTS affiliate_payouts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    payout_type ENUM('credit', 'money') NOT NULL,
    created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id INT NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    user_count INT NOT NULL,
    status ENUM('created', 'processing', 'completed', 'cancelled') DEFAULT 'created',
    csv_filename VARCHAR(255) DEFAULT NULL,
    notes TEXT,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_created_date (created_date),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for affiliate payout details
CREATE TABLE IF NOT EXISTS affiliate_payout_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    payout_id INT NOT NULL,
    user_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    status ENUM('pending', 'paid', 'failed') DEFAULT 'pending',
    paid_date DATETIME DEFAULT NULL,
    transaction_reference VARCHAR(255) DEFAULT NULL,
    FOREIGN KEY (payout_id) REFERENCES affiliate_payouts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_payout (payout_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for affiliate settings
CREATE TABLE IF NOT EXISTS affiliate_settings (
    id INT PRIMARY KEY DEFAULT 1,
    credits_per_registration DECIMAL(10,2) DEFAULT 10.00,
    money_per_registration DECIMAL(10,2) DEFAULT 0.50,
    minimum_payout_amount DECIMAL(10,2) DEFAULT 20.00,
    tax_reporting_threshold DECIMAL(10,2) DEFAULT 600.00,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by_user_id INT DEFAULT NULL,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert default affiliate settings
INSERT INTO affiliate_settings (credits_per_registration, money_per_registration, minimum_payout_amount, tax_reporting_threshold)
VALUES (10.00, 0.50, 20.00, 600.00)
ON DUPLICATE KEY UPDATE id=id;