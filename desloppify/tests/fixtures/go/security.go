package main

import (
	"database/sql"
	"fmt"
	"os/exec"
)

// SQL injection — query built with string formatting on same line
func sqlInjection(db *sql.DB, userInput string) {
	db.Query(fmt.Sprintf("SELECT * FROM users WHERE name = '%s'", userInput))
}

// Command injection
func commandInjection(cmd string) {
	exec.Command("sh", "-c", cmd)
}
