import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { IoTPipelinesPage } from './iotPipelinesPage.jsx';
import { SettingsPage } from './settingsPage.jsx';
import { appendWorkflowSteps, buildWorkflowFromPrompt } from './workflowAssistant.js';
import './styles.css';

const API = 'http://localhost:8787/api';
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
const load = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value));
const mergeById = (current = [], incoming = []) => {
  const seen = new Set();
  const merged = [];
  for (const item of [...current, ...incoming]) {
    if (!item?.id || seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push(item);
  }
  return merged;
};
const normalizeFlow = (flow) => Array.isArray(flow) ? flow.map(step => ({ id: step.id || uuid(), note: '', cron: '', loops: 1, dependsOnPrevious: true, ...step })) : [];
const normalizeLoopGroups = (groups, flowLength) => Array.isArray(groups) ? groups.map(g => ({ ...g, start: Number(g.start || 0), end: Number(g.end || 0), loops: Number(g.loops || 2) })).filter(g => g.start >= 0 && g.end > g.start && g.end < flowLength) : [];
const providerOptions = [
  { id: 'mock', name: 'Mock', defaultModel: 'mock-model' },
  { id: 'openai', name: 'OpenAI', defaultModel: 'gpt-4.1-mini' },
  { id: 'ollama', name: 'Ollama', defaultModel: 'llama3.1' },
  { id: 'gemini', name: 'Gemini', defaultModel: 'gemini-1.5-flash' },
  { id: 'anthropic', name: 'Claude', defaultModel: 'claude-3-5-sonnet-latest' }
];
const isWorkflowProviderReady = (provider) => provider?.enabled !== false && provider?.configured === true;
const firstReadyProvider = (providers = []) => providers.find(isWorkflowProviderReady) || null;
const providerOptionLabel = (provider) => `${provider.name || provider.id}${provider.enabled === false ? ' (disabled)' : provider.configured === false ? ' (not configured)' : ''}`;

function App() {
  const [page, setPage] = useState('flow');
  const [dark, setDark] = useState(() => load('darkMode', true));
  const [health, setHealth] = useState({ provider: 'loading' });
  const [skills, setSkills] = useState([]);
  const [mcps, setMcps] = useState([]);
  const [providers, setProviders] = useState(providerOptions);
  const [settings, setSettings] = useState({ id: 'runtime-settings', llmProviders: providerOptions, iotSources: [], iotActions: [], features: { iot: true } });
  const [agents, setAgents] = useState(() => load('agents', []));
  const [flow, setFlow] = useState(() => load('activeFlow', []));
  const [flowMeta, setFlowMeta] = useState(() => load('activeFlowMeta', {}));
  const [runSessions, setRunSessions] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const runControllers = useRef(new Map());

  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; save('darkMode', dark); }, [dark]);
  useEffect(() => {
    Promise.all([
      fetch(`${API}/health`).then(r => r.json()).catch(() => ({ provider: 'offline' })),
      fetch(`${API}/registry`).then(r => r.json()).catch(() => null),
      fetch(`${API}/settings`).then(r => r.json()).catch(() => null)
    ]).then(([h, registry, runtimeSettings]) => {
      setHealth(h);
      const nextSettings = runtimeSettings || registry?.settings || h.settings;
      if (nextSettings) setSettings(nextSettings);
      if (registry) {
        setSkills(registry.skills || []);
        setMcps(registry.mcps || []);
        setProviders(registry.providers?.length ? registry.providers : h.providers || providerOptions);
        setAgents(current => {
          const merged = mergeById(current, registry.agents || []);
          save('agents', merged);
          return merged;
        });
      }
    });
  }, []);

  const persistAgents = (next) => { setAgents(next); save('agents', next); };
  const persistFlow = (next) => { const safe = normalizeFlow(next); setFlow(safe); save('activeFlow', safe); };
  const persistMeta = (next) => { const safe = { ...(next || {}), steps: normalizeFlow(next?.steps || []), loopGroups: normalizeLoopGroups(next?.loopGroups || [], normalizeFlow(next?.steps || []).length) }; setFlowMeta(safe); save('activeFlowMeta', safe); };
  const iotEnabled = health?.features?.iot !== false && settings?.features?.iot !== false;
  useEffect(() => { if (!iotEnabled && page === 'iot') setPage('flow'); }, [iotEnabled, page]);
  const activeRun = runSessions.find(run => run.id === activeRunId) || runSessions[0] || null;
  const runningCount = runSessions.filter(run => run.status === 'running' || run.status === 'stopping').length;
  const startRunSession = ({ name, task, workspaceRoot, stepCount }) => {
    const id = uuid();
    const session = { id, name: name || 'Pipeline run', task, workspaceRoot, stepCount, startedAt: new Date().toISOString(), status: 'running', events: [], logs: [], error: '' };
    setRunSessions(prev => [session, ...prev]);
    setActiveRunId(id);
    setPage('run');
    return id;
  };
  const updateRunSession = (id, updater) => setRunSessions(prev => prev.map(run => run.id === id ? updater(run) : run));
  const appendRunEvent = (id, event) => updateRunSession(id, run => {
    const logs = event.type === 'run_done' && event.logs ? event.logs : event.type === 'step_done' && event.log ? [...run.logs, event.log] : run.logs;
    return { ...run, events: [...run.events, event], logs };
  });
  const finishRunSession = (id, status, error = '') => {
    runControllers.current.delete(id);
    updateRunSession(id, run => ({ ...run, status, error, finishedAt: new Date().toISOString() }));
  };
  const stopRun = (id) => {
    const controller = runControllers.current.get(id);
    if (!controller) return;
    updateRunSession(id, run => ({ ...run, status: 'stopping' }));
    controller.abort();
  };

  return <div className="app">
    <aside className="sidebar">
      <div className="brand"><div className="logo">⚙️</div><div><b>Agent Flow</b><span>full-stack lite</span></div></div>
      <div className="status">API: <b>{health.provider}</b></div>
      <button className={page === 'flow' ? 'active' : ''} onClick={() => setPage('flow')}>Workflow builder</button>
      {iotEnabled && <button className={page === 'iot' ? 'active' : ''} onClick={() => setPage('iot')}>IoT Pipelines</button>}
      <button className={page === 'run' ? 'active' : ''} onClick={() => setPage('run')}>Live run show{runningCount ? ` (${runningCount})` : ''}</button>
      <button className={page === 'saved' ? 'active' : ''} onClick={() => setPage('saved')}>Pipelines</button>
      <button className={page === 'builder' ? 'active' : ''} onClick={() => setPage('builder')}>Agent builder</button>
      <button className={page === 'settings' ? 'active' : ''} onClick={() => setPage('settings')}>Settings</button>
      <button className={page === 'skills' ? 'active' : ''} onClick={() => setPage('skills')}>Skills / MCP</button>
      <button className="ghost" onClick={() => setDark(!dark)}>{dark ? '☀️ Light mode' : '🌙 Dark mode'}</button>
    </aside>
    <main>
      {page === 'flow' && <FlowPage agents={agents} setAgents={persistAgents} skills={skills} mcps={mcps} providers={providers} settings={settings} iotEnabled={iotEnabled} flow={flow} setFlow={persistFlow} meta={flowMeta} setMeta={persistMeta} setPage={setPage} startRunSession={startRunSession} appendRunEvent={appendRunEvent} finishRunSession={finishRunSession} runControllers={runControllers} runningCount={runningCount} />}
      {iotEnabled && page === 'iot' && <IoTPipelinesPage agents={agents} providers={providers} settings={settings} setSettings={setSettings} setAgents={persistAgents} setFlow={persistFlow} setMeta={persistMeta} setPage={setPage} />}
      {page === 'run' && <RunShowPage runs={runSessions} activeRun={activeRun} setActiveRunId={setActiveRunId} stopRun={stopRun} />}
      {page === 'saved' && <SavedFlowsPage setPage={setPage} setFlow={persistFlow} setMeta={persistMeta} />}
      {page === 'builder' && <AgentBuilder agents={agents} setAgents={persistAgents} skills={skills} mcps={mcps} providers={providers} />}
      {page === 'settings' && <SettingsPage settings={settings} setSettings={setSettings} setProviders={setProviders} />}
      {page === 'skills' && <SkillsPage skills={skills} mcps={mcps} />}
    </main>
  </div>;
}

function Header({ title, subtitle }) { return <header className="header"><h1>{title}</h1><p>{subtitle}</p></header>; }

function FlowPage({ agents, setAgents, skills, mcps, providers, settings, iotEnabled, flow, setFlow, meta, setMeta, setPage, startRunSession, appendRunEvent, finishRunSession, runControllers, runningCount }) {
  const [dragAgentId, setDragAgentId] = useState(null);
  const [dragStepIndex, setDragStepIndex] = useState(null);
  const [viewMode, setViewMode] = useState('chain');
  const [selectedStepId, setSelectedStepId] = useState(null);
  const [assistantPrompt, setAssistantPrompt] = useState('');
  const [assistantPlan, setAssistantPlan] = useState(null);
  const [task, setTask] = useState(meta.task || 'Проаналізуй папку проєкту, знайди проблеми, запропонуй зміни, підготуй код/патч і README.');
  const [flowName, setFlowName] = useState(meta.name || 'Developer project pipeline');
  const [workspaceRoot, setWorkspaceRoot] = useState(meta.workspaceRoot || './workspace');
  const [loops, setLoops] = useState(meta.loops || 1);
  const [chainCron, setChainCron] = useState(meta.cron || '');
  const [loopGroups, setLoopGroups] = useState(() => normalizeLoopGroups(meta.loopGroups || [], flow.length));
  const [groupStart, setGroupStart] = useState(1);
  const [groupEnd, setGroupEnd] = useState(2);
  const [groupLoops, setGroupLoops] = useState(2);
  const [error, setError] = useState('');
  const readyProvider = firstReadyProvider(providers);

  useEffect(() => {
    setTask(meta.task || 'Проаналізуй папку проєкту, знайди проблеми, запропонуй зміни, підготуй код/патч і README.');
    setFlowName(meta.name || 'Developer project pipeline');
    setWorkspaceRoot(meta.workspaceRoot || './workspace');
    setLoops(meta.loops || 1);
    setChainCron(meta.cron || '');
    setLoopGroups(normalizeLoopGroups(meta.loopGroups || [], normalizeFlow(meta.steps || flow).length));
  }, [meta?.id]);

  const metaPayload = () => ({ id: meta.id, name: flowName, task, workspaceRoot, loops, cron: chainCron, steps: flow, loopGroups });
  const persistAll = () => setMeta(metaPayload());
  const addAgentToFlow = (agentId) => { if (agents.find(a => a.id === agentId)) setFlow([...flow, { id: uuid(), agentId, note: '', cron: '', loops: 1, dependsOnPrevious: true }]); };
  const moveStep = (from, to) => { if (from === null || to === null || from === to) return; const next = [...flow]; const [item] = next.splice(from, 1); next.splice(to, 0, item); setFlow(next); };
  const updateStep = (id, patch) => setFlow(flow.map(s => s.id === id ? { ...s, ...patch } : s));
  const removeStep = (id) => { const index = flow.findIndex(s => s.id === id); const nextFlow = flow.filter(s => s.id !== id); setLoopGroups(loopGroups.map(g => ({ ...g, start: g.start > index ? g.start - 1 : g.start, end: g.end > index ? g.end - 1 : g.end })).filter(g => g.start < g.end && g.end < nextFlow.length)); setFlow(nextFlow); };
  const addLoopGroup = () => { const start = Math.max(0, Number(groupStart || 1) - 1); const end = Math.max(0, Number(groupEnd || 1) - 1); if (!flow.length || start >= end || end >= flow.length) return; setLoopGroups([...loopGroups, { id: uuid(), name: `Loop group ${loopGroups.length + 1}`, start, end, loops: Math.max(2, Math.min(Number(groupLoops || 2), 20)) }]); };
  const updateLoopGroup = (id, patch) => setLoopGroups(loopGroups.map(g => g.id === id ? { ...g, ...patch } : g));
  const removeLoopGroup = (id) => setLoopGroups(loopGroups.filter(g => g.id !== id));
  const groupsForIndex = (index) => loopGroups.filter(g => index >= Number(g.start) && index <= Number(g.end));
  const groupStartsAt = (index) => loopGroups.filter(g => Number(g.start) === index);
  const groupEndsAt = (index) => loopGroups.filter(g => Number(g.end) === index);
  const selectedStep = flow.find(step => step.id === selectedStepId) || null;
  const selectedAgent = selectedStep ? agents.find(agent => agent.id === selectedStep.agentId) : null;
  const planWithAssistant = () => {
    const plan = buildWorkflowFromPrompt({ prompt: assistantPrompt || task, agents, existingFlow: flow, idFactory: uuid, iotEnabled, providers });
    setAssistantPlan(plan);
  };
  const applyAssistantPlan = (mode = 'replace') => {
    const plan = assistantPlan || buildWorkflowFromPrompt({ prompt: assistantPrompt || task, agents, existingFlow: flow, idFactory: uuid, iotEnabled, providers });
    setAgents(plan.agents);
    const nextFlow = mode === 'append' ? appendWorkflowSteps(flow, plan.steps, uuid) : plan.steps;
    setFlow(nextFlow);
    setLoopGroups(mode === 'append' ? [] : plan.loopGroups);
    setMeta({ ...metaPayload(), task: assistantPrompt || task, steps: nextFlow, loopGroups: mode === 'append' ? [] : plan.loopGroups });
    setSelectedStepId(nextFlow[0]?.id || null);
    setAssistantPlan(plan);
  };

  const saveFlowBackend = async () => {
    const payload = metaPayload(); setMeta(payload);
    const res = await fetch(`${API}/flows`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    return res.json();
  };

  const runChain = async () => {
    setError('');
    const runId = startRunSession({ name: flowName, task, workspaceRoot, stepCount: flow.length });
    const controller = new AbortController();
    runControllers.current.set(runId, controller);
    try {
      await saveFlowBackend();
      const res = await fetch(`${API}/flows/run/stream`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ flow, agents, skills, mcps, task, loops, workspaceRoot, loopGroups }), signal: controller.signal });
      if (!res.ok || !res.body) throw new Error('Stream run failed');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n'); buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          appendRunEvent(runId, event);
          if (event.type === 'error') throw new Error(event.error || 'Run error');
        }
      }
      finishRunSession(runId, 'done');
    } catch (e) {
      const stopped = e.name === 'AbortError';
      const event = { type: stopped ? 'stopped' : 'error', message: stopped ? 'Run stopped by user.' : e.message, at: new Date().toISOString() };
      appendRunEvent(runId, event);
      finishRunSession(runId, stopped ? 'stopped' : 'error', stopped ? '' : e.message);
      if (!stopped) setError(e.message);
    }
  };

  return <section>
    <Header title="Workflow builder" subtitle="Build agent workflows as a chain or n8n-style diagram, tune each step, and watch execution in Live run show." />
    {!readyProvider && <div className="error">No workflow LLM provider is configured. Open Settings → Agent LLM providers and add an API key or local base URL before running agents.</div>}
    <div className="toolbar">
      <input value={flowName} onChange={e => setFlowName(e.target.value)} onBlur={persistAll} placeholder="Sequence name" />
      <input value={workspaceRoot} onChange={e => setWorkspaceRoot(e.target.value)} onBlur={persistAll} placeholder="Project folder / WORKSPACE_ROOT" />
      <input value={chainCron} onChange={e => setChainCron(e.target.value)} onBlur={persistAll} placeholder="Chain cron, e.g. */30 * * * *" />
      <label>Chain loops <input type="number" min="1" max="10" value={loops} onChange={e => setLoops(e.target.value)} onBlur={persistAll} /></label>
      <button onClick={saveFlowBackend}>💾 Save</button>
      <button className="primary" disabled={!flow.length} onClick={runChain}>▶ Run live{runningCount ? ` · ${runningCount} active` : ''}</button>
    </div>

    <textarea className="task" value={task} onChange={e => setTask(e.target.value)} onBlur={persistAll} placeholder="Initial task for the whole pipeline" />

    <div className="panel assistant-panel">
      <div>
        <h3>AI workflow assistant</h3>
        <p>Describe what you want to build. The assistant will reuse preset agents where possible, create missing agents, and place them in a useful workflow order.</p>
      </div>
      <textarea value={assistantPrompt} onChange={e => setAssistantPrompt(e.target.value)} placeholder="Example: Build a backend export API with migrations, tests, docs and QA review." />
      <div className="row">
        <button onClick={planWithAssistant}>Plan workflow</button>
        <button className="primary" onClick={() => applyAssistantPlan('replace')}>Replace workflow</button>
        <button disabled={!flow.length} onClick={() => applyAssistantPlan('append')}>Append to current</button>
      </div>
      {assistantPlan && <div className="assistant-plan"><b>{assistantPlan.summary}</b>{assistantPlan.warning && <em>{assistantPlan.warning}</em>}<span>{assistantPlan.steps.map((step, index) => `${index + 1}. ${assistantPlan.agents.find(agent => agent.id === step.agentId)?.name || step.agentId}`).join(' → ')}</span></div>}
    </div>

    <div className="view-switch">
      <button className={viewMode === 'chain' ? 'active' : ''} onClick={() => setViewMode('chain')}>Chain editor</button>
      <button className={viewMode === 'diagram' ? 'active' : ''} onClick={() => setViewMode('diagram')}>Diagram view</button>
    </div>

    <div className="grid two">
      <div className="panel"><h3>Available agents</h3><div className="cards">{agents.map(agent => <div key={agent.id} className="agent-card" draggable onDragStart={(event) => { setDragAgentId(agent.id); event.dataTransfer.setData('text/plain', agent.id); }}><b>{agent.name}</b><span>{agent.role}</span><small>{agent.skills?.length || 0} skills · {agent.mcps?.length || 0} MCP</small></div>)}</div></div>
      <div className="panel drop-panel">
        <h3>{viewMode === 'diagram' ? 'Workflow diagram' : 'Highlighted sequence area'}</h3>
        <div className="inline-loop-builder"><label>From <input type="number" min="1" max={Math.max(flow.length, 1)} value={groupStart} onChange={e => setGroupStart(e.target.value)} /></label><label>To <input type="number" min="1" max={Math.max(flow.length, 1)} value={groupEnd} onChange={e => setGroupEnd(e.target.value)} /></label><label>Repeat <input type="number" min="2" max="20" value={groupLoops} onChange={e => setGroupLoops(e.target.value)} /></label><button disabled={flow.length < 2} onClick={addLoopGroup}>🔁 Group selected range</button></div>
        {viewMode === 'diagram' ? <WorkflowDiagram flow={flow} agents={agents} loopGroups={loopGroups} selectedStepId={selectedStepId} setSelectedStepId={setSelectedStepId} onDropAgent={(agentId) => addAgentToFlow(agentId)} onRemoveStep={removeStep} /> : <div className={`dropzone ${flow.length ? '' : 'empty'}`} onDragOver={e => e.preventDefault()} onDrop={() => { if (dragAgentId) addAgentToFlow(dragAgentId); setDragAgentId(null); }}>
          {!flow.length && <div className="empty-hint">Drop agents here. The order is saved and every next agent receives the previous result.</div>}
          {flow.map((step, index) => { const agent = agents.find(a => a.id === step.agentId); return <React.Fragment key={step.id}>
            {groupStartsAt(index).map(g => <div key={`${g.id}-start`} className="group-band start"><b>🔁 {g.name}</b><span>steps #{g.start + 1}–#{g.end + 1} · {g.loops} cycles</span><button onClick={() => removeLoopGroup(g.id)}>remove</button></div>)}
            <div className={`flow-step ${groupsForIndex(index).length ? 'inside-group' : ''} ${selectedStepId === step.id ? 'selected-step' : ''}`} draggable onClick={() => setSelectedStepId(step.id)} onDragStart={() => setDragStepIndex(index)} onDragOver={e => e.preventDefault()} onDrop={() => { moveStep(dragStepIndex, index); setDragStepIndex(null); }}>
              <div className="step-head"><span className="badge">#{index + 1}</span><b>{agent?.name || step.agentId}</b><button onClick={() => removeStep(step.id)}>✕</button></div>
              {!!groupsForIndex(index).length && <div className="loop-tags">{groupsForIndex(index).map(g => <span key={g.id}>🔁 {g.name}: {g.loops}x</span>)}</div>}
              <small>{agent?.role}</small><textarea value={step.note} onChange={e => updateStep(step.id, { note: e.target.value })} placeholder="Extra prompt/comment for this agent" />
              <div className="row"><label>Agent loops <input type="number" min="1" max="10" value={step.loops || 1} onChange={e => updateStep(step.id, { loops: e.target.value })} /></label><input value={step.cron || ''} onChange={e => updateStep(step.id, { cron: e.target.value })} placeholder="Optional agent cron" /><label><input type="checkbox" checked={step.dependsOnPrevious !== false} onChange={e => updateStep(step.id, { dependsOnPrevious: e.target.checked })} /> use previous output</label></div>
            </div>
            {groupEndsAt(index).map(g => <div key={`${g.id}-end`} className="group-band end">↩ repeat block {g.loops}x then continue</div>)}
          </React.Fragment>; })}
        </div>}
      </div>
    </div>
    <StepSettingsDrawer step={selectedStep} agent={selectedAgent} agents={agents} setAgents={setAgents} skills={skills} mcps={mcps} providers={providers} settings={settings} updateStep={updateStep} close={() => setSelectedStepId(null)} />
    {error && <div className="error">{error}</div>}
  </section>;
}

function WorkflowDiagram({ flow, agents, loopGroups, selectedStepId, setSelectedStepId, onDropAgent, onRemoveStep }) {
  const nodeWidth = 220;
  const nodeHeight = 112;
  const gapX = 92;
  const top = 70;
  const width = Math.max(760, flow.length * (nodeWidth + gapX) + 100);
  const height = 310;
  const nodeFor = (index) => ({ x: 50 + index * (nodeWidth + gapX), y: top });
  return <div className={`diagram-canvas ${flow.length ? '' : 'empty'}`} onDragOver={e => e.preventDefault()} onDrop={(event) => { const agentId = event.dataTransfer.getData('text/plain'); if (agentId) onDropAgent(agentId); }}>
    {!flow.length && <div className="empty-hint">Drop agents here to build a visual workflow.</div>}
    {!!flow.length && <div className="diagram-stage" style={{ width, minHeight: height }}>
      <svg className="diagram-links" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" /></marker></defs>
        {flow.slice(0, -1).map((step, index) => {
          const from = nodeFor(index);
          const to = nodeFor(index + 1);
          return <path key={step.id} d={`M${from.x + nodeWidth} ${from.y + 55} C${from.x + nodeWidth + 42} ${from.y + 55}, ${to.x - 42} ${to.y + 55}, ${to.x} ${to.y + 55}`} markerEnd="url(#arrow)" />;
        })}
        {loopGroups.map(group => {
          const start = nodeFor(group.start);
          const end = nodeFor(group.end);
          return <path key={group.id} className="loop-link" d={`M${end.x + nodeWidth - 12} ${end.y + nodeHeight + 22} C${end.x + 90} ${end.y + 210}, ${start.x + 120} ${start.y + 210}, ${start.x + 20} ${start.y + nodeHeight + 22}`} markerEnd="url(#arrow)" />;
        })}
      </svg>
      {flow.map((step, index) => {
        const agent = agents.find(item => item.id === step.agentId);
        const position = nodeFor(index);
        return <div key={step.id} role="button" tabIndex={0} className={`diagram-node ${selectedStepId === step.id ? 'selected-node' : ''}`} style={{ left: position.x, top: position.y, width: nodeWidth }} onClick={() => setSelectedStepId(step.id)} onKeyDown={event => { if (event.key === 'Enter') setSelectedStepId(step.id); }}>
          <button className="diagram-delete" aria-label={`Remove ${agent?.name || step.agentId}`} onClick={event => { event.stopPropagation(); onRemoveStep(step.id); }}>✕</button>
          <span className="node-index">#{index + 1}</span>
          <b>{agent?.name || step.agentId}</b>
          <small>{agent?.role || 'Agent step'}</small>
          <em>{step.loops || 1} loop{Number(step.loops || 1) === 1 ? '' : 's'}</em>
        </div>;
      })}
    </div>}
  </div>;
}

function StepSettingsDrawer({ step, agent, agents, setAgents, skills, mcps, providers, settings, updateStep, close }) {
  if (!step) return null;
  const agentSkills = (agent?.skills || []).map(id => skills.find(skill => skill.id === id)?.name || id);
  const agentMcps = (agent?.mcps || []).map(id => mcps.find(mcp => mcp.id === id)?.name || id);
  const iotSources = settings?.iotSources || [];
  const iotActions = settings?.iotActions || [];
  const selectedProvider = providers.find(item => item.id === agent?.provider) || null;
  const providerReady = selectedProvider ? isWorkflowProviderReady(selectedProvider) : !!firstReadyProvider(providers);
  const updateAgent = (patch) => {
    if (!agent) return;
    setAgents(agents.map(item => item.id === agent.id ? { ...item, ...patch } : item));
  };
  const toggleStepList = (key, id) => {
    const current = step[key] || [];
    updateStep(step.id, { [key]: current.includes(id) ? current.filter(item => item !== id) : [...current, id] });
  };
  const chooseProvider = (providerId) => {
    if (!providerId) {
      updateAgent({ provider: '', model: '' });
      return;
    }
    const provider = providers.find(item => item.id === providerId);
    updateAgent({ provider: providerId, model: provider?.defaultModel || agent?.model || '' });
  };
  return <aside className="step-drawer">
    <div className="drawer-head"><div><b>Step settings</b><span>{agent?.name || step.agentId}</span></div><button onClick={close}>Close</button></div>
    <label>Agent
      <select value={step.agentId} onChange={event => updateStep(step.id, { agentId: event.target.value })}>
        {agents.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    <div className="drawer-grid">
      <label>Provider
        <select value={agent?.provider || ''} onChange={event => chooseProvider(event.target.value)}>
          <option value="">Auto: first ready provider</option>
          {providers.map(provider => <option key={provider.id} value={provider.id} disabled={!isWorkflowProviderReady(provider)}>{providerOptionLabel(provider)}</option>)}
        </select>
      </label>
      <label>Model
        <input value={agent?.model || ''} onChange={event => updateAgent({ model: event.target.value })} placeholder="model name" />
      </label>
    </div>
    <div className={providerReady ? 'drawer-meta' : 'error'}>
      <b>Provider readiness</b>
      <span>{providerReady ? 'This step can run with a configured workflow provider.' : 'This agent has no configured workflow provider. Configure it in Settings before running.'}</span>
    </div>
    <label>Extra prompt
      <textarea value={step.note || ''} onChange={event => updateStep(step.id, { note: event.target.value })} />
    </label>
    <div className="drawer-grid">
      <label>Loops <input type="number" min="1" max="10" value={step.loops || 1} onChange={event => updateStep(step.id, { loops: event.target.value })} /></label>
      <label>Cron <input value={step.cron || ''} onChange={event => updateStep(step.id, { cron: event.target.value })} placeholder="optional" /></label>
    </div>
    {!!iotSources.length && <div className="drawer-meta">
      <b>IoT input sources</b>
      <div className="mini-checks">{iotSources.map(source => <label key={source.id}><input type="checkbox" checked={(step.iotSourceIds || []).includes(source.id)} onChange={() => toggleStepList('iotSourceIds', source.id)} /> {source.name}</label>)}</div>
    </div>}
    {!!iotActions.length && <div className="drawer-meta">
      <b>IoT device actions</b>
      <div className="mini-checks">{iotActions.map(action => <label key={action.id}><input type="checkbox" checked={(step.iotActionIds || []).includes(action.id)} onChange={() => toggleStepList('iotActionIds', action.id)} /> {action.name}</label>)}</div>
    </div>}
    <label className="check-row"><input type="checkbox" checked={step.dependsOnPrevious !== false} onChange={event => updateStep(step.id, { dependsOnPrevious: event.target.checked })} /> Use previous output</label>
    <div className="drawer-meta"><b>Agent skills</b><span>{agentSkills.join(', ') || 'No skills'}</span></div>
    <div className="drawer-meta"><b>MCP connectors</b><span>{agentMcps.join(', ') || 'No MCP connectors'}</span></div>
  </aside>;
}

function RunShowPage({ runs, activeRun, setActiveRunId, stopRun }) {
  const events = activeRun?.events || [];
  const logs = activeRun?.logs || [];
  const isRunning = activeRun?.status === 'running' || activeRun?.status === 'stopping';
  return <section>
    <Header title="Live run show" subtitle="Watch every running pipeline, switch between active runs, stop a run, and inspect its live events and artifacts." />
    <div className="run-layout">
      <div className="panel run-list-panel">
        <div className="run-list-head"><h3>Runs in work</h3><span>{runs.filter(run => run.status === 'running' || run.status === 'stopping').length} active</span></div>
        {!runs.length && <div className="muted">Run a pipeline to see it here.</div>}
        <div className="run-list">
          {runs.map(run => <button key={run.id} className={`run-list-item ${activeRun?.id === run.id ? 'active-run' : ''}`} onClick={() => setActiveRunId(run.id)}>
            <b>{run.name}</b>
            <span>{statusLabel(run.status)} · {run.stepCount || 0} steps · {(run.startedAt || '').slice(11, 19)}</span>
            <small>{run.task}</small>
          </button>)}
        </div>
      </div>
      <div>
        <div className="panel console-panel">
          <div className="console-head">
            <div><b>{activeRun ? statusLabel(activeRun.status) : 'No run selected'}</b><span>{activeRun?.name || 'Start a pipeline from the Pipeline page'}</span></div>
            <div className="console-actions"><span>{events.length} events · {logs.length} step results</span>{isRunning && <button className="danger-btn" onClick={() => stopRun(activeRun.id)}>{activeRun.status === 'stopping' ? 'Stopping...' : 'Stop run'}</button>}</div>
          </div>
          <div className="terminal">{!events.length && <div className="muted">Run a pipeline to see live progress here.</div>}{events.map((e, i) => <div key={i} className={`term-line ${e.type}` }><span className="term-time">{(e.at || '').slice(11, 19)}</span><span className="term-type">{e.type}</span><span>{e.message || e.error || e.agentName || e.tool || ''}</span>{e.path && <code>{e.path}</code>}{e.log && <span>{e.log.agentName}: done</span>}</div>)}</div>
        </div>
        <RunLogs logs={logs} />
      </div>
    </div>
  </section>;
}

function statusLabel(status) {
  if (status === 'running') return 'Running';
  if (status === 'stopping') return 'Stopping';
  if (status === 'stopped') return 'Stopped';
  if (status === 'error') return 'Error';
  if (status === 'done') return 'Done';
  return 'Idle';
}

function RunLogs({ logs }) { if (!logs.length) return null; return <div className="panel logs"><h3>Step outputs and artifacts</h3>{logs.map((log, i) => <details key={i} open={i === logs.length - 1}><summary>Chain {log.loop} · {log.loopGroupName ? `${log.loopGroupName} cycle ${log.groupLoop} · ` : ''}Step {log.step}.{log.stepLoop} · {log.agentName}{log.artifactPath ? ` · file: ${log.artifactPath}` : ''}</summary><pre>{log.output}</pre></details>)}</div>; }

function SavedFlowsPage({ setPage, setFlow, setMeta }) {
  const [flows, setFlows] = useState([]); const loadFlows = () => fetch(`${API}/flows`).then(r => r.json()).then(setFlows).catch(() => setFlows([])); useEffect(loadFlows, []);
  const remove = async (id) => { await fetch(`${API}/flows/${id}`, { method: 'DELETE' }); loadFlows(); };
  return <section><Header title="Pipelines" subtitle="Saved workflow configurations with task, workspace path, cron, ordered steps and visible loop groups." /><div className="panel">{!flows.length && <p>No pipelines yet.</p>}{flows.map(flow => <div className="saved" key={flow.id}><div><b>{flow.name}</b><span>{flow.steps?.length || 0} steps · chain loops {flow.loops || 1} · loop groups {flow.loopGroups?.length || 0} · cron {flow.cron || 'none'}</span><small>{flow.task}</small></div><button onClick={() => { const steps = normalizeFlow(flow.steps || []); const safe = { ...flow, steps, loopGroups: normalizeLoopGroups(flow.loopGroups || [], steps.length) }; save('activeFlowMeta', safe); save('activeFlow', steps); setMeta(safe); setFlow(steps); setPage('flow'); }}>Load</button><button onClick={() => remove(flow.id)}>Delete</button></div>)}</div></section>;
}

function AgentBuilder({ agents, setAgents, skills, mcps, providers }) {
  const defaultProvider = firstReadyProvider(providers);
  const empty = { id: '', name: '', role: '', provider: defaultProvider?.id || '', model: defaultProvider?.defaultModel || '', temperature: 0.2, skills: [], mcps: [], systemPrompt: '' };
  const [draft, setDraft] = useState(empty);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const draftProvider = providers.find(provider => provider.id === draft.provider);
  const draftProviderReady = draft.provider ? isWorkflowProviderReady(draftProvider) : !!defaultProvider;
  useEffect(() => {
    if (agents.length) return;
    let alive = true;
    setLoadingAgents(true);
    fetch(`${API}/agents`)
      .then(response => response.json())
      .then(items => {
        if (!alive || !Array.isArray(items)) return;
        setAgents(items);
      })
      .catch(() => null)
      .finally(() => { if (alive) setLoadingAgents(false); });
    return () => { alive = false; };
  }, [agents.length]);
  const markdown = useMemo(() => `# ${draft.name || 'Agent'}\n\n## Role\n${draft.role}\n\n## Provider\n${draft.provider || 'Auto: first ready workflow provider'}\n\n## Model\n${draft.model || 'Provider default'}\n\n## Temperature\n${draft.temperature}\n\n## Skills\n${(draft.skills || []).map(id => `- ${skills.find(s => s.id === id)?.name || id}`).join('\n')}\n\n## MCP\n${(draft.mcps || []).map(id => `- ${mcps.find(m => m.id === id)?.name || id}`).join('\n')}\n\n## System Prompt\n${draft.systemPrompt}\n`, [draft, skills, mcps]);
  const toggle = (key, id) => setDraft(d => ({ ...d, [key]: d[key].includes(id) ? d[key].filter(x => x !== id) : [...d[key], id] }));
  const changeProvider = (providerId) => {
    if (!providerId) {
      setDraft({ ...draft, provider: '', model: '' });
      return;
    }
    const provider = providers.find(item => item.id === providerId);
    setDraft({ ...draft, provider: providerId, model: provider?.defaultModel || draft.model });
  };
  const saveAgent = async () => { const agent = { ...draft, id: draft.id || slug(draft.name) || uuid() }; const next = agents.filter(a => a.id !== agent.id).concat(agent); setAgents(next); await fetch(`${API}/agents`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(agent) }).catch(() => null); setDraft(empty); };
  return <section>
    <Header title="Agent builder" subtitle="Create an agent, choose a configured workflow LLM provider, attach skills and MCP connectors, then export its configuration as Markdown." />
    {!defaultProvider && <div className="error">No workflow provider is ready. Configure one in Settings before creating production agents.</div>}
    <div className="grid two agent-builder-grid">
      <div className="panel form agent-builder-form">
        <input value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="Agent name" />
        <input value={draft.role} onChange={e => setDraft({ ...draft, role: e.target.value })} placeholder="Role / goal" />
        <div className="agent-provider-grid">
          <label>Provider
            <select value={draft.provider || ''} onChange={e => changeProvider(e.target.value)}>
              <option value="">Auto: first ready provider</option>
              {providers.map(provider => <option key={provider.id} value={provider.id} disabled={!isWorkflowProviderReady(provider)}>{providerOptionLabel(provider)}</option>)}
            </select>
          </label>
          <label>Model
            <input value={draft.model} onChange={e => setDraft({ ...draft, model: e.target.value })} placeholder="Use provider default or override" />
          </label>
          <label>Temp
            <input type="number" step="0.05" min="0" max="1" value={draft.temperature} onChange={e => setDraft({ ...draft, temperature: e.target.value })} />
          </label>
        </div>
        <div className={draftProviderReady ? 'drawer-meta' : 'error'}>
          <b>Workflow readiness</b>
          <span>{draftProviderReady ? 'This agent can run with a configured workflow provider.' : 'Select a ready provider or configure one in Settings.'}</span>
        </div>
        <textarea rows="8" value={draft.systemPrompt} onChange={e => setDraft({ ...draft, systemPrompt: e.target.value })} placeholder="System prompt / instruction" />
        <h3>Skills</h3>
        <div className="chips">{skills.map(s => <button key={s.id} className={draft.skills.includes(s.id) ? 'selected' : ''} onClick={() => toggle('skills', s.id)}>{s.name}</button>)}</div>
        <h3>MCP</h3>
        <div className="chips">{mcps.map(m => <button key={m.id} className={draft.mcps.includes(m.id) ? 'selected' : ''} onClick={() => toggle('mcps', m.id)}>{m.name}</button>)}</div>
        <button className="primary" onClick={saveAgent}>Save agent</button>
      </div>
      <div className="panel">
        <h3>Existing agents</h3>
        {loadingAgents && <div className="muted">Loading agents...</div>}
        {!loadingAgents && !agents.length && <div className="muted">No agents loaded yet. Check API connection or create the first agent.</div>}
        {agents.map(a => {
          const provider = providers.find(item => item.id === a.provider);
          const ready = a.provider ? isWorkflowProviderReady(provider) : !!defaultProvider;
          return <div className="saved" key={a.id}>
            <div><b>{a.name}</b><span>{a.provider || 'auto'} · {a.model || 'provider default'} · {ready ? 'ready' : 'not configured'}</span><small>{a.role}</small></div>
            <button onClick={() => setDraft({ ...empty, ...JSON.parse(JSON.stringify(a)) })}>Edit</button>
          </div>;
        })}
        <h3>Markdown export</h3>
        <pre>{markdown}</pre>
      </div>
    </div>
  </section>;
}

function SkillsPage({ skills, mcps }) { return <section><Header title="Skills / MCP catalog" subtitle="Base capabilities that can be attached to agents." /><div className="grid two"><div className="panel"><h3>Skills</h3>{skills.map(s => <div className="item" key={s.id}><b>{s.name}</b><span>{s.category}</span><p>{s.description}</p></div>)}</div><div className="panel"><h3>MCP connectors</h3>{mcps.map(m => <div className="item" key={m.id}><b>{m.name}</b><span>{m.endpoint}</span><p>{m.description}</p></div>)}</div></div></section>; }
function slug(text) { return String(text || '').toLowerCase().trim().replace(/[^a-z0-9а-яіїєґ]+/gi, '-').replace(/^-|-$/g, ''); }
createRoot(document.getElementById('root')).render(<App />);
