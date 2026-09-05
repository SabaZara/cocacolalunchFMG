// Actual kiosk JavaScript, simulated keyboard reader/DOM/network; no printer needed.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/kiosk.js'), 'utf8');
function kiosk() {
  let now = 10000;
  const requests = [];
  const elements = {};
  for (const id of ['capture', 'screen', 'bigText', 'subText', 'beepToggle']) {
    const handlers = {};
    const el = {value: '', className: '', textContent: '', handlers,
      addEventListener: (name, cb) => {handlers[name] = cb;}, focus: () => {}};
    el.classList = {add: () => {}, remove: () => {}, toggle: () => {},
      contains: (name) => el.className.split(' ').includes(name)};
    elements[id] = el;
  }
  const context = {
    Date: {now: () => now}, document: {getElementById: id => elements[id], addEventListener: () => {}},
    window: {addEventListener: () => {}}, location: {pathname: '/', replace: () => {}},
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1,
    fetch: (url, options) => {
      if (url !== '/api/scan') return Promise.resolve({json: () => ({version: '2.5.0'})});
      return new Promise(resolve => requests.push({payload: JSON.parse(options.body),
        reply: result => resolve({json: () => result})}));
    }
  };
  vm.runInNewContext(source, context);
  return {elements, requests, advance: ms => {now += ms;},
    tap: id => {
      elements.capture.value = id;
      elements.capture.handlers.keydown({key: 'Enter', preventDefault: () => {}});
    }};
}
const flush = () => new Promise(resolve => setImmediate(resolve));
test('keyboard reader preserves zeros and repeated Enter does not duplicate a receipt request', async () => {
  const k = kiosk();
  k.tap('00001234');
  k.tap('00001234');
  assert.equal(k.requests.length, 1);
  assert.equal(k.requests[0].payload.card_id, '00001234');
  k.requests[0].reply({status: 'ALLOWED', scanned_at: '12:30:00'});
  await flush();
  assert.equal(k.elements.bigText.textContent, 'ნებადართულია');
  k.advance(1199);
  k.tap('00001234');
  assert.equal(k.requests.length, 1);
  k.advance(1);
  k.tap('00001234');
  assert.equal(k.requests.length, 2);
});
test('empty reader input creates no scan or receipt', () => {
  const k = kiosk();
  k.tap(''); k.tap('   ');
  assert.equal(k.requests.length, 0);
});
test('denied result remains visible and never resubmits automatically', async () => {
  const k = kiosk();
  k.tap('limited');
  k.requests[0].reply({status: 'DENIED', reason: 'დღის ლიმიტი ამოიწურა'});
  await flush();
  assert.equal(k.elements.bigText.textContent, 'უარყოფილია');
  assert.equal(k.elements.subText.textContent, 'დღის ლიმიტი ამოიწურა');
  assert.equal(k.requests.length, 1);
});
