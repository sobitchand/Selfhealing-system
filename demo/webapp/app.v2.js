var RATE = { standard: 5.00, student: 2.00 };

function fmt(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

document.querySelector('.btn-primary').addEventListener('click', function () {
  var borrower = document.getElementById('borrower-code').value.trim();
  var days = parseInt(document.getElementById('days-overdue').value, 10);
  var tier = document.getElementById('membership-level');

  if (!borrower || !days || days <= 0 || !tier.value) {
    document.getElementById('notice').textContent =
      'Enter a borrower number, the days overdue, and a membership.';
    return;
  }

  var fee = days * RATE[tier.value];
  document.getElementById('amount-due').textContent = fmt(fee);
  document.getElementById('notice').textContent =
    'Fine calculated for ' + borrower + ' — ' + days + ' day(s) overdue.';
});
