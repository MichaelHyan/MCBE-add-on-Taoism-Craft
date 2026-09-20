with open('./other/README_modify.md','r',encoding='utf-8') as f:
    f = f.read()
f = f.split('\n\n')
dic = []
for i in f:
    i=i.strip()
    temp = {}
    ind = i.split('\n')
    temp['index'] = ind[0]
    temp['name'] = ind[1] if ind[1] != 'none' else ''
    temp['description'] = '\n'.join(ind[2:-2])
    temp['url'] = ind[-2] if ind[-2] != 'none' else ''
    temp['parent'] = ind[-1] if ind[-1] != 'none' else ''
    dic.append(temp)

with open('./other/graph_empty.html','r',encoding='utf-8') as f:
    g = f.read()
g = g.replace('#CONFIG#',repr(dic))

with open('./graph.html','w',encoding='utf-8') as f:
    f.write(g)