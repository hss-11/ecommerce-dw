"""
全角标点体检脚本
扫描指定 py 文件，找出所有中文标点（手敲代码时输入法误输入的典型问题）
"""
from pathlib import Path

# __file__ 是 Python 内置变量，值为当前脚本的完整路径
# .resolve() 转成绝对路径，.parent 取所在文件夹
# 脚本在 scratch/ 下，所以 parent.parent 就是项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 要检查的文件：相对项目根目录定位，与从哪个目录运行无关
TARGET = PROJECT_ROOT / 'scratch' / 'test_env.py'

FULLWIDTH = {
    '，': '英文逗号 ,', '。': '英文句点 .', '：': '英文冒号 :',
    '；': '英文分号 ;', '（': '英文左括号 (', '）': '英文右括号 )',
    '“': '英文双引号 "', '”': '英文双引号 "',
    '‘': "英文单引号 '", '’': "英文单引号 '",
    '【': '英文方括号 [', '】': '英文方括号 ]',
    '＝': '英文等号 =', '＊': '英文星号 *',
    ' ': '全角空格（最隐蔽！）',
}

print(f"项目根目录：{PROJECT_ROOT}")
print(f"检查文件：  {TARGET}")
print("-" * 55)

# 先确认文件存在，给出友好提示而不是抛异常
if not TARGET.exists():
    print(f"文件不存在：{TARGET}")
    print("请确认 test_env.py 已经建在 scratch 目录下")
    raise SystemExit(1)

with open(TARGET, encoding='utf-8') as f:
    lines = f.readlines()

found = 0
for i, line in enumerate(lines, start=1):
    for bad, good in FULLWIDTH.items():
        if bad in line:
            found += 1
            print(f"第 {i} 行发现【{bad}】→ 应改为 {good}")
            print(f"    内容：{line.rstrip()}")

print("-" * 55)
if found == 0:
    print("没有发现全角标点，问题在别处")
else:
    print(f"共发现 {found} 处，全部改成英文标点后重新运行")
