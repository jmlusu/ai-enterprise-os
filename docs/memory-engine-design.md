# Memory Engine Design

## 1. Strategic Role — Cognitive Persistence

The Memory Engine is the **cognitive core** of the AI Enterprise OS. At scale — 84+
autonomous agents across 17 departments — the primary engineering challenge shifts
from task execution to **context management**. Without a sophisticated persistence
layer, agents suffer from *context-window pollution*: the dilution of relevant
triggers by transient operational noise. The engine solves this by synthesizing
collective experience into a queryable narrative, ensuring continuity as individual
models are updated or replaced.

> "Forgetting is a feature, not a failure."

This philosophy differentiates the engine from standard database storage. While
traditional systems aim for infinite data accumulation, the Memory Engine recognizes
that cognitive efficiency requires intentional noise reduction. By pruning low-utility
data and prioritizing high-signal insights, the engine ensures that agent recall
remains performant and strategically aligned.

---

## 2. Memory Taxonomy — 6 Types

The engine mirrors cognitive science to segment data by utility and retrieval
frequency, preventing factual resolutions from being buried under narrative logs.

| Type | Core Purpose | Writer | Strategic Impact |
|---|---|---|---|
| **Episodic** | Temporal narrative of activity and task outcomes | `record_task_outcome()` via Executor | Historical context for successes and failures |
| **Semantic** | Factual knowledge, resolutions, approvals | `BaseService.record_knowledge()` | "Truth" layer for declarative organizational facts |
| **Procedural** | Step-by-step workflows and operational how-to | `integration.record_procedure()` | Consistency in SOP execution |
| **Relational** | Entity mappings (agent-to-agent, agent-to-department) | `MemoryStore.store("relational")` | In-memory only; no on-disk persistence yet |
| **Temporal** | Time-stamped events and chronologies for sequencing | `MemoryStore.store("temporal")` | In-memory only; runtime sequence analysis |
| **Aggregate** | Computed summaries, rollups, statistical digests | `MemoryStore.consolidate_all()` | Transforms raw logs into strategic insights |

### 2.1 Content Formats

**Episodic** — Narrative strings with metadata (`task_id`, `status`, `department`) and
automated tags for agents/tools.
```
"Task t-001: Deploy the API. Status: completed. Result: Deployed to staging."
```

**Semantic** — Declarative statements and normalized resolutions.
```
"Resolution for 'Login issue': Password reset"
"Contract 'NDA' with Acme approved. Value: $0.00."
```
Deduplication: normalizes whitespace and lowercases content to preserve the earliest
"truth" entry.

**Procedural** — Ordered step sequences extracted by the Consolidator from repeated
episodic patterns.

**Relational** — Adjacency pairs: `{agent_id: "alice", relates_to: "bob", type: "reports_to"}`.

**Temporal** — Timestamp-keyed events: `{timestamp, event_type, agent_id, payload}`.

**Aggregate** — Computed dicts with `top_tags`, `top_agents`, `latest`, `most_accessed`.

---

## 3. Data Model: MemoryEntry

```python
@dataclass
class MemoryEntry:
    # Identity
    id: str  # "mem_20260730_143022_123456789"
    memory_type: MemoryType  # episodic | semantic | procedural | relational | temporal | aggregate

    # Content
    content: dict[str, Any]  # type-specific payload
    summary: str  # auto-generated one-liner
    tags: list[str]  # automated + manual tags
    source: str  # writer identifier (agent_id or service)

    # Salience
    importance: float  # 0.0–1.0, decays over time
    base_importance: float  # initial importance (before decay)
    recall_count: int  # incremented on every retrieve()

    # Topology
    parent_id: str | None  # causal/relational parent
    agent_id: str | None  # originating agent
    session_id: str | None  # originating session

    # Lifecycle
    version: int  # incremented on update
    tier: str  # working | short_term | long_term | archived
    encrypted: bool  # true if payload is AES-256-GCM encrypted
    archived: bool  # soft-delete flag
    consolidated: bool  # true if merged into an aggregate

    # Temporal
    created_at: datetime
    updated_at: datetime | None
    accessed_at: datetime | None
    expires_at: datetime | None  # auto-archival deadline

    # Embedding (semantic search)
    embedding: list[float] | None  # 384-dim from all-MiniLM-L6-v2

    # Extensibility
    metadata: dict[str, Any]  # arbitrary key-value extensions
```

### 2.2 MemoryType Enum

```python
class MemoryType(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    RELATIONAL = "relational"
    TEMPORAL = "temporal"
    AGGREGATE = "aggregate"
```

---

## 3. Persistence Layer — FileStore

A simplicity-over-scale file-based approach prioritizing reliability and transparency.

### 3.1 Atomic Writes

```python
def atomic_write(path: Path, data: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)  # atomic on POSIX; race-free on Windows
    except:
        os.unlink(tmp_path)
        raise
```

### 3.2 Cross-Platform Locking

```python
class FileLock:
    def __enter__(self):
        self.lock_fd = open(self.lock_path, "w")
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        self.lock_fd.close()
```

### 3.3 Redundancy

Every write generates an optional `.bak` backup copy before overwriting.

```python
def safe_write(store_path: Path, data: dict) -> None:
    backup = store_path.with_suffix(".bak")
    if store_path.exists():
        shutil.copy2(store_path, backup)
    atomic_write(store_path, data)
```

### 3.4 Filesystem Layout

```
memory/
├── memory-index.yaml        # Vestigial artifact — NOT consumed by engine (to be cleaned)
├── episodic.json            # Primary store: Episodic memory
├── semantic.json            # Primary store: Semantic memory (deduplicated)
├── procedural.json          # Primary store: Procedural memory
├── relational.json          # FUTURE: not yet auto-written
├── temporal.json            # FUTURE: not yet auto-written
├── aggregate.json           # Computed by consolidation pipeline
├── vector_index/            # Persisted embedding vectors (entry_id → float array)
│   └── *.npy
├── embeddings/              # Cache for sentence-transformers model
│   └── ...
├── working/                 # FUTURE: per-session working memory
├── short-term/              # FUTURE: session-scoped short-term (currently non-functional)
├── long-term/               # FUTURE: durable long-term (currently non-functional)
└── archive/                 # Cold storage for forgotten/purged entries
```

Per-type JSON files share a common schema (serialized `MemoryEntry.to_dict()`)
with a `memory_type` discriminator so the loader can dispatch to the correct list.

---

## 4. Search — Substring and Semantic Vector Retrieval

Agents are required to "warm" their context through a **Recall-Before-Execute**
search before initiating new tasks.

### 4.1 Keyword Search (Default)

- Case-insensitive substring matching across `content`, `tags`, `source`, `summary`
- Tag intersection filter (AND/OR)
- Term-frequency scoring across concatenated text fields
- No external dependencies

### 4.2 Vector Search (Semantic)

When `numpy` and `sentence-transformers` are available:

- **Model**: `all-MiniLM-L6-v2` (384-dimensional)
- **Algorithm**: L2-normalized dot product (cosine similarity) via `numpy`
- **Threshold**: configurable minimum score (default: `0.3`)
- **Index**: per-type HNSW or flat numpy arrays

```python
def vector_search(query: str, k: int = 10, min_score: float = 0.3) -> list[ScoredEntry]:
    query_vec = embedder.encode(query)
    query_vec = query_vec / np.linalg.norm(query_vec)
    scores = np.dot(index, query_vec)  # index: (N, 384) float array
    top_k = np.argsort(scores)[-k:][::-1]
    return [
        ScoredEntry(entry=entries[i], score=float(scores[i]))
        for i in top_k
        if scores[i] >= min_score
    ]
```

### 4.3 Graceful Fallback

```python
def search(query: str, **filters) -> list[MemoryEntry]:
    if _vector_search_available():
        try:
            return _vector_search(query, **filters)
        except Exception:
            logger.warning("Vector search failed, falling back to substring")
    return _substring_search(query, **filters)
```

Vector search is strategically optional — missing dependencies or an empty index
automatically degrades to substring search with approximate density scoring,
ensuring memory recall is non-blocking and resilient.

---

## 5. Lifecycle Management — Consolidation, Pruning, Aggregation

Intentional forgetting is the primary mechanism for maintaining system latency.

### 5.1 Consolidation Pipeline

Managed by a `ConsolidationScheduler` that runs every **50 ticks** or **3600s**
(whichever hits first). Pruning occurs **before** aggregation so summaries are
based on clean data.

```
    ┌──────────────────────────────────────────┐
    │          Consolidation Tick               │
    │  (every 50 ticks  OR  3600s elapsed)      │
    └────────────┬─────────────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  1. Prune                    │
    │     - Episodic age > 90d     │
    │     - Per-type cap > 2000    │
    │     - Importance < threshold │
    └────────────┬─────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  2. Deduplicate              │
    │     - Semantic: normalize    │
    │       whitespace + lowercase │
    │     - Episodic: near-        │
    │       duplicate detection    │
    └────────────┬─────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  3. Aggregate                │
    │     - Compute rollups        │
    │     - Extract top_tags       │
    │     - Identify top_agents    │
    │     - Track most_accessed    │
    │     - Write aggregate.json   │
    └────────────┬─────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  4. Tier Management          │
    │     - Promote high-imp →     │
    │       long-term (future)     │
    │     - Archive stale entries  │
    └─────────────────────────────┘
```

### 5.2 Pruning Parameters

| Rule | Value | Scope |
|---|---|---|
| Episodic age limit | 90 days | Deletes entries older than N days |
| Per-type cap | 2,000 entries | Oldest evicted when limit exceeded |
| Minimum importance | 0.05 | Entries below threshold are archived |

### 5.3 Aggregate Output

```json
{
  "memory_type": "aggregate",
  "content": {
    "top_tags": ["deploy", "api", "bugfix", "review", "docs"],
    "top_agents": ["alice", "bob", "charlie", "diana"],
    "latest": "2026-07-30T14:30:22Z",
    "most_accessed": "mem_20260728_091234_001",
    "total_entries": 1842,
    "by_type": {"episodic": 1200, "semantic": 400, "procedural": 242}
  }
}
```

---

## 6. Search — Substring and Semantic Vector Retrieval

Agents are required to "warm" their context through a **Recall-Before-Execute**
search before initiating new tasks.

### 6.1 Keyword Search (Default)

- Case-insensitive substring matching across `content`, `tags`, `source`, `summary`
- Tag intersection filter (AND/OR)
- Term-frequency scoring across concatenated text fields
- No external dependencies

### 6.2 Vector Search (Semantic)

When `numpy` and `sentence-transformers` are available:

- **Model**: `all-MiniLM-L6-v2` (384-dimensional)
- **Algorithm**: L2-normalized dot product (cosine similarity) via `numpy`
- **Threshold**: configurable minimum score (default: `0.3`)
- **Index**: per-type HNSW or flat numpy arrays

```python
def vector_search(query: str, k: int = 10, min_score: float = 0.3) -> list[ScoredEntry]:
    query_vec = embedder.encode(query)
    query_vec = query_vec / np.linalg.norm(query_vec)
    scores = np.dot(index, query_vec)
    top_k = np.argsort(scores)[-k:][::-1]
    return [
        ScoredEntry(entry=entries[i], score=float(scores[i]))
        for i in top_k
        if scores[i] >= min_score
    ]
```

### 6.3 Graceful Fallback

```python
def search(query: str, **filters) -> list[MemoryEntry]:
    if _vector_search_available():
        try:
            return _vector_search(query, **filters)
        except Exception:
            logger.warning("Vector search failed, falling back to substring")
    return _substring_search(query, **filters)
```

Vector search is strategically optional — missing dependencies or an empty index
automatically degrades to substring search with approximate density scoring,
ensuring memory recall is non-blocking and resilient.

---

## 6. Security — AES-256-GCM Encryption

All cognitive assets encrypted at rest without introducing excessive recall latency.

### 6.1 Encryption Key Manager

```python
class EncryptionKeyManager:
    current_key: bytes  # 256-bit active key
    previous_key: bytes | None  # supports 2-key rotation window

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(12)  # 96-bit random nonce
        cipher = AES.new(self.current_key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        payload = base64.b64encode(nonce + ciphertext + tag).decode()
        return f"ENC:{payload}"

    def decrypt(self, encrypted: str) -> str:
        raw = base64.b64decode(encrypted.removeprefix("ENC:"))
        nonce, ciphertext, tag = raw[:12], raw[12:-16], raw[-16:]
        for key in (self.current_key, self.previous_key):
            if key is None:
                continue
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                return cipher.decrypt_and_verify(ciphertext, tag).decode()
            except (ValueError, KeyError):
                continue
        raise DecryptionError("Failed to decrypt with any available key")
```

### 6.2 Key Rotation

- Two-key rotation window: decrypt attempts the current key first, falls back to
  the previous key for backward compatibility.
- Rotation is decoupled from re-encryption; old entries are re-encrypted lazily
  on access or eagerly via `migrate_memory_encrypt.py`.

### 6.3 Migration

A standalone utility (`scripts/migrate_memory_encrypt.py`) provides idempotent
encryption for legacy plaintext entries from Sprints 1 and 2. It walks every
JSON store, detects unencrypted entries (no `ENC:` prefix), encrypts them, and
writes back atomically.

---

## 7. Governance — Memory Owner Agent

The Memory Engine is governed as a managed asset under the "Organization as Code"
framework, overseen by a specialized agent.

### 7.1 Memory Owner Mandates

The `memory_owner` agent in `company-registry.yaml` is bound by:

1. **Maintain Recall-Before-Execute** — integrate memory recall into the core
   executor loop so every task begins with a context-warming search.
2. **Define and enforce Forgetting Policies** — intentional noise reduction via
   pruning rules, caps, and decay schedules.
3. **Manage Latency Budgets** — ensure memory recall remains a non-blocking
   operational advantage (<50ms p99 for keyword, <200ms p99 for vector).

### 7.2 Service Layer Integration

Standardized via `BaseService` base class:

```python
class BaseService:
    memory: MemoryEngine

    def record_event(self, event_type: str, payload: dict) -> MemoryEntry:
        """Automated write to Episodic memory (campaigns, deals, etc.)."""
        return self.memory.save(
            content={"event_type": event_type, **payload},
            memory_type=MemoryType.EPISODIC,
            source=self.service_name,
        )

    def record_knowledge(self, statement: str, metadata: dict) -> MemoryEntry:
        """Automated write to Semantic memory (approvals, resolutions, etc.)."""
        return self.memory.save(
            content={"statement": statement, **metadata},
            memory_type=MemoryType.SEMANTIC,
            source=self.service_name,
        )
```

**Integration map** (all services use these hooks):

| Service | `record_event()` | `record_knowledge()` |
|---|---|---|
| Marketing | Campaign launches | N/A |
| Sales | Deal closures | Contract approvals |
| Customer Success | Ticket resolutions | KB article updates |
| Legal | N/A | Contract signings |
| HR | Onboarding events | Policy updates |

---

## 8. Current State & Roadmap

**Status** (July 2026): Operationally stable. 1,205 passing tests.

| Implemented | Gaps |
|---|---|
| 6-type taxonomy with per-type JSON stores | **Prompt injection gap**: recall results tracked but not injected into LLM prompt |
| Episodic via `record_task_outcome()` in Executor | `working/`, `short-term/`, `long-term/` directories are non-functional placeholders |
| Semantic via `record_knowledge()` in BaseService | Relational/Temporal: no automated writers; in-memory only |
| Atomic FileStore with `.bak` + cross-platform locking | `memory-index.yaml` is a vestigial artifact to be cleaned |
| AES-256-GCM encryption with key rotation | No Vector search integration yet (deps optional) |
| Consolidation scheduler (50-tick / 3600s) | No `forget()` or `consolidate()` exposed via CLI |
| Procedural extraction from repeated sequences | No working ↔ short ↔ long tier promotion/demotion |

### 8.1 Implementation Phases

**Phase 1 — Consolidate existing** *(immediate)*
1. Add `base_importance`, `recall_count`, `expires_at`, `agent_id`, `session_id`, `tier` to MemoryEntry
2. Wire CLI `memory` group → MemoryEngine (drop `.ai-company/state/current_sprint.yaml`)
3. Add `forget()` and `consolidate()` as first-class MemoryEngine methods
4. Remove vestigial `memory-index.yaml`
5. Hook recall results into executor context (close the prompt injection gap)

**Phase 2 — Tiered storage**
1. `InMemoryStore` for working memory (per-session, LRU, cap 100)
2. `JsonlStore` for short-term (session-scoped, recency-ordered)
3. Upgrade FileStore for long-term (indexed, cross-session)
4. Tier promotion (short→long on importance > 0.7) and demotion (long→archive on decay < threshold)

**Phase 3 — Semantic search**
1. Pluggable embedding provider (Ollama API default, sentence-transformers optional)
2. Numpy-based cosine similarity index (flat for <1K, HNSW for >1K)
3. Hybrid search: fuse vector scores with keyword scores via weighted sum
4. Graceful fallback when deps missing (always non-blocking)

**Phase 4 — Full lifecycle automation**
1. Deduplication pipeline (semantic: normalize+lowercase; episodic: embedding similarity)
2. Procedure extraction from 3+ repeated episodic sequences
3. Importance decay function running on every consolidation tick
4. Automatic archival of entries past 90d or below 0.05 importance

**Phase 5 — Observability & CLI**
1. `ai-company memory status` — tier sizes, hit rates, pending consolidation
2. `ai-company memory search <query>` — hybrid search
3. `ai-company memory show <id>` — full trace details
4. `ai-company memory stats` — usage, decay rates, tier distribution
5. `ai-company memory consolidate` — manual consolidation trigger

---

## Appendix A: Recall-Before-Execute Flow

```
                ┌──────────────────┐
                │  Task dispatched  │
                └────────┬─────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  1. RECALL phase        │
            │  search(query=task.desc)│
            │  ← top-5 MemoryEntries  │
            └────────┬───────────────┘
                     │
                     ▼
            ┌────────────────────────┐
            │  2. CONTEXT WARM        │
            │  Inject into agent      │
            │  prompt as context      │
            └────────┬───────────────┘
                     │
                     ▼
            ┌────────────────────────┐
            │  3. EXECUTE             │
            │  Agent processes task   │
            └────────┬───────────────┘
                     │
                     ▼
            ┌────────────────────────┐
            │  4. RECORD phase        │
            │  save(episodic, outcome)│
            └────────┬───────────────┘
                     │
                     ▼
            ┌────────────────────────┐
            │  5. CONSOLIDATE         │
            │  (async, periodic)      │
            └────────────────────────┘
```

## Appendix B: Encryption Format

```
ENC:<base64({nonce:12B}{ciphertext:var}{tag:16B})>

nonce     = 12 bytes (secrets.token_bytes)
cipher    = AES-256-GCM
key_size  = 256 bits
tag       = 16 bytes (GCM authentication tag)
rotation  = 2-key window (current + previous)
```

## Appendix C: Data Flow Diagram

```
 Agent ──(observe)──▶ Encoder ──▶ FileStore ──▶ Disk (.json + .bak)
   ▲                        │
   │                        ├─▶ Embedder ──▶ vector_index/*.npy
   │                        │
   │                        ▼
   │                  ConsolidationScheduler
   │                  ┌─ prune → dedup → aggregate
   │                  └─ encrypt → backup
   │
   └──(context)◀── Retriever ◀── Fuser ◀── SearchEngine
        ▲                               ├─ vector (cosine)
        │                               ├─ substring (tf)
        │                               └─ tag intersect
        │
   Orchestrator (injects into executor loop)
```
