# Demo Runbook — Self-Healing System (all cases)

Cold start to every heal case. Run top to bottom.

---

## 0. Open 4 terminals — each one first runs:

```powershell
cd C:\Users\Acer\Downloads\selfhealing\demo
./venv/Scripts/activate
```

## 1. Start 3 services (leave running)

**Terminal A — dashboard:**
```powershell
python -m streamlit run dashboard.py
```
Open **http://localhost:8501** and keep it visible.

**Terminal B — collector** (receives browser-agent events):
```powershell
python collector_server.py
```

**Terminal C — target app** (serves the page + runs the infra monitor every 2s):
```powershell
python demo_target_app.py
```
Wait for `Mock Target Web Application live`. **Terminal D** is where you run the cases.

---

## 2. Cases (Terminal D, in order)

### A — App-breakage QA suite ⭐ (headline)
One command. Breaks the **app** four different ways and heals all of them.
```powershell
python run_qa_heal.py
```
Expected: `RESULT: 4/4 scenarios healed.` Dashboard tab **UI Heuristic Healing**
gains 4 rows.

The four scenarios mutate the START button the way a developer might:

| Scenario | App change | Stale locator that errors |
|----------|-----------|---------------------------|
| CSS class renamed | `btn-main` → `btn-primary` | `.btn-main` |
| Element id renamed | `start-btn` → `start-btn-v2` | `#start-btn` |
| Data attribute changed | `data-action="start"` → `"begin"` | `[data-action='start']` |
| Multiple at once | class + id + attribute | `.btn-main` |

Say: "A dev refactors the app — renames a class, an id, an attribute. A normal
test crashes with NoSuchElementException. The healer scrapes the live DOM, scores
every element against the golden fingerprint (text + structure + neighbours),
recognises the START button despite the changed attribute, re-grabs it by its
live position, and logs the heal. Zero test edits."

Optional visual: open `http://127.0.0.1:8000/?break=css` (or `id`, `attr`, `all`)
in Chrome → View Source shows the changed markup.

### B — Locator heal, AUTOMATIC
Confirm `run_selenium_heal.py` line 43 is `(By.ID, "start-btn")`, then:
```powershell
python run_selenium_heal.py
```
→ tab **UI Heuristic Healing**: AUTOMATIC HEAL with R1–R4 scores.

### C — Source self-heal (the source file rewrites itself)
```powershell
python demo_show.py
```
Press Enter at each gate. Terminal shows `BEFORE old-start-btn → AFTER start-btn`;
tab **Locator Self-Correction** gets a write-back row.
Re-arm for the next run: `python demo_show.py --reset`

### D — Intent-aware (heals a *different* element)
Edit `run_selenium_heal.py` line 43 and save:
```python
BROKEN_LOCATOR = (By.ID, "focus-mode-btn")
```
```powershell
python run_selenium_heal.py
```
→ recovered element is **Focus**, not START (engine is not hardcoded to one button).

### E — CRITICAL FAULT (low confidence, safe halt)
Edit line 43 and save:
```python
BROKEN_LOCATOR = (By.ID, "zzz-nonexistent-999")
```
```powershell
python run_selenium_heal.py
```
→ tab **Alert Notification Logs**: critical "recovery aborted". No source edit.
Then set line 43 back to `(By.ID, "start-btn")`.

### F — Infrastructure heal
```powershell
python simulate_infra_heal.py
```
→ tab **Server Infrastructure Heals**: a fix row.

Real-stress alternative (auto-heals via the monitor):
```powershell
1..8 | ForEach-Object { try { Invoke-WebRequest http://127.0.0.1:8000/error -UseBasicParsing } catch {} }
```
Wait ~4s → the same tab fills by itself.

### G — Browser resource heal (broken image)
Open **http://127.0.0.1:8000** in normal Chrome (collector in Terminal B must be up).
→ tab **Alert Notification Logs**: "Browser Application Anomaly (resource_failure)".

---

## 3. Reset after the demo
```powershell
python demo_show.py --reset
```
Confirm `run_selenium_heal.py` line 43 is `(By.ID, "start-btn")`.

---

## Suggested order on screen
**A → B → C → D → E → F → G**
(app-breakage suite → live heal → permanent fix → intelligence → safety → infra → client)

Only manual edits are line 43 for cases **D** and **E**. Everything else is
zero-edit. Case **A** is the strongest — it shows the *app* changing, not just a
missing id.

## Dashboard tabs
- 🔗 **UI Heuristic Healing** — locator heals + R1–R4 confidence scores
- 📝 **Locator Self-Correction** — source-code write-back log
- ⚙️ **Server Infrastructure Heals** — infra anomaly fixes
- 🚨 **Alert Notification Logs** — critical faults, resource failures, escalations
