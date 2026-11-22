import os
from collections import Counter
from PIL import Image

ITEMS = r"D:/git/MCBE-add-on-Taoism-Craft/Taoism_R/textures/items"

files = sorted(f for f in os.listdir(ITEMS) if f.lower().endswith(".png"))
size_cnt = Counter()
mode_cnt = Counter()
need_scale = []
semi_total = 0
semi_files = 0
zero_alpha_files = 0
p_mode = []

for fn in files:
    p = os.path.join(ITEMS, fn)
    with Image.open(p) as im:
        w, h = im.size
        mode = im.mode
        size_cnt[(w, h)] += 1
        mode_cnt[mode] += 1
        if mode == "P":
            p_mode.append((fn, "transparency" in im.info))
        im2 = im.convert("RGBA")
        hist = im2.getchannel("A").histogram()
        semi = sum(hist[1:255])
        zero = hist[0]
        if semi > 0:
            semi_files += 1
            semi_total += semi
        if zero > 0:
            zero_alpha_files += 1
        if (w, h) == (16, 16):
            need_scale.append(fn)

print("items 目录 PNG 总数:", len(files))
print()
print("尺寸分布:")
for (w, h), c in sorted(size_cnt.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {w}x{h} : {c}")
print()
print("模式分布:", dict(mode_cnt))
print("调色板模式(P)文件:", p_mode if p_mode else "无")
print()
print("含半透明像素(1~254)的文件数:", semi_files, " 半透明像素总数:", semi_total)
print("含全透明像素(alpha=0)的文件数:", zero_alpha_files)
print()
print("需要放大到 32x32 的 16x16 文件数:", len(need_scale))
print("其余文件(尺寸不变，仅做半透明->不透明):", len(files) - len(need_scale))