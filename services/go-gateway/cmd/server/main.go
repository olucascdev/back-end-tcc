// Entrypoint do servidor Go Gateway.
// Inicializa configuracao, aplica setup do Gin e inicia listener.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/olucasdev/tcc/go-gateway/internal/app"
	"github.com/olucasdev/tcc/go-gateway/internal/config"
)

func main() {
	// Carregar configuracoes de variaveis de ambiente
	cfg := config.LoadConfig()

	// Setup do router Gin e recursos de background (fila PDF, worker pool)
	router, cleanup := app.Setup(cfg)

	// Configurar servidor HTTP com timeouts
	srv := &http.Server{
		Addr:         ":" + cfg.ServerPort,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Iniciar servidor em goroutine para graceful shutdown
	go func() {
		log.Printf("Go Gateway starting on port %s", cfg.ServerPort)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed to start: %v", err)
		}
	}()

	// Aguardar sinal de interrupcao para graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	// Graceful shutdown com timeout de 10s para drenar conexoes ativas
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Encerrar worker pool e recursos de background antes do shutdown HTTP
	cleanup()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited properly")
}
