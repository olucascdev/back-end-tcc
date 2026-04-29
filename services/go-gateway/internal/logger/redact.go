// Package logger fornece logging estruturado em JSON para o gateway.
// Usa log/slog (pacote padrao do Go 1.21+) com handler JSON.
package logger

import (
	"encoding/json"
	"strings"
)

// sensitiveFields lista de chaves consideradas sensiveis e que devem ser
// redacionadas antes de registrar em logs.
var sensitiveFields = []string{
	"api_key",
	"token",
	"password",
	"secret",
	"email",
	"authorization",
}

const redactedPlaceholder = "[REDACTED]"

// RedactMap redaciona campos sensiveis em um map[string]interface{}.
// Retorna um novo mapa com os valores sensiveis substituidos por [REDACTED].
// O mapa original nao e modificado.
func RedactMap(data map[string]interface{}) map[string]interface{} {
	if data == nil {
		return nil
	}

	result := make(map[string]interface{}, len(data))
	for k, v := range data {
		if isSensitive(k) {
			result[k] = redactedPlaceholder
			continue
		}
		// Redacao recursiva para mapas aninhados
		if nested, ok := v.(map[string]interface{}); ok {
			result[k] = RedactMap(nested)
			continue
		}
		result[k] = v
	}
	return result
}

// RedactBytes redaciona campos sensiveis em JSON bruto ([]byte).
// Retorna um novo []byte com os valores sensiveis substituidos por [REDACTED].
// Se o JSON nao for valido, retorna o original sem modificacao.
func RedactBytes(data []byte) []byte {
	if len(data) == 0 {
		return data
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		// JSON invalido ou nao e objeto — retorna original
		return data
	}

	redacted := RedactMap(parsed)
	out, err := json.Marshal(redacted)
	if err != nil {
		return data
	}
	return out
}

// RedactString redaciona campos sensiveis em uma string JSON.
// Conveniente para logging direto com slog.
func RedactString(data string) string {
	return string(RedactBytes([]byte(data)))
}

// isSensitive verifica se uma chave corresponde a um campo sensivel.
// Comparacao case-insensitive para cobrir variacoes de nomenclatura.
func isSensitive(key string) bool {
	lower := strings.ToLower(key)
	for _, field := range sensitiveFields {
		if lower == field {
			return true
		}
	}
	return false
}
