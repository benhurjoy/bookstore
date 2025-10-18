# reset_db.py
import pymysql
from config import config

def reset_database():
    # Connect without database to drop/create it
    conn = pymysql.connect(
        host=config['default'].MYSQL_HOST,
        user=config['default'].MYSQL_USER,
        password=config['default'].MYSQL_PASSWORD
    )
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP DATABASE IF EXISTS bookstore")
            cursor.execute("CREATE DATABASE bookstore")
            print("Database 'bookstore' reset successfully!")
        conn.commit()
    except Exception as e:
        print(f"Error resetting database: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    reset_database()
    from models import init_db
    init_db()