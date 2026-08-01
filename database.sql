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
('Oil Change', 'Quick oil replacement service', 1200.00),
('Car Wash', 'Exterior and interior cleaning', 800.00),
('Brake Repair', 'Brake pad and rotor inspection', 3500.00),
('Engine Repair', 'Advanced engine diagnostics and repair', 8000.00),
('Battery Replacement', 'Premium battery replacement', 4500.00),
('Tyre Replacement', 'New tyre installation', 6000.00),
('Wheel Alignment', 'Precision wheel alignment', 2200.00),
('Insurance Claim', 'Claim support and documentation', 1500.00),
('Emergency Service', 'Rapid roadside assistance', 3000.00);
