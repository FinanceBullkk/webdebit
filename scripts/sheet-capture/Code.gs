// Capture only. Never writes to the source workbook or to Webdebit.
const CAPTURE_HEADERS = ['id', 'captured_at_utc', 'kind', 'sheet_id', 'sheet_name',
  'range', 'actor_if_available', 'group_id', 'part', 'parts', 'payload_json'];

function captureConfig() {
  const p = PropertiesService.getScriptProperties();
  const source = p.getProperty('SOURCE_ID');
  const log = p.getProperty('LOG_ID');
  if (!source || !log || source === log) throw new Error('Configure distinct SOURCE_ID and LOG_ID');
  return { p: p, source: source, log: log };
}

function captureLocked(fn) {
  const lock = LockService.getScriptLock();
  lock.waitLock(25000);
  try { return fn(); } finally { lock.releaseLock(); }
}

function captureText(value) {
  // User text must never become a formula in the log workbook.
  return typeof value === 'string' && /^[=+\-@]/.test(value) ? "'" + value : value;
}

function captureAppend(c, kind, sheet, range, actor, payload) {
  const text = JSON.stringify(payload);
  // Keep each stored cell valid Unicode as well as below the cell-size ceiling.
  const pieces = [];
  for (let i = 0; i < text.length;) {
    let end = Math.min(i + 20000, text.length);
    const last = text.charCodeAt(end - 1);
    if (end < text.length && last >= 0xD800 && last <= 0xDBFF) end--;
    pieces.push(text.slice(i, end));
    i = end;
  }
  const id = Utilities.getUuid();
  const at = new Date().toISOString();
  const rows = pieces.map(function(piece, index) {
    return [Utilities.getUuid(), at, kind, sheet ? sheet.getSheetId() : '',
      sheet ? sheet.getName() : '', range || '', actor || '', id,
      index + 1, pieces.length, piece].map(captureText);
  });
  // A group is usable only with its COMPLETE record and every numbered part.
  rows.push([Utilities.getUuid(), at, 'COMPLETE', '', '', '', '', id, '', '',
    JSON.stringify({ kind: kind, parts: pieces.length, status: 'CAPTURED' })]);
  const book = SpreadsheetApp.openById(c.log);
  const tab = book.getSheetByName('EVENTS');
  if (!tab || JSON.stringify(tab.getRange(1, 1, 1, CAPTURE_HEADERS.length).getValues()[0]) !== JSON.stringify(CAPTURE_HEADERS)) {
    throw new Error('EVENTS header missing or changed');
  }
  const end = tab.getLastRow() + rows.length;
  // The workbook limit counts every allocated column, not just the headers.
  if (end * Math.max(CAPTURE_HEADERS.length, tab.getMaxColumns()) > 8000000) throw new Error('Log near capacity: archive to another private workbook');
  if (end > tab.getMaxRows()) tab.insertRowsAfter(tab.getMaxRows(), end - tab.getMaxRows());
  tab.getRange(end - rows.length + 1, 1, rows.length, CAPTURE_HEADERS.length).setValues(rows);
  SpreadsheetApp.flush();
  return id;
}

function captureQueueAll(c, source) {
  const pending = {};
  source.getSheets().forEach(function(tab) { pending['dirty_' + tab.getSheetId()] = '1'; });
  c.p.setProperties(pending);
}

function captureEdit(e) {
  if (!e || !e.source || !e.range) throw new Error('Installable edit event required');
  captureLocked(function() {
    const c = captureConfig();
    if (e.source.getId() !== c.source) throw new Error('Unexpected source');
    const tab = e.range.getSheet();
    c.p.setProperty('dirty_' + tab.getSheetId(), '1');
    c.p.setProperty('urgent_' + tab.getSheetId(), '1');
    const actor = e.user ? e.user.getEmail() : '';
    // Read at handler time, not guaranteed to be the exact edit-time state.
    // Huge pastes store only the range; the full-tab snapshot captures the surviving state.
    const cells = e.range.getNumRows() * e.range.getNumColumns();
    const payload = { schema: 1, observation: 'HANDLER_TIME',
      old_value_available: Object.prototype.hasOwnProperty.call(e, 'oldValue'),
      old_value: Object.prototype.hasOwnProperty.call(e, 'oldValue') ? e.oldValue : null,
      event_value_available: Object.prototype.hasOwnProperty.call(e, 'value'),
      event_value: Object.prototype.hasOwnProperty.call(e, 'value') ? e.value : null,
      values: cells <= 20000 ? e.range.getValues() : null,
      formulas: cells <= 20000 ? e.range.getFormulas() : null,
      needs_snapshot: true };
    captureAppend(c, 'EDIT', tab, e.range.getA1Notation(), actor, payload);
  });
}

function captureChange(e) {
  if (!e || !e.source) throw new Error('Installable change event required');
  if (e.changeType === 'EDIT') return; // edit trigger records these with a reliable range.
  captureLocked(function() {
    const c = captureConfig();
    if (e.source.getId() !== c.source) throw new Error('Unexpected source');
    // onChange has no reliable affected range/tab. Do not use getActiveSheet().
    captureQueueAll(c, e.source);
    captureAppend(c, 'STRUCTURE', null, '', e.user ? e.user.getEmail() : '',
      { schema: 1, change_type: e.changeType || 'UNKNOWN', affected_tab: null });
  });
}

function captureFullSweep() {
  captureLocked(function() {
    const c = captureConfig();
    const source = SpreadsheetApp.openById(c.source);
    captureQueueAll(c, source);
    captureAppend(c, 'INVENTORY', null, '', '', { schema: 1, tabs: source.getSheets().map(function(tab) {
      return { id: tab.getSheetId(), name: tab.getName() };
    }) });
  });
}

function captureDrain() {
  captureLocked(function() {
    const c = captureConfig();
    const pending = Object.keys(c.p.getProperties()).filter(function(key) { return key.indexOf('dirty_') === 0; });
    if (!pending.length) return;
    // A tab that failed last time goes behind the others so it cannot stall the queue;
    // it is retried once nothing else is pending.
    const ready = pending.filter(function(item) { return !c.p.getProperty(item.replace('dirty_', 'fail_')); });
    const pool = ready.length ? ready : pending;
    const key = pool.find(function(item) { return c.p.getProperty(item.replace('dirty_', 'urgent_')); }) || pool[0];
    const id = Number(key.slice(6));
    try {
      const tab = SpreadsheetApp.openById(c.source).getSheetById(id);
      if (!tab) {
        captureAppend(c, 'TAB_MISSING', null, '', '', { sheet_id: id });
      } else {
        const rows = tab.getLastRow();
        const columns = tab.getLastColumn();
        if (rows * columns > 250000) throw new Error('Tab exceeds scan ceiling; pending retained');
        const range = rows && columns ? tab.getRange(1, 1, rows, columns) : null;
        const snapshot = { schema: 1, sheet_id: id, name: tab.getName(), rows: rows, columns: columns,
          values: range ? range.getValues() : [], formulas: range ? range.getFormulas() : [] };
        const hash = Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,
          JSON.stringify(snapshot), Utilities.Charset.UTF_8));
        if (c.p.getProperty('hash_' + id) !== hash) {
          captureAppend(c, 'SNAPSHOT', tab, range ? range.getA1Notation() : '', '', snapshot);
          c.p.setProperty('hash_' + id, hash);
        }
      }
    } catch (err) {
      c.p.setProperty('fail_' + id, new Date().toISOString());
      throw err;
    }
    c.p.deleteProperty(key); // Only after durable log write (or identical snapshot).
    c.p.deleteProperty('urgent_' + id);
    c.p.deleteProperty('fail_' + id);
    c.p.setProperty('LAST_DRAIN_OK_UTC', new Date().toISOString());
  });
}

function captureInstall() {
  captureLocked(function() {
    const c = captureConfig();
    const source = SpreadsheetApp.openById(c.source);
    const book = SpreadsheetApp.openById(c.log);
    let tab = book.getSheetByName('EVENTS');
    if (!tab) tab = book.insertSheet('EVENTS');
    if (tab.getLastRow() === 0) tab.getRange(1, 1, 1, CAPTURE_HEADERS.length).setValues([CAPTURE_HEADERS]);
    captureAppend(c, 'INSTALL', null, '', '', { schema: 1, source_id: c.source, capture_only: true });
    const handlers = ['captureEdit', 'captureChange', 'captureDrain', 'captureFullSweep'];
    ScriptApp.getProjectTriggers().forEach(function(trigger) {
      if (handlers.indexOf(trigger.getHandlerFunction()) !== -1) ScriptApp.deleteTrigger(trigger);
    });
    ScriptApp.newTrigger('captureEdit').forSpreadsheet(source).onEdit().create();
    ScriptApp.newTrigger('captureChange').forSpreadsheet(source).onChange().create();
    ScriptApp.newTrigger('captureDrain').timeBased().everyMinutes(1).create();
    ScriptApp.newTrigger('captureFullSweep').timeBased().everyDays(1).atHour(1).inTimezone('Asia/Ho_Chi_Minh').create();
    // A new destination needs a fresh baseline, even if prior hashes match.
    Object.keys(c.p.getProperties()).forEach(function(key) {
      if (/^(hash_|dirty_|urgent_|fail_)/.test(key) || key === 'LAST_DRAIN_OK_UTC') c.p.deleteProperty(key);
    });
    captureQueueAll(c, source);
  });
}

function captureUninstall() {
  const handlers = ['captureEdit', 'captureChange', 'captureDrain', 'captureFullSweep'];
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (handlers.indexOf(trigger.getHandlerFunction()) !== -1) ScriptApp.deleteTrigger(trigger);
  });
}
