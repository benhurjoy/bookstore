from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from models import get_db_connection, init_db
from config import config
import functools
import razorpay
import json
import time
import secrets
from datetime import datetime, timedelta
app = Flask(__name__)
app.config.from_object(config['default'])
mail = Mail(app)
# Initialize Razorpay client
razorpay_client = razorpay.Client(
    auth=(app.config['RAZORPAY_KEY_ID'], app.config['RAZORPAY_KEY_SECRET'])
)

# Initialize database
try:
    init_db()
except Exception as e:
    print(f"Database initialization failed: {e}")
    print("Please check your MySQL connection and database configuration")

def login_required(role=None):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in first.', 'danger')
                return redirect(url_for('login'))
            
            if role and session.get('role') != role:
                flash('Access denied.', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM books WHERE stock > 0 LIMIT 6")
            books = cursor.fetchall()
    finally:
        conn.close()
    
    return render_template('index.html', books=books)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check if user exists
                cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
                if cursor.fetchone():
                    flash('Username or email already exists', 'danger')
                    return render_template('register.html')
                
                # Create new user
                hashed_password = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                    (username, email, hashed_password)
                )
                conn.commit()
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
        finally:
            conn.close()
    
    return render_template('register.html')
def update_cart_count():
    """Update cart count in session"""
    if 'user_id' in session and session.get('role') == 'user':
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM cart WHERE user_id = %s", (session['user_id'],))
                cart_count = cursor.fetchone()['count']
                session['cart_count'] = cart_count
        except Exception as e:
            print(f"Error updating cart count: {e}")
            session['cart_count'] = 0
        finally:
            conn.close()
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                
                if user and check_password_hash(user['password'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['role'] = user['role']
                    update_cart_count()
                    flash('Login successful!', 'success')
                    
                    if user['role'] == 'admin':
                        return redirect(url_for('admin_dashboard'))
                    else:
                        return redirect(url_for('user_dashboard'))
                else:
                    flash('Invalid credentials', 'danger')
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# Admin Routes
@app.route('/admin/dashboard')
@login_required(role='admin')
def admin_dashboard():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total_books FROM books")
            total_books = cursor.fetchone()['total_books']
            
            cursor.execute("SELECT COUNT(*) as total_users FROM users WHERE role = 'user'")
            total_users = cursor.fetchone()['total_users']
            
            cursor.execute("SELECT * FROM books ORDER BY created_at DESC LIMIT 5")
            recent_books = cursor.fetchall()
    finally:
        conn.close()
    
    return render_template('admin/dashboard.html', 
                         total_books=total_books, 
                         total_users=total_users,
                         recent_books=recent_books)

@app.route('/admin/books')
@login_required(role='admin')
def admin_books():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM books ORDER BY created_at DESC")
            books = cursor.fetchall()
    finally:
        conn.close()
    
    return render_template('admin/books.html', books=books)

@app.route('/admin/add_book', methods=['GET', 'POST'])
@login_required(role='admin')
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        description = request.form['description']
        price = request.form['price']
        stock = request.form['stock']
        image_url = request.form['image_url'] or '/static/images/default-book.jpg'
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO books (title, author, description, price, stock, image_url) VALUES (%s, %s, %s, %s, %s, %s)",
                    (title, author, description, price, stock, image_url)
                )
                conn.commit()
                flash('Book added successfully!', 'success')
                return redirect(url_for('admin_books'))
        finally:
            conn.close()
    
    return render_template('admin/add_book.html')

@app.route('/admin/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required(role='admin')
def edit_book(book_id):
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            title = request.form['title']
            author = request.form['author']
            description = request.form['description']
            price = request.form['price']
            stock = request.form['stock']
            image_url = request.form['image_url']
            
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE books SET title=%s, author=%s, description=%s, price=%s, stock=%s, image_url=%s WHERE id=%s",
                    (title, author, description, price, stock, image_url, book_id)
                )
                conn.commit()
                flash('Book updated successfully!', 'success')
                return redirect(url_for('admin_books'))
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM books WHERE id = %s", (book_id,))
            book = cursor.fetchone()
            
        if not book:
            flash('Book not found', 'danger')
            return redirect(url_for('admin_books'))
            
        return render_template('admin/edit_book.html', book=book)
    finally:
        conn.close()

@app.route('/admin/delete_book/<int:book_id>')
@login_required(role='admin')
def delete_book(book_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))
            conn.commit()
            flash('Book deleted successfully!', 'success')
    finally:
        conn.close()
    
    return redirect(url_for('admin_books'))

# User Routes
@app.route('/user/dashboard')
@login_required()
def user_dashboard():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM books WHERE stock > 0 LIMIT 8")
            books = cursor.fetchall()
    finally:
        conn.close()
    
    return render_template('user/dashboard.html', books=books)

@app.route('/user/books')
@login_required()
def user_books():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM books WHERE stock > 0")
            books = cursor.fetchall()
    finally:
        conn.close()
    
    return render_template('user/books.html', books=books)

@app.route('/add_to_cart/<int:book_id>')
@login_required()
def add_to_cart(book_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Checking if book exists and is in stock
            cursor.execute("SELECT * FROM books WHERE id = %s AND stock > 0", (book_id,))
            book = cursor.fetchone()
            
            if not book:
                flash('Book not available', 'danger')
                return redirect(url_for('user_books'))
            
            # Checking if book is already in cart
            cursor.execute("SELECT * FROM cart WHERE user_id = %s AND book_id = %s", (session['user_id'], book_id))
            existing_item = cursor.fetchone()
            
            if existing_item:
                cursor.execute("UPDATE cart SET quantity = quantity + 1 WHERE id = %s", (existing_item['id'],))
            else:
                cursor.execute("INSERT INTO cart (user_id, book_id) VALUES (%s, %s)", (session['user_id'], book_id))
            
            conn.commit()
            update_cart_count()
            flash('Book added to cart!', 'success')
    finally:
        conn.close()
    
    return redirect(url_for('user_books'))

@app.route('/cart')
@login_required()
def cart():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT c.*, b.title, b.author, b.price, b.image_url, (b.price * c.quantity) as total_price
                FROM cart c 
                JOIN books b ON c.book_id = b.id 
                WHERE c.user_id = %s
            ''', (session['user_id'],))
            cart_items = cursor.fetchall()
            
            total_amount = sum(item['total_price'] for item in cart_items)
    finally:
        conn.close()
    
    return render_template('user/cart.html', cart_items=cart_items, total_amount=total_amount)

@app.route('/update_cart/<int:cart_id>', methods=['POST'])
@login_required()
def update_cart(cart_id):
    quantity = int(request.form['quantity'])
    
    if quantity <= 0:
        return remove_from_cart(cart_id)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s AND user_id = %s", 
                         (quantity, cart_id, session['user_id']))
            conn.commit()
    finally:
        conn.close()
    update_cart_count()
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:cart_id>')
@login_required()
def remove_from_cart(cart_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM cart WHERE id = %s AND user_id = %s", (cart_id, session['user_id']))
            conn.commit()
    finally:
        conn.close()
    update_cart_count()
    return redirect(url_for('cart'))
@app.route('/checkout', methods=['GET', 'POST'])
@login_required()
def checkout():
    if request.method == 'POST':
        address_id = request.form['address_id']
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Verify address belongs to user
                cursor.execute("SELECT * FROM user_addresses WHERE id = %s AND user_id = %s", (address_id, session['user_id']))
                address = cursor.fetchone()
                
                if not address:
                    flash('Invalid address selected', 'danger')
                    return redirect(url_for('checkout'))
                
                # Get cart items
                cursor.execute('''
                    SELECT c.*, b.title, b.stock, b.price
                    FROM cart c 
                    JOIN books b ON c.book_id = b.id 
                    WHERE c.user_id = %s
                ''', (session['user_id'],))
                cart_items = cursor.fetchall()
                
                if not cart_items:
                    flash('Your cart is empty', 'danger')
                    return redirect(url_for('cart'))
                
                # Check stock
                for item in cart_items:
                    if item['stock'] < item['quantity']:
                        flash(f'Not enough stock for {item["title"]}', 'danger')
                        return redirect(url_for('cart'))
                
                total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
                
                # For Razorpay integration, we'll create the order after payment
                # For now, just store the address selection in session
                session['selected_address_id'] = address_id
                session['checkout_total'] = float(total_amount)
                session['checkout_items'] = [{
                    'book_id': item['book_id'],
                    'quantity': item['quantity'],
                    'price': float(item['price'])
                } for item in cart_items]
                
                # Redirect to payment
                return redirect(url_for('payment'))
                
        except Exception as e:
            print(f"Error during checkout: {e}")
            flash('Error processing order. Please try again.', 'danger')
            return redirect(url_for('cart'))
        finally:
            conn.close()
    
    # GET request - show address selection
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get user addresses
            cursor.execute("SELECT * FROM user_addresses WHERE user_id = %s ORDER BY is_default DESC", (session['user_id'],))
            addresses = cursor.fetchall()
            
            # Get cart total
            cursor.execute('''
                SELECT SUM(b.price * c.quantity) as total
                FROM cart c 
                JOIN books b ON c.book_id = b.id 
                WHERE c.user_id = %s
            ''', (session['user_id'],))
            cart_total = cursor.fetchone()['total'] or 0
            
    except Exception as e:
        print(f"Error loading checkout: {e}")
        addresses = []
        cart_total = 0
    finally:
        conn.close()
    
    if not addresses:
        flash('Please add a delivery address before checkout.', 'warning')
        return redirect(url_for('add_address'))
    
    return render_template('user/checkout.html', addresses=addresses, cart_total=cart_total)

# Update the create_order route to use address from session
@app.route('/create_order', methods=['POST'])
@login_required()
def create_order():
    # Check if we have checkout data in session
    if 'selected_address_id' not in session or 'checkout_total' not in session:
        flash('Please complete the checkout process first.', 'danger')
        return redirect(url_for('cart'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            total_amount = session['checkout_total']
            amount_in_paise = int(total_amount * 100)  # Razorpay expects amount in paise
            
            # Create Razorpay order
            order_data = {
                'amount': amount_in_paise,
                'currency': 'INR',
                'payment_capture': 1  # Auto capture payment
            }
            
            razorpay_order = razorpay_client.order.create(order_data)
            
            # Generate unique order ID
            order_id = f"ORDER_{int(time.time())}_{session['user_id']}"
            
            # Calculate estimated delivery (7 days from now)
            from datetime import datetime, timedelta
            estimated_delivery = datetime.now() + timedelta(days=7)
            
            # Generate tracking number
            tracking_number = f"TRK{int(time.time())}{session['user_id']}"
            
            # Save order to database (with address)
            cursor.execute(
                "INSERT INTO orders (order_id, user_id, amount, address_id, tracking_number, estimated_delivery, status, razorpay_order_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (order_id, session['user_id'], total_amount, session['selected_address_id'], tracking_number, estimated_delivery, 'pending', razorpay_order['id'])
            )
            
            # Save order items
            for item in session['checkout_items']:
                cursor.execute(
                    "INSERT INTO order_items (order_id, book_id, quantity, price) VALUES (%s, %s, %s, %s)",
                    (order_id, item['book_id'], item['quantity'], item['price'])
                )
            
            # Add initial tracking entry
            cursor.execute('''
                INSERT INTO order_tracking (order_id, status, description, location)
                VALUES (%s, 'confirmed', 'Order has been confirmed and is being processed.', 'Warehouse')
            ''', (order_id,))
            
            conn.commit()
            
            # Store order_id in session for payment verification
            session['current_order_id'] = order_id
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'razorpay_order_id': razorpay_order['id'],
                'amount': amount_in_paise,
                'key': app.config['RAZORPAY_KEY_ID'],
                'name': 'BookStore',
                'description': 'Book Purchase',
                'prefill': {
                    'name': session.get('username', ''),
                    'email': '',  # You can store user email and prefill it
                },
                'theme': {
                    'color': '#3399cc'
                }
            })
            
    except Exception as e:
        print(f"Error creating order: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# Update payment_success to complete the order
@app.route('/payment_success', methods=['POST'])
@login_required()
def payment_success():
    try:
        # Get payment details from request
        razorpay_payment_id = request.form.get('razorpay_payment_id')
        razorpay_order_id = request.form.get('razorpay_order_id')
        razorpay_signature = request.form.get('razorpay_signature')
        order_id = session.get('current_order_id')
        
        if not order_id:
            flash('Order session expired. Please try again.', 'danger')
            return redirect(url_for('cart'))
        
        # Verify payment signature
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }
        
        try:
            razorpay_client.utility.verify_payment_signature(params_dict)
            payment_verified = True
        except razorpay.errors.SignatureVerificationError:
            payment_verified = False
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if payment_verified:
                    # Payment successful - update order status
                    cursor.execute(
                        "UPDATE orders SET status = 'completed', razorpay_payment_id = %s, razorpay_signature = %s WHERE order_id = %s",
                        (razorpay_payment_id, razorpay_signature, order_id)
                    )
                    
                    # Update book stock
                    for item in session.get('checkout_items', []):
                        cursor.execute(
                            "UPDATE books SET stock = stock - %s WHERE id = %s",
                            (item['quantity'], item['book_id'])
                        )
                    
                    # Clear cart
                    cursor.execute("DELETE FROM cart WHERE user_id = %s", (session['user_id'],))
                    
                    conn.commit()
                    
                    # Clear checkout session data
                    session.pop('selected_address_id', None)
                    session.pop('checkout_total', None)
                    session.pop('checkout_items', None)
                    session.pop('current_order_id', None)
                    
                    # Update cart count
                    update_cart_count()
                    
                    flash('Payment successful! Your order has been placed.', 'success')
                    return redirect(url_for('order_confirmation', order_id=order_id))
                else:
                    # Payment failed - update order status
                    cursor.execute(
                        "UPDATE orders SET status = 'failed' WHERE order_id = %s",
                        (order_id,)
                    )
                    conn.commit()
                    
                    flash('Payment verification failed. Please try again.', 'danger')
                    return redirect(url_for('cart'))
                    
        except Exception as e:
            print(f"Error processing payment: {e}")
            conn.rollback()
            flash('Error processing payment. Please contact support.', 'danger')
            return redirect(url_for('cart'))
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Error in payment success: {e}")
        flash('Error processing payment. Please contact support.', 'danger')
        return redirect(url_for('cart'))

# Simple checkout for testing (without payment)
@app.route('/direct_checkout', methods=['POST'])
@login_required()
def direct_checkout():
    """Direct checkout without payment for testing"""
    address_id = request.form['address_id']
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Verify address belongs to user
            cursor.execute("SELECT * FROM user_addresses WHERE id = %s AND user_id = %s", (address_id, session['user_id']))
            address = cursor.fetchone()
            
            if not address:
                flash('Invalid address selected', 'danger')
                return redirect(url_for('checkout'))
            
            # Get cart items
            cursor.execute('''
                SELECT c.*, b.title, b.stock, b.price
                FROM cart c 
                JOIN books b ON c.book_id = b.id 
                WHERE c.user_id = %s
            ''', (session['user_id'],))
            cart_items = cursor.fetchall()
            
            if not cart_items:
                flash('Your cart is empty', 'danger')
                return redirect(url_for('cart'))
            
            # Check stock
            for item in cart_items:
                if item['stock'] < item['quantity']:
                    flash(f'Not enough stock for {item["title"]}', 'danger')
                    return redirect(url_for('cart'))
            
            total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
            order_id = f"ORDER_{int(time.time())}_{session['user_id']}"
            
            # Calculate estimated delivery (7 days from now)
            from datetime import datetime, timedelta
            estimated_delivery = datetime.now() + timedelta(days=7)
            
            # Generate tracking number
            tracking_number = f"TRK{int(time.time())}{session['user_id']}"
            
            # Create order with address
            cursor.execute('''
                INSERT INTO orders (order_id, user_id, amount, address_id, tracking_number, estimated_delivery, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'completed')
            ''', (order_id, session['user_id'], total_amount, address_id, tracking_number, estimated_delivery))
            
            # Save order items
            for item in cart_items:
                cursor.execute(
                    "INSERT INTO order_items (order_id, book_id, quantity, price) VALUES (%s, %s, %s, %s)",
                    (order_id, item['book_id'], item['quantity'], item['price'])
                )
                
                # Update stock
                cursor.execute(
                    "UPDATE books SET stock = stock - %s WHERE id = %s",
                    (item['quantity'], item['book_id'])
                )
            
            # Add order tracking entry
            cursor.execute('''
                INSERT INTO order_tracking (order_id, status, description, location)
                VALUES (%s, 'confirmed', 'Order has been confirmed and is being processed.', 'Warehouse')
            ''', (order_id,))
            
            # Clear cart
            cursor.execute("DELETE FROM cart WHERE user_id = %s", (session['user_id'],))
            
            conn.commit()
            
            # Update cart count
            update_cart_count()
            
            flash('Order placed successfully! Your books will be delivered soon.', 'success')
            return redirect(url_for('order_confirmation', order_id=order_id))
            
    except Exception as e:
        print(f"Error during direct checkout: {e}")
        conn.rollback()
        flash('Error processing order. Please try again.', 'danger')
        return redirect(url_for('cart'))
    finally:
        conn.close()

@app.route('/order_confirmation/<order_id>')
@login_required()
def order_confirmation(order_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get order details
            cursor.execute('''
                SELECT o.*, oi.book_id, oi.quantity, oi.price, b.title, b.author, b.image_url
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                JOIN books b ON oi.book_id = b.id
                WHERE o.order_id = %s AND o.user_id = %s
            ''', (order_id, session['user_id']))
            order_items = cursor.fetchall()
            
            if not order_items:
                flash('Order not found', 'danger')
                return redirect(url_for('user_dashboard'))
            
            order_total = order_items[0]['amount']
            
    except Exception as e:
        print(f"Error fetching order: {e}")
        flash('Error loading order details', 'danger')
        return redirect(url_for('user_dashboard'))
    finally:
        conn.close()
    
    return render_template('user/order_confirmation.html', 
                         order_items=order_items, 
                         order_id=order_id, 
                         order_total=order_total)

@app.route('/order_history')
@login_required()
def order_history():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT o.*, 
                       (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id) as item_count
                FROM orders o 
                WHERE o.user_id = %s 
                ORDER BY o.created_at DESC
            ''', (session['user_id'],))
            orders = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching order history: {e}")
        orders = []
    finally:
        conn.close()
    
    return render_template('user/order_history.html', orders=orders)
# Add these routes to your app.py

# Search Routes
@app.route('/search')
def search_books():
    query = request.args.get('q', '').strip()
    
    if not query:
        return redirect(url_for('user_books'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Search in title, author, and description
            search_query = f"%{query}%"
            cursor.execute('''
                SELECT * FROM books 
                WHERE (title LIKE %s OR author LIKE %s OR description LIKE %s) 
                AND stock > 0
                ORDER BY 
                    CASE 
                        WHEN title LIKE %s THEN 1
                        WHEN author LIKE %s THEN 2
                        ELSE 3
                    END,
                    title
            ''', (search_query, search_query, search_query, search_query, search_query))
            books = cursor.fetchall()
            
            # Get search result count
            cursor.execute('''
                SELECT COUNT(*) as count FROM books 
                WHERE (title LIKE %s OR author LIKE %s OR description LIKE %s) 
                AND stock > 0
            ''', (search_query, search_query, search_query))
            result_count = cursor.fetchone()['count']
            
    except Exception as e:
        print(f"Error searching books: {e}")
        books = []
        result_count = 0
    finally:
        conn.close()
    
    return render_template('user/search_results.html', 
                         books=books, 
                         query=query, 
                         result_count=result_count)

@app.route('/admin/search')
@login_required(role='admin')
def admin_search_books():
    query = request.args.get('q', '').strip()
    
    if not query:
        return redirect(url_for('admin_books'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Search in title, author, and description (all books including out of stock)
            search_query = f"%{query}%"
            cursor.execute('''
                SELECT * FROM books 
                WHERE title LIKE %s OR author LIKE %s OR description LIKE %s
                ORDER BY 
                    CASE 
                        WHEN title LIKE %s THEN 1
                        WHEN author LIKE %s THEN 2
                        ELSE 3
                    END,
                    title
            ''', (search_query, search_query, search_query, search_query, search_query))
            books = cursor.fetchall()
            
            # Get search result count
            cursor.execute('''
                SELECT COUNT(*) as count FROM books 
                WHERE title LIKE %s OR author LIKE %s OR description LIKE %s
            ''', (search_query, search_query, search_query))
            result_count = cursor.fetchone()['count']
            
    except Exception as e:
        print(f"Error searching books: {e}")
        books = []
        result_count = 0
    finally:
        conn.close()
    
    return render_template('admin/search_results.html', 
                         books=books, 
                         query=query, 
                         result_count=result_count)
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check if user exists
                cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
                
                if user:
                    # Generate reset token
                    token = secrets.token_urlsafe(32)
                    expires_at = datetime.now() + timedelta(hours=1)  # Token valid for 1 hour
                    
                    # Save token to database
                    cursor.execute(
                        "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
                        (user['id'], token, expires_at)
                    )
                    
                    # Send reset email
                    reset_url = url_for('reset_password', token=token, _external=True)
                    
                    try:
                        msg = Message(
                            subject='Password Reset Request - BookStore',
                            recipients=[email],
                            html=render_template('email/reset_password.html', 
                                               username=user['username'], 
                                               reset_url=reset_url)
                        )
                        mail.send(msg)
                        flash('Password reset link has been sent to your email.', 'success')
                    except Exception as e:
                        print(f"Error sending email: {e}")
                        flash('Error sending email. Please try again.', 'danger')
                    
                else:
                    flash('If that email exists, a reset link has been sent.', 'success')  # Don't reveal if email exists
                
                conn.commit()
                
        except Exception as e:
            print(f"Error in forgot password: {e}")
            flash('An error occurred. Please try again.', 'danger')
        finally:
            conn.close()
    
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Validate token
            cursor.execute('''
                SELECT prt.*, u.username 
                FROM password_reset_tokens prt 
                JOIN users u ON prt.user_id = u.id 
                WHERE prt.token = %s AND prt.used = FALSE AND prt.expires_at > %s
            ''', (token, datetime.now()))
            
            token_data = cursor.fetchone()
            
            if not token_data:
                flash('Invalid or expired reset link.', 'danger')
                return redirect(url_for('forgot_password'))
            
            if request.method == 'POST':
                new_password = request.form['password']
                confirm_password = request.form['confirm_password']
                
                if new_password != confirm_password:
                    flash('Passwords do not match.', 'danger')
                    return render_template('reset_password.html', token=token)
                
                if len(new_password) < 6:
                    flash('Password must be at least 6 characters long.', 'danger')
                    return render_template('reset_password.html', token=token)
                
                # Update password
                hashed_password = generate_password_hash(new_password)
                cursor.execute(
                    "UPDATE users SET password = %s WHERE id = %s",
                    (hashed_password, token_data['user_id'])
                )
                
                # Mark token as used
                cursor.execute(
                    "UPDATE password_reset_tokens SET used = TRUE WHERE token = %s",
                    (token,)
                )
                
                conn.commit()
                flash('Password reset successfully! You can now login with your new password.', 'success')
                return redirect(url_for('login'))
            
    except Exception as e:
        print(f"Error in reset password: {e}")
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('forgot_password'))
    finally:
        conn.close()
    
    return render_template('reset_password.html', token=token)
# Address Management Routes
@app.route('/addresses')
@login_required()
def user_addresses():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_addresses WHERE user_id = %s ORDER BY is_default DESC, created_at DESC", (session['user_id'],))
            addresses = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching addresses: {e}")
        addresses = []
    finally:
        conn.close()
    
    return render_template('user/addresses.html', addresses=addresses)

@app.route('/add_address', methods=['GET', 'POST'])
@login_required()
def add_address():
    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        address_line1 = request.form['address_line1']
        address_line2 = request.form.get('address_line2', '')
        city = request.form['city']
        state = request.form['state']
        postal_code = request.form['postal_code']
        country = request.form.get('country', 'India')
        is_default = request.form.get('is_default') == 'on'
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # If setting as default, remove default from other addresses
                if is_default:
                    cursor.execute(
                        "UPDATE user_addresses SET is_default = FALSE WHERE user_id = %s",
                        (session['user_id'],)
                    )
                
                cursor.execute('''
                    INSERT INTO user_addresses 
                    (user_id, full_name, phone, address_line1, address_line2, city, state, postal_code, country, is_default)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (session['user_id'], full_name, phone, address_line1, address_line2, city, state, postal_code, country, is_default))
                
                conn.commit()
                flash('Address added successfully!', 'success')
                return redirect(url_for('user_addresses'))
                
        except Exception as e:
            print(f"Error adding address: {e}")
            flash('Error adding address. Please try again.', 'danger')
        finally:
            conn.close()
    
    return render_template('user/add_address.html')

@app.route('/edit_address/<int:address_id>', methods=['GET', 'POST'])
@login_required()
def edit_address(address_id):
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            full_name = request.form['full_name']
            phone = request.form['phone']
            address_line1 = request.form['address_line1']
            address_line2 = request.form.get('address_line2', '')
            city = request.form['city']
            state = request.form['state']
            postal_code = request.form['postal_code']
            country = request.form.get('country', 'India')
            is_default = request.form.get('is_default') == 'on'
            
            with conn.cursor() as cursor:
                # If setting as default, remove default from other addresses
                if is_default:
                    cursor.execute(
                        "UPDATE user_addresses SET is_default = FALSE WHERE user_id = %s AND id != %s",
                        (session['user_id'], address_id)
                    )
                
                cursor.execute('''
                    UPDATE user_addresses 
                    SET full_name=%s, phone=%s, address_line1=%s, address_line2=%s, 
                        city=%s, state=%s, postal_code=%s, country=%s, is_default=%s
                    WHERE id=%s AND user_id=%s
                ''', (full_name, phone, address_line1, address_line2, city, state, postal_code, country, is_default, address_id, session['user_id']))
                
                conn.commit()
                flash('Address updated successfully!', 'success')
                return redirect(url_for('user_addresses'))
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_addresses WHERE id = %s AND user_id = %s", (address_id, session['user_id']))
            address = cursor.fetchone()
            
        if not address:
            flash('Address not found', 'danger')
            return redirect(url_for('user_addresses'))
            
        return render_template('user/edit_address.html', address=address)
        
    except Exception as e:
        print(f"Error editing address: {e}")
        flash('Error updating address. Please try again.', 'danger')
        return redirect(url_for('user_addresses'))
    finally:
        conn.close()

@app.route('/delete_address/<int:address_id>')
@login_required()
def delete_address(address_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_addresses WHERE id = %s AND user_id = %s", (address_id, session['user_id']))
            conn.commit()
            flash('Address deleted successfully!', 'success')
    except Exception as e:
        print(f"Error deleting address: {e}")
        flash('Error deleting address. Please try again.', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('user_addresses'))

# Update checkout process to include address selection
# @app.route('/checkout', methods=['GET', 'POST'])
# @login_required()
# def checkout():
#     if request.method == 'POST':
#         address_id = request.form['address_id']
        
#         conn = get_db_connection()
#         try:
#             with conn.cursor() as cursor:
#                 # Verify address belongs to user
#                 cursor.execute("SELECT * FROM user_addresses WHERE id = %s AND user_id = %s", (address_id, session['user_id']))
#                 address = cursor.fetchone()
                
#                 if not address:
#                     flash('Invalid address selected', 'danger')
#                     return redirect(url_for('checkout'))
                
#                 # Get cart items
#                 cursor.execute('''
#                     SELECT c.*, b.title, b.stock, b.price
#                     FROM cart c 
#                     JOIN books b ON c.book_id = b.id 
#                     WHERE c.user_id = %s
#                 ''', (session['user_id'],))
#                 cart_items = cursor.fetchall()
                
#                 if not cart_items:
#                     flash('Your cart is empty', 'danger')
#                     return redirect(url_for('cart'))
                
#                 # Check stock
#                 for item in cart_items:
#                     if item['stock'] < item['quantity']:
#                         flash(f'Not enough stock for {item["title"]}', 'danger')
#                         return redirect(url_for('cart'))
                
#                 total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
#                 order_id = f"ORDER_{int(time.time())}_{session['user_id']}"
                
#                 # Generate tracking number
#                 tracking_number = f"TRK{int(time.time())}{session['user_id']}"
                
#                 # Calculate estimated delivery (7 days from now)
#                 from datetime import datetime, timedelta
#                 estimated_delivery = datetime.now() + timedelta(days=7)
                
#                 # Create order with address
#                 cursor.execute('''
#                     INSERT INTO orders (order_id, user_id, amount, address_id, tracking_number, estimated_delivery, status)
#                     VALUES (%s, %s, %s, %s, %s, %s, 'completed')
#                 ''', (order_id, session['user_id'], total_amount, address_id, tracking_number, estimated_delivery))
                
#                 # Save order items
#                 for item in cart_items:
#                     cursor.execute(
#                         "INSERT INTO order_items (order_id, book_id, quantity, price) VALUES (%s, %s, %s, %s)",
#                         (order_id, item['book_id'], item['quantity'], item['price'])
#                     )
                    
#                     # Update stock
#                     cursor.execute(
#                         "UPDATE books SET stock = stock - %s WHERE id = %s",
#                         (item['quantity'], item['book_id'])
#                     )
                
#                 # Add order tracking entry
#                 cursor.execute('''
#                     INSERT INTO order_tracking (order_id, status, description, location)
#                     VALUES (%s, 'confirmed', 'Order has been confirmed and is being processed.', 'Warehouse')
#                 ''', (order_id,))
                
#                 # Clear cart
#                 cursor.execute("DELETE FROM cart WHERE user_id = %s", (session['user_id'],))
                
#                 conn.commit()
                
#                 # Update cart count
#                 update_cart_count()
                
#                 flash('Order placed successfully! Your books will be delivered soon.', 'success')
#                 return redirect(url_for('order_confirmation', order_id=order_id))
                
#         except Exception as e:
#             print(f"Error during checkout: {e}")
#             conn.rollback()
#             flash('Error processing order. Please try again.', 'danger')
#             return redirect(url_for('cart'))
#         finally:
#             conn.close()
    
#     # GET request - show address selection
#     conn = get_db_connection()
#     try:
#         with conn.cursor() as cursor:
#             # Get user addresses
#             cursor.execute("SELECT * FROM user_addresses WHERE user_id = %s ORDER BY is_default DESC", (session['user_id'],))
#             addresses = cursor.fetchall()
            
#             # Get cart total
#             cursor.execute('''
#                 SELECT SUM(b.price * c.quantity) as total
#                 FROM cart c 
#                 JOIN books b ON c.book_id = b.id 
#                 WHERE c.user_id = %s
#             ''', (session['user_id'],))
#             cart_total = cursor.fetchone()['total'] or 0
            
#     except Exception as e:
#         print(f"Error loading checkout: {e}")
#         addresses = []
#         cart_total = 0
#     finally:
#         conn.close()
    
#     if not addresses:
#         flash('Please add a delivery address before checkout.', 'warning')
#         return redirect(url_for('add_address'))
    
#     return render_template('user/checkout.html', addresses=addresses, cart_total=cart_total)

# Order Tracking
@app.route('/track_order/<order_id>')
@login_required()
def track_order(order_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get order details
            cursor.execute('''
                SELECT o.*, ua.*, ot.status as current_status, ot.updated_at as status_date,
                       ot.description as status_description, ot.location
                FROM orders o
                LEFT JOIN user_addresses ua ON o.address_id = ua.id
                LEFT JOIN order_tracking ot ON o.order_id = ot.order_id
                WHERE o.order_id = %s AND o.user_id = %s
                ORDER BY ot.updated_at DESC
                LIMIT 1
            ''', (order_id, session['user_id']))
            
            order_data = cursor.fetchone()
            
            if not order_data:
                flash('Order not found', 'danger')
                return redirect(url_for('order_history'))
            
            # Get tracking history
            cursor.execute('''
                SELECT * FROM order_tracking 
                WHERE order_id = %s 
                ORDER BY updated_at ASC
            ''', (order_id,))
            tracking_history = cursor.fetchall()
            
            # Get order items
            cursor.execute('''
                SELECT oi.*, b.title, b.author, b.image_url
                FROM order_items oi
                JOIN books b ON oi.book_id = b.id
                WHERE oi.order_id = %s
            ''', (order_id,))
            order_items = cursor.fetchall()
            
    except Exception as e:
        print(f"Error tracking order: {e}")
        flash('Error loading order tracking', 'danger')
        return redirect(url_for('order_history'))
    finally:
        conn.close()
    
    return render_template('user/track_order.html', 
                         order=order_data, 
                         tracking_history=tracking_history,
                         order_items=order_items)

# Admin Order Management
@app.route('/admin/orders')
@login_required(role='admin')
def admin_orders():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT o.*, u.username, ua.full_name, ua.city, ua.state,
                       (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id) as item_count
                FROM orders o
                JOIN users u ON o.user_id = u.id
                LEFT JOIN user_addresses ua ON o.address_id = ua.id
                ORDER BY o.created_at DESC
            ''')
            orders = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
    finally:
        conn.close()
    
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/update_order_status/<order_id>', methods=['POST'])
@login_required(role='admin')
def update_order_status(order_id):
    new_status = request.form['status']
    description = request.form.get('description', '')
    location = request.form.get('location', '')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Update order status
            cursor.execute(
                "UPDATE orders SET delivery_status = %s WHERE order_id = %s",
                (new_status, order_id)
            )
            
            # Add tracking entry
            cursor.execute('''
                INSERT INTO order_tracking (order_id, status, description, location)
                VALUES (%s, %s, %s, %s)
            ''', (order_id, new_status, description, location))
            
            conn.commit()
            flash('Order status updated successfully!', 'success')
            
    except Exception as e:
        print(f"Error updating order status: {e}")
        flash('Error updating order status', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('admin_orders'))
# Add this route after the checkout route
@app.route('/payment')
@login_required()
def payment():
    # Check if we have checkout data
    if 'selected_address_id' not in session or 'checkout_total' not in session:
        flash('Please complete the checkout process first.', 'danger')
        return redirect(url_for('cart'))
    
    return render_template('user/payment.html', total_amount=session['checkout_total'])

if __name__ == '__main__':
    app.run(debug=True)