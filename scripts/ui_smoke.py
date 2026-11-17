"""Headless-browser click-through of the real dashboard (TEST-ONLY fake model injected here; the shipped
app has no fake fallback). Requires: pip install playwright && playwright install chromium.
Run from repo root: python scripts/ui_smoke.py"""
import os, sys, subprocess, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
os.environ['FOUNDEROS_DB'] = '/tmp/ui_smoke.sqlite3'
if os.path.exists('/tmp/ui_smoke.sqlite3'): os.remove('/tmp/ui_smoke.sqlite3')
from playwright.sync_api import sync_playwright
import threading, uvicorn
from app import main
from tests.conftest import FakeModel
main.LLM = FakeModel()
async def fake_verify(url, excerpt): return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T00:00:00+00:00', 'test'
main.verify_excerpt = fake_verify
cfg = uvicorn.Config(main.app, host='127.0.0.1', port=8765, log_level='warning')
server = uvicorn.Server(cfg); threading.Thread(target=server.run, daemon=True).start(); time.sleep(1.5)
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or None); page = b.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.goto('http://127.0.0.1:8765/')
    page.fill('textarea[name=idea]', 'A WhatsApp-based study planner for Cairo engineering students who miss deadlines. Budget 300 EGP, 5 weeks.')
    page.fill('input[name=budget]', '300 EGP'); page.click('#create-form button[type=submit]'); page.wait_for_selector('#workspace:not(.hide)')
    page.click('#refine-btn'); page.wait_for_selector('#brief-fields .field'); 
    assert 'EXPLICIT' in page.inner_text('#brief-fields') and 'INFERRED_UNCONFIRMED' in page.inner_text('#brief-fields')
    assert 'ALLOW_DISCOVERY' in page.inner_text('#safety-pill')
    page.click('[data-view=discovery]'); page.click('#discover-btn'); page.wait_for_selector('#discover-decision [data-action=APPROVE]')
    page.click('#discover-decision [data-action=APPROVE]'); page.wait_for_selector('#validate-btn:not([disabled])')
    # evidence (secondary)
    page.click('[data-view=evidence]')
    page.fill('#evidence-src input[name=claim]', 'Egypt has many university students'); page.fill('#evidence-src input[name=url]', 'https://example.org/stats')
    page.fill('#evidence-src textarea[name=excerpt]', 'students enrolled in Egyptian universities'); page.select_option('#evidence-src select[name=direction]', 'SUPPORTS')
    page.click('#evidence-src button[type=submit]'); page.wait_for_selector('.evidence-row')
    # experiment from suggestion -> lock -> result
    page.click('[data-view=experiment]')
    page.wait_for_selector('#experiment-suggestion .field'); page.click('#experiment-new'); page.click('#experiment-form button[type=submit]')
    page.wait_for_selector('[data-lock]'); page.once('dialog', lambda d: d.accept()); page.click('[data-lock]'); page.wait_for_selector('.result-form')
    page.fill('.result-form input[name=sample_size]', '12'); page.fill('.result-form input[name=positives]', '1'); page.fill('.result-form input[name=method]', 'Asked 12 classmates in person')
    today = time.strftime('%Y-%m-%d'); page.fill('.result-form input[name=collected_from]', today); page.fill('.result-form input[name=collected_to]', today)
    page.check('.result-form input[name=consent_confirmed]'); page.click('.result-form button[type=submit]'); page.wait_for_selector('text=outcome')
    page.click('[data-view=decision]'); page.click('#validate-btn'); page.wait_for_selector('#passport .verdict')
    verdict = page.inner_text('#passport .verdict'); assert 'STOP_DO_NOT_LAUNCH' in verdict, verdict
    assert page.locator('#passport a[href^="#ev-"]').count() >= 1
    # approve against recommendation requires ack + reasons -> truthful error first
    page.click('#validate-decision [data-action=APPROVE]'); page.wait_for_selector('.alert:not(.hide)')
    assert 'HTTP 422' in page.inner_text('#alert'), page.inner_text('#alert')
    page.fill('#validate-decision .decision-feedback', 'I will retest another segment first'); page.check('#validate-decision .risk-ack')
    page.click('#validate-decision [data-action=APPROVE]'); page.wait_for_selector('text=RESEARCH_ONLY')
    # persistence across reload
    page.reload(); page.wait_for_selector('#passport .verdict'); assert 'STOP_DO_NOT_LAUNCH' in page.inner_text('#passport .verdict')
    assert page.locator('#decision-list tr').count() >= 3
    # blocked brief path
    page.once('dialog', lambda d: d.accept()); page.click('#switch-project'); page.wait_for_selector('#new-project:not(.hide)')
    page.fill('textarea[name=idea]', 'A tutoring marketplace; generate fake reviews and fake sign-ups to look popular.'); page.click('#create-form button[type=submit]')
    page.wait_for_selector('#workspace:not(.hide)'); page.click('#refine-btn'); page.wait_for_selector('.verdict.BLOCK')
    assert page.is_disabled('#discover-btn') and 'FAKE_SOCIAL_PROOF' in page.inner_text('#safety-output')
    page.screenshot(path=os.getenv('UI_SMOKE_SHOT', '/tmp/ui_blocked.png'), full_page=True)
    b.close()
print('UI SMOKE OK; page errors:', errors)
