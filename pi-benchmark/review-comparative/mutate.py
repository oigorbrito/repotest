import os, shutil, sys, re
SRC='integrated/resty-3'; BASE='../resty-3.zip'
OUT='integrated-mut'
shutil.rmtree(OUT, ignore_errors=True)
import zipfile
z=zipfile.ZipFile(BASE)
def base(rel): return z.read('resty-3/'+rel).decode('utf-8')
def mk(name):
    d=os.path.join(OUT,name); shutil.copytree(SRC,d); return d
def rd(p): return open(p,encoding='utf-8',newline='').read()
def wr(p,s): open(p,'w',encoding='utf-8',newline='').write(s)
def drop_lines(p, prefixes):
    s=rd(p); out=[]; n=0
    for l in s.split('\n'):
        if any(l.strip().startswith(x) for x in prefixes): n+=1; continue
        out.append(l)
    wr(p,'\n'.join(out)); return n
def replace_once(p, old, new):
    s=rd(p); assert s.count(old)==1,(p,old[:60],s.count(old)); wr(p,s.replace(old,new))
def replace_func_with(p, header, new_text):
    s=rd(p); i=s.index(header); assert s.count(header)==1
    end=s.index('\n}\n',i)+3; wr(p,s[:i]+new_text+s[end:])
def base_func(header):
    s=base('client.go'); i=s.index(header); end=s.index('\n}\n',i)+3; return s[i:end]

# A: sem clone dos slices de hook
d=mk('mA-hook-slices-not-cloned')
n=drop_lines(d+'/client.go',['cc.errorHooks = slices.Clone','cc.invalidHooks = slices.Clone','cc.panicHooks = slices.Clone',
  'cc.successHooks = slices.Clone','cc.closeHooks = slices.Clone','cc.retryHooks = slices.Clone'])
print('A removed',n)
# B: sem clone de beforeRequest/afterResponse/retryConditions
d=mk('mB-middleware-retry-not-cloned')
n=drop_lines(d+'/client.go',['cc.beforeRequest = slices.Clone','cc.afterResponse = slices.Clone','cc.retryConditions = slices.Clone'])
print('B removed',n)
# C: contentDecompresserKeys como no base (copia sobre si mesmo)
d=mk('mC-decompresser-keys-base')
replace_once(d+'/client.go','cc.contentDecompresserKeys = slices.Clone(c.contentDecompresserKeys)',
  'copy(cc.contentDecompresserKeys, c.contentDecompresserKeys)')
print('C ok')
# D: cookies como no base (só aloca se houver cookies)
d=mk('mD-cookies-base')
replace_once(d+'/client.go','\tcc.cookies = make([]*http.Cookie, 0, len(c.cookies))\n\tfor _, cookie := range c.cookies {\n\t\tcc.cookies = append(cc.cookies, cloneCookie(cookie))\n\t}',
  '\tif l := len(c.cookies); l > 0 {\n\t\tcc.cookies = make([]*http.Cookie, 0, l)\n\t\tfor _, cookie := range c.cookies {\n\t\t\tcc.cookies = append(cc.cookies, cloneCookie(cookie))\n\t\t}\n\t}')
print('D ok')
# E: circuit breaker como no ZIP
d=mk('mE-circuit-breaker-base')
shutil.copy(os.path.join('integrated','../../resty-3or/resty-3/circuit_breaker.go') if False else '/dev/null','/dev/null') if False else None
wr(d+'/circuit_breaker.go', base('circuit_breaker.go'))
print('E ok')
# F: despacho de hooks como no ZIP (segura RLock durante os hooks)
d=mk('mF-dispatch-holds-lock')
for hdr in ['func (c *Client) onErrorHooks(','func (c *Client) onPanicHooks(','func (c *Client) onInvalidHooks(','func (c *Client) onCloseHooks(']:
    replace_func_with(d+'/client.go', hdr, base_func(hdr))
print('F ok')
# G: Clone sem RLock (não detectável sem -race: esperado PASS)
d=mk('mG-clone-without-rlock')
replace_once(d+'/client.go','\tc.lock.RLock()\n\tdefer c.lock.RUnlock()\n\n\tcc := new(Client)','\tcc := new(Client)')
print('G ok')
