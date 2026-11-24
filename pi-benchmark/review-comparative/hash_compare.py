import zipfile, hashlib, os, sys, json
def h(b): return hashlib.sha256(b).hexdigest()
ZIP = 'resty-3.zip'
z = zipfile.ZipFile(ZIP)
ref = {}
for n in z.namelist():
    if n.endswith('/'):
        continue
    rel = n.split('/', 1)[1]
    ref[rel] = h(z.read(n))
def tree(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            out[rel] = h(open(p, 'rb').read())
    return out
orr = tree('resty-3or/resty-3')
rst = tree('resty-3rust/resty-3')
def cmp(a, b, label):
    common = set(a) & set(b)
    mod = sorted(k for k in common if a[k] != b[k])
    add = sorted(set(b) - set(a))
    rem = sorted(set(a) - set(b))
    print(f'== {label}: modified={len(mod)} added={len(add)} removed={len(rem)}')
    for k in mod: print('  M', k)
    for k in add: print('  A', k)
    for k in rem: print('  R', k)
    return mod, add, rem
print('counts ref/or/rust:', len(ref), len(orr), len(rst))
cmp(ref, orr, 'ZIP -> ORIGINAL (controle)')
cmp(ref, rst, 'ZIP -> RUST')
json.dump({'ref': ref, 'or': orr, 'rust': rst}, open('review-comparative/hashes.json', 'w'), indent=1)
