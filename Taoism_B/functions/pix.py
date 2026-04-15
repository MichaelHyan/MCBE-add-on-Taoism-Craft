import cv2
import numpy as np
def get_non_transparent_pixel_coordinates(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img.shape[2] < 4:
        mask = np.ones((img.shape[0], img.shape[1]), dtype=np.uint8)
    else:
        alpha_channel = img[:, :, 3]
        _, mask = cv2.threshold(alpha_channel, 0, 255, cv2.THRESH_BINARY)
    height, width = mask.shape
    center_x = width // 2
    center_y = height // 2
    rows, cols = np.where(mask > 0)
    centered_coords = []
    for r, c in zip(rows, cols):
        new_x = c - center_x
        new_y = r - center_y
        centered_coords.append((new_x, new_y))
    return centered_coords

path_to_image = 'C:\\Users\\wnaiq\\Desktop\\a.png' 
coordinates = get_non_transparent_pixel_coordinates(path_to_image)
    
print(len(coordinates))
s = ''
for i in coordinates:
    s += f'particle minecraft:balloon_gas_particle ~{i[0]/2:.1f} ~0.5 ~{i[1]/2:.1f}\n'
with open('lotusa.mcfunction','w',encoding='utf-8') as f:
    f.write(s)
        
    
