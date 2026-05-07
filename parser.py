import os
import csv

def parse_capabilities(file_path, mode="default"):
    tasks = []
    if not os.path.exists(file_path):
        return []

    with open(file_path, 'r') as f:
        lines = f.readlines()

    if mode == "default":
        current_category = ""
        current_point = ""
        for line in lines:
            stripped = line.strip()
            if not stripped: continue
            indent = len(line) - len(line.lstrip())
            if "capabilities identified" in stripped:
                current_category = stripped.split(" capabilities ")[0].replace("The ", "").strip()
            elif stripped.startswith("*"):
                content = stripped.replace("*", "").strip()
                if indent < 5:
                    current_point = content
                else:
                    tasks.append({"category": current_category, "point": current_point, "sub_point": content})
    elif mode == "csv":
        reader = csv.reader(lines)
        for row in reader:
            if len(row) >= 3:
                tasks.append({"category": row[0], "point": row[1], "sub_point": row[2]})
    elif mode == "pipe":
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                tasks.append({"category": parts[0], "point": parts[1], "sub_point": parts[2]})
                
    return tasks
