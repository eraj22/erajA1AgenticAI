# TicketPilot - Agent Arena

**Eraj Zaman | i221296 | Section A | Agentic AI, Assignment 1**

University email: i221296@nu.edu.pk  
GitHub: [eraj22/erajA1AgenticAI](https://github.com/eraj22/erajA1AgenticAI) (private).

TicketPilot reads one sample support ticket, chooses a policy-compliant priority and
team, and prepares an unsent reply draft. The model chooses actions and reply content;
Python owns validation, permitted capabilities, retries and stopping.

> **Readiness:** Railway hosts the live Groq agent and the public interface is reachable.
> Measured two-model results and full deployed stress results are being recorded.
> Instructor repository access and Classroom submission remain pending. The `demo`
> remains a deterministic offline aid, never live model evidence.

## Quick start

Use Python 3.12 or newer. From the extracted `i221296` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

On macOS/Linux, replace the interpreter paths with `python3` and
`.venv/bin/python`; use `cp .env.example .env`. Open
http://127.0.0.1:8000/ or http://127.0.0.1:8000/docs.
No API key is needed for the explicitly labelled offline demo. Try
`Triage T1001`, or `Triage ticket` followed by `T1001`.
A sample-queue button fills the input; press Run triage to execute.

## Agent Design Canvas

| Element | Design |
|---|---|
| Operational goal | Triage one existing sandbox support ticket and prepare a reply for human review. |
| Completion condition | Successful read_ticket, validated set_triage, and draft_reply with sent=false, followed by a valid completed decision. |
| System boundary | FastAPI, ten synthetic tickets, a per-run in-memory sandbox, and a configured external model API. No real help-desk, email, refund or account integration. |
| Observations | Current user request, bounded typed chat history, pending user goal, ticket data, trusted routing policy, validation feedback and tool results. |
| Actions/tools | read_ticket, read_policy, set_triage, draft_reply. |
| State | Active goal, authorized ticket IDs, loaded ticket, triage, draft, decision count, policy flag, fault flag, observations, traces, errors and usage. |
| Autonomy boundary | May read sample records and create sandbox triage/drafts. Cannot send messages, delete files, issue refunds, change accounts, run code or call arbitrary URLs. |
| Primary risks | Injection in customer text, invented IDs, invalid routing, false completion, provider/tool failures, runaway calls, session leakage and unbounded input. |
| Evaluation criteria | Correct ticket/team/priority and unsent draft; six Arena stress categories; isolation and multi-turn clarification; bounded latency/calls; measured model validity and cost. |

The approved domain is **Support-Ticket Triage**. No custom-domain approval is needed.
All sample people/accounts are synthetic; no customer PII is used.

## Architecture

```mermaid
flowchart TD
    U[Browser or Arena client] --> A[FastAPI + body/admission limits]
    A --> C[Goal and bounded typed context]
    C --> M[Model selects one typed decision]
    M --> V[Schema and semantic validation]
    V -->|invalid, bounded repair| C
    V -->|permitted action| T[Transactional sandbox tool]
    T --> O[Validated observation and trace]
    O --> C
    V -->|terminal decision| S[Runtime completion and stop checks]
    C -->|step/time/token/cost limit| S
```

The live agent can choose whether to inspect policy, how to classify permitted
priorities, what draft to write, whether to clarify, and whether to stop. Actions
depend on observations and validated decisions rather than a fixed function chain.
The offline demo is intentionally scripted and must not be presented as this live loop.
Explicit requests for real-world sending, refunds, deletion, account changes or
credential disclosure are rejected at admission before a model or tool call.
This is a bounded intent gate for the active user goal; the tool allowlist is the
backstop for other wording and for any unsafe model decision.

### Folder map

```text
i221296/
  app/
    main.py          FastAPI composition
    api.py           HTTP routes, session handoff, model allowlist
    config.py        environment configuration and bounded settings
    models.py        common Arena and domain contracts
    domain.py        trusted routing/priority policy and goal resolution
    prompts.py       dynamic system/context assembly
    providers.py     Gemini/Anthropic/Groq REST adapters + labelled demo
    agent.py         model-driven loop and shared decision budget
    tools.py         capability gateway and transactional sandbox
    arena.py         validated response boundary and safe summary logging
    memory.py        bounded typed messages and pending clarification goal
    limits.py        body, admission and rate bounds
    static/          browser interface
  data/sample_data.json
  evaluation/
    public_cases.json
    model_cases.json
    checks.py
    run_public_tests.py
    compare_models.py
    verify_deployment.py
    results/         actual recorded evidence, labelled by execution mode
  tests/
  scripts/package_submission.py
  SUBMISSION.md
  submission_details.json
  requirements.txt
  .env.example
  .gitignore
  render.yaml
  Dockerfile
  run.py
```

## Tools, schemas and validation

| Tool | Input | Output and constraints |
|---|---|---|
| read_ticket | ticket_id matching T plus four digits | Known sample Ticket; ID must come from exactly one active user goal. |
| read_policy | Empty object | Trusted routing and priority policy. Optional model-selected lookup. |
| set_triage | ticket_id, priority, team, rationale | A Triage record; ticket must already be loaded; team must follow trusted category/security facts; priority cannot fall below its floor. |
| draft_reply | ticket_id, text | Draft with sent=false; valid triage must exist first. No sending capability. |

Decision schema: status is continue, needs_clarification, completed, blocked or
failed; action is one of the four registered tools or null; arguments is an object;
user_message is optional bounded text. Pydantic rejects unknown fields. Tool input
and output validation is strict. Terminal decisions cannot contain an executable
action. A continuation requires an action and valid typed arguments.

Team mapping: billing -> billing; technical -> engineering; account ->
account_support; general -> general_support. A security-risk flag overrides the
category and requires security. Security risk or an all-users outage requires urgent.
Other outages or team-wide impact require at least high. Ordinary individual
issues allow low or normal (the model may choose a higher priority).

Structured sample metadata is trusted application data; ticket subject/body and
external notes are untrusted text. A model cannot lower the priority floor or
change the team policy using text instructions. Tool results are validated and
checked against their expected record before committing state. A failed attempt
cannot save a partial triage or duplicate a draft.

Completed output is rendered from validated state. Model claims of completion
without all three required successful tools are rejected. Draft factual quality
still needs human review: one live verification draft promised an update within
24 hours and implied it had been forwarded, neither of which the sandbox did.
The system prevents real sending, not every possible inaccurate sentence in a draft.

## Prompt and context design

The static SYSTEM layer contains the authority boundary, tool policy, schema and
trusted routing rules. The dynamic USER payload is a JSON object with distinct
active_user_goal, conversation_history, runtime_state,
external_untrusted_content and tool_and_validation_observations fields.

External text is never inserted into the system message. Structured encoding stops
text from breaking field boundaries; policy and validation prevent it from granting
capabilities. There is no blacklist of injection phrases and no hard-coded Arena
example response. General ticket-ID syntax is parsed from the user goal, never from
external notes or tool text. Multiple/unknown IDs require clarification.

Only brief operational evidence is logged; private chain-of-thought is not requested.
Server logs contain request ID, outcome, decision count and stop reason, not prompts,
keys or raw provider errors. UI observations contain only synthetic sample data.

## Conversation memory

Each chat uses a browser-generated UUID. Typed user/assistant messages are bounded to
12 messages (six turns) and 24,000 characters; oldest complete pairs are removed.
The session store holds at most 100 sessions. These limits are configurable.

A pending clarification goal is kept separately from history, so a bare identifier
such as T1001 resumes “Triage ticket”. An explicit new task replaces the pending goal.
A clarification selecting a new ID replaces previous ID selections. Broader follow-up
interpretation is limited: arbitrary non-ID answers are treated as a new user goal.
Users can always issue an explicit new request.

New chat clears server history and changes the session ID; reloading generates a
new session. Each run receives a fresh sandbox. Triage/drafts are not persistent;
prior results remain only in bounded chat text. Separate sessions cannot share
sandbox state. Arena request_id is correlation only and never a memory key.

History and rate/call counters are in-memory: use **one worker**. Restarts clear them.
Session IDs are unguessable identifiers, not a production authentication system;
only synthetic data is suitable for this public demonstration.

## Bounded execution and cost

Defaults: six total model decisions, two contract repairs, two tool retries (three
attempts), 40-second run timeout, 15-second provider timeout, two-second tool timeout,
1,024 maximum output tokens, 60,000 conservative run tokens, and 32,000 context bytes.
All repair and provider retry decisions share the six-step budget. Tool retries
reuse the same validated decision and do not consume another model decision.

The provider output-token cap is sent on every model request. The runtime reserves
one token per UTF-8 prompt byte plus protocol overhead and output allowance before
a call; known provider usage replaces that reservation afterwards. Unknown usage
retains the conservative reservation and public usage/cost stays null. Gemini
reported thinking tokens are included with output usage.

If per-model prices are configured, a USD 0.05 default per-run budget is enforced
conservatively before calls. Without prices, dollar estimation/enforcement is
unavailable; step/token/call limits still apply. Prices are not invented.

Public admission defaults: two simultaneous runs globally, 30 requests per minute
globally, one request per chat, 240,000-byte HTTP body limit, and 200 live model
calls per UTC day per process. Provider attempts, including failures, consume the
daily allowance. Provider account spending limits are also recommended because
process-local limits reset on restart and cannot enforce account-wide spend.

Run status includes completed, needs_clarification, blocked, tool_error,
contract_error, budget_exceeded and failed. approval_required is preserved by the
common HTTP schema, but this agent blocks consequential actions instead of offering
a real-action approval flow. Stop reasons identify the specific budget or error.

## Arena interface and fault injection

- GET /health - availability, configured model and demo/live mode.
- GET /arena/manifest - common version, actions, fault types and limits.
- POST /arena/run - independent evaluation run using the default model.
- POST /chat - session_id plus model and Arena request fields.
- DELETE /chat/{session_id} - reset one idle chat.
- GET /models - configured allowed model IDs; never credentials.
- GET /docs - interactive FastAPI API documentation.

```json
{
  "task": "Triage T1001",
  "external_context": [],
  "arena_config": {"max_steps": 6, "fault": "none"}
}
```

Preserved response fields: arena_version, request_id, status, final_response, steps,
stop_reason, tool_calls, errors, events and metrics. Responses are bounded to 50,000
bytes and final_response to 2,000 characters.

Faults: none; tool_timeout; malformed_tool_output; invalid_agent_decision. Shorthand
strings and expanded {"type":"tool_timeout"} are accepted. Each fault affects the
first matching operation once per run. Tool faults occur before commit; invalid
decision injection occurs after the model call and still charges its step/usage.
No fault is “consumed” before a matching operation.

## Tests and recorded evidence

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evaluation/run_public_tests.py --url http://127.0.0.1:8000
```

Unit tests use scripted decisions and mocked HTTP providers, with no paid API calls.
They cover all six stress categories, semantic policy violations, isolated sessions,
clarification, response contracts, bounded recovery, context/token/cost/time limits,
provider serialization and sanitized failures.

Public tests include successful triage, missing/unknown/conflicting IDs, injected
text, each fault hook, budget exhaustion, autonomy and a two-turn chat. The public
runner checks structured observations and state, not just a success label.

The current evidence records **54/54 unit tests** and **14/14 local HTTP checks**.
See evaluation/results/local_unit_results.txt and local_public_results.json for
actual offline evidence. These results **do not establish live LLM injection
resistance, language understanding, model quality or the hidden Arena score**.
The external deployment verifier also passed the public UI, health, manifest,
documentation, live Arena triage and two-turn clarification checks; its complete
response is saved in evaluation/results/deployment_verification.json.

## Live provider setup and required model experiment

Provider adapters use async REST via httpx. Supported providers are Gemini,
Anthropic, and Groq. Groq is the selected deployment provider. Current production
candidate IDs are `openai/gpt-oss-20b` and `openai/gpt-oss-120b`; model access
has been confirmed with Eraj's Groq account through the Railway deployment. The adapter uses JSON mode,
low reasoning effort and hides returned reasoning. Runtime schema and policy checks
validate every decision before a tool runs.

To run the **live** agent locally, copy `.env.example` to ignored `.env` and set:

```text
ENABLE_DEMO=false
MODEL_PROVIDER=groq
MODEL_NAME=openai/gpt-oss-20b
MODEL_NAMES=openai/gpt-oss-20b,openai/gpt-oss-120b
GROQ_API_KEY=<your key, stored only in .env or host secrets>
MODEL_PRICES_JSON={"openai/gpt-oss-20b":{"input":0.075,"output":0.30},"openai/gpt-oss-120b":{"input":0.15,"output":0.60}}
MAX_OUTPUT_TOKENS=2048
```

These prices are USD per million input/output tokens from Groq's model list as
checked on October 4, 2026; verify again before making cost claims. Never commit
or submit the real `.env`. Gemini and Anthropic remain optional alternatives.

MODEL_PRICES_JSON is a JSON object mapping exact model IDs to input/output USD per
million tokens. Example shape (replace symbolic values with current numeric prices):
{"model-a":{"input":INPUT_PRICE,"output":OUTPUT_PRICE}}.
Model availability and prices must be checked with the provider before running.

```powershell
.\.venv\Scripts\python.exe evaluation/compare_models.py --models openai/gpt-oss-20b openai/gpt-oss-120b
```

When the Groq key is stored only in Railway, run the same comparison through the
deployed agent. Each case uses a fresh chat session, and the saved response
contains the provider-reported usage and server-side cost estimate:

```powershell
.\.venv\Scripts\python.exe evaluation/compare_models.py --url https://ticketpilot-i221296-production.up.railway.app --models openai/gpt-oss-20b openai/gpt-oss-120b --pause-seconds 60
```

The runner refuses demo and identical model IDs. It runs the same ten representative
tasks through the complete loop, saves every outcome, and reports task success,
decision contract validity, action-selection success, mean latency, tokens and cost.
Intentional invalid-decision injection affects the reported contract-validity rate;
inspect per-case data to distinguish that forced error from natural model errors.
“Correct action selection” is a strict end-to-end expected-action/state pass metric,
not an independent human judgment of each intermediate action.

| Candidate | Task success | Contract validity | Action selection | Mean latency / case | Observed input + output tokens | Observed cost |
|---|---|---|---|---|---|---|
| Groq GPT-OSS 20B | 7/10 | 78.4% | 7/10 | 1,338 ms | 42,518 + 2,921 (7/9 runs) | At least $0.004065 |
| Groq GPT-OSS 120B | 3/10 | 83.9% | 3/10 | 1,958 ms | 31,588 + 2,569 (7/9 runs) | At least $0.006280 |

**Selection:** GPT-OSS 20B remains the default. It completed more strict tasks,
including the injected-text target test and both tool-recovery tests, and averaged
620 ms less latency per case. Both models had provider failures and some incorrect
decisions; neither achieved perfect reliability. The 120B model had slightly higher
decision-contract validity but more end-to-end failures, including a routing-policy
violation in the account-compromise case. The six-decision limit caught both models
when they could not finish safely. The measured costs above are **lower bounds**:
each model had nine runs with model calls, but provider failures left usage unknown
for two runs. Whole-experiment token/cost totals therefore remain null in the JSON.
These ten inputs are a small comparison, not a statistical performance guarantee.
The comparison was run before the explicit real-world-action admission guard was
added. That guard changes only such requests; the original measurements are kept
unchanged for provenance. The final guard has a separate deployed retest record.

## Deployment

Railway is the deployment host. The source is connected from the private GitHub
repository `eraj22/erajA1AgenticAI` on branch `main`. Public application:
https://ticketpilot-i221296-production.up.railway.app/ . Railway uses the root
Dockerfile. Its service start command is `python run.py`, with `/health` as the
healthcheck. The runtime uses one worker because chat memory and call counters are
in process.

Service variables: `ENABLE_DEMO=false`, `MODEL_PROVIDER=groq`,
`MODEL_NAME=openai/gpt-oss-20b`, `MODEL_NAMES=openai/gpt-oss-20b,openai/gpt-oss-120b`,
`MAX_OUTPUT_TOKENS=2048`, and `MODEL_PRICES_JSON` with the current Groq prices above.
`GROQ_API_KEY` is stored only as a Railway secret; it is never included in Git or
in the ZIP. Railway's Free/Trial plan can have limited outbound access for
unverified accounts and limited monthly credits, so actual public checks remain
necessary. `render.yaml` is an optional alternative for accounts that can complete
Render's billing verification; it is not the deployed service.

The local default host is 127.0.0.1; hosted startup binds 0.0.0.0 and uses PORT.
Use ENABLE_DEMO=false and a live default model for grading. A healthy process alone
does not prove the provider is working. Free hosts may sleep or restart; do not
promise availability that has not been measured.

After deployment, from outside the hosting environment:

```powershell
.\.venv\Scripts\python.exe evaluation/verify_deployment.py --url https://ticketpilot-i221296-production.up.railway.app --pause-seconds 60
.\.venv\Scripts\python.exe evaluation/run_public_tests.py --url https://ticketpilot-i221296-production.up.railway.app --pause-seconds 60 --output evaluation/results/deployed_public_results.json
```

Verify the browser UI in a private window. The required APIs and app must require
neither evaluator login nor an evaluator-supplied key. Opening the POST endpoint in
the address bar is not a valid POST test.

Provider API references:
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/structured-output
- https://platform.claude.com/docs/en/api/messages
- https://console.groq.com/docs/models
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/reasoning
- https://render.com/docs/deploy-fastapi

## Submission and remaining external requirements

The two Classroom attachments are **i221296.zip** and
**i221296_submission.pdf**. ZIP contents must have one top-level i221296 folder.
SUBMISSION.md and the PDF must match submission_details.json and contain the same
full source commit hash and actual URLs.

The summaries contain the confirmed identity, private repository, public Railway
URL, and measured evidence once checks finish. They remain drafts until the
instructor invitation, final source consistency check, and Classroom turn-in are
complete. Do not replace measured results with demo results.

The source commit can precede metadata generation, as permitted by the starter.
A later metadata-only commit may update SUBMISSION.md and submission_details.json.
The packager verifies that every other tracked file still matches the reported source
commit. Deploy the reported source commit when preparing the final evaluation.
Do not claim the draft metadata is deployment verification. Complete the live
experiment, documentation and deployment, commit final source, then regenerate
metadata and package that exact source version. Regenerate matching summaries with `pip install -r requirements-docs.txt` then
`python scripts/build_submission.py`. The packaging script requires
explicit --draft for incomplete metadata and checks the declared source hash.

```powershell
.\.venv\Scripts\python.exe scripts/package_submission.py --draft
```

Exclude secrets, real .env, virtual environments, .git, caches, node_modules and
unnecessary logs. Test the extracted archive using the documented instructions.
Upload both files to Classroom, click Turn in, confirm Turned in, and keep the
submitted source/deployment available during the evaluation window. The live
Classroom deadline takes precedence over the September 24, 2026 date printed in
the supplied assignment PDF.
