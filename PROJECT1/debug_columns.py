import mysql.connector

try:
    db = mysql.connector.connect(host="localhost", user="root", password="", database="scrutiny_db")
    cursor = db.cursor()
    
    print("\n--- CHECKING TABLE: faculty_master ---")
    cursor.execute("DESCRIBE faculty_master")
    for col in cursor.fetchall():
        print(f"Column: {col[0]} | Type: {col[1]}")

    print("\n--- CHECKING TABLE: course_master ---")
    cursor.execute("DESCRIBE course_master")
    for col in cursor.fetchall():
        print(f"Column: {col[0]} | Type: {col[1]}")

    db.close()
    print("\n✅ DONE. Compare these column names with the app.py code.")

except Exception as e:
    print(f"❌ DATABASE ERROR: {e}")