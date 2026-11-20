"""Several files dropped at once (Requirement 18): the first is examined, and the page says so.

Drops real File objects on the real drop zone in a real browser.
"""
from tests.ui.conftest import run_in_browser

DROP = r"""
window.__drop = async (files) => {
  await __until(() => document.querySelector('.drop'), 'start');
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(f);
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
};
window.__sample = async (n) => new Uint8Array(await (await fetch('/samples/' + n)).arrayBuffer());
"""


def test_three_files_examine_the_first_and_name_the_rest(base_url):
    got = run_in_browser(base_url, DROP + r"""
(async () => {
  const pcx = await __sample('external_a');
  await __drop([new File([pcx], 'holiday.pcx'), new File(['notes'], 'notes.txt'), new File([new Uint8Array(40)], 'blob.bin')]);
  const skip = await __until(() => document.querySelector('.rp-bar button[title="Skip to the end"]'), 'result');
  if (!skip.disabled) skip.click();
  const notice = await __until(() => document.querySelector('#view > .notice'), 'notice');
  const dims = (await __until(() => document.querySelector('.exam-right:not(.pending) .dims'), 'outcome')).textContent;
  const out = { notice: notice.textContent, role: notice.getAttribute('role'), first: document.getElementById('view').firstElementChild === notice, dims };
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click();
  out.afterTab = !!document.querySelector('#view > .notice') && document.querySelector('#view > .notice').getClientRects().length > 0;
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Examination').click();
  document.querySelector('.exam-right .card-dl [data-act="data"]').click();
  await __until(() => __blobs.length && __blobs[0].name, 'download');
  out.downloadName = __blobs[0].name;
  document.getElementById('again').click();
  await __until(() => document.querySelector('.drop'), 'start');
  out.noticeGoneOnStart = !document.querySelector('.notice');
  out.multipleAttr = document.querySelector('input[type=file]').hasAttribute('multiple');
  return JSON.stringify(out);
})()
""")
    assert got["notice"] == ("3 files were dropped. NECROPSY examines one file at a time: it examined holiday.pcx "
                             "and ignored 2 others: notes.txt, blob.bin.")
    assert got["role"] == "status" and got["first"], "the statement is not announced, or not before the result"
    assert got["dims"] == "64 × 48 · 8-bit", "the result is not the first file's"
    assert got["afterTab"], "the statement disappeared when the view changed"
    assert got["downloadName"].startswith("holiday_64x48_8bit_data_")
    assert got["noticeGoneOnStart"] and got["multipleAttr"] is False


def test_two_files_singular_wording_and_a_single_file_has_no_statement(base_url):
    got = run_in_browser(base_url, DROP + r"""
(async () => {
  const d = await __sample('mystery_d');
  await __drop([new File([d], 'a.raw'), new File([d], 'b.raw')]);
  const two = (await __until(() => document.querySelector('#view > .notice'), 'notice')).textContent;
  await __until(() => document.querySelectorAll('.card').length, 'cards');
  document.getElementById('again').click();
  await __drop([new File([d], 'only.raw')]);
  await __until(() => document.querySelectorAll('.card').length, 'cards again');
  return JSON.stringify({ two, single: !!document.querySelector('.notice') });
})()
""")
    assert got["two"] == "2 files were dropped. NECROPSY examines one file at a time: it examined a.raw and ignored 1 other: b.raw."
    assert got["single"] is False


def test_oversized_first_file_and_empty_drop_are_stated(base_url):
    got = run_in_browser(base_url, DROP + r"""
(async () => {
  await __drop([new File([new Uint8Array(70000)], 'big.bin'), new File(['x'], 'small.txt')]);
  const big = (await __until(() => document.querySelector('.drop-msg.bad'), 'refusal')).textContent;
  const stayed = !!document.querySelector('.drop');
  document.querySelector('.drop-msg').classList.remove('bad');
  await __drop([]);
  const empty = (await __until(() => document.querySelector('.drop-msg.bad'), 'empty')).textContent;
  return JSON.stringify({ big, stayed, empty, still: !!document.querySelector('.drop') });
})()
""")
    assert got["big"] == "That file is 70,000 bytes. The limit is 65,536 bytes. Try a smaller file or a fragment of it. The other 1 dropped file was not examined."
    assert got["stayed"] and got["still"]
    assert got["empty"] == "Nothing to examine: drop a file."
