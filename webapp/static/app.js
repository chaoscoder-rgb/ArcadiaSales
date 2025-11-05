function parseCurrency(val){
  const n = (val||'').toString().replace(/[^0-9.-]/g,'');
  return n ? parseFloat(n) : 0;
}

function updatePrevLabel(input){
  const prev = input.getAttribute('data-prev');
  const label = input.parentElement.querySelector('small.prev');
  if(!label) return;
  const cur = input.name.match(/base_sqft_price|amenties_and_premiums|amount_received|land_sqyards/)
    ? formatCurrency(parseCurrency(input.value))
    : (input.value || '');
  const prevDisp = input.name.match(/base_sqft_price|amenties_and_premiums|amount_received|land_sqyards/)
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
  // Currency inputs formatting
  ['base_sqft_price','amenties_and_premiums','amount_received','land_sqyards'].forEach(name=>{
    const el = form[name];
    if(!el) return;
    el.addEventListener('blur', ()=> { formatInputCurrency(el); updatePrevLabel(el); calcEditTotals(form); });
    el.addEventListener('focus', ()=> { el.value = parseCurrency(el.value) || ''; });
    el.addEventListener('input', ()=> { calcEditTotals(form); updatePrevLabel(el); });
  });
  // Other fields previous display
  Array.from(form.querySelectorAll('input,select,textarea')).forEach(el=>{
    if(el.name && !['base_sqft_price','amenties_and_premiums','amount_received','land_sqyards'].includes(el.name)){
      el.addEventListener('input', ()=> updatePrevLabel(el));
    }
    updatePrevLabel(el);
  });
  calcEditTotals(form);
}

function calcEditTotals(form){
  const land = parseCurrency(form.land_sqyards.value);
  const base = parseCurrency(form.base_sqft_price.value);
  const prem = parseCurrency(form.amenties_and_premiums.value);
  const received = parseCurrency(form.amount_received.value);
  const tos = (form.type_of_sale.value||'').toUpperCase();
  const total = (base + prem) * land;
  const balance = total - received;
  const byPlan = tos==='OTP' ? balance : (total*0.20) - balance;
  document.getElementById('edit_total_sale_price').textContent = formatCurrency(total);
  document.getElementById('edit_balance_amount').textContent = formatCurrency(balance);
  document.getElementById('edit_balance_plan').textContent = formatCurrency(byPlan);
}

function formatCurrency(num){
  if(isNaN(num)) num = 0;
  return new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:2 }).format(num);
}

function formatInputCurrency(input){
  const caret = input.selectionStart;
  const val = input.value;
  const num = parseCurrency(val);
  input.value = formatCurrency(num);
  try { input.setSelectionRange(caret, caret); } catch(e) {}
}

function calcTotals(form){
  const land = parseCurrency(form.land_sqyards.value);
  const base = parseCurrency(form.base_sqft_price.value);
  const prem = parseCurrency(form.amenties_and_premiums.value);
  const received = parseCurrency(form.amount_received.value);
  const tos = (form.type_of_sale.value||'').toUpperCase();
  const total = (base + prem) * land; // updated formula
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
  // Currency inputs formatting
  ['base_sqft_price','amenties_and_premiums','amount_received','land_sqyards'].forEach(name=>{
    const el = form[name];
    if(!el) return;
    el.addEventListener('blur', ()=> { formatInputCurrency(el); calcTotals(form); showErrors(validateForm(form)); });
    el.addEventListener('focus', ()=> { el.value = parseCurrency(el.value) || ''; });
  });
  const onInput = ()=>{ calcTotals(form); showErrors(validateForm(form)); };
  form.addEventListener('input', onInput);
  onInput();
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const errs = validateForm(form);
    if(errs.length){ showErrors(errs); return; }
    const fd = new FormData(form);
    const res = await fetch(window.location.pathname, { method:'POST', body: fd });
    const data = await res.json();
    if(!data.ok){ showErrors(data.errors||['Unknown error']); }
    else{ window.location.href = '/crm/new?saved=1'; }
  });
}

// Format any plain number currency placeholders in tables
document.addEventListener('DOMContentLoaded', ()=>{
  const nodes = document.querySelectorAll('.currency[data-value]');
  nodes.forEach(el=>{
    const v = parseCurrency(el.getAttribute('data-value'));
    el.textContent = formatCurrency(v);
  });
});
