import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API = 'http://localhost:8787/api';
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
const load = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value));
const normalizeFlow = (flow) => Array.isArray(flow) ? flow.map(step => ({ id: step.id || uuid(), note: '', cron: '', loops: 1, dependsOnPrevious: true, ...step })) : [];
const normalizeLoopGroups = (groups, flowLength) => Array.isArray(groups) ? groups.map(g => ({ ...g, start: Number(g.start || 0), end: Number(g.end || 0), loops: Number(g.loops || 2) })).filter(g => g.start >= 0 && g.end > g.start && g.end < flowLength) : [];

function App() {
  const [page, setPage] = useState('flow');
  const [dark, setDark] = useState(() => load('darkMode', true));
  const [health, setHealth] = useState({ provider: 'loading' });
  const [skills, setSkills] = useState([]);
  const [mcps, setMcps] = useState([]);
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
      fetch(`${API}/registry`).then(r => r.json()).catch(() => null)
    ]).then(([h, registry]) => {
      setHealth(h);
      if (registry) {
        setSkills(registry.skills || []);
        setMcps(registry.mcps || []);
        if (!agents.length) { setAgents(registry.agents || []); save('agents', registry.agents || []); }
      }
    });
  }, []);

  const persistAgents = (next) => { setAgents(next); save('agents', next); };
  const persistFlow = (next) => { const safe = normalizeFlow(next); setFlow(safe); save('activeFlow', safe); };
  const persistMeta = (next) => { const safe = { ...(next || {}), steps: normalizeFlow(next?.steps || []), loopGroups: normalizeLoopGroups(next?.loopGroups || [], normalizeFlow(next?.steps || []).length) }; setFlowMeta(safe); save('activeFlowMeta', safe); };
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
      <button className={page === 'flow' ? 'active' : ''} onClick={() => setPage('flow')}>Pipeline</button>
      <button className={page === 'run' ? 'active' : ''} onClick={() => setPage('run')}>Live run show{runningCount ? ` (${runningCount})` : ''}</button>
      <button className={page === 'saved' ? 'active' : ''} onClick={() => setPage('saved')}>Saved sequences</button>
      <button className={page === 'builder' ? 'active' : ''} onClick={() => setPage('builder')}>Agent builder</button>
      <button className={page === 'workspace' ? 'active' : ''} onClick={() => setPage('workspace')}>Workspace / Git</button>
      <button className={page === 'skills' ? 'active' : ''} onClick={() => setPage('skills')}>Skills / MCP</button>
      <button className="ghost" onClick={() => setDark(!dark)}>{dark ? '☀️ Light mode' : '🌙 Dark mode'}</button>
    </aside>
    <main>
      {page === 'flow' && <FlowPage agents={agents} skills={skills} mcps={mcps} flow={flow} setFlow={persistFlow} meta={flowMeta} setMeta={persistMeta} setPage={setPage} startRunSession={startRunSession} appendRunEvent={appendRunEvent} finishRunSession={finishRunSession} runControllers={runControllers} runningCount={runningCount} />}
      {page === 'run' && <RunShowPage runs={runSessions} activeRun={activeRun} setActiveRunId={setActiveRunId} stopRun={stopRun} />}
      {page === 'saved' && <SavedFlowsPage setPage={setPage} setFlow={persistFlow} setMeta={persistMeta} />}
      {page === 'builder' && <AgentBuilder agents={agents} setAgents={persistAgents} skills={skills} mcps={mcps} />}
      {page === 'workspace' && <WorkspacePage />}
      {page === 'skills' && <SkillsPage skills={skills} mcps={mcps} />}
    </main>
  </div>;
}

function Header({ title, subtitle }) { return <header className="header"><h1>{title}</h1><p>{subtitle}</p></header>; }

function FlowPage({ agents, skills, mcps, flow, setFlow, meta, setMeta, setPage, startRunSession, appendRunEvent, finishRunSession, runControllers, runningCount }) {
  const [dragAgentId, setDragAgentId] = useState(null);
  const [dragStepIndex, setDragStepIndex] = useState(null);
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
    <Header title="Pipeline: agents sequence" subtitle="Drag agents into the highlighted work area, add prompts, create visible loop groups directly inside the chain, and watch execution in Live run show." />
    <div className="toolbar">
      <input value={flowName} onChange={e => setFlowName(e.target.value)} onBlur={persistAll} placeholder="Sequence name" />
      <input value={workspaceRoot} onChange={e => setWorkspaceRoot(e.target.value)} onBlur={persistAll} placeholder="Project folder / WORKSPACE_ROOT" />
      <input value={chainCron} onChange={e => setChainCron(e.target.value)} onBlur={persistAll} placeholder="Chain cron, e.g. */30 * * * *" />
      <label>Chain loops <input type="number" min="1" max="10" value={loops} onChange={e => setLoops(e.target.value)} onBlur={persistAll} /></label>
      <button onClick={saveFlowBackend}>💾 Save</button>
      <button className="primary" disabled={!flow.length} onClick={runChain}>▶ Run live{runningCount ? ` · ${runningCount} active` : ''}</button>
    </div>

    <textarea className="task" value={task} onChange={e => setTask(e.target.value)} onBlur={persistAll} placeholder="Initial task for the whole pipeline" />

    <div className="grid two">
      <div className="panel"><h3>Available agents</h3><div className="cards">{agents.map(agent => <div key={agent.id} className="agent-card" draggable onDragStart={() => setDragAgentId(agent.id)}><b>{agent.name}</b><span>{agent.role}</span><small>{agent.skills?.length || 0} skills · {agent.mcps?.length || 0} MCP</small></div>)}</div></div>
      <div className="panel drop-panel">
        <h3>Highlighted sequence area</h3>
        <div className="inline-loop-builder"><label>From <input type="number" min="1" max={Math.max(flow.length, 1)} value={groupStart} onChange={e => setGroupStart(e.target.value)} /></label><label>To <input type="number" min="1" max={Math.max(flow.length, 1)} value={groupEnd} onChange={e => setGroupEnd(e.target.value)} /></label><label>Repeat <input type="number" min="2" max="20" value={groupLoops} onChange={e => setGroupLoops(e.target.value)} /></label><button disabled={flow.length < 2} onClick={addLoopGroup}>🔁 Group selected range</button></div>
        <div className={`dropzone ${flow.length ? '' : 'empty'}`} onDragOver={e => e.preventDefault()} onDrop={() => { if (dragAgentId) addAgentToFlow(dragAgentId); setDragAgentId(null); }}>
          {!flow.length && <div className="empty-hint">Drop agents here. The order is saved and every next agent receives the previous result.</div>}
          {flow.map((step, index) => { const agent = agents.find(a => a.id === step.agentId); return <React.Fragment key={step.id}>
            {groupStartsAt(index).map(g => <div key={`${g.id}-start`} className="group-band start"><b>🔁 {g.name}</b><span>steps #{g.start + 1}–#{g.end + 1} · {g.loops} cycles</span><button onClick={() => removeLoopGroup(g.id)}>remove</button></div>)}
            <div className={`flow-step ${groupsForIndex(index).length ? 'inside-group' : ''}`} draggable onDragStart={() => setDragStepIndex(index)} onDragOver={e => e.preventDefault()} onDrop={() => { moveStep(dragStepIndex, index); setDragStepIndex(null); }}>
              <div className="step-head"><span className="badge">#{index + 1}</span><b>{agent?.name || step.agentId}</b><button onClick={() => removeStep(step.id)}>✕</button></div>
              {!!groupsForIndex(index).length && <div className="loop-tags">{groupsForIndex(index).map(g => <span key={g.id}>🔁 {g.name}: {g.loops}x</span>)}</div>}
              <small>{agent?.role}</small><textarea value={step.note} onChange={e => updateStep(step.id, { note: e.target.value })} placeholder="Extra prompt/comment for this agent" />
              <div className="row"><label>Agent loops <input type="number" min="1" max="10" value={step.loops || 1} onChange={e => updateStep(step.id, { loops: e.target.value })} /></label><input value={step.cron || ''} onChange={e => updateStep(step.id, { cron: e.target.value })} placeholder="Optional agent cron" /><label><input type="checkbox" checked={step.dependsOnPrevious !== false} onChange={e => updateStep(step.id, { dependsOnPrevious: e.target.checked })} /> use previous output</label></div>
            </div>
            {groupEndsAt(index).map(g => <div key={`${g.id}-end`} className="group-band end">↩ repeat block {g.loops}x then continue</div>)}
          </React.Fragment>; })}
        </div>
      </div>
    </div>
    {error && <div className="error">{error}</div>}
  </section>;
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
  return <section><Header title="Saved sequences" subtitle="Saved chain configurations with task, workspace path, cron, ordered steps and visible loop groups." /><div className="panel">{!flows.length && <p>No saved sequences yet.</p>}{flows.map(flow => <div className="saved" key={flow.id}><div><b>{flow.name}</b><span>{flow.steps?.length || 0} steps · chain loops {flow.loops || 1} · loop groups {flow.loopGroups?.length || 0} · cron {flow.cron || 'none'}</span><small>{flow.task}</small></div><button onClick={() => { const steps = normalizeFlow(flow.steps || []); const safe = { ...flow, steps, loopGroups: normalizeLoopGroups(flow.loopGroups || [], steps.length) }; save('activeFlowMeta', safe); save('activeFlow', steps); setMeta(safe); setFlow(steps); setPage('flow'); }}>Load</button><button onClick={() => remove(flow.id)}>Delete</button></div>)}</div></section>;
}

function AgentBuilder({ agents, setAgents, skills, mcps }) {
  const empty = { id: '', name: '', role: '', model: 'gpt-4.1-mini', temperature: 0.2, skills: [], mcps: [], systemPrompt: '' };
  const [draft, setDraft] = useState(empty);
  const markdown = useMemo(() => `# ${draft.name || 'Agent'}\n\n## Role\n${draft.role}\n\n## Model\n${draft.model}\n\n## Temperature\n${draft.temperature}\n\n## Skills\n${(draft.skills || []).map(id => `- ${skills.find(s => s.id === id)?.name || id}`).join('\n')}\n\n## MCP\n${(draft.mcps || []).map(id => `- ${mcps.find(m => m.id === id)?.name || id}`).join('\n')}\n\n## System Prompt\n${draft.systemPrompt}\n`, [draft, skills, mcps]);
  const toggle = (key, id) => setDraft(d => ({ ...d, [key]: d[key].includes(id) ? d[key].filter(x => x !== id) : [...d[key], id] }));
  const saveAgent = async () => { const agent = { ...draft, id: draft.id || slug(draft.name) || uuid() }; const next = agents.filter(a => a.id !== agent.id).concat(agent); setAgents(next); await fetch(`${API}/agents`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(agent) }).catch(() => null); setDraft(empty); };
  return <section><Header title="Agent builder" subtitle="Create an agent, attach skills and MCP connectors, then export its configuration as Markdown." /><div className="grid two"><div className="panel form"><input value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="Agent name" /><input value={draft.role} onChange={e => setDraft({ ...draft, role: e.target.value })} placeholder="Role / goal" /><div className="row"><input value={draft.model} onChange={e => setDraft({ ...draft, model: e.target.value })} /><label>Temp <input type="number" step="0.05" min="0" max="1" value={draft.temperature} onChange={e => setDraft({ ...draft, temperature: e.target.value })} /></label></div><textarea rows="8" value={draft.systemPrompt} onChange={e => setDraft({ ...draft, systemPrompt: e.target.value })} placeholder="System prompt / instruction" /><h3>Skills</h3><div className="chips">{skills.map(s => <button key={s.id} className={draft.skills.includes(s.id) ? 'selected' : ''} onClick={() => toggle('skills', s.id)}>{s.name}</button>)}</div><h3>MCP</h3><div className="chips">{mcps.map(m => <button key={m.id} className={draft.mcps.includes(m.id) ? 'selected' : ''} onClick={() => toggle('mcps', m.id)}>{m.name}</button>)}</div><button className="primary" onClick={saveAgent}>Save agent</button></div><div className="panel"><h3>Existing agents</h3>{agents.map(a => <div className="saved" key={a.id}><div><b>{a.name}</b><span>{a.role}</span></div><button onClick={() => setDraft(JSON.parse(JSON.stringify(a)))}>Edit</button></div>)}<h3>Markdown export</h3><pre>{markdown}</pre></div></div></section>;
}

function WorkspacePage() {
  const [workspaceRoot, setWorkspaceRoot] = useState('./workspace'); const [path, setPath] = useState('.'); const [tree, setTree] = useState(''); const [filePath, setFilePath] = useState('README.md'); const [fileContent, setFileContent] = useState(''); const [git, setGit] = useState(null);
  const scan = async () => setTree((await post('/workspace/scan', { workspaceRoot, path, depth: 4 })).tree || ''); const read = async () => setFileContent((await post('/workspace/read', { workspaceRoot, path: filePath })).content || ''); const write = async () => await post('/workspace/write', { workspaceRoot, path: filePath, content: fileContent }); const loadGit = async () => setGit((await post('/git/info', { workspaceRoot })).git);
  return <section><Header title="Workspace / Git" subtitle="Point the system to a local project folder. Agents can scan folders, read/write files, and use safe git info." /><div className="toolbar"><input value={workspaceRoot} onChange={e => setWorkspaceRoot(e.target.value)} placeholder="/absolute/or/relative/project/path" /><button onClick={scan}>Scan folder</button><button onClick={loadGit}>Git info</button></div><div className="grid two"><div className="panel"><input value={path} onChange={e => setPath(e.target.value)} /><pre>{tree}</pre>{git && <pre>{JSON.stringify(git, null, 2)}</pre>}</div><div className="panel"><input value={filePath} onChange={e => setFilePath(e.target.value)} /><button onClick={read}>Read</button><button onClick={write}>Write</button><textarea rows="18" value={fileContent} onChange={e => setFileContent(e.target.value)} /></div></div></section>;
}

function SkillsPage({ skills, mcps }) { return <section><Header title="Skills / MCP catalog" subtitle="Base capabilities that can be attached to agents." /><div className="grid two"><div className="panel"><h3>Skills</h3>{skills.map(s => <div className="item" key={s.id}><b>{s.name}</b><span>{s.category}</span><p>{s.description}</p></div>)}</div><div className="panel"><h3>MCP connectors</h3>{mcps.map(m => <div className="item" key={m.id}><b>{m.name}</b><span>{m.endpoint}</span><p>{m.description}</p></div>)}</div></div></section>; }
async function post(url, body) { const res = await fetch(`${API}${url}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); const data = await res.json(); if (!res.ok || data.ok === false) throw new Error(data.error || 'Request failed'); return data; }
function slug(text) { return String(text || '').toLowerCase().trim().replace(/[^a-z0-9а-яіїєґ]+/gi, '-').replace(/^-|-$/g, ''); }
createRoot(document.getElementById('root')).render(<App />);
