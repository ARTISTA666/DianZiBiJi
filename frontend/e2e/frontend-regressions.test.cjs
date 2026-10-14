/* eslint-disable @typescript-eslint/no-require-imports */
// Run: node --test frontend/e2e/frontend-regressions.test.cjs
// Execute current TypeScript source with controlled HTTP/stores/hooks. No services or secrets.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');

function loadSource(relative, requireMock) {
  const source = fs.readFileSync(path.join(root, 'src', relative), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const sourceModule = { exports: {} };
  new Function('require', 'module', 'exports', compiled)(requireMock, sourceModule, sourceModule.exports);
  return sourceModule.exports;
}
function storeCreate(initializer) {
  if (!initializer) return storeCreate;
  let state;
  const set = patch => { state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) }; };
  const get = () => state;
  const store = selector => selector(state);
  store.getState = get;
  store.setState = set;
  state = initializer(set, get, store);
  return store;
}
function hooks() {
  const values = [], effectDeps = [], cleanups = [];
  let index = 0, effects = [];
  const changed = (a, b) => !a || !b || a.length !== b.length || a.some((v, i) => v !== b[i]);
  return {
    react: {
      useState(initial) {
        const i = index++;
        if (!(i in values)) values[i] = typeof initial === 'function' ? initial() : initial;
        return [values[i], v => { values[i] = typeof v === 'function' ? v(values[i]) : v; }];
      },
      useRef(initial) { const i = index++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
      useMemo(fn, deps) { const i = index++; if (!(i in values) || changed(values[i].deps, deps)) values[i] = { value: fn(), deps }; return values[i].value; },
      useCallback(fn, deps) { const i = index++; if (!(i in values) || changed(values[i].deps, deps)) values[i] = { value: fn, deps }; return values[i].value; },
      useEffect(fn, deps) { const i = index++; if (changed(effectDeps[i], deps)) { effectDeps[i] = deps; effects.push(() => { cleanups[i]?.(); cleanups[i] = fn(); }); } },
    },
    render(Component) { index = 0; effects = []; const tree = Component(); const todo = effects; effects = []; todo.forEach(fn => fn()); return tree; },
    unmount() { cleanups.forEach(fn => fn?.()); },
  };
}
const jsxRuntime = { jsx: (type, props) => ({ type, props: props || {} }), jsxs: (type, props) => ({ type, props: props || {} }), Fragment: 'Fragment' };
function findAll(tree, predicate) {
  if (!tree || typeof tree !== 'object') return [];
  const found = predicate(tree) ? [tree] : [];
  return found.concat([tree.props?.children].flat(Infinity).flatMap(child => findAll(child, predicate)));
}
const find = (tree, predicate) => findAll(tree, predicate)[0];
function baseMock(spec) {
  if (spec === 'react/jsx-runtime') return jsxRuntime;
  return new Proxy({}, { get: (_, name) => String(name) });
}
function globals() {
  const storage = new Map();
  const redirects = [];
  global.window = {
    location: { replace: url => redirects.push(url) }, addEventListener() {}, removeEventListener() {},
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
  };
  global.document = { addEventListener() {}, removeEventListener() {}, querySelector: () => null };
  global.sessionStorage = { setItem() {} };
  return { storage, redirects };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const utilityMock = { getErrorMessage: (e, fallback) => e?.message || fallback, formatFileSize: () => '' };
function loadApi(auth) {
  return loadSource('lib/api.ts', spec => spec === 'sonner' ? { toast: { error() {} } } : spec === '@/stores/auth-store' ? auth : baseMock(spec));
}
const image = { id: 99, project_id: 1, original_filename: 'image.png', mime_type: 'image/png', file_category: 'knowledge_document', status: 'uploaded', knowledge_sync_status: 'pending_review', file_size: 1, note_id: null };

test('R04: real SSE subscription delivers expiry and disposes its native listener', t => {
  const OriginalEventSource = global.EventSource;
  t.after(() => { global.EventSource = OriginalEventSource; });
  const sources = [];
  global.EventSource = class extends EventTarget {
    constructor(url, options) { super(); this.url = url; this.options = options; this.listeners = new Set(); sources.push(this); }
    addEventListener(type, listener) { this.listeners.add(type); super.addEventListener(type, listener); }
    removeEventListener(type, listener) { this.listeners.delete(type); super.removeEventListener(type, listener); }
    close() { this.closed = true; }
  };
  const api = loadApi({}), received = []; let errors = 0;
  const unsubscribe = api.subscribeAgentSessionEvents('test-session', 'session-A', event => received.push(event), () => { errors++; });
  const source = sources[0];
  assert.ok(source.url.endsWith('/api/agent/sessions/session-A/events'));
  assert.deepEqual(source.options, { withCredentials: true });
  const data = { action_id: 'action-A', turn_id: 'turn-A', terminal: true };
  const expiry = () => new MessageEvent('confirmation.expired', { data: JSON.stringify(data), lastEventId: '42' });
  source.dispatchEvent(expiry());
  assert.deepEqual(received, [{ id: '42', event: 'confirmation.expired', data }]);
  source.onerror(); assert.equal(errors, 1);
  unsubscribe(); assert.equal(source.closed, true); assert.equal(source.listeners.size, 0);
  source.dispatchEvent(expiry()); assert.equal(received.length, 1);
});

test('R07: invalid login rejects locally without logout or redirect', async () => {
  const { redirects } = globals();
  let auth;
  global.fetch = async () => ({ ok: false, status: 401, text: async () => JSON.stringify({ detail: 'Invalid credentials' }), headers: { get: () => null } });
  const api = loadApi(new Proxy({}, { get: (_, key) => auth[key] }));
  auth = loadSource('stores/auth-store.ts', spec => spec === 'zustand' ? { create: storeCreate } : spec === '@/lib/api' ? api : spec === './project' ? { useProjectStore: { getState: () => ({ resetProjectState() {} }) } } : spec === '@/lib/utils' ? utilityMock : baseMock(spec));
  await assert.rejects(auth.useAuthStore.getState().login('test-user', 'wrong-password'), /Invalid credentials/);
  assert.equal(auth.useAuthStore.getState().error, 'Invalid credentials');
  assert.deepEqual(redirects, []);
});

function agentFixture(apiOverrides = {}) {
  globals();
  process.env.NEXT_PUBLIC_NEW_AGENT_ENABLED = 'true';
  const h = hooks();
  const authState = { token: 'test-session', user: { id: 1 } };
  const state = { selectedProjectId: 1, selectedProject: { id: 1 }, projects: [], notes: [], files: [], members: [], ragStatus: null };
  const sessionCalls = [], turnCalls = [], subscriptions = [];
  const useAuthStore = selector => selector(authState); useAuthStore.getState = () => authState;
  const useProjectStore = selector => selector(state); useProjectStore.getState = () => state;
  const snapshot = sid => ({ session: { id: sid, provider: 'test', model_name: 'test' }, messages: [{ role: 'assistant', content: 'RESULT-' + sid }], steps: [], pending_actions: [] });
  const apiMock = {
    ApiRequestError: class extends Error {}, getProjectRagStatus: async () => ({ initialized: false }),
    createAgentSession: async (_, pid) => { sessionCalls.push(pid); return { session: { id: 'session-' + pid } }; },
    createAgentTurn: async (_, sid, text) => { turnCalls.push({ sid, text }); return snapshot(sid); },
    subscribeAgentSessionEvents: (_, sid, onEvent, onError) => { const sub = { sid, onEvent, onError, closed: false }; subscriptions.push(sub); return () => { sub.closed = true; }; },
    ...apiOverrides,
  };
  const component = loadSource('components/shared/AgentAssistant.tsx', spec => spec === 'react' ? h.react : spec === 'next/navigation' ? { usePathname: () => '/projects/' + state.selectedProjectId, useRouter: () => ({}) } : spec === '@/lib/api' ? apiMock : spec === '@/stores' ? { useAuthStore, useProjectStore } : spec === './agent-assistant/intents' ? {
    projectIdFromPath: p => Number(p.split('/')[2]), initialMessages: [{ id: 'initial', role: 'assistant', content: 'initial' }], redactSensitiveText: t => t, formatAgentBudget: () => '', agentErrorMessage: e => e.message,
  } : spec === './agent-assistant/commands' ? { runAgentCommands: async () => {} } : baseMock(spec)).AgentAssistant;
  let tree = h.render(component);
  find(tree, e => e.props['aria-label'] === '打开 Agent 助手').props.onClick();
  const render = () => { tree = h.render(component); return tree; }; render();
  const send = text => { find(tree, e => e.props['aria-label'] === '输入 Agent 指令').props.onChange({ target: { value: text } }); render(); find(tree, e => e.type === 'form').props.onSubmit({ preventDefault() {} }); return tick(); };
  const changeProject = id => { state.selectedProjectId = id; state.selectedProject = { id }; render(); render(); };
  return { render, send, changeProject, authState, state, subscriptions, sessionCalls, turnCalls, snapshot, h };
}
test('R01: late session creation cannot start a turn or poison the next project session', async () => {
  const pending = deferred();
  const f = agentFixture({ createAgentSession: (_, pid) => { f.sessionCalls.push(pid); return pid === 1 ? pending.promise : Promise.resolve({ session: { id: 'session-2' } }); } });
  const first = f.send('in project A'); f.changeProject(2);
  pending.resolve({ session: { id: 'session-1' } }); await first;
  f.render(); await f.send('in project B');
  assert.deepEqual(f.sessionCalls, [1, 2]);
  assert.deepEqual(f.turnCalls, [{ sid: 'session-2', text: 'in project B' }]);
});
test('R01: late turn, plan and SSE results are discarded after project/user changes', async () => {
  const pending = deferred();
  const f = agentFixture({ createAgentTurn: () => pending.promise });
  const first = f.send('old request'); await tick();
  const oldStream = f.subscriptions[0]; f.changeProject(2);
  pending.resolve({ plan_hash: 'old-hash', turn_id: 'old-turn', plan: { text: 'OLD-PLAN' }, budget: {} }); await first;
  oldStream.onEvent({ id: 'old-event', event: 'tool.started', data: { tool: 'OLD-TOOL' } }); oldStream.onError();
  let tree = f.render();
  assert.equal(JSON.stringify(tree).includes('OLD-PLAN'), false);
  assert.equal(JSON.stringify(tree).includes('OLD-TOOL'), false);
  assert.equal(oldStream.closed, true);
  f.authState.user = null; f.authState.token = null; f.render();
  f.authState.user = { id: 2 }; f.authState.token = 'new-session'; tree = f.render(); f.render();
  assert.equal(JSON.stringify(tree).includes('OLD-PLAN'), false);
});
test('R01: logout invalidates a session request before the component rerenders', async () => {
  const pending = deferred();
  const f = agentFixture({ createAgentSession: () => pending.promise });
  f.send('old identity request');
  f.authState.user = null; f.authState.token = null;
  pending.resolve({ session: { id: 'old-identity-session' } }); await tick();
  assert.deepEqual(f.turnCalls, []); assert.deepEqual(f.subscriptions, []);
  assert.equal(f.render(), null);
});
test('R01: an in-flight confirmation cannot render into the next identity with the same session id', async () => {
  const pending = deferred();
  const f = agentFixture({
    createAgentTurn: async (_, sid) => ({ ...f.snapshot(sid), pending_actions: [{ id: 'pending-1', status: 'pending', tool_name: 'OLD-WRITE', arguments_summary: 'old action' }] }),
    approveAgentPendingAction: () => pending.promise,
  });
  await f.send('prepare action'); f.render(); await f.send('确认');
  const oldStream = f.subscriptions[0];
  f.authState.user = { id: 2 }; f.authState.token = 'new-session'; f.render(); f.render();
  pending.resolve({ execution_status: 'completed' }); await tick();
  oldStream.onEvent({ id: 'old-confirmation', event: 'confirmation.completed', data: { action_id: 'pending-1' } });
  const tree = f.render(); assert.equal(JSON.stringify(tree).includes('OLD-WRITE'), false);
  assert.equal(JSON.stringify(tree).includes('已确认执行完成'), false);
  assert.equal(oldStream.closed, true);
});
for (const action of ['确认', '取消']) {
  test(`R01: late deep-plan ${action === '确认' ? 'start' : 'cancel'} failure is discarded`, async () => {
    const pending = deferred();
    const f = agentFixture({
      createAgentTurn: async () => ({ plan_hash: 'hash', turn_id: 'turn-1', plan: { text: 'PLAN-A' }, budget: {} }),
      startAgentTurn: () => pending.promise, cancelAgentTurn: () => pending.promise,
    });
    await f.send('prepare plan'); f.render(); await f.send(action); f.changeProject(2);
    pending.reject(new Error('OLD-PLAN-FAILURE')); await tick();
    const tree = f.render(); assert.equal(JSON.stringify(tree).includes('OLD-PLAN-FAILURE'), false);
    assert.equal(JSON.stringify(tree).includes('PLAN-A'), false);
    assert.equal(find(tree, e => e.props['aria-label'] === '输入 Agent 指令').props.disabled, false);
  });
}
for (const firstAction of ['确认', '取消']) {
  test(`R04: two pending actions remain actionable after the first ${firstAction}`, async () => {
    const approved = [], rejected = [];
    const f = agentFixture({
      createAgentTurn: async (_, sid) => ({ ...f.snapshot(sid), pending_actions: [
        { id: 'action-A', status: 'pending', tool_name: 'write-A', arguments_summary: 'A' },
        { id: 'action-B', status: 'pending', tool_name: 'write-B', arguments_summary: 'B' },
      ] }),
      approveAgentPendingAction: async (_, id) => { approved.push(id); return { execution_status: 'completed' }; },
      rejectAgentPendingAction: async (_, id) => { rejected.push(id); },
    });
    await f.send('prepare both'); f.render(); await f.send(firstAction); f.render(); await f.send('确认');
    assert.deepEqual(approved, firstAction === '确认' ? ['action-A', 'action-B'] : ['action-B']);
    assert.deepEqual(rejected, firstAction === '取消' ? ['action-A'] : []);
    assert.equal(f.sessionCalls.length, 1);
  });
}
for (const eventName of ['confirmation.completed', 'confirmation.rejected', 'confirmation.expired']) {
  test(`R04: ${eventName} only removes its own action and keeps the stream active`, async () => {
    const approved = [];
    const f = agentFixture({
      createAgentTurn: async (_, sid) => ({ ...f.snapshot(sid), pending_actions: [
        { id: 'action-A', status: 'pending', tool_name: 'write-A', arguments_summary: 'A' },
        { id: 'action-B', status: 'pending', tool_name: 'write-B', arguments_summary: 'B' },
      ] }),
      approveAgentPendingAction: async (_, id) => { approved.push(id); return { execution_status: 'completed' }; },
    });
    await f.send('prepare both');
    const stream = f.subscriptions[0];
    stream.onEvent({ id: 'required-A', event: 'confirmation.required', data: { action_id: 'action-A' } });
    stream.onEvent({ id: 'required-B', event: 'confirmation.required', data: { action_id: 'action-B' } });
    stream.onEvent({ id: 'settled-A', event: eventName, data: { action_id: 'action-A', terminal: false } });
    stream.onError(); let tree = f.render();
    assert.ok(JSON.stringify(tree).includes('事件连接中断，正在重连'));
    await f.send('确认'); assert.deepEqual(approved, ['action-B']);
    stream.onEvent({ id: 'settled-B', event: 'confirmation.completed', data: { action_id: 'action-B', terminal: true } });
    stream.onError(); tree = f.render();
    assert.equal(JSON.stringify(tree).includes('事件连接中断，正在重连'), false);
  });
}
function confirmationFailureFixture(overrides = {}) {
  let turns = 0;
  const f = agentFixture({
    createAgentTurn: async (_, sid) => { turns++; return { ...f.snapshot(sid), pending_actions: turns === 1 ? [
      { id: 'action-A', status: 'pending', tool_name: 'write-A', arguments_summary: 'A' },
      { id: 'action-B', status: 'pending', tool_name: 'write-B', arguments_summary: 'B' },
    ] : [] }; },
    ...overrides,
  });
  return { ...f, turns: () => turns };
}
for (const decision of ['确认', '取消']) {
  for (const failure of ['network', '503']) {
    test(`R04 retry: ${decision} ${failure} failure retains A for explicit retry before B`, async () => {
      const attempts = [], ApiRequestError = loadApi({}).ApiRequestError;
      const decide = async (_, id) => {
        attempts.push({ decision, id });
        if (attempts.length === 1) throw failure === '503' ? new ApiRequestError('Service unavailable', 503, null) : new TypeError('Failed to fetch');
        return { execution_status: 'completed' };
      };
      const f = confirmationFailureFixture({
        ApiRequestError,
        approveAgentPendingAction: decision === '确认' ? decide : async (_, id) => { attempts.push({ decision: '确认', id }); return { execution_status: 'completed' }; },
        rejectAgentPendingAction: decide,
      });
      await f.send('prepare both'); f.render(); await f.send(decision); f.render();
      assert.equal(attempts.length, 1); // No automatic retry.
      await f.send(decision); f.render(); await f.send('确认'); f.render();
      assert.deepEqual(attempts, [{ decision, id: 'action-A' }, { decision, id: 'action-A' }, { decision: '确认', id: 'action-B' }]);
      assert.equal(f.turns(), 1);
      await f.send('a new request'); assert.equal(f.turns(), 2);
    });
  }
}
for (const status of [409, 403]) {
  test(`R04 retry: terminal ${status} refusal does not restore A ahead of B`, async () => {
    const attempts = [], ApiRequestError = loadApi({}).ApiRequestError;
    const f = confirmationFailureFixture({ ApiRequestError,
      approveAgentPendingAction: async (_, id) => { attempts.push(id); if (id === 'action-A') throw new ApiRequestError('Action unavailable', status, null); return { execution_status: 'completed' }; },
    });
    await f.send('prepare both'); f.render(); await f.send('确认'); f.render(); await f.send('确认'); f.render();
    assert.deepEqual(attempts, ['action-A', 'action-B']);
    await f.send('a new request'); assert.equal(f.turns(), 2);
  });
}
for (const settledEvent of ['confirmation.completed', 'confirmation.rejected', 'confirmation.expired']) {
  test(`R04 retry: ${settledEvent} before a late transport error prevents restoring settled A`, async () => {
    const pending = deferred(), attempts = [];
    const f = confirmationFailureFixture({ approveAgentPendingAction: async (_, id) => { attempts.push(id); return id === 'action-A' ? pending.promise : { execution_status: 'completed' }; } });
    await f.send('prepare both'); f.render(); await f.send('确认');
    f.subscriptions[0].onEvent({ id: 'settled-A', event: settledEvent, data: { action_id: 'action-A', terminal: false } });
    pending.reject(new TypeError('Failed to fetch')); await tick(); f.render(); await f.send('确认'); f.render();
    assert.deepEqual(attempts, ['action-A', 'action-B']);
    await f.send('a new request'); assert.equal(f.turns(), 2);
  });
}

test('R08: note id survives partial image upload failure; retry only uploads failed files', async () => {
  globals(); const h = hooks(); let createCount = 0, refreshCount = 0;
  const uploads = [];
  const state = { token: 'test-session', user: { id: 1, role: 'super_admin' }, members: [], selectedProjectId: 1, selectedProject: { id: 1 }, notes: [], notesTotal: 0, templates: [{ id: 1, experiment_type: 'test', schema_json: { fields: [] } }], busy: false,
    loadNotesPaginated: async () => { refreshCount++; }, createNote: async () => ({ id: ++createCount }), updateNote: async () => ({}) };
  const useAuthStore = selector => selector(state); useAuthStore.getState = () => state;
  const useProjectStore = selector => selector(state); useProjectStore.getState = () => state;
  const page = loadSource('app/(dashboard)/projects/[id]/page.tsx', spec => spec === 'react' ? h.react : spec === 'next/navigation' ? { useParams: () => ({ id: '1' }) } : spec === '@/stores' ? { useAuthStore, useProjectStore } : spec === '@/lib/api' ? { uploadFile: async (_, __, file, noteId) => { uploads.push({ name: file.name, noteId }); if (file.name === 'failed.png' && uploads.filter(x => x.name === file.name).length === 1) throw new Error('image upload failed'); return {}; } } : spec === '@/lib/utils' ? utilityMock : spec === '@/hooks/use-confirm-dialog' ? { useConfirmDialog: () => ({ confirm() {}, ConfirmDialog: null }) } : spec === '@/hooks/use-action-feedback' ? { useActionFeedback: () => ({ success() {} }) } : baseMock(spec)).default;
  let tree = h.render(page); find(tree, e => e.type === 'NoteFilters').props.onNewNote(); tree = h.render(page);
  let form = find(tree, e => e.type === 'NoteFormDialog'); form.props.onFormChange({ ...form.props.form, title: 'note' }); form.props.onPendingImagesChange([{ name: 'success.png' }, { name: 'failed.png' }]); tree = h.render(page);
  await find(tree, e => e.type === 'NoteFormDialog').props.onSave({ preventDefault() {} }); tree = h.render(page);
  form = find(tree, e => e.type === 'NoteFormDialog');
  assert.equal(form.props.editingNote, 1);
  assert.deepEqual(form.props.pendingImages.map(f => f.name), ['failed.png']);
  assert.equal(form.props.open, true); assert.match(form.props.error, /image upload failed/);
  assert.ok(refreshCount >= 2);
  await form.props.onSave({ preventDefault() {} });
  assert.equal(createCount, 1);
  assert.deepEqual(uploads, [{ name: 'success.png', noteId: 1 }, { name: 'failed.png', noteId: 1 }, { name: 'failed.png', noteId: 1 }]);
});

function notesFixture(options = {}) {
  const { storage } = globals(), h = hooks(), view = { projectId: 1 };
  const created = [], updated = [], uploaded = [], refreshed = [], successes = [];
  const state = { token: 'identity-A', user: { id: 1, role: 'super_admin' }, members: [], selectedProjectId: 1, selectedProject: { id: 1 }, notes: [], notesTotal: 0, templates: [], busy: false,
    loadNotesPaginated: async (token, projectId) => { refreshed.push({ token, projectId }); },
    createNote: async (token, data) => { created.push({ token, ...data }); return options.create ? options.create(token, data) : { id: created.length === 1 ? 101 : 202 }; },
    updateNote: async (token, id) => { updated.push({ token, id }); return {}; },
  };
  const useAuthStore = selector => selector(state); useAuthStore.getState = () => state;
  const useProjectStore = selector => selector(state); useProjectStore.getState = () => state;
  const page = loadSource('app/(dashboard)/projects/[id]/page.tsx', spec => spec === 'react' ? h.react : spec === 'next/navigation' ? { useParams: () => ({ id: String(view.projectId) }) } : spec === '@/stores' ? { useAuthStore, useProjectStore } : spec === '@/lib/api' ? {
    uploadFile: async (token, projectId, file, noteId) => { uploaded.push({ token, projectId, name: file.name, noteId }); return options.upload ? options.upload(file) : {}; },
  } : spec === '@/lib/utils' ? utilityMock : spec === '@/hooks/use-confirm-dialog' ? { useConfirmDialog: () => ({ confirm() {}, ConfirmDialog: null }) } : spec === '@/hooks/use-action-feedback' ? { useActionFeedback: () => ({ success: message => successes.push(message) }) } : baseMock(spec)).default;
  let tree;
  const render = () => { tree = h.render(page); return tree; }; render();
  const form = () => find(tree, e => e.type === 'NoteFormDialog').props;
  const open = (title, images = []) => { find(tree, e => e.type === 'NoteFilters').props.onNewNote(); render(); form().onFormChange({ ...form().form, title }); form().onPendingImagesChange(images); render(); };
  const change = kind => {
    if (kind === 'project') { view.projectId = 2; state.selectedProjectId = 2; state.selectedProject = { id: 2 }; }
    else { state.token = 'identity-B'; state.user = { id: 2, role: 'super_admin' }; }
    render(); render();
  };
  return { h, state, view, storage, created, updated, uploaded, refreshed, successes, render, form, open, change, save: () => form().onSave({ preventDefault() {} }) };
}
for (const context of ['project', 'identity']) {
  test(`R16: late note creation cannot upload attachments or overwrite a new ${context} draft`, async () => {
    const oldCreation = deferred();
    const f = notesFixture({ create: (_, data) => data.title === 'A draft' ? oldCreation.promise : Promise.resolve({ id: 202 }), upload: file => file.name === 'A.png' ? Promise.reject(new Error('old attachment failure')) : Promise.resolve({}) });
    f.open('A draft', [{ name: 'A.png' }]); const oldSave = f.save();
    f.change(context); f.open('B draft', [{ name: 'B.png' }]);
    const draftKey = `eln.note-draft:${f.view.projectId}:new`, draft = f.storage.get(draftKey);
    oldCreation.resolve({ id: 101 }); await oldSave; f.render();
    assert.deepEqual(f.uploaded, []);
    assert.equal(f.form().editingNote, null); assert.equal(f.form().form.title, 'B draft');
    assert.equal(f.form().error, ''); assert.equal(f.form().open, true);
    assert.equal(f.storage.get(draftKey), draft);
    await f.save(); f.render();
    assert.equal(f.created.length, 2); assert.deepEqual(f.updated, []);
    assert.deepEqual(f.uploaded, [{ token: f.state.token, projectId: f.view.projectId, name: 'B.png', noteId: 202 }]);
  });
  test(`R16: an old attachment failure cannot alter a new ${context} save or unlock it`, async () => {
    const oldUpload = deferred(), newUpload = deferred();
    const f = notesFixture({ upload: file => file.name === 'A.png' ? oldUpload.promise : newUpload.promise });
    f.open('A draft', [{ name: 'A.png' }]); const oldSave = f.save(); await tick();
    f.change(context); f.open('B draft', [{ name: 'B.png' }]); const newSave = f.save(); await tick(); f.render();
    const draftKey = `eln.note-draft:${f.view.projectId}:202`, draft = f.storage.get(draftKey);
    oldUpload.reject(new Error('old attachment failure')); await oldSave; f.render();
    assert.equal(f.form().editingNote, 202); assert.equal(f.form().busy, true); assert.equal(f.form().error, '');
    assert.deepEqual(f.form().pendingImages.map(file => file.name), ['B.png']);
    assert.equal(f.storage.get(draftKey), draft); assert.deepEqual(f.successes, []);
    newUpload.resolve({}); await newSave; f.render();
    assert.equal(f.form().open, false); assert.equal(f.form().busy, false); assert.equal(f.successes.length, 1);
  });
}
for (const boundary of ['unmount', 'logout before rerender']) {
  test(`R16: ${boundary} stops a created note from starting attachment uploads`, async () => {
    const pending = deferred(), f = notesFixture({ create: () => pending.promise });
    f.open('A draft', [{ name: 'A.png' }]); const saving = f.save(), refreshCount = f.refreshed.length;
    if (boundary === 'unmount') f.h.unmount(); else { f.state.token = null; f.state.user = null; }
    pending.resolve({ id: 101 }); await saving;
    assert.deepEqual(f.uploaded, []); assert.equal(f.refreshed.length, refreshCount);
    assert.equal(f.storage.has('eln.note-draft:1:101'), false); assert.deepEqual(f.successes, []);
  });
}
test('R16: closing and reopening a form isolates its in-flight save in the same project', async () => {
  const oldCreation = deferred(), newUpload = deferred();
  const f = notesFixture({ create: (_, data) => data.title === 'A draft' ? oldCreation.promise : Promise.resolve({ id: 202 }), upload: file => file.name === 'B.png' ? newUpload.promise : Promise.reject(new Error('old attachment failure')) });
  f.open('A draft', [{ name: 'A.png' }]); const oldSave = f.save();
  f.form().onOpenChange(false); f.render(); f.open('B draft', [{ name: 'B.png' }]);
  const newSave = f.save(); await tick();
  oldCreation.resolve({ id: 101 }); await oldSave; f.render();
  assert.deepEqual(f.uploaded.map(file => file.name), ['B.png']);
  assert.equal(f.form().editingNote, 202); assert.equal(f.form().busy, true); assert.equal(f.form().error, '');
  newUpload.resolve({}); await newSave; f.render();
  assert.equal(f.form().open, false); assert.deepEqual(f.updated, []);
});

function dataFixture(files = [image], api = {}) {
  globals(); const h = hooks();
  const state = { token: 'test-session', user: { id: 2, role: 'member' }, files, filesTotal: files.length, filesComplete: true, notes: [], members: [{ user_id: 2, can_read: true, can_review: true, can_write: false, can_manage: false }], selectedProject: { id: 1, owner_user_id: 1 }, selectedProjectId: 1, busy: false, loadDataTabData: async () => {} };
  const useProjectStore = selector => selector(state); useProjectStore.getState = () => state; useProjectStore.setState = patch => Object.assign(state, patch);
  const page = loadSource('app/(dashboard)/projects/[id]/data/page.tsx', spec => spec === 'react' ? h.react : spec === 'next/navigation' ? { useParams: () => ({ id: '1' }) } : spec === '@/stores' ? { useAuthStore: selector => selector(state), useProjectStore } : spec === '@/lib/api' ? api : spec === '@/lib/utils' ? utilityMock : spec === '@/components/constants' ? { knowledgeSyncText: {} } : spec === '@/hooks/use-confirm-dialog' ? { useConfirmDialog: () => ({ confirm() {}, ConfirmDialog: null }) } : spec === '@/hooks/use-action-feedback' ? { useActionFeedback: () => ({ success() {}, error() {} }) } : baseMock(spec)).default;
  return { render: () => h.render(page), state };
}
test('R09: reader/reviewer can view and correct existing OCR without write', async () => {
  let extracted = 0, confirmed = 0;
  const f = dataFixture([image], { getLatestOcrResult: async () => ({ file_id: 99, ocr_result_id: 5, extracted_text: 'existing text' }), extractOcr: async () => { extracted++; }, confirmOcrResult: async () => { confirmed++; }, getAllProjectFiles: async () => ({ items: [image], total: 1 }) });
  let tree = f.render();
  const button = find(tree, e => e.props['aria-label'] === '提取文本 image.png'); assert.ok(button);
  await button.props.onClick(); tree = f.render();
  const dialog = find(tree, e => e.type === 'OcrDialog'); assert.equal(dialog.props.draft, 'existing text'); assert.equal(dialog.props.canReview, true);
  await dialog.props.onConfirm(); assert.equal(confirmed, 1); assert.equal(extracted, 0);
});
test('R09: reviewer cannot extract a missing OCR result', async () => {
  let extracted = 0;
  class ApiRequestError extends Error { constructor() { super('not found'); this.status = 404; } }
  const f = dataFixture([image], { ApiRequestError, getLatestOcrResult: async () => { throw new ApiRequestError(); }, extractOcr: async () => { extracted++; } });
  const button = find(f.render(), e => e.props['aria-label'] === '提取文本 image.png'); assert.ok(button);
  await button.props.onClick(); const tree = f.render(); assert.equal(extracted, 0); assert.match(find(tree, e => e.type === 'ErrorBanner').props.message, /写入权限/);
});
test('R10: all file pages are collected, deduplicated, and empty pages terminate', async () => {
  globals(); const urls = []; const api = loadApi({});
  global.fetch = async url => { urls.push(url); const skip = Number(new URL(url).searchParams.get('skip')); return { ok: true, status: 200, json: async () => skip === 0 ? { items: [{ ...image, id: 3 }, { ...image, id: 2 }], total: 3, skip: 0, limit: 2 } : { items: [{ ...image, id: 2 }, { ...image, id: 1 }], total: 3, skip: 2, limit: 2 } }; };
  const result = await api.getAllProjectFiles('test-session', 1);
  assert.deepEqual(result.items.map(f => f.id), [3, 2, 1]); assert.equal(result.total, 3); assert.equal(urls.length, 2);
  let calls = 0;
  global.fetch = async () => ({ ok: true, status: 200, json: async () => { calls++; return { items: [], total: 100, skip: 0, limit: 200 }; } });
  await api.getAllProjectFiles('test-session', 1); assert.equal(calls, 1);
});
test('R10: a project/identity change discards a pending file page and stops fetching', async () => {
  globals(); const api = loadApi({}); const page = deferred(); let current = true, calls = 0;
  global.fetch = async () => { calls++; return { ok: true, status: 200, json: () => page.promise }; };
  const result = api.getAllProjectFiles('test-session', 1, () => current);
  current = false; page.resolve({ items: [image], total: 250, skip: 0, limit: 200 });
  await assert.rejects(result, { name: 'AbortError' }); assert.equal(calls, 1);
});
test('R10: file UI exposes item 51 and approvals include the oldest pending file', () => {
  const files = Array.from({ length: 51 }, (_, i) => ({ ...image, id: 51 - i, status: i === 50 ? 'uploaded' : 'approved' }));
  const f = dataFixture(files); let tree = f.render();
  assert.equal(findAll(tree, e => String(e.props['data-testid'] || '').startsWith('file-row-')).length, 50);
  const pagination = find(tree, e => e.type === 'PagePagination'); assert.ok(pagination); assert.equal(pagination.props.total, 51);
  pagination.props.onNext(); tree = f.render(); assert.ok(find(tree, e => e.props['data-testid'] === 'file-row-1'));
  const h = hooks(); const state = { token: 'test-session', pendingNotes: [], members: [], files, filesTotal: 51, filesComplete: true, busy: false, loadBaseProjectData: async () => {} };
  const page = loadSource('app/(dashboard)/projects/[id]/approvals/page.tsx', spec => spec === 'react' ? h.react : spec === 'next/navigation' ? { useParams: () => ({ id: '1' }), useRouter: () => ({ push() {} }) } : spec === '@/stores' ? { useAuthStore: selector => selector(state), useProjectStore: selector => selector(state) } : spec === '@/lib/utils' ? utilityMock : spec === '@/hooks/use-action-feedback' ? { useActionFeedback: () => ({ success() {}, error() {} }) } : spec === 'sonner' ? { toast: { info() {} } } : baseMock(spec)).default;
  tree = h.render(page); assert.equal(find(tree, e => e.props.children === '所有笔记和资料已审批完毕'), undefined);
  assert.ok(JSON.stringify(tree).includes('image.png'));
  state.files = []; state.filesComplete = false;
  tree = h.render(page); assert.equal(/所有笔记(?:和资料)?已审批完毕/.test(JSON.stringify(tree)), false);
  assert.ok(find(tree, e => e.props.role === 'alert'));
});
test('R06: knowledge format validation rejects Office, including renamed gzip, and preserves attachment choice', () => {
  const api = loadSource('lib/knowledge-files.ts', baseMock);
  for (const name of ['document.docx', 'data.xlsx', 'slides.pptx', 'document.docx.gz', 'data.gz']) {
    assert.equal(api.isSupportedKnowledgeFile({ name, type: name.endsWith('.gz') ? 'application/gzip' : 'application/octet-stream' }), false, name);
  }
  for (const name of ['document.pdf', 'image.png', 'data.csv', 'data.soft', 'data.soft.gz', 'protocol.md', 'data.csv.gz']) {
    assert.equal(api.isSupportedKnowledgeFile({ name, type: 'application/octet-stream' }), true, name);
  }
  assert.equal(api.isSupportedKnowledgeFile({ name: 'image.png', type: 'application/zip' }), false);
  assert.equal(api.KNOWLEDGE_DOCUMENT_ACCEPT.includes('.docx'), false);
  assert.equal(api.NOTE_ATTACHMENT_ACCEPT.includes('.docx'), true);
});
test('R06: a committed approval survives metadata refresh failure', async () => {
  const reviewed = { ...image, status: 'approved', knowledge_sync_status: 'failed', knowledge_sync_message: 'index unavailable' };
  let state = { selectedProjectId: 1, files: [image], filesComplete: true, projectDataErrors: [] };
  const set = patch => { state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) }; };
  const slice = loadSource('stores/project/file-slice.ts', spec => spec === '@/lib/api' ? { reviewFile: async () => reviewed, getAllProjectFiles: async () => { throw new Error('refresh unavailable'); } } : spec === './request-epoch' ? { epochs: { projectData: 1 }, isCurrentProjectRequest: (get, pid, epoch) => get().selectedProjectId === pid && epoch === 1 } : baseMock(spec)).createFileSlice(set, () => state);
  assert.equal(await slice.reviewFile('test-session', 99, 'approve', ''), reviewed);
  assert.equal(state.files[0].status, 'approved'); assert.equal(state.filesComplete, false);
  assert.deepEqual(state.projectDataErrors, ['项目资料']);
});
test('R06: approved-but-failed sync is visible and retries sync without approving twice', async () => {
  const f = dataFixture(); let reviews = 0, syncs = 0;
  f.state.members[0].can_manage = true;
  f.state.invalidateCache = () => {};
  f.state.reviewFile = async () => { reviews++; const file = { ...image, status: 'approved', knowledge_sync_status: 'failed', knowledge_sync_message: 'index unavailable' }; f.state.files = [file]; return file; };
  f.state.syncFileToRag = async () => { syncs++; f.state.files = [{ ...f.state.files[0], knowledge_sync_status: 'synced' }]; };
  let tree = f.render(); await find(tree, e => e.props['aria-label'] === '通过 image.png').props.onClick(); tree = f.render();
  assert.match(find(tree, e => e.type === 'ErrorBanner').props.message, /审核已通过.*同步失败/);
  const retry = find(tree, e => [e.props.children].flat(Infinity).includes('重试向量入库')); assert.ok(retry);
  await retry.props.onClick(); tree = f.render(); assert.equal(reviews, 1); assert.equal(syncs, 1);
  assert.equal(find(tree, e => [e.props.children].flat(Infinity).includes('重试向量入库')), undefined);
});

function uploadFixture() {
  globals(); const h = hooks(); const requests = [], refreshed = [], errors = [];
  let error = '';
  global.XMLHttpRequest = class {
    constructor() { this.upload = {}; }
    open(_, url) { this.url = url; }
    send(body) { this.file = body.get('upload'); requests.push(this); }
    finish(status = 200, detail = '') {
      this.status = status;
      this.responseText = JSON.stringify(status === 200 ? { ...image, original_filename: this.file.name } : { detail });
      this.onload();
    }
  };
  const props = { projectId: 1, token: 'upload-session', notes: [{ id: 1, title: 'note' }],
    onStart() { error = ''; }, onUploaded(names) { error = ''; refreshed.push({ projectId: props.projectId, names }); },
    onError(message) { error = message; errors.push(message); } };
  const knowledge = loadSource('lib/knowledge-files.ts', baseMock);
  const Component = loadSource('app/(dashboard)/projects/[id]/data/upload-section.tsx', spec => spec === 'react' ? h.react : spec === '@/lib/utils' ? utilityMock : spec === '@/lib/knowledge-files' ? knowledge : baseMock(spec)).UploadSection;
  const render = () => h.render(() => Component(props));
  const select = (...files) => { find(render(), e => e.type === 'Dropzone').props.onFilesSelected(files); render(); };
  const start = () => find(render(), e => e.type === 'Button').props.onClick();
  let tree = render(); find(tree, e => e.type === 'Select' && e.props.value === 'note_attachment').props.onValueChange('knowledge_document'); render();
  return { requests, refreshed, errors, render, select, start, props, h, error: () => error };
}
const uploadFile = name => new File(['review fixture'], name, { type: 'text/plain' });
test('R14: partial batch upload refreshes success and retries only the failed file', async () => {
  const f = uploadFixture(); f.select(uploadFile('A.txt'), uploadFile('B.txt'));
  const first = f.start(); f.requests[0].finish(); await tick(); f.requests[1].finish(422, 'B unavailable'); await first;
  const tree = JSON.stringify(f.render()); assert.equal(tree.includes('A.txt'), false); assert.equal(tree.includes('B.txt'), true);
  assert.deepEqual(f.refreshed, [{ projectId: 1, names: ['A.txt'] }]); assert.equal(f.error(), 'B unavailable');
  const retry = f.start(); f.requests[2].finish(); await retry;
  assert.deepEqual(f.requests.map(r => r.file.name), ['A.txt', 'B.txt', 'B.txt']);
  assert.deepEqual(f.refreshed, [{ projectId: 1, names: ['A.txt'] }, { projectId: 1, names: ['B.txt'] }]);
});
test('R14: the active batch cannot change category, queue, or start twice', async () => {
  const f = uploadFixture(); f.select(uploadFile('A.txt'), uploadFile('B.txt'));
  const first = f.start(); let tree = f.render();
  const category = find(tree, e => e.type === 'Select' && e.props.value === 'knowledge_document');
  assert.equal(category.props.disabled, true); category.props.onValueChange('note_attachment');
  f.select(uploadFile('C.txt')); await f.start(); assert.equal(f.requests.length, 1);
  f.requests[0].finish(); await tick(); f.requests[1].finish(); await first; tree = f.render();
  assert.ok(find(tree, e => e.type === 'Select' && e.props.value === 'knowledge_document'));
  assert.deepEqual(f.requests.map(r => r.file.name), ['A.txt', 'B.txt']);
  assert.equal(JSON.stringify(tree).includes('C.txt'), false);
});
for (const change of ['project', 'identity']) {
  test(`R14: a ${change} change clears the queue and discards an old batch without unlocking the new batch`, async () => {
    const f = uploadFixture(); f.select(uploadFile('A.txt'), uploadFile('B.txt'));
    const old = f.start();
    if (change === 'project') f.props.projectId = 2; else f.props.token = 'new-upload-session';
    f.render(); f.render(); assert.equal(JSON.stringify(f.render()).includes('A.txt'), false);
    f.select(uploadFile('C.txt')); const current = f.start(); f.requests[0].finish(); await old;
    assert.equal(f.requests.length, 2); assert.deepEqual(f.refreshed, []); assert.deepEqual(f.errors, []);
    assert.equal(find(f.render(), e => e.type === 'Button').props.isLoading, true);
    f.requests[1].finish(); await current;
    assert.deepEqual(f.refreshed, [{ projectId: f.props.projectId, names: ['C.txt'] }]);
    assert.deepEqual(f.requests.map(r => r.file.name), ['A.txt', 'C.txt']);
  });
}
