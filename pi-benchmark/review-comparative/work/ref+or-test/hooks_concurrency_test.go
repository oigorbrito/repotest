package resty

import (
	"context"
	"net/http"
	"net/http/httptest"
	"runtime"
	"testing"
	"time"
)

// hookTestTimeout bounds every blocking wait so a deadlock fails the test
// instead of hanging the whole test binary.
const hookTestTimeout = 5 * time.Second

const writerURL = "http://writer.example"

// hookCase binds one hook kind to its registration and to an action that runs it.
type hookCase struct {
	name       string
	register   func(c *Client, fn func())
	trigger    func(c *Client)
	repeatable bool // OnClose runs once per Client, so it cannot be re-dispatched
}

func hookCases() []hookCase {
	okServer := func() *httptest.Server {
		return createTestServer(func(w http.ResponseWriter, r *http.Request) {})
	}
	return []hookCase{
		{
			name:     "OnError",
			register: func(c *Client, fn func()) { c.OnError(func(*Request, error) { fn() }) },
			trigger: func(c *Client) {
				srv := okServer()
				u := srv.URL
				srv.Close() // connection refused => error hooks
				_, _ = c.R().Get(u)
			},
			repeatable: true,
		},
		{
			name:     "OnSuccess",
			register: func(c *Client, fn func()) { c.OnSuccess(func(*Client, *Response) { fn() }) },
			trigger: func(c *Client) {
				srv := okServer()
				defer srv.Close()
				_, _ = c.R().Get(srv.URL)
			},
			repeatable: true,
		},
		{
			name:     "OnInvalid",
			register: func(c *Client, fn func()) { c.OnInvalid(func(*Request, error) { fn() }) },
			trigger: func(c *Client) {
				_, _ = c.R().Get("http://[::1") // unparsable URL => invalid request
			},
			repeatable: true,
		},
		{
			name:     "OnPanic",
			register: func(c *Client, fn func()) { c.OnPanic(func(*Request, error) { fn() }) },
			trigger: func(c *Client) {
				c.SetRequestMiddlewares(func(*Client, *Request) error { panic("boom") })
				defer func() { _ = recover() }() // Execute re-panics after the hooks run
				_, _ = c.R().Get("http://example.invalid")
			},
			repeatable: true,
		},
		{
			name:     "OnClose",
			register: func(c *Client, fn func()) { c.OnClose(func() { fn() }) },
			trigger:  func(c *Client) { _ = c.Close() },
		},
	}
}

// contentionProbe returns a hook body that reads a Client property while a
// writer goroutine is queued on the write lock. It reports the value read on got
// and closes writerDone once the writer has finished.
//
// The writer is queued once TryRLock fails: sync.RWMutex refuses new readers while
// a writer is pending. If the dispatcher still holds its read lock, the writer can
// never finish before the body returns, so the wait loop always ends with the
// writer queued. The loop also stops if the writer completes on its own.
func contentionProbe(c *Client) (body func(), got <-chan string, writerDone <-chan struct{}) {
	g := make(chan string, 1)
	done := make(chan struct{})
	body = func() {
		started := make(chan struct{})
		go func() {
			defer close(done)
			close(started)
			c.SetBaseURL(writerURL)
		}()
		<-started

		for !isClosedChan(done) && c.lock.TryRLock() {
			c.lock.RUnlock()
			runtime.Gosched()
		}
		g <- c.BaseURL() // must return even though a writer waits for the lock
	}
	return body, g, done
}

// mustReturn runs fn and fails the test if it does not return within hookTestTimeout.
func mustReturn(t *testing.T, what string, fn func()) {
	t.Helper()
	done := make(chan struct{})
	go func() {
		defer close(done)
		fn()
	}()
	select {
	case <-done:
	case <-time.After(hookTestTimeout):
		t.Fatalf("deadlock: %s did not return", what)
	}
}

func isClosedChan(ch <-chan struct{}) bool {
	select {
	case <-ch:
		return true
	default:
		return false
	}
}

// Regression for GH #1263: a hook reading a Client getter while a writer waits on
// the lock must not deadlock. Covers all five hook kinds.
func TestClientHookGetterWhileWriterWaits(t *testing.T) {
	for _, tc := range hookCases() {
		t.Run(tc.name, func(t *testing.T) {
			c := dcnl()
			body, got, writerDone := contentionProbe(c)
			tc.register(c, body)

			triggered := make(chan struct{})
			go func() {
				defer close(triggered)
				tc.trigger(c)
			}()

			select {
			case v := <-got:
				if v != "" && v != writerURL {
					t.Errorf("getter returned unexpected value %q", v)
				}
			case <-time.After(hookTestTimeout):
				t.Fatal("deadlock: hook getter did not return while a writer waited for the lock")
			}

			select {
			case <-writerDone:
			case <-time.After(hookTestTimeout):
				t.Fatal("writer never acquired the lock after the hook returned")
			}
			select {
			case <-triggered:
			case <-time.After(hookTestTimeout):
				t.Fatal("trigger did not return")
			}
			assertEqual(t, writerURL, c.BaseURL())
		})
	}
}

// Regression: Close() called from an OnClose hook must be a no-op, not a deadlock.
func TestClientCloseReentrantFromOnCloseHook(t *testing.T) {
	c := dcnl()
	calls := 0
	var reentrantErr error
	c.OnClose(func() {
		calls++
		reentrantErr = c.Close()
	})

	done := make(chan error, 1)
	go func() { done <- c.Close() }()
	select {
	case err := <-done:
		assertNil(t, err)
	case <-time.After(hookTestTimeout):
		t.Fatal("deadlock: reentrant Close() from OnClose hook did not return")
	}

	assertNil(t, reentrantErr)
	assertEqual(t, 1, calls)
	assertNil(t, c.Close())
	assertEqual(t, 1, calls)
}

// Hooks run in registration order; hooks registered while a dispatch is running
// (including via a Client setter called from inside a hook) take effect from the
// next dispatch, not the one in progress.
func TestClientHookOrderAndRegistration(t *testing.T) {
	rec := func(log *[]string, name string) func() {
		return func() { *log = append(*log, name) }
	}

	for _, tc := range hookCases() {
		t.Run(tc.name, func(t *testing.T) {
			c := dcnl()
			var log []string
			tc.register(c, rec(&log, "a"))
			tc.register(c, rec(&log, "b"))
			tc.register(c, rec(&log, "c"))
			mustReturn(t, "hook dispatch", func() { tc.trigger(c) })
			assertEqual(t, []string{"a", "b", "c"}, log, "registration order")

			if !tc.repeatable {
				return
			}

			// registration from inside a running hook, then a second dispatch
			c2 := dcnl()
			var log2 []string
			tc.register(c2, func() {
				log2 = append(log2, "outer")
				tc.register(c2, rec(&log2, "late"))
			})
			mustReturn(t, "hook dispatch", func() { tc.trigger(c2) })
			assertEqual(t, []string{"outer"}, log2, "in-flight dispatch")

			log2 = nil
			mustReturn(t, "hook dispatch", func() { tc.trigger(c2) })
			assertEqual(t, []string{"outer", "late"}, log2, "next dispatch")
		})
	}
}

// Regression: Clone() copies the hook slices without isolating their backing
// arrays, so appends on the parent and the clone could overwrite each other.
func TestClientCloneHookRegistrationIsolated(t *testing.T) {
	parent := dcnl()
	var p, q int
	parent.OnClose(func() {}).OnClose(func() {}).OnClose(func() {}) // len 3, spare capacity
	clone := parent.Clone(context.Background())

	parent.OnClose(func() { p++ })
	clone.OnClose(func() { q++ })

	// the parent's hook list must still hold the hook registered on the parent
	hooks := parent.closeHooks
	assertEqual(t, 4, len(hooks))
	hooks[3]()
	assertEqual(t, 1, p)
	assertEqual(t, 0, q)
}

// Regression: circuit breaker hooks run while the breaker's lock is held, so a
// hook that registers another hook must not deadlock.
func TestCircuitBreakerHookReentrantRegistration(t *testing.T) {
	noopTrigger := func(*Request, error) {}
	noopState := func(CircuitBreakerState, CircuitBreakerState) {}

	cases := []struct {
		name string
		run  func(cb *CircuitBreakerCount)
	}{
		{
			name: "OnTrigger",
			run: func(cb *CircuitBreakerCount) {
				cb.OnTrigger(func(*Request, error) { cb.OnTrigger(noopTrigger) })
				cb.RunOnTriggerHooks(nil, ErrCircuitBreakerOpen)
			},
		},
		{
			name: "OnStateChange",
			run: func(cb *CircuitBreakerCount) {
				cb.OnStateChange(func(CircuitBreakerState, CircuitBreakerState) { cb.OnStateChange(noopState) })
				cb.RunOnStateChangeHooks(CircuitBreakerStateClosed, CircuitBreakerStateOpen)
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cb := NewCircuitBreakerCount(1, 1, time.Hour)
			done := make(chan struct{})
			go func() {
				defer close(done)
				tc.run(cb)
			}()
			select {
			case <-done:
			case <-time.After(hookTestTimeout):
				t.Fatal("deadlock: circuit breaker hook registering another hook did not return")
			}
		})
	}
}
