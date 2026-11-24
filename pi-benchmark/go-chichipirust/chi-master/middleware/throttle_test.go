package middleware

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
)

var testContent = []byte("Hello world!")

func TestThrottleBacklog(t *testing.T) {
	r := chi.NewRouter()

	r.Use(ThrottleBacklog(10, 50, time.Second*10))

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		time.Sleep(time.Second * 1) // Expensive operation.
		w.Write(testContent)
	})

	server := httptest.NewServer(r)
	defer server.Close()

	client := http.Client{
		Timeout: time.Second * 5, // Maximum waiting time.
	}

	var wg sync.WaitGroup

	// The throttler processes 10 consecutive requests, each one of those
	// requests lasts 1s. The maximum number of requests this can possible serve
	// before the clients time out (5s) is 40.
	for i := range 40 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()

			res, err := client.Get(server.URL)
			assertNoError(t, err)

			assertEqual(t, http.StatusOK, res.StatusCode)
			buf, err := io.ReadAll(res.Body)
			assertNoError(t, err)
			assertEqual(t, testContent, buf)
		}(i)
	}

	wg.Wait()
}

func TestThrottleClientTimeout(t *testing.T) {
	r := chi.NewRouter()

	r.Use(ThrottleBacklog(10, 50, time.Second*10))

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		time.Sleep(time.Second * 5) // Expensive operation.
		w.Write(testContent)
	})

	server := httptest.NewServer(r)
	defer server.Close()

	client := http.Client{
		Timeout: time.Second * 3, // Maximum waiting time.
	}

	var wg sync.WaitGroup

	for i := range 10 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_, err := client.Get(server.URL)
			assertError(t, err)
		}(i)
	}

	wg.Wait()
}

func TestThrottleTriggerGatewayTimeout(t *testing.T) {
	r := chi.NewRouter()

	r.Use(ThrottleBacklog(50, 100, time.Second*5))

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		time.Sleep(time.Second * 10) // Expensive operation.
		w.Write(testContent)
	})

	server := httptest.NewServer(r)
	defer server.Close()

	client := http.Client{
		Timeout: time.Second * 60, // Maximum waiting time.
	}

	var wg sync.WaitGroup

	// These requests will be processed normally until they finish.
	for i := range 50 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()

			res, err := client.Get(server.URL)
			assertNoError(t, err)
			assertEqual(t, http.StatusOK, res.StatusCode)
		}(i)
	}

	time.Sleep(time.Second * 1)

	// These requests will wait for the first batch to complete but it will take
	// too much time, so they will eventually receive a timeout error.
	for i := range 50 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()

			res, err := client.Get(server.URL)
			assertNoError(t, err)

			buf, err := io.ReadAll(res.Body)
			assertNoError(t, err)
			assertEqual(t, http.StatusTooManyRequests, res.StatusCode)
			assertEqual(t, errTimedOut, strings.TrimSpace(string(buf)))
		}(i)
	}

	wg.Wait()
}

func TestThrottleMaximum(t *testing.T) {
	r := chi.NewRouter()

	r.Use(ThrottleBacklog(10, 10, time.Second*5))

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		time.Sleep(time.Second * 3) // Expensive operation.
		w.Write(testContent)
	})

	server := httptest.NewServer(r)
	defer server.Close()

	client := http.Client{
		Timeout: time.Second * 60, // Maximum waiting time.
	}

	var wg sync.WaitGroup

	for i := range 20 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()

			res, err := client.Get(server.URL)
			assertNoError(t, err)
			assertEqual(t, http.StatusOK, res.StatusCode)

			buf, err := io.ReadAll(res.Body)
			assertNoError(t, err)
			assertEqual(t, testContent, buf)
		}(i)
	}

	// Wait less time than what the server takes to reply.
	time.Sleep(time.Second * 2)

	// At this point the server is still processing, all the following request
	// will be beyond the server capacity.
	for i := range 20 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()

			res, err := client.Get(server.URL)
			assertNoError(t, err)

			buf, err := io.ReadAll(res.Body)
			assertNoError(t, err)
			assertEqual(t, http.StatusTooManyRequests, res.StatusCode)
			assertEqual(t, errCapacityExceeded, strings.TrimSpace(string(buf)))
		}(i)
	}

	wg.Wait()
}

func TestThrottleRetryAfter(t *testing.T) {
	r := chi.NewRouter()
	retryAfterFn := func(ctxDone bool) time.Duration { return time.Hour }

	r.Use(ThrottleWithOpts(ThrottleOpts{
		Limit:        5,
		BacklogLimit: 0,
		RetryAfterFn: retryAfterFn,
	}))

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(time.Second * 1) // Expensive operation.
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})

	server := httptest.NewServer(r)
	defer server.Close()
	client := http.Client{}

	type result struct {
		status int
		header http.Header
	}

	var wg sync.WaitGroup
	totalRequests := 10
	resultsCh := make(chan result, totalRequests)

	for i := 0; i < totalRequests; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			res, _ := client.Get(server.URL)
			resultsCh <- result{status: res.StatusCode, header: res.Header}
		}()
	}

	wg.Wait()
	close(resultsCh)

	count200 := 0
	count429 := 0
	for res := range resultsCh {
		switch res.status {
		case http.StatusOK:
			count200++
			continue
		case http.StatusTooManyRequests:
			count429++
			assertEqual(t, "3600", res.header.Get("Retry-After"))
			continue
		default:
			t.Fatalf("Unexpected status code: %d", res.status)
			continue
		}
	}

	assertEqual(t, 5, count200)
	assertEqual(t, 5, count429)
}

func TestThrottleRetryAfterRounding(t *testing.T) {
	tests := []struct {
		delay time.Duration
		want  string
	}{
		{-time.Second, "0"},
		{0, "0"},
		{time.Nanosecond, "1"},
		{500 * time.Millisecond, "1"},
		{time.Second, "1"},
		{1500 * time.Millisecond, "2"},
		{time.Hour, "3600"},
		{time.Duration(1<<63 - 1), "9223372037"},
	}

	for _, tc := range tests {
		th := throttler{retryAfterFn: func(bool) time.Duration { return tc.delay }}
		w := httptest.NewRecorder()
		th.setRetryAfterHeaderIfNeeded(w, false)
		assertEqual(t, tc.want, w.Header().Get("Retry-After"))
	}

	w := httptest.NewRecorder()
	throttler{}.setRetryAfterHeaderIfNeeded(w, false)
	assertEqual(t, "", w.Header().Get("Retry-After"))
}

func TestThrottleCustomStatusCode(t *testing.T) {
	const timeout = time.Second * 3

	wait := make(chan struct{})

	r := chi.NewRouter()
	r.Use(ThrottleWithOpts(ThrottleOpts{Limit: 1, StatusCode: http.StatusServiceUnavailable}))
	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-wait:
		case <-time.After(timeout):
		}
		w.WriteHeader(http.StatusOK)
	})
	server := httptest.NewServer(r)
	defer server.Close()

	const totalRequestCount = 5

	codes := make(chan int, totalRequestCount)
	errs := make(chan error, totalRequestCount)
	client := &http.Client{Timeout: timeout}
	for range totalRequestCount {
		go func() {
			resp, err := client.Get(server.URL)
			if err != nil {
				errs <- err
				return
			}
			codes <- resp.StatusCode
		}()
	}

	waitResponse := func(wantCode int) {
		select {
		case err := <-errs:
			t.Fatal(err)
		case code := <-codes:
			assertEqual(t, wantCode, code)
		case <-time.After(timeout):
			t.Fatalf("waiting %d code, timeout exceeded", wantCode)
		}
	}

	for range totalRequestCount - 1 {
		waitResponse(http.StatusServiceUnavailable)
	}
	close(wait) // Allow the last request to proceed.
	waitResponse(http.StatusOK)
}

// TestThrottleAlreadyCanceled checks that a request whose context is already
// canceled or whose deadline has already expired on entry is rejected and never
// reaches the handler, even when processing and backlog capacity are available.
// Each iteration uses a fresh middleware so the race is sampled many times.
func TestThrottleAlreadyCanceled(t *testing.T) {
	const iterations = 100

	expiredDeadline := func() (context.Context, context.CancelFunc) {
		return context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	}
	canceled := func() (context.Context, context.CancelFunc) {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		return ctx, cancel
	}

	tests := []struct {
		name        string
		opts        ThrottleOpts
		ctx         func() (context.Context, context.CancelFunc)
		wantStatus  int
		wantBody    string
		wantRetry   string
		wantCtxDone bool
	}{
		{
			name:       "canceled/default",
			opts:       ThrottleOpts{Limit: 1, BacklogTimeout: time.Second},
			ctx:        canceled,
			wantStatus: http.StatusTooManyRequests,
			wantBody:   errContextCanceled + "\n",
		},
		{
			name:       "deadline/default",
			opts:       ThrottleOpts{Limit: 1, BacklogTimeout: time.Second},
			ctx:        expiredDeadline,
			wantStatus: http.StatusTooManyRequests,
			wantBody:   errContextCanceled + "\n",
		},
		{
			name: "canceled/custom-status-and-retry-after",
			opts: ThrottleOpts{
				Limit:          2,
				BacklogLimit:   3,
				BacklogTimeout: time.Second,
				StatusCode:     http.StatusServiceUnavailable,
				RetryAfterFn: func(ctxDone bool) time.Duration {
					if ctxDone {
						return 1500 * time.Millisecond
					}
					return time.Hour
				},
			},
			ctx:         canceled,
			wantStatus:  http.StatusServiceUnavailable,
			wantBody:    errContextCanceled + "\n",
			wantRetry:   "2",
			wantCtxDone: true,
		},
		{
			name: "deadline/custom-status-and-retry-after",
			opts: ThrottleOpts{
				Limit:          2,
				BacklogLimit:   3,
				BacklogTimeout: time.Second,
				StatusCode:     http.StatusServiceUnavailable,
				RetryAfterFn: func(ctxDone bool) time.Duration {
					if ctxDone {
						return 1500 * time.Millisecond
					}
					return time.Hour
				},
			},
			ctx:         expiredDeadline,
			wantStatus:  http.StatusServiceUnavailable,
			wantBody:    errContextCanceled + "\n",
			wantRetry:   "2",
			wantCtxDone: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			for i := range iterations {
				var calls atomic.Int32
				var ctxDoneSeen atomic.Int32
				opts := tc.opts
				if opts.RetryAfterFn != nil {
					inner := opts.RetryAfterFn
					opts.RetryAfterFn = func(ctxDone bool) time.Duration {
						if ctxDone {
							ctxDoneSeen.Add(1)
						}
						return inner(ctxDone)
					}
				}

				h := ThrottleWithOpts(opts)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					calls.Add(1)
					w.WriteHeader(http.StatusOK)
				}))

				ctx, cancel := tc.ctx()
				req := httptest.NewRequestWithContext(ctx, http.MethodGet, "/", nil)
				rec := httptest.NewRecorder()
				h.ServeHTTP(rec, req)
				cancel()

				if got := calls.Load(); got != 0 {
					t.Fatalf("iteration %d: handler executed %d time(s) for an already-finished context", i, got)
				}
				assertEqual(t, tc.wantStatus, rec.Code)
				assertEqual(t, tc.wantBody, rec.Body.String())
				assertEqual(t, tc.wantRetry, rec.Header().Get("Retry-After"))
				if tc.wantCtxDone {
					if tc.opts.RetryAfterFn != nil {
						assertEqual(t, int32(1), ctxDoneSeen.Load())
					}
				}

				// Recovery: a valid request must still be admitted afterwards,
				// which proves no processing or backlog token was lost.
				for range opts.Limit {
					valid := httptest.NewRequest(http.MethodGet, "/", nil)
					validRec := httptest.NewRecorder()
					h.ServeHTTP(validRec, valid)
					assertEqual(t, http.StatusOK, validRec.Code)
				}
				assertEqual(t, int32(opts.Limit), calls.Load())
			}
		})
	}
}

func BenchmarkThrottle(b *testing.B) {
	throttleMiddleware := ThrottleBacklog(1000, 50, time.Second)

	handler := throttleMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/", nil)

	b.ReportAllocs()
	for b.Loop() {
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
	}
}
