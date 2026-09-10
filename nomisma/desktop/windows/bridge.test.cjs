const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function loadBridge({origin = 'http://127.0.0.1:8765', frame = false, permission = 'default'} = {}) {
  const sent = [];
  const window = new EventTarget();
  const webview = new EventTarget();
  const activation = {isActive: true};
  let printCount = 0;
  webview.postMessage = message => sent.push(message);
  window.chrome = {webview};
  window.top = frame ? {} : window;
  window.print = () => printCount++;
  const context = vm.createContext({window, location: {origin}, navigator: {userActivation: activation}, EventTarget, Event, setTimeout, clearTimeout});
  const configuration = {origin: 'http://127.0.0.1:8765', configFile: 'C:\\Users\\Test\\.env', dataDirectory: 'C:\\Users\\Test\\data', notificationPermission: permission};
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'Bridge.js'), 'utf8').replace('__NOMISMA_CONFIG__', JSON.stringify(configuration)), context);
  const reply = data => webview.dispatchEvent(Object.assign(new Event('message'), {data: {channel: 'nomisma', ...data}}));
  return {window, sent, activation, reply, get printCount() { return printCount; }};
}

test('the native bridge exists only in the exact trusted top-level origin', () => {
  for (const config of [{origin: 'https://example.com'}, {origin: 'http://127.0.0.1:8766'}, {frame: true}])
    assert.equal(loadBridge(config).window.nomismaDesktop, undefined);
  const {window} = loadBridge();
  assert.equal(window.nomismaDesktop.platform, 'windows');
  assert.equal(Object.isFrozen(window.nomismaDesktop), true);
});

test('notification permission requires an active user gesture and a native reply', async () => {
  const bridge = loadBridge();
  bridge.activation.isActive = false;
  assert.equal(await bridge.window.Notification.requestPermission(), 'default');
  assert.equal(bridge.sent.length, 0);
  bridge.activation.isActive = true;
  const result = bridge.window.Notification.requestPermission();
  assert.equal(bridge.sent[0].action, 'notificationPermission');
  assert.equal(bridge.window.Notification.permission, 'default');
  bridge.reply({id: bridge.sent[0].id, result: 'granted'});
  assert.equal(await result, 'granted');
  assert.equal(bridge.window.Notification.permission, 'granted');
});

test('the print promise stays pending until afterprint and prevents duplicate dialogs', async () => {
  const bridge = loadBridge();
  let completed = false;
  const printing = bridge.window.nomismaDesktop.print();
  printing.then(() => { completed = true; });
  assert.equal(bridge.window.nomismaDesktop.print(), printing);
  assert.equal(bridge.printCount, 1);
  await Promise.resolve();
  assert.equal(completed, false);
  bridge.window.dispatchEvent(new Event('afterprint'));
  await printing;
  assert.equal(completed, true);
  const second = bridge.window.nomismaDesktop.print();
  assert.equal(bridge.printCount, 2);
  bridge.window.dispatchEvent(new Event('afterprint'));
  await second;
});

test('notification click replies invoke the existing app click handler', async () => {
  const bridge = loadBridge({permission: 'granted'});
  const notification = new bridge.window.Notification('Alert', {body: 'Details', tag: 'PLUG'});
  let clicked = false;
  notification.onclick = () => { clicked = true; };
  const request = bridge.sent[0];
  assert.equal(request.action, 'notify');
  bridge.reply({id: request.id, result: true});
  bridge.reply({event: 'notificationClick', notificationId: request.notificationId});
  assert.equal(clicked, true);
  clicked = false;
  notification.close();
  bridge.reply({event: 'notificationClick', notificationId: request.notificationId});
  assert.equal(clicked, false);
});

test('native errors reject requests without enabling permission', async () => {
  const bridge = loadBridge();
  const request = bridge.window.Notification.requestPermission();
  bridge.reply({id: bridge.sent[0].id, error: 'Unavailable'});
  await assert.rejects(request, /Unavailable/);
  assert.equal(bridge.window.Notification.permission, 'default');
  assert.throws(() => new bridge.window.Notification('Alert'), /Enable desktop alerts/);
});
