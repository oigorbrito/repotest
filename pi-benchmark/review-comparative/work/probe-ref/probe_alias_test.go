package resty

import (
	"context"
	"testing"
)

// PROBE descartável: Clone() compartilha o backing array de afterResponse?
// Verifica o último elemento do pai após o clone registrar um middleware próprio.
func TestProbeAfterResponseCloneAliasing(t *testing.T) {
	parent := dcnl()
	var got []string
	mk := func(name string) ResponseMiddleware {
		return func(*Client, *Response) error { got = append(got, name); return nil }
	}
	parent.AddResponseMiddleware(mk("a"))
	parent.AddResponseMiddleware(mk("b"))
	parent.AddResponseMiddleware(mk("c"))
	clone := parent.Clone(context.Background())
	sameArray := &parent.afterResponse[0] == &clone.afterResponse[0]
	parent.AddResponseMiddleware(mk("P"))
	clone.AddResponseMiddleware(mk("C"))
	last := parent.afterResponse[len(parent.afterResponse)-1]
	last(parent, &Response{})
	t.Logf("sameBackingArray=%v parentLastRan=%v expected=[P]", sameArray, got)
	if len(got) != 1 || got[0] != "P" {
		t.Errorf("ALIASING: parent's last response middleware was replaced by clone's: ran %v", got)
	}
}
