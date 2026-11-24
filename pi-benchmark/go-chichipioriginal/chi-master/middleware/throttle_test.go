package middleware

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
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

func TestThrottleAlreadyCanceled(t *testing.T) {
	canceledCtx := func() (context.Context, context.CancelFunc) {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		return ctx, cancel
	}
	expiredCtx := func() (context.Context, context.CancelFunc) {
		return context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	}

	tests := []struct {
		name      string
		ctx       func() (context.Context, context.CancelFunc)
		opts      ThrottleOpts
		wantCode  int
		wantRetry string
	}{
		{
			name:     "canceled with default status",
			ctx:      canceledCtx,
			opts:     ThrottleOpts{Limit: 1, BacklogLimit: 1, BacklogTimeout: time.Second},
			wantCode: http.StatusTooManyRequests,
		},
		{
			name: "expired deadline with custom status and retry-after",
			ctx:  expiredCtx,
			opts: ThrottleOpts{
				Limit: 1, BacklogLimit: 1, BacklogTimeout: time.Second,
				StatusCode: http.StatusServiceUnavailable,
				RetryAfterFn: func(ctxDone bool) time.Duration {
					if !ctxDone {
						return 0
					}
					return 1500 * time.Millisecond
				},
			},
			wantCode:  http.StatusServiceUnavailable,
			wantRetry: "2",
		},
		{
			name: "canceled with custom status and retry-after",
			ctx:  canceledCtx,
			opts: ThrottleOpts{
				Limit: 2, BacklogLimit: 1, BacklogTimeout: time.Second,
				StatusCode: http.StatusServiceUnavailable,
				RetryAfterFn: func(ctxDone bool) time.Duration {
					if !ctxDone {
						return time.Hour
					}
					return 90 * time.Second
				},
			},
			wantCode:  http.StatusServiceUnavailable,
			wantRetry: "90",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			mw := ThrottleWithOpts(tc.opts)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls++
				w.WriteHeader(http.StatusOK)
			}))

			// Repeat to make the random choice in the admission select observable:
			// each rejected request must return its tokens, so the loop also
			// checks that rejections do not leak capacity or backlog.
			for range 200 {
				ctx, cancel := tc.ctx()
				req := httptest.NewRequest(http.MethodGet, "/", nil).WithContext(ctx)
				rec := httptest.NewRecorder()
				mw.ServeHTTP(rec, req)
				cancel()

				if calls != 0 {
					t.Fatalf("handler executed %d time(s) for an already-cancelled request", calls)
				}
				assertEqual(t, tc.wantCode, rec.Code)
				assertEqual(t, errContextCanceled, strings.TrimSpace(rec.Body.String()))
				assertEqual(t, tc.wantRetry, rec.Header().Get("Retry-After"))
			}
		})
	}

	// Recovery: after the rejections, valid requests must still be admitted,
	// and the full configured capacity (Limit=2) must still be available.
	const limit = 2
	arrived := make(chan struct{}, limit)
	release := make(chan struct{})
	mw := ThrottleWithOpts(ThrottleOpts{Limit: limit, BacklogLimit: 1, BacklogTimeout: time.Second})
	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Block") != "" {
			arrived <- struct{}{}
			<-release
		}
		w.WriteHeader(http.StatusOK)
	}))

	for range 50 {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil).WithContext(ctx))
		assertEqual(t, http.StatusTooManyRequests, rec.Code)
	}

	codes := make(chan int, limit)
	for range limit {
		go func() {
			rec := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, "/", nil)
			req.Header.Set("X-Block", "1")
			handler.ServeHTTP(rec, req)
			codes <- rec.Code
		}()
	}

	for range limit {
		select {
		case <-arrived:
		case <-time.After(5 * time.Second):
			t.Fatal("valid requests were not admitted after cancelled rejections")
		}
	}
	close(release)
	for range limit {
		assertEqual(t, http.StatusOK, <-codes)
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
