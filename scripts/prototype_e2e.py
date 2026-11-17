"""Real-browser check of generated prototypes: three different ventures must produce three different, working apps.

    CHROMIUM_PATH=/path/to/chrome python scripts/prototype_e2e.py

It generates each prototype with the real Product Architect -> Website Builder -> QA agents, opens it in headless
Chromium, uses its forms and buttons, and fails on any JavaScript error. Nothing is served or deployed.
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.agents import product_architect as pa, website_builder as wb, qa  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

CASES = {
    'studyflow': {'original_idea_text': 'TEST_ONLY: a study planner that turns university assignments and deadlines into a weekly study schedule for students in Cairo',
                  'problem': 'Students miss assignment deadlines', 'target_customers': 'University students in Cairo'},
    'freelancer': {'original_idea_text': 'TEST_ONLY: a client tracker for independent freelancers to manage clients, projects, tasks and delivery dates',
                   'problem': 'Freelancers lose track of client deliverables across chats', 'target_customers': 'Independent freelance designers'},
    'booking': {'original_idea_text': 'TEST_ONLY: an appointment booking app for independent barbers in Giza so customers can book free slots',
                'problem': 'Barbers lose bookings over phone calls', 'target_customers': 'Independent barbers in Giza'},
}
problems: list[str] = []


def check(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what)
    if not cond:
        problems.append(what)


def write_site(name, brief) -> tuple[Path, dict]:
    sp = pa.spec(brief, None, 'NEEDS_EVIDENCE', 'DEMO_ONLY')
    files = wb.build(sp, 7)
    check(qa.check(sp, files)['status'] == 'PASS', f'{name}: QA PASS')
    d = Path(tempfile.mkdtemp(prefix=f'proto-{name}-'))
    for n, c in files.items():
        (d / n).write_text(c, encoding='utf-8')
    return d / 'index.html', sp


def main():
    exe = os.environ.get('CHROMIUM_PATH')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        kinds = set()
        for name, brief in CASES.items():
            path, sp = write_site(name, brief)
            kinds.add(sp['archetype'])
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.goto(path.as_uri())
            check('DEMO' in page.inner_text('#demo-banner'), f'{name}: DEMO banner shown')
            if sp['archetype'] == 'planner':
                page.fill('#title', 'Essay draft'); page.fill('#due', '3'); page.fill('#hours', '4')
                page.click('#add button[type=submit]')
                check('Essay draft' in page.inner_text('#list'), 'studyflow: task added')
                check('Essay draft' in page.inner_text('#schedule'), 'studyflow: task scheduled into the 7-day plan')
            elif sp['archetype'] == 'tracker':
                page.fill('#client-name', 'Demo Client A'); page.click('#add-client button')
                check('already exists' in page.inner_text('#form-msg'), 'freelancer: duplicate client rejected')
                page.fill('#client-name', 'Studio Nile'); page.click('#add-client button')
                page.select_option('#project-client', 'Studio Nile'); page.fill('#project-title', 'Logo refresh'); page.fill('#project-due', '2')
                page.click('#add-project button')
                check('Logo refresh' in page.inner_text('#projects'), 'freelancer: project added for the new client')
                page.select_option('#task-project', label='Logo refresh (Studio Nile)'); page.fill('#task-title', 'First sketches'); page.click('#add-task button')
                row = page.locator('#projects tr', has_text='Logo refresh')
                check('At risk' in row.inner_text() and '0%' in row.inner_text(), 'freelancer: due in 2 days with open work is At risk, 0%')
                row.locator('button', has_text='Done: First sketches').click()
                row = page.locator('#projects tr', has_text='Logo refresh')
                check('100%' in row.inner_text() and 'Delivered' in row.inner_text(), 'freelancer: completing the last task gives 100% Delivered')
                check('Late' in page.inner_text('#projects'), 'freelancer: an overdue demo project is flagged Late')
                check('Studio Nile: 1 project(s), 0 open task(s)' in page.inner_text('#progress'), 'freelancer: per-client progress summary updates')
            elif sp['archetype'] == 'booking':
                free_before = page.locator('#slot option').count()
                slot = page.locator('#slot option').first.get_attribute('value')
                page.fill('#ref', 'AB'); page.select_option('#slot', slot); page.click('#book button')
                check('No confirmation message was sent' in page.inner_text('#confirmation'), 'booking: confirmation shown, says nothing was sent')
                check(page.locator('#slot option').count() == free_before - 1, 'booking: booked slot removed from free slots')
                check(page.locator(f'#slot option[value="{slot}"]').count() == 0, 'booking: the same slot cannot be chosen again')
                page.fill('#ref', '<script>'); page.click('#book button')
                check('short client reference' in page.inner_text('#form-msg') or page.locator('#ref:invalid').count() == 1, 'booking: invalid reference refused')
                row = page.locator('#bookings tr', has_text='AB')
                row.locator('button', has_text='Cancel').click()
                check(page.locator('#slot option').count() == free_before, 'booking: cancelling frees the slot')
            check(not errors, f'{name}: no JavaScript errors ({errors[:2]})')
            page.close()
        check(len(kinds) == 3, f'three ventures produced three different prototype types: {sorted(kinds)}')
        browser.close()
    print(f'\nPROTOTYPE E2E {"PASSED" if not problems else "FAILED"}: {len(problems)} problem(s)')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
