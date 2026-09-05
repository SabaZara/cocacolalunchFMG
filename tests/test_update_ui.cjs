const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/admin.js'), 'utf8');
const start = source.indexOf('    els.updateBtn.addEventListener("click", function () {');
const end = source.indexOf('\n  }', start);
const handlerSource = source.slice(start, end);
const flush = () => new Promise(resolve => setImmediate(resolve));
function ui(oldInstance) {
  let click, interval, cleared = false, reloadScheduled = false;
  const state = {response: {version: '2.4.0', instance_id: 'old'}};
  const context = {els: {updateBtn: {addEventListener: (event, fn) => {click=fn;}}, updateMsg: {}},
    confirm: () => true, notice: () => {}, esc: s => s,
    api: async () => ({ok:true,j:{ok:true,version_changed:true,version_on_disk:'2.5.1',
      restarting:true,instance_before_restart:oldInstance}}),
    fetch: async () => ({json: async () => state.response}),
    setInterval: fn => {interval=fn;return 1;}, clearInterval: () => {cleared=true;},
    setTimeout: () => {reloadScheduled=true;}, location: {reload:()=>{}}};
  vm.runInNewContext(handlerSource, context);
  return {click, tick:()=>interval(), state, done:()=>cleared && reloadScheduled};
}
test('update UI does not reload when old v2.4 responds before restart begins', async () => {
  const p=ui(); p.click(); await flush(); p.tick(); await flush();
  assert.equal(p.done(),false);
  p.state.response={version:'2.5.1',instance_id:'new'};
  p.tick(); await flush(); assert.equal(p.done(),true);
});
test('same-version update requires a new process instance', async () => {
  const p=ui('old'); p.click(); await flush();
  p.state.response={version:'2.5.1',instance_id:'old'};
  p.tick(); await flush(); assert.equal(p.done(),false);
  p.state.response={version:'2.5.1',instance_id:'new'};
  p.tick(); await flush(); assert.equal(p.done(),true);
});
