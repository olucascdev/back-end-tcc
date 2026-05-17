package logger

import (
	"encoding/json"
	"testing"
)

func TestRedactMap_RedactsSensitiveFields(t *testing.T) {
	input := map[string]interface{}{
		"api_key":       "secret-key-123",
		"token":         "abc-token",
		"password":      "hunter2",
		"secret":        "my-secret",
		"email":         "user@example.com",
		"authorization": "Bearer xyz",
		"username":      "john",
		"project_id":    "proj-1",
	}

	result := RedactMap(input)

	sensitiveKeys := []string{"api_key", "token", "password", "secret", "email", "authorization"}
	for _, key := range sensitiveKeys {
		if result[key] != redactedPlaceholder {
			t.Errorf("expected %q to be redacted, got %v", key, result[key])
		}
	}

	// Campos nao sensiveis devem permanecer intactos
	if result["username"] != "john" {
		t.Errorf("expected username to be 'john', got %v", result["username"])
	}
	if result["project_id"] != "proj-1" {
		t.Errorf("expected project_id to be 'proj-1', got %v", result["project_id"])
	}
}

func TestRedactMap_NestedMaps(t *testing.T) {
	input := map[string]interface{}{
		"user": map[string]interface{}{
			"email":    "user@example.com",
			"name":     "John",
			"password": "secret",
		},
		"api_key": "key-123",
	}

	result := RedactMap(input)

	userMap, ok := result["user"].(map[string]interface{})
	if !ok {
		t.Fatal("expected user to be a map")
	}

	if userMap["email"] != redactedPlaceholder {
		t.Errorf("expected nested email to be redacted, got %v", userMap["email"])
	}
	if userMap["name"] != "John" {
		t.Errorf("expected nested name to remain, got %v", userMap["name"])
	}
	if userMap["password"] != redactedPlaceholder {
		t.Errorf("expected nested password to be redacted, got %v", userMap["password"])
	}
	if result["api_key"] != redactedPlaceholder {
		t.Errorf("expected api_key to be redacted, got %v", result["api_key"])
	}
}

func TestRedactMap_NilInput(t *testing.T) {
	result := RedactMap(nil)
	if result != nil {
		t.Errorf("expected nil result for nil input, got %v", result)
	}
}

func TestRedactMap_EmptyMap(t *testing.T) {
	result := RedactMap(map[string]interface{}{})
	if len(result) != 0 {
		t.Errorf("expected empty map, got %v", result)
	}
}

func TestRedactMap_DoesNotModifyOriginal(t *testing.T) {
	input := map[string]interface{}{
		"api_key": "secret-key",
		"name":    "test",
	}

	RedactMap(input)

	if input["api_key"] != "secret-key" {
		t.Error("original map was modified")
	}
}

func TestRedactBytes_ValidJSON(t *testing.T) {
	input := []byte(`{"api_key":"secret","message":"hello","token":"abc"}`)

	result := RedactBytes(input)

	var parsed map[string]interface{}
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("failed to unmarshal result: %v", err)
	}

	if parsed["api_key"] != redactedPlaceholder {
		t.Errorf("expected api_key redacted, got %v", parsed["api_key"])
	}
	if parsed["token"] != redactedPlaceholder {
		t.Errorf("expected token redacted, got %v", parsed["token"])
	}
	if parsed["message"] != "hello" {
		t.Errorf("expected message unchanged, got %v", parsed["message"])
	}
}

func TestRedactBytes_InvalidJSON(t *testing.T) {
	input := []byte(`not valid json`)

	result := RedactBytes(input)

	if string(result) != string(input) {
		t.Errorf("expected original bytes for invalid JSON, got %s", string(result))
	}
}

func TestRedactBytes_Empty(t *testing.T) {
	result := RedactBytes([]byte{})
	if len(result) != 0 {
		t.Errorf("expected empty result for empty input, got %s", string(result))
	}
}

func TestRedactBytes_Array(t *testing.T) {
	// JSON array nao e objeto — deve retornar original
	input := []byte(`[{"api_key":"secret"}]`)

	result := RedactBytes(input)

	// json.Unmarshal em map falha para array, retorna original
	if string(result) != string(input) {
		t.Errorf("expected original bytes for array JSON, got %s", string(result))
	}
}

func TestRedactString(t *testing.T) {
	input := `{"password":"hunter2","action":"login"}`

	result := RedactString(input)

	var parsed map[string]interface{}
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("failed to unmarshal result: %v", err)
	}

	if parsed["password"] != redactedPlaceholder {
		t.Errorf("expected password redacted, got %v", parsed["password"])
	}
	if parsed["action"] != "login" {
		t.Errorf("expected action unchanged, got %v", parsed["action"])
	}
}

func TestIsSensitive_CaseInsensitive(t *testing.T) {
	tests := []struct {
		key      string
		expected bool
	}{
		{"api_key", true},
		{"API_KEY", true},
		{"Api_Key", true},
		{"Token", true},
		{"TOKEN", true},
		{"PASSWORD", true},
		{"Secret", true},
		{"EMAIL", true},
		{"Authorization", true},
		{"username", false},
		{"api_key_hash", false},
		{"tokenized", false},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.key, func(t *testing.T) {
			result := isSensitive(tt.key)
			if result != tt.expected {
				t.Errorf("isSensitive(%q) = %v, want %v", tt.key, result, tt.expected)
			}
		})
	}
}
