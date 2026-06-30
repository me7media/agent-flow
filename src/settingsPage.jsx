import React, { useEffect, useMemo, useState } from 'react';

const API = 'http://localhost:8787/api';
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
const emptySettings = { id: 'runtime-settings', agentExecution: { fileWriteMode: 'direct', maxFileBlocks: 20, allowMockProvider: false }, llmProviders: [], iotSources: [], iotActions: [] };

export function SettingsPage({ settings, setSettings, setProviders }) {
  const [draft, setDraft] = useState(settings || emptySettings);
  const [status, setStatus] = useState('');

  useEffect(() => setDraft(settings || emptySettings), [settings]);

  const providers = draft?.llmProviders || [];
  const execution = draft?.agentExecution || emptySettings.agentExecution;
  const canSave = useMemo(() => !!draft?.id, [draft]);

  const updateExecution = (patch) => setDraft(current => ({
    ...current,
    agentExecution: { ...(current.agentExecution || emptySettings.agentExecution), ...patch }
  }));
  const updateProvider = (id, patch) => setDraft(current => ({
    ...current,
    llmProviders: (current.llmProviders || []).map(provider => provider.id === id ? { ...provider, ...patch } : provider)
  }));
  const providerStatus = (provider) => {
    if (provider.enabled === false) return { label: 'Disabled', tone: 'muted' };
    if (provider.configured) return { label: 'Ready for workflows', tone: 'ready' };
    if ((provider.providerKind || provider.id) === 'mock') return { label: 'Test-only disabled', tone: 'warn' };
    return { label: 'Needs settings', tone: 'warn' };
  };
  const addProvider = () => setDraft(current => ({
    ...current,
    llmProviders: [
      ...(current.llmProviders || []),
      { id: `custom-${uuid()}`, name: 'Custom provider', providerKind: 'openai', enabled: true, defaultModel: '', apiKey: '', baseUrl: '' }
    ]
  }));
  const saveSettings = async () => {
    try {
      setStatus('Saving...');
      const response = await fetch(`${API}/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft) });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || 'Settings save failed');
      setSettings(data.settings);
      if (data.providers) setProviders(data.providers);
      setStatus('Saved');
    } catch (error) {
      setStatus(error.message);
    }
  };

  return <section>
    <Header title="Settings" subtitle="Configure workflow-agent LLM providers stored locally in SQLite. Env credentials are reserved for system AI assistants. IoT devices live in IoT Pipelines." />
    <div className="settings-grid">
      <div className="panel">
        <h3>Agent execution</h3>
        <p className="muted">Controls whether developer agents write `file` blocks directly into the selected workspace or stage them for review.</p>
        <div className="drawer-grid">
          <label>File write mode
            <select value={execution.fileWriteMode || 'direct'} onChange={e => updateExecution({ fileWriteMode: e.target.value })}>
              <option value="direct">Direct write to workspace</option>
              <option value="review">Stage under agent-flow-output/generated</option>
            </select>
          </label>
          <label>Max file blocks
            <input type="number" min="1" max="100" value={execution.maxFileBlocks || 20} onChange={e => updateExecution({ maxFileBlocks: e.target.value })} />
          </label>
        </div>
        <label className="check-row"><input type="checkbox" checked={!!execution.allowMockProvider} onChange={e => updateExecution({ allowMockProvider: e.target.checked })} /> Allow Mock provider for local tests only</label>
      </div>
      <div className="panel">
        <h3>Agent LLM providers</h3>
        <p className="muted">Per-agent provider/model choices use only these runtime settings. Add API keys or local base URLs here; `.env` keys are not used by workflow agents.</p>
        <button onClick={addProvider}>+ Add provider</button>
        <div className="settings-list">
          {providers.map(provider => {
            const status = providerStatus(provider);
            return <div className="settings-card" key={provider.id}>
            <div className="settings-card-head"><div><b>{provider.name || provider.id}</b><span className={`provider-badge ${status.tone}`}>{status.label}</span></div><label><input type="checkbox" checked={provider.enabled !== false} onChange={e => updateProvider(provider.id, { enabled: e.target.checked })} /> enabled</label></div>
            <div className="drawer-grid">
              <label>Provider ID
                <input value={provider.id || ''} onChange={e => updateProvider(provider.id, { id: e.target.value })} placeholder="openai / ollama / custom-id" />
              </label>
              <label>Name
                <input value={provider.name || ''} onChange={e => updateProvider(provider.id, { name: e.target.value })} placeholder="Display name" />
              </label>
            </div>
            <label>Provider kind
              <select value={provider.providerKind || provider.id || 'openai'} onChange={e => updateProvider(provider.id, { providerKind: e.target.value })}>
                <option value="openai">OpenAI / OpenAI-compatible</option>
                <option value="ollama">Ollama</option>
                <option value="gemini">Gemini</option>
                <option value="anthropic">Claude / Anthropic</option>
                <option value="mock">Mock</option>
              </select>
            </label>
            <div className="drawer-grid">
              <label>Default model
                <input value={provider.defaultModel || ''} onChange={e => updateProvider(provider.id, { defaultModel: e.target.value })} placeholder="gpt-4.1-mini / llama3.1" />
              </label>
              <label>Base URL
                <input value={provider.baseUrl || ''} onChange={e => updateProvider(provider.id, { baseUrl: e.target.value })} placeholder="http://localhost:11434" />
              </label>
            </div>
            <label>API key
              <input type="password" value={provider.apiKey || ''} onChange={e => updateProvider(provider.id, { apiKey: e.target.value })} placeholder="Stored locally for workflow agents; masked keys are preserved" />
            </label>
            {provider.status && <small className="muted">{provider.status}</small>}
          </div>;
          })}
        </div>
      </div>
    </div>
    <div className="sticky-actions"><button className="primary" disabled={!canSave} onClick={saveSettings}>Save settings</button><span>{status}</span></div>
  </section>;
}

function Header({ title, subtitle }) { return <header className="header"><h1>{title}</h1><p>{subtitle}</p></header>; }
