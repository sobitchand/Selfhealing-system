var RATE = { standard: 5.00, student: 2.00 };

function fmt(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

document.querySelector('.btn-calc').addEventListener('click', function () {
  var borrower = document.getElementById('member-id').value.trim();
  var days = parseInt(document.getElementById('days').value, 10);
  var tier = document.getElementById('tier');

  if (!borrower || !days || days <= 0 || !tier.value) {
    document.getElementById('notice').textContent =
      'Enter a borrower number, the days overdue, and a membership.';
    return;
  }

  var fee = days * RATE[tier.value];
  document.getElementById('total-fee').textContent = fmt(fee);
  document.getElementById('notice').textContent =
    'Fine calculated for ' + borrower + ' — ' + days + ' day(s) overdue.';
});
