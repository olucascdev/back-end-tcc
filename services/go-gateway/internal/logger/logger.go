// Package logger fornece logging estruturado em JSON para o gateway.
// Usa log/slog (pacote padrao do Go 1.21+) com handler JSON.
package logger

import (
	"io"
	"log/slog"
	"os"
	"time"
)

// Setup configura o logger global com formato JSON e nivel INFO.
// Retorna o logger configurado para uso explicito quando necessario.
func Setup(output io.Writer, level slog.Level) *slog.Logger {
	if output == nil {
		output = os.Stdout
	}

	handler := slog.NewJSONHandler(output, &slog.HandlerOptions{
		Level: level,
		// Substitui a chave "time" por "timestamp" no formato ISO 8601
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			if a.Key == slog.TimeKey {
				if t, ok := a.Value.Any().(time.Time); ok {
					return slog.String("timestamp", t.Format(time.RFC3339Nano))
				}
			}
			// Renomeia "msg" para "message" para consistencia com Python
			if a.Key == slog.MessageKey {
				return slog.String("message", a.Value.String())
			}
			return a
		},
	})

	logger := slog.New(handler)
	slog.SetDefault(logger)
	return logger
}

// Default retorna o logger padrao configurado com Setup.
// Conveniente para uso em middlewares e handlers.
func Default() *slog.Logger {
	return slog.Default()
}
