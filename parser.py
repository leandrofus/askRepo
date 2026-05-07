import os
import csv
import re

def parse_capabilities(file_path, mode="markdown"):
    tasks = []
    if not os.path.exists(file_path):
        return []

    with open(file_path, 'r') as f:
        lines = f.readlines()

    if mode == "markdown":
        current_category = "General"
        current_point = "Default Point"
        
        for line in lines:
            stripped = line.strip()
            if not stripped: continue
            
            # Detect Category (e.g., "The Authentication capabilities identified:")
            if "capabilities identified" in stripped.lower():
                current_category = stripped.split(" capabilities ")[0].replace("The ", "").replace("#", "").strip()
                continue
                
            # Detect Point or Subpoint via bullets
            if stripped.startswith("*") or stripped.startswith("-"):
                indent = len(line) - len(line.lstrip())
                content = re.sub(r'^[*\s-]+', '', stripped).strip()
                
                if indent < 4:
                    current_point = content
                else:
                    tasks.append({
                        "category": current_category,
                        "point": current_point,
                        "sub_point": content
                    })
    
    elif mode == "csv":
        reader = csv.reader(lines)
        for row in reader:
            if len(row) >= 3:
                tasks.append({"category": row[0], "point": row[1], "sub_point": row[2]})
                
    return tasks
