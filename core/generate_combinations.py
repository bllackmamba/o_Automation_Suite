import itertools
import csv
import os

def export_combinations(total_numbers, select_count, filename):
    # Determine the desktop path dynamically
    desktop_path = os.path.expanduser("~/Desktop")
    full_path = os.path.join(desktop_path, filename)
    
    print(f"🔄 Processing {select_count}/{total_numbers}...")
    print(f"📁 Saving directly to: {full_path}")
    
    # Open the file and stream rows out one by one
    with open(full_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        
        # Write column headers (c1, c2, c3...)
        writer.writerow([f'c{i}' for i in range(1, select_count + 1)])
        
        # Generate the numbers from total_numbers down to 1
        numbers = list(range(1, total_numbers + 1))
        
        # itertools.combinations streams data sequentially using almost ZERO memory
        count = 0
        for comb in itertools.combinations(numbers, select_count):
            # Sort descending to match your original MySQL logic (e.g. 47, 46, 45...)
            writer.writerow(sorted(comb, reverse=True))
            count += 1
            
            # Print a progress update every 10 million rows so you know it's working
            if count % 10000000 == 0:
                print(f"   ⚡ Progress: {count:,} rows written...")
                
    print(f"✅ Finished! Total rows: {count:,}\n")

if __name__ == "__main__":
    print("🚀 Starting Combination Generator...")
    
    # 1. Run 8 / 44 (Produces 176,358,405 rows)
    export_combinations(44, 8, 'combinations_8_44.csv')
    
    # 2. Run 8 / 47 (Produces 318,101,340 rows)
    export_combinations(47, 8, 'combinations_8_47.csv')
    
    print("🎉 All tasks completed successfully! Check your Desktop.")