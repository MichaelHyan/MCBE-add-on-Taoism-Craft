start_cord = [-12,1]
end_cord = [12,17]
result = []
for i in range(start_cord[0],end_cord[0]+1):
    result.append([i,start_cord[1]])
    result.append([i,end_cord[1]])
for i in range(start_cord[1],end_cord[1]+1):
    result.append([start_cord[0],i])
    result.append([end_cord[0],i])
resulta = []
for i in result:
    if i not in resulta:
        resulta.append(i)
result = ''
for i in resulta:
    result += f'particle minecraft:balloon_gas_particle ^{i[0]} ^0.5 ^{i[1]}\n'
with open('./Taoism_B/functions/unit_j.mcfunction','w',encoding='utf-8') as f:
    f.write(result)