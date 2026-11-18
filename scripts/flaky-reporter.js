// Reporter cho `node --test` dùng trong scripts/flaky-repeat.js: mỗi ca xong in một dòng JSON
// {kind, file, name, nesting, ms, error}; kind là pass, fail hoặc retry (shared-browser.js chạy lại vì
// ERR_NO_BUFFER_SPACE). Không dùng riêng; xem docs/development.md, mục "Job đêm tìm test chập chờn".
//
// `file` của từng ca là chỗ gọi test(): ca khai qua shared-browser.js thì mang tên file đó. Sự kiện của mỗi file
// test đến thành một khối, kết thúc bằng test:summary có `file` là chính file test, nên giữ các dòng tới đó rồi
// mới ghi, kèm tên file thật.

module.exports = async function* flakyReporter(source) {
  let pending = [];
  for await (const event of source) {
    const data = event.data ?? {};
    if (event.type === 'test:pass' || event.type === 'test:fail') {
      // Ca bị bỏ qua hoặc todo vẫn đi qua test:pass; không tính.
      if (data.skip !== undefined || data.todo !== undefined) continue;
      const row = {
        kind: event.type === 'test:pass' ? 'pass' : 'fail',
        file: data.file ?? null,
        name: data.name,
        nesting: data.nesting,
        type: data.details?.type ?? 'test',
        ms: Math.round(data.details?.duration_ms ?? 0),
      };
      if (row.kind === 'fail') {
        const error = data.details?.error;
        const cause = error?.cause ?? error;
        row.failureType = error?.failureType ?? null;
        row.error = String(cause?.message ?? cause ?? error?.message ?? '').split('\n').slice(0, 3).join(' ').slice(0, 300);
      }
      pending.push(row);
    } else if (event.type === 'test:diagnostic' && /ERR_NO_BUFFER_SPACE/.test(data.message ?? '')) {
      pending.push({ kind: 'retry', file: data.file ?? null, name: data.message, nesting: data.nesting });
    } else if (event.type === 'test:summary' && data.file) {
      for (const row of pending) yield `${JSON.stringify({ ...row, file: data.file })}\n`;
      pending = [];
    }
  }
  for (const row of pending) yield `${JSON.stringify(row)}\n`;
};
