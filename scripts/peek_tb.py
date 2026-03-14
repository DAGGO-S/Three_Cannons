import pickle
import os

def peek_tb(filename):
    path = os.path.join("data", "tablebase", filename)
    with open(path, 'rb') as f:
        tb = pickle.load(f)
    print(f"Path: {path}")
    print(f"Count: {len(tb)}")
    
    # 打印前 5 个解决的节点 (val != 0)
    print("\nSolved Samples (val != 0):")
    found = 0
    for h, (v, d) in tb.items():
        if v != 0:
            print(f"  Hash: {h} | Val: {v} | DTM: {d}")
            found += 1
            if found >= 10: break

if __name__ == "__main__":
    peek_tb("tb_c2_s3.pkl")
