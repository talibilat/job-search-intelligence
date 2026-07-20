import { useState } from "react";

type FunctionNode = Readonly<{
  name: string;
  file: string;
  definition: string;
  input: string;
  output: string;
  schema: string;
  kind: "client" | "api" | "agent" | "tool" | "data" | "provider";
}>;

type FlowStep = Readonly<{
  title: string;
  summary: string;
  functions: readonly FunctionNode[];
  input: string;
  output: string;
  note?: string;
}>;

type FeatureFlow = Readonly<{
  id: string;
  label: string;
  eyebrow: string;
  title: string;
  description: string;
  request: string;
  response: string;
  steps: readonly FlowStep[];
}>;

const fn = (
  name: string,
  file: string,
  definition: string,
  input: string,
  output: string,
  schema: string,
  kind: FunctionNode["kind"],
): FunctionNode => ({ definition, file, input, kind, name, output, schema });

const FUNCTIONS = {
  ask: fn("ChatDrawer.ask", "frontend/src/redesign/ChatDrawer.tsx", "Creates an idempotent optimistic turn and translates stream events into visible state.", "question: string, retryTurn?: PendingTurn", "Visible user/assistant messages and progress state", "PendingTurn { assistantId, question, turnId }", "client"),
  send: fn("sendChatTurn", "frontend/src/api/chat.ts", "Posts one turn and incrementally parses fragmented server-sent event frames.", "ChatTurnRequest, onEvent, AbortSignal", "Promise<ChatTurnResponse>", "ChatRequest + route | tool | answer_delta | complete events", "client"),
  parseFrame: fn("parseStreamFrame", "frontend/src/api/chat.ts", "Validates one complete SSE frame and rejects unknown event payloads.", "frame: string", "ChatClientStreamEvent | null", "Strict event discriminated union", "client"),
  post: fn("post_chat", "backend/app/api/chat.py", "Adapts ChatService's async event iterator to a no-cache text/event-stream response.", "ChatRequest, ChatService", "StreamingResponse", "event: <type>\\ndata: <ChatStreamEvent JSON>", "api"),
  sse: fn("_sse", "backend/app/api/chat.py", "Serializes a typed chat event into SSE wire format.", "ChatStreamEvent", "str", "Two-line named SSE frame", "api"),
  stream: fn("ChatService.stream", "backend/app/services/chat_service.py", "Serializes concurrent retries by turn ID before executing a chat turn.", "ChatRequest", "AsyncIterator<ChatStreamEvent>", "route, tool, delta, complete events", "agent"),
  streamLocked: fn("ChatService._stream_locked", "backend/app/services/chat_service.py", "Replays completed turns or executes graph, synthesis, citation filtering, and atomic persistence.", "ChatRequest", "AsyncIterator<ChatStreamEvent>", "Persisted, grounded ChatResponse", "agent"),
  graphStream: fn("ChatGraph.stream", "backend/app/agent/chat_graph.py", "Runs the compiled LangGraph and yields node updates.", "ChatGraphState", "AsyncIterator<state update>", "route, plan, tool_outputs, citations", "agent"),
  route: fn("ChatGraph._route", "backend/app/agent/chat_graph.py", "Combines typed LLM planning with deterministic route reinforcement and trusted tool requests.", "ChatRequest + history", "ChatPlan + ChatRoute", "conversation | quantitative | content | mixed | web", "agent"),
  planner: fn("ChatPlanner.plan", "backend/app/agent/planner.py", "Asks the configured LLM for a schema-constrained plan, retrying one invalid generation.", "question, up to 12 history rows, timezone", "ChatPlan", "No SQL field; route-specific tool constraints", "provider"),
  routeQuestion: fn("route_question", "backend/app/agent/chat_graph.py", "Classifies known metric, list, diagnostic, and content language without trusting model SQL or parameters.", "question: string", "quantitative | content | mixed", "Deterministic lexical rules", "agent"),
  structuredRequest: fn("_structured_request", "backend/app/agent/chat_graph.py", "Builds a whitelisted query request from trusted parsers and filters.", "question, planner request, timezone", "StructuredQueryRequest", "template + typed filters + date_window", "agent"),
  structuredRun: fn("StructuredQueryTool.run", "backend/app/agent/tools/structured_query.py", "Dispatches an allowed template to deterministic repository or diagnostic logic.", "StructuredQueryRequest", "StructuredQueryResult", "template, rows, totals, resolved date window", "tool"),
  resolveWindow: fn("StructuredQueryTool._resolve_date_window", "backend/app/agent/tools/structured_query.py", "Resolves relative dates in the user's validated IANA timezone.", "DateWindowSpec, timezone", "ResolvedDateWindow", "start_at?, end_at?, label", "tool"),
  deterministicSynthesis: fn("synthesize_grounded_answer", "backend/app/agent/chat_graph.py", "Formats quantitative outputs in Python so an LLM never invents dashboard truth.", "tool_outputs, citations", "answer: string", "Inline metric/application citation IDs", "agent"),
  reconcile: fn("ChatIndexService.reconcile", "backend/app/services/chat_index.py", "Indexes only changed, retained, job-related email bodies under a process-wide lock.", "embedding provider + eligible email rows", "updated sqlite-vec index", "1536-dimensional chunk embeddings", "tool"),
  chunks: fn("EmailChunkingService.build_chunks", "backend/app/services/email_chunking.py", "Normalizes paragraphs and creates overlapping bounded text chunks.", "EmailChunkSource", "list[EmailTextChunk]", "max 1200 characters, 200 overlap", "tool"),
  semanticPlan: fn("SemanticSearchTool.run_plan", "backend/app/agent/tools/semantic_search.py", "Selects vector, latest-company, or exhaustive lexical retrieval from a validated plan.", "RetrievalPlan, limit", "list[SemanticSearchResult]", "semantic | latest_company_email | exhaustive_mentions", "tool"),
  vectorSearch: fn("EmailChunkRepository.search", "backend/app/db/repositories/email_chunk.py", "Runs sqlite-vec nearest-neighbor retrieval and maps private IDs to public evidence IDs.", "embedding[1536], limit, max_distance", "list[SemanticSearchResult]", "email_public_id, chunk, content, application_ids", "data"),
  lexicalSearch: fn("EmailChunkRepository.find_all_mentioning", "backend/app/db/repositories/email_chunk.py", "Finds every indexed chunk containing a term with optional rejection filtering.", "term, category?", "list[SemanticSearchResult]", "Deterministic case-insensitive evidence set", "data"),
  synth: fn("ChatSynthesizer._stream_grounded", "backend/app/agent/synthesis.py", "Buffers provider JSON, validates grounded claims, rejects unknown citations, then emits safe text.", "question, evidence, allowed citation IDs", "AsyncIterator<answer text>", "SynthesisOutput { claims[] | refusal }", "provider"),
  conversation: fn("ChatSynthesizer.generate_conversation", "backend/app/agent/synthesis.py", "Produces ordinary non-factual conversation without tools or citations.", "question + safe history", "ConversationOutput", "answer + up to 3 follow_up_prompts", "provider"),
  web: fn("WebSearchTool.run", "backend/app/agent/tools/web_search.py", "Sends only an approved public query to the configured web provider.", "WebSearchRequest", "WebSearchResponse", "HTTPS results only", "tool"),
  citedIds: fn("cited_ids", "backend/app/agent/synthesis.py", "Extracts evidence IDs actually referenced by the final answer.", "answer: string", "set[str]", "email: | application: | metric: | web:", "agent"),
  addMessage: fn("ChatRepository.add_message", "backend/app/db/repositories/chat.py", "Serializes compact evidence arrays and inserts one chat history row.", "ChatMessageCreate", "ChatMessageRecord", "chat_messages row", "data"),
  completeTurn: fn("ChatRepository.get_completed_assistant_turn", "backend/app/db/repositories/chat.py", "Looks up an authoritative completed assistant row for retry replay.", "turn_id: string", "ChatMessageRecord | None", "Unique partial assistant turn index", "data"),
  history: fn("ChatHistoryService.list_messages", "backend/app/services/chat_history.py", "Returns a bounded recent window in chronological display order.", "conversation_id?, limit", "list[ChatMessageRecord]", "Compact citations, tool outputs, follow-ups", "data"),
  loadHistory: fn("loadChatHistory", "frontend/src/api/chat.ts", "Loads generated GET history data and defensively parses compact JSON arrays.", "conversationId?: string", "Promise<ChatHistoryMessage[]>", "Visible and hidden persisted roles", "client"),
} as const;

const FLOWS: readonly FeatureFlow[] = [
  {
    id: "main",
    label: "Main flow",
    eyebrow: "FR-5.1 · FR-5.4 · FR-5.5",
    title: "One grounded turn, browser to SQLite",
    description: "The authoritative path for every chat question. The browser creates a stable turn ID, the backend routes and grounds the answer, then commits the whole turn before completion is announced.",
    request: `POST /chat\n{\n  "turn_id": "turn_9f4...",\n  "message": "Who am I waiting on?",\n  "conversation_id": null,\n  "retrieval_limit": 5,\n  "timezone": "America/Toronto"\n}`,
    response: `event: complete\ndata: {\n  "route": "quantitative",\n  "answer_kind": "grounded",\n  "answer": "You are waiting on… [application:42]",\n  "citations": [{ "source": "application" }],\n  "follow_up_prompts": []\n}`,
    steps: [
      { title: "Submit", summary: "Create optimistic messages and one stable retry key.", functions: [FUNCTIONS.ask], input: "A trimmed natural-language question", output: "ChatRequest with crypto.randomUUID() turn_id" },
      { title: "Stream", summary: "Open the SSE request and validate each wire event.", functions: [FUNCTIONS.send, FUNCTIONS.parseFrame], input: "ChatRequest + browser timezone", output: "Typed progress and answer events" },
      { title: "Enter API", summary: "Convert service updates to named SSE frames.", functions: [FUNCTIONS.post, FUNCTIONS.sse], input: "Validated Pydantic ChatRequest", output: "text/event-stream" },
      { title: "Execute", summary: "Lock, replay or route, run tools, and synthesize.", functions: [FUNCTIONS.stream, FUNCTIONS.streamLocked, FUNCTIONS.graphStream], input: "Turn + persisted history", output: "Grounded answer and compact evidence" },
      { title: "Commit", summary: "Persist user, tool, and assistant rows atomically.", functions: [FUNCTIONS.addMessage, FUNCTIONS.citedIds], input: "Validated final answer", output: "Durable turn followed by complete event", note: "The complete event follows the database commit, so visible completion always has durable history." },
    ],
  },
  {
    id: "routing",
    label: "Routing",
    eyebrow: "FR-5.1 · security boundary",
    title: "Typed planning, deterministic guardrails",
    description: "The model proposes a typed plan. Deterministic rules then reinforce metric and mixed questions and construct trusted tool inputs. There is no raw SQL field anywhere in the plan.",
    request: `{\n  "question": "How many interviews did I get this year?",\n  "history": ["up to 12 safe context rows"],\n  "timezone": "Europe/London"\n}`,
    response: `{\n  "route": "quantitative",\n  "structured_query": {\n    "template": "summary_counts",\n    "date_window": { "kind": "calendar_year", "year": 2026 }\n  }\n}`,
    steps: [
      { title: "Plan", summary: "Request schema-constrained JSON at temperature zero.", functions: [FUNCTIONS.planner], input: "Question + redacted structured history", output: "Validated ChatPlan", note: "Simulated here: the real provider may be Azure OpenAI or Ollama." },
      { title: "Classify", summary: "Recognize quantitative, content, and mixed intent locally.", functions: [FUNCTIONS.routeQuestion], input: "Current user question", output: "Trusted route hint" },
      { title: "Constrain", summary: "Replace model query details with whitelisted templates and typed filters.", functions: [FUNCTIONS.structuredRequest], input: "Question + safe planner fields", output: "StructuredQueryRequest with no SQL" },
      { title: "Branch", summary: "Select exactly the graph nodes allowed by the validated plan.", functions: [FUNCTIONS.route, FUNCTIONS.graphStream], input: "ChatPlan", output: "Tool node updates" },
    ],
  },
  {
    id: "quantitative",
    label: "Quantitative",
    eyebrow: "FR-5.2 · dashboard parity",
    title: "Counts come from deterministic tools",
    description: "Quantitative answers use the same repositories and deterministic logic as the dashboard. The model routes the question but cannot calculate totals, emit SQL, or rewrite returned facts.",
    request: `{\n  "template": "rates",\n  "filters": { "work_mode": "remote" },\n  "date_window": { "kind": "relative", "days": 30 },\n  "timezone": "UTC"\n}`,
    response: `{\n  "template": "rates",\n  "rows": [{ "response_rate": 0.24, "interview_rate": 0.08 }],\n  "citation": "metric:rates"\n}`,
    steps: [
      { title: "Build request", summary: "Parse only supported dimensions, dates, salaries, roles, statuses, and sources.", functions: [FUNCTIONS.structuredRequest], input: "Natural language", output: "Whitelisted template request" },
      { title: "Resolve dates", summary: "Turn relative language into explicit UTC boundaries.", functions: [FUNCTIONS.resolveWindow], input: "DateWindowSpec + IANA timezone", output: "ResolvedDateWindow" },
      { title: "Query facts", summary: "Dispatch to deterministic metric and application readers.", functions: [FUNCTIONS.structuredRun], input: "StructuredQueryRequest", output: "Typed rows and totals" },
      { title: "Format", summary: "Render facts and citations in Python without an LLM.", functions: [FUNCTIONS.deterministicSynthesis], input: "StructuredQueryResult", output: "Grounded answer with metric/application IDs" },
    ],
  },
  {
    id: "retrieval",
    label: "Retrieval",
    eyebrow: "FR-5.3 · Q-47 · Q-48",
    title: "Email recall with exact source evidence",
    description: "Only retained, classified job email bodies enter the local vector index. The retrieval plan chooses semantic similarity, latest company mail, or exhaustive lexical matching.",
    request: `{\n  "mode": "exhaustive_mentions",\n  "term": "sponsorship",\n  "category": "rejection",\n  "company_results": true\n}`,
    response: `[{\n  "email_public_id": "mail_7d2...",\n  "application_ids": ["42"],\n  "chunk_index": 0,\n  "content": "…visa sponsorship…",\n  "distance": 0\n}]`,
    steps: [
      { title: "Reconcile index", summary: "Delete stale vectors and embed only changed eligible messages.", functions: [FUNCTIONS.reconcile, FUNCTIONS.chunks], input: "Retained job-related email bodies", output: "Atomic 1536-dimension sqlite-vec rows" },
      { title: "Choose retrieval", summary: "Validate semantic, latest-company, or exhaustive mode.", functions: [FUNCTIONS.semanticPlan], input: "RetrievalPlan", output: "Bounded evidence rows" },
      { title: "Search", summary: "Run nearest-neighbor or exhaustive deterministic evidence lookup.", functions: [FUNCTIONS.vectorSearch, FUNCTIONS.lexicalSearch], input: "Embedding or exact term", output: "Public email IDs plus associated application IDs" },
      { title: "Ground", summary: "Expose content internally for synthesis but persist only compact evidence metadata.", functions: [FUNCTIONS.synth, FUNCTIONS.citedIds], input: "Retrieved source text + allowed IDs", output: "Validated cited claims" },
    ],
  },
  {
    id: "synthesis",
    label: "Synthesis & SSE",
    eyebrow: "FR-5.4 · FR-5.5",
    title: "Validate first, reveal second",
    description: "Grounded provider tokens are not forwarded raw. JSON is buffered, validated against the evidence allowlist, and only then emitted as readable answer deltas. This prevents partial unsupported claims.",
    request: `{\n  "evidence": [{ "citation_id": "email:mail_7d2:0", "content": "…" }],\n  "response_schema": "SynthesisOutput",\n  "temperature": 0\n}`,
    response: `{\n  "claims": [{\n    "text": "The recruiter cannot sponsor this role.",\n    "citation_ids": ["email:mail_7d2:0"]\n  }]\n}`,
    steps: [
      { title: "Generate", summary: "Simulate streaming structured JSON from the selected provider.", functions: [FUNCTIONS.synth], input: "Question + evidence allowlist", output: "Buffered provider JSON", note: "The animation represents provider activity; this page never calls a real LLM." },
      { title: "Validate", summary: "Reject malformed output, unknown citation IDs, and invalid claim/refusal shapes.", functions: [FUNCTIONS.synth, FUNCTIONS.citedIds], input: "Complete provider generation", output: "Validated grounded claims or refusal" },
      { title: "Emit", summary: "Send route, tool, answer_delta, then complete events.", functions: [FUNCTIONS.sse, FUNCTIONS.send, FUNCTIONS.parseFrame], input: "Typed ChatStreamEvent", output: "Progressive browser transcript" },
      { title: "Conversation path", summary: "Ordinary non-factual chat skips tools and citations.", functions: [FUNCTIONS.conversation], input: "Question + safe conversation history", output: "Answer and up to three follow-ups" },
      { title: "External path", summary: "Approved current-information questions send only a public query.", functions: [FUNCTIONS.web], input: "Public WebSearchRequest", output: "HTTPS-only web evidence" },
    ],
  },
  {
    id: "history",
    label: "History & retry",
    eyebrow: "FR-5.6 · local-first",
    title: "Every completed turn is durable and replayable",
    description: "The turn ID makes network retries safe. A completed assistant row is replayed rather than re-running tools or providers, while a conflicting question for the same turn is rejected.",
    request: `GET /chat/history?conversation_id=conv_31&limit=100`,
    response: `{\n  "messages": [\n    { "role": "user", "turn_id": "turn_9f4..." },\n    { "role": "tool", "tool_outputs_json": "[…]" },\n    { "role": "assistant", "answer_kind": "grounded" }\n  ]\n}`,
    steps: [
      { title: "Check retry", summary: "Look for a completed authoritative assistant row before doing work.", functions: [FUNCTIONS.completeTurn, FUNCTIONS.streamLocked], input: "turn_id + question + conversation", output: "Replay or conflict" },
      { title: "Write transaction", summary: "Insert user, each tool output, and assistant result together.", functions: [FUNCTIONS.addMessage], input: "Final turn artifacts", output: "Atomic chat_messages rows" },
      { title: "Read history", summary: "Select the newest bounded window and return it chronologically.", functions: [FUNCTIONS.history], input: "conversation_id?, limit 1..500", output: "ChatHistoryResponse" },
      { title: "Project for UI", summary: "Parse compact arrays and hide tool/system rows from the visible transcript.", functions: [FUNCTIONS.loadHistory, FUNCTIONS.ask], input: "Persisted message records", output: "Saved conversation selector and visible messages" },
    ],
  },
] as const;

const GRAPH_COLUMNS = [
  { label: "Browser", nodes: [FUNCTIONS.ask, FUNCTIONS.send, FUNCTIONS.parseFrame, FUNCTIONS.loadHistory] },
  { label: "HTTP", nodes: [FUNCTIONS.post, FUNCTIONS.sse] },
  { label: "Orchestrator", nodes: [FUNCTIONS.stream, FUNCTIONS.streamLocked, FUNCTIONS.graphStream, FUNCTIONS.route] },
  { label: "Planning", nodes: [FUNCTIONS.planner, FUNCTIONS.routeQuestion, FUNCTIONS.structuredRequest] },
  { label: "Tools", nodes: [FUNCTIONS.structuredRun, FUNCTIONS.semanticPlan, FUNCTIONS.web, FUNCTIONS.reconcile] },
  { label: "Grounding", nodes: [FUNCTIONS.deterministicSynthesis, FUNCTIONS.synth, FUNCTIONS.citedIds] },
  { label: "SQLite", nodes: [FUNCTIONS.vectorSearch, FUNCTIONS.lexicalSearch, FUNCTIONS.completeTurn, FUNCTIONS.addMessage, FUNCTIONS.history] },
] as const;

function FunctionChip({ node }: { node: FunctionNode }) {
  return (
    <span className={`ca-function ca-function--${node.kind}`} tabIndex={0}>
      <code>{node.name}</code>
      <span className="ca-function__tooltip" role="tooltip">
        <strong>{node.name}</strong>
        <span>{node.definition}</span>
        <dl>
          <div><dt>Input</dt><dd>{node.input}</dd></div>
          <div><dt>Output</dt><dd>{node.output}</dd></div>
          <div><dt>Schema</dt><dd>{node.schema}</dd></div>
          <div><dt>Source</dt><dd>{node.file}</dd></div>
        </dl>
      </span>
    </span>
  );
}

function SchemaBlock({ label, value }: { label: string; value: string }) {
  return <div className="ca-schema"><div><span>{label}</span><button onClick={() => void navigator.clipboard?.writeText(value)} type="button">Copy</button></div><pre>{value}</pre></div>;
}

export function ChatArchitecturePage() {
  const [tabId, setTabId] = useState(FLOWS[0].id);
  const [stepIndex, setStepIndex] = useState(0);
  const flow = FLOWS.find((item) => item.id === tabId) ?? FLOWS[0];
  const step = flow.steps[Math.min(stepIndex, flow.steps.length - 1)];

  const chooseFlow = (id: string) => {
    setTabId(id);
    setStepIndex(0);
  };

  return (
    <article className="ca-page">
      <header className="ca-hero">
        <div className="ca-hero__copy">
          <p className="ca-kicker"><span /> Chat architecture atlas <b>Phase 5</b></p>
          <h1>One question.<br /><em>Every function.</em></h1>
          <p>A code-level, chat-only map of how JobTracker routes, grounds, streams, cites, and stores an answer. Hover or focus any function to inspect its contract.</p>
          <div className="ca-hero__stats" aria-label="Chat architecture summary">
            <span><strong>5</strong> routes</span><span><strong>4</strong> tool families</span><span><strong>0</strong> raw SQL</span><span><strong>1</strong> local database</span>
          </div>
        </div>
        <div className="ca-terminal" aria-label="Simulated chat trace">
          <div className="ca-terminal__bar"><i /><i /><i /><span>turn_9f4.trace</span></div>
          <ol>
            <li><span>00</span><b>question</b><code>Who am I waiting on?</code></li>
            <li><span>01</span><b>route</b><code>quantitative</code></li>
            <li><span>02</span><b>tool</b><code>live_applications</code></li>
            <li><span>03</span><b>ground</b><code>application:42</code></li>
            <li className="ca-terminal__active"><span>04</span><b>commit</b><code>complete ✓</code></li>
          </ol>
        </div>
      </header>

      <nav aria-label="Chat feature documentation" className="ca-tabs" role="tablist">
        {FLOWS.map((item, index) => <button aria-selected={item.id === flow.id} key={item.id} onClick={() => chooseFlow(item.id)} role="tab" type="button"><span>0{index + 1}</span>{item.label}</button>)}
      </nav>

      <section aria-live="polite" className="ca-feature" role="tabpanel">
        <div className="ca-feature__intro">
          <div><p className="ca-kicker">{flow.eyebrow}</p><h2>{flow.title}</h2></div>
          <p>{flow.description}</p>
        </div>
        <div className="ca-contracts"><SchemaBlock label="Exact input" value={flow.request} /><SchemaBlock label="Expected output" value={flow.response} /></div>

        <div className="ca-walkthrough">
          <div className="ca-walkthrough__rail">
            <p className="ca-section-label">Execution path</p>
            {flow.steps.map((item, index) => <button aria-current={index === stepIndex ? "step" : undefined} key={item.title} onClick={() => setStepIndex(index)} type="button"><span>{String(index + 1).padStart(2, "0")}</span><span><strong>{item.title}</strong><small>{item.summary}</small></span></button>)}
          </div>
          <div className="ca-step-card" key={`${flow.id}-${stepIndex}`}>
            <div className="ca-step-card__top"><span>Step {stepIndex + 1} of {flow.steps.length}</span><span>{stepIndex + 1 < flow.steps.length ? `Next: ${flow.steps[stepIndex + 1].title}` : "Next: turn complete"}</span></div>
            <h3>{step.title}</h3><p>{step.summary}</p>
            <div className="ca-io"><div><span>Input</span><strong>{step.input}</strong></div><div><span>Output</span><strong>{step.output}</strong></div></div>
            <div className="ca-function-list"><span>Functions in order</span><div>{step.functions.map((node) => <FunctionChip key={node.name} node={node} />)}</div></div>
            {step.note ? <p className="ca-note"><span>i</span>{step.note}</p> : null}
            <div className="ca-step-nav"><button disabled={stepIndex === 0} onClick={() => setStepIndex((value) => Math.max(0, value - 1))} type="button">← Previous</button><button disabled={stepIndex === flow.steps.length - 1} onClick={() => setStepIndex((value) => Math.min(flow.steps.length - 1, value + 1))} type="button">Next step →</button></div>
          </div>
        </div>
      </section>

      <section className="ca-graph-section">
        <div className="ca-section-heading"><div><p className="ca-kicker">Complete function graph</p><h2>Every chat layer, connected</h2></div><p>Read left to right for a new turn. History and idempotent retry loop from SQLite back to the browser and orchestrator.</p></div>
        <div className="ca-legend"><span className="client">Client</span><span className="api">API</span><span className="agent">Agent</span><span className="tool">Tool</span><span className="provider">Provider / LLM</span><span className="data">Data</span></div>
        <div className="ca-graph" aria-label="Chat function connection graph">
          {GRAPH_COLUMNS.map((column, index) => <section key={column.label}><header><span>{String(index + 1).padStart(2, "0")}</span>{column.label}</header><div>{column.nodes.map((node) => <FunctionChip key={node.name} node={node} />)}</div>{index < GRAPH_COLUMNS.length - 1 ? <i aria-hidden="true">→</i> : null}</section>)}
        </div>
      </section>

      <section className="ca-hierarchy">
        <div className="ca-section-heading"><div><p className="ca-kicker">Function hierarchy</p><h2>Main function to leaf operations</h2></div><p>The hierarchy follows runtime ownership, including the intermediate functions that are easy to miss in a route diagram.</p></div>
        <ol className="ca-tree">
          <li><FunctionChip node={FUNCTIONS.ask} /><p>Owns browser turn state, optimistic UI, retry identity, and progress.</p></li>
          <li><FunctionChip node={FUNCTIONS.send} /><p>Owns transport.</p><ol><li><FunctionChip node={FUNCTIONS.parseFrame} /></li><li><FunctionChip node={FUNCTIONS.post} /><ol><li><FunctionChip node={FUNCTIONS.sse} /></li></ol></li></ol></li>
          <li><FunctionChip node={FUNCTIONS.stream} /><p>Owns one authoritative turn.</p><ol><li><FunctionChip node={FUNCTIONS.completeTurn} /></li><li><FunctionChip node={FUNCTIONS.streamLocked} /><ol><li><FunctionChip node={FUNCTIONS.graphStream} /><ol><li><FunctionChip node={FUNCTIONS.route} /><ol><li><FunctionChip node={FUNCTIONS.planner} /></li><li><FunctionChip node={FUNCTIONS.routeQuestion} /></li><li><FunctionChip node={FUNCTIONS.structuredRequest} /></li></ol></li><li><FunctionChip node={FUNCTIONS.structuredRun} /></li><li><FunctionChip node={FUNCTIONS.semanticPlan} /><ol><li><FunctionChip node={FUNCTIONS.reconcile} /></li><li><FunctionChip node={FUNCTIONS.chunks} /></li><li><FunctionChip node={FUNCTIONS.vectorSearch} /></li><li><FunctionChip node={FUNCTIONS.lexicalSearch} /></li></ol></li><li><FunctionChip node={FUNCTIONS.web} /></li></ol></li><li><FunctionChip node={FUNCTIONS.deterministicSynthesis} /></li><li><FunctionChip node={FUNCTIONS.synth} /></li><li><FunctionChip node={FUNCTIONS.conversation} /></li><li><FunctionChip node={FUNCTIONS.citedIds} /></li><li><FunctionChip node={FUNCTIONS.addMessage} /></li></ol></li></ol></li>
          <li><FunctionChip node={FUNCTIONS.history} /><p>Reads durable turns for the generated history endpoint.</p><ol><li><FunctionChip node={FUNCTIONS.loadHistory} /></li></ol></li>
        </ol>
      </section>

      <footer className="ca-footer"><strong>Scope boundary</strong><p>This atlas covers only Phase 5 chat: FR-5.1 through FR-5.6 and Q-47 through Q-50. Dashboard, ingestion, classification, and insight generation are intentionally not documented here, except where chat calls their read-only contracts.</p><code>local-first · cited · deterministic where quantitative</code></footer>
    </article>
  );
}
