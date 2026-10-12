'use strict';
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
  if (!window.confirm(form.dataset.confirm)) event.preventDefault();
}));
const refresh = document.querySelector('#refresh');
if (refresh) {
  refresh.addEventListener('click', () => window.location.reload());
  window.setInterval(() => { if (document.visibilityState === 'visible' && !document.querySelector('input:focus,select:focus')) window.location.reload(); }, 30000);
}
const printQr = document.querySelector('#print-qr');
if (printQr) printQr.addEventListener('click', () => window.print());
