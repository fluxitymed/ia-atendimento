"""Disposable PostgreSQL + pgvector. Never reads a remote database URL."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import psycopg
from psycopg.rows import dict_row


@contextmanager
def database():
    with tempfile.TemporaryDirectory(prefix="knowledge-pg-") as directory:
        root = Path(directory)
        binary = Path(os.environ.get("TEST_PG_BIN", Path(shutil.which("initdb") or "initdb").parent))
        data = root / "data"
        def run(command):
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
        run([str(binary / "initdb"), "-D", str(data), "-A", "trust", "-U", "knowledge_test", "--no-locale", "-E", "UTF8"])
        # Private unix socket directory, no TCP listener, no existing service touched.
        options = f"-F -k {root} -h '' -p 55439"
        started = False
        try:
            run([str(binary / "pg_ctl"), "-D", str(data), "-l", str(root / "postgres.log"), "-o", options, "-w", "start"])
            started = True
            dsn = f"host={root} port=55439 user=knowledge_test dbname=postgres"
            with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
                for name in ("202608200001_ai_runtime_integrations.sql", "202609070001_ai_organization_runtime_config.sql"):
                    connection.execute((Path("supabase/migrations") / name).read_text())
                yield connection, dsn
        finally:
            if started:
                run([str(binary / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop"])
