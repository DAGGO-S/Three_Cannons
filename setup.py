from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy
import os
import sys

# 定义扩展模块
extensions = [
    Extension(
        "core.game_logic",
        ["core/game_logic.pyx"],
        include_dirs=[numpy.get_include()],
    ),
    Extension(
        "core.ai",
        ["core/ai.pyx"],
        include_dirs=[numpy.get_include()],
    ),
    Extension(
        "core.evaluation_logic",
        ["core/evaluation_logic.pyx"],
        include_dirs=[numpy.get_include()],
    ),
    Extension(
        "core.zobrist_hashing",
        ["core/zobrist_hashing.pyx"],
        include_dirs=[numpy.get_include()],
    ),
]

# 编译扩展
setup(
    ext_modules=cythonize(extensions, compiler_directives={'language_level': "3", 'profile': True}),
    zip_safe=False,
)

# 编译完成后显示成功信息
print("\n" + "="*50)
print("Cython模块编译完成！")
print("="*50)

# 检查编译文件是否存在
expected_files = [
    "core/game_logic.cp313-win_amd64.pyd",
    "core/ai.cp313-win_amd64.pyd",
    "core/evaluation_logic.cp313-win_amd64.pyd",
    "core/zobrist_hashing.cp313-win_amd64.pyd"
]

all_exist = True
for file_path in expected_files:
    if os.path.exists(file_path):
        print(f"✓ {file_path} - 编译成功")
    else:
        print(f"✗ {file_path} - 未找到")
        all_exist = False

if all_exist:
    print("\n所有Cython模块编译成功！")
    print("现在可以运行 'python main.py' 启动游戏。")
else:
    print("\n警告：部分Cython模块可能未正确编译。")
    print("请检查错误信息并重试。")

print("="*50)