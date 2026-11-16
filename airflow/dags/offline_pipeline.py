"""Offline pipeline of Open Intelligence Graph.

verify services -> ingest OpenAlex and arXiv (parallel, one task per partition) -> verify ingestion
-> quality gate -> load Postgres -> verify Postgres -> two parallel branches:
  * PDFs -> text check -> chunk + embed -> Qdrant -> verify
  * entity extraction (LLM) -> Neo4j graph -> verify
-> report.

Test it with "Trigger DAG w/ config": small limits make a quick run.
Pools (created by airflow-init): arxiv_api=1 (arXiv rate limit), openalex_api=3, heavy_compute=1 (CPU heavy).
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException, AirflowSkipException
from airflow.models.param import Param
from airflow.operators.python import get_current_context
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)
SOURCES = ["openalex", "arxiv"]


# ------------------------------------------------------------------ helpers
def _param(name: str):
    """A value from 'Trigger DAG w/ config' (empty means: use the default)."""
    return get_current_context()["params"].get(name) or None


def _plain(value):
    """Make a result safe for XCom (dates become text)."""
    return json.loads(json.dumps(value, default=str))


def _states(prefix: str) -> dict:
    """Task states of this run whose task id starts with prefix."""
    run = get_current_context()["dag_run"]
    return {ti.task_id: str(ti.state) for ti in run.get_task_instances() if ti.task_id.startswith(prefix)}


def notify_failure(context):
    """Called for every failed task. Replace the log line with Slack or email when you want alerts."""
    ti = context["task_instance"]
    log.error("ALERT task=%s run=%s try=%s error=%r log=%s",
              ti.task_id, context["run_id"], ti.try_number, context.get("exception"), ti.log_url)


# ------------------------------------------------------------------ tasks
def _make_check(name: str):
    @task(task_id=f"check_{name}", retries=2, retry_delay=timedelta(seconds=20))
    def check():
        from open_intelligence.orchestration import checks
        return _plain(getattr(checks, f"check_{name}")())
    return check()


@task
def plan_partitions(source: str) -> list[dict]:
    """Partitions that still need work (closed years already loaded are skipped)."""
    from open_intelligence.ingestion import runner
    todo = runner.plan(source, _param("ingest_query"), _param("ingest_year"))
    log.info("%s: %d partitions to ingest", source, len(todo))
    return todo


@task(retries=3, retry_delay=timedelta(minutes=5), retry_exponential_backoff=True,
      max_retry_delay=timedelta(minutes=30), execution_timeout=timedelta(hours=2))
def ingest_partition(partition: dict) -> dict:
    from open_intelligence.ingestion import runner
    return _plain(runner.run_partition(**partition, limit=_param("ingest_limit")))


@task(task_id="verify_ingestion", trigger_rule=TriggerRule.ALL_DONE)
def verify_ingestion():
    # all_done lets us accept a few failed partitions, but the services must have been healthy
    bad = {t: s for t, s in _states("verify_services.").items() if s != "success"}
    if bad:
        raise AirflowFailException(f"service checks did not pass: {bad}")
    from open_intelligence.orchestration import checks
    return _plain(checks.verify_ingestion(get_current_context()["dag_run"].start_date))


@task(retries=0, execution_timeout=timedelta(minutes=30))
def quality_gate():
    """Parse and validate the new raw files without writing. Stops the pipeline if too many are rejected."""
    from open_intelligence.processing import pipeline
    try:
        return _plain(pipeline.run(dry_run=True))
    except pipeline.QualityGateError as e:
        raise AirflowFailException(f"quality gate: {e}")


@task(retries=1, execution_timeout=timedelta(hours=1))
def load_postgres():
    from open_intelligence.processing import pipeline
    return _plain(pipeline.run())


@task(task_id="verify_postgres")
def verify_postgres():
    from open_intelligence.orchestration import checks
    return _plain(checks.verify_postgres())


@task(pool="arxiv_api", retries=1, execution_timeout=timedelta(hours=3))
def download_pdfs():
    from open_intelligence.documents import pdf_downloader
    return _plain(pdf_downloader.download_pdfs(limit=_param("pdf_limit")))


@task(execution_timeout=timedelta(hours=1))
def check_texts():
    from open_intelligence.documents import text_check
    return _plain(text_check.check_texts())


@task(pool="heavy_compute", retries=1, execution_timeout=timedelta(hours=6))
def embed_and_index():
    from open_intelligence.indexing import pipeline
    return _plain(pipeline.index_papers(limit=_param("index_limit")))


@task(task_id="verify_qdrant")
def verify_qdrant():
    from open_intelligence.orchestration import checks
    return _plain(checks.verify_qdrant())


@task(task_id="check_ollama")
def check_ollama():
    """Entity extraction is optional: without Ollama it is skipped and the rest still runs."""
    from open_intelligence.orchestration import checks
    try:
        return _plain(checks.check_ollama())
    except checks.CheckFailed as e:
        raise AirflowSkipException(f"entity extraction skipped: {e}")


@task(pool="heavy_compute", retries=1, execution_timeout=timedelta(hours=6))
def extract_entities():
    from open_intelligence.extraction import pipeline
    return _plain(pipeline.extract_papers(limit=_param("extract_limit")))


@task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS, execution_timeout=timedelta(hours=1))
def build_graph():
    from open_intelligence.graph import pipeline
    return _plain(pipeline.build_graph())


@task(task_id="verify_neo4j")
def verify_neo4j():
    from open_intelligence.orchestration import checks
    return _plain(checks.verify_neo4j())


@task(trigger_rule=TriggerRule.ALL_DONE)
def report():
    """Summary of the run. Fails the run if a stage failed (failed ingestion partitions are only warnings)."""
    context = get_current_context()
    by_state: dict[str, list] = {}
    for ti in context["dag_run"].get_task_instances():
        if ti.task_id == "report":
            continue
        name = ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]"
        by_state.setdefault(str(ti.state), []).append(name)

    problems = by_state.get("failed", []) + by_state.get("upstream_failed", [])
    partition_failures = [p for p in problems if p.startswith("ingestion.") and "[" in p]
    critical = [p for p in problems if p not in partition_failures]

    stages = ["verify_ingestion", "quality_gate", "load_postgres", "verify_postgres", "download_pdfs",
              "check_texts", "embed_and_index", "verify_qdrant", "extract_entities", "build_graph", "verify_neo4j"]
    results = {}
    for stage in stages:
        for task_id in (stage, *[f"{g}.{stage}" for g in ("processing", "documents_and_vectors", "knowledge_graph")]):
            value = context["ti"].xcom_pull(task_ids=task_id)
            if value is not None:
                results[stage] = value
                break
    log.info("states: %s", {state: len(ids) for state, ids in by_state.items()})
    log.info("results: %s", json.dumps(results, default=str))
    if partition_failures:
        log.warning("ingestion partitions that failed (warning only): %s", partition_failures)
    if by_state.get("skipped"):
        log.info("skipped: %s", by_state["skipped"])
    if critical:
        raise AirflowFailException(f"pipeline finished with failures: {critical}")
    return {"states": {state: len(ids) for state, ids in by_state.items()},
            "ingestion_partition_failures": len(partition_failures)}


# ------------------------------------------------------------------ the DAG
@dag(
    dag_id="offline_pipeline",
    description="Ingest -> clean -> Postgres -> PDFs -> Qdrant vectors and Neo4j graph",
    schedule="0 3 * * 1",  # Mondays 03:00
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "oig", "retries": 1, "retry_delay": timedelta(minutes=2),
                  "on_failure_callback": notify_failure},
    params={
        "ingest_query": Param(None, type=["null", "string"], description="only this query, e.g. rag (empty = all)"),
        "ingest_year": Param(None, type=["null", "integer"], description="only this year (empty = all)"),
        "ingest_limit": Param(None, type=["null", "integer"], description="test: stop after about N works per partition"),
        "pdf_limit": Param(None, type=["null", "integer"], description="PDFs to download (empty = config)"),
        "index_limit": Param(None, type=["null", "integer"], description="papers to embed (empty = config)"),
        "extract_limit": Param(25, type=["null", "integer"], description="papers for entity extraction"),
    },
    tags=["offline", "ingestion", "indexing", "graph"],
    doc_md=__doc__,
)
def offline_pipeline():
    # 1. services must be healthy (all checks run in parallel)
    with TaskGroup("verify_services") as verify_services:
        for name in ["config", "postgres", "minio", "qdrant", "neo4j"]:
            _make_check(name)

    # 2. ingestion: both sources in parallel, one mapped task per partition, rate limits through pools
    with TaskGroup("ingestion") as ingestion:
        for source in SOURCES:
            with TaskGroup(source):
                partitions = plan_partitions.override(task_id="plan")(source)
                ingest_partition.override(task_id="ingest", pool=f"{source}_api").expand(partition=partitions)
    ingested = verify_ingestion()

    # 3. clean, validate, quality gate, load
    with TaskGroup("processing"):
        gate = quality_gate()
        loaded = load_postgres()
        gate >> loaded
    verified = verify_postgres()

    # 4a. PDFs -> text check -> embeddings -> Qdrant
    with TaskGroup("documents_and_vectors") as vector_path:
        download = download_pdfs()
        texts = check_texts()
        embedded = embed_and_index()
        vectors_ok = verify_qdrant()
        download >> texts >> embedded >> vectors_ok

    # 4b. entity extraction -> Neo4j graph (runs in parallel with 4a)
    with TaskGroup("knowledge_graph"):
        ollama = check_ollama()
        extracted = extract_entities()
        graph = build_graph()
        graph_ok = verify_neo4j()
        ollama >> extracted >> graph >> graph_ok

    verify_services >> ingestion >> ingested >> gate
    loaded >> verified >> [vector_path, ollama]
    verified >> graph  # the graph is still built (metadata + older entities) if Ollama is down
    [vectors_ok, graph_ok] >> report()


offline_pipeline()