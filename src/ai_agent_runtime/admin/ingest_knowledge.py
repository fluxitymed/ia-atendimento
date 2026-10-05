"""python -m ai_agent_runtime.admin.ingest_knowledge --help"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .knowledge import KnowledgeAdmin, organization_uuid
from .markdown import KnowledgeError, read_sources


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes untrusted arguments, including accidental keys.
        raise KnowledgeError("INVALID_ARGUMENTS_USE_HELP")


def parser():
    p = SafeParser(description="Administração transacional de Markdown. Não usa o smoke sandbox.")
    p.add_argument("--organization-id", required=True)
    source = p.add_mutually_exclusive_group()
    source.add_argument("--directory", type=Path)
    source.add_argument("--file", type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    for name in ("dry-run", "ingest", "validate", "publish", "deactivate", "smoke"):
        mode.add_argument("--" + name, action="store_true")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--actor", help="Identificador do revisor/publicador; validate registra a aprovação humana.")
    p.add_argument("--query", action="append", help="Consulta de smoke; não é impressa no relatório.")
    return p


def smoke(admin, manifest, retrieval, queries):
    entries = admin.manifest_entries(manifest)
    if not queries or any(not q.strip() for q in queries):
        raise KnowledgeError("SMOKE_QUERIES_REQUIRED")
    with admin.transaction(readonly=True):
        for e in entries:
            v = admin._inspect(e)["version"]
            if (v["status"] != "PUBLISHED" or not v["processing_valid"] or
                str(admin.latest(e["document_id"])["id"]) != e["version_id"]):
                raise KnowledgeError("SMOKE_VERSION_NOT_CURRENT")
        expected = {e["document_id"]: e["version_id"] for e in entries}
        found = set()
        for query in queries:
            hits = retrieval.search(admin.org, query)
            if not hits:
                raise KnowledgeError("SMOKE_NO_EVIDENCE")
            for hit in hits:
                if (hit.get("organization_id") != admin.org or
                    hit.get("document_id") not in expected or
                    hit.get("document_version_id") != expected[hit["document_id"]]):
                    raise KnowledgeError("SMOKE_UNEXPECTED_EVIDENCE")
                found.add(hit["document_version_id"])
        return {"mode": "smoke", "organization_id": admin.org, "passed": True,
                "queries_checked": len(queries), "versions_checked": len(entries),
                "versions_retrieved": sorted(found)}


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        org = organization_uuid(args.organization_id)
        path = args.directory or args.file
        needs_source = args.dry_run or args.ingest or args.validate
        needs_manifest = args.validate or args.publish or args.deactivate or args.smoke
        if bool(path) != bool(needs_source) or bool(args.manifest) != bool(needs_manifest):
            raise KnowledgeError("INVALID_MODE_INPUTS")
        if (args.validate or args.publish or args.deactivate) and not args.actor:
            raise KnowledgeError("ACTOR_REQUIRED")
        if args.directory and not args.directory.is_dir():
            raise KnowledgeError("DIRECTORY_REQUIRED")
        if args.file and not args.file.is_file():
            raise KnowledgeError("FILE_REQUIRED")
        sources = read_sources(path) if path else None
        manifest = None
        if args.manifest:
            if args.manifest.stat().st_size > 1_000_000:
                raise KnowledgeError("INVALID_MANIFEST")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise KnowledgeError("INVALID_MANIFEST")
        # Deliberately do not load .env: connection/embedding credentials must be
        # explicitly exported for this administrative operation.
        dsn = os.environ.get("KNOWLEDGE_DATABASE_URL")
        if not dsn:
            raise KnowledgeError("KNOWLEDGE_DATABASE_URL_REQUIRED")
        import psycopg
        from psycopg.rows import dict_row
        provider = None
        if args.ingest:
            from ai_agent_runtime.integrations.config import IntegrationConfig
            from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
            config = IntegrationConfig(openai_api_key=os.environ.get("OPENAI_API_KEY"),
                openai_embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", IntegrationConfig.openai_embedding_model))
            # Same canonical provider/config defaults as the application.
            provider = OpenAIResponsesProvider(config)
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row, connect_timeout=10) as db:
            admin = KnowledgeAdmin(db, org, provider)
            if args.dry_run or args.ingest:
                report = admin.ingest(sources, dry_run=args.dry_run)
            elif args.validate:
                report = admin.validate(manifest, sources, args.actor)
            elif args.publish:
                report = admin.publish(manifest, args.actor)
            elif args.deactivate:
                report = admin.deactivate(manifest, args.actor)
            else:
                from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval
                url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                if not url or not key:
                    raise KnowledgeError("RETRIEVAL_CONFIGURATION_REQUIRED")
                report = smoke(admin, manifest, ZApiRuntimeRetrieval(supabase_url=url, service_role_key=key), args.query)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except KnowledgeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except (Exception, KeyboardInterrupt):
        # Drivers/provider errors may contain DSNs, SQL values or API responses.
        print(json.dumps({"error": "KNOWLEDGE_OPERATION_FAILED"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
