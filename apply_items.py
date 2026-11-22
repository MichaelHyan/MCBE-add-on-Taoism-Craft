import os
from PIL import Image

ITEMS = r"D:/git/MCBE-add-on-Taoism-Craft/Taoism_R/textures/items"
PNG = Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST

files = sorted(f for f in os.listdir(ITEMS) if f.lower().endswith(".png"))

changed_files = 0
semi_pixels_fixed = 0
scaled_files = 0
errors = []

for fn in files:
    p = os.path.join(ITEMS, fn)
    try:
        with Image.open(p) as im:
            orig_size = im.size
            im2 = im.convert("RGBA")

        w, h = im2.size
        data = bytearray(im2.tobytes())
        fixed = 0
        for i in range(3, len(data), 4):
            a = data[i]
            if 0 < a < 255:
                data[i] = 255
                fixed += 1
        im3 = Image.frombytes("RGBA", (w, h), bytes(data))

        need_scale = (w, h) == (16, 16)
        if need_scale:
            im3 = im3.resize((32, 32), PNG)

        im3.save(p, format="PNG")

        if fixed > 0 or need_scale:
            changed_files += 1
        semi_pixels_fixed += fixed
        if need_scale:
            scaled_files += 1

        print(f"{fn}: {orig_size[0]}x{orig_size[1]} -> {im3.size[0]}x{im3.size[1]}, 半透明像素修正={fixed}")
    except Exception as e:
        errors.append((fn, str(e)))

print()
print("=== 汇总 ===")
print("处理文件总数:", len(files))
print("有改动的文件数:", changed_files)
print("半透明像素转不透明总数:", semi_pixels_fixed)
print("16x16 -> 32x32 放大文件数:", scaled_files)
print("错误数:", len(errors))
for fn, e in errors:
    print("  ERROR", fn, e)