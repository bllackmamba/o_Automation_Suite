import itertools
import csv
import os

def export_835():
    # Target directory path directly from your mac file path
    target_dir = "/Users/mamba/Desktop/Sika/o_Automation_Suite/core"
    filename = "combinations_8_35.csv"
    full_path = os.path.join(target_dir, filename)
    
    print(f"🚀 Starting execution for 8/35 combinations...")
    print(f"📁 Target Output File: {full_path}")
    
    # Ensure the directory path exists
    if not os.path.exists(target_dir):
        print(f"⚠️ Directory path not found. Falling back to current directory.")
        full_path = filename

    # Generate total combinations count mathematically: 35! / (8! * (35-8)!) = 23,535,820
    print("⏳ Streaming 23,535,820 rows... Please wait.")

    with open(full_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        
        # Write column headers (c1 to c8)
        writer.writerow([f'c{i}' for i in range(1, 9)])
        
        # Numbers pool limited to 35
        numbers = list(range(1, 36))
        
        count = 0
        # Stream combinations sequentially with zero RAM overhead
        for comb in itertools.combinations(numbers, 8):
            # Sort descending to match your original MySQL logic (highest number first)
            writer.writerow(sorted(comb, reverse=True))
            count += 1
            
            # Print a progress log line every 5 million rows
            if count % 5000000 == 0:
                print(f"   ⚡ Progress: {count:,} / 23,535,820 rows written...")
                
    print(f"✅ Completed successfully! Total lines saved: {count:,}")

if __name__ == "__main__":
    export_835()