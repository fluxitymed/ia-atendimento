"""Transactional administrative writer over the existing canonical tables."""
from __future__ import annotations

import json
import math
import time
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
    def __init__(self, connection, organization_id, embeddings=None, *, deadline=None):
        self.db = connection
        self.org = organization_uuid(organization_id)
        self.embeddings = embeddings
        self.deadline = deadline

    def check_deadline(self):
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise KnowledgeError("KNOWLEDGE_DEADLINE_EXCEEDED")

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
                "version_number": latest["version_number"] if latest else 0,
                "current_status": latest["status"] if latest else None, "action": action}

    def ingest(self, sources: list[Source], *, dry_run=False, correlation_id=None, actor=None, original_filename=None):
        if not sources or len({s.key for s in sources}) != len(sources):
            raise KnowledgeError("INVALID_SOURCE_COUNT")
        with self.transaction(readonly=dry_run):
            entries = []
            for source in sources:
                self.check_deadline()
                entry = self._plan(source)
                if not dry_run:
                    if entry["action"] != "unchanged":
                        self._insert(source, entry)
                    integrity = self._inspect(entry)
                    entry["index_digest"] = integrity["index_digest"]
                    entry["status"] = integrity["version"]["status"]
                entries.append(entry)
            self.check_deadline()
            report = {"format_version": MANIFEST_VERSION, "organization_id": self.org,
                    "mode": "dry-run" if dry_run else "ingest", "documents": entries,
                    "summary": {key: sum(e["action"] == key for e in entries)
                                for key in ("new_document", "unchanged", "new_version")}}
            if not dry_run and correlation_id:
                for entry in entries:
                    self._audit_event("knowledge_ingested", entry, actor, correlation_id,
                                      original_filename=original_filename,
                                      manifest={"format_version": MANIFEST_VERSION,
                                                "organization_id": self.org, "mode": "ingest",
                                                "documents": [entry]})
            return report

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
            self.check_deadline()
            cid = str(uuid5(UUID(ver), str(i)))
            meta = {**chunk["metadata"], "source_key": source.key, "source_sha256": source.sha256,
                    "chunk_digest": source.chunk_digest}
            self.db.execute("""INSERT INTO chunks (id,organization_id,document_id,document_version_id,
                chunk_index,content,section_path,semantic_type,metadata,chunking_strategy,chunking_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (cid, self.org, doc, ver, i, chunk["content"], chunk["section_path"], chunk["semantic_type"],
                 json.dumps(meta), STRATEGY, VERSION))
            embedding = self.embeddings.create_embedding(text=chunk["content"])
            self.check_deadline()
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
            self.check_deadline()
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
            self.check_deadline()
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

    def validate(self, manifest, sources, actor, *, correlation_id=None):
        actor = actor_name(actor)
        entries = self.manifest_entries(manifest)
        by_key = {s.key: s for s in sources} if sources is not None else None
        if by_key is not None and set(by_key) != {e["source"] for e in entries}:
            raise KnowledgeError("VALIDATION_SOURCE_SET_MISMATCH")
        with self.transaction():
            for entry in entries:
                self.check_deadline()
                if by_key is not None:
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
            self.check_deadline()
            report = self._report(manifest, "validate")
            if correlation_id:
                for entry in entries:
                    self._audit_event("knowledge_validated", entry, actor, correlation_id)
            return report

    def publish(self, manifest, actor, *, correlation_id=None):
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
                self.check_deadline()
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
                if correlation_id and old:
                    self._audit_event("knowledge_superseded", entry, actor, correlation_id,
                                      superseded_version=str(old[0]["id"]))
            self.check_deadline()
            report = self._report(manifest, "publish")
            if correlation_id:
                for entry in entries:
                    self._audit_event("knowledge_published", entry, actor, correlation_id)
            return report

    def _audit_event(self, decision, entry, actor, correlation_id, *, manifest=None, superseded_version=None,
                     original_filename=None):
        payload = {"documentId": entry["document_id"], "versionId": entry["version_id"],
                   "actor": actor, "correlationId": correlation_id, "outcome": "success"}
        if manifest is not None:
            payload["manifest"] = manifest
        if superseded_version is not None:
            payload["supersededVersionId"] = superseded_version
        if original_filename is not None:
            payload["originalFilename"] = original_filename
        self.db.execute("""INSERT INTO operational_audit_events
            (id,organization_id,decision,tool_called,document_versions_used,payload)
            VALUES (%s,%s,%s,'admin.knowledge',%s::uuid[],%s::jsonb)""",
            (str(uuid4()), self.org, decision, [entry["version_id"]], json.dumps(payload)))

    def manifest_for_version(self, version_id):
        with self.transaction(readonly=True):
            rows = self.rows("""SELECT payload->'manifest' AS manifest FROM operational_audit_events
                WHERE organization_id=%s AND decision='knowledge_ingested'
                AND %s::uuid = ANY(document_versions_used)
                ORDER BY created_at DESC, id DESC LIMIT 1""", (self.org, version_id))
            if not rows or not rows[0]["manifest"]:
                raise KnowledgeError("VERSION_NOT_FOUND_IN_TENANT")
            manifest = rows[0]["manifest"]
            entries = self.manifest_entries(manifest)
            if len(entries) != 1 or entries[0]["version_id"] != version_id:
                raise KnowledgeError("VERSION_NOT_FOUND_IN_TENANT")
            return manifest

    def list_documents(self):
        with self.transaction(readonly=True):
            docs = self.rows("""SELECT id,title,updated_at FROM documents
                WHERE organization_id=%s ORDER BY title,id LIMIT 1000""", (self.org,))
            return [self._document_summary(row) for row in docs]

    def _document_summary(self, row):
        versions = self.rows("""SELECT id,status,version_number,published_at,created_at
            FROM document_versions WHERE organization_id=%s AND document_id=%s
            ORDER BY version_number DESC""", (self.org, row["id"]))
        published = next((v for v in versions if v["status"] == "PUBLISHED"), None)
        pending = next((v for v in versions if v["status"] in ("REVIEW_REQUIRED", "APPROVED")), None)
        last_published = next((v for v in versions if v["published_at"]), None)
        return {"documentId": str(row["id"]), "logicalName": row["title"].removesuffix(".md"),
                "title": row["title"], "status": "PUBLISHED" if published else "PENDING" if pending else "INACTIVE",
                "publishedVersion": published["version_number"] if published else None,
                "publishedVersionId": str(published["id"]) if published else None,
                "pendingVersion": pending["version_number"] if pending else None,
                "pendingVersionId": str(pending["id"]) if pending else None,
                "pendingStatus": pending["status"] if pending else None,
                "updatedAt": row["updated_at"].isoformat(),
                "lastPublishedAt": last_published["published_at"].isoformat() if last_published else None}

    def document_detail(self, document_id):
        with self.transaction(readonly=True):
            rows = self.rows("SELECT id,title,updated_at FROM documents WHERE organization_id=%s AND id=%s",
                             (self.org, document_id))
            if len(rows) != 1:
                raise KnowledgeError("DOCUMENT_NOT_FOUND")
            return self._document_summary(rows[0])

    def document_versions(self, document_id):
        with self.transaction(readonly=True):
            rows = self.rows("SELECT id FROM documents WHERE organization_id=%s AND id=%s", (self.org, document_id))
            if len(rows) != 1:
                raise KnowledgeError("DOCUMENT_NOT_FOUND")
            versions = self.rows("""SELECT id,version_number,status,processing_valid,created_at,
                approved_at,published_at,supersedes_version_id FROM document_versions
                WHERE organization_id=%s AND document_id=%s ORDER BY version_number DESC""",
                (self.org, document_id))
            result = []
            for row in versions:
                chunk = self.rows("""SELECT metadata FROM chunks WHERE organization_id=%s
                    AND document_version_id=%s ORDER BY chunk_index LIMIT 1""", (self.org, row["id"]))
                count = self.rows("SELECT count(*) AS n FROM chunks WHERE organization_id=%s AND document_version_id=%s",
                                  (self.org, row["id"]))[0]["n"]
                filename = self.rows("""SELECT payload->>'originalFilename' AS filename FROM operational_audit_events
                    WHERE organization_id=%s AND decision='knowledge_ingested'
                    AND %s::uuid=ANY(document_versions_used) AND payload ? 'originalFilename'
                    ORDER BY created_at,id LIMIT 1""", (self.org, row["id"]))
                result.append({"versionId": str(row["id"]), "versionNumber": row["version_number"],
                               "status": row["status"], "processingValid": row["processing_valid"],
                               "contentHash": chunk[0]["metadata"].get("source_sha256") if chunk else None,
                               "chunkCount": count, "createdAt": row["created_at"].isoformat(),
                               "filename": filename[0]["filename"] if filename else None,
                               "approvedAt": row["approved_at"].isoformat() if row["approved_at"] else None,
                               "publishedAt": row["published_at"].isoformat() if row["published_at"] else None,
                               "supersedesVersionId": str(row["supersedes_version_id"]) if row["supersedes_version_id"] else None})
            return result

    def review_chunks(self, document_id, version_id):
        with self.transaction(readonly=True):
            rows = self.rows("""SELECT id FROM document_versions WHERE organization_id=%s
                AND document_id=%s AND id=%s""", (self.org, document_id, version_id))
            if len(rows) != 1:
                raise KnowledgeError("VERSION_NOT_FOUND_IN_TENANT")
            chunks = self.chunks(version_id)
            if any(str(c["document_id"]) != document_id for c in chunks):
                raise KnowledgeError("CHUNK_IDENTITY_MISMATCH")
            return [{"chunkIndex": c["chunk_index"], "content": c["content"],
                     "sectionPath": c["section_path"], "semanticType": c["semantic_type"]} for c in chunks]

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
