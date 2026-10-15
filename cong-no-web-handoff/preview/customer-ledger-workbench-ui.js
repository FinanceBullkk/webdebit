/* Browser adapter for synthetic in-memory workbench only. */
(() => {
  'use strict';
  const workbench=CustomerLedgerWorkbench.createWorkbench();
  const $=id=>document.getElementById(id);
  const fmt=n=>new Intl.NumberFormat('en-US').format(n);
  const money=n=>n===null || n===undefined || n==='' ? '—' : fmt(n);
  const day=s=>s ? s.slice(8,10)+'/'+s.slice(5,7)+'/'+s.slice(0,4) : '—';
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fieldNames={date:'Ngày chuyến · xe nhập kho',container:'Số container',carrier:'Hãng tàu / số xe',shipper:'Shipper',origin:'Nơi đi',destination:'Nơi đến',otherFee:'Phí khác',tractionFee:'Phí đầu kéo / điện',insuranceFee:'Bảo hiểm',price:'Đơn giá',approvedTotal:'Thành tiền dự kiến'};
  const columns=['date','container','carrier','shipper','origin','destination','price','otherFee','tractionFee','insuranceFee','approvedTotal'];
  const label=p=>'THÁNG '+p.slice(5)+'/'+p.slice(0,4);
  let state={period:'all',asOf:'2026-04-30'};
  let view;
  function rowStatus(s){return s.status==='posted' ? '' : `<span class="status">${s.status==='waiting_price'?'Chờ giá':'Chờ duyệt'}</span>`;}
  function shipmentRow(s,i){
    const values=[i+1,`<button type="button" class="link" data-detail="shipment:${escape(s.id)}">${escape(s.container||'Khoản chung')}</button>`,escape(s.carrier)||'—',escape(s.shipper)||'—',day(s.date),escape(s.origin)||'—',escape(s.destination)||'—',money(s.otherFee),money(s.tractionFee),money(s.insuranceFee),money(s.price),s.status==='posted'?money(s.approvedTotal):(s.status==='waiting_price'?'Chờ giá':money(workbench.estimate(s)))];
    return `<tr id="shipment-${escape(s.id)}">${values.map((v,j)=>`<td class="${j>=7?'amount':''}">${v}${j===11?rowStatus(s):''}</td>`).join('')}</tr>`;
  }
  function draftRow(r){
    const cells=columns.map(f=>`<td><input data-edit="${f}" data-id="${escape(r.id)}" data-period="${r.period}" aria-label="${escape(fieldNames[f])} · ${escape(r.id)}" class="${f==='date'||f==='container'?'wide':''}" value="${escape(r[f])}"></td>`).join('');
    const notes=[...r.errors.map(e=>`<span class="error">${escape(e)}</span>`),...r.warnings.map(e=>`<span class="warning">${escape(e)}</span>`)].join('<br>');
    return `<tr><td><input type="checkbox" data-select="${escape(r.id)}" aria-label="Chọn dòng ${escape(r.id)}"></td>${cells}<td>${notes||'<span class="status draft">Nháp</span>'}</td></tr>`;
  }
  function month(m,index){
    const opened=document.getElementById('month-'+m.period)?.open;
    const open=opened===undefined ? index===view.months.length-1 : opened;
    const p=m.period;
    const srows=m.shipments.map(shipmentRow).join('')||'<tr><td colspan="12">Không có chuyến tại ngày chốt.</td></tr>';
    const payments=m.payments.map(pay=>`<tr id="payment-${escape(pay.id)}"><td><button class="link" type="button" data-detail="payment:${escape(pay.id)}">${day(pay.date)}</button></td><td>${pay.kind==='receipt'?'Thực nhận':'Cấn trừ'}${pay.status!=='posted'?'<span class="status">Chưa xác nhận / chờ duyệt</span>':''}</td><td class="amount">${money(pay.amount)}</td></tr>`).join('')||'<tr><td colspan="3">Chưa có khoản thanh toán.</td></tr>';
    return `<details id="month-${p}" class="month card" ${open?'open':''}><summary><span class="month-title">${label(p)}</span><span class="month-balance">Còn nợ kỳ: ${fmt(m.balance)}</span></summary><div class="month-body">
      <div class="table-heading"><h3>Chuyến hàng</h3><button type="button" class="secondary" data-action="open-editor" data-period="${p}">＋ Nhập chuyến</button></div><div class="table-scroll"><table class="shipment-table"><thead><tr>${['STT','Số container','Hãng tàu / số xe','Shipper','Ngày chuyến','Nơi đi','Nơi đến','Phí khác','Phí đầu kéo / điện','Bảo hiểm','Đơn giá','Thành tiền'].map((h,i)=>`<th class="${i>=7?'amount':''}">${h}</th>`).join('')}</tr></thead><tbody>${srows}</tbody></table></div>
      <details class="editor" data-editor="${p}"><summary>Bảng nhập chuyến · ${label(p)}</summary><div class="editor-inner"><p class="editor-note">Dán theo thứ tự cột bên dưới: ngày → container → hãng/xe → shipper → nơi đi → nơi đến → đơn giá → phí khác → phí đầu kéo/điện → bảo hiểm → thành tiền. Giữ nguyên ô trống; điền 0 khi đã xác nhận không phát sinh phí.</p><textarea class="paste-area" data-paste="${p}" aria-label="Dán bảng TSV ${p}" placeholder="2026-02-11\tDEMO-NEW\t\t\t\t\t\t\t\t\t"></textarea><div class="editor-actions"><button type="button" class="secondary" data-action="paste" data-period="${p}">Dán dòng</button><button type="button" class="secondary" data-action="add" data-period="${p}">Thêm dòng</button><label>Đơn giá <input data-bulk="price" data-period="${p}" inputmode="numeric" placeholder="VND"></label><label>Phí khác <input data-bulk="otherFee" data-period="${p}" inputmode="numeric" placeholder="VND"></label><label>Phí đầu kéo/điện <input data-bulk="tractionFee" data-period="${p}" inputmode="numeric" placeholder="VND"></label><label>Bảo hiểm <input data-bulk="insuranceFee" data-period="${p}" inputmode="numeric" placeholder="VND"></label><button type="button" class="secondary" data-action="fill" data-period="${p}">Điền dòng đã chọn</button><button type="button" class="primary" data-action="save" data-period="${p}">Lưu nháp trong tab</button></div><div class="table-scroll"><table class="draft-table"><thead><tr><th>Chọn</th>${columns.map(f=>`<th>${escape(fieldNames[f])}</th>`).join('')}<th>Kiểm tra</th></tr></thead><tbody>${m.drafts.map(draftRow).join('')||'<tr><td colspan="13">Chưa có dòng nhập.</td></tr>'}</tbody></table></div><p class="feedback" data-feedback="${p}" aria-live="polite"></p></div></details>
      <div class="section-spacer"></div><div class="table-heading"><h3>Thanh toán cho tháng này</h3><button type="button" class="secondary" data-action="open-receipt" data-period="${p}">＋ Thanh toán</button></div><div class="table-scroll"><table class="payment-table"><thead><tr><th>Ngày trả</th><th>Hình thức</th><th class="amount">Số tiền phân bổ cho tháng này</th></tr></thead><tbody>${payments}</tbody></table></div>
      <div class="month-summary"><div><span>DƯ ĐẦU KỲ</span><strong>${fmt(m.opening)}</strong></div><div><span>PHÁT SINH</span><strong>${fmt(m.charge)}</strong></div><div><span>THANH TOÁN &amp; CẤN TRỪ</span><strong>${fmt(m.paid)}</strong></div><div><span>CÒN NỢ</span><strong class="balance">${fmt(m.balance)}</strong></div></div></div></details>`;
  }
  function render(){
    const openEditors=[...document.querySelectorAll('[data-editor][open]')].map(e=>e.dataset.editor);
    const openMonths=[...document.querySelectorAll('.month[open]')].map(e=>e.id);
    view=workbench.snapshot(state);
    $('all-balance').textContent=fmt(view.allBalance);
    $('visible-card').hidden=state.period==='all';
    $('visible-balance').textContent=fmt(view.visibleBalance);
    $('visible-label').textContent=state.period==='all'?'':label(state.period)+' · đến '+day(state.asOf);
    const price=view.months.reduce((n,m)=>n+m.shipments.filter(s=>s.status==='waiting_price').length,0);
    const receipt=view.months.reduce((n,m)=>n+m.payments.filter(p=>p.status!=='posted').length,0);
    $('pending-line').hidden=price+receipt===0;
    $('pending-price').hidden=price===0;
    $('pending-receipt').hidden=receipt===0;
    $('pending-price').textContent=price+' chuyến chờ giá';
    $('pending-receipt').textContent=receipt+' khoản thu chờ xác nhận';
    $('pending-price').href='#shipment-'+(view.months.flatMap(m=>m.shipments).find(s=>s.status==='waiting_price')?.id||'');
    $('pending-receipt').href='#payment-'+(view.months.flatMap(m=>m.payments).find(p=>p.status!=='posted')?.id||'');
    $('months').innerHTML=view.months.length?view.months.map(month).join(''):'<div class="card notice">Chưa có dữ liệu tại ngày chốt này.</div>';
    for(const id of openMonths){const e=document.getElementById(id);if(e)e.open=true;}
    for(const p of openEditors){const e=document.querySelector(`[data-editor="${p}"]`);if(e)e.open=true;}
  }
  $('filters').addEventListener('submit',event=>{
    event.preventDefault();
    try{const next={period:$('period').value,asOf:$('as-of').value};workbench.snapshot(next);state=next;$('filter-error').textContent='';render();}
    catch(error){$('filter-error').textContent=error.message;}
  });
  for(const id of ['pending-price','pending-receipt'])$(id).addEventListener('click',event=>{
    const target=document.getElementById(event.currentTarget.hash.slice(1));
    if(!target)return;
    target.closest('.month').open=true;
    target.scrollIntoView({block:'center'});
  });
  $('months').addEventListener('paste',event=>{
    const cell=event.target.closest('[data-edit]');
    const text=event.clipboardData?.getData('text/plain');
    if(!cell || !text || !/[\t\r\n]/.test(text))return;
    event.preventDefault();
    const period=cell.dataset.period;
    const editor=cell.closest('.editor');
    const startColumn=columns.indexOf(cell.dataset.edit);
    const rows=text.replace(/\r/g,'').replace(/\n$/,'').split('\n').map(line=>line.split('\t'));
    if(rows.length>50 || rows.some(row=>startColumn+row.length>columns.length)){
      editor.querySelector('[data-feedback]').textContent='Vùng dán vượt 50 dòng hoặc quá số cột. Chưa thay đổi dữ liệu.';
      return;
    }
    const existing=view.months.find(m=>m.period===period)?.drafts||[];
    const startRow=existing.findIndex(r=>r.id===cell.dataset.id);
    rows.forEach((values,i)=>{
      const target=existing[startRow+i] || workbench.addDraft(period);
      const update=Object.fromEntries(values.map((value,j)=>[columns[startColumn+j],value]));
      workbench.updateDraft(period,target.id,update);
    });
    render();
  });
  $('months').addEventListener('input',event=>{
    const target=event.target;
    if(target.dataset.edit)workbench.updateDraft(target.dataset.period,target.dataset.id,{[target.dataset.edit]:target.value});
  });
  $('months').addEventListener('click',event=>{
    const button=event.target.closest('[data-action]');
    if(!button)return;
    const p=button.dataset.period, action=button.dataset.action;
    const editor=button.closest('.editor');
    const feedback=editor?.querySelector('[data-feedback]');
    try{
      if(action==='open-editor'){const target=document.querySelector(`[data-editor="${p}"]`);target.open=true;target.scrollIntoView({block:'nearest'});return;}
      if(action==='open-receipt'){$('receipt-editor').hidden=false;$('receipt-period').value=label(p);$('receipt-editor').scrollIntoView({block:'nearest'});return;}
      if(action==='add')workbench.addDraft(p);
      if(action==='paste'){
        const text=editor.querySelector('[data-paste]').value;
        const rows=workbench.paste(p,text);
        feedback.textContent=`Đã thêm ${rows.length} dòng nháp; chưa ảnh hưởng số dư.`;
      }
      if(action==='fill'){
        const ids=[...editor.querySelectorAll('[data-select]:checked')].map(e=>e.dataset.select);
        const values=Object.fromEntries([...editor.querySelectorAll('[data-bulk]')].filter(e=>e.value!=='').map(e=>[e.dataset.bulk,e.value]));
        if(!ids.length||!Object.keys(values).length)throw Error('Chọn ít nhất một dòng và nhập giá/phí cần điền.');
        workbench.fillSelected(p,ids,values);
      }
      if(action==='save'){
        const result=workbench.saveShipments(p);
        if(!result.ok){render();document.querySelector(`[data-feedback="${p}"]`).textContent='Còn lỗi kiểm tra. Dữ liệu và lỗi vẫn ở từng dòng; sửa rồi thử lại.';return;}
        render();document.querySelector(`[data-feedback="${p}"]`).textContent=`Đã giữ ${result.count} dòng nháp/chờ giá trong tab. Chưa ghi sổ, chưa thay đổi số dư.`;return;
      }
      render();
    }catch(error){if(feedback){feedback.textContent=error.message;feedback.classList.add('error');}else $('filter-error').textContent=error.message;}
  });
  let receiptKey='';
  function receiptInput(){if(!receiptKey)receiptKey=crypto.randomUUID();return {date:$('receipt-date').value,amount:$('receipt-amount').value,requestId:receiptKey,unconfirmed:$('receipt-confirmed').checked,overpayPeriod:$('overpay-period').value||undefined};}
  function showPlan(plan,title){$('receipt-result').className='result';$('receipt-result').innerHTML=`<strong>${escape(title)}</strong><ul>${plan.allocations.map(a=>`<li>${label(a.period)}: ${fmt(a.amount)}</li>`).join('')||'<li>Không có kỳ dư dương</li>'}</ul><p>Tiền vượt dư dương: <strong>${fmt(plan.unallocated)}</strong>${plan.overpayment?' · đề nghị ghi âm kỳ '+label(plan.overpayment.period):' · chọn kỳ để trình duyệt nếu có dư'}. Chưa vào sổ.</p>`;}
  $('close-receipt').addEventListener('click',()=>{$('receipt-editor').hidden=true;});
  $('preview-receipt').addEventListener('click',()=>{
    try{const i=receiptInput();showPlan(workbench.planReceipt(i.amount,i.date,{overpayPeriod:i.overpayPeriod}),'Đề xuất · chưa lưu, chưa ghi sổ');}
    catch(e){$('receipt-result').className='result error';$('receipt-result').textContent=e.message;}
  });
  $('receipt-form').addEventListener('submit',event=>{
    event.preventDefault();
    const result=workbench.saveReceipt(receiptInput());
    if(!result.ok){$('receipt-result').className='result error';$('receipt-result').textContent=result.error+' · Các trường đã nhập được giữ lại.';return;}
    showPlan(result.receipt,result.duplicate?'Đề nghị đã có · không tạo trùng':'Đã lưu nháp trong tab · Chờ duyệt; số dư không đổi');
    render();
  });
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-detail]');
    if(!button)return;
    const [kind,id]=button.dataset.detail.split(':');
    const row=view.months.flatMap(m=>kind==='shipment'?m.shipments:m.payments).find(r=>r.id===id);
    if(!row)return;
    $('detail-title').textContent=id;
    const pairs=kind==='shipment'?[['Kỳ nợ',row.period],['Ngày xe nhập kho',day(row.date)],['Container',row.container],['Hãng/xe',row.carrier||'Chưa có'],['Đơn vị vận chuyển',row.shipper||'Chưa có'],['Tuyến',(row.origin||'—')+' → '+(row.destination||'—')],['Đơn giá',money(row.price)],['Phí khác',money(row.otherFee)],['Kéo / điện',money(row.tractionFee)],['Bảo hiểm',money(row.insuranceFee)],['Tổng đã duyệt fixture',row.status==='posted'?money(row.approvedTotal):'—'],['Trạng thái',row.status==='posted'?'Đã ghi sổ trong fixture':'Nháp / chờ giá; không vào số dư']]:[['Receipt',row.receiptId],['Ngày thực nhận',day(row.date)],['Kỳ nợ phân bổ',row.period],['Số tiền phân bổ',money(row.amount)],['Tổng receipt',money(row.receiptTotal)],['Trạng thái',row.status==='posted'?'Đã ghi sổ trong fixture':'Chưa xác nhận; không vào số dư']];
    pairs.push(['Chứng từ / người duyệt','Không có trong fixture; không suy đã đối soát ngân hàng']);
    $('detail-content').innerHTML='<dl class="detail-list">'+pairs.map(([k,v])=>`<dt>${escape(k)}</dt><dd>${escape(v)}</dd>`).join('')+'</dl>';
    $('detail').showModal();
  });
  $('close-detail').addEventListener('click',()=>$('detail').close());
  render();
})();
