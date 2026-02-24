package main

import (
	"fmt"
	"os"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	msg := greet("world")
	fmt.Println(msg)
	return nil
}

func greet(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}
