// Package securityoverrides anchors the repository-owned compiled-dependency
// override modules to real package imports so Go module maintenance tools do
// not treat the deliberately minimal requirements as unused.
package securityoverrides

import (
	_ "golang.org/x/crypto/cryptobyte"
	_ "google.golang.org/grpc/codes"
)
