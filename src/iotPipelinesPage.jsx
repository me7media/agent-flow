import React, { useEffect, useState } from 'react';
import { buildWorkflowFromPrompt } from './workflowAssistant.js';

const API = 'http://localhost:8787/api';
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
const asJson = async (response) => {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || data.message || 'IoT request failed');
  return data;
};
const post = (url, body) => fetch(`${API}${url}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(asJson);

const sourcePresets = [
  { name: 'Camera0 (Tuya FaceTime)', kind: 'camera', transport: 'wifi/http', endpoint: 'http://127.0.0.1:8787/api/iot/camera/PTZB648647BMZSB', dataType: 'video', description: 'Surveillance camera Camera0 (Tuya ID: PTZB648647BMZSB) via local HTTP gateway/FaceTime HD camera.' },
  { name: 'Doorbell Camera', kind: 'camera', transport: 'wifi/http', endpoint: 'http://127.0.0.1:8787/api/iot/camera/PTZB648647BMZSB', dataType: 'video', description: 'Smart video doorbell camera stream at the front door.' },
  { name: 'RTSP IP Camera', kind: 'camera', transport: 'wifi/rtsp', endpoint: 'rtsp://192.168.0.101/live/ch0', dataType: 'video', description: 'Generic RTSP/ONVIF security camera stream.' },
  { name: 'Porch Microphone', kind: 'microphone', transport: 'usb/audio', endpoint: 'local://audio/porch', dataType: 'audio', description: 'Audio input source for voice or sound-event workflows.' },
  { name: 'Living Room Thermostat', kind: 'sensor', transport: 'wifi/http', endpoint: 'http://127.0.0.1:8787/api/iot/thermo/telemetry', dataType: 'json', description: 'Wi-Fi sensor reporting temperature, humidity and air quality index.' },
  { name: 'Garden Motion Sensor', kind: 'sensor', transport: 'mqtt/wifi', endpoint: 'mqtt://iot.local/sensors/garden-motion', dataType: 'boolean', description: 'Motion sensor event stream used by demo IoT pipelines.' },
  { name: 'Custom ESP32 Telemetry', kind: 'sensor', transport: 'custom/esp32', endpoint: 'http://192.168.0.150/telemetry', dataType: 'json', description: 'Custom embedded microcontroller telemetry feed (temperature/vibration/distance).' }
];

const actionPresets = [
  { name: 'Driveway Gate Controller', kind: 'gate', transport: 'wifi/http', endpoint: 'http://127.0.0.1:8787/api/iot/gate/control', commands: ['open', 'close', 'stop'], adapter: 'generic-json', requiresApproval: true, description: 'Driveway gate actuator used by gesture workflows.' },
  { name: 'Garage Door Opener', kind: 'gate', transport: 'wifi/http', endpoint: 'http://127.0.0.1:8787/api/iot/gate/control?device=garage', commands: ['open', 'close'], adapter: 'generic-json', requiresApproval: true, description: 'Smart garage relay board.' },
  { name: 'Living Room AC', kind: 'appliance', transport: 'wifi/http', endpoint: 'http://127.0.0.1:8787/api/iot/gate/control?device=ac', commands: ['turn_on', 'turn_off', 'set_temp_22', 'set_temp_24'], adapter: 'generic-json', requiresApproval: false, description: 'Smart air conditioner IR blaster or Wi-Fi control.' },
  { name: 'Window Blinds Motor', kind: 'motor', transport: 'zigbee/mqtt', endpoint: 'mqtt://iot.local/blinds/control', commands: ['open', 'close', 'stop'], adapter: 'custom', requiresApproval: false, description: 'Zigbee motorized roller shade controller.' },
  { name: 'Smart Door Lock', kind: 'lock', transport: 'ble/lock', endpoint: 'local://lock/front-door', commands: ['lock', 'unlock'], adapter: 'custom', requiresApproval: true, description: 'Smart Bluetooth deadbolt actuator.' },
  { name: 'Tuya Smart Plug', kind: 'relay', transport: 'tuya-local', endpoint: '192.168.0.100', commands: ['turn_on', 'turn_off'], adapter: 'tuya-local', deviceId: 'bf60bd5c14400e69b1nplq', localKey: '', version: '3.3', dps: 1, requiresApproval: true, description: 'Tuya smart plug local relay control.' },
  { name: 'Custom ESP32 Relay Board', kind: 'switch', transport: 'custom/esp32', endpoint: 'http://192.168.0.150/relay', commands: ['high', 'low'], adapter: 'generic-json', requiresApproval: false, description: 'Custom Arduino/ESP32 relay switch controlling secondary GPIO pins.' }
];

export function IoTPipelinesPage({ agents, providers = [], settings, setSettings, setAgents, setFlow, setMeta, setPage }) {
  const [pipelines, setPipelines] = useState([]);
  const [catalog, setCatalog] = useState({ sources: [], actions: [] });
  const [draftCatalog, setDraftCatalog] = useState({ sources: settings?.iotSources || [], actions: settings?.iotActions || [] });
  const [adapters, setAdapters] = useState([]);
  const [prompt, setPrompt] = useState('Розпізнати жест з прибудинкової камери й підготувати команду відкрити або закрити ворота з перевіркою безпеки.');
  const [assistantPlan, setAssistantPlan] = useState(null);
  const [view, setView] = useState('cards');
  const [status, setStatus] = useState('');
  const [sourceResults, setSourceResults] = useState({});
  const [actionResults, setActionResults] = useState({});
  const [discoveryDraft, setDiscoveryDraft] = useState({ transport: 'wifi/http', subnet: '', hosts: '127.0.0.1', ports: '80,443,8080,8123' });
  const [discoveryResult, setDiscoveryResult] = useState(null);

  useEffect(() => {
    fetch(`${API}/iot/pipelines`).then(response => response.json()).then(setPipelines).catch(() => setPipelines([]));
    fetch(`${API}/iot/catalog`).then(response => response.json()).then(data => { setCatalog(data); setDraftCatalog(data); }).catch(() => setCatalog({ sources: [], actions: [] }));
    fetch(`${API}/iot/adapters`).then(response => response.json()).then(data => setAdapters(data.adapters || [])).catch(() => setAdapters([]));
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
    const plan = buildWorkflowFromPrompt({ prompt, agents, existingFlow: [], idFactory: uuid, iotEnabled: true, providers });
    setAssistantPlan(plan);
  };
  const applyAssistantPlan = () => {
    const plan = assistantPlan || buildWorkflowFromPrompt({ prompt, agents, existingFlow: [], idFactory: uuid, iotEnabled: true, providers });
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
  const addSource = (source = null) => setDraftCatalog(current => ({
    ...current,
    sources: [...(current.sources || []), source || { id: `iot-source-${uuid()}`, name: 'New IoT source', kind: 'sensor', transport: 'wifi/http', endpoint: '', dataType: 'json', enabled: true, description: '' }]
  }));
  const addAction = (action = null) => setDraftCatalog(current => ({
    ...current,
    actions: [...(current.actions || []), action || { id: `iot-action-${uuid()}`, name: 'New IoT action', kind: 'relay', transport: 'wifi/http', endpoint: '', adapter: 'generic-json', commands: ['turn_on', 'turn_off'], commandMap: {}, requiresApproval: true, enabled: true, description: '' }]
  }));
  const addDiscoveredAction = (action) => setDraftCatalog(current => ({
    ...current,
    actions: [...(current.actions || []), action]
  }));
  const saveIoTSettings = async () => {
    try {
      setStatus('Saving IoT catalog...');
      const cleanActions = (draftCatalog.actions || []).map(({ commandMapText, ...action }) => action);
      const payload = { ...(settings || { id: 'runtime-settings' }), iotSources: draftCatalog.sources || [], iotActions: cleanActions };
      const response = await fetch(`${API}/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await asJson(response);
      setSettings(data.settings);
      const nextCatalog = { sources: data.settings.iotSources || [], actions: data.settings.iotActions || [] };
      setCatalog(nextCatalog);
      setDraftCatalog(nextCatalog);
      setStatus('IoT catalog saved');
    } catch (error) {
      setStatus(error.message);
    }
  };
  const discover = async () => {
    try {
      setStatus('Scanning IoT network...');
      const body = {
        transport: discoveryDraft.transport,
        subnet: discoveryDraft.subnet,
        hosts: discoveryDraft.hosts.split(',').map(item => item.trim()).filter(Boolean),
        ports: discoveryDraft.ports.split(',').map(item => item.trim()).filter(Boolean)
      };
      const result = await post('/iot/discover', body);
      setDiscoveryResult(result);
      setStatus(`Discovery complete: ${(result.devices || []).length} device(s)`);
    } catch (error) {
      setStatus(error.message);
    }
  };
  const readSource = async (source) => {
    try {
      const result = await post('/iot/sources/read', { sourceId: source.id });
      setSourceResults(current => ({ ...current, [source.id]: result }));
    } catch (error) {
      setSourceResults(current => ({ ...current, [source.id]: { ok: false, message: error.message } }));
    }
  };
  const runAction = async (action, command, options = {}) => {
    try {
      const result = await post(options.execute ? '/iot/actions/execute' : '/iot/actions/test', { actionId: action.id, command, approved: options.approved, dryRun: options.dryRun });
      setActionResults(current => ({ ...current, [`${action.id}:${command}`]: result }));
    } catch (error) {
      setActionResults(current => ({ ...current, [`${action.id}:${command}`]: { ok: false, message: error.message } }));
    }
  };

  return <section>
    <Header title="IoT Pipelines" subtitle="Discover devices, register signal sources, test reads, map actions, and build safe workflows for home or enterprise automation." />
    <div className="panel assistant-panel">
      <div>
        <h3>AI IoT assistant</h3>
        <p>Describe the physical-world scenario. It will reuse preset IoT agents or create missing ones and wire source/action-aware steps.</p>
      </div>
      <textarea value={prompt} onChange={e => setPrompt(e.target.value)} />
      <div className="row"><button onClick={planWithAssistant}>Plan IoT workflow</button><button className="primary" onClick={applyAssistantPlan}>Open in Workflow builder</button><button onClick={saveIoTSettings}>Save IoT catalog</button><span className="muted">{status}</span></div>
      {assistantPlan && <div className="assistant-plan"><b>{assistantPlan.summary}</b>{assistantPlan.warning && <em>{assistantPlan.warning}</em>}<span>{assistantPlan.steps.map((step, index) => `${index + 1}. ${assistantPlan.agents.find(agent => agent.id === step.agentId)?.name || step.agentId}`).join(' → ')}</span></div>}
    </div>

    <div className="grid two">
      <DiscoveryPanel adapters={adapters} draft={discoveryDraft} setDraft={setDiscoveryDraft} result={discoveryResult} discover={discover} addSource={addSource} addAction={addDiscoveredAction} />
      <div className="panel">
        <h3>Runtime architecture</h3>
        <div className="iot-diagram compact">
          <div className="iot-column"><b>1. Discover</b><span>Wi‑Fi HTTP scan</span><span>Bluetooth inventory</span><span>Manual gateway</span></div>
          <div className="iot-arrow">→</div>
          <div className="iot-column"><b>2. Connect</b><span>Source read</span><span>Webhook/sensor payload</span><span>Gateway bridge</span></div>
          <div className="iot-arrow">→</div>
          <div className="iot-column"><b>3. Act safely</b><span>Dry-run first</span><span>Approval required</span><span>Allowlisted hosts</span></div>
        </div>
        <p className="muted">Real Wi‑Fi/HTTP reads/actions require `IOT_ALLOWED_HOSTS`. Physical actions require `IOT_DEVICE_ACTIONS_ENABLED=true`; otherwise the API returns dry-run plans.</p>
      </div>
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
        <div className="settings-card-head">
          <h3>IoT sources</h3>
          <div className="row" style={{ gap: '8px', alignItems: 'center' }}>
            <button onClick={() => addSource()}>+ Add source</button>
            <select onChange={e => {
              if (e.target.value) {
                const preset = sourcePresets[parseInt(e.target.value)];
                addSource({ id: `iot-source-${uuid()}`, ...preset, enabled: true });
                e.target.value = '';
              }
            }} className="preset-select" style={{ padding: '6px', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--panel-bg)', color: 'var(--text-color)', fontSize: '13px' }}>
              <option value="">-- Add Preconfigured --</option>
              {sourcePresets.map((preset, idx) => <option key={idx} value={idx}>{preset.name}</option>)}
            </select>
          </div>
        </div>
        <p className="muted">Inputs: cameras, microphones, sensors, webhooks or telemetry over Wi‑Fi, Bluetooth, cable, HTTP, MQTT, RTSP and similar transports.</p>
        <div className="settings-list">{(draftCatalog.sources || []).map(source => <IoTSourceEditor key={source.id} source={source} update={patch => updateSource(source.id, patch)} read={() => readSource(source)} result={sourceResults[source.id]} />)}</div>
      </div>
      <div className="panel">
        <div className="settings-card-head">
          <h3>IoT actions</h3>
          <div className="row" style={{ gap: '8px', alignItems: 'center' }}>
            <button onClick={() => addAction()}>+ Add action</button>
            <select onChange={e => {
              if (e.target.value) {
                const preset = actionPresets[parseInt(e.target.value)];
                addAction({ id: `iot-action-${uuid()}`, ...preset, enabled: true });
                e.target.value = '';
              }
            }} className="preset-select" style={{ padding: '6px', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--panel-bg)', color: 'var(--text-color)', fontSize: '13px' }}>
              <option value="">-- Add Preconfigured --</option>
              {actionPresets.map((preset, idx) => <option key={idx} value={idx}>{preset.name}</option>)}
            </select>
          </div>
        </div>
        <p className="muted">Actions are device-like capabilities for agents: gate controllers, relays, appliances, locks or other actuators with allowed commands.</p>
        <div className="settings-list">{(draftCatalog.actions || []).map(action => <IoTActionEditor key={action.id} action={action} update={patch => updateAction(action.id, patch)} runAction={runAction} results={actionResults} />)}</div>
      </div>
    </div>
    <div className="panel">
      <h3>IoT control agents</h3>
      <p className="muted">Add an IoT-aware agent to a workflow when you need sensing, gesture recognition, safety approval or device control.</p>
      <div className="iot-agent-grid">
        {iotAgents.map(agent => <div className="iot-pipeline-card" key={agent.id}>
          <b>{agent.name}</b>
          <span>{agent.role}</span>
          <small>{agent.provider || 'auto'} · {agent.model || 'provider default'} · {(agent.skills || []).join(', ')}</small>
          <button onClick={() => openWithAgent(agent)}>Open with this agent</button>
        </div>)}
      </div>
    </div>
  </section>;
}

function DiscoveryPanel({ adapters, draft, setDraft, result, discover, addSource, addAction }) {
  return <div className="panel">
    <h3>Connectivity & discovery</h3>
    <p className="muted">Scan small host lists/subnets for Wi‑Fi HTTP gateways, inspect known Bluetooth devices, or manually register gateways.</p>
    <div className="drawer-grid"><label>Transport
      <select value={draft.transport} onChange={e => setDraft({ ...draft, transport: e.target.value })}>
        <option value="wifi/http">Wi‑Fi / HTTP</option>
        <option value="tuya-local">Tuya local encrypted</option>
        <option value="bluetooth">Bluetooth inventory</option>
        <option value="mqtt">MQTT gateway</option>
        <option value="rtsp">RTSP camera gateway</option>
      </select>
    </label><label>Ports
      <input value={draft.ports} onChange={e => setDraft({ ...draft, ports: e.target.value })} placeholder="80,443,8080" />
    </label></div>
    <div className="drawer-grid"><input value={draft.hosts} onChange={e => setDraft({ ...draft, hosts: e.target.value })} placeholder="Hosts: 192.168.1.10,192.168.1.11" /><input value={draft.subnet} onChange={e => setDraft({ ...draft, subnet: e.target.value })} placeholder="Optional CIDR: 192.168.1.0/28" /></div>
    <div className="row"><button className="primary" onClick={discover}>Discover / inspect</button><span className="muted">Keep scans small; max hosts are server-limited.</span></div>
    <div className="adapter-grid">{adapters.map(adapter => <div className="iot-mini" key={adapter.id}><b>{adapter.name}</b><span>{adapter.transports.join(', ')}</span><small>{adapter.notes}</small></div>)}</div>
    {result && <div className="settings-list"><b>Discovery result</b><small>{result.notes || `${result.scannedHosts || 0} host(s), ${(result.devices || []).length} device(s)`}</small>{(result.devices || []).map(device => <div className="iot-mini" key={device.id || device.address || device.name}><b>{device.name || device.id}</b><span>{device.transport || result.transport} · {device.endpoint || device.address || 'no endpoint'}</span><small>{device.sample || device.status || ''}</small><div className="row">{device.suggestedSource && <button onClick={() => addSource(device.suggestedSource)}>Add as source</button>}{device.suggestedAction && <button onClick={() => addAction(device.suggestedAction)}>Add as action</button>}</div></div>)}</div>}
  </div>;
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

function IoTSourceEditor({ source, update, read, result }) {
  return <div className="settings-card">
    <div className="settings-card-head"><b>{source.name}</b><label><input type="checkbox" checked={source.enabled !== false} onChange={e => update({ enabled: e.target.checked })} /> enabled</label></div>
    <div className="drawer-grid"><input value={source.name || ''} onChange={e => update({ name: e.target.value })} placeholder="Name" /><input value={source.kind || ''} onChange={e => update({ kind: e.target.value })} placeholder="camera / microphone / sensor" /></div>
    <div className="drawer-grid"><input value={source.transport || ''} onChange={e => update({ transport: e.target.value })} placeholder="wifi/http, mqtt, bluetooth" /><input value={source.dataType || ''} onChange={e => update({ dataType: e.target.value })} placeholder="video / audio / json" /></div>
    <input value={source.endpoint || ''} onChange={e => update({ endpoint: e.target.value })} placeholder="Endpoint" />
    <textarea value={source.description || ''} onChange={e => update({ description: e.target.value })} placeholder="Human description and usage notes" />
    <div className="row"><button onClick={read}>Read / test source</button><span className="muted">HTTP reads require `IOT_ALLOWED_HOSTS`.</span></div>
    {result && <pre className={result.ok === false ? 'error' : ''}>{JSON.stringify(result, null, 2)}</pre>}
  </div>;
}

function IoTActionEditor({ action, update, runAction, results }) {
  const commands = action.commands || [];
  const commandMapText = JSON.stringify(action.commandMap || {}, null, 2);
  const updateCommandMap = (value) => {
    try {
      update({ commandMap: value.trim() ? JSON.parse(value) : {} });
    } catch {
      update({ commandMapText: value });
    }
  };
  return <div className="settings-card">
    <div className="settings-card-head"><b>{action.name}</b><label><input type="checkbox" checked={action.enabled !== false} onChange={e => update({ enabled: e.target.checked })} /> enabled</label></div>
    <div className="drawer-grid"><input value={action.name || ''} onChange={e => update({ name: e.target.value })} placeholder="Name" /><input value={action.kind || ''} onChange={e => update({ kind: e.target.value })} placeholder="gate / relay / appliance" /></div>
    <div className="drawer-grid"><input value={action.transport || ''} onChange={e => update({ transport: e.target.value })} placeholder="wifi/http, mqtt, bluetooth" /><input value={commands.join(', ')} onChange={e => update({ commands: e.target.value.split(',').map(item => item.trim()).filter(Boolean) })} placeholder="turn_on, turn_off" /></div>
    <label>HTTP adapter preset
      <select value={action.adapter || 'generic-json'} onChange={e => update({ adapter: e.target.value })}>
        <option value="generic-json">Generic JSON POST</option>
        <option value="tasmota">Tasmota HTTP</option>
        <option value="shelly">Shelly relay HTTP</option>
        <option value="tuya-local">Tuya local encrypted</option>
        <option value="home-assistant-webhook">Home Assistant webhook</option>
        <option value="custom">Custom command map</option>
      </select>
    </label>
    <input value={action.endpoint || ''} onChange={e => update({ endpoint: e.target.value })} placeholder="Endpoint" />
    {(action.adapter === 'tuya-local' || action.transport === 'tuya-local') && <div className="drawer-grid">
      <input value={action.deviceId || ''} onChange={e => update({ deviceId: e.target.value })} placeholder="Tuya deviceId" />
      <input type="password" value={action.localKey || ''} onChange={e => update({ localKey: e.target.value })} placeholder="Tuya localKey" />
      <input value={action.version || '3.3'} onChange={e => update({ version: e.target.value })} placeholder="Protocol version" />
      <input value={action.dps || 1} onChange={e => update({ dps: e.target.value })} placeholder="Switch DPS, usually 1" />
    </div>}
    <label>Command map JSON
      <textarea rows="7" value={action.commandMapText ?? commandMapText} onChange={e => updateCommandMap(e.target.value)} onBlur={() => update({ commandMapText: undefined })} placeholder={'{"turn_on":{"method":"GET","path":"/cm","query":{"cmnd":"Power On"}}}'} />
    </label>
    <small className="muted">Use templates like {"{{command}}"} and {"{{actionId}}"}. Tasmota/Shelly presets work without custom JSON.</small>
    <label className="check-row"><input type="checkbox" checked={action.requiresApproval !== false} onChange={e => update({ requiresApproval: e.target.checked })} /> Requires approval before real device action</label>
    <textarea value={action.description || ''} onChange={e => update({ description: e.target.value })} placeholder="Human description and safety notes" />
    <div className="command-grid">{commands.map(command => <div className="iot-mini" key={command}><b>{command}</b><div className="row"><button onClick={() => runAction(action, command)}>Dry run</button><button className="danger-btn" onClick={() => runAction(action, command, { execute: true, approved: true })}>Execute approved</button></div>{results[`${action.id}:${command}`] && <pre>{JSON.stringify(results[`${action.id}:${command}`], null, 2)}</pre>}</div>)}</div>
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
