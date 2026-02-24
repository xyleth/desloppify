package lib

import "fmt"

// Panic in library code (non-main package)
func PanicInLib() {
	panic("library panic")
}

func SafeFunc() {
	fmt.Println("safe")
}
