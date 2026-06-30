const roleCatalog = [
  {
    key: 'requirements',
    label: 'Requirements Analyst',
    match: ['requirement', 'scope', 'brief', 'acceptance', 'вимог', 'задач'],
    skills: ['research', 'planner', 'product'],
    keywords: ['requirements', 'analyst', 'research', 'planning', 'product']
  },
  {
    key: 'scanner',
    label: 'Project Scanner',
    match: ['repo', 'project', 'codebase', 'scan', 'workspace', 'файл', 'проект', 'код'],
    skills: ['folder_scan', 'file_read', 'codebase_map', 'repo_indexer'],
    keywords: ['scanner', 'scan', 'codebase', 'repository', 'filesystem']
  },
  {
    key: 'architect',
    label: 'Architecture Agent',
    match: ['architecture', 'design', 'database', 'api', 'міграц', 'архітект', 'schema'],
    skills: ['architect', 'database', 'migration_planner'],
    keywords: ['architect', 'architecture', 'system']
  },
  {
    key: 'developer',
    label: 'Developer Agent',
    match: ['build', 'create', 'implement', 'code', 'backend', 'frontend', 'fix', 'додай', 'створи', 'реаліз'],
    skills: ['developer', 'file_read', 'file_write', 'patch_writer', 'code_generation'],
    keywords: ['developer', 'implementation', 'autonomous developer', 'code builder']
  },
  {
    key: 'qa',
    label: 'QA Agent',
    match: ['test', 'qa', 'verify', 'перевір', 'тест'],
    skills: ['qa', 'tester', 'test_runner', 'playwright_e2e'],
    keywords: ['qa', 'tester', 'quality']
  },
  {
    key: 'iot_source',
    label: 'IoT Signal Agent',
    match: ['iot', 'camera', 'microphone', 'sensor', 'signal', 'mqtt', 'rtsp', 'wifi', 'bluetooth', 'камер', 'мікроф', 'датчик', 'сигнал'],
    skills: ['iot_source', 'sensor_reading', 'audio_signal'],
    keywords: ['iot signal', 'iot source', 'sensor', 'camera']
  },
  {
    key: 'vision',
    label: 'Vision Gesture Agent',
    match: ['gesture', 'vision', 'image', 'video', 'recognition', 'жест', 'розпізн', 'відео', 'зображ'],
    skills: ['iot_source', 'computer_vision', 'gesture_recognition'],
    keywords: ['vision', 'gesture', 'camera']
  },
  {
    key: 'iot_control',
    label: 'IoT Device Manager',
    match: ['gate', 'device', 'relay', 'kettle', 'open', 'close', 'control', 'ворот', 'пристр', 'чайник', 'відкр', 'закр'],
    skills: ['device_control', 'iot_safety', 'api_connector'],
    keywords: ['iot device', 'device manager', 'control', 'gate']
  },
  {
    key: 'iot_safety',
    label: 'IoT Safety Supervisor',
    match: ['safety', 'approval', 'permission', 'physical', 'безпек', 'дозвіл', 'підтвердж'],
    skills: ['iot_safety', 'security', 'reviewer'],
    keywords: ['iot safety', 'safety supervisor', 'security']
  },
  {
    key: 'security',
    label: 'Security Reviewer',
    match: ['security', 'auth', 'token', 'secret', 'permission', 'безпек'],
    skills: ['security', 'code_review'],
    keywords: ['security', 'auditor']
  },
  {
    key: 'docs',
    label: 'Documentation Writer',
    match: ['readme', 'docs', 'documentation', 'інструкц', 'документ'],
    skills: ['docs', 'writer', 'summary'],
    keywords: ['documentation', 'docs', 'writer']
  },
  {
    key: 'final',
    label: 'Final Assembler',
    match: ['release', 'summary', 'final', 'результат'],
    skills: ['summary', 'executor', 'release_manager'],
    keywords: ['final', 'assembler', 'finalizer', 'release']
  }
];

const defaultOrder = ['requirements', 'scanner', 'iot_source', 'vision', 'architect', 'developer', 'qa', 'iot_safety', 'iot_control', 'security', 'docs', 'final'];

export function buildWorkflowFromPrompt({ prompt, agents = [], existingFlow = [], idFactory = defaultIdFactory, iotEnabled = true, providers = [] } = {}) {
  const text = String(prompt || '').trim();
  const lower = text.toLowerCase();
  const isIot = iotEnabled && ['iot', 'camera', 'microphone', 'sensor', 'gesture', 'gate', 'mqtt', 'rtsp', 'камер', 'датчик', 'жест', 'ворот'].some(token => lower.includes(token));
  const requested = isIot
    ? new Set(['requirements', 'iot_source', 'iot_safety', 'iot_control', 'final'])
    : new Set(['requirements', 'scanner', 'developer', 'qa', 'final']);
  for (const role of roleCatalog) {
    if (!iotEnabled && (role.key.startsWith('iot') || role.key === 'vision')) continue;
    if (role.match.some(token => lower.includes(token))) requested.add(role.key);
  }
  if (lower.includes('full') || lower.includes('production') || lower.includes('повн')) {
    for (const key of ['architect', 'security', 'docs']) requested.add(key);
  }
  if (isIot && ['gesture', 'vision', 'camera', 'жест', 'камер', 'розпізн'].some(token => lower.includes(token))) {
    requested.add('vision');
  }

  const createdAgents = [];
  const knownAgents = [...agents];
  const steps = [];
  const defaultProvider = providers.find(provider => provider.enabled !== false && provider.configured === true) || null;

  for (const key of defaultOrder) {
    if (!requested.has(key)) continue;
    const role = roleCatalog.find(item => item.key === key);
    const agent = findAgentForRole(knownAgents, role) || createAgentForRole(role, idFactory, defaultProvider);
    if (!knownAgents.some(item => item.id === agent.id)) {
      knownAgents.push(agent);
      createdAgents.push(agent);
    }
    steps.push({
      id: idFactory(`step-${key}`),
      roleKey: key,
      agentId: agent.id,
      note: noteForRole(role.key, text),
      cron: '',
      loops: role.key === 'developer' && lower.includes('iterate') ? 2 : 1,
      dependsOnPrevious: true
    });
  }

  const loopGroups = buildLoopGroups(steps, idFactory);
  return {
    agents: knownAgents,
    createdAgents,
    steps,
    loopGroups,
    summary: `${steps.length} steps planned${createdAgents.length ? `, ${createdAgents.length} new agent(s) created` : ''}.`,
    warning: defaultProvider ? '' : 'No configured workflow LLM provider found. Configure one in Settings before running.',
    canAppend: existingFlow.length > 0
  };
}

export function appendWorkflowSteps(existingFlow = [], plannedSteps = [], idFactory = defaultIdFactory) {
  return [
    ...existingFlow,
    ...plannedSteps.map(step => ({ ...step, id: idFactory(step.id || 'step') }))
  ];
}

function findAgentForRole(agents, role) {
  return agents.find(agent => {
    const haystack = [agent.id, agent.name, agent.role, ...(agent.skills || [])].join(' ').toLowerCase();
    return role.keywords.some(keyword => haystack.includes(keyword));
  });
}

function createAgentForRole(role, idFactory, provider) {
  return {
    id: idFactory(`ai-${role.key}`),
    name: role.label,
    role: `${role.label} generated by AI workflow assistant.`,
    provider: provider?.id || '',
    model: provider?.defaultModel || '',
    temperature: role.key === 'developer' ? 0.15 : 0.2,
    skills: role.skills,
    mcps: role.key === 'developer' || role.key === 'scanner'
      ? ['filesystem-mcp', 'git-mcp']
      : role.key.startsWith('iot') || role.key === 'vision'
        ? ['iot-gateway-mcp']
        : [],
    systemPrompt: `You are ${role.label}. Produce concrete deliverables for your workflow step.`
  };
}

function noteForRole(key, prompt) {
  const notes = {
    requirements: 'Convert the prompt into acceptance criteria and explicit deliverables.',
    scanner: 'Inspect the workspace and identify files, folders and risks related to the prompt.',
    architect: 'Design the minimal implementation structure, data flow and migration plan.',
    developer: 'Implement the requested change with complete file blocks and validation commands.',
    qa: 'Verify behavior, edge cases, test commands and defects.',
    iot_source: 'Normalize incoming IoT source metadata, transport, payload type and confidence.',
    vision: 'Recognize visual gestures/events and return intent, confidence and uncertainty.',
    iot_safety: 'Check approval, false-positive risk and safe fallback before physical actions.',
    iot_control: 'Prepare explicit dry-run device commands only for configured safe actions.',
    security: 'Review permissions, secrets, file writes and risky operations.',
    docs: 'Update usage notes, README text and operator instructions.',
    final: 'Assemble final result, changed files, risks and next actions.'
  };
  return `${notes[key] || 'Execute this workflow step.'}\n\nPrompt: ${prompt}`;
}

function buildLoopGroups(steps, idFactory) {
  const developerIndex = steps.findIndex(step => step.roleKey === 'developer');
  const qaIndex = steps.findIndex(step => step.roleKey === 'qa');
  if (developerIndex < 0 || qaIndex < 0 || qaIndex <= developerIndex) return [];
  return [{
    id: idFactory('ai-dev-qa-loop'),
    name: 'AI Dev QA loop',
    start: developerIndex,
    end: qaIndex,
    loops: 2
  }];
}

function defaultIdFactory(prefix = 'id') {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const workflowAssistantRoles = roleCatalog.map(role => ({ key: role.key, label: role.label }));
