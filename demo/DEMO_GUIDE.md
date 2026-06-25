# Teacher Demo Guide — Self-Healing Source Code

Goal: show that when a UI locator breaks, the system not only keeps the test
running but **rewrites the broken locator in the source file on disk** — so the
bug self-repairs once and stays fixed.

---

## Setup (once, before the demo)

Two terminals, both in the `demo/` folder, same Python env.

**Terminal A — dashboard (leave running):**
```bash
python -m streamlit run dashboard.py
```
Open **http://localhost:8501** in a browser. Keep it visible on screen.

**Terminal B — the demo runner** (you'll type one command here during the demo).

> Prereq: Google Chrome installed (the heal drives real headless Chrome).
> `demo_show.py` auto-starts the target app if it isn't already up.

---

## The demo (≈90 seconds)

In **Terminal B**:
```bash
python demo_show.py
```

The script pauses at each stage (press Enter to advance). What to say:

| Stage | On screen | Say this |
|-------|-----------|----------|
| **1. Broken source** | `BROKEN_LOCATOR = (By.ID, "old-start-btn")` | "This test looks for an element id that doesn't exist. Normally it crashes." |
| **2. Run the heal** | live `⚠️ Element Missing → ✨ Auto-Heal 100% → 📝 Source healed` | "It detects the failure, finds the right element by matching against known fingerprints, and keeps going." |
| **3. File changed** | `BEFORE: old-start-btn` / `AFTER: start-btn` | "Look — the **source file on disk** just rewrote itself. The broken locator is permanently fixed." |
| **4. Dashboard** | open http://localhost:8501 | "Every heal is logged. Tab 'Source Code Heals' shows the write-back." |

**Prove it's permanent:**
```bash
python run_selenium_heal.py
```
No "Element Missing" this time — locator is valid, no heal needed.

**Repeat for another viewer:** `python demo_show.py` (auto re-arms first), or
re-arm only with `python demo_show.py --reset`.

---

## The one line that matters

> "Normal self-healing tests patch the locator *in memory* for one run — the bug
> comes back next time. This writes the fix back to **source code**, so it heals
> once and stays healed."

---

## Likely questions + answers

**How does it pick the right element?**
`healing_engine.py` scores every live DOM element against saved "golden"
fingerprints — tag + visible text + CSS class similarity. Highest score wins
(`evaluate_live_candidates`).

**Is it safe to auto-edit source?**
Yes — guardrails in `source_healer.py`:
- Only on **high confidence** (≥75%); below that it halts and raises a CRITICAL alert, source untouched.
- **Whole-token** replace (won't corrupt similar names).
- **Backup** — every file gets a one-time `.bak`.
- **Atomic** write (temp file → os.replace), never a half-written file.

**What if it heals to the wrong element?**
Honest limitation: the engine picks the globally best-matching fingerprint, not
the one tied to the specific broken selector. With one obvious target (this demo)
it's correct. With several similar candidates it could mismatch — that fix would
then also be permanent. Mitigation = the confidence gate + the `.bak` rollback.

**How do I undo a heal?**
Restore the backup: `copy /Y run_selenium_heal.py.bak run_selenium_heal.py`
(or `python demo_show.py --reset`).

---

## If something goes wrong live
- Nothing changes at step 3 → confidence was low, or target app down. Re-run
  `python demo_show.py` (it re-arms and restarts the app automatically).
- Dashboard blank → make sure Terminal A is still running; it auto-refreshes every 3s.
