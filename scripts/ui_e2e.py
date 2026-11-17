"""Real-browser end-to-end test of the FounderOS UI (Playwright + Chromium) against a live uvicorn server.

TEST_ONLY wiring: the local model is replaced by the deterministic FakeModel from the test suite, and research
providers/page fetches are replaced by fixed mock responses, because CI and sandboxes may have no model and no
internet. Every click still goes through the real FastAPI backend, SQLite database and gates.
This does NOT verify live Ollama inference or live provider access; see scripts/live_check.py for that.

Run from repo root:  pip install playwright && playwright install chromium && python scripts/ui_e2e.py
Screenshots are written to docs/screenshots/.
"""
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
DB = '/tmp/founderos_ui_e2e.sqlite3'
for suffix in ('', '-wal', '-shm'):
    if os.path.exists(DB + suffix):
        os.remove(DB + suffix)
os.environ['FOUNDEROS_DB'] = DB

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright, expect  # noqa: E402
from app import main, research  # noqa: E402
from app.llm import ModelUnavailable  # noqa: E402
from tests.conftest import FakeModel  # noqa: E402

SHOTS = ROOT / 'docs' / 'screenshots'
SHOTS.mkdir(parents=True, exist_ok=True)
main.LLM = FakeModel()   # TEST_ONLY

PAGE = ('<html><head><title>TEST_ONLY student survey</title><meta property="og:site_name" content="TEST_ONLY University Portal">'
        '<meta property="article:published_time" content="2024-05-01"></head><body>'
        '<p>In a TEST_ONLY 2024 survey, many engineering students in Cairo said they missed at least one assignment deadline each term.</p>'
        '<p>Students mostly coordinate deadlines through WhatsApp groups and printed timetables, the TEST_ONLY survey team wrote.</p>'
        + '<p>Filler paragraph about campus facilities that makes this page long enough to look like a real article page.</p>' * 20 + '</body></html>')
_real_fetch = research.safe_fetch


async def fake_fetch(url, **k):   # TEST_ONLY
    if 'testonly-publisher.org' in url:
        from tests.test_research_v7 import Client, Resp
        orig = research.check_public_url
        research.check_public_url = lambda u: 'testonly-publisher.org'
        try:
            return await _real_fetch(url, client_factory=lambda: Client({'testonly-publisher.org': Resp(200, PAGE.encode())}))
        finally:
            research.check_public_url = orig
    raise research.FetchError('FETCH_FAILED', 'HTTP 403 (access denied or paywall)', 403)


async def fake_providers(item, country, client_factory=None):   # TEST_ONLY
    if item['provider'] == 'worldbank':
        return {'status': 'OK', 'results': [{'provider': 'worldbank', 'title': f'TEST_ONLY {item["indicator"]} — {country}', 'url': f'https://data.worldbank.org/indicator/{item["indicator"]}?locations=EG',
                                             'publisher': 'World Bank (TEST_ONLY mock)', 'year': 2023, 'geography': country, 'datum': f'TEST_ONLY datum {item["indicator"]}, {country}, 2023: 100',
                                             'state': 'FETCHED', 'evidence_status': 'STRUCTURED_DATUM', 'limitation': 'National-level figure.'}]}
    if item['provider'] == 'crossref':
        return {'status': 'OK', 'results': [{'provider': 'crossref', 'title': 'TEST_ONLY: deadline stress among engineering students', 'doi': '10.9999/testonly',
                                             'url': 'https://doi.org/10.9999/testonly', 'publisher': 'TEST_ONLY Press', 'year': 2022, 'abstract': 'TEST_ONLY abstract.',
                                             'state': 'CANDIDATE_METADATA', 'evidence_status': 'METADATA_ONLY'}]}
    return {'status': 'OFFLINE', 'error': 'TEST_ONLY: provider offline', 'results': []}


research.safe_fetch = fake_fetch
research.run_item = fake_providers

server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=8766, log_level='warning'))
threading.Thread(target=server.run, daemon=True).start()
time.sleep(1.5)
BASE = 'http://127.0.0.1:8766'
problems, page_errors = [], []


def check(cond, msg):
    if not cond:
        problems.append(msg)
        print('  FAIL', msg)
    else:
        print('  ok  ', msg)


def no_overflow(page, where):
    w = page.evaluate('[document.documentElement.scrollWidth, window.innerWidth]')
    check(w[0] <= w[1] + 1, f'no horizontal overflow on {where} ({w[0]} <= {w[1]})')


def no_raw_json(page, where):
    txt = page.evaluate("""() => { const m = document.querySelector('main').cloneNode(true); m.querySelectorAll('details:not([open])').forEach(d => d.remove()); return m.innerText; }""")
    check(not re.search(r'\{\s*"\w+"\s*:', txt), f'no raw JSON visible on {where}')


def shot(page, name):
    page.screenshot(path=str(SHOTS / f'{name}.png'), full_page=False)


exe = os.getenv('CHROMIUM_PATH') or None
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe)
    ctx = browser.new_context(viewport={'width': 1366, 'height': 768})
    page = ctx.new_page()
    page.on('pageerror', lambda e: page_errors.append(str(e)))
    # The deliberate out-of-memory step (11) produces one expected HTTP 503 network log line; everything else counts.
    page.on('console', lambda m: page_errors.append(m.text) if m.type == 'error' and 'favicon' not in m.text and 'status of 503' not in m.text else None)
    page.on('dialog', lambda d: d.accept())

    print('1. Projects: create a venture')
    page.goto(BASE + '/')
    expect(page).to_have_url(re.compile(r'/projects$'))
    check(page.locator('nav#workspace-nav').count() == 1, 'exactly one sidebar navigation')
    check(page.locator('h1').first.inner_text() == 'Ventures', 'projects heading')
    shot(page, '01-projects-empty-1366')
    page.fill('#f-idea', 'A digital study planner web app for Cairo University engineering students who keep missing assignment deadlines. I can build Python web apps. No interviews done yet.')
    page.fill('#f-name', 'PlanWell')
    page.fill('#f-target_customers', 'Cairo University engineering students')
    page.fill('#f-target_market', 'Cairo, Egypt')
    page.fill('#f-current_workaround', 'WhatsApp groups and paper notes')
    page.fill('#f-budget', '1000 EGP')
    page.fill('#f-timeline', '6 weeks')
    page.fill('#f-values', 'privacy first, no ads')
    page.reload()   # draft persistence
    check(page.input_value('#f-name') == 'PlanWell', 'create-form draft survives a refresh')
    page.click('#create-btn')
    page.wait_for_url(re.compile(r'/projects/[a-f0-9]{32}/brief$'))
    pid = re.search(r'/projects/([a-f0-9]{32})/', page.url).group(1)
    page.wait_for_selector('h1:has-text("Your brief")')

    print('2. Brief: refine')
    check(page.locator('[aria-disabled="true"]', has_text='Continue to safety').count() == 1, 'continue is disabled with a reason before refinement')
    page.click('#refine-btn')
    page.wait_for_selector('#clarify-form')
    check(page.locator('#clarify-form .chip', has_text='Typed by you').count() >= 5, 'typed fields marked as yours')
    check(page.locator('.original mark').count() >= 1, 'phrases used from your own words are highlighted')
    no_raw_json(page, 'brief')
    shot(page, '02-brief-1366')
    page.check('input[name=confirm][value=problem]')
    page.click('#clarify-btn')
    page.wait_for_selector('text=Saved as brief version 2')
    check('version 2' in page.locator('#crumb-sub').inner_text(), 'confirming a field creates brief v2')
    check(page.locator('[data-field=problem] .chip', has_text='Confirmed by you').count() == 1, 'problem now confirmed by the founder')

    print('3. Safety')
    page.click('text=Continue to safety')
    page.wait_for_url(re.compile('/safety$'))
    check(page.locator('#sg').inner_text().startswith('Allowed for research'), 'study planner allowed for research')
    check(page.locator('tbody tr').count() == 12, 'twelve named checks listed')
    check(page.locator('text=Source not checked').count() >= 1, 'legal check honestly shows source not checked')
    no_raw_json(page, 'safety')
    shot(page, '03-safety-1366')

    print('4. Discover: run, revise, re-run')
    page.click('text=Continue to discover')
    page.click('#disc-run')
    page.wait_for_selector('#dg')
    check(page.locator('#dg').inner_text() == 'Repeat with more evidence', 'zero evidence: Discover gate says repeat (code, PDF p.2)')
    check(page.locator('.card').count() >= 8, 'discovery shown as readable cards')
    no_raw_json(page, 'discovery')
    shot(page, '04-discover-gate-1366')
    page.click('[data-decide="REVISE"]')
    page.fill('#d-fb', 'Focus on third-year students only')
    page.click('#dlg-ok')
    page.wait_for_selector('text=Recorded: Revision requested')
    page.click('#disc-run')
    page.wait_for_selector('text=run v2')
    check(main.LLM.calls[-1][1].get('founder_revision_feedback') == 'Focus on third-year students only', 'revision feedback reached the next agent run')

    print('5. Research: plan, sources, verified passage, ledger')
    page.click('text=Continue to research')
    page.wait_for_selector('.mx-detail h2')
    check(page.locator('[aria-selected="true"][data-tab="matrix"]').count() == 1, 'research opens on the criteria matrix')
    shot(page, '05a-criteria-matrix-empty-1366')
    page.click('[data-tab="plan"]')
    page.click('#plan-run')
    page.wait_for_selector('text=searches returned results')
    page.click('[data-f="unreviewed"]')
    check(page.locator('.source').count() >= 2, 'candidates listed as source cards')
    page.fill('#i-url', 'https://testonly-publisher.org/survey')
    page.fill('#i-q', 'engineering students missed deadline')
    page.click('#insp-btn')
    page.wait_for_selector('text=passages offered from the actual page text')
    card = page.locator('.source', has_text='TEST_ONLY student survey').first
    card.locator('input[name=claim]').fill('Cairo engineering students often miss deadlines')
    card.locator('select[name=subcriterion_id]').select_option('must_have_pain')
    card.locator('select[name=source_type]').select_option('INDUSTRY_REPORT')
    card.locator('select[name=direction]').select_option('SUPPORTS')
    card.locator('input[name=geography]').fill('Egypt')
    for k in ('claim_supported', 'geography', 'buyer_user', 'method', 'date'):
        card.locator(f'select[name="rel.{k}"]').select_option('YES')
    card.locator('button[type=submit]').click()
    page.wait_for_selector('text=Added to the ledger')
    check(page.locator('#flash', has_text='Accepted, relevant').count() == 1, 'reviewed passage accepted as relevant')
    shot(page, '05-research-sources-1366')
    page.click('[data-tab="ledger"]')
    check(page.locator('#tab-body blockquote').count() >= 1, 'ledger shows the exact verified passage')
    page.click('[data-tab="matrix"]')
    page.wait_for_selector('.mx-detail h2')
    check(page.locator('.mx-list li').count() == 67, 'criteria matrix lists all 67 team checks')
    page.click('.mx-list summary:has-text("Problem and customer")')
    page.click('.mx-list a[href*="check=must_have_pain"]')
    page.wait_for_selector('#mx-judge')
    check(page.locator('.mx-detail', has_text='testonly-publisher.org').count() == 1, 'check shows its accepted organisation')
    page.click('#mx-judge')
    page.wait_for_selector('text=Judged: Mixed')
    check(page.locator('.mx-detail header .chip', has_text='Mixed').count() == 1, 'judged check shows its code-capped rating')
    shot(page, '05b-criteria-matrix-1366')
    page.goto(BASE + f'/projects/{pid}/research?tab=matrix&check=no_blocking_patent')
    page.wait_for_selector('text=Search Google Patents')
    check(page.locator('.mx-detail', has_text='bounded search is not proof of absence').count() == 1, 'patent check explains absence limit')
    page.click('#rs-eval')
    page.wait_for_selector('text=Re-evaluated with')
    no_raw_json(page, 'research')

    print('6. Discover gate: approve research with a recorded reason')
    page.click('#workspace-nav >> text=Discover')
    page.wait_for_selector('#dg')
    page.click('[data-decide="APPROVE"]')
    check(page.locator('#dlg').inner_text().count('never allows building') == 1, 'approval dialog says exactly what it grants')
    page.fill('#d-fb', 'Proceed to design a demand test')
    page.check('#dlg input[name=ack]')
    page.click('#dlg-ok')
    page.wait_for_selector('text=Scope: research only')

    print('7. Demand tests: draft, lock, result')
    page.click('#workspace-nav >> text=Demand tests')
    page.click('#use-sug')
    page.fill('#x-m', 'Share of students who voluntarily join the waitlist')
    page.click('#exp-save')
    page.wait_for_selector('button[data-lock]')
    page.click('button[data-lock]')
    page.check('#dlg input[name=c]')
    page.click('#dlg-ok')
    page.wait_for_selector('form[data-result]')
    rf = page.locator('form[data-result]')
    rf.locator('input[name=sample_size]').fill('12')
    rf.locator('input[name=positives]').fill('1')
    rf.locator('input[name=method]').fill('TEST_ONLY waitlist form in two lectures')
    today = time.strftime('%Y-%m-%d')
    rf.locator('input[name=collected_from]').fill(today)
    rf.locator('input[name=collected_to]').fill(today)
    rf.locator('input[name=recruitment_method]').fill('TEST_ONLY asked in two lectures, opt-in')
    rf.locator('input[name=consent_confirmed]').check()
    rf.locator('button', has_text='Submit result').click()
    page.wait_for_selector('text=people did the action')
    check(page.locator('.gate-actions dt', has_text='Denominator').count() == 1, 'result shows denominator, numerator, dates, consent, recruitment')
    shot(page, '06-demand-test-1366')

    print('8. Decision passport')
    page.click('text=Continue to decision')
    page.click('#val-run')
    page.wait_for_selector('#vg')
    verdict = page.locator('#vg').inner_text()
    check(verdict == 'Stop: do not launch', f'failed critical locked test gives an advisory stop (got {verdict})')
    check(page.locator('#main a[href*="research?ev="]').count() >= 1, 'passport links to exact evidence ids')
    no_raw_json(page, 'decision')
    shot(page, '07-decision-passport-1366')
    page.click('[data-decide="APPROVE"]')
    page.click('#dlg-ok')
    check(page.locator('#dlg-err .notice.error').count() == 1 or page.locator('#dlg').evaluate('d => d.open'), 'approving against STOP without a reason is refused')
    page.fill('#d-fb', 'Retest with second-year students first')
    page.check('#dlg input[name=ack]')
    page.click('#dlg-ok')
    page.wait_for_selector('text=Scope: research only')

    print('9. Audit, refresh, deep link, back')
    page.click('#workspace-nav >> text=Decision log')
    page.wait_for_selector('h1:has-text("Decision log")')
    page.wait_for_selector('.timeline li')
    check(page.locator('.decision').count() >= 3, 'decision log lists the founder decisions')
    first = page.locator('.decision').first
    check(first.locator('dt', has_text='Gate said').count() == 1 and 'Stop: do not launch' in first.inner_text(), 'newest decision shows the gate it was made against')
    check('Retest with second-year students first' in first.inner_text(), 'the founder reason is shown in its own field')
    check(page.locator('.decision', has_text='None given (optional here)').count() + page.locator('.decision', has_text='Given').count() >= 3, 'reason status shown for every decision')
    shot(page, '08-decision-log-1366')
    page.reload()
    check(page.locator('h1').inner_text() == 'Decision log', 'refresh keeps the route')
    page.go_back()
    page.wait_for_selector('#vg')
    check('/decision' in page.url, 'browser back returns to the passport')
    ev_link = page.locator('#main a[href*="research?ev="]').first.get_attribute('href')
    page.goto(BASE + ev_link)
    page.wait_for_selector('#tab-body li')
    check(page.locator('[aria-selected="true"][data-tab="ledger"]').count() == 1, 'deep link to evidence opens the ledger')

    print('9b. Restaurant brief: fields from own words, one question for the workaround')
    page.goto(BASE + '/projects')
    page.fill('#f-idea', 'I want to build a simple AI tool for small restaurants in Cairo (5–20 employees) that predicts daily ingredient needs so they waste less food. I have a budget of $200 and six weeks. My skills are Python, basic ML and basic web development. I believe restaurants waste a lot of food but I have not verified this pain yet.')
    page.click('#create-btn')
    page.wait_for_url(re.compile('/brief$'))
    page.click('#refine-btn')
    page.wait_for_selector('#clarify-form')
    txt = page.locator('#clarify-form').inner_text()
    check(all(x in txt for x in ('$200', 'six weeks', 'Python', 'Cairo')), 'restaurant brief: budget, time, skills and city captured from own words')
    check(page.locator('[data-field=current_workaround] .chip', has_text='Model suggestion').count() == 1, 'model-suggested workaround is not treated as confirmed')
    check(page.locator('.notice', has_text='Idea clarity (D02): not yet').count() == 1, 'D02 explains what is missing before discovery')
    shot(page, '02b-brief-restaurant-spans-1366')
    page.fill('#c-current_workaround', 'Owners order by gut feeling and throw away leftovers')
    page.click('#clarify-btn')
    page.wait_for_selector('text=Idea clarity (D02): pass')

    print('10. Hard stop path')
    page.goto(BASE + '/projects')
    page.fill('#f-idea', 'A tutoring marketplace; we buy fake reviews and fake sign-ups so it looks popular in Cairo.')
    page.click('#create-btn')
    page.wait_for_url(re.compile('/brief$'))
    page.click('#refine-btn')
    page.wait_for_selector('#clarify-form')
    page.click('text=Continue to safety')
    page.wait_for_selector('#sg')
    check(page.locator('#sg').inner_text() == 'Hard stop', 'fake-proof brief is a hard stop')
    check(page.locator('[aria-disabled="true"]', has_text='Continue to discover').count() == 1, 'cannot continue past a hard stop')
    check(page.locator('#ack-form').count() == 0, 'no acknowledgment offered for a hard stop')
    shot(page, '09-hard-stop-1366')

    print('11. Model failure keeps input')
    class OOM(FakeModel):
        async def generate(self, *a, **k):
            raise ModelUnavailable('MODEL_OOM_CPU: failed to allocate CPU_REPACK buffer (TEST_ONLY)', 'MODEL_OOM_CPU')
    main.LLM = OOM()
    page.goto(BASE + '/projects')
    page.fill('#f-idea', 'A revision timetable generator for Alexandria high-achieving adult learners preparing certifications.')
    page.click('#create-btn')
    page.wait_for_url(re.compile('/brief$'))
    page.click('#refine-btn')
    page.wait_for_selector('.notice.error')
    msg = page.locator('.notice.error').inner_text()
    check('Model oom cpu' in msg or 'MODEL_OOM_CPU' in msg or 'ran out of RAM' in msg, 'out-of-memory error explained with advice')
    check('revision timetable' in page.locator('.original').inner_text(), 'founder input still shown after the failure')
    shot(page, '10-model-oom-1366')
    main.LLM = FakeModel()

    print('12. Keyboard and dark theme')
    page.goto(BASE + '/projects')
    page.keyboard.press('Tab')
    check(page.evaluate('document.activeElement.className') == 'skip', 'first Tab reaches the skip link')
    page.click('#theme-toggle')
    shot(page, '11-projects-dark-1366')
    page.click('#theme-toggle')

    print('13. Phone 390 px')
    m = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    mp = m.new_page()
    mp.on('pageerror', lambda e: page_errors.append(str(e)))
    store = page.evaluate("localStorage.getItem('founderos_projects')")
    mp.goto(BASE + '/projects')
    mp.evaluate(f"localStorage.setItem('founderos_projects', {store!r})")
    for route, name in (('/projects', 'projects'), (f'/projects/{pid}/safety', 'safety'), (f'/projects/{pid}/decision', 'decision'), (f'/projects/{pid}/research', 'research'), (f'/projects/{pid}/audit', 'decision-log')):
        mp.goto(BASE + route)
        mp.wait_for_selector('h1')
        mp.wait_for_timeout(300)
        no_overflow(mp, f'phone {name}')
        mp.screenshot(path=str(SHOTS / f'12-{name}-390.png'), full_page=False)
    for route in ('/projects', f'/projects/{pid}/discovery', f'/projects/{pid}/experiments', '/roadmap', '/help'):
        page.goto(BASE + route)
        page.wait_for_selector('h1')
        no_overflow(page, f'desktop {route}')
    shot(page, '13-help-1366')
    page.goto(BASE + '/roadmap')
    page.wait_for_selector('.phase')
    check(page.locator('.phase[data-live="1"]').count() == 2 and page.locator('.chip', has_text='Architecture only').count() == 4, 'roadmap: 2 live phases, 4 architecture-only')
    shot(page, '14-roadmap-1366')
    browser.close()

check(not page_errors, f'no JavaScript errors in the browser ({page_errors[:3]})')
print(f'\n{"UI E2E PASSED" if not problems else "UI E2E FAILED"}: {len(problems)} problem(s)')
sys.exit(1 if problems else 0)
