import React, { useEffect, useState } from 'react';
import { buildWorkflowFromPrompt } from './workflowAssistant.js';

const API = 'http://localhost:8787/api';
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

export function IoTPipelinesPage({ agents, settings, setSettings, setAgents, setFlow, setMeta, setPage }) {
  const [pipelines, setPipelines] = useState([]);
  const [catalog, setCatalog] = useState({ sources: [], actions: [] });
  const [draftCatalog, setDraftCatalog] = useState({ sources: settings?.iotSources || [], actions: settings?.iotActions || [] });
  const [prompt, setPrompt] = useState('Розпізнати жест з прибудинкової камери й підготувати команду відкрити або закрити ворота з перевіркою безпеки.');
  const [assistantPlan, setAssistantPlan] = useState(null);
  const [view, setView] = useState('cards');
  const [status, setStatus] = useState('');

  useEffect(() => {
    fetch(`${API}/iot/pipelines`).then(response => response.json()).then(setPipelines).catch(() => setPipelines([]));
    fetch(`${API}/iot/catalog`).then(response => response.json()).then(data => { setCatalog(data); setDraftCatalog(data); }).catch(() => setCatalog({ sources: [], actions: [] }));
  }, []);

  useEffect(() => {
    if (!settings) return;
    setDraftCatalog({ sources: settings.iotSources || [], actions: settings.iotActions || [] });
  }, [settings]);

  const loadPipeline = (pipeline) => {
    const steps = pipeline.steps || [];
    setMeta({ ...pipeline, steps });
    setFlow(steps);
    setPage('flow');
  };
  const planWithAssistant = () => {
    const plan = buildWorkflowFromPrompt({ prompt, agents, existingFlow: [], idFactory: uuid });
    setAssistantPlan(plan);
  };
  const applyAssistantPlan = () => {
    const plan = assistantPlan || buildWorkflowFromPrompt({ prompt, agents, existingFlow: [], idFactory: uuid });
    setAgents(plan.agents);
    const flow = decorateIoTSteps(plan.steps, settings);
    setMeta({ id: '', name: 'AI IoT pipeline', category: 'iot', task: prompt, workspaceRoot: './workspace', loops: 1, cron: '', steps: flow, loopGroups: plan.loopGroups });
    setFlow(flow);
    setPage('flow');
  };
  const iotAgents = agents.filter(agent => {
    const haystack = [agent.id, agent.name, agent.role, ...(agent.skills || [])].join(' ').toLowerCase();
    return ['iot', 'device_control', 'gesture', 'sensor', 'camera'].some(token => haystack.includes(token));
  });
  const openWithAgent = (agent) => {
    const step = {
      id: uuid(),
      agentId: agent.id,
      note: `IoT control step for ${agent.name}.`,
      cron: '',
      loops: 1,
      dependsOnPrevious: true,
      iotSourceIds: (draftCatalog.sources || []).filter(item => item.enabled !== false).slice(0, 1).map(item => item.id),
      iotActionIds: (draftCatalog.actions || []).filter(item => item.enabled !== false).slice(0, 1).map(item => item.id)
    };
    setMeta({ id: '', name: `${agent.name} IoT pipeline`, category: 'iot', task: `Configure ${agent.name} to handle an IoT signal and prepare safe device actions.`, workspaceRoot: './workspace', loops: 1, cron: '', steps: [step], loopGroups: [] });
    setFlow([step]);
    setPage('flow');
  };
  const updateSource = (id, patch) => setDraftCatalog(current => ({ ...current, sources: (current.sources || []).map(source => source.id === id ? { ...source, ...patch } : source) }));
  const updateAction = (id, patch) => setDraftCatalog(current => ({ ...current, actions: (current.actions || []).map(action => action.id === id ? { ...action, ...patch } : action) }));
  const addSource = () => setDraftCatalog(current => ({
    ...current,
    sources: [...(current.sources || []), { id: `iot-source-${uuid()}`, name: 'New IoT source', kind: 'sensor', transport: 'wifi/http', endpoint: '', dataType: 'json', enabled: true, description: '' }]
  }));
  const addAction = () => setDraftCatalog(current => ({
    ...current,
    actions: [...(current.actions || []), { id: `iot-action-${uuid()}`, name: 'New IoT action', kind: 'relay', transport: 'wifi/http', endpoint: '', commands: ['turn_on', 'turn_off'], requiresApproval: true, enabled: true, description: '' }]
  }));
  const saveIoTSettings = async () => {
    try {
      setStatus('Saving IoT catalog...');
      const payload = { ...(settings || { id: 'runtime-settings' }), iotSources: draftCatalog.sources || [], iotActions: draftCatalog.actions || [] };
      const response = await fetch(`${API}/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || 'IoT settings save failed');
      setSettings(data.settings);
      const nextCatalog = { sources: data.settings.iotSources || [], actions: data.settings.iotActions || [] };
      setCatalog(nextCatalog);
      setDraftCatalog(nextCatalog);
      setStatus('IoT catalog saved');
    } catch (error) {
      setStatus(error.message);
    }
  };

  return <section>
    <Header title="IoT Pipelines" subtitle="Build signal-driven workflows from cameras, microphones and sensors, then map them to safe device actions." />
    <div className="panel assistant-panel">
      <div>
        <h3>AI IoT assistant</h3>
        <p>Describe the physical-world scenario. It will reuse preset IoT agents or create missing ones and wire source/action-aware steps.</p>
      </div>
      <textarea value={prompt} onChange={e => setPrompt(e.target.value)} />
      <div className="row"><button onClick={planWithAssistant}>Plan IoT workflow</button><button className="primary" onClick={applyAssistantPlan}>Open in Workflow builder</button><button onClick={saveIoTSettings}>Save IoT catalog</button><span className="muted">{status}</span></div>
      {assistantPlan && <div className="assistant-plan"><b>{assistantPlan.summary}</b><span>{assistantPlan.steps.map((step, index) => `${index + 1}. ${assistantPlan.agents.find(agent => agent.id === step.agentId)?.name || step.agentId}`).join(' → ')}</span></div>}
    </div>

    <div className="view-switch">
      <button className={view === 'cards' ? 'active' : ''} onClick={() => setView('cards')}>Cards</button>
      <button className={view === 'diagram' ? 'active' : ''} onClick={() => setView('diagram')}>Signal diagram</button>
    </div>

    <div className="grid two">
      <div className="panel">
        <h3>Example IoT pipelines</h3>
        <div className="settings-list">
          {pipelines.map(pipeline => <div className="iot-pipeline-card" key={pipeline.id}>
            <b>{pipeline.name}</b>
            <span>{pipeline.task}</span>
            <small>{pipeline.steps?.length || 0} steps · {pipeline.cron || 'manual run'}</small>
            <button className="primary" onClick={() => loadPipeline(pipeline)}>Open builder</button>
          </div>)}
        </div>
      </div>
      <div className="panel">
        <h3>{view === 'diagram' ? 'Source → Agent → Action' : 'Configured IoT catalog'}</h3>
        {view === 'diagram' ? <IoTSignalDiagram sources={draftCatalog.sources} actions={draftCatalog.actions} /> : <IoTCatalog sources={draftCatalog.sources} actions={draftCatalog.actions} />}
      </div>
    </div>
    <div className="grid two iot-admin-grid">
      <div className="panel">
        <div className="settings-card-head"><h3>IoT sources</h3><button onClick={addSource}>+ Add source</button></div>
        <p className="muted">Inputs: cameras, microphones, sensors, webhooks or telemetry over Wi‑Fi, Bluetooth, cable, HTTP, MQTT, RTSP and similar transports.</p>
        <div className="settings-list">{(draftCatalog.sources || []).map(source => <IoTSourceEditor key={source.id} source={source} update={patch => updateSource(source.id, patch)} />)}</div>
      </div>
      <div className="panel">
        <div className="settings-card-head"><h3>IoT actions</h3><button onClick={addAction}>+ Add action</button></div>
        <p className="muted">Actions are device-like capabilities for agents: gate controllers, relays, appliances, locks or other actuators with allowed commands.</p>
        <div className="settings-list">{(draftCatalog.actions || []).map(action => <IoTActionEditor key={action.id} action={action} update={patch => updateAction(action.id, patch)} />)}</div>
      </div>
    </div>
    <div className="panel">
      <h3>IoT control agents</h3>
      <p className="muted">Add an IoT-aware agent to a workflow when you need sensing, gesture recognition, safety approval or device control.</p>
      <div className="iot-agent-grid">
        {iotAgents.map(agent => <div className="iot-pipeline-card" key={agent.id}>
          <b>{agent.name}</b>
          <span>{agent.role}</span>
          <small>{agent.provider || 'openai'} · {agent.model || 'default model'} · {(agent.skills || []).join(', ')}</small>
          <button onClick={() => openWithAgent(agent)}>Open with this agent</button>
        </div>)}
      </div>
    </div>
  </section>;
}

function decorateIoTSteps(steps, settings) {
  const sourceIds = (settings?.iotSources || []).filter(item => item.enabled !== false).map(item => item.id);
  const actionIds = (settings?.iotActions || []).filter(item => item.enabled !== false).map(item => item.id);
  return steps.map(step => {
    const lower = `${step.roleKey || ''} ${step.note || ''}`.toLowerCase();
    return {
      ...step,
      iotSourceIds: lower.includes('iot') || lower.includes('vision') || lower.includes('gesture') || lower.includes('signal') ? sourceIds.slice(0, 2) : step.iotSourceIds || [],
      iotActionIds: lower.includes('control') || lower.includes('gate') || lower.includes('device') || lower.includes('action') ? actionIds.slice(0, 2) : step.iotActionIds || []
    };
  });
}

function IoTCatalog({ sources, actions }) {
  return <div className="iot-catalog">
    <div><h4>Sources</h4>{sources.map(source => <div className="iot-mini" key={source.id}><b>{source.name}</b><span>{source.kind} · {source.dataType} · {source.transport}</span><small>{source.endpoint}</small></div>)}</div>
    <div><h4>Actions</h4>{actions.map(action => <div className="iot-mini" key={action.id}><b>{action.name}</b><span>{action.kind} · {(action.commands || []).join(', ')}</span><small>{action.requiresApproval ? 'approval required' : 'automatic allowed'} · {action.endpoint}</small></div>)}</div>
  </div>;
}

function IoTSourceEditor({ source, update }) {
  return <div className="settings-card">
    <div className="settings-card-head"><b>{source.name}</b><label><input type="checkbox" checked={source.enabled !== false} onChange={e => update({ enabled: e.target.checked })} /> enabled</label></div>
    <div className="drawer-grid"><input value={source.name || ''} onChange={e => update({ name: e.target.value })} placeholder="Name" /><input value={source.kind || ''} onChange={e => update({ kind: e.target.value })} placeholder="camera / microphone / sensor" /></div>
    <div className="drawer-grid"><input value={source.transport || ''} onChange={e => update({ transport: e.target.value })} placeholder="wifi/rtsp, mqtt, bluetooth" /><input value={source.dataType || ''} onChange={e => update({ dataType: e.target.value })} placeholder="video / audio / json" /></div>
    <input value={source.endpoint || ''} onChange={e => update({ endpoint: e.target.value })} placeholder="Endpoint" />
    <textarea value={source.description || ''} onChange={e => update({ description: e.target.value })} placeholder="Human description and usage notes" />
  </div>;
}

function IoTActionEditor({ action, update }) {
  return <div className="settings-card">
    <div className="settings-card-head"><b>{action.name}</b><label><input type="checkbox" checked={action.enabled !== false} onChange={e => update({ enabled: e.target.checked })} /> enabled</label></div>
    <div className="drawer-grid"><input value={action.name || ''} onChange={e => update({ name: e.target.value })} placeholder="Name" /><input value={action.kind || ''} onChange={e => update({ kind: e.target.value })} placeholder="gate / relay / appliance" /></div>
    <div className="drawer-grid"><input value={action.transport || ''} onChange={e => update({ transport: e.target.value })} placeholder="wifi/http, mqtt, bluetooth" /><input value={(action.commands || []).join(', ')} onChange={e => update({ commands: e.target.value.split(',').map(item => item.trim()).filter(Boolean) })} placeholder="open, close, stop" /></div>
    <input value={action.endpoint || ''} onChange={e => update({ endpoint: e.target.value })} placeholder="Endpoint" />
    <label className="check-row"><input type="checkbox" checked={action.requiresApproval !== false} onChange={e => update({ requiresApproval: e.target.checked })} /> Requires approval before real device action</label>
    <textarea value={action.description || ''} onChange={e => update({ description: e.target.value })} placeholder="Human description and safety notes" />
  </div>;
}

function IoTSignalDiagram({ sources, actions }) {
  return <div className="iot-diagram">
    <div className="iot-column"><b>Sources</b>{sources.map(source => <span key={source.id}>📡 {source.name}</span>)}</div>
    <div className="iot-arrow">→</div>
    <div className="iot-column"><b>Agents</b><span>IoT Signal Agent</span><span>Vision Gesture Agent</span><span>IoT Safety Supervisor</span><span>IoT Device Manager</span></div>
    <div className="iot-arrow">→</div>
    <div className="iot-column"><b>Actions</b>{actions.map(action => <span key={action.id}>⚙️ {action.name}</span>)}</div>
  </div>;
}

function Header({ title, subtitle }) { return <header className="header"><h1>{title}</h1><p>{subtitle}</p></header>; }
