import mysql.connector

def get_faculty_details(search_id):
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="scrutiny_db"
    )
    cursor = db.cursor(dictionary=True) # Returns results as a dictionary
    
    query = "SELECT * FROM faculty_master WHERE faculty_id = %s"
    cursor.execute(query, (search_id,))
    
    return cursor.fetchone() # Returns one faculty's full row