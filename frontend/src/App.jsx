import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api.js';

const WELCOME = {
  role: 'assistant',
  text: 'Hi, I’m JeolAI. Tell me what you’re shopping for, your budget, or ask me to check inventory and promotions.',
};

const emptyTrace = {
  metrics: { models: [], input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0, total_latency_ms: 0, tool_calls: 0, model_calls: 0 },
  budget: { dollars_spent: 0, budget_cap: 0.1, percent_used: 0, tier: 'normal' },
  steps: [],
};

function makeSessionId() {
  return `shop-${Math.random().toString(36).slice(2, 9)}`;
}

function money(value) {
  return `$${Number(value || 0).toFixed(6)}`;
}

function Metric({ label, value, model = false }) {
  return (
    <div className={`metric${model ? ' model' : ''}`}>
      <div className="label">{label}</div>
      <div className="value" data-metric={label.toLowerCase().replaceAll(' ', '-')}>{value}</div>
    </div>
  );
}

function Message({ message }) {
  return (
    <div className={`message ${message.role}${message.blocked ? ' blocked' : ''}`}>
      {message.role === 'assistant' && <div className="avatar">J</div>}
      <div className="bubble">{message.text}</div>
      {message.role === 'user' && <div className="avatar">Y</div>}
    </div>
  );
}

function ExecutionTimeline({ steps }) {
  if (!steps.length) {
    return <div className="empty-state">Send a shopping request to see the execution stack.</div>;
  }

  return steps.map((step, index) => {
    const blocked = step.step_type === 'blocked' || /blocked|rejected/i.test(step.label || '');
    const meta = [
      step.model,
      step.input_tokens ? `${step.input_tokens} in` : '',
      step.output_tokens ? `${step.output_tokens} out` : '',
      step.cost_usd ? money(step.cost_usd) : '',
      step.latency_ms ? `${Number(step.latency_ms).toLocaleString()} ms` : '',
    ].filter(Boolean).join(' • ');

    return (
      <div className={`step${blocked ? ' blocked' : ''}`} key={`${step.label}-${index}`}>
        <div className="step-icon">{blocked ? '!' : '✓'}</div>
        <div className="step-name">{step.label}</div>
        {meta && <div className="step-meta">{meta}</div>}
        {step.details && (
          <details>
            <summary>View details</summary>
            <pre>{JSON.stringify(step.details, null, 2)}</pre>
          </details>
        )}
      </div>
    );
  });
}

function SummaryModal({ summary, onClose, onNewChat }) {
  if (!summary) return null;

  const stats = [
    ['Messages', summary.total_messages],
    ['Duration', `${summary.duration_seconds}s`],
    ['Total tokens', summary.total_tokens],
    ['Estimated cost', money(summary.estimated_cost_usd)],
    ['Model calls', summary.model_calls],
    ['Tool calls', summary.tool_calls],
    ['Latency', `${summary.total_latency_ms} ms`],
    ['Budget tier', summary.current_budget_tier],
  ];

  return (
    <div className="summary-overlay show" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="summary-modal" role="dialog" aria-modal="true" aria-labelledby="summary-title">
        <button className="summary-close" type="button" aria-label="Close session summary" onClick={onClose}>×</button>
        <h2 id="summary-title">Session summary</h2>
        <p>Your JeolAI shopping conversation summary.</p>
        <div className="summary-grid">
          {stats.map(([label, value]) => (
            <div className="summary-stat" key={label}>
              <span>{label}</span>
              <strong>{value ?? 0}</strong>
            </div>
          ))}
        </div>
        <div className="transcript">
          <h3>Chat history</h3>
          {(summary.transcript || []).map((item, index) => (
            <div className="transcript-row" key={`${item.role}-${index}`}>
              <strong>{item.role === 'user' ? 'You' : 'JeolAI'}:</strong> {item.message}
            </div>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn-soft" type="button" onClick={onClose}>Back to chat</button>
          <button className="btn-primary" type="button" onClick={onNewChat}>Start a new chat</button>
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(makeSessionId);
  const [messages, setMessages] = useState([WELCOME]);
  const [trace, setTrace] = useState(emptyTrace);
  const [input, setInput] = useState('');
  const [escalate, setEscalate] = useState(false);
  const [working, setWorking] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [summary, setSummary] = useState(null);
  const [approvalPending, setApprovalPending] = useState(false);
  const messagesRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const handler = (event) => event.key === 'Escape' && summary && setSummary(null);
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [summary]);

  const metrics = trace.metrics || emptyTrace.metrics;
  const budget = trace.budget || emptyTrace.budget;
  const percent = Math.min(100, Number(budget.percent_used || 0));
  const selectedModel = metrics.models?.length ? metrics.models.join(', ') : 'Not called';
  const progressColor = percent >= 95 ? '#c84a61' : percent >= 70 ? '#d08a32' : '#7b68c7';

  const promptSuggestions = useMemo(() => [
    'Find waterproof hiking boots under $170.',
    'Build me a complete hiking outfit under $450.',
    'Is Summit GTX available in size 10?',
  ], []);

  async function refreshTrace() {
    try {
      setTrace(await api.trace(sessionId));
    } catch {
      // A new session may not have trace records yet.
    }
  }

  async function submitMessage(event) {
    event.preventDefault();
    const message = input.trim();
    if (!message || working) return;

    setMessages((current) => [...current, { role: 'user', text: message }]);
    setInput('');
    setWorking(true);
    setStatus('Agent is working…');

    try {
      const response = await api.chat({
        session_id: sessionId,
        message,
        wants_escalation: escalate,
      });
      setMessages((current) => [...current, {
        role: 'assistant',
        text: response.reply || 'Something went wrong.',
        blocked: response.domain_allowed === false,
      }]);
      setApprovalPending(Boolean(response.requires_approval));
      await refreshTrace();
    } catch (error) {
      setMessages((current) => [...current, {
        role: 'assistant',
        text: `I couldn't reach the backend: ${error.message}`,
        blocked: true,
      }]);
    } finally {
      setWorking(false);
      setStatus('Ready');
      inputRef.current?.focus();
    }
  }

  async function resolveApproval(approved) {
    setWorking(true);
    setStatus(approved ? 'Approving checkout…' : 'Denying checkout…');
    try {
      const response = await api.approve(sessionId, approved);
      setMessages((current) => [...current, {
        role: 'assistant',
        text: response.reply || response.error || 'Approval decision recorded.',
        blocked: !approved,
      }]);
      setApprovalPending(Boolean(response.requires_approval));
      await refreshTrace();
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', text: error.message, blocked: true }]);
    } finally {
      setWorking(false);
      setStatus('Ready');
    }
  }

  async function setSpend(dollars) {
    setStatus('Updating budget tier…');
    try {
      await api.setSpend(sessionId, dollars);
      await refreshTrace();
    } finally {
      setStatus('Ready');
    }
  }

  async function endChat() {
    setStatus('Preparing summary…');
    try {
      setSummary(await api.endChat(sessionId));
      await refreshTrace();
      setStatus('Summary ready');
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function newChat() {
    try {
      await api.deleteSession(sessionId);
    } catch {
      // Starting a fresh local session should still work if cleanup fails.
    }
    setSessionId(makeSessionId());
    setMessages([WELCOME]);
    setTrace(emptyTrace);
    setSummary(null);
    setStatus('Ready');
    setInput('');
    setEscalate(false);
    setApprovalPending(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  return (
    <div className="shell">
      <header>
        <div className="brand">
          <div className="brand-mark">JeolAI • FastAPI • React • Vertex AI + Gemini</div>
          <h1>Shop Smart. Spend Smarter.</h1>
          <p>A budget-aware shopping assistant with its agent execution visible in real time.</p>
        </div>
        <div className="header-actions">
          <button className="btn-soft" type="button" onClick={newChat}>New chat</button>
          <button className="btn-danger" type="button" onClick={endChat} disabled={working}>End chat</button>
        </div>
      </header>

      <main className="app-grid">
        <section className="card chat-card" data-testid="chat-card">
          <div className="chat-head">
            <h2>Shopping conversation</h2>
            <span className="session">{sessionId}</span>
          </div>
          <div className="messages" ref={messagesRef}>
            {messages.map((message, index) => <Message message={message} key={`${message.role}-${index}`} />)}
            {working && (
              <div className="message assistant">
                <div className="avatar">J</div>
                <div className="bubble typing">Thinking and checking tools…</div>
              </div>
            )}
          </div>
          <div className="composer" data-testid="composer">
            <div className="suggestions">
              {promptSuggestions.map((prompt) => (
                <button type="button" className="suggestion" key={prompt} onClick={() => setInput(prompt)}>{prompt}</button>
              ))}
            </div>
            <form onSubmit={submitMessage}>
              <div className="input-row">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  type="text"
                  placeholder="Try: Build me a hiking outfit under $450"
                  autoComplete="off"
                  disabled={working}
                />
                <button className="btn-primary" type="submit" disabled={working || !input.trim()}>Send</button>
              </div>
              <div className="composer-meta">
                <label><input checked={escalate} onChange={(event) => setEscalate(event.target.checked)} type="checkbox" /> Use higher-capability model when policy allows</label>
                <span>{status}</span>
              </div>
            </form>
          </div>
        </section>

        <aside className="card execution-card" data-testid="execution-card">
          <div className="execution-head">
            <h2>Agent execution</h2>
            <span className="live-dot">Live</span>
          </div>
          <div className="budget-card">
            <div className="budget-top">
              <div>
                <div className="eyebrow">Session budget</div>
                <div className="budget-value">{money(budget.dollars_spent)} / ${Number(budget.budget_cap || 0.1).toFixed(3)}</div>
              </div>
              <div className="tier">{String(budget.tier || 'normal').replaceAll('_', ' ')}</div>
            </div>
            <div className="progress"><div className="progress-fill" style={{ width: `${percent}%`, background: progressColor }} /></div>
            <div className="progress-caption">
              <span>{percent.toFixed(1)}% consumed</span>
              <span>{money(Math.max(0, (budget.budget_cap || 0.1) - (budget.dollars_spent || 0)))} remaining</span>
            </div>
          </div>
          <div className="metrics">
            <Metric label="Model selected" value={selectedModel} model />
            <Metric label="Input tokens" value={Number(metrics.input_tokens || 0).toLocaleString()} />
            <Metric label="Output tokens" value={Number(metrics.output_tokens || 0).toLocaleString()} />
            <Metric label="Estimated cost" value={money(metrics.estimated_cost_usd)} />
            <Metric label="Total latency" value={`${Number(metrics.total_latency_ms || 0).toLocaleString()} ms`} />
            <Metric label="Tool calls" value={metrics.tool_calls || 0} />
            <Metric label="Model calls" value={metrics.model_calls || 0} />
          </div>
          <div className="timeline-wrap">
            <div className="timeline-title">Execution steps</div>
            <div className="timeline"><ExecutionTimeline steps={trace.steps || []} /></div>
          </div>
          {approvalPending && (
            <div className="approval-panel" role="group" aria-label="Checkout approval">
              <strong>Human approval required</strong>
              <span>Review the pending checkout before allowing the agent to continue.</span>
              <div>
                <button className="btn-primary" type="button" onClick={() => resolveApproval(true)} disabled={working}>Approve checkout</button>
                <button className="btn-danger" type="button" onClick={() => resolveApproval(false)} disabled={working}>Deny checkout</button>
              </div>
            </div>
          )}
          <div className="presenter">
            <button type="button" onClick={() => setSpend(0.075)}>Set 75% · Downgraded</button>
            <button type="button" onClick={() => setSpend(0.096)}>Set 96% · Approval gated</button>
            <button type="button" onClick={() => setSpend(0)}>Reset spend</button>
          </div>
        </aside>
      </main>

      <SummaryModal summary={summary} onClose={() => { setSummary(null); setStatus('Ready'); inputRef.current?.focus(); }} onNewChat={newChat} />
    </div>
  );
}
