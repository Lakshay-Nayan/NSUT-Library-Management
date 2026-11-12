
import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": ""
}

DATABASE_NAME = "LIBRARY"


def get_connection():
    return mysql.connector.connect(
        **DB_CONFIG,
        database=DATABASE_NAME
    )


def initialize_database():

    # Connect to MySQL server first
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Create database if it doesn't exist
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}"
    )

    cursor.close()
    connection.close()

    # Connect to the newly created database
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            author VARCHAR(150) NOT NULL,
            isbn VARCHAR(30) UNIQUE,
            category VARCHAR(100),
            total_copies INT NOT NULL DEFAULT 1,
            available_copies INT NOT NULL DEFAULT 1,
            price DECIMAL(10,2) DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            roll_no VARCHAR(30) NOT NULL UNIQUE,
            name VARCHAR(150) NOT NULL,
            email VARCHAR(150),
            phone VARCHAR(20),
            enrollment_year INT NOT NULL,
            student_type VARCHAR(30),
            study_year INT,
            series_code VARCHAR(10),
            class_roll VARCHAR(10)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id INT AUTO_INCREMENT PRIMARY KEY,
            book_id INT NOT NULL,
            student_id INT NOT NULL,
            issue_date DATE NOT NULL,
            due_date DATE NOT NULL,
            return_date DATE NULL,
            status VARCHAR(20) DEFAULT 'Issued',
            FOREIGN KEY (book_id) REFERENCES books(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fines (
            id INT AUTO_INCREMENT PRIMARY KEY,
            issue_id INT NOT NULL,
            student_id INT NOT NULL,
            amount DECIMAL(10,2) NOT NULL DEFAULT 0,
            reason VARCHAR(255) NOT NULL,
            paid BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES issues(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS damages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            issue_id INT NOT NULL,
            description TEXT NOT NULL,
            charge DECIMAL(10,2) NOT NULL DEFAULT 0,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES issues(id)
        )
    """)

    connection.commit()
    cursor.close()
    connection.close()

    print("Database and tables created successfully!")
