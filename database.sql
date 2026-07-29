CREATE DATABASE IF NOT EXISTS svams_db;
USE svams_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('customer','admin','mechanic') DEFAULT 'customer',
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) DEFAULT 0.00
);

CREATE TABLE IF NOT EXISTS bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    service_id INT NOT NULL,
    vehicle_type VARCHAR(50),
    vehicle_number VARCHAR(50),
    booking_date DATE,
    status VARCHAR(20) DEFAULT 'Pending',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    message TEXT NOT NULL,
    rating INT DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id)
);

INSERT INTO services (name, description, price) VALUES
('Oil Change', 'Quick oil replacement service', 49.99),
('Car Wash', 'Exterior and interior cleaning', 29.99),
('Brake Repair', 'Brake pad and rotor inspection', 89.99),
('Engine Repair', 'Advanced engine diagnostics and repair', 149.99),
('Battery Replacement', 'Premium battery replacement', 119.99),
('Tyre Replacement', 'New tyre installation', 79.99),
('Wheel Alignment', 'Precision wheel alignment', 59.99),
('Insurance Claim', 'Claim support and documentation', 39.99),
('Emergency Service', 'Rapid roadside assistance', 99.99);
