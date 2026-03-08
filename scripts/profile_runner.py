import cProfile
import pstats
import os
import sys

# 确保能正确导入项目模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import scripts.bench_fixed_depth as bench_fixed_depth

if __name__ == "__main__":
    print("开始带探针的性能基准测试，请稍候...")
    
    # 启动性能抓取
    profiler = cProfile.Profile()
    profiler.enable()
    
    bench_fixed_depth.run_benchmark()
    
    profiler.disable()
    
    # 按内部纯耗时(tottime)进行降序排列
    stats = pstats.Stats(profiler).sort_stats('tottime')
    
    with open('profile_detailed.txt', 'w', encoding='utf-8') as f:
        stats.stream = f
        f.write("\n" + "="*80 + "\n")
        f.write("🔥 真实的引擎内部性能剖析 (Top 35 纯函数内部耗时) 🔥\n")
        f.write("="*80 + "\n")
        stats.print_stats(35)
        
    print("分析结果已保存到 profile_detailed.txt")
