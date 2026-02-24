package main

import "fmt"

// Nil map write
func nilMapWrite() {
	var m map[string]int
	m["key"] = 1
}

// String concat in loop
func stringConcatLoop(items []string) string {
	var result string
	for _, s := range items {
		result += s + ","
	}
	return result
}

// Yoda condition
func yodaCheck(x int) bool {
	if 42 == x {
		return true
	}
	return false
}

// TODO comment
func incomplete() {
	// TODO: implement this properly
	fmt.Println("placeholder")
}

// Panic in library code (this file is package main, so panic won't be flagged)
func panicInMain() {
	panic("something went wrong")
}

// Dogsledding — excessive blank identifiers
func dogsledding() {
	_, _, _, x := multiReturn()
	fmt.Println(x)
}

func multiReturn() (int, int, int, int) {
	return 1, 2, 3, 4
}

// Too many parameters
func tooManyParams(a int, b int, c string, d bool, e float64, f int) {
	fmt.Println(a, b, c, d, e, f)
}
