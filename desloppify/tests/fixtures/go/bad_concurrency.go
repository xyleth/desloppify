package main

import (
	"fmt"
	"os"
	"os/signal"
	"time"
)

// time.Tick leak
func tickLeak() {
	ch := time.Tick(time.Second)
	for range ch {
		fmt.Println("tick")
	}
}

// Defer in loop
func deferInLoop(paths []string) {
	for _, p := range paths {
		f, _ := os.Open(p)
		defer f.Close()
		fmt.Println(f.Name())
	}
}

// Fire-and-forget goroutine
func fireAndForget() {
	go func() {
		fmt.Println("running in background")
	}()
}

// Unbuffered signal channel
func unbufferedSignal() {
	ch := make(chan os.Signal)
	signal.Notify(ch, os.Interrupt)
	<-ch
}

// Single-case select
func singleSelect(ch chan int) {
	select {
	case v := <-ch:
		fmt.Println(v)
	}
}
