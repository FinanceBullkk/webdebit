/* Bản thử trong bộ nhớ tab; mọi phép tính tiền đi qua LedgerV6Model. */
(() => {
  'use strict';
  const model = LedgerV6Model;
  const root = document.querySelector('#app');
  const params = new URLSearchParams(location.search);
  let today = params.get('today') || '2026-05-03';
  try { model.isDirectEditable('2026-04',today); } catch { today = '2026-05-03'; }
  const actor = 'Trần Thị B';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = value => value === null || value === undefined ? '—' : value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const fromText = text => /^(?:0|[1-9]\d*)(?:\.\d{3})*$/.test(text) ? text.replaceAll('.', '') : null;
  const signedText = text => /^[+-]?(?:0|[1-9]\d*)(?:\.\d{3})*$/.test(text) ? text.replaceAll('.', '').replace(/^\+/, '') : text;
  const dateIso = text => { const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text); return m ? `${m[3]}-${m[2]}-${m[1]}` : null; };
  const dateLabel = iso => iso ? `${iso.slice(8)}/${iso.slice(5,7)}/${iso.slice(0,4)}` : '—';
  const monthLabel = key => `${key.slice(5)}.${key.slice(0,4)}`;
  const line = (id, price, date, pasted = null) => ({id,unitPriceVnd:price,otherFeeVnd:null,plugFeeVnd:null,escortFeeVnd:null,pastedAmountVnd:pasted,carrier:'WH',date,from:'PHAN THIET',to:'SHEKOU'});
  const base = {
    opening:{beforeKey:'before-2026-01',beforeBalanceVnd:'20000000',months:[
      {key:'2026-01',endOfMonthVnd:'40000000',remainingVnd:'20000000',lines:[line('DEMO-101','20000000','15/01/2026')]},
      {key:'2026-02',endOfMonthVnd:'70000000',remainingVnd:'30000000',lines:[line('DEMO-102','30000000','15/02/2026')]},
      {key:'2026-03',endOfMonthVnd:'95000000',remainingVnd:'25000000',lines:[line('DEMO-104','25000000','15/03/2026')]},
    ]},
    months:[{key:'2026-04',lines:[line('DEMO-105','40000000','08/04/2026'),line('DEMO-106','30000000','12/04/2026'),line('DEMO-107','20000000','18/04/2026'),line('DEMO-103',null,'22/04/2026')]}],
    adjustments:[],receipts:[{id:'CT-CHO-05',monthKey:'2026-04',receivedOn:null,method:null,ref:'CT-CHO-05',amountVnd:'5000000'}]
  };
  const simpleBook = (carry, prices, received) => ({opening:{beforeKey:'before-2026-04',beforeBalanceVnd:carry,months:[]},months:[{key:'2026-04',lines:prices.map((price,index)=>line(`SAMPLE-${index + 1}`,price,'18/04/2026'))}],adjustments:[],receipts:received ? [{id:'SAMPLE-THU',monthKey:'2026-04',receivedOn:'2026-04-20',method:'Chuyển khoản',ref:'SAMPLE-THU',amountVnd:received}] : []});
  const books = {
    KHACH_MAU:base, KHACH_B:simpleBook('18000000',['122000000',...Array(8).fill('0')],'40000000'),
    KHACH_C:simpleBook('0',[],null), KHACH_D:simpleBook('30000000',['60000000','0','0'],'20000000'),
    KHACH_E:simpleBook('12000000',['45000000','0'],null)
  };
  const kinds = {KHACH_MAU:'thanh long',KHACH_B:'thanh long',KHACH_C:'thanh long',KHACH_D:'mít',KHACH_E:'mít'};
  const state = {customer:null,month:'2026-04',filter:'all',search:'',history:false,historyMonth:'all',historyActor:'all',payForm:true,payError:'',adjForm:false,adjError:[],allocation:null,logs:[],before:{},pasteError:''};
  const book = () => structuredClone(books[state.customer]);
  const computed = customer => { const b = structuredClone(books[customer]); return {book:b,chain:model.monthChain(b),allocation:model.allocate(b)}; };
  const last = rows => rows.at(-1);
  const money = value => value === null ? '—' : fmt(value);
  const fieldMoney = value => value === null ? '—' : fmt(model.lineAmount({unitPriceVnd:value,otherFeeVnd:null,plugFeeVnd:null,escortFeeVnd:null}));
  const stamp = () => `${dateLabel(today)} ${new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',hour12:false})}`;
  const log = item => state.logs.unshift({actor,at:stamp(),customer:state.customer,...item});
  function refresh(next) { const chain = model.monthChain(next); const allocation = model.allocate(next); books[state.customer] = next; return {chain,allocation}; }
  function warn(id, text, number) { const tip = `tip-${id}`; return `<span class="tipwrap"><button type="button" class="warn" data-warn="${escape(id)}" aria-label="Dòng ${number}: ${escape(text)}" aria-describedby="${tip}"><span>${number}</span><span class="glyph" aria-hidden="true">!</span></button><span role="tooltip" class="tip" id="${tip}">${escape(text)}</span></span>`; }
  function locked(key) { return !model.isDirectEditable(key,today); }
  function lockBadge(key) {
    const next = key.slice(5) === '12' ? '01' : ['01','02','03','04','05','06','07','08','09','10','11','12'].at(['01','02','03','04','05','06','07','08','09','10','11','12'].indexOf(key.slice(5))+1);
    if (locked(key)) return `<span class="tipwrap"><span class="badge b-past" tabindex="0" aria-describedby="lock-${key}">Đã khóa ⓘ</span><span class="tip" role="tooltip" id="lock-${key}">Hết ngày đệm 05/${next}. Muốn sửa số tháng này, bấm Ghi điều chỉnh.</span></span>`;
    if (key === today.slice(0,7)) return '';
    return `<span class="badge b-grace">Sửa được đến 05/${next}</span>`;
  }
  function renderTotal() {
    const rows = Object.keys(books).map(customer => ({customer,...computed(customer)}));
    const debt = rows.filter(({chain}) => last(chain).endOfMonthVnd > 0n).length;
    const advance = rows.filter(({chain}) => last(chain).endOfMonthVnd < 0n).length;
    const missing = rows.filter(({chain}) => last(chain).missingPriceIds.length).length;
    const filters = [['all',`Tất cả (${rows.length})`],['debt',`Còn nợ (${debt})`],['advance',`Ứng trước (${advance})`],['missing',`Thiếu giá (${missing})`]];
    const visible = rows.filter(({customer,chain}) => {
      const row=last(chain); return (state.filter==='all'||state.filter==='debt'&&row.endOfMonthVnd>0n||state.filter==='advance'&&row.endOfMonthVnd<0n||state.filter==='missing'&&row.missingPriceIds.length) && `${customer} ${kinds[customer]}`.toLowerCase().includes(state.search.toLowerCase());
    });
    root.innerHTML = `<div class="top"><h1>Công nợ phải thu</h1><select aria-label="Tháng"><option>Tháng 04.2026</option></select><span class="sp"></span><span class="muted">${actor}</span></div>
      <div class="bar">${filters.map(([key,label])=>`<button class="fb ${state.filter===key?'on':''}" data-action="filter" data-value="${key}">${label}</button>`).join('')}<span class="sp"></span><input class="search" type="search" placeholder="Tìm khách hoặc loại hàng…" aria-label="Tìm khách hoặc loại hàng" value="${escape(state.search)}"></div>
      <div class="sheet"><table><thead><tr><th style="width:200px">Khách</th><th class="r" style="width:160px">Chuyển sang</th><th class="r" style="width:160px">Phát sinh</th><th class="r" style="width:150px">Đã ứng trước / đã thu</th><th class="r" style="width:170px">Còn phải thu cuối tháng</th><th class="r" style="width:70px">Cont</th><th>Cần xử lý</th></tr></thead><tbody>
      ${['thanh long','mít'].map(kind=>{const group=visible.filter(row=>kinds[row.customer]===kind);return group.length?`<tr class="grp"><td colspan="7">${kind==='mít'?'Mít':'Thanh long'} (${group.length})</td></tr>${group.map(({customer,chain})=>{const row=last(chain);return `<tr><td><button class="lnk" data-action="open-book" data-value="${customer}">${customer}</button></td><td class="r">${fmt(row.carryVnd)}</td><td class="r">${row.lineCount?fmt(row.chargesVnd):'—'}</td><td class="r">${row.receivedVnd===0n?'—':fmt(row.receivedVnd)}</td><td class="r b">${fmt(row.endOfMonthVnd)}</td><td class="r">${row.lineCount||'—'}</td><td>${row.missingPriceIds.length?`<span class="todo">${row.missingPriceIds.length} thiếu giá</span>`:''}</td></tr>`}).join('')}`:''}).join('')}</tbody></table></div>`;
  }
  function renderPayment(b,alloc,key) {
    const receipts=b.receipts.filter(r=>r.monthKey===key);
    const form=state.payForm?`<div class="row"><label style="flex:0 0 124px">Ngày nhận<input data-pay="date" placeholder="dd/mm/yyyy"></label><label style="flex:1">Cách thu<select data-pay="method">${['Chuyển khoản','Cấn trừ','Ứng trước','Khác'].map(x=>`<option>${x}</option>`).join('')}</select></label></div><div class="row"><label style="flex:1">Tham chiếu<input data-pay="ref"></label></div><div class="row" style="align-items:flex-end"><label style="flex:1">Số tiền<input data-pay="amount" inputmode="numeric" style="text-align:right" aria-describedby="loi-so-tien" aria-invalid="${!!state.payError}" class="${state.payError?'invalid':''}"></label><button class="btn pri" data-action="pay-save">Lưu</button></div>${state.payError?`<div id="loi-so-tien" class="tipbox" role="alert">${escape(state.payError)}</div>`:'<div id="loi-so-tien" class="hidden"></div>'}`:`<button class="btn" style="width:100%;margin-bottom:8px" data-action="add-pay">＋ Thêm khoản thu</button>`;
    return `${form}${receipts.filter(r=>r.receivedOn).map(r=>{const result=alloc.receipts.find(x=>x.id===r.id);return `<div class="paycard"><span class="kv"><span>${dateLabel(r.receivedOn)} · ${escape(r.ref)}</span><b>${money(r.amountVnd)}</b></span><span class="kv muted"><span>${escape(r.method)}</span><button data-action="allocation" data-value="${escape(r.id)}" aria-expanded="${state.allocation===r.id}">Phân bổ ⌄</button></span>${state.allocation===r.id?`<div class="paylist">${result.allocations.map(a=>`<span class="kv"><span>${a.key===b.opening.beforeKey?'Trước 01.2026':monthLabel(a.key)}</span><span>${fmt(a.amountVnd)}</span></span>`).join('')}${result.overpaymentVnd?`<span class="kv"><span>Ứng trước</span><span>${fmt(result.overpaymentVnd)}</span></span>`:''}</div>`:''}</div>`}).join('')}${receipts.filter(r=>!r.receivedOn).map(r=>`<div style="border-top:1px solid #dbe4f0;padding-top:6px;color:#526781"><span class="kv"><span>${escape(r.ref)} · chờ ngày nhận</span><span>${money(r.amountVnd)}</span></span></div>`).join('')}`;
  }
  const headers = [['48px','No.'],['106px','CONTAINER NO'],['88px','CARRIER'],['108px','DATE'],['108px','FROM'],['80px','TO'],['64px','OTHER FEE'],['60px','PLUG FEE'],['68px','ESCORT FEE'],['104px','UNIT PRICE'],['118px','TOTAL (VND)'],['276px','NGÀY TT (STK) · ĐÃ THU']];
  function displayLines(b,key) { return [...b.opening.months,...b.months].find(m=>m.key===key)?.lines || []; }
  function renderLine(item,index,chain,editable) {
    const amount=model.lineAmount(item);
    const mismatch=chain.mismatches.find(x=>x.id===item.id);
    const missing=chain.missingPriceIds.includes(item.id)||amount===null;
    const tip=missing?'Chưa có đơn giá · chưa tính vào phát sinh':mismatch?`Sheet ghi ${fmt(mismatch.pastedVnd)}, hệ thống cộng ${fmt(mismatch.computedVnd)}, lệch ${fmt(mismatch.diffVnd)}. Kiểm lại đơn giá và phí.`:'';
    const unit=item.unitPriceVnd===null?null:model.lineAmount({unitPriceVnd:item.unitPriceVnd,otherFeeVnd:null,plugFeeVnd:null,escortFeeVnd:null});
    const price=editable||missing?`<input class="${unit===null?'cellin':'bare'}" data-edit="price" data-line="${escape(item.id)}" value="${unit===null?'':fmt(unit)}" placeholder="nhập giá" aria-label="Đơn giá ${escape(item.id)}" ${editable?'':'readonly'}>`:fmt(unit);
    const fee=field=>{const value=item[field];const shown=value===null?'':fmt(model.lineAmount({unitPriceVnd:value,otherFeeVnd:null,plugFeeVnd:null,escortFeeVnd:null}));return editable?`<input class="bare" data-edit="${field}" data-line="${escape(item.id)}" value="${shown}" placeholder="—" aria-label="${field} ${escape(item.id)}">`:shown||'—';};
    return `<tr class="${missing?'miss':mismatch?'mismatch':index>3?'added':''}"><td>${tip?warn(item.id,tip,index+1):index+1}</td><td><button class="lnk" type="button">${escape(item.id)}</button></td><td>${escape(item.carrier||'—')}</td><td>${escape(item.date||'—')}</td><td>${escape(item.from||'—')}</td><td>${escape(item.to||'—')}</td><td class="muted">${fee('otherFeeVnd')}</td><td class="muted">${fee('plugFeeVnd')}</td><td class="muted">${fee('escortFeeVnd')}</td><td class="r">${price}</td><td class="r b">${fmt(amount)}</td></tr>`;
  }
  function renderAdjustment(b,key) {
    const lines=displayLines(b,key);
    if (!state.adjForm) return '';
    return `<tr class="adj"><td colspan="3"><label>Chuyến<select data-adj="line">${lines.map(x=>`<option>${escape(x.id)}</option>`).join('')}<option value="">Cả tháng, không gắn chuyến</option></select></label></td><td colspan="6"><label>Lý do<input data-adj="reason"></label></td><td colspan="2"><label>Số tiền<input data-adj="amount" style="text-align:right" aria-describedby="adj-errors"></label></td><td class="mcol"><span style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-action="adjust-cancel">Hủy</button><button class="btn pri" data-action="adjust-save">Lưu</button></span></td></tr><tr class="${state.adjError.length?'':'hidden'}"><td colspan="12" id="adj-errors" role="alert" class="error">${state.adjError.map(escape).join(' ')}</td></tr>`;
  }
  function renderBlock(b,row,alloc) {
    const key=row.key, lines=displayLines(b,key), editable=model.isDirectEditable(key,today)&&row.source==='web';
    const old=state.before[key];
    const adjustments=b.adjustments.filter(a=>a.monthKey===key);
    const warning=[...row.missingPriceIds,...row.mismatches].length;
    const receipt=row.source==='web';
    return `<section class="blk" aria-label="Sổ chi tiết tháng ${monthLabel(key)}"><div class="bh"><span class="t">SỔ CHI TIẾT THÁNG ${monthLabel(key)}</span>${lockBadge(key)}<span class="sp"></span>${warning?`<span class="badge b-wait">${row.mismatches.length?`${warning} dòng cần kiểm`:`${warning} dòng thiếu giá`}</span>`:''}${locked(key)?`<button class="btn ${state.adjForm?'pri':''}" data-action="open-adjust" aria-expanded="${state.adjForm}">＋ Ghi điều chỉnh</button>`:''}</div><table><colgroup>${headers.map(([width])=>`<col style="width:${width}">`).join('')}</colgroup><thead><tr>${headers.map(([,label],i)=>`<th class="${i===11?'mcol':i>=9?'r':''}">${label}</th>`).join('')}</tr></thead><tbody><tr class="carry"><td colspan="11" class="b">Chuyển sang</td><td class="mcol r b">${fmt(row.carryVnd)}${old&&old.carryVnd!==row.carryVnd?` <s>${fmt(old.carryVnd)}</s>`:''}</td></tr>
      ${lines.map((item,index)=>{const html=renderLine(item,index,row,editable);return index===0&&receipt?html.replace('</tr>',`<td rowspan="${lines.length+(editable?1:0)}" class="recv">${renderPayment(b,alloc,key)}</td></tr>`):html}).join('')}
      ${receipt&&!lines.length?`<tr><td colspan="11"></td><td class="recv">${renderPayment(b,alloc,key)}</td></tr>`:''}
      ${adjustments.map(a=>{const amount=model.monthChain({...b,adjustments:[a]}).find(x=>x.key===key).adjustmentsVnd;return `<tr style="background:#f6f2fe"><td colspan="3"><span class="badge b-adj">Điều chỉnh</span> <span class="muted">· ${escape(a.lineId||'Cả tháng')}</span></td><td colspan="7" style="white-space:normal">${escape(a.reason)}</td><td class="r b">${amount<0n?'':'+'}${fmt(amount)}</td><td class="mcol"></td></tr>`}).join('')}
      ${state.adjForm?renderAdjustment(b,key):''}
      ${editable?`<tr class="paste"><td class="muted">${lines.length+1}</td><td colspan="10"><div class="pastebox" contenteditable="true" role="textbox" tabindex="0" aria-label="Dán từ Sheet" data-action="inline-paste"></div></td></tr>`:''}
      ${state.pasteError&&editable?`<tr><td colspan="12" class="error" role="alert">${escape(state.pasteError)}</td></tr>`:''}
      <tr class="tot"><td colspan="4">TỔNG · ${row.lineCount} cont</td><td colspan="6"></td><td class="r">${fmt(row.monthTotalVnd)}</td><td class="mcol" style="white-space:normal;line-height:1.25;padding:4px 8px"><span class="kv"><span style="font-weight:600">Đã thu</span><span class="${row.receivedVnd===null||row.receivedVnd===0n?'muted':''}">${row.receivedVnd===null||row.receivedVnd===0n?'—':fmt(row.receivedVnd)}</span></span><span class="kv" style="font-size:17px"><span>Còn phải thu</span><span>${fmt(row.endOfMonthVnd)}</span></span>${old&&old.endOfMonthVnd!==row.endOfMonthVnd?`<span class="kv"><span></span><s>${fmt(old.endOfMonthVnd)}</s></span>`:''}</td></tr></tbody></table></section>`;
  }
  function renderHistory() {
    if (!state.history) return '';
    const logs=state.logs.filter(x=>x.customer===state.customer&& (state.historyMonth==='all'||x.monthKey===state.historyMonth) && (state.historyActor==='all'||x.actor===state.historyActor));
    return `<div class="drawer-bg" data-action="close-history"></div><aside class="drawer" aria-label="Lịch sử sửa"><div class="drawer-head"><b style="font-size:19px">Lịch sử sửa</b><span class="sp"></span><button class="btn" data-action="close-history">Đóng</button></div><div style="display:flex;gap:8px;padding:10px 0"><select aria-label="Tháng" data-history="month"><option value="all">Mọi tháng</option>${['2026-04','2026-03','2026-02','2026-01'].map(x=>`<option value="${x}" ${state.historyMonth===x?'selected':''}>${monthLabel(x)}</option>`).join('')}</select><select aria-label="Người sửa" data-history="actor"><option value="all">Mọi người</option><option>${actor}</option></select></div>${logs.map(x=>`<div class="history-item"><span class="kv"><b>${escape(x.at)} · ${escape(x.actor)}</b><span class="badge b-adj">${escape(x.type)}</span></span><div>Tháng ${x.monthKey.slice(5)} · ${escape(x.lineId||x.ref||'')} · <b>${escape(x.amount||'')}</b></div>${x.beforeText||x.afterText?`<div class="muted">${escape(x.beforeText||'—')} → ${escape(x.afterText||'—')}</div>`:''}${x.reason?`<div class="muted">Lý do: ${escape(x.reason)}</div>`:''}${x.allocBefore||x.allocAfter?`<div class="muted">Phân bổ trước: ${escape(x.allocBefore||'—')}<br>Phân bổ sau: ${escape(x.allocAfter||'—')}</div>`:''}</div>`).join('')}</aside>`;
  }
  function renderBook() {
    const {book:b,chain,allocation}=computed(state.customer);
    const current=chain.find(x=>x.key===state.month)||last(chain);
    const previous=chain.filter(x=>x.key<current.key);
    const next=chain.find(x=>x.key>current.key);
    root.innerHTML=`<div class="top"><button class="back" data-action="back">‹ Tổng</button><h1>${state.customer} · ${kinds[state.customer]}</h1><span class="sp"></span><span class="muted">${actor}</span><button class="btn" data-action="open-history" aria-expanded="${state.history}">Lịch sử sửa</button></div><div class="hist"><span class="muted" style="font-weight:600">Tháng trước</span>${previous.map(row=>`<button class="mb" data-action="expand-month" data-value="${row.key}" aria-expanded="false"><span aria-hidden="true">›</span><span>${monthLabel(row.key)}</span><b>${fmt(row.endOfMonthVnd)}</b>${state.before[row.key]&&state.before[row.key].endOfMonthVnd!==row.endOfMonthVnd?`<s>${fmt(state.before[row.key].endOfMonthVnd)}</s>`:''}</button>`).join('')}</div>${renderBlock(b,current,allocation)}${next?`<button class="next" data-action="expand-month" data-value="${next.key}" aria-expanded="false"><span aria-hidden="true">›</span><b>THÁNG ${monthLabel(next.key)}</b><span class="muted">chuyển sang</span><b>${fmt(next.carryVnd)}</b>${state.before[next.key]&&state.before[next.key].carryVnd!==next.carryVnd?`<s>${fmt(state.before[next.key].carryVnd)}</s>`:''}<span class="sp"></span><span class="muted">còn phải thu</span><b>${fmt(next.endOfMonthVnd)}</b>${state.before[next.key]&&state.before[next.key].endOfMonthVnd!==next.endOfMonthVnd?`<s>${fmt(state.before[next.key].endOfMonthVnd)}</s>`:''}</button>`:''}${renderHistory()}`;
  }
  function render() { if (state.customer) renderBook(); else renderTotal(); }
  root.addEventListener('click', event => {
    const button=event.target.closest('[data-action]'); if(!button)return;
    const action=button.dataset.action, value=button.dataset.value;
    if(action==='open-book'){state.customer=value;state.month='2026-04';render();root.querySelector('[data-pay="date"]')?.focus();}
    if(action==='back'){state.customer=null;state.history=false;render();}
    if(action==='filter'){state.filter=value;render();}
    if(action==='expand-month'){state.month=value;state.adjForm=false;render();root.querySelector('[data-action="open-adjust"]')?.focus();}
    if(action==='open-adjust'){state.adjForm=true;state.adjError=[];render();root.querySelector('[data-adj="line"]')?.focus();}
    if(action==='adjust-cancel'){state.adjForm=false;state.adjError=[];render();}
    if(action==='open-history'){state.history=true;render();root.querySelector('.drawer [data-action="close-history"]')?.focus();}
    if(action==='close-history'){state.history=false;render();root.querySelector('[data-action="open-history"]')?.focus();}
    if(action==='add-pay'){state.payForm=true;render();root.querySelector('[data-pay="date"]')?.focus();}
    if(action==='allocation'){state.allocation=state.allocation===value?null:value;render();}
    if(action==='pay-save')savePayment();
    if(action==='adjust-save')saveAdjustment();
  });
  root.addEventListener('input',event=>{if(event.target.matches('.search')){const pos=event.target.selectionStart;state.search=event.target.value;render();const field=root.querySelector('.search');field.focus();field.setSelectionRange(pos,pos);} if(event.target.matches('[data-pay="amount"]')&&state.payError){state.payError='';event.target.classList.remove('invalid');event.target.setAttribute('aria-invalid','false');const error=root.querySelector('#loi-so-tien');error.textContent='';error.classList.add('hidden');}});
  root.addEventListener('change',event=>{if(event.target.matches('[data-history="month"]')){state.historyMonth=event.target.value;render();}if(event.target.matches('[data-history="actor"]')){state.historyActor=event.target.value;render();}if(event.target.matches('[data-edit]'))editPrice(event.target);});
  root.addEventListener('paste',event=>{if(event.target.matches('[data-action="inline-paste"]')){event.preventDefault();pasteLines(event.clipboardData.getData('text/plain'));}});
  function showPayError(message){state.payError=message;const error=root.querySelector('#loi-so-tien');error.classList.remove('hidden');error.classList.add('tipbox');error.textContent=message;root.querySelector('[data-pay="amount"]').setAttribute('aria-invalid','true');}
  function savePayment() {
    const date=root.querySelector('[data-pay="date"]'),method=root.querySelector('[data-pay="method"]'),ref=root.querySelector('[data-pay="ref"]'),amount=root.querySelector('[data-pay="amount"]');
    const value=fromText(amount.value.trim());
    if(!value||value==='0'){showPayError('Chỉ nhập số dương, ví dụ 120.000.000');amount.classList.add('invalid');return;}
    const iso=dateIso(date.value.trim());
    if(!iso||iso.slice(0,7)!==state.month||!ref.value.trim()){showPayError('Nhập ngày nhận trong tháng này và tham chiếu hợp lệ.');return;}
    const next=book(), id=ref.value.trim();
    if(next.receipts.some(r=>r.id===id)){showPayError('Tham chiếu đã có trong sổ.');return;}
    const receipt={id,monthKey:state.month,receivedOn:iso,method:method.value,ref:id,amountVnd:value};
    next.receipts.push(receipt);
    let result;try{result=refresh(next);}catch(error){showPayError(error.message);return;}
    state.payForm=false;state.payError='';state.allocation=null;
    log({type:'Ghi khoản thu',monthKey:state.month,ref:id,amount:fmt(value)});
    if(next.adjustments.length){const unadjusted=structuredClone(next);unadjusted.adjustments=[];const prior=model.allocate(unadjusted);for(const entry of state.logs.filter(x=>x.customer===state.customer&&x.type==='Điều chỉnh')){entry.allocBefore=allocationText(prior,id);entry.allocAfter=allocationText(result.allocation,id);}}
    render();
  }
  const allocationText=(allocation,id)=>allocation.receipts.find(r=>r.id===id)?.allocations.map(a=>`${a.key}: ${fmt(a.amountVnd)}`).join(' · ')||'—';
  function saveAdjustment(){
    const next=book(),lineId=root.querySelector('[data-adj="line"]').value||null,reason=root.querySelector('[data-adj="reason"]').value,raw=root.querySelector('[data-adj="amount"]').value.trim();
    const adjustment={id:`ADJ-${next.adjustments.length+1}`,monthKey:state.month,lineId,reason,amountVnd:signedText(raw)};
    const validation=model.validateAdjustment(adjustment,next);
    if(!validation.ok){state.adjError=validation.reasons;const error=root.querySelector('#adj-errors');error.parentElement.classList.remove('hidden');error.textContent=validation.reasons.join(' ');return;}
    const beforeChain=model.monthChain(next),beforeAlloc=model.allocate(next);next.adjustments.push(adjustment);
    let afterChain,afterAlloc;try{afterChain=model.monthChain(next);afterAlloc=model.allocate(next);}catch(error){state.adjError=[error.message==='Negative debt bucket'?'Điều chỉnh giảm làm khoản nợ tháng âm.':error.message];const message=root.querySelector('#adj-errors');message.parentElement.classList.remove('hidden');message.textContent=state.adjError.join(' ');return;}
    for(const row of beforeChain){if(afterChain.find(x=>x.key===row.key)?.endOfMonthVnd!==row.endOfMonthVnd||afterChain.find(x=>x.key===row.key)?.carryVnd!==row.carryVnd)state.before[row.key]=row;}
    books[state.customer]=next;state.adjForm=false;state.adjError=[];
    const adjusted=model.monthChain({...next,adjustments:[adjustment]}).find(x=>x.key===state.month).adjustmentsVnd;
    log({type:'Điều chỉnh',monthKey:state.month,lineId,reason,amount:`${adjusted<0n?'':'+'}${fmt(adjusted)}`,beforeText:fmt(beforeChain.find(x=>x.key===state.month).endOfMonthVnd),afterText:fmt(afterChain.find(x=>x.key===state.month).endOfMonthVnd),allocBefore:beforeAlloc.receipts.map(r=>allocationText(beforeAlloc,r.id)).join(' / '),allocAfter:afterAlloc.receipts.map(r=>allocationText(afterAlloc,r.id)).join(' / ')});
    render();
  }
  function editPrice(input){
    if(locked(state.month))return;
    const next=book(),item=next.months.find(x=>x.key===state.month)?.lines.find(x=>x.id===input.dataset.line);if(!item)return;
    const raw=input.value.trim(),value=raw===''?null:fromText(raw);
    if(raw!==''&&value===null){input.setAttribute('aria-invalid','true');return;}
    const field=input.dataset.edit==='price'?'unitPriceVnd':input.dataset.edit;
    const old=item[field];item[field]=value;
    if(old===value)return;
    try{model.monthChain(next);model.allocate(next);}catch(error){input.setAttribute('aria-invalid','true');return;}
    const labels={unitPriceVnd:'UNIT PRICE',otherFeeVnd:'OTHER FEE',plugFeeVnd:'PLUG FEE',escortFeeVnd:'ESCORT FEE'};
    books[state.customer]=next;log({type:'Sửa ô',monthKey:state.month,lineId:`${item.id} · ${labels[field]}`,beforeText:fieldMoney(old),afterText:fieldMoney(value)});render();
  }
  function pasteLines(text){
    if(locked(state.month))return;
    const rows=text.replace(/\r/g,'').replace(/\n$/,'').split('\n');
    if(rows.length>50){state.pasteError='Chỉ dán tối đa 50 dòng.';render();return;}
    const next=book(),month=next.months.find(x=>x.key===state.month);
    const parsed=[];
    for(const row of rows){const cells=row.split('\t');if(cells.length!==11){state.pasteError='Mỗi dòng cần đúng 11 cột.';render();return;}
      const [mark,id,carrier,date,from,to,other,plug,escort,unit,pasted]=cells;
      if(!id.trim()||month.lines.some(x=>x.id===id.trim())||parsed.some(x=>x.id===id.trim())){state.pasteError='Mã chuyến trống hoặc đã có.';render();return;}
      const fields=[other,plug,escort,unit,pasted].map(x=>x.trim()===''?null:fromText(x.trim()));
      if([other,plug,escort,unit,pasted].some((x,i)=>x.trim()!==''&&fields[i]===null)){state.pasteError='Số tiền trong dòng dán sai định dạng.';render();return;}
      parsed.push({id:id.trim(),carrier:carrier||'—',date,from,to,otherFeeVnd:fields[0],plugFeeVnd:fields[1],escortFeeVnd:fields[2],unitPriceVnd:fields[3],pastedAmountVnd:fields[4],mark});
    }
    month.lines.push(...parsed);
    try{model.monthChain(next);model.allocate(next);}catch(error){state.pasteError=error.message;render();return;}
    books[state.customer]=next;state.pasteError='';log({type:'Dán lô',monthKey:state.month,lineId:parsed.map(x=>x.id).join(', '),amount:`${parsed.length} dòng`});render();
  }
  render();
})();
