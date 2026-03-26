import re
import os
import shutil

def symmetrize():
    header_path = "core/nnue_weights.h"
    backup_path = "core/nnue_weights.h.bak"
    
    if not os.path.exists(header_path):
        print(f"Error: {header_path} not found")
        return

    # Backup
    shutil.copy(header_path, backup_path)
    print(f"Backup created at {backup_path}")

    with open(header_path, 'r') as f:
        content = f.read()

    # Parse NNUE_W1
    # Format: const float NNUE_W1[51][256] = { {val, val...}, {...}, ... }
    w1_match = re.search(r'const float NNUE_W1\[51\]\[256\] = \{(.*?)\};', content, re.DOTALL)
    if not w1_match:
        print("Error: Could not find NNUE_W1 in header")
        return

    w1_data_str = w1_match.group(1).strip()
    
    # Extract each feature row using regex to handle nested braces
    # The data looks like: {v,v...}, {v,v...}, ...
    rows = re.findall(r'\{(.*?)\}', w1_data_str)
    if len(rows) != 51:
        print(f"Error: Expected 51 features, found {len(rows)}")
        return

    # Convert to numeric
    w1_weights = []
    for r_str in rows:
        vals = [float(v.strip().replace('f', '')) for v in r_str.split(',')]
        w1_weights.append(vals)

    # Symmetry mapping (Horizontal flip for 5x5 board)
    def get_mirror(idx):
        if idx < 25: # Soldier features
            r, c = divmod(idx, 5)
            mirror_idx = r * 5 + (4 - c)
            return mirror_idx
        elif idx < 50: # Cannon features
            idx2 = idx - 25
            r, c = divmod(idx2, 5)
            mirror_idx = 25 + r * 5 + (4 - c)
            return mirror_idx
        else: # STM (Side to move) index 50
            return 50

    # Symmetrize
    new_w1 = [row[:] for row in w1_weights]
    for i in range(51):
        m = get_mirror(i)
        if i < m: # Only process each pair once
            for j in range(256):
                avg = (w1_weights[i][j] + w1_weights[m][j]) / 2.0
                new_w1[i][j] = avg
                new_w1[m][j] = avg

    # Generate new C array content string
    new_rows_str = []
    for i in range(51):
        row_str = "    {" + ", ".join([f"{v:.6f}f" for v in new_w1[i]]) + "}"
        new_rows_str.append(row_str)
    
    replacement = "const float NNUE_W1[51][256] = {\n" + ",\n".join(new_rows_str) + "\n};"
    
    # Sub back into content
    new_content = re.sub(r'const float NNUE_W1\[51\]\[256\] = \{.*?\};', replacement, content, flags=re.DOTALL)

    with open(header_path, 'w') as f:
        f.write(new_content)

    print("Success: NNUE_W1 has been symmetrized horizontally.")

if __name__ == "__main__":
    symmetrize()
