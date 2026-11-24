// Copyright (c) 2015-present Jeevanandam M (jeeva@myjeeva.com), All rights reserved.
// resty source code and usage is governed by a MIT style
// license that can be found in the LICENSE file.
// SPDX-License-Identifier: MIT

package resty

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"runtime"
	"sync"
	"testing"
	"time"
)

// hookWatchdog bounds how long a dispatch may take. It only converts a hang
// (deadlock) into a test failure; it is never used to provoke a condition.
const hookWatchdog = 10 * time.Second

// hookKind describes one of the client hook families and how to dispatch it.
type hookKind struct {
	name string
	// register installs fn as one hook of this family.
	register func(c *Client, fn func())
	// dispatch performs the client operation that runs this family's hooks.
	// It is invoked from a helper goroutine; it must use only t.Errorf.
	dispatch func(t *testing.T, c *Client)
	// reusable reports whether dispatch can run more than once on the same client.
	reusable bool
}

var hookKinds = []hookKind{
	{
		name:     "OnSuccess",
		register: func(c *Client, fn func()) { c.OnSuccess(func(*Client, *Response) { fn() }) },
		dispatch: func(t *testing.T, c *Client) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusOK)
			}))
			defer srv.Close()
			if _, err := c.R().Get(srv.URL); err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		},
		reusable: true,
	},
	{
		name:     "OnError",
		register: func(c *Client, fn func()) { c.OnError(func(*Request, error) { fn() }) },
		dispatch: func(t *testing.T, c *Client) {
			srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
			url := srv.URL
			srv.Close() // connection refused => transport error => OnError
			if _, err := c.R().Get(url); err == nil {
				t.Errorf("expected transport error")
			}
		},
		reusable: true,
	},
	{
		name:     "OnInvalid",
		register: func(c *Client, fn func()) { c.OnInvalid(func(*Request, error) { fn() }) },
		dispatch: func(t *testing.T, c *Client) {
			// unparsable URL => invalidRequestError => OnInvalid
			if _, err := c.R().Get("http://[::1"); err == nil {
				t.Errorf("expected invalid request error")
			}
		},
		reusable: true,
	},
	{
		name:     "OnPanic",
		register: func(c *Client, fn func()) { c.OnPanic(func(*Request, error) { fn() }) },
		dispatch: func(t *testing.T, c *Client) {
			c.SetRequestMiddlewares(func(*Client, *Request) error { panic("boom") })
			defer func() {
				if recover() == nil {
					t.Errorf("expected panic to propagate")
				}
			}()
			_, _ = c.R().Get("http://127.0.0.1:1/")
		},
		reusable: true,
	},
	{
		name:     "OnClose",
		register: func(c *Client, fn func()) { c.OnClose(func() { fn() }) },
		dispatch: func(t *testing.T, c *Client) {
			if err := c.Close(); err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		},
		reusable: false, // Close is idempotent: a second dispatch runs no hooks
	},
}

// runWithWatchdog runs dispatch in a helper goroutine and fails the test if it
// does not finish within hookWatchdog.
func runWithWatchdog(t *testing.T, k hookKind, c *Client) {
	t.Helper()
	done := make(chan struct{})
	go func() {
		defer close(done)
		k.dispatch(t, c)
	}()
	select {
	case <-done:
	case <-time.After(hookWatchdog):
		t.Fatalf("%s dispatch did not complete within %v (deadlock)", k.name, hookWatchdog)
	}
}

// waitForPendingWriter returns once a writer has entered mu.Lock (so a new
// RLock would queue behind it), or once writerDone is closed. A failed TryRLock
// means a writer is already registered on the lock; no sleep is involved.
func waitForPendingWriter(mu *sync.RWMutex, writerDone <-chan struct{}) {
	for {
		select {
		case <-writerDone:
			return
		default:
		}
		if !mu.TryRLock() {
			return
		}
		mu.RUnlock()
		runtime.Gosched()
	}
}

// Test A: a hook that queries a client getter while another goroutine waits
// for the write lock must not deadlock.
func TestClientHookGetterWhileWriterWaitsCross(t *testing.T) {
	for _, k := range hookKinds {
		t.Run(k.name, func(t *testing.T) {
			c := dcnl()
			hookRuns := 0
			writerDone := make(chan struct{})
			k.register(c, func() {
				hookRuns++
				go func() {
					defer close(writerDone)
					c.SetBaseURL("http://writer.example")
				}()
				waitForPendingWriter(c.lock, writerDone)
				_ = c.BaseURL() // would block forever on the buggy dispatcher
			})

			runWithWatchdog(t, k, c)
			select {
			case <-writerDone:
			case <-time.After(hookWatchdog):
				t.Fatalf("writer did not complete within %v", hookWatchdog)
			}
			assertEqual(t, 1, hookRuns, "hook should run exactly once")
			assertEqual(t, "http://writer.example", c.BaseURL())
		})
	}
}

// Test B: an OnClose hook calling Close again must return without blocking.
func TestClientCloseReentrantFromOnCloseCross(t *testing.T) {
	c := dcnl()
	closeHookRuns := 0
	reentrantErr := errors.New("not run")
	c.OnClose(func() {
		closeHookRuns++
		reentrantErr = c.Close()
	})

	done := make(chan struct{})
	go func() {
		defer close(done)
		assertNil(t, c.Close())
	}()
	select {
	case <-done:
	case <-time.After(hookWatchdog):
		t.Fatalf("Close did not return within %v (reentrant deadlock)", hookWatchdog)
	}

	assertEqual(t, 1, closeHookRuns)
	assertNil(t, reentrantErr)
}

// Test C1: hooks run in registration order.
func TestClientHookExecutionOrderCross(t *testing.T) {
	for _, k := range hookKinds {
		t.Run(k.name, func(t *testing.T) {
			c := dcnl()
			var got []string
			for _, id := range []string{"first", "second", "third"} {
				k.register(c, func() { got = append(got, id) })
			}

			runWithWatchdog(t, k, c)
			assertEqual(t, []string{"first", "second", "third"}, got)
		})
	}
}

// Test C2: a hook registering another hook during dispatch must not deadlock.
// The new hook is not part of the in-flight dispatch; it runs on later dispatches.
func TestClientHookRegistrationDuringDispatchCross(t *testing.T) {
	for _, k := range hookKinds {
		t.Run(k.name, func(t *testing.T) {
			c := dcnl()
			var got []string
			registered := false
			k.register(c, func() {
				got = append(got, "outer")
				if !registered {
					registered = true
					k.register(c, func() { got = append(got, "inner") })
				}
			})

			runWithWatchdog(t, k, c)
			assertEqual(t, []string{"outer"}, got, "newly registered hook must not run in the in-flight dispatch")

			if k.reusable {
				got = nil
				runWithWatchdog(t, k, c)
				assertEqual(t, []string{"outer", "inner"}, got)
			}
		})
	}
}

// Test C3: concurrent registration and dispatch are race-free (see -race).
func TestClientHookConcurrentRegistrationAndDispatchCross(t *testing.T) {
	const registrars = 8
	const perRegistrar = 10

	for _, k := range hookKinds {
		if !k.reusable {
			continue
		}
		t.Run(k.name, func(t *testing.T) {
			c := dcnl()
			var wg sync.WaitGroup
			wg.Add(registrars)
			for i := 0; i < registrars; i++ {
				go func() {
					defer wg.Done()
					for j := 0; j < perRegistrar; j++ {
						k.register(c, func() {})
					}
				}()
			}
			for i := 0; i < perRegistrar; i++ {
				runWithWatchdog(t, k, c)
			}
			wg.Wait()
		})
	}
}
