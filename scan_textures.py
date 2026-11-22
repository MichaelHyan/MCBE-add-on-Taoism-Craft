import os, sys
from collections import Counter
from PIL import Image

ROOT = r"D:/git/MCBE-add-on-Taoism-Craft/Taoism_R/textures"
EXCLUDE = {"attachable", "entity"}

# 收集目标目录（第一层）
targets = []
for name in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, name)
    if os.path.isdir(p) and name not in EXCLUDE:
        targets.append(p)

# 递归收集所有 png
files = []
for t in targets:
    for dirpath, dirnames, filenames in os.walk(t):
        for fn in filenames:
            if fn.lower().endswith(".png"):
                files.append(os.path.join(dirpath, fn))
files.sort()

size_counter = Counter()
semi = []      # 含半透明
opaque_only = []
transparent_present = []
errors = []

for f in files:
    try:
        with Image.open(f) as im:
            w, h = im.size
            mode = im.mode
            has_alpha = mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in im.info)
            size_counter[(w, h)] += 1
            if not has_alpha:
                opaque_only.append(f)
                continue
            im2 = im.convert("RGBA")
            alpha = im2.getchannel("A")
            amin, amax = alpha.getextrema()
            # 半透明像素统计
            hist = alpha.histogram()
            semi_count = sum(hist[1:255])
            if amax == 255:
                transparent_present.append(f)
            if semi_count > 0:
                semi.append((f, w, h, semi_count, mode))
    except Exception as e:
        errors.append((f, str(e)))

print("=== 目录清单 ===")
for t in targets:
    print(" ", os.path.relpath(t, ROOT))
print()
print("=== 文件总数 ===", len(files))
print()
print("=== 尺寸统计 (宽x高 : 数量) ===")
for (w, h), c in sorted(size_counter.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {w}x{h} : {c}")
print()
print("=== 含半透明像素的贴图 ===")
if semi:
    for f, w, h, sc, mode in sorted(semi):
        print(f"  {os.path.relpath(f, ROOT)}  [{w}x{h}, {mode}, 半透明像素={sc}]")
else:
    print("  (无)")
print()
print("=== 无 alpha 通道的文件数 ===", len(opaque_only))
for f in sorted(opaque_only):
    print("  ", os.path.relpath(f, ROOT))
print()
print("=== 错误 ===", len(errors))
for f, e in errors:
    print("  ", os.path.relpath(f, ROOT), e)