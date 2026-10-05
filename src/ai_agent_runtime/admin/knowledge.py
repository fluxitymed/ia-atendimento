"""Transactional administrative writer over the existing canonical tables."""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from uuid import UUID, uuid4, uuid5

from ai_agent_runtime.organization_config import ACTIVE_ORGANIZATION_STATUSES
from .markdown import KnowledgeError, Source, STRATEGY, VERSION, fingerprint

NAMESPACE = UUID("46f46d07-4da7-44ca-a13e-0c909aadfd3b")
MANIFEST_VERSION = 1
DIMENSIONS = 1536


def organization_uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise KnowledgeError("ORGANIZATION_ID_REQUIRED_UUID") from None


def document_id(org, source_key):
    return str(uuid5(NAMESPACE, org + "/" + source_key))


def actor_name(actor):
    # Operator identifier, not free-text notes or credentials.
    import re
    if not actor or not re.fullmatch(r"[\w.@+-]{1,100}", actor):
        raise KnowledgeError("ACTOR_REQUIRED")
    return actor


class KnowledgeAdmin:
    def __init__(self, connection, organization_id, embeddings=None):
        self.db = connection
        self.org = organization_uuid(organization_id)
        self.embeddings = embeddings

    def rows(self, sql, params=()):
        return self.db.execute(sql, params).fetchall()

    @contextmanager
    def transaction(self, *, readonly=False):
        with self.db.transaction():
            if readonly:
                self.db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            self.db.execute("SET LOCAL lock_timeout = '10s'")
            self.db.execute("SET LOCAL statement_timeout = '60s'")
            # The org lock serializes every mutation through this administrator,
            # including concurrent first imports. It also guards deactivation.
            rows = self.rows("SELECT id, status FROM organizations WHERE id = %s" +
                             ("" if readonly else " FOR UPDATE"), (self.org,))
            if len(rows) != 1 or rows[0]["status"] not in ACTIVE_ORGANIZATION_STATUSES:
                raise KnowledgeError("ORGANIZATION_NOT_ACTIVE_OR_MISSING")
            yield

    def latest(self, doc):
        rows = self.rows("""SELECT * FROM document_versions
            WHERE organization_id=%s AND document_id=%s ORDER BY version_number DESC LIMIT 1""",
            (self.org, doc))
        return rows[0] if rows else None

    def chunks(self, version):
        return self.rows("""SELECT * FROM chunks WHERE organization_id=%s AND document_version_id=%s
            ORDER BY chunk_index, id""", (self.org, version))

    def indices(self, version):
        return self.rows("""SELECT *, embedding::text AS vector_text FROM retrieval_index_entries
            WHERE organization_id=%s AND document_version_id=%s ORDER BY chunk_id, id""", (self.org, version))

    def _plan(self, source):
        doc = document_id(self.org, source.key)
        documents = self.rows("SELECT * FROM documents WHERE organization_id=%s AND id=%s", (self.org, doc))
        if documents and (documents[0]["title"] != source.key or documents[0]["document_type"] != "KNOWLEDGE_MARKDOWN"):
            raise KnowledgeError("DOCUMENT_IDENTITY_CONFLICT")
        latest = self.latest(doc)
        action = "new_document" if not documents else "new_version"
        if latest:
            chunks = self.chunks(latest["id"])
            hashes = {c["metadata"].get("source_sha256") for c in chunks}
            if hashes == {source.sha256} and latest["status"] in ("REVIEW_REQUIRED", "APPROVED", "PUBLISHED"):
                action = "unchanged"
        return {"source": source.key, "sha256": source.sha256,
                "chunk_digest": source.chunk_digest, "chunk_count": len(source.chunks),
                "document_id": doc, "version_id": str(latest["id"]) if latest else None,
                "version_number": latest["version_number"] if latest else 0, "action": action}

    def ingest(self, sources: list[Source], *, dry_run=False):
        if not sources or len({s.key for s in sources}) != len(sources):
            raise KnowledgeError("INVALID_SOURCE_COUNT")
        with self.transaction(readonly=dry_run):
            entries = []
            for source in sources:
                entry = self._plan(source)
                if not dry_run:
                    if entry["action"] != "unchanged":
                        self._insert(source, entry)
                    integrity = self._inspect(entry)
                    entry["index_digest"] = integrity["index_digest"]
                    entry["status"] = integrity["version"]["status"]
                entries.append(entry)
            return {"format_version": MANIFEST_VERSION, "organization_id": self.org,
                    "mode": "dry-run" if dry_run else "ingest", "documents": entries,
                    "summary": {key: sum(e["action"] == key for e in entries)
                                for key in ("new_document", "unchanged", "new_version")}}

    def _insert(self, source, entry):
        if self.embeddings is None:
            raise KnowledgeError("EMBEDDING_PROVIDER_REQUIRED")
        doc, ver = entry["document_id"], str(uuid4())
        if entry["action"] == "new_document":
            self.db.execute("""INSERT INTO documents (id,organization_id,document_type,title)
                VALUES (%s,%s,'KNOWLEDGE_MARKDOWN',%s)""", (doc, self.org, source.key))
        number = entry["version_number"] + 1
        self.db.execute("""INSERT INTO document_versions
            (id,organization_id,document_id,version_number,status,processing_valid,knowledge_mode)
            VALUES (%s,%s,%s,%s,'DRAFT',false,'OPEN_WORLD')""", (ver, self.org, doc, number))
        self.db.execute("UPDATE document_versions SET status='PROCESSING' WHERE organization_id=%s AND id=%s",
                        (self.org, ver))
        for i, chunk in enumerate(source.chunks):
            cid = str(uuid5(UUID(ver), str(i)))
            meta = {**chunk["metadata"], "source_key": source.key, "source_sha256": source.sha256,
                    "chunk_digest": source.chunk_digest}
            self.db.execute("""INSERT INTO chunks (id,organization_id,document_id,document_version_id,
                chunk_index,content,section_path,semantic_type,metadata,chunking_strategy,chunking_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (cid, self.org, doc, ver, i, chunk["content"], chunk["section_path"], chunk["semantic_type"],
                 json.dumps(meta), STRATEGY, VERSION))
            embedding = self.embeddings.create_embedding(text=chunk["content"])
            check_vector(embedding.vector)
            if embedding.model != self.embeddings.config.openai_embedding_model or not embedding.embedding_version:
                raise KnowledgeError("INVALID_EMBEDDING_MODEL")
            self.db.execute("""INSERT INTO retrieval_index_entries
                (id,organization_id,chunk_id,document_id,document_version_id,embedding,
                 embedding_model,embedding_version,indexed_at,metadata)
                VALUES (%s,%s,%s,%s,%s,%s::vector,%s,%s,%s,%s::jsonb)""",
                (str(uuid5(UUID(cid), "embedding")), self.org, cid, doc, ver, json.dumps(embedding.vector),
                 embedding.model, embedding.embedding_version, embedding.indexed_at, json.dumps(meta)))
        self.db.execute("""UPDATE document_versions SET status='REVIEW_REQUIRED'
            WHERE organization_id=%s AND id=%s""", (self.org, ver))
        self.db.execute("UPDATE documents SET updated_at=now() WHERE organization_id=%s AND id=%s", (self.org, doc))
        entry.update(version_id=ver, version_number=number)

    def _inspect(self, entry):
        """Independently reconstruct chunk digest and verify every object link."""
        ver, doc = entry["version_id"], entry["document_id"]
        rows = self.rows("SELECT * FROM document_versions WHERE organization_id=%s AND id=%s", (self.org, ver))
        if len(rows) != 1:
            raise KnowledgeError("VERSION_NOT_FOUND_IN_TENANT")
        version = rows[0]
        if str(version["document_id"]) != doc or version["version_number"] != entry["version_number"]:
            raise KnowledgeError("VERSION_IDENTITY_MISMATCH")
        docs = self.rows("SELECT title FROM documents WHERE organization_id=%s AND id=%s", (self.org, doc))
        if len(docs) != 1 or docs[0]["title"] != entry["source"] or doc != document_id(self.org, entry["source"]):
            raise KnowledgeError("DOCUMENT_IDENTITY_MISMATCH")
        chunks = self.chunks(ver)
        indices = self.indices(ver)
        if not chunks or len(chunks) != entry["chunk_count"] or len(indices) != len(chunks):
            raise KnowledgeError("INCOMPLETE_KNOWLEDGE_VERSION")
        payload = []
        chunk_ids = set()
        for i, chunk in enumerate(chunks):
            if (str(chunk["document_id"]) != doc or chunk["chunk_index"] != i or
                chunk["chunking_strategy"] != STRATEGY or chunk["chunking_version"] != VERSION or
                str(chunk["id"]) != str(uuid5(UUID(ver), str(i)))):
                raise KnowledgeError("CHUNK_IDENTITY_MISMATCH")
            meta = dict(chunk["metadata"])
            if (meta.pop("source_sha256", None) != entry["sha256"] or
                meta.pop("source_key", None) != entry["source"] or
                meta.pop("chunk_digest", None) != entry["chunk_digest"]):
                raise KnowledgeError("CHUNK_PROVENANCE_MISMATCH")
            payload.append({"content": chunk["content"], "section_path": chunk["section_path"],
                            "semantic_type": chunk["semantic_type"], "metadata": meta})
            chunk_ids.add(str(chunk["id"]))
        if fingerprint(payload) != entry["chunk_digest"]:
            raise KnowledgeError("CHUNK_CONTENT_MISMATCH")
        indexed_ids, index_payload, models = set(), [], set()
        for index in indices:
            cid = str(index["chunk_id"])
            if (str(index["document_id"]) != doc or cid not in chunk_ids or cid in indexed_ids or
                str(index["id"]) != str(uuid5(UUID(cid), "embedding"))):
                raise KnowledgeError("INDEX_IDENTITY_MISMATCH")
            chunk = next(c for c in chunks if str(c["id"]) == cid)
            if index["metadata"] != chunk["metadata"] or not index["indexed_at"]:
                raise KnowledgeError("INDEX_PROVENANCE_MISMATCH")
            vector = json.loads(index["vector_text"] or "null")
            check_vector(vector)
            models.add((index["embedding_model"], index["embedding_version"]))
            indexed_ids.add(cid)
            index_payload.append({"id": str(index["id"]), "chunk_id": cid, "vector": vector,
                                  "model": index["embedding_model"], "version": index["embedding_version"]})
        if len(models) != 1 or any(not x for pair in models for x in pair):
            raise KnowledgeError("INVALID_EMBEDDING_MODEL")
        index_digest = fingerprint(index_payload)
        if entry.get("index_digest") and entry["index_digest"] != index_digest:
            raise KnowledgeError("INDEX_CONTENT_MISMATCH")
        return {"version": version, "index_digest": index_digest}

    def manifest_entries(self, manifest):
        if (manifest.get("format_version") != MANIFEST_VERSION or
            manifest.get("organization_id") != self.org or manifest.get("mode") == "dry-run"):
            raise KnowledgeError("MANIFEST_TENANT_OR_FORMAT_MISMATCH")
        entries = manifest.get("documents")
        if not isinstance(entries, list) or not entries or len(entries) > 100:
            raise KnowledgeError("INVALID_MANIFEST")
        seen = set()
        for e in entries:
            required = ("source", "sha256", "chunk_digest", "chunk_count", "document_id",
                        "version_id", "version_number", "index_digest")
            if not isinstance(e, dict) or any(k not in e for k in required):
                raise KnowledgeError("INVALID_MANIFEST")
            if e["document_id"] in seen:
                raise KnowledgeError("DUPLICATE_MANIFEST_DOCUMENT")
            seen.add(e["document_id"])
        return entries

    def validate(self, manifest, sources, actor):
        actor = actor_name(actor)
        entries = self.manifest_entries(manifest)
        by_key = {s.key: s for s in sources}
        if set(by_key) != {e["source"] for e in entries}:
            raise KnowledgeError("VALIDATION_SOURCE_SET_MISMATCH")
        with self.transaction():
            for entry in entries:
                source = by_key[entry["source"]]
                if source.sha256 != entry["sha256"] or source.chunk_digest != entry["chunk_digest"]:
                    raise KnowledgeError("VALIDATION_SOURCE_CHANGED")
                v = self._inspect(entry)["version"]
                latest = self.latest(entry["document_id"])
                if str(latest["id"]) != entry["version_id"]:
                    raise KnowledgeError("STALE_VERSION")
                if v["status"] not in ("REVIEW_REQUIRED", "APPROVED", "PUBLISHED"):
                    raise KnowledgeError("VERSION_NOT_REVIEWABLE")
                if v["status"] == "REVIEW_REQUIRED":
                    self.db.execute("""UPDATE document_versions SET status='APPROVED', processing_valid=true,
                        approved_by=%s, approved_at=now() WHERE organization_id=%s AND id=%s""",
                        (actor, self.org, entry["version_id"]))
                elif not v["processing_valid"] or not v["approved_by"] or not v["approved_at"]:
                    raise KnowledgeError("APPROVAL_INVALID")
            return self._report(manifest, "validate")

    def publish(self, manifest, actor):
        actor = actor_name(actor)
        entries = self.manifest_entries(manifest)
        with self.transaction():
            # Validate the entire batch before changing any published state.
            for entry in entries:
                v = self._inspect(entry)["version"]
                if str(self.latest(entry["document_id"])["id"]) != entry["version_id"]:
                    raise KnowledgeError("STALE_VERSION")
                if v["status"] not in ("APPROVED", "PUBLISHED") or not v["processing_valid"] or not v["approved_by"] or not v["approved_at"]:
                    raise KnowledgeError("APPROVAL_REQUIRED")
                if v["effective_until"] is not None:
                    raise KnowledgeError("VERSION_HAS_END_DATE")
                future = self.rows("SELECT %s::timestamptz > now() AS future", (v["effective_from"],))[0]["future"]
                if future:
                    raise KnowledgeError("VERSION_NOT_EFFECTIVE")
            for entry in entries:
                old = self.rows("""SELECT id FROM document_versions WHERE organization_id=%s AND document_id=%s
                    AND status='PUBLISHED' AND id<>%s ORDER BY version_number DESC""",
                    (self.org, entry["document_id"], entry["version_id"]))
                self.db.execute("""UPDATE document_versions SET status='SUPERSEDED',effective_until=now()
                    WHERE organization_id=%s AND document_id=%s AND status='PUBLISHED' AND id<>%s""",
                    (self.org, entry["document_id"], entry["version_id"]))
                self.db.execute("""UPDATE document_versions SET status='PUBLISHED',published_by=%s,published_at=now(),
                    effective_from=now(),supersedes_version_id=%s
                    WHERE organization_id=%s AND id=%s AND status='APPROVED'""",
                    (actor, old[0]["id"] if old else None, self.org, entry["version_id"]))
            return self._report(manifest, "publish")

    def deactivate(self, manifest, actor):
        actor = actor_name(actor)
        entries = self.manifest_entries(manifest)
        with self.transaction():
            for entry in entries:
                v = self._inspect(entry)["version"]
                if v["status"] not in ("PUBLISHED", "INACTIVE"):
                    raise KnowledgeError("ROLLBACK_REQUIRES_CURRENT_PUBLICATION")
                if str(self.latest(entry["document_id"])["id"]) != entry["version_id"]:
                    raise KnowledgeError("STALE_VERSION")
            for entry in entries:
                self.db.execute("""UPDATE document_versions SET status='INACTIVE',effective_until=now()
                    WHERE organization_id=%s AND id=%s AND status='PUBLISHED'""", (self.org, entry["version_id"]))
            self.db.execute("""INSERT INTO operational_audit_events
                (id,organization_id,decision,tool_called,document_versions_used,payload)
                VALUES (%s,%s,'KNOWLEDGE_DEACTIVATED','admin.ingest_knowledge',%s::uuid[],%s::jsonb)""",
                (str(uuid4()), self.org, [e["version_id"] for e in entries], json.dumps({"actor": actor})))
            return self._report(manifest, "deactivate")

    def _report(self, manifest, mode):
        # Rebuild the allowlist rather than echo arbitrary input JSON to logs.
        entries = []
        keys = ("source", "sha256", "chunk_digest", "chunk_count", "document_id", "version_id",
                "version_number", "index_digest")
        for e in self.manifest_entries(manifest):
            entry = {k: e[k] for k in keys}
            entry["status"] = self._inspect(e)["version"]["status"]
            entries.append(entry)
        return {"format_version": MANIFEST_VERSION, "organization_id": self.org, "mode": mode, "documents": entries}


def check_vector(vector):
    if (not isinstance(vector, list) or len(vector) != DIMENSIONS or
        any(type(x) not in (int, float) or not math.isfinite(x) for x in vector) or
        not any(x != 0 for x in vector)):
        raise KnowledgeError("INVALID_EMBEDDING_VECTOR")
