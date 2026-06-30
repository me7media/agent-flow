import test from 'node:test';
import assert from 'node:assert/strict';

import { appendWorkflowSteps, buildWorkflowFromPrompt } from '../src/workflowAssistant.js';

const ids = () => {
  let count = 0;
  return prefix => `${prefix}-${++count}`;
};

test('builds a workflow from prompt using preset agents', () => {
  const idFactory = ids();
  const agents = [
    { id: 'requirements-analyst', name: 'Requirements Analyst', role: 'Scope', skills: ['research'] },
    { id: 'autonomous-developer-v2', name: 'Autonomous Developer v2', role: 'Developer', skills: ['developer'] },
    { id: 'qa-agent', name: 'QA Agent', role: 'Quality', skills: ['qa'] }
  ];
  const plan = buildWorkflowFromPrompt({ prompt: 'Build backend API with tests', agents, idFactory });
  assert.equal(plan.createdAgents.some(agent => agent.name === 'Developer Agent'), false);
  assert.ok(plan.steps.length >= 5);
  assert.ok(plan.steps.some(step => step.agentId === 'autonomous-developer-v2'));
  assert.ok(plan.loopGroups.length >= 1);
  assert.ok(plan.createdAgents.every(agent => agent.provider));
});

test('creates missing agents when presets are unavailable', () => {
  const plan = buildWorkflowFromPrompt({ prompt: 'Create secure production workflow with docs', agents: [], idFactory: ids() });
  assert.ok(plan.createdAgents.length >= 5);
  assert.ok(plan.agents.some(agent => agent.name === 'Security Reviewer'));
  assert.ok(plan.steps.some(step => step.note.includes('Prompt: Create secure production workflow with docs')));
});

test('appends planned steps without mutating existing flow', () => {
  const existing = [{ id: 'existing-step', agentId: 'agent-1' }];
  const planned = [{ id: 'planned-step', agentId: 'agent-2' }];
  const merged = appendWorkflowSteps(existing, planned, ids());
  assert.equal(existing.length, 1);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, 'existing-step');
  assert.notEqual(merged[1].id, planned[0].id);
});

test('plans IoT workflows with signal, safety and control agents', () => {
  const plan = buildWorkflowFromPrompt({
    prompt: 'IoT: розпізнати жест з камери та відкрити ворота після safety approval',
    agents: [],
    idFactory: ids()
  });
  const roleKeys = plan.steps.map(step => step.roleKey);
  assert.ok(roleKeys.includes('iot_source'));
  assert.ok(roleKeys.includes('vision'));
  assert.ok(roleKeys.includes('iot_safety'));
  assert.ok(roleKeys.includes('iot_control'));
  assert.equal(roleKeys.includes('developer'), false);
  assert.ok(plan.agents.some(agent => agent.skills.includes('device_control')));
});

test('does not plan IoT roles when IoT is disabled', () => {
  const plan = buildWorkflowFromPrompt({
    prompt: 'IoT: розпізнати жест з камери та відкрити ворота',
    agents: [],
    idFactory: ids(),
    iotEnabled: false
  });
  const roleKeys = plan.steps.map(step => step.roleKey);
  assert.equal(roleKeys.includes('iot_source'), false);
  assert.equal(roleKeys.includes('vision'), false);
  assert.equal(roleKeys.includes('iot_control'), false);
  assert.ok(roleKeys.includes('developer'));
});
