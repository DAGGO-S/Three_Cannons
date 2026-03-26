import pickle
import os
import sys

# 确保脚本可以从项目根目录导入核心模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def peek_tb(filename):
    """
    快速查看残局库文件的元数据及样本节点。
    用于验证库文件的完整性以及评估结果分布。
    """
    # 自动定位项目根目录下的数据存储路径
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "tablebase", filename)
    
    if not os.path.exists(path):
        print(f"[错误] 找不到残局库文件: {path}")
        return

    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    print(f"[*] 库路径: {path}")
    print(f"[*] 局面总数: {len(tb)}")
    
    # 抽样显示前 10 个已确权的节点 (胜负不为 0)
    print("\n[典型必杀/必败样本查询]:")
    found = 0
    for h, data in tb.items():
        # 数据结构适配：处理 (胜负, 步数, 压力) 或 (胜负, 步数)
        v = data[0]
        d = data[1]
        
        if v != 0:
            status = "炮胜" if v == 1 else "兵胜"
            print(f"  哈希: {h} | 评价: {status} | 绝杀步数(DTM): {d}")
            found += 1
            if found >= 10: break

if __name__ == "__main__":
    # 默认查看 2C3S 的残局库数据
    peek_tb("tb_c2_s3.pkl")
