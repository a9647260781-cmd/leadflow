import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const workflowDirectory = dirname(fileURLToPath(import.meta.url));
const endpoint = 'http://backend:8000/api/internal/notifications/dispatch';
const credential = {
  id: 'leadflow-backend-dispatch-auth',
  name: 'LeadFlow Backend Dispatch Auth',
};

const specifications = [
  {
    filename: 'leadflow-new-lead-notifications.json',
    id: 'leadflow-new-lead-notifications-v1',
    name: 'LeadFlow — уведомления о новых заявках',
    kind: 'new_lead',
    schedule: { field: 'seconds', secondsInterval: 30 },
  },
  {
    filename: 'leadflow-reminder-notifications.json',
    id: 'leadflow-reminder-notifications-v1',
    name: 'LeadFlow — напоминания по заявкам',
    kind: 'reminder',
    schedule: { field: 'minutes', minutesInterval: 1 },
  },
];

const allowedNodeVersions = new Map([
  ['n8n-nodes-base.scheduleTrigger', 1.4],
  ['n8n-nodes-base.httpRequest', 4.5],
  ['n8n-nodes-base.if', 2.4],
  ['n8n-nodes-base.noOp', 1],
]);

function fail(filename, message) {
  throw new Error(`${filename}: ${message}`);
}

function check(condition, filename, message) {
  if (!condition) fail(filename, message);
}

function sameValue(actual, expected, filename, message) {
  try {
    assert.deepStrictEqual(actual, expected);
  } catch {
    fail(filename, `${message}; got ${JSON.stringify(actual)}`);
  }
}

function getOnlyNode(workflow, type, filename) {
  const nodes = workflow.nodes.filter((node) => node.type === type);
  check(nodes.length === 1, filename, `expected exactly one ${type} node`);
  return nodes[0];
}

function outgoingTargets(workflow, sourceName, outputIndex, filename) {
  const source = workflow.connections[sourceName];
  check(source && Array.isArray(source.main), filename, `missing connections for ${sourceName}`);
  const output = source.main[outputIndex];
  check(Array.isArray(output), filename, `missing output ${outputIndex} for ${sourceName}`);
  return output.map((connection) => connection.node);
}

function validateGraph(workflow, schedule, request, branch, filename) {
  const names = new Set(workflow.nodes.map((node) => node.name));
  check(names.size === workflow.nodes.length, filename, 'node names must be unique');
  check(new Set(workflow.nodes.map((node) => node.id)).size === workflow.nodes.length, filename, 'node ids must be unique');

  for (const [source, connectionSet] of Object.entries(workflow.connections)) {
    check(names.has(source), filename, `connection source does not exist: ${source}`);
    check(Array.isArray(connectionSet.main), filename, `connection main output is invalid: ${source}`);
    for (const output of connectionSet.main) {
      for (const connection of output ?? []) {
        check(connection.type === 'main' && connection.index === 0, filename, `invalid connection from ${source}`);
        check(names.has(connection.node), filename, `connection target does not exist: ${connection.node}`);
      }
    }
  }

  sameValue(outgoingTargets(workflow, schedule.name, 0, filename), [request.name], filename, 'schedule must call dispatcher');
  sameValue(outgoingTargets(workflow, request.name, 0, filename), [branch.name], filename, 'dispatcher must feed result branch');

  const branchOutputs = workflow.connections[branch.name]?.main;
  check(Array.isArray(branchOutputs) && branchOutputs.length === 2, filename, 'result branch must wire true and false outputs');
  check(branchOutputs.every((output) => Array.isArray(output) && output.length === 1), filename, 'each result branch must have one terminal');
  check(
    branchOutputs.flat().every((connection) => workflow.nodes.find((node) => node.name === connection.node)?.type === 'n8n-nodes-base.noOp'),
    filename,
    'result branches must terminate in No Operation nodes',
  );

  const reachable = new Set([schedule.name]);
  const queue = [schedule.name];
  while (queue.length > 0) {
    const source = queue.shift();
    for (const output of workflow.connections[source]?.main ?? []) {
      for (const connection of output ?? []) {
        if (!reachable.has(connection.node)) {
          reachable.add(connection.node);
          queue.push(connection.node);
        }
      }
    }
  }
  check(reachable.size === workflow.nodes.length, filename, 'all nodes must be reachable from the schedule trigger');
}

function validateSecrets(workflow, filename) {
  const serialized = JSON.stringify(workflow);
  check(!/\b\d{6,12}:[A-Za-z0-9_-]{30,}\b/.test(serialized), filename, 'Telegram bot token-shaped value is forbidden');
  check(!/Bearer\s+[A-Za-z0-9._~+/-]{12,}/i.test(serialized), filename, 'inline Bearer token is forbidden');

  for (const node of workflow.nodes) {
    const parameters = node.parameters ?? {};
    check(!Object.hasOwn(parameters, 'sendHeaders'), filename, `${node.name} must not define inline headers`);
    check(!Object.hasOwn(parameters, 'headerParameters'), filename, `${node.name} must not define inline headers`);
  }
}

async function validateWorkflow(specification) {
  const { filename } = specification;
  const raw = await readFile(join(workflowDirectory, filename), 'utf8');
  const workflow = JSON.parse(raw);

  check(workflow.id === specification.id, filename, 'unexpected workflow id');
  check(workflow.name === specification.name, filename, 'unexpected workflow name');
  check(workflow.active === false, filename, 'committed workflow must stay inactive');
  sameValue(workflow.pinData, {}, filename, 'pinData must be empty');
  check(Array.isArray(workflow.tags) && workflow.tags.length === 0, filename, 'tags must be empty');
  check(Array.isArray(workflow.nodes) && workflow.nodes.length === 5, filename, 'expected five nodes');

  sameValue(workflow.settings, {
    executionOrder: 'v1',
    timezone: 'Europe/Moscow',
    saveDataErrorExecution: 'all',
    saveDataSuccessExecution: 'none',
    saveManualExecutions: false,
    saveExecutionProgress: false,
    executionTimeout: 45,
    callerPolicy: 'none',
    redactionPolicy: 'all',
    availableInMCP: false,
  }, filename, 'workflow settings are not hardened as expected');

  for (const node of workflow.nodes) {
    check(allowedNodeVersions.has(node.type), filename, `unexpected node type ${node.type}`);
    check(node.typeVersion === allowedNodeVersions.get(node.type), filename, `unexpected ${node.type} version ${node.typeVersion}`);
    check(node.type !== 'n8n-nodes-base.telegram', filename, 'Telegram transport belongs to FastAPI, not n8n');
    check(node.type !== 'n8n-nodes-base.code', filename, 'Code nodes are not needed');
    check(node.disabled !== true, filename, `${node.name} must not be disabled inside the inactive workflow`);
  }

  const schedule = getOnlyNode(workflow, 'n8n-nodes-base.scheduleTrigger', filename);
  sameValue(schedule.parameters.rule?.interval, [specification.schedule], filename, 'unexpected schedule');
  check(schedule.parameters.misfirePolicy === 'skip', filename, 'missed runs must be skipped');
  check(schedule.parameters.misfireGraceSeconds === 0, filename, 'schedule must use the instance grace period');

  const request = getOnlyNode(workflow, 'n8n-nodes-base.httpRequest', filename);
  check(request.parameters.method === 'POST', filename, 'dispatcher request must use POST');
  check(request.parameters.url === endpoint, filename, 'dispatcher URL must use the Compose backend service');
  check(request.parameters.authentication === 'genericCredentialType', filename, 'request must use generic credentials');
  check(request.parameters.genericAuthType === 'httpHeaderAuth', filename, 'request must use HTTP Header Auth');
  sameValue(request.credentials?.httpHeaderAuth, credential, filename, 'unexpected Header Auth credential reference');
  check(request.parameters.sendBody === true, filename, 'dispatcher request must send JSON');
  check(request.parameters.contentType === 'json', filename, 'dispatcher content type must be JSON');
  check(request.parameters.specifyBody === 'json', filename, 'dispatcher body must be explicit JSON');
  sameValue(JSON.parse(request.parameters.jsonBody), { kind: specification.kind, limit: 1 }, filename, 'unexpected dispatcher body');
  check(request.parameters.options?.timeout === 30000, filename, 'request timeout must be 30 seconds');
  check(request.parameters.options?.response?.response?.responseFormat === 'json', filename, 'response must be parsed as JSON');
  check(request.parameters.options?.response?.response?.neverError !== true, filename, 'non-2xx responses must fail execution');
  check(request.continueOnFail !== true, filename, 'dispatcher errors must not continue');
  check(request.onError === undefined || request.onError === 'stopWorkflow', filename, 'dispatcher errors must stop the workflow');
  check(request.retryOnFail !== true, filename, 'n8n retries must stay disabled; backend owns durable retry state');

  const branch = getOnlyNode(workflow, 'n8n-nodes-base.if', filename);
  const condition = branch.parameters.conditions?.conditions?.[0];
  check(branch.parameters.conditions?.conditions?.length === 1, filename, 'result branch must have one condition');
  check(condition?.leftValue === '={{ $json.claimed }}', filename, 'result branch must inspect claimed count');
  check(condition?.rightValue === 0, filename, 'result branch threshold must be zero');
  sameValue(condition?.operator, { type: 'number', operation: 'gt' }, filename, 'result branch must test claimed > 0');

  validateGraph(workflow, schedule, request, branch, filename);
  validateSecrets(workflow, filename);
  return workflow;
}

const workflows = [];
for (const specification of specifications) workflows.push(await validateWorkflow(specification));
check(new Set(workflows.map((workflow) => workflow.id)).size === workflows.length, 'all workflows', 'workflow ids must be unique');
console.log(`Validated ${workflows.length} LeadFlow n8n workflows for n8n 2.44.6.`);
