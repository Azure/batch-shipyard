#!/usr/bin/env python3

with open('sample.fa', 'r') as f:
    data = f.read()
sp = data.split('>')
for i in range(1, len(sp)):
    with open('query-{}.fa'.format(i), 'w') as f:
        f.write('>{}'.format(sp[i]))
