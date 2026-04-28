// =============================================================================
// Migration 001: Create Books Collection (MongoDB)
// =============================================================================
// Collection para catalogo publico de livros (Project Gutenberg + Open Library).
// Usada pelo servico public-indexer para armazenar metadados de livros disponiveis.
// =============================================================================

const DB_NAME = process.env.MONGO_DB || "tcc_catalog";
const COLLECTION_NAME = "books";

// Seleciona o banco de dados
db = db.getSiblingDB(DB_NAME);

// -------------------------------------------------------------------------
// Drop collection existente (idempotente para re-execucao)
// -------------------------------------------------------------------------
if (db.getCollectionNames().includes(COLLECTION_NAME)) {
    print(`Dropping existing collection: ${COLLECTION_NAME}`);
    db.getCollection(COLLECTION_NAME).drop();
}

// -------------------------------------------------------------------------
// Cria collection com validacao de schema
// -------------------------------------------------------------------------
db.createCollection(COLLECTION_NAME, {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["title", "indexed"],
            properties: {
                title: {
                    bsonType: "string",
                    minLength: 1,
                    description: "Titulo do livro (obrigatorio)"
                },
                authors: {
                    bsonType: "array",
                    items: {
                        bsonType: "string"
                    },
                    description: "Lista de autores do livro"
                },
                isbn: {
                    bsonType: "string",
                    description: "ISBN do livro (quando disponivel)"
                },
                gutenberg_id: {
                    bsonType: "string",
                    description: "Identificador no Project Gutenberg"
                },
                ol_key: {
                    bsonType: "string",
                    description: "Chave no Open Library (ex: /works/OL12345W)"
                },
                formats: {
                    bsonType: "array",
                    items: {
                        bsonType: "string"
                    },
                    description: "Formatos disponiveis (txt, epub, pdf, etc)"
                },
                indexed: {
                    bsonType: "bool",
                    description: "Indica se o livro foi indexado no sistema"
                },
                indexed_at: {
                    bsonType: "date",
                    description: "Data/hora da ultima indexacao"
                },
                metadata: {
                    bsonType: "object",
                    description: "Metadados adicionais flexiveis",
                    properties: {
                        language: { bsonType: "string" },
                        subjects: {
                            bsonType: "array",
                            items: { bsonType: "string" }
                        },
                        publication_year: { bsonType: "int" },
                        publisher: { bsonType: "string" },
                        description: { bsonType: "string" }
                    }
                }
            }
        }
    },
    validationLevel: "moderate",
    validationAction: "warn"
});

print(`Collection '${COLLECTION_NAME}' created with schema validation`);

// -------------------------------------------------------------------------
// Cria indices
// -------------------------------------------------------------------------

// Indice de texto para busca full-text no titulo
db.getCollection(COLLECTION_NAME).createIndex(
    { title: "text" },
    { name: "idx_books_title_text" }
);

// Indice para busca por autores
db.getCollection(COLLECTION_NAME).createIndex(
    { authors: 1 },
    { name: "idx_books_authors" }
);

// Indice para filtrar livros ja indexados
db.getCollection(COLLECTION_NAME).createIndex(
    { indexed: 1 },
    { name: "idx_books_indexed" }
);

// Indice unico para gutenberg_id (quando presente)
db.getCollection(COLLECTION_NAME).createIndex(
    { gutenberg_id: 1 },
    { name: "idx_books_gutenberg_id", sparse: true, unique: true }
);

// Indice unico para ol_key (quando presente)
db.getCollection(COLLECTION_NAME).createIndex(
    { ol_key: 1 },
    { name: "idx_books_ol_key", sparse: true, unique: true }
);

// Indice composto para consulta de livros nao indexados por fonte
db.getCollection(COLLECTION_NAME).createIndex(
    { indexed: 1, gutenberg_id: 1 },
    { name: "idx_books_unindexed_gutenberg", partialFilterExpression: { indexed: false } }
);

print("All indexes created successfully");

// -------------------------------------------------------------------------
// Verificacao final
// -------------------------------------------------------------------------
print("\n--- Collection Info ---");
printjson(db.getCollection(COLLECTION_NAME).stats());
print("\n--- Indexes ---");
printjson(db.getCollection(COLLECTION_NAME).getIndexes());
