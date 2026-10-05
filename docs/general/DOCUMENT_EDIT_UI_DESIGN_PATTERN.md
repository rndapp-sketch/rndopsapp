# Document Editor — Form UI Design Pattern

Source: `apps/frappe/frappe/www/document_edit.html`.

This page is a **generic, metadata-driven form renderer**: it can load, edit,
and create any Rndopsapp-module DocType (including its child tables) without
any doctype-specific frontend code. Everything about a field's shape — type,
label, section, required-ness, read-only-ness, link targets — comes from
metadata handed to it at request time; the rendering code never branches on
a specific doctype or fieldname. This document describes the pattern, with
the actual HTML/CSS/JS behind each piece, so it can be reused for other admin
tool pages in this app family (`kafka_control.html`, `pr_link_graph.html`,
`document_edit.html`).

---

## 1. App shell (shared across all three tool pages)

Every tool page uses the identical shell so they read as one product: CSS
variables for both themes, then a fixed sidebar + sticky topbar layout.

```css
:root {
    --bg-page: #F8FAFC;
    --surface: #FFFFFF;
    --bg-sidebar: #F1F5F9;
    --text-main: #0F172A;
    --text-muted: #64748B;
    --accent: #2563EB;
    --accent-hover: #1D4ED8;
    --accent-light: #EFF6FF;
    --border: #E2E8F0;
    --table-header: #F1F5F9;
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
    --shadow-md: 0 6px 16px rgba(15, 23, 42, 0.08);
    --shadow-lg: 0 20px 48px rgba(15, 23, 42, 0.16);
    --radius-lg: 16px; --radius-md: 12px; --radius-sm: 8px;
    --success: #22C55E; --success-soft: #ECFDF3;
    --warning: #F59E0B; --warning-soft: #FFFBEB;
    --danger: #EF4444;  --danger-soft: #FEF2F2;
    --sidebar-width: 268px;
}
:root[data-theme="dark"] {
    --bg-page: #0B1120; --surface: #111827; --bg-sidebar: #0F172A;
    --text-main: #F1F5F9; --text-muted: #94A3B8;
    --accent: #3B82F6; --accent-hover: #60A5FA;
    --accent-light: rgba(59, 130, 246, 0.16);
    --border: #1E293B; --table-header: #1E293B;
    /* + dark variants of shadow/success/warning/danger */
}
```

Layout skeleton — a fixed-width sidebar, and a main column offset by that
same width with a sticky topbar:

```css
.app-shell { display: flex; min-height: 100vh; }

.app-sidebar {
    width: var(--sidebar-width);
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    position: fixed; top: 0; left: 0; height: 100vh;
    overflow-y: auto; padding: 1.4rem 1rem 1.5rem;
    display: flex; flex-direction: column; gap: 1.5rem;
    z-index: 100;
}

.nav-item {
    display: flex; align-items: center; gap: .7rem;
    padding: .62rem .75rem; border-radius: var(--radius-sm);
    color: var(--text-muted); font-size: .89rem; font-weight: 600;
    text-decoration: none; border: none; background: transparent;
}
.nav-item:hover  { background: var(--accent-light); color: var(--accent); }
.nav-item.active { background: var(--accent); color: #fff; box-shadow: var(--shadow-sm); }

.app-main {
    margin-left: var(--sidebar-width);
    flex: 1; min-width: 0;
    display: flex; flex-direction: column;
}
.app-topbar {
    position: sticky; top: 0; z-index: 90; height: 66px;
    background: color-mix(in srgb, var(--surface) 88%, transparent);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 1rem; padding: 0 1.75rem;
}
```

Sidebar nav markup — one `<a class="nav-item">` per tool page, the current
page marked `.active`:

```html
<aside class="app-sidebar">
    <div class="brand-row">
        <div class="brand-logo"><svg>...</svg></div>
        <div class="brand-text">rndopsapp<small>DevOps Control Center</small></div>
    </div>
    <div class="nav-scroll">
        <div class="nav-group-label">Tools</div>
        <ul class="nav-list">
            <li><a class="nav-item" href="/kafka_control">...Dashboard</a></li>
            <li><a class="nav-item" href="/pr_link_graph">...PR Link Graph</a></li>
            <li><a class="nav-item active" href="/document_edit">...Document Editor</a></li>
        </ul>
    </div>
</aside>
```

Shared JS every page relies on: `callMethod(method, args)` is the one fetch
wrapper for whitelisted calls, and `escHtml(s)` is the only place raw values
are allowed to touch `innerHTML` — every interpolated value in a template
string goes through it.

```js
async function callMethod(method, args = {}) {
    const response = await fetch(`/api/method/${method}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Frappe-CSRF-Token': window.csrf_token || ''
        },
        body: JSON.stringify(args)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || data.exc || response.statusText);
    return data;
}
function escHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
```

When adding a new tool page: copy this shell verbatim (see
`document_edit.html` lines 1–450 for a clean copy), add a nav-item for it to
the other two pages' sidebars, and never build a second CSRF/fetch helper.

---

## 2. Rendering a form from metadata

A field is described by a small, flat object — fieldname, label, fieldtype,
options, required, read-only, description, section — and the whole form is
built by walking a list of these. No step in the rendering pipeline ever
says "if this is the Project Registration doctype…" — it only ever asks
"what does this field's metadata say".

### Field → input mapping (`deFieldInputHtml`)

One function is the single source of truth for "what HTML does this
fieldtype render as". Every branch shares the same `common` attribute string
so every input, regardless of type, ends up with identical `data-*` hooks:

```js
function deFieldInputHtml(field, value, extraAttrs, linkOptions) {
    const ft = field.fieldtype;
    const original = deCoerceForInput(ft, value);
    // Always start disabled — the page loads in read-only View mode;
    // deSetEditMode(true) is what turns non-read_only inputs back on.
    const common = `data-fieldname="${escHtml(field.fieldname)}" data-fieldtype="${escHtml(ft)}" ` +
                   `data-original="${escHtml(original)}" data-readonly="${field.read_only ? '1' : '0'}" ` +
                   `${extraAttrs || ''} disabled`;

    if (ft === 'Check') {
        const checked = (value === 1 || value === '1' || value === true) ? 'checked' : '';
        return `<input type="checkbox" class="doc-field-input" ${common} ${checked} onchange="deTrackChange(this)">`;
    }

    // Link fields: render as a dropdown of "label — docname", capped at 200 rows,
    // falling back to a plain text input if no options were fetched for this field.
    if (ft === 'Link' && linkOptions && linkOptions[field.fieldname] && linkOptions[field.fieldname].length) {
        const opts = linkOptions[field.fieldname];
        const hasOriginal = !original || opts.some(o => o.value === original);
        const currentOpt = (original && !hasOriginal)
            ? `<option value="${escHtml(original)}" selected>${escHtml(original)} (current)</option>` : '';
        return `<select class="form-input doc-field-input" ${common} onchange="deTrackChange(this)">
            <option value="">— none —</option>
            ${currentOpt}
            ${opts.map(o => `<option value="${escHtml(o.value)}" ${o.value === original ? 'selected' : ''}>${escHtml(o.label || o.value)} — ${escHtml(o.value)}</option>`).join('')}
        </select>`;
    }

    if (ft === 'Select') {
        const opts = (field.options || '').split('\n').map(o => o.trim()).filter((o, i) => o !== '' || i === 0);
        return `<select class="form-input doc-field-input" ${common} onchange="deTrackChange(this)">
            ${opts.map(o => `<option value="${escHtml(o)}" ${o === original ? 'selected' : ''}>${escHtml(o || '—')}</option>`).join('')}
        </select>`;
    }
    if (['Text', 'Small Text', 'Long Text', 'Text Editor', 'Code', 'Markdown Editor', 'HTML Editor', 'JSON'].includes(ft)) {
        return `<textarea class="form-input doc-field-input" ${common} oninput="deTrackChange(this)">${escHtml(original)}</textarea>`;
    }
    if (ft === 'Int') {
        return `<input type="number" step="1" class="form-input doc-field-input" ${common} value="${escHtml(original)}" oninput="deTrackChange(this)">`;
    }
    if (['Float', 'Currency', 'Percent'].includes(ft)) {
        return `<input type="number" step="any" class="form-input doc-field-input" ${common} value="${escHtml(original)}" oninput="deTrackChange(this)">`;
    }
    if (ft === 'Date') {
        return `<input type="date" class="form-input doc-field-input" ${common} value="${escHtml(original)}" oninput="deTrackChange(this)">`;
    }
    if (ft === 'Datetime') {
        return `<input type="datetime-local" class="form-input doc-field-input" ${common} value="${escHtml(original)}" oninput="deTrackChange(this)">`;
    }
    return `<input type="text" class="form-input doc-field-input" ${common} value="${escHtml(original)}" oninput="deTrackChange(this)">`;
}
```

| fieldtype | input |
|---|---|
| `Check` | `<input type=checkbox>` |
| `Link` (with options) | `<select>` of `"label — docname"`, + synthetic "(current)" option |
| `Link` (no options) | plain text — exact docname must be typed |
| `Select` | `<select>` from `options.split('\n')` |
| `Text` / `Small Text` / `Long Text` / `Text Editor` / `Code` / `Markdown Editor` / `HTML Editor` / `JSON` | `<textarea>` |
| `Int` | `<input type=number step=1>` |
| `Float` / `Currency` / `Percent` | `<input type=number step=any>` |
| `Date` | `<input type=date>` |
| `Datetime` | `<input type=datetime-local>` |
| anything else | plain `<input type=text>` |

A field's input is wrapped in a `.field-group` that carries the label,
required marker, fieldtype hint, and description — this is the unit that
gets a "changed" or "missing" highlight later:

```js
function deFieldGroupHtml(f, val, linkOptions) {
    const req = f.reqd ? '<span class="req-dot">*</span>' : '';
    const desc = f.description ? `<div class="field-desc">${escHtml(f.description)}</div>` : '';
    return `<div class="field-group" data-reqd="${f.reqd ? '1' : '0'}" data-label="${escHtml(f.label)}">
        <label>${escHtml(f.label)}${req} <span class="field-type-hint">${escHtml(f.fieldtype)}${f.options ? ' → ' + escHtml(f.options) : ''}</span></label>
        ${deFieldInputHtml(f, val, null, linkOptions)}
        ${desc}
    </div>`;
}
```

```css
.field-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: .9rem 1.1rem; }
.field-group { display: flex; flex-direction: column; gap: .3rem; }
.field-group label { font-size: .78rem; color: var(--text-muted); font-weight: 600; }
.field-group.field-changed label      { color: var(--accent); }
.field-group.field-changed .form-input { border-color: var(--accent); background: var(--accent-light); }
.field-group.field-missing label      { color: var(--danger); }
.field-group.field-missing .form-input { border-color: var(--danger); background: var(--danger-soft); }
```

### Sections (`deGroupFieldsIntoSections`)

Fields are grouped by their `section` value, preserving first-appearance
order:

```js
function deGroupFieldsIntoSections(fields) {
    const order = [];
    const bySection = {};
    fields.forEach(f => {
        const key = f.section || '__none__';
        if (!bySection[key]) { bySection[key] = { label: f.section, fields: [] }; order.push(key); }
        bySection[key].fields.push(f);
    });
    return order.map(key => bySection[key]);
}
```

If a doctype only has one section (or none), the caller skips the wrapper
chrome entirely and renders a flat `.field-grid` — don't show a single
collapsible section, it's just noise. Multi-section doctypes get a
`.form-section` per group, collapsible via its header:

```css
.form-section { border: 1px solid var(--border); border-radius: var(--radius-md); margin-bottom: 1.1rem; overflow: hidden; }
.form-section-header {
    display: flex; align-items: center; gap: .5rem; padding: .7rem 1rem; cursor: pointer;
    background: var(--bg-sidebar); font-size: .85rem; font-weight: 700;
}
.form-section-header .chevron { transition: transform .15s; }
.form-section.collapsed .chevron { transform: rotate(-90deg); }
.form-section.collapsed .form-section-body { display: none; }
```

### Child tables (`deChildRowHtml` / `deAddChildRow` / `deRemoveChildRow`)

Each child table renders as its own table with one column per child field
plus a remove-row column. Rows carry `data-row-name` (empty for a
not-yet-inserted row) and `data-is-new="1"/"0"`:

```js
function deChildRowHtml(childTable, row, cols) {
    const rowName = row ? row.name : '';
    const isNew = !rowName;
    const linkOptions = childTable.link_options || {};
    return `<tr data-row-name="${escHtml(rowName)}" data-is-new="${isNew ? '1' : '0'}">
        ${cols.map(cf => `<td>${deFieldInputHtml(cf, row ? row[cf.fieldname] : '', null, linkOptions)}</td>`).join('')}
        <td><button type="button" class="row-remove-btn" onclick="deRemoveChildRow(this)" title="Remove row">✕</button></td>
    </tr>`;
}
```

"+ Add Row" builds a row from the **same** `deChildRowHtml` used for
existing rows, so a freshly added row and a loaded row are indistinguishable
to the rest of the code — only `data-is-new` distinguishes them at
diff/save time:

```js
function deAddChildRow(btn) {
    const block = btn.closest('.child-table-block');
    const ct = (deSchema.child_tables || []).find(c => c.fieldname === block.dataset.childFieldname);
    const tbody = block.querySelector('.child-table-body');
    const tr = document.createElement('tr');
    tr.innerHTML = deChildRowHtml(ct, null, ct.fields).replace(/^<tr[^>]*>/, '').replace(/<\/tr>$/, '');
    tr.dataset.rowName = '';
    tr.dataset.isNew = '1';
    tr.classList.add('row-changed');
    tbody.appendChild(tr);
    // Add Row is only reachable while in edit mode, so unlock this row's inputs now.
    tr.querySelectorAll('.doc-field-input').forEach(inp => { inp.disabled = inp.dataset.readonly === '1'; });
}
```

```css
table.child-edit-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
table.child-edit-table th { text-align: left; padding: .5rem .6rem; background: var(--table-header); position: sticky; top: 0; }
table.child-edit-table tr.row-changed td { background: var(--accent-light); }
.child-empty-row td { text-align: center; color: var(--text-muted); font-style: italic; padding: .8rem; }
```

An empty table shows a `.child-empty-row` placeholder instead of a bare
`<thead>` with nothing under it.

---

## 3. Interaction pattern

### View / Edit mode gate (`deSetEditMode`)

Every input renders `disabled` (see `common` above) — the page always opens
in a read-only **View** state, regardless of doctype. One function is the
only thing that ever flips that:

```js
function deSetEditMode(on) {
    deEditMode = on;
    const force = document.getElementById('de-force-readonly')?.checked;
    document.querySelectorAll('.doc-field-input').forEach(input => {
        input.disabled = !on || (!force && input.dataset.readonly === '1');
    });
    document.querySelectorAll('.add-row-btn, .row-remove-btn').forEach(b => {
        b.style.display = on ? '' : 'none';
    });
    document.querySelector('.save-bar').style.display = on ? 'flex' : 'none';
    deUpdateSaveSummary();
}
```

`data-readonly="1"` fields stay disabled even in Edit mode unless a
"Force-edit read_only fields" checkbox is also checked. Nothing is ever
editable just because it was rendered — it has to be explicitly unlocked.
A brand-new document (`+ New`, `Duplicate`) skips the View gate and renders
directly in Edit mode — there's nothing to accidentally overwrite yet.

### Diffing (`deComputeChanges`) — the single source of truth for "what changed"

One function walks the DOM and produces `{changes, childTableChanges}`:

```js
function deComputeChanges() {
    const changes = {};
    document.querySelectorAll('#de-form-container .doc-field-input').forEach(input => {
        if (input.closest('.child-table-block')) return; // parent fields only here
        const { raw, value } = deReadInput(input);
        if (raw !== input.dataset.original) changes[input.dataset.fieldname] = value;
    });

    const childTableChanges = [];
    document.querySelectorAll('#de-form-container .child-table-block').forEach(block => {
        const updated = [], inserted = [];
        block.querySelectorAll('tbody tr').forEach(row => {
            if (row.classList.contains('child-empty-row')) return;
            const rowInputs = Array.from(row.querySelectorAll('.doc-field-input'));
            if (row.dataset.isNew === '1') {
                const rowData = {};
                let hasValue = false;
                rowInputs.forEach(input => {
                    const { raw, value } = deReadInput(input);
                    if (raw !== '') hasValue = true;
                    rowData[input.dataset.fieldname] = value;
                });
                if (hasValue) inserted.push(rowData);
            } else {
                const rowChanges = {};
                rowInputs.forEach(input => {
                    const { raw, value } = deReadInput(input);
                    if (raw !== input.dataset.original) rowChanges[input.dataset.fieldname] = value;
                });
                if (Object.keys(rowChanges).length) updated.push({ name: row.dataset.rowName, changes: rowChanges });
            }
        });
        const deleted = deDeletedRows[block.dataset.childFieldname] || [];
        if (updated.length || inserted.length || deleted.length) {
            childTableChanges.push({ fieldname: block.dataset.childFieldname, updated, inserted, deleted });
        }
    });

    return { changes, childTableChanges };
}
```

It is called from three places that need the same answer for different
reasons — **Save/Create** (what actually gets submitted), the live
`deUpdateSaveSummary` text in the save bar (refreshed on every keystroke via
`deTrackChange`), and `deHasUnsavedChanges`/`deConfirmDiscard` (the
dirty-guard before switching documents or leaving the page). Never duplicate
this walk elsewhere; call `deComputeChanges()` again — it's cheap (a handful
of DOM queries) and keeps all three consumers consistent by construction.

### Required-field validation (`deFindMissingRequired`)

Only checks fields whose input is currently **enabled**
(`!input.disabled`) — a field locked behind View mode or `read_only` can
never block a save, because the user has no way to fill it in anyway.
Child-row-level `reqd` is intentionally not enforced; child rows are
free-form line items, and enforcing required-ness there adds a lot of
edge-case handling (partially filled new rows, etc.) for little real
benefit in an admin tool.

### List / Document tabs

The doctype detail panel is two tabs — List and Document — each just a
`display: none` toggle on a sibling container, driven by one function:

```html
<div class="de-tab-bar">
    <button class="de-tab-btn active" data-tab="list" onclick="deSwitchTab('list')">
        List <span class="tab-badge" id="de-tab-list-count">0</span>
    </button>
    <button class="de-tab-btn" data-tab="form" onclick="deSwitchTab('form')">Document</button>
</div>
<div id="de-tab-list" class="de-tab-panel">...searchable document list...</div>
<div id="de-tab-form" class="de-tab-panel" style="display:none;">...banner + form container...</div>
```

```js
function deSwitchTab(tab) {
    document.querySelectorAll('.de-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.getElementById('de-tab-list').style.display = tab === 'list' ? '' : 'none';
    document.getElementById('de-tab-form').style.display = tab === 'form' ? '' : 'none';
}
```

```css
.de-tab-btn { padding: .55rem 1rem; border: none; background: transparent; cursor: pointer;
    border-bottom: 2px solid transparent; margin-bottom: -1px; }
.de-tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
```

The List tab's rows follow "Frappe style" — a colored `.indicator-pill` for
`workflow_state` when the doctype has one, relative time via `deTimeAgo`.
Opening/creating/duplicating a document always calls `deSwitchTab('form')`
immediately, before anything has loaded, so the loading spinner and any
error banner show up where the user is about to look — never leave someone
on the List tab wondering why nothing happened.

---

## 4. Extending this pattern

- **New fieldtype**: add one branch to `deFieldInputHtml`. Don't add
  type-specific branches anywhere else (diffing, validation, and rendering
  all key off `data-fieldtype` generically).
- **New per-field behavior** (e.g. a tooltip, a max-length): add the extra
  metadata to the field object and read it in `deFieldGroupHtml`/
  `deFieldInputHtml`. Keep it flat — deeply nested per-field config has no
  consumer yet and isn't worth the complexity.
- **New tool page reusing this form pattern**: don't copy/paste
  `document_edit.html` wholesale. At minimum copy the app shell (§1) and the
  diff/validate/save trio (`deComputeChanges` / `deFindMissingRequired` /
  `deSetEditMode`) rather than re-deriving them — they're the part that's
  easy to get subtly wrong a second time (e.g. forgetting that a disabled
  field must never count toward "missing required" or "changed").
