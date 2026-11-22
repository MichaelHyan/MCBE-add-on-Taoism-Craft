import os
from collections import Counter
from PIL import Image

ITEMS = r"D:/git/MCBE-add-on-Taoism-Craft/Taoism_R/textures/items"
files = sorted(f for f in os.listdir(ITEMS) if f.lower().endswith(".png"))
size_cnt = Counter()
bad_semi = []
bad_16 = []
for fn in files:
    p = os.path.join(ITEMS, fn)
    with Image.open(p) as im:
        w, h = im.size
        size_cnt[(w, h)] += 1
        hist = im.convert("RGBA").getchannel("A").histogram()
        semi = sum(hist[1:255])
        if semi > 0:
            bad_semi.append((fn, semi))
        if (w, h) == (16, 16):
            bad_16.append(fn)
print("文件总数:", len(files))
print("尺寸分布:")
for (w, h), c in sorted(size_cnt.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {w}x{h} : {c}")
print()
print("仍含半透明像素的文件数:", len(bad_semi))
for fn, s in bad_semi:
    print("  ", fn, s)
print("仍为 16x16 的文件数:", len(bad_16), bad_16)