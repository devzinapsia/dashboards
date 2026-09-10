# Zinapsia — Odoo development project memory

This file is generic and lives in multiple repositories on this machine —
every Odoo module development repo (e.g. `account-financial-tools`,
`stock`), and every client/odoo.sh deployment repo. Only the section
relevant to the repo you are actually in applies. Detect which kind of
repo you're in before doing anything:

- If it contains Odoo module folders (each with its own `__manifest__.py`),
  it's a **module development repo** → use Section A.
- If it has a `.gitmodules` file referencing other git repos (e.g.
  `zinapsia/*`, `ingadhoc/*`, `OCA/*`), it's a **client/deployment repo** →
  use Section B.

## Company info (used in every manifest / LICENSE / README)

- Legal name: Zinapsia SRL (used in the LICENSE file's copyright line)
- Manifest `author` / README "Credits > Authors": just "Zinapsia" (no
  "SRL") — this is the string Odoo's Apps list groups modules by, and it
  must match exactly across all modules or they split into separate
  author groups in the UI. Don't use "Zinapsia SRL" here even though it's
  the legal name.
- Website: https://www.zinapsia.com
- Dev contact: dev@zinapsia.com
- GitHub org: https://github.com/devzinapsia

## Things to always ask — don't assume, don't skip

1. **Brand-new module**: should it be `auto_install = True` (installs
   automatically as soon as its dependencies are present), or a regular
   opt-in module (`auto_install = False`, the default)?
2. **New standalone model with its own ABM** (a new model with its own
   list/form views, i.e. a new "table" the user manages, like a
   classification or configuration catalog): ask —
   - Does it need the chatter (`mail.thread` / `mail.activity.mixin`,
     `message_ids`/`activity_ids` fields and the chatter widget in the
     form view)? Don't add it by default.
   - Which fields should be available as filters in its search view, and
     which (if any) as default group-by options?
3. **New field added to an existing model** (e.g. adding a field to
   `account.move`, `stock.picking`, `res.partner`, etc.): ask —
   - Should it be searchable/filterable from the search bar?
   - Should it be available as a "Group By" option?
   - Should it be added as an optional column in the relevant list/grid
     view (`optional="hide"`)?
   Don't assume any of these — a new field is not automatically wired into
   search/group-by/grid just because a previous module did it that way.

---

## Section A — Module development repos (e.g. account-financial-tools, stock)

### Environment
- OS: macOS.
- Odoo 19 source, used for tests and to confirm real view/menu XML ids
  before writing any xpath (never guess these from memory):
  `/Users/pablocampo/devzinapsia/odoo19`
- Odoo 18 source, same purpose, for modules targeting 18.0:
  `/Users/pablocampo/devzinapsia/odoo18`
- Always confirm the current git branch matches the Odoo version you're
  developing for (branch `19.0` → check against the Odoo 19 source, branch
  `18.0` → Odoo 18 source). Run `git branch` and check before starting;
  don't assume the checked-out branch is the right one.

### Module folder naming
- English, snake_case, descriptive of the feature.

### Standard module contents (every module must have all of this)
```
<module_name>/
├── __init__.py
├── __manifest__.py
├── LICENSE                    (full AGPL-3 text, same as repo root)
├── README.rst                 (documents the functionality — see below)
├── models/
├── views/
├── security/
├── data/                       (config/seed data, if any, noupdate="1")
├── i18n/ (.pot, es.po, es_AR.po — always fully translated, no empty msgstr)
├── static/description/index.html
├── readme/ (DESCRIPTION.rst, CONFIGURE.rst, USAGE.rst — source fragments)
└── tests/
```
- `README.rst` at the module root must document what the module does, how
  to configure it, and how to use it. Build it from the `readme/*.rst`
  fragments (OCA convention), plus a "Bug Tracker" section linking to this
  module's own GitHub repo URL, and a "Credits > Authors" section listing
  "Zinapsia". Don't skip this file — `static/description/index.html`
  alone is not enough, that one is only for the Apps Store listing.

### Manifest fields (mandatory on every module)
- `license`: `"AGPL-3"`
- `author`: `"Zinapsia"`
- `website`: `"https://www.zinapsia.com"`
- Also put this module's own GitHub repo URL in `README.rst`'s "Bug
  Tracker" section (not in the manifest — the manifest `website` key only
  holds one URL, and that slot is reserved for the company site).
- `name` (the display name shown in the Apps list): Spanish, sentence
  case. This is the one exception to the "English source" rule below —
  it's what the client actually sees when browsing installed apps. The
  module's **technical name** (the folder name, used in `depends`, XML
  ids, etc.) stays English snake_case as usual — only the manifest
  `name` field itself is translated.

### Coding language rules (strict)
1. All Python/XML/JS code and ALL comments/docstrings: English, no
   exceptions.
2. All UI-facing strings (field `string=`, menu/action `name=`, help text):
   English source, fully translated in `es.po` and `es_AR.po` — never leave
   `msgstr ""` empty.
3. Business/master-data literal seed values may stay in Spanish when
   they're proper nouns or client-facing business terms — confirm with the
   user case by case, don't assume.
4. Label capitalization: sentence case only — first letter capitalized,
   rest lowercase, except proper nouns (e.g. "Agreed payment method", not
   "Agreed Payment Method"). Applies to English source AND Spanish
   translations, on every field/menu/action label added.

### View development rules
- Never assume a view id, menu id, or xpath target from memory — confirm it
  against the real Odoo source path above (or against how it was already
  solved in an existing sibling module in this same repo). If it can't be
  confirmed, leave an explicit `TODO` comment and flag it instead of
  guessing.
- `account.move` has a single shared form view across all `move_type`
  values (invoices, bills, credit/debit notes) — use
  `invisible="move_type not in (...)"` to scope a field, instead of
  duplicating views. (The same "one shared view across sub-types" pattern
  shows up elsewhere in Odoo too — e.g. `stock.picking` across picking
  types — check for it before assuming you need separate inherited views.)
- Modern view syntax only: `readonly="..."`, `invisible="..."` as direct
  attributes — never `attrs={}` (deprecated).
- Extra grid/list columns that shouldn't show by default: `optional="hide"`.
- Search view "Group By" filters: available as an option, not
  auto-activated, unless the user explicitly asks for auto-activation.

### Security patterns
- `ir.model.access.csv`: read access for the module's relevant base user
  group, full CRUD for the module's relevant manager/admin group (e.g.
  `account.group_account_invoice` / `account.group_account_manager` for
  accounting modules, `stock.group_stock_user` /
  `stock.group_stock_manager` for inventory modules — adjust to the
  module's actual domain, don't default to accounting groups on a stock
  module).
- Multi-company models: `ir.rule` domain
  `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`
  (empty `company_id` = shared across all companies).

### Testing & validation before showing a diff
1. `python3 -m py_compile` on all `.py` files.
2. Well-formed XML check on all `.xml` files.
3. TransactionCase tests covering the core scenarios of the module.
4. **Always run this install/uninstall cycle against the matching local
   Odoo source** (the 19 or 18 path above, whichever matches the branch)
   before considering the module done, using a local test database:
   - Install the module. Confirm it installs with no errors.
   - Verify it's actually active (e.g. `-i <module> --stop-after-init` exits
     cleanly, and/or check `ir.module.module` state is `installed`).
   - Uninstall the module (`-u`/`--uninstall` as applicable, or via the
     Apps list). Confirm it uninstalls cleanly with no leftover errors.
   - Install it again. Confirm the second install also succeeds cleanly.
   - Report the outcome of all four steps explicitly — don't just say
     "tests passed" without showing this cycle ran.
   - If there's no local test database set up yet to run this against, ask
     what's needed to set one up before marking the module as ready for
     review — don't skip this step silently.

### Git workflow
- Always show `git status` and the full `git diff` before committing.
- Never commit or push without explicit user confirmation — ask first,
  every time.
- Commit message format (English): `[ADD] <module_name>: <short summary>`.

### Hard-won Odoo debugging lessons
- `self.assertRaises(...)` in Odoo's `TransactionCase` wraps the call in a
  cursor savepoint that rolls back once the expected exception is caught —
  this erases every change the code made before raising, not just the
  exception itself. If a test needs to inspect state *after* an expected
  exception, use a manual `try/except` + `self.fail(...)` instead of
  `self.assertRaises()`.
- When overriding a method on a core model that *other installed modules
  also override* (e.g. `account.payment.action_post()`,
  `stock.picking.button_validate()`), never assume your override is the
  one that actually runs, or that it runs at all. Verify with
  `inspect.getsourcefile(type(record).method_name)` /
  `inspect.getsourcelines(...)` in `odoo-bin shell` before spending time
  debugging logic that never executes — the real MRO owner is sometimes a
  third-party module loaded later.
- A field meant to identify "the related record" that a user will also
  need to reference from a *visual* domain/filter builder should reuse an
  existing, obviously-named core field rather than a new custom technical
  field with a different label. Users naturally pick the field with the
  intuitive name in the picker; if that's not the one your code actually
  populates, conditions silently never match and the bug looks like
  "nothing works" with no error anywhere.
- When syncing a relational field from another source on every change, use
  `Command.set` (replace) not `Command.link` (add-only) — otherwise stale
  entries accumulate over time, and can leak into *other* modules that
  also read that same field, not just your own logic.
- If a module needs to optionally interoperate with a third-party module
  that isn't installed in every deployment reusing this repo (e.g.
  ingadhoc's modules on some clients but not others), build a separate
  glue module (`<base_module>_<other_module>`, `depends=[base, other]`,
  `auto_install=True`) rather than hard-depending on the optional module
  from the base one, or littering it with defensive
  `if field in self._fields` checks. Keeps the base module portable across
  every client repo that reuses it.
- Some third-party modules add their own separate, *unnamed* `<notebook>`
  to a form instead of extending a core model's named one. Inserting a new
  tab into the "obviously correct" named notebook can silently render as a
  disconnected second tab strip. Before assuming a tab landed where you
  put it, check the actual resolved view (`env['model'].get_view(view_id=...,
  view_type='form')` and inspect the `<notebook>` elements in the returned
  arch) — and use `position="move"` plus a high view `priority` to relocate
  it if needed.
- To verify a fix against a client's actual third-party modules instead of
  guessing: point a temporary `--addons-path` at that client's deployment
  repo submodules (e.g. `<client-repo>/ingadhoc/*`, `<client-repo>/OCA/*`)
  and install for real in a scratch local database. Reading those
  submodules for this kind of investigation/testing is fine and often the
  only reliable way to reproduce a client-specific bug — the "never touch
  `ingadhoc/*`/`OCA/*`" rule (Section B) is about not *modifying* them, not
  about being unable to read/install them locally for diagnosis.

---

## Section B — Client / odoo.sh deployment repos (e.g. grupolara)

### Environment
- These repos deploy Odoo for a specific client via odoo.sh, and consume
  module repos (like account-financial-tools, stock) as git submodules,
  typically grouped under a `zinapsia/` folder alongside other submodule
  groups such as `ingadhoc/*` and `OCA/*`.
- **Never touch `ingadhoc/*` or `OCA/*` submodules unless explicitly
  asked** — only work with `zinapsia/*`.
- Confirm the tracked branch of a submodule with:
  `grep -A5 "<submodule-name>" .gitmodules`

### Golden rules for submodule commands
1. Always run submodule commands from the **repo root**, never from inside
   a subfolder — a submodule path is relative to the repo root, and
   running the command elsewhere can make git silently update *all*
   submodules instead of just the intended one.
2. Always scope the update to the specific path:
   ```bash
   git submodule update --remote --merge -- zinapsia/<module-repo>
   ```
3. `git checkout <branch>` does NOT auto-realign submodule working trees to
   what that branch expects. After switching branches, check `git status`:
   if submodules other than the intended one show up as "modified (new
   commits)", realign them with
   `git submodule update -- <path1> <path2> ...`, or configure
   `git config submodule.recurse true` once, locally, to avoid this
   going forward.

### Standard update flow (repeat per branch — pointers are independent per branch)
```bash
cd <repo root>
git checkout <branch>
git submodule update --remote --merge -- zinapsia/<module-repo>
git status   # must show ONLY the intended submodule as modified
git add zinapsia/<module-repo>
git commit -m "Update <module-repo> submodule: <short summary of what changed>"
git push origin <branch>
```

### Branch caution
- `staging2` is the primary branch for first-round testing of new submodule
  changes.
- Never push to a production branch (e.g. `main`) without explicit
  confirmation in the conversation that testing passed on a staging branch
  first — even if the update already went out to `staging2`/`staging`.

### A pushed submodule update may need a rebuild to actually take effect
Updating the submodule pointer and pushing does NOT guarantee the running
Odoo server picks up the new code. On odoo.sh, a push to a linked branch
usually triggers an automatic rebuild — but if a user reports "I pushed the
fix and it's still broken," don't assume the code itself is wrong before
confirming a rebuild actually ran:
1. Ask the user to check the module's installed version in **Apps** (should
   match the version in the latest commit's `__manifest__.py`). If it's
   older, the update never ran on that server at all.
2. If the version *does* match but behavior is still the old one, the DB
   update likely ran (picking up view/field/version changes) but the
   long-running web workers may still have the old Python source loaded in
   memory — ask the user to trigger an explicit rebuild (not just an app
   update) and retest.
View/XML changes are less likely to hit this than Python logic changes,
since views are re-read from the DB on every request, but a rebuild is the
safe first troubleshooting step either way when "it looks like my fix
should have worked but didn't."
