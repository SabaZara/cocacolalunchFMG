const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../static/printer.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function panel() {
  const elements = {}, calls = [];
  const ids = ['receiptPrinter','receiptEnabled','printerRefresh','printerTest','printerSave','printerInstall','printerState','printerMsg'];
  ids.forEach(id => elements[id] = {value: '', checked: false, hidden: false, textContent: '',
    handlers: {}, appendChild: () => {}, addEventListener(name, cb) {this.handlers[name] = cb;}});
  const state = {printer: 'HPRT', printers: ['HPRT'], enabled: false, queue: {failed: 2}};
  const context = {document: {getElementById: id => elements[id], createElement: () => ({})},
    fetch: async (url, options) => {
      calls.push({url, options});
      let data = state;
      if (url.endsWith('/test')) data = {message: 'Sample submitted'};
      else if (options && options.method === 'POST') Object.assign(state, JSON.parse(options.body));
      return {ok: true, json: async () => data};
    }};
  vm.runInNewContext(code, context);
  return {elements, calls, state};
}
test('remote panel loads saved printer and queue errors', async () => {
  const p = panel(); await flush();
  assert.equal(p.elements.receiptPrinter.value, 'HPRT');
  assert.equal(p.elements.receiptEnabled.checked, false);
  assert.ok(p.elements.printerState.textContent.includes('შეცდომა: 2'));
});
test('test button sends selected printer without enabling printing', async () => {
  const p = panel(); await flush();
  p.elements.printerTest.handlers.click(); await flush();
  const call = p.calls.find(c => c.url.endsWith('/test'));
  assert.equal(JSON.parse(call.options.body).printer, 'HPRT');
  assert.equal(p.state.enabled, false);
  assert.equal(p.elements.printerMsg.textContent, 'Sample submitted');
  assert.equal(p.elements.printerTest.disabled, false);
});
test('save applies enabled setting through remote API', async () => {
  const p = panel(); await flush();
  p.elements.receiptEnabled.checked = true;
  p.elements.printerSave.handlers.click(); await flush();
  assert.equal(p.state.enabled, true);
  assert.equal(p.elements.printerSave.disabled, false);
  assert.ok(p.elements.printerMsg.textContent.includes('შენახულია'));
});
