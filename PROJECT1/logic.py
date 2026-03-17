def generate_claim_calculations(faculty_id, course_codes_list, is_holiday, db_connection):
    cursor = db_connection.cursor(dictionary=True)
    
    # 1. Fetch Faculty Info
    cursor.execute("SELECT * FROM faculty_master WHERE faculty_id = %s", (faculty_id,))
    faculty = cursor.fetchone()
    
    # 2. Optimized Course Fetch (One query instead of a loop)
    format_strings = ','.join(['%s'] * len(course_codes_list))
    query = f"SELECT course_code as code, course_name as name FROM course_master WHERE course_code IN ({format_strings})"
    cursor.execute(query, tuple(course_codes_list))
    courses = cursor.fetchall()

    # 3. Apply GCE Salem Rules
    subject_count = len(course_codes_list)
    remuneration = subject_count * 150
    
    # Check if faculty exists to avoid crashes
    dist = faculty['distance'] if faculty else 0
    cat = faculty['category'].lower() if faculty else 'internal'
    
    ta = min(dist * 12, 3600) if cat == 'external' else 0
    da = 150 if is_holiday else 0
    
    return {
        "faculty": faculty,
        "courses": courses,
        "remuneration": remuneration,
        "ta": ta,
        "da": da,
        "grand_total": remuneration + ta + da
    }