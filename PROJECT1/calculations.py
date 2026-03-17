def calculate_scrutiny_fees(subject_count, category, distance, is_holiday):
    # 1. Remuneration: 150 per subject
    remuneration = subject_count * 150
    
    # 2. TA Calculation (Only for External Faculty)
    ta = 0
    if category.lower() == 'external':
        # Rule: km * 12, but never more than 3600
        ta = min(distance * 12, 3600)
    
    # 3. DA Calculation (Only if it's a holiday/Sunday)
    da = 0
    if is_holiday:
        da = 150
        
    grand_total = remuneration + ta + da
    
    return {
        "remuneration": remuneration,
        "ta": ta,
        "da": da,
        "total": grand_total
    }

# --- TEST IT ---
# Example: External Faculty, 4 subjects, 400km away, on a Sunday
result = calculate_scrutiny_fees(4, 'external', 400, True)
print(f"Total Amount: ₹{result['total']}") # Should be 4350