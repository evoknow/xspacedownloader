-- Create the email_config table
CREATE TABLE IF NOT EXISTS email_config (
    id INT PRIMARY KEY AUTO_INCREMENT,
    provider VARCHAR(50) NOT NULL COMMENT 'Provider type (sendgrid, mailgun, default-smtp)',
    api_key VARCHAR(255) COMMENT 'API key for the email service provider',
    from_email VARCHAR(100) COMMENT 'From email address',
    from_name VARCHAR(100) COMMENT 'From name to display',
    server VARCHAR(100) COMMENT 'SMTP server address',
    port INT COMMENT 'SMTP server port',
    username VARCHAR(100) COMMENT 'SMTP username',
    password VARCHAR(255) COMMENT 'SMTP password',
    use_tls BOOLEAN DEFAULT TRUE COMMENT 'Whether to use TLS for SMTP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Insert SendGrid configuration
INSERT INTO email_config 
(provider, api_key, from_email, from_name, server, port, username, password, use_tls)
VALUES
(
    'sendgrid', 
    'YOUR_SENDGRID_API_KEY',
    'noreply@xspacedownload.com', 
    'X Space Downloader',
    NULL, NULL, NULL, NULL, TRUE
);

-- Insert Mailgun configuration
INSERT INTO email_config 
(provider, api_key, from_email, from_name, server, port, username, password, use_tls)
VALUES
(
    'mailgun', 
    'YOUR_SENDGRID_API_KEY',
    'noreply@xspacedownload.com', 
    'X Space Downloader',
    NULL, NULL, NULL, NULL, TRUE
);

-- Insert SMTP configuration
INSERT INTO email_config 
(provider, api_key, from_email, from_name, server, port, username, password, use_tls)
VALUES
(
    'default-smtp', 
    NULL,
    'your_email@gmail.com', 
    'X Space Downloader',
    'smtp.gmail.com', 
    587, 
    'your_email@gmail.com', 
    'your_app_password',
    TRUE
);