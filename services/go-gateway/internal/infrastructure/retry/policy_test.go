package retry

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"
)

var errRetryable = errors.New("retryable error")
var errNonRetryable = errors.New("non-retryable error")

func TestPolicy_ExecuteSuccessOnFirstAttempt(t *testing.T) {
	policy := NewPolicy(Config{
		MaxRetries:      3,
		BaseDelay:       10 * time.Millisecond,
		MaxDelay:        100 * time.Millisecond,
		RetryableErrors: []error{errRetryable},
	})

	calls := 0
	err := policy.Execute(context.Background(), "test", func() error {
		calls++
		return nil
	})

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if calls != 1 {
		t.Errorf("expected 1 call, got %d", calls)
	}
}

func TestPolicy_ExecuteSuccessAfterRetries(t *testing.T) {
	policy := NewPolicy(Config{
		MaxRetries:      3,
		BaseDelay:       5 * time.Millisecond,
		MaxDelay:        50 * time.Millisecond,
		RetryableErrors: []error{errRetryable},
	})

	var calls atomic.Int32
	err := policy.Execute(context.Background(), "test", func() error {
		c := calls.Add(1)
		if c < 3 {
			return errRetryable
		}
		return nil
	})

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if calls.Load() != 3 {
		t.Errorf("expected 3 calls (2 retries + 1 success), got %d", calls.Load())
	}
}

func TestPolicy_ExecuteExhaustedRetries(t *testing.T) {
	policy := NewPolicy(Config{
		MaxRetries:      2,
		BaseDelay:       5 * time.Millisecond,
		MaxDelay:        50 * time.Millisecond,
		RetryableErrors: []error{errRetryable},
	})

	var calls atomic.Int32
	err := policy.Execute(context.Background(), "test", func() error {
		calls.Add(1)
		return errRetryable
	})

	if err == nil {
		t.Fatal("expected error after exhausted retries, got nil")
	}
	if err != errRetryable {
		t.Errorf("expected errRetryable, got %v", err)
	}
	// 1 initial + 2 retries = 3 total calls
	if calls.Load() != 3 {
		t.Errorf("expected 3 calls (1 + 2 retries), got %d", calls.Load())
	}
}

func TestPolicy_NoRetryForNonRetryableError(t *testing.T) {
	policy := NewPolicy(Config{
		MaxRetries:      3,
		BaseDelay:       10 * time.Millisecond,
		MaxDelay:        100 * time.Millisecond,
		RetryableErrors: []error{errRetryable},
	})

	var calls atomic.Int32
	err := policy.Execute(context.Background(), "test", func() error {
		calls.Add(1)
		return errNonRetryable
	})

	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if err != errNonRetryable {
		t.Errorf("expected errNonRetryable, got %v", err)
	}
	// Should fail immediately without retry
	if calls.Load() != 1 {
		t.Errorf("expected 1 call (no retry for non-retryable), got %d", calls.Load())
	}
}

func TestPolicy_ContextCancelationStopsRetry(t *testing.T) {
	policy := NewPolicy(Config{
		MaxRetries:      5,
		BaseDelay:       100 * time.Millisecond,
		MaxDelay:        500 * time.Millisecond,
		RetryableErrors: []error{errRetryable},
	})

	ctx, cancel := context.WithCancel(context.Background())

	var calls atomic.Int32
	errCh := make(chan error, 1)

	go func() {
		err := policy.Execute(ctx, "test", func() error {
			c := calls.Add(1)
			if c == 2 {
				cancel()
			}
			return errRetryable
		})
		errCh <- err
	}()

	select {
	case err := <-errCh:
		// Context was canceled, should return context error
		if err == nil {
			t.Fatal("expected error from context cancellation, got nil")
		}
		if err != context.Canceled {
			t.Errorf("expected context.Canceled, got %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("test timed out — retry did not stop on context cancellation")
	}
}
