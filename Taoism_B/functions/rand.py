import math,random,time
flo = ['sunflower',
'lilac',
'rose_bush',
'peony',
'pitcher_plant',
'tall_grass',
'dandelion',
'poppy',
'blue_orchid',
'allium',
'azure_bluet',
'red_tulip',
'orange_tulip',
'white_tulip',
'pink_tulip',
'oxeye_daisy',
'cornflower',
'lily_of_the_valley',
'pink_petals',
'wildflowers',
'wither_rose',
'torchflower',
'cactus_flower',
'open_eyeblossom',
'bush'
]

def get_points_within_distance(points, max_distance=25):
    result = []
    threshold_squared = max_distance ** 2
    for x, y in points:
        if x*x + y*y < threshold_squared:
            result.append((x, y))
            
    return result

def generate_grid_points_within_distance(range_limit, max_distance=25):
    result = []
    threshold_squared = max_distance ** 2
    for x in range(-range_limit, range_limit + 1):
        for y in range(-range_limit, range_limit + 1):
            if x*x + y*y < threshold_squared:
                result.append((x, y))
                
    return result

grid_points = generate_grid_points_within_distance(2)
print(len(grid_points))
o = 0
for j in ['a']:
    o += 1
    random.seed(time.time())
    s = ''
    for i in grid_points:
        s += f'setblock ~{i[0]} ~ ~{i[1]} {random.choice(flo)} replace\n'
    with open(f'flo{j}.mcfunction','w',encoding='utf-8') as f:
        f.write(s)
