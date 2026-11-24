import re, sys, os
os.chdir(sys.argv[1])

def replace_func(src, header, new_text):
    i = src.index(header)  # AssertionError se ausente
    assert src.count(header) == 1, header
    end = src.index("\n}\n", i) + 3
    return src[:i] + new_text + src[end:]

# ---------- circuit_breaker.go ----------
p = "circuit_breaker.go"
s = open(p, encoding="utf-8").read()
s = replace_func(s, "func (cb *circuitBreakerBase) RunOnTriggerHooks(", """func (cb *circuitBreakerBase) RunOnTriggerHooks(req *Request, err error) {
	// hooks run without holding cb.lock, so they may register further hooks
	cb.lock.RLock()
	hooks := cb.triggerHooks
	cb.lock.RUnlock()
	for _, h := range hooks {
		h(req, err)
	}
}
""")
s = replace_func(s, "func (cb *circuitBreakerBase) RunOnStateChangeHooks(", """func (cb *circuitBreakerBase) RunOnStateChangeHooks(oldState, newState CircuitBreakerState) {
	// hooks run without holding cb.lock, so they may register further hooks
	cb.lock.RLock()
	hooks := cb.stateChangeHooks
	cb.lock.RUnlock()
	for _, h := range hooks {
		h(oldState, newState)
	}
}
""")
open(p, "w", encoding="utf-8").write(s)

# ---------- client.go ----------
p = "client.go"
s = open(p, encoding="utf-8").read()

# 1) remove the deadlock NOTE blocks (now false: hooks run without the lock)
note = re.compile(r"//\n// NOTE:\n//   - Do not use \[Client\] setter methods within \w+ hooks; deadlock will happen\.\n")
assert len(note.findall(s)) == 4, len(note.findall(s))
s = note.sub("", s)

# 2) hook dispatchers: snapshot under RLock, run outside the lock
s = replace_func(s, "func (c *Client) onErrorHooks(", """func (c *Client) onErrorHooks(req *Request, res *Response, err error) {
	// Hooks run without holding c.lock, so they may call Client getters and setters.
	// Hook slices are only ever appended to, and elements below the snapshot length
	// are never rewritten, so reading the snapshot after unlocking is race-free.
	c.lock.RLock()
	errorHooks, successHooks := c.errorHooks, c.successHooks
	c.lock.RUnlock()
	if err != nil {
		if res != nil { // wrap with ResponseError
			err = &ResponseError{Response: res, Err: err}
		}
		for _, h := range errorHooks {
			h(req, err)
		}
	} else {
		for _, h := range successHooks {
			h(c, res)
		}
	}
}
""")
for name, field, call in [
    ("onPanicHooks", "panicHooks", "h(req, err)"),
    ("onInvalidHooks", "invalidHooks", "h(req, err)"),
]:
    sig = f"func (c *Client) {name}("
    s = replace_func(s, sig, f"""func (c *Client) {name}(req *Request, err error) {{
	c.lock.RLock()
	hooks := c.{field}
	c.lock.RUnlock()
	for _, h := range hooks {{
		{call}
	}}
}}
""")
s = replace_func(s, "func (c *Client) onCloseHooks(", """func (c *Client) onCloseHooks() {
	c.lock.RLock()
	hooks := c.closeHooks
	c.lock.RUnlock()
	for _, h := range hooks {
		h()
	}
}
""")

# 3) Clone(): copy under the parent's read lock; every mutable slice/map reachable
#    from the copy is duplicated so parent and clone never share storage.
s = replace_func(s, "func (c *Client) Clone(ctx context.Context) *Client {", """func (c *Client) Clone(ctx context.Context) *Client {
	// Copy under the parent's read lock. Clone never runs hooks or setters, so this
	// cannot deadlock with hook dispatch, and no internal caller holds c.lock here.
	c.lock.RLock()
	defer c.lock.RUnlock()

	cc := new(Client)
	// dereference the pointer and copy the value
	*cc = *c

	cc.ctx = ctx
	cc.queryParams = cloneURLValues(c.queryParams)
	cc.formData = cloneURLValues(c.formData)
	cc.header = c.header.Clone()
	cc.pathParams = maps.Clone(c.pathParams)

	// Slices below are appended to by Client setters under each client's own lock.
	// Each client must own its backing arrays, otherwise appends on one side can
	// overwrite elements that the other side still sees.
	cc.beforeRequest = slices.Clone(c.beforeRequest)
	cc.afterResponse = slices.Clone(c.afterResponse)
	cc.retryConditions = slices.Clone(c.retryConditions)
	cc.retryHooks = slices.Clone(c.retryHooks)
	cc.errorHooks = slices.Clone(c.errorHooks)
	cc.invalidHooks = slices.Clone(c.invalidHooks)
	cc.panicHooks = slices.Clone(c.panicHooks)
	cc.successHooks = slices.Clone(c.successHooks)
	cc.closeHooks = slices.Clone(c.closeHooks)
	cc.contentDecompresserKeys = slices.Clone(c.contentDecompresserKeys)

	if c.credentials != nil {
		cc.credentials = c.credentials.Clone()
	}

	cc.contentTypeEncoders = maps.Clone(c.contentTypeEncoders)
	cc.contentTypeDecoders = maps.Clone(c.contentTypeDecoders)
	cc.contentDecompressers = maps.Clone(c.contentDecompressers)

	if c.proxyURL != nil {
		cc.proxyURL, _ = url.Parse(c.proxyURL.String())
	}
	// clone cookies: always allocate, so a parent slice with spare capacity is never shared
	cc.cookies = make([]*http.Cookie, 0, len(c.cookies))
	for _, cookie := range c.cookies {
		cc.cookies = append(cc.cookies, cloneCookie(cookie))
	}

	// certain values need to be reset
	cc.lock = &sync.RWMutex{}
	cc.certWatcherStopChan = make(chan bool)
	cc.isClosed = false
	return cc
}
""")
open(p, "w", encoding="utf-8").write(s)
print("production edits applied")
