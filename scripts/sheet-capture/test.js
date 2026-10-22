const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');

const properties = { SOURCE_ID: 'fake-source', LOG_ID: 'fake-log' };
const written = [];
let failWrite = false;
let available = true;
let values = [['', 0, '=SUM(A1)', '😀']];
const props = {
  getProperty: key => properties[key] || null,
  setProperty: (key, value) => { properties[key] = value; },
  deleteProperty: key => { delete properties[key]; },
  getProperties: () => ({ ...properties }),
  setProperties: data => Object.assign(properties, data),
};
const sourceRange = {
  getValues: () => values, getFormulas: () => [['', '', '=SUM(A1)', '']],
  getA1Notation: () => 'A1:D1', getNumRows: () => 1, getNumColumns: () => 4,
  getSheet: () => tab,
};
const tab = {
  getSheetId: () => 42, getName: () => '=untrusted',
  getLastRow: () => 1, getLastColumn: () => 4, getRange: () => sourceRange,
};
const bigTab = {
  getSheetId: () => 7, getName: () => 'big', getLastRow: () => 1000, getLastColumn: () => 300,
  getRange: () => { throw Error('oversize tab must not be read'); },
};
const source = { getId: () => 'fake-source',
  getSheetById: id => id === 7 ? bigTab : (available ? tab : null),
  getSheets: () => [tab] };
let logRowsBefore = 0;
let logColumns = 11;
const log = { getSheetByName: () => ({
  getLastRow: () => 1 + logRowsBefore + written.length, getMaxRows: () => 1000000,
  getMaxColumns: () => logColumns,
  getRange: (row) => ({ getValues: () => [headers], setValues: rows => {
    if (failWrite) throw Error('fake outage');
    assert.ok(row > 1);
    written.push(...rows);
  } }),
}) };
const context = vm.createContext({
  ScriptApp: {
    getProjectTriggers: () => [], deleteTrigger() {},
    newTrigger: () => {
      const chain = { forSpreadsheet: () => chain, onEdit: () => chain, onChange: () => chain,
        timeBased: () => chain, everyMinutes: () => chain, everyDays: () => chain,
        atHour: () => chain, inTimezone: () => chain, create() {} };
      return chain;
    },
  },
  PropertiesService: { getScriptProperties: () => props },
  LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
  SpreadsheetApp: { openById: id => {
    if (id === 'fake-source') return source;
    assert.equal(id, 'fake-log');
    return log;
  }, flush() {} },
  Utilities: { getUuid: () => crypto.randomUUID(),
    computeDigest: (_, text) => crypto.createHash('sha256').update(text).digest(),
    base64Encode: bytes => Buffer.from(bytes).toString('base64'),
    DigestAlgorithm: { SHA_256: 'sha256' }, Charset: { UTF_8: 'utf8' } },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, 'Code.gs'), 'utf8'), context);
const headers = vm.runInContext('CAPTURE_HEADERS', context);

assert.throws(() => context.captureEdit(), /event required/);
properties.LOG_ID = properties.SOURCE_ID;
assert.throws(() => context.captureConfig(), /distinct/);
properties.LOG_ID = 'fake-log';
assert.throws(() => context.captureEdit({ source: { getId: () => 'wrong' }, range: sourceRange }), /Unexpected/);
context.captureEdit({ source, range: sourceRange, oldValue: 'old', value: 'new' });
assert.equal(properties.dirty_42, '1');
assert.equal(properties.urgent_42, '1');
assert.equal(written[0][4], "'=untrusted");
const event = JSON.parse(written[0][10]);
assert.equal(event.old_value, 'old');
assert.equal(event.event_value, 'new');
assert.equal(event.values[0][0], '');
assert.equal(event.values[0][1], 0);
context.captureDrain();
assert.ok(properties.hash_42);
assert.equal(properties.dirty_42, undefined);
const count = written.length;
properties.dirty_42 = '1';
context.captureDrain();
assert.equal(written.length, count, 'unchanged snapshot must not repeat');

values = [['updated']];
properties.dirty_42 = '1';
failWrite = true;
const previousHash = properties.hash_42;
assert.throws(() => context.captureDrain(), /outage/);
assert.equal(properties.dirty_42, '1');
assert.equal(properties.hash_42, previousHash);
failWrite = false;
context.captureDrain();
assert.notEqual(properties.hash_42, previousHash);
properties.dirty_7 = '1';
properties.urgent_7 = '1';
properties.dirty_42 = '1';
values = [['after-stall']];
assert.throws(() => context.captureDrain(), /scan ceiling/);
assert.equal(properties.dirty_7, '1', 'oversize tab keeps its pending flag');
assert.ok(properties.fail_7);
context.captureDrain();
assert.equal(properties.dirty_42, undefined, 'a failing tab must not block other tabs');
assert.throws(() => context.captureDrain(), /scan ceiling/, 'failed tab is retried when nothing else is pending');
delete properties.dirty_7;
delete properties.urgent_7;
delete properties.fail_7;
logRowsBefore = 310000;
logColumns = 26;
assert.throws(() => context.captureAppend(context.captureConfig(), 'TEST', null, '', '', {}), /capacity/,
  'capacity counts allocated columns of the log tab');
logRowsBefore = 0;
logColumns = 11;
context.captureChange({ source, changeType: 'REMOVE_ROW' });
assert.equal(properties.dirty_42, '1');
assert.equal(JSON.parse(written.at(-2)[10]).affected_tab, null);
available = false;
context.captureDrain();
assert.equal(written.at(-2)[2], 'TAB_MISSING');
assert.equal(properties.dirty_42, undefined);
context.captureAppend(context.captureConfig(), 'TEST', null, '', '', { text: '😀'.repeat(25000) });
const complete = written.at(-1);
const parts = written.filter(row => row[7] === complete[7] && row[2] !== 'COMPLETE');
assert.ok(parts.length > 1);
assert.ok(parts.every(row => row[10].isWellFormed()), 'chunks must not split Unicode surrogate pairs');
assert.equal(parts.length, JSON.parse(complete[10]).parts);
assert.equal(JSON.parse(parts.map(row => row[10]).join('')).text, '😀'.repeat(25000));
properties.hash_42 = 'previous-log';
properties.dirty_99 = '1';
properties.urgent_99 = '1';
properties.fail_99 = 'x';
context.captureInstall();
assert.equal(properties.fail_99, undefined);
assert.equal(properties.hash_42, undefined, 'new log must receive baseline');
assert.equal(properties.dirty_99, undefined, 'old source queue cleared');
assert.equal(properties.urgent_99, undefined);
assert.equal(properties.dirty_42, '1');
console.log('PASS: source validation, edit evidence, blank/zero, formula safety, snapshots, retry, failing tab does not stall queue, log capacity, structure, deleted tab, chunk completeness');
