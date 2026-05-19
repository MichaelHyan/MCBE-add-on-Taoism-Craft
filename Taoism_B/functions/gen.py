import cv2
import numpy as np

def get_alpha_coordinates(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return []
    if img.shape[2] < 4:
        mask = np.ones((img.shape[0], img.shape[1]), dtype=np.uint8)
    else:
        alpha_channel = img[:, :, 3]
        _, mask = cv2.threshold(alpha_channel, 0, 255, cv2.THRESH_BINARY)
    height, width = mask.shape
    center_x = width // 2
    center_y = height // 2
    rows, cols = np.where(mask > 0)
    
    coordinates = []
    
    for r, c in zip(rows, cols):
        rel_x = c - center_x
        rel_y = r - center_y
        
        coordinates.append((rel_x, rel_y))
        
    return coordinates

if __name__ == "__main__":
    path_to_image = f'D:/a1.png'
    
    coords = get_alpha_coordinates(path_to_image)
    p = ''
    q = ''
    j = 0
    for i in coords:
        j += 1
        if j < 8500:
            p += f'particle minecraft:balloon_gas_particle ~{i[0]/4:.2f} ~ ~{i[1]/4:.2f}\n'
        else:
            q += f'particle minecraft:balloon_gas_particle ~{i[0]/4:.2f} ~ ~{i[1]/4:.2f}\n'
    with open('./Taoism_B/functions/bss1.mcfunction', 'w', encoding='utf-8') as f:
        f.write(p)
    with open('./Taoism_B/functions/bss2.mcfunction', 'w', encoding='utf-8') as f:
        f.write(q)
