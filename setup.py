from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy
import os
import sys

# 定义扩展模块
compile_args = ['/O2', '/fp:fast', '/arch:AVX2'] if sys.platform == 'win32' else ['-O3', '-ffast-math', '-mavx2']

extensions = [
    Extension("core.constants", ["core/constants.pyx"], extra_compile_args=compile_args),
    Extension("core.board_ops", ["core/board_ops.pyx"], extra_compile_args=compile_args),
    Extension(
        "core.game_logic",
        ["core/game_logic.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=compile_args
    ),
    Extension(
        "core.search_infrastructure",
        ["core/search_infrastructure.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=compile_args
    ),
    Extension(
        "core.engine",
        ["core/engine.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=compile_args
    ),
    Extension(
        "core.search_manager",
        ["core/search_manager.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=compile_args
    ),
    Extension(
        "core.zobrist_hashing",
        ["core/zobrist_hashing.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=compile_args
    ),
    Extension(
        "core.nnue_evaluator",
        ["core/nnue_evaluator.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=compile_args
    ),
]

# 编译扩展
setup(
    ext_modules=cythonize(extensions, compiler_directives={'language_level': "3", 'profile': False}),
    zip_safe=False,
)

# 编译完成后显示成功信息
print("\n" + "="*50)
print("Cython模块编译完成！")
print("="*50)

# 检查编译文件是否存在
expected_files = [
    "core/game_logic.cp313-win_amd64.pyd",
    "core/search_infrastructure.cp313-win_amd64.pyd",
    "core/engine.cp313-win_amd64.pyd",
    "core/search_manager.cp313-win_amd64.pyd",
    "core/zobrist_hashing.cp313-win_amd64.pyd"
]

all_exist = True
for file_path in expected_files:
    if os.path.exists(file_path):
        print(f"File found: {file_path}")
    else:
        print(f"File missing: {file_path}")
        all_exist = False

if all_exist:
    print("\nAll Cython modules compiled successfully!")
else:
    print("\nWarning: Some modules might be missing.")

print("="*50)