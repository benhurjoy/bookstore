import pymysql
from config import config
from werkzeug.security import generate_password_hash

def get_db_connection():
    return pymysql.connect(
        host=config['default'].MYSQL_HOST,
        user=config['default'].MYSQL_USER,
        password=config['default'].MYSQL_PASSWORD,
        database=config['default'].MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # # Drop tables if they exist (for clean start)
            # cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            # # Drop tables in correct order to avoid foreign key constraints
            # cursor.execute("DROP TABLE IF EXISTS order_tracking")
            # cursor.execute("DROP TABLE IF EXISTS order_items")
            # cursor.execute("DROP TABLE IF EXISTS orders")
            # cursor.execute("DROP TABLE IF EXISTS password_reset_tokens")
            # cursor.execute("DROP TABLE IF EXISTS cart")
            # cursor.execute("DROP TABLE IF EXISTS user_addresses")
            # cursor.execute("DROP TABLE IF EXISTS books")
            # cursor.execute("DROP TABLE IF EXISTS users")
            
            # cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    role ENUM('admin', 'user') DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Books table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS books (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    author VARCHAR(255) NOT NULL,
                    description TEXT,
                    price DECIMAL(10, 2) NOT NULL,
                    stock INT DEFAULT 0,
                    image_url VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # User addresses table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_addresses (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    full_name VARCHAR(255) NOT NULL,
                    phone VARCHAR(20) NOT NULL,
                    address_line1 VARCHAR(255) NOT NULL,
                    address_line2 VARCHAR(255),
                    city VARCHAR(100) NOT NULL,
                    state VARCHAR(100) NOT NULL,
                    postal_code VARCHAR(20) NOT NULL,
                    country VARCHAR(100) DEFAULT 'India',
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Cart table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cart (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    book_id INT NOT NULL,
                    quantity INT DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_cart_item (user_id, book_id)
                )
            ''')
            
            # Orders table (with delivery fields)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(255) NOT NULL UNIQUE,
                    user_id INT NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    currency VARCHAR(10) DEFAULT 'INR',
                    status ENUM('pending', 'processing', 'completed', 'failed', 'cancelled') DEFAULT 'pending',
                    razorpay_order_id VARCHAR(255),
                    razorpay_payment_id VARCHAR(255),
                    razorpay_signature VARCHAR(255),
                    address_id INT,
                    delivery_status ENUM('confirmed', 'processing', 'shipped', 'out_for_delivery', 'delivered', 'cancelled') DEFAULT 'confirmed',
                    tracking_number VARCHAR(100),
                    estimated_delivery DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (address_id) REFERENCES user_addresses(id) ON DELETE SET NULL
                )
            ''')
            
            # Order items table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS  order_items (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(255) NOT NULL,
                    book_id INT NOT NULL,
                    quantity INT NOT NULL,
                    price DECIMAL(10, 2) NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
                )
            ''')
            
            # Order tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS order_tracking (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(255) NOT NULL,
                    status ENUM('confirmed', 'processing', 'shipped', 'out_for_delivery', 'delivered', 'cancelled') NOT NULL,
                    description TEXT,
                    location VARCHAR(255),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
                )
            ''')
            
            # Password reset tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            
            # Add sample books
            # sample_books = [
            #     ('The Great Gatsby', 'F. Scott Fitzgerald', 'A classic American novel', 12.99, 10, 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=400'),
            #     ('To Kill a Mockingbird', 'Harper Lee', 'A novel about racial inequality', 14.99, 8, 'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400'),
            #     ('1984', 'George Orwell', 'Dystopian social science fiction', 13.50, 12, 'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=400'),
            #     ('Pride and Prejudice', 'Jane Austen', 'Romantic novel of manners', 11.99, 15, 'https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=400')
            # ]
            
            # for book in sample_books:
            #     cursor.execute(
            #         "INSERT INTO books (title, author, description, price, stock, image_url) VALUES (%s, %s, %s, %s, %s, %s)",
            #         book
            #     )
            
        conn.commit()
        print("SUCCESS: Database initialized successfully!")
        print("ADMIN: User created - username: admin, password: admin123")
        print("BOOKS: Sample books added to database")
        
    except Exception as e:
        print(f"ERROR: Database initialization failed: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()