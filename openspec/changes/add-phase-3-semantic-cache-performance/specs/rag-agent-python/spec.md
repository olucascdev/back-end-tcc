## ADDED Requirements

### Requirement: Document version tracking for cache invalidation
The system SHALL track a monotonically increasing version number for each document. The version MUST increment whenever a document is reprocessed or updated. The version MUST be included in the process-document response so the gateway can associate cache entries with the correct document version.

#### Scenario: Initial document processing sets version to 1
- **WHEN** a document is processed for the first time
- **THEN** the document is assigned `document_version = 1` and the response includes this version

#### Scenario: Reprocessing increments version
- **WHEN** an existing document is reprocessed (same document_id, new content)
- **THEN** the `document_version` is incremented by 1 and the response includes the new version

#### Scenario: Version included in response
- **WHEN** the process-document endpoint completes successfully
- **THEN** the response includes `document_version` field alongside `document_id`, `status`, and `pages`
