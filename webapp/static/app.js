function parseCurrency(val){
  const n = (val||'').toString().replace(/[^0-9.-]/g,'');
  return n ? parseFloat(n) : 0;
}

function updatePrevLabel(input){
  const prev = input.getAttribute('data-prev');
  const label = input.parentElement.querySelector('small.prev');
  if(!label) return;
  const cur = input.name.match(/base_sqft_price|amenties_and_premiums|amount_received/)
    ? formatCurrency(parseCurrency(input.value))
    : (input.value || '');
  const prevDisp = input.name.match(/base_sqft_price|amenties_and_premiums|amount_received/)
    ? formatCurrency(parseCurrency(prev))
    : (prev || '');
  if(prev !== null && prev !== undefined && cur.toString() !== (prev || '').toString()){
    label.textContent = `Previous: ${prevDisp}`;
    label.style.display = 'block';
  } else {
    label.textContent = '';
    label.style.display = 'none';
  }
}

function initEditForm(){
  const form = document.getElementById('crmEditForm');
  if(!form) return;
  const updateSbua = ()=>{
    const land = parseCurrency(form.land_sqyards.value);
    const sbua = land * 13.5;
    const val = isNaN(sbua)? '' : String(sbua);
    if (form.sbua_sqft) form.sbua_sqft.value = val;
    const disp = document.getElementById('sbua_display');
    if (disp) disp.textContent = val ? formatNumber(parseFloat(val)) : '0';
  };
  // Currency inputs formatting
  ['base_sqft_price','amenties_and_premiums','amount_received'].forEach(name=>{
    const el = form[name];
    if(!el) return;
    el.addEventListener('blur', ()=> { formatInputCurrency(el); updatePrevLabel(el); calcEditTotals(form); });
    el.addEventListener('focus', ()=> { el.value = parseCurrency(el.value) || ''; });
    el.addEventListener('input', ()=> { formatInputCurrency(el); calcEditTotals(form); updatePrevLabel(el); });
  });
  // Other fields previous display
  Array.from(form.querySelectorAll('input,select,textarea')).forEach(el=>{
    if(el.name && !['base_sqft_price','amenties_and_premiums','amount_received'].includes(el.name)){
      el.addEventListener('input', ()=> updatePrevLabel(el));
    }
    updatePrevLabel(el);
  });
  // Auto-calc SBUA when land changes
  if (form.land_sqyards){ form.land_sqyards.addEventListener('input', ()=>{ updateSbua(); calcEditTotals(form); }); }
  // Recalculate totals on any input change (e.g., type_of_sale, etc.)
  form.addEventListener('input', ()=>{ if(event && event.target!==form.land_sqyards){ calcEditTotals(form); } });
  // Add Payment amount currency formatting
  const payForm = document.querySelector('form[action*="add_payment"]');
  if (payForm){
    const amt = payForm.querySelector('input[name="amount"]');
    if (amt){
      amt.addEventListener('input', ()=>{ formatInputCurrency(amt); });
      amt.addEventListener('blur', ()=>{
        // format
        formatInputCurrency(amt);
        // enforce not exceeding balance
        const balNode = document.getElementById('edit_balance_amount');
        const balance = balNode ? parseCurrency(balNode.textContent) : 0;
        const valNum = parseCurrency(amt.value);
        if (valNum > balance){
          const msg = `Entered amount (${formatCurrency(valNum)}) exceeds current balance (${formatCurrency(balance)}).\nDo you want to set amount to the balance?`;
          if (window.confirm(msg)){
            amt.value = formatCurrency(balance);
          } else {
            amt.value = formatCurrency(0);
            amt.focus();
            amt.select();
          }
        }
      });
      amt.addEventListener('focus', ()=>{ amt.value = parseCurrency(amt.value) || ''; });
    }
  }
  updateSbua();
  calcEditTotals(form);
}

function calcEditTotals(form){
  const sbua = parseCurrency(form.sbua_sqft.value);
  const base = parseCurrency(form.base_sqft_price.value);
  const prem = parseCurrency(form.amenties_and_premiums.value);
  const received = parseCurrency(form.amount_received.value);
  const paymentsNode = document.getElementById('payments_total');
  const extraPaid = paymentsNode ? parseCurrency(paymentsNode.getAttribute('data-value')) : 0;
  const tos = (form.type_of_sale.value||'').toUpperCase();
  const total = (base + prem) * sbua;
  const balance = total - (received + extraPaid);
  const byPlan = tos==='OTP' ? balance : (total*0.20) - balance;
  document.getElementById('edit_total_sale_price').textContent = formatCurrency(total);
  document.getElementById('edit_balance_amount').textContent = formatCurrency(balance);
  document.getElementById('edit_balance_plan').textContent = formatCurrency(byPlan);
}

function formatCurrency(num){
  if(isNaN(num)) num = 0;
  return new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:2 }).format(num);
}

function formatNumber(num){
  if(isNaN(num)) num = 0;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits:2 }).format(num);
}

function formatInputCurrency(input){
  const caret = input.selectionStart;
  const val = input.value;
  const num = parseCurrency(val);
  input.value = formatCurrency(num);
  try { input.setSelectionRange(caret, caret); } catch(e) {}
}

function calcTotals(form){
  // derive sbua from land
  const land = parseCurrency(form.land_sqyards.value);
  const sbua = land * 13.5;
  if (form.sbua_sqft) form.sbua_sqft.value = isNaN(sbua)? '' : String(sbua);
  const disp = document.getElementById('sbua_display');
  if (disp) disp.textContent = isNaN(sbua)? '0' : formatNumber(sbua);
  const base = parseCurrency(form.base_sqft_price.value);
  const prem = parseCurrency(form.amenties_and_premiums.value);
  const received = parseCurrency(form.amount_received.value);
  const tos = (form.type_of_sale.value||'').toUpperCase();
  const total = (base + prem) * sbua; // updated formula: sbua_sqft * (base + amenities)
  const balance = total - received;
  const byPlan = tos==='OTP' ? balance : (total*0.20) - balance;
  document.getElementById('total_sale_price').textContent = formatCurrency(total);
  document.getElementById('balance_amount').textContent = formatCurrency(balance);
  document.getElementById('balance_plan').textContent = formatCurrency(byPlan);
}

function showErrors(list){
  const box = document.getElementById('errors');
  if(!list || !list.length){ box.style.display='none'; box.innerHTML=''; return; }
  box.style.display='block';
  box.innerHTML = '<ul>' + list.map(e=>`<li>${e}</li>`).join('') + '</ul>';
}

function validateForm(form){
  const errors=[];
  // Required fields
  const required = [
    'booking_date','project','spg_praneeth','type_of_sale','buyer_name','land_sqyards','base_sqft_price'
  ];
  required.forEach(name=>{
    const el = form[name];
    if(el && (el.value===undefined || el.value===null || String(el.value).trim()==='')){
      errors.push(`${name} is required`);
    }
  });
  const spg = form.spg_praneeth.value.trim();
  if(spg!=="SPG" && spg!=="Praneeth"){ errors.push('spg_praneeth must be SPG or Praneeth'); }
  const tos = (form.type_of_sale.value||'').toUpperCase();
  if(tos!=="OTP" && tos!=="R"){ errors.push('type_of_sale must be OTP or R'); }
  const numericFields=['land_sqyards','sbua_sqft','base_sqft_price','amenties_and_premiums','amount_received'];
  numericFields.forEach(n=>{ if(isNaN(parseCurrency(form[n].value))){ errors.push(`${n} must be a number`);} });
  return errors;
}

function initCrmForm(){
  const form = document.getElementById('crmForm');
  if(!form) return;
  const submitBtn = form.querySelector('button[type="submit"]');
  const updateSbua = ()=>{
    const land = parseCurrency(form.land_sqyards.value);
    const sbua = land * 13.5;
    const val = isNaN(sbua)? '' : String(sbua);
    if (form.sbua_sqft) form.sbua_sqft.value = val;
    const disp = document.getElementById('sbua_display');
    if (disp) disp.textContent = val ? formatNumber(parseFloat(val)) : '0';
  };
  // Currency inputs formatting
  ['base_sqft_price','amenties_and_premiums','amount_received'].forEach(name=>{
    const el = form[name];
    if(!el) return;
    el.addEventListener('input', ()=> { formatInputCurrency(el); calcTotals(form); const errs=validateForm(form); showErrors(errs); if(submitBtn) submitBtn.disabled = errs.length>0; });
    el.addEventListener('blur', ()=> { formatInputCurrency(el); calcTotals(form); const errs=validateForm(form); showErrors(errs); if(submitBtn) submitBtn.disabled = errs.length>0; });
    el.addEventListener('focus', ()=> { el.value = parseCurrency(el.value) || ''; });
  });
  if (form.land_sqyards){ form.land_sqyards.addEventListener('input', ()=>{ updateSbua(); calcTotals(form); }); }
  const onInput = ()=>{ if(event && event.target===form.land_sqyards){ return; } calcTotals(form); const errs=validateForm(form); showErrors(errs); if(submitBtn) submitBtn.disabled = errs.length>0; };
  form.addEventListener('input', onInput);
  if(submitBtn) submitBtn.disabled = true;
  updateSbua();
  onInput();
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const errs = validateForm(form);
    if(errs.length){ showErrors(errs); return; }
    const fd = new FormData(form);
    console.log('[submit] posting form via AJAX to', window.location.pathname);
    const res = await fetch(window.location.pathname, { method:'POST', body: fd, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    const data = await res.json();
    console.log('[submit] server response', data);
    if(!data.ok){ showErrors(data.errors||['Unknown error']); }
    else{
      let redirectUrl = form.getAttribute('data-success-redirect') || '/crm/new?saved=1';
      if (data.s_no){
        const u = new URL(redirectUrl, window.location.origin);
        u.searchParams.set('saved','1');
        u.searchParams.set('s_no', data.s_no);
        redirectUrl = u.pathname + (u.search||'');
      }
      console.log('[submit] redirecting to', redirectUrl);
      window.location.href = redirectUrl;
    }
  });
}

// Format any plain number currency placeholders in tables
function formatCurrencyNodes(){
  const nodes = document.querySelectorAll('.currency[data-value]');
  nodes.forEach(el=>{
    const v = parseCurrency(el.getAttribute('data-value'));
    el.textContent = formatCurrency(v);
  });
}
if (document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', formatCurrencyNodes);
} else {
  formatCurrencyNodes();
}
