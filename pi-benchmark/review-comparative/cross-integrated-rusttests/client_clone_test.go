package resty

import (
	"context"
	"net/http"
	"sync"
	"testing"
)

// Regression tests for Client.Clone(). Each test gives the parent's slice spare
// capacity explicitly, so the outcome never depends on how the Go runtime grows
// slices: with spare capacity, an append on one side writes into storage that the
// other side would see if the backing array were shared.

// withSpareCap returns a copy of s with len(s) elements and capacity n.
func withSpareCap[T any](s []T, n int) []T {
	out := make([]T, len(s), n)
	copy(out, s)
	return out
}

// Response middlewares added to parent and clone must not overwrite each other.
func TestCloneDoesNotShareResponseMiddlewares(t *testing.T) {
	parent := dcnl()
	var ran []string
	mk := func(name string) ResponseMiddleware {
		return func(*Client, *Response) error { ran = append(ran, name); return nil }
	}
	parent.afterResponse = withSpareCap([]ResponseMiddleware{mk("p0")}, 8)

	clone := parent.Clone(context.Background())
	parent.AddResponseMiddleware(mk("P"))
	clone.AddResponseMiddleware(mk("C"))

	assertEqual(t, 2, len(parent.afterResponse))
	assertEqual(t, 2, len(clone.afterResponse))
	parent.afterResponse[1](parent, &Response{})
	assertEqual(t, []string{"P"}, ran, "parent's middleware was overwritten by the clone's")
	ran = nil
	clone.afterResponse[1](clone, &Response{})
	assertEqual(t, []string{"C"}, ran, "clone's middleware was overwritten by the parent's")
}

// Request middlewares inserted on parent and clone must not overwrite each other.
func TestCloneDoesNotShareRequestMiddlewares(t *testing.T) {
	parent := dcnl()
	var ran []string
	mk := func(name string) RequestMiddleware {
		return func(*Client, *Request) error { ran = append(ran, name); return nil }
	}
	parent.beforeRequest = withSpareCap([]RequestMiddleware{mk("p0")}, 8)

	clone := parent.Clone(context.Background())
	parent.AddRequestMiddleware(mk("P"))
	clone.AddRequestMiddleware(mk("C"))

	// AddRequestMiddleware inserts before the last entry, so the expected order is
	// [new, p0] on each side. Compare the whole sequence, not a fixed index.
	runAll := func(c *Client) []string {
		ran = nil
		for _, m := range c.beforeRequest {
			_ = m(c, &Request{})
		}
		return ran
	}
	assertEqual(t, 2, len(parent.beforeRequest))
	assertEqual(t, 2, len(clone.beforeRequest))
	assertEqual(t, []string{"P", "p0"}, runAll(parent), "parent's middleware was overwritten by the clone's")
	assertEqual(t, []string{"C", "p0"}, runAll(clone), "clone's middleware was overwritten by the parent's")
}

// Retry conditions added to parent and clone must not overwrite each other.
func TestCloneDoesNotShareRetryConditions(t *testing.T) {
	parent := dcnl()
	mk := func(result bool) RetryConditionFunc {
		return func(*Response, error) bool { return result }
	}
	parent.retryConditions = withSpareCap([]RetryConditionFunc{mk(false)}, 8)

	clone := parent.Clone(context.Background())
	parent.AddRetryConditions(mk(true)) // parent's second condition: true
	clone.AddRetryConditions(mk(false)) // clone's second condition: false

	assertEqual(t, 2, len(parent.retryConditions))
	assertEqual(t, 2, len(clone.retryConditions))
	assertEqual(t, true, parent.retryConditions[1](nil, nil), "parent's condition was overwritten")
	assertEqual(t, false, clone.retryConditions[1](nil, nil))
}

// The decompresser key list must have its own storage on each side.
func TestCloneDoesNotShareContentDecompresserKeys(t *testing.T) {
	parent := dcnl()
	parent.contentDecompresserKeys = withSpareCap([]string{"gzip", "deflate"}, 8)

	clone := parent.Clone(context.Background())
	if &parent.contentDecompresserKeys[0] == &clone.contentDecompresserKeys[0] {
		t.Fatal("clone shares the decompresser key backing array with its parent")
	}
	clone.contentDecompresserKeys[0] = "changed-in-clone"
	assertEqual(t, "gzip", parent.contentDecompresserKeys[0], "parent sees the clone's write")
}

// Close hooks registered on parent and clone must each run only on their own side.
func TestCloneHookRegistrationIsolated(t *testing.T) {
	parent := dcnl()
	var p, q int
	parent.closeHooks = withSpareCap([]CloseHook{func() {}, func() {}, func() {}}, 8)
	clone := parent.Clone(context.Background())

	parent.OnClose(func() { p++ })
	clone.OnClose(func() { q++ })

	assertEqual(t, 4, len(parent.closeHooks))
	assertEqual(t, 4, len(clone.closeHooks))
	parent.closeHooks[3]()
	assertEqual(t, 1, p)
	assertEqual(t, 0, q, "clone's hook leaked into the parent's storage")
	clone.closeHooks[3]()
	assertEqual(t, 1, p)
	assertEqual(t, 1, q)
}

// Clone must not deadlock when called from a hook: hooks run without c.lock held.
func TestCloneFromInsideHookDoesNotDeadlock(t *testing.T) {
	parent := dcnl()
	var cloned *Client
	parent.OnClose(func() { cloned = parent.Clone(context.Background()) })
	mustReturn(t, "Clone inside OnClose hook", func() { _ = parent.Close() })
	if cloned == nil {
		t.Fatal("hook did not produce a clone")
	}
}

// Clone and registration racing on the same parent: no panic, no lost hooks, and
// no clone ever observes more hooks than the parent finally holds.
func TestCloneConcurrentWithRegistration(t *testing.T) {
	parent := dcnl()
	base := len(parent.closeHooks)
	const writers = 4
	const perWriter = 25
	const clones = 50

	var wg sync.WaitGroup
	cloneCh := make(chan *Client, clones)
	for i := 0; i < writers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perWriter; j++ {
				parent.OnClose(func() {})
			}
		}()
	}
	for i := 0; i < clones; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cloneCh <- parent.Clone(context.Background())
		}()
	}
	wg.Wait()
	close(cloneCh)

	final := len(parent.closeHooks)
	assertEqual(t, base+writers*perWriter, final, "registrations were lost")
	for c := range cloneCh {
		if n := len(c.closeHooks); n > final {
			t.Errorf("clone observed %d hooks, parent ends with %d", n, final)
		}
	}
}

// Clone keeps the values it copies from the parent, and resets per-instance state.
func TestCloneCopiesStateAndResetsInstanceState(t *testing.T) {
	parent := dcnl().
		SetBaseURL("http://example.com").
		SetHeader("X-Parent", "1").
		SetQueryParam("q", "v")
	parent.cookies = []*http.Cookie{{Name: "c", Value: "1"}}

	clone := parent.Clone(context.Background())
	assertEqual(t, "http://example.com", clone.BaseURL())
	assertEqual(t, "1", clone.Header().Get("X-Parent"))
	assertEqual(t, 1, len(clone.Cookies()))

	// header and query params are independent copies
	clone.SetHeader("X-Parent", "2")
	clone.SetQueryParam("q", "other")
	assertEqual(t, "1", parent.Header().Get("X-Parent"))
	assertEqual(t, "v", parent.queryParams.Get("q"))

	// the clone gets a fresh lock: a parent's lock state does not leak to it
	if clone.lock == parent.lock {
		t.Fatal("clone shares the parent's lock")
	}
	assertEqual(t, false, clone.isClosed)
}

// An empty cookie slice with spare capacity must not be shared with the clone.
func TestCloneDoesNotShareEmptyCookieSlice(t *testing.T) {
	parent := dcnl()
	parent.cookies = make([]*http.Cookie, 0, 4)

	clone := parent.Clone(context.Background())
	parent.cookies = append(parent.cookies, &http.Cookie{Name: "parent", Value: "1"})
	clone.cookies = append(clone.cookies, &http.Cookie{Name: "clone", Value: "2"})

	assertEqual(t, 1, len(parent.cookies))
	assertEqual(t, "parent", parent.cookies[0].Name, "clone overwrote the parent's cookie")
	assertEqual(t, "clone", clone.cookies[0].Name)
}
