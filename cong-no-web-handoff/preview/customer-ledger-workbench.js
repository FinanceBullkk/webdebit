/* Isolated synthetic fixture. No network, database, or production posting. */
const CustomerLedgerWorkbench = (() => {
  const periods = ['2026-01', '2026-02', '2026-03'];
  const fixture = {
    openings: [{ id:'MO-01', period:'2026-01', date:'2026-01-01', amount:20000000n, status:'posted' }],
    shipments: [
      { id:'CH-101',period:'2026-01',date:'2026-01-05',container:'DEMO-101',carrier:'Tàu A / 51A-001',shipper:'Demo Logistics',origin:'Cát Lái',destination:'Kho A',otherFee:'',tractionFee:'',insuranceFee:'',price:'30000000',approvedTotal:30000000n,status:'posted' },
      { id:'CH-102',period:'2026-02',date:'2026-02-06',container:'DEMO-102',carrier:'Tàu B / 51A-002',shipper:'Demo Logistics',origin:'Kho B',destination:'Cát Lái',otherFee:'',tractionFee:'',insuranceFee:'',price:'40000000',approvedTotal:40000000n,status:'posted' },
      { id:'CH-103',period:'2026-02',date:'2026-02-10',container:'DEMO-103',carrier:'',shipper:'',origin:'',destination:'',otherFee:'',tractionFee:'',insuranceFee:'',price:'',approvedTotal:null,status:'waiting_price' },
      { id:'CH-104',period:'2026-03',date:'2026-03-03',container:'DEMO-104',carrier:'',shipper:'',origin:'',destination:'',otherFee:'',tractionFee:'',insuranceFee:'',price:'25000000',approvedTotal:25000000n,status:'posted' },
    ],
    payments: [
      { id:'PT-101',receiptId:'PT-101',date:'2026-02-08',period:'2026-01',amount:10000000n,receiptTotal:10000000n,status:'posted',kind:'receipt' },
      { id:'PT-102',receiptId:'PT-102',date:'2026-03-15',period:'2026-02',amount:10000000n,receiptTotal:10000000n,status:'posted',kind:'receipt' },
      { id:'PT-103',receiptId:'PT-103',date:'2026-03-16',period:'2026-03',amount:5000000n,receiptTotal:5000000n,status:'waiting_confirmation',kind:'receipt' },
    ]
  };
  const validDate = s => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0,10) === s;
  function createWorkbench() {
    const shipments = fixture.shipments.map(s => ({...s}));
    const payments = fixture.payments.map(p => ({...p}));
    const openings = fixture.openings.map(o => ({...o}));
    const drafts = Object.fromEntries(periods.map(p => [p, []]));
    let nextId = 1;
    const receiptsByRequest = new Map();
    const credits = [];
    const fields = ['date','container','carrier','shipper','origin','destination','price','otherFee','tractionFee','insuranceFee','approvedTotal'];
    const money = s => typeof s === 'string' && /^(0|[1-9]\d*)$/.test(s) ? BigInt(s) : null;
    function addDraft(period) {
      if (!periods.includes(period)) throw Error('Kỳ không hợp lệ');
      const row = {id:'NH-'+nextId++, period, status:'draft',errors:[],warnings:[]};
      for (const f of fields) row[f]='';
      drafts[period].push(row);
      return row;
    }
    function paste(period, tsv) {
      if (typeof tsv !== 'string' || !tsv.trim()) return [];
      const lines=tsv.replace(/\r/g,'').replace(/\n$/,'').split('\n');
      if (lines.length>50) throw Error('Tối đa 50 dòng mỗi lần dán');
      return lines.map(line => {
        const cells=line.split('\t');
        const row=addDraft(period);
        fields.forEach((f,i)=>row[f]=cells[i]??'');
        return row;
      });
    }
    function updateDraft(period,id,values) {
      const row=drafts[period]?.find(r=>r.id===id);
      if (!row) throw Error('Không thấy dòng nháp');
      for (const [key,val] of Object.entries(values)) if (fields.includes(key)) row[key]=String(val);
      row.errors=[]; row.warnings=[];
      return row;
    }
    function fillSelected(period,ids,values) {
      if (!['price','otherFee','tractionFee','insuranceFee','approvedTotal'].some(k=>Object.hasOwn(values,k))) throw Error('Chỉ điền giá/phí/tổng đã xác nhận');
      const selected=new Set(ids);
      return (drafts[period]||[]).filter(r=>selected.has(r.id)).map(r=>updateDraft(period,r.id,values));
    }
    function saveShipments(period) {
      const rows=drafts[period];
      if (!rows?.length) return {ok:false,errors:['Chưa có dòng nhập']};
      for (const r of rows) {
        r.errors=[]; r.warnings=[];
        if (!validDate(r.date) || r.date.slice(0,7)!==period) r.errors.push('Sai ngày hoặc ngày không thuộc kỳ');
        if (!r.container.trim()) r.errors.push('Thiếu container hoặc mã khoản chung');
        for (const f of ['price','otherFee','tractionFee','insuranceFee','approvedTotal']) if (r[f]!=='' && money(r[f])===null) r.errors.push(`${f}: tiền phải là số nguyên VND không âm`);
        const similar=[...shipments,...rows.filter(x=>x!==r)].some(x=>x.period===period && x.date===r.date && x.container.trim().toUpperCase()===r.container.trim().toUpperCase());
        if (similar && r.container.trim()) r.warnings.push('Trùng container + ngày + kỳ: cần kiểm tra, không tự gộp');
        const estimated=estimate(r);
        if (r.approvedTotal!=='' && estimated===null && ['otherFee','tractionFee','insuranceFee'].some(f=>r[f]!==''))
          r.errors.push('Có tổng và phí nhưng cấu phần còn trống: cần xác minh');
        if (r.approvedTotal!=='' && estimated!==null && money(r.approvedTotal)!==estimated)
          r.errors.push('Sai khác tổng và cấu phần phí: giữ nháp, cần xác minh');
        if (r.price!=='' && estimated===null)
          r.warnings.push('Có giá nhưng một khoản phí còn trống; cần xác nhận 0 hoặc bổ sung trước duyệt');
      }
      if (rows.some(r=>r.errors.length)) return {ok:false,rows};
      // Even with an entered total, browser cannot approve price/fees. Save drafts only.
      for (const r of rows) {
        shipments.push({...r, status:r.price===''?'waiting_price':'draft',approvedTotal:null});
      }
      drafts[period]=[];
      return {ok:true,count:rows.length,posted:false,warnings:rows.flatMap(r=>r.warnings)};
    }
    function estimate(row) {
      const values=['price','otherFee','tractionFee','insuranceFee'].map(k=>money(row[k]));
      return values.some(v=>v===null) ? null : values.reduce((sum,v)=>sum+v,0n);
    }
    function planReceipt(amount,date='2026-04-30',options={}) {
      const n=money(String(amount));
      if (n===null || n<=0n || !validDate(date) || date<'2026-01-01' || date>'2026-04-30') throw Error('Tiền/ngày không hợp lệ');
      let remaining=n;
      const allocations=[];
      for (const m of snapshot({asOf:date}).months) {
        const available=m.balance>0n ? m.balance : 0n;
        const applied=remaining < available ? remaining : available;
        if (applied>0n) allocations.push({period:m.period,amount:applied});
        remaining-=applied;
      }
      if (remaining>0n && options.overpayPeriod!==undefined && !periods.includes(options.overpayPeriod)) throw Error('Phải chọn kỳ nợ hợp lệ cho tiền trả dư');
      return {allocations,unallocated:remaining,overpayment:remaining>0n && options.overpayPeriod ? {period:options.overpayPeriod,amount:remaining}:null};
    }
    function saveReceipt(input) {
      const {date,amount,requestId,overpayPeriod}=input;
      const fail=error=>({ok:false,error,input});
      if (!requestId || !String(requestId).trim()) return fail('Thiếu mã yêu cầu mô phỏng');
      if (receiptsByRequest.has(requestId)) {
        const old=receiptsByRequest.get(requestId);
        return JSON.stringify(old.input)===JSON.stringify(input) ? {ok:true,duplicate:true,receipt:old.receipt} : fail('Mã yêu cầu đã dùng với dữ liệu khác');
      }
      if (!validDate(date) || date<'2026-01-01' || date>'2026-04-30' || money(String(amount))===null || money(String(amount))<=0n) return fail('Ngày hoặc tiền không hợp lệ');
      let plan;
      try { plan=planReceipt(String(amount),date,{overpayPeriod}); }
      catch (error) { return fail(error.message); }
      if (plan.unallocated>0n && !overpayPeriod) return fail('Tiền trả dư: chọn kỳ nợ để trình duyệt số dư âm');
      const receipt={id:'TH-'+(receiptsByRequest.size+1),date,amount:money(String(amount)),status:'pending',allocations:plan.allocations,unallocated:plan.unallocated,overpayment:plan.overpayment};
      for (const [i,a] of plan.allocations.entries()) payments.push({id:`${receipt.id}/A${i+1}`,requestId,receiptId:receipt.id,date,period:a.period,amount:a.amount,receiptTotal:receipt.amount,status:'pending',kind:'receipt'});
      if (plan.overpayment) payments.push({id:`${receipt.id}/OVER`,requestId,receiptId:receipt.id,date,period:plan.overpayment.period,amount:plan.overpayment.amount,receiptTotal:receipt.amount,status:'pending',kind:'receipt'});
      receiptsByRequest.set(requestId,{input:{...input},receipt});
      return {ok:true,receipt};
    }
    function snapshot({asOf='2026-04-30',period='all'}={}) {
      if (!validDate(asOf) || asOf < '2026-01-01' || asOf > '2026-04-30') throw Error('Ngày ngoài phạm vi fixture');
      if (period !== 'all' && !periods.includes(period)) throw Error('Kỳ không hợp lệ');
      const months = periods.map(p => {
        const pick = rows => rows.filter(r => r.period === p && r.date <= asOf).sort((a,b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
        const op = pick(openings), sh = pick(shipments), pay = pick(payments);
        const opening = op.reduce((n,r) => n+r.amount,0n);
        const charge = sh.reduce((n,r) => n+(r.status==='posted' ? r.approvedTotal : 0n),0n);
        const paid = pay.reduce((n,r) => n+(r.status==='posted' ? r.amount : 0n),0n);
        return {period:p,openings:op,shipments:sh,payments:pay,opening,charge,paid,balance:opening+charge-paid,waitingPrice:sh.filter(r => r.status!=='posted').length,waitingConfirmation:pay.filter(r=>r.status!=='posted').length,drafts:drafts[p]};
      }).filter(m => m.openings.length || m.shipments.length || m.payments.length || m.drafts.length);
      const visible = period==='all' ? months : months.filter(m=>m.period===period);
      const sum = ms => ms.reduce((n,m)=>n+m.balance,0n);
      return {period,asOf,months:visible,allBalance:sum(months),visibleBalance:sum(visible),pendingAll:months.reduce((n,m)=>n+m.waitingPrice+m.waitingConfirmation+m.drafts.length,0),pendingVisible:visible.reduce((n,m)=>n+m.waitingPrice+m.waitingConfirmation+m.drafts.length,0),confirmedUnallocated:credits.filter(c=>c.date<=asOf).reduce((n,c)=>n+c.amount,0n)};
    }
    return {snapshot,addDraft,paste,updateDraft,fillSelected,saveShipments,estimate,planReceipt,saveReceipt};
  }
  return {createWorkbench,periods,validDate};
})();
if (typeof module !== 'undefined') module.exports = CustomerLedgerWorkbench;
