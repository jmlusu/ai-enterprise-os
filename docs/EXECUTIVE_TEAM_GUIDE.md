# AI Enterprise OS — Executive Team Interaction Guide

How to work with your AI executive team (CEO, COO, CTO, CFO, etc.) through Opencode. This is your day-to-day guide for assigning work, getting decisions, running meetings, and governing the company.

---

## 1. Your Executive Team

The registry defines 13 executives. Each has an agent configuration (model, temperature, tools) and a full prompt that defines their role, authority, and communication style.

| Executive | Title | Department | Key Responsibility |
|---|---|---|---|
| **Sarah Chen** | CEO | Executive | Vision, strategy, board liaison, final decisions |
| **Marcus Webb** | COO | Operations | Execution, runtime, pipelines, daily ops |
| **Priya Patel** | CTO | Engineering | Architecture, tech decisions, engineering org |
| **James Morrison** | CFO | Finance | Budgets, capital allocation, financial health |
| **Elena Rodriguez** | CMO | Marketing | Brand, growth, customer acquisition |
| **David Kim** | CPO | Product | Product strategy, roadmap, prioritization |
| **Lisa Thompson** | CHRO | HR | Talent, culture, org design, performance |
| **Robert Chen** | CISO | Security | Security posture, compliance, risk |
| **Amanda Foster** | CLO | Legal | Contracts, IP, regulatory, governance |
| **Michael Park** | CRO | Sales | Revenue, pipeline, customer success |
| **Jennifer Walsh** | CCO | Customer Success | Retention, expansion, NPS, advocacy |
| **Kevin Liu** | CDO | Data | Data strategy, analytics, ML/AI platform |
| **Rachel Green** | CIO | IT | Infrastructure, platforms, vendor management |

> Run `ai-company exec list` to see the current roster with KPIs and status.

---

## 2. How to Talk to an Executive

### 2.1 One-Shot Task (Opencode CLI)

```powershell
# Generate the executive's agent prompt, then run a task
ai-company exec agent "Sarah Chen" > /tmp/ceo_prompt.md
opencode run --file /tmp/ceo_prompt.md "Review Q3 strategy and approve budget reallocation"
```

### 2.2 Interactive Session (Recommended)

```powershell
opencode
# In the session:
> Read the CEO prompt first: @.ai-company/constitution @.ai-company/state
> Now act as Sarah Chen, CEO. Here's the situation: [your context]
```

The interactive session maintains context across turns — essential for
multi-step work.

### 2.3 Using the Generated Prompt Library

After `ai-company generate prompt`, each executive has a standalone prompt:

```powershell
opencode run --file generated/prompts/executive_sarah_chen.md \
  "We need to decide on the Series B timeline. Present options."
```

---

## 3. Common Interaction Patterns

### 3.1 Decision Request (CEO, CFO, CTO, CISO, CLO)

> **You:** "We're evaluating two vendors for the ML platform. Vendor A: $200k/yr, SOC2, 99.9% SLA. Vendor B: $120k/yr, no SOC2, 99.5% SLA. CTO recommends A. CFO prefers B. I need a decision with rationale."

**Executive responds with:** Decision ID, risk score, approval path, conditions.

### 3.2 Strategic Direction (CEO, COO, CPO)

> **You:** "Market shifted. Competitor launched AI feature X. We have 6 weeks before our planned launch. Should we: (a) accelerate and cut scope, (b) keep date and differentiate, (c) partner? Give me a recommendation by Friday."

**Executive responds with:** Analysis, trade-offs, recommended path, execution plan.

### 3.3 Budget Approval (CFO, CEO)

> **You:** "Engineering requests $500k for GPU cluster. Current budget: $2.1M allocated, $1.8M spent. ROI projection: 3x in 18 months. Approve / modify / deny with conditions."

**Executive responds with:** Approval decision, budget impact, conditions, tracking.

### 3.4 Operational Review (COO)

> **You:** "Run the weekly ops review. Check: runtime health, pipeline success rates, memory consolidation status, any degraded engines, scheduled jobs executed. Summarize in 5 bullets."

**Executive responds with:** Status snapshot, anomalies, actions needed.

### 3.5 Team/Org Changes (CHRO, CEO)

> **You:** "We need a new VP of AI Research. Draft: role spec, reporting line, budget authority, hiring timeline, interview loop. CHRO owns process, CTO owns technical eval."

**Executive responds with:** Role spec, process, timeline, decision rights.

### 3.6 Risk/Compliance (CISO, CLO)

> **You:** "New regulation requires data residency in EU by Q2. Current architecture: single-region US. Assess: engineering effort, cost, timeline, compliance risk of delay. CISO + CLO joint response."

**Executive responds with:** Joint assessment, risk register, mitigation plan.

---

## 4. Running Executive Meetings

The system has **scheduled meetings** (board, quarterly strategy, monthly board). You can also convene ad-hoc meetings.

### 4.1 Board Meeting (Monthly)

```powershell
# Triggered automatically by scheduler, or manually:
opencode run --file generated/prompts/executive_sarah_chen.md \
  "Convene board meeting. Agenda: Q3 results, Series B timeline, risk register, CEO priorities. Produce minutes and action items."
```

### 4.2 Executive Standup (Weekly)

```powershell
opencode run --file generated/prompts/executive_marcus_webb.md \
  "Run executive standup. Each exec: 1) top priority this week, 2) blocker, 3) decision needed. 10 min max. Output: shared decisions log."
```

### 4.3 Strategy Review (Quarterly)

```powershell
opencode run --file generated/prompts/executive_sarah_chen.md \
  "Quarterly strategy review. Inputs: market analysis, competitive intel, financial model, tech debt assessment. Output: updated strategy doc, 3 OKRs for next quarter, resource allocation changes."
```

---

## 5. Delegating to Departments

Executives own departments. Route work through the right executive.

| Work Type | Route Through |
|---|---|
| Architecture / tech debt / platform | CTO → Engineering |
| Product roadmap / prioritization | CPO → Product |
| Hiring / org design / performance | CHRO → HR |
| Budget / capital / forecasting | CFO → Finance |
| Security / compliance / audit | CISO → Security |
| Legal / contracts / IP | CLO → Legal |
| Sales pipeline / revenue | CRO → Sales |
| Customer health / retention | CCO → Customer Success |
| Data platform / analytics / ML | CDO → Data |
| Infrastructure / IT / vendors | CIO → IT |
| Marketing / brand / growth | CMO → Marketing |
| Operations / runtime / pipelines | COO → Operations |

### Example: Delegate to Engineering via CTO

> **You (to CTO):** "Engineering needs to refactor the authentication module. Current tech debt: 47 TODOs, 3 critical CVEs in deps. Timeline: 3 sprints. Owner: VP Engineering. I need: plan, risk mitigation, rollback strategy, and a decision on whether to pause feature work."

**CTO responds with:** Technical plan, risk assessment, resource needs, go/no-go.

---

## 6. Using the Runtime as COO

The COO (Marcus Webb) owns the **Enterprise Runtime Engine**. Use him for:

```powershell
opencode run --file generated/prompts/executive_marcus_webb.md \
  "Runtime status: start the runtime, run health check, execute memory consolidation job, show metrics. If any engine degraded, initiate recovery and report."
```

```powershell
opencode run --file generated/prompts/executive_marcus_webb.md \
  "Schedule a new recurring pipeline: 'Daily data quality check' every 6 hours. Use the orchestration engine. Define stages: load registry → validate → audit → alert on failure."
```

The COO operates the `orchestrate` and `runtime` CLI surfaces on your behalf.

---

## 7. Getting Artifacts from Executives

Each executive can generate their domain artifacts:

```powershell
# CTO → architecture decision records, tech specs
opencode run --file generated/prompts/executive_priya_patel.md \
  "Generate an ADR for: migrating from REST to gRPC for internal services. Include: context, decision, consequences, migration plan."

# CFO → budget model, forecast
opencode run --file generated/prompts/executive_james_morrison.md \
  "Build Q4 forecast model. Inputs: current burn, pipeline, hiring plan, infrastructure costs. Scenarios: base, aggressive, conservative. Output: spreadsheet + narrative."

# CHRO → org chart, role specs
opencode run --file generated/prompts/executive_lisa_thompson.md \
  "Update org chart for Engineering after adding VP AI Research. Show reporting lines, span of control, open roles. Export to generated/org_chart.md."
```

---

## 8. Session Protocol (Constitution)

**Start every executive session this way:**

```markdown
# In Opencode session:

1. Read constitution: @.ai-company/constitution
2. Read state: @.ai-company/state
3. Identify executive: "Act as [Name], [Title]"
4. Provide context: "Situation: ..."
5. Ask for: decision / plan / artifact / review
```

**End every session this way:**

```markdown
# Before closing:

1. Summarize decisions made
2. Update .ai-company/state/:
   - sprint status
   - technical debt changes
   - next actions (who, what, when)
   - project health (green/yellow/red)
3. Note any follow-ups for other executives
```

This ensures continuity across sessions and creates an audit trail.

---

## 9. Escalation Paths

| Situation | Escalate To |
|---|---|
| Cross-functional deadlock | CEO (final authority) |
| Budget overrun > 10% | CFO → CEO |
| Security incident | CISO → CEO + CLO |
| Legal liability | CLO → CEO |
| Technical architecture dispute | CTO → CEO |
| Strategic pivot | CEO + Board |
| Talent crisis | CHRO → CEO |

Executives will invoke escalation automatically when their decision
authority is exceeded — you don't need to manage this manually.

---

## 10. Quick Reference Cards

### CEO (Sarah Chen) — "Decide / Direct / Delegate"
- Final authority on strategy, budget, hiring executives, board matters
- Temperature: 0.3 (deliberate), Tools: all
- Use for: approvals, trade-offs, vision, crises

### COO (Marcus Webb) — "Execute / Monitor / Recover"
- Owns runtime, pipelines, operations, scheduled jobs
- Temperature: 0.2 (precise), Tools: runtime, orchestrate, health
- Use for: ops reviews, pipeline runs, incident response

### CTO (Priya Patel) — "Architect / Evaluate / Standardize"
- Owns technical decisions, architecture, engineering org
- Temperature: 0.4 (analytical), Tools: code, graph, validator
- Use for: ADRs, tech debt, platform choices, eng hiring

### CFO (James Morrison) — "Model / Allocate / Control"
- Owns budgets, forecasts, capital allocation, financial health
- Temperature: 0.1 (rigorous), Tools: memory, validator, reports
- Use for: approvals, forecasts, unit economics, scenarios

### CPO (David Kim) — "Prioritize / Define / Measure"
- Owns product roadmap, prioritization, metrics, launches
- Temperature: 0.5 (creative), Tools: workflows, graph, memory
- Use for: roadmap, PRDs, OKRs, launch reviews

### CHRO (Lisa Thompson) — "Design / Develop / Retain"
- Owns org design, hiring, performance, culture, compensation
- Temperature: 0.6 (empathetic), Tools: graph, org_chart, memory
- Use for: role specs, hiring plans, org changes, reviews

### CISO (Robert Chen) — "Assess / Harden / Certify"
- Owns security posture, compliance, incidents, risk
- Temperature: 0.2 (paranoid), Tools: validator, audit, memory
- Use for: risk assessments, incidents, audits, vendor reviews

### CLO (Amanda Foster) — "Protect / Structure / Resolve"
- Owns contracts, IP, regulatory, governance, disputes
- Temperature: 0.3 (precise), Tools: validator, memory, reports
- Use for: contracts, compliance, IP, board governance

---

## 11. Pro Tips

1. **One executive per session** — avoids context bleeding
2. **Paste the generated prompt** (`exec agent <name>`) into Opencode for fidelity
3. **Use memory** — executives remember via the memory engine; reference past decisions by ID
4. **Tag work** — "For CTO: ..." routes correctly even in multi-exec sessions
5. **Schedule recurring** — let the COO set up weekly/monthly automated reviews via `orchestrate`
6. **Audit trail** — every decision publishes `pipeline.*` and `decision.*` events; query with `ai-company report generate health`

---

## 12. Your First Week

| Day | Activity |
|---|---|
| Mon | `opencode` → read constitution → CEO standup: "What are my top 3 priorities this week?" |
| Tue | COO: "Run health check, show me the runtime, any degraded engines?" |
| Wed | CTO: "Review tech debt backlog. Which 3 items to tackle this sprint?" |
| Thu | CFO: "Q3 forecast vs actual. Where are we over/under?" |
| Fri | CPO: "Roadmap review. Any priority changes needed?" |
| Ongoing | Board meeting (monthly), Quarterly strategy (quarterly), Executive standup (weekly) |

---

## 13. When Things Go Wrong

| Problem | Fix |
|---|---|
| Executive gives generic answer | Re-run with more context: "Here are the numbers, constraints, stakeholders..." |
| Two executives conflict | Escalate to CEO explicitly: "CTO says X, CFO says Y. Decide." |
| Decision stalled | Add deadline: "Need decision by EOD tomorrow. If no consensus, CEO decides." |
| Lost context | Re-read `.ai-company/state/` at session start |
| Want different style | Adjust temperature in `exec agent <name>` output or edit `.opencode/agents/` |

---

You now have an executive team. Treat them like senior leaders: give context,
ask for decisions, hold them accountable, and update the state so the next
session picks up where you left off.
