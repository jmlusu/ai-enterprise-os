# AI Enterprise OS — System Architecture Diagram

```mermaid
flowchart TB
    subgraph CLI["CLI Layer (Typer)"]
        CLI_root["ai-company<br/>(bootstrap | build | generate<br/>validate | doctor | targets | status)"]
        CLI_reg["registry<br/>(list | show | verify)"]
        CLI_mem["memory<br/>(show | clear)"]
        CLI_graph["graph<br/>(show | stats)"]
        CLI_report["report<br/>(generate)"]
    end

    subgraph DATA["Company Data (YAML)"]
        C_MANIFEST["config/company/*.yaml<br/>Manifest + Vision + Strategy<br/>Culture + Governance<br/>Policies + Budget + KPIs"]
        C_REGISTRY["company/*.yaml<br/>Departments + Executives<br/>Board + Specialists<br/>Policies + Workflows"]
    end

    subgraph ENGINES["Engine Layer"]
        REG["Registry Engine<br/>Loader → Parser → Validator<br/>→ Resolver → CompanyRegistry"]
        TEMPLATE["Template Engine<br/>Jinja2 / Python / Markdown<br/>JSON / YAML handlers"]
        GENERATOR["Generator Engine<br/>Planner → Execution<br/>Retry + Rollback"]
        BOOTSTRAP["Bootstrap Generator<br/>Idempotent scaffolding"]
        MEMORY["Memory Engine<br/>Store + Search + Archive<br/>Snapshots + Summaries"]
        DECISION["Decision Engine<br/>Approval + Risk + Policy<br/>History + Routing"]
        ORCH["Orchestration Engine<br/>Router + Scheduler<br/>Executor + Workflow"]
        AUDIT["Audit Engine<br/>JSONL event store<br/>Metrics + Sessions"]
        GRAPH["Graph Engine<br/>Org chart + Workflow DAGs<br/>Dependency analysis"]
        VALIDATOR["Validator Engine<br/>YAML → Registry → Templates<br/>→ Manifest → Output"]
    end

    subgraph PROVIDERS["AI Provider Layer"]
        P_BASE["BaseProvider (ABC)"]
        P_OPENAI["OpenAI"]
        P_ANTH["Anthropic"]
        P_OLLAMA["Ollama"]
        P_GEMINI["Gemini"]
        P_MOCK["Mock"]
    end

    subgraph EXTERNAL["External Integrations"]
        EXT_OC["OpenCode AI<br/>(subprocess)"]
        EXT_OLLAMA["Ollama (localhost:11434)"]
        EXT_GH["GitHub Actions<br/>CI/CD Pipeline"]
    end

    subgraph OUTPUT["Generated Outputs"]
        OUT_README["generated/READMEs"]
        OUT_DOCS["generated/docs/*"]
        OUT_PROMPTS["generated/prompts/*"]
        OUT_TESTS["generated/test stubs"]
    end

    %% Data Flow
    C_MANIFEST --> CLI_root
    C_REGISTRY --> REG
    REG -->|CompanyRegistry| BOOTSTRAP
    REG -->|CompanyRegistry| GENERATOR
    REG -->|CompanyRegistry| TEMPLATE
    REG -->|CompanyRegistry| MEMORY
    REG -->|CompanyRegistry| DECISION
    REG -->|CompanyRegistry| GRAPH
    BOOTSTRAP --> TEMPLATE
    GENERATOR --> TEMPLATE
    TEMPLATE --> OUT_README
    TEMPLATE --> OUT_DOCS
    TEMPLATE --> OUT_PROMPTS
    TEMPLATE --> OUT_TESTS

    CLI_root --> REG
    CLI_root --> BOOTSTRAP
    CLI_root --> GENERATOR
    CLI_root --> VALIDATOR
    CLI_reg --> REG
    CLI_mem --> MEMORY
    CLI_graph --> GRAPH
    CLI_report --> GENERATOR

    ORCH --> REG
    ORCH --> GENERATOR
    ORCH --> MEMORY
    ORCH --> DECISION
    ORCH --> AUDIT
    ORCH --> GRAPH

    DECISION --> MEMORY
    AUDIT --> MEMORY

    GENERATOR -.->|AI prompts| EXT_OC
    EXT_OC -.-> EXT_OLLAMA
    PROVIDERS --> EXT_OLLAMA

    VALIDATOR --> REG
    VALIDATOR --> TEMPLATE
    VALIDATOR --> BOOTSTRAP

    %% Styling: completed vs in-progress vs planned
    classDef completed fill:#1a7a3a,stroke:#2ecc71,stroke-width:2px,color:#fff
    classDef inprogress fill:#7a6a1a,stroke:#f1c40f,stroke-width:2px,color:#fff
    classDef planned fill:#3a3a3a,stroke:#666,stroke-width:2px,color:#aaa

    class CLI_root,CLI_reg,CLI_mem,CLI_graph,CLI_report completed
    class REG,TEMPLATE,BOOTSTRAP,VALIDATOR completed
    class C_MANIFEST,C_REGISTRY completed
    class EXT_GH,EXT_OLLAMA completed
    class OUT_README,OUT_DOCS,OUT_PROMPTS,OUT_TESTS completed

    class MEMORY,DECISION,AUDIT,GRAPH,GENERATOR inprogress
    class P_BASE,P_OPENAI,P_ANTH,P_OLLAMA,P_GEMINI,P_MOCK inprogress

    class ORCH planned
    class EXT_OC planned
```

## Legend

| Color | Status |
|---|---|
| 🟢 **Green** (completed) | Production-ready, tested, wired to CLI |
| 🟡 **Yellow** (in progress) | Framework exists, deeper implementation needed |
| ⬛ **Gray** (planned) | Architecture designed, not yet built |
