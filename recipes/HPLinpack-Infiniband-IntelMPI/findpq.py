#!/usr/bin/env python

from __future__ import division

import math
import sys

n = int(sys.argv[1])

x = int(math.floor(math.sqrt(n)))

if x * x == n:
    print('{} {}'.format(x, x))
    sys.exit(0)

for i in range(x, 0, -1):
    j = n // i
    if j * i == n:
        if i < j:
            print('{} {}'.format(i, j))
        else:
            print('{} {}'.format(j, i))
        sys.exit(0)

print('cannot determine p and q for {}'.format(n))
sys.exit(1)
