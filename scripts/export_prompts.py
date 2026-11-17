"""Write prompts/<agent>.md: one file per agent. Model agents get their exact system prompt, copied from
backend/app/llm.py (tests/test_six_phases.py checks they stay identical). Code-only agents get their written
contract, because they have no prompt. Run: python scripts/export_prompts.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app import llm  # noqa: E402

MODEL_AGENTS = {
    'brief_refiner': ('Phase 1', 'REFINE_SYSTEM', 'RefinedBrief', 'Normalizes the founder brief. Field values are never promoted from model suggestions; code extracts spans from the founder text.'),
    'discovery': ('Phase 1', 'DISCOVER_SYSTEM', 'DiscoveryReport', 'Drafts hypotheses, unknowns and candidate directions. A code guard removes claims not grounded in the brief.'),
    'criterion_judge': ('Phases 1-2', 'JUDGE_SYSTEM', 'JudgeOutput', 'Proposes a score for one criterion from accepted evidence only; criteria.validate_judgment caps and checks it.'),
    'check_judge': ('Phase 1', 'CHECK_JUDGE_SYSTEM', 'CheckJudgeOutput', 'Rates one of the 67 team rubric checks from accepted evidence only.'),
    'validation': ('Phase 2', 'VALIDATE_SYSTEM', 'ValidationReport', 'Explains the verdict that code already computed; a skeptic pass corrects over-claims.'),
}

CODE_AGENTS = {
    'safety_screen': ('Phase 1', 'backend/app/safety.py', 'Twelve written rules applied to the founder text before any model call. BLOCK stops the venture; REVIEW_REQUIRED allows research only.'),
    'experiment_designer': ('Phase 2', 'backend/app/criteria.py (experiment_design_check), decision.py, main.py experiment endpoints', 'Checks a demand-test design, locks it with a hash before results, and reads results against the locked pass mark (hit / near miss / clear miss / too little data).'),
    'product_architect': ('Phase 3', 'backend/app/agents/product_architect.py', 'Input: brief + gate 2 verdict + mode. Output: spec (archetype, entity, features, out of scope), user stories with acceptance criteria, status label. Uses only the founder\'s own words; never claims validation.'),
    'website_builder': ('Phase 3', 'backend/app/agents/website_builder.py', 'Input: spec. Output: index.html, styles.css, app.js, README.txt. All text is HTML-escaped; demo data is JSON rendered with textContent; no network, storage or eval.'),
    'qa': ('Phase 3', 'backend/app/agents/qa.py', 'Input: spec + files. Output: PASS/FAIL with one item per check (structure, unique and required ids, forbidden HTML/JS, feature evidence, DEMO label).'),
    'revision': ('Phase 3', 'backend/app/agents/revision.py', 'Input: feedback lines + current spec. Output: spec overrides and a list of changes, each APPLIED or NOT APPLIED. Nothing is guessed.'),
    'commercial': ('Phase 4', 'backend/app/agents/commercial.py', 'Input: ASSUMPTION inputs. Output: unit economics in Decimal, break-even, scenarios, pricing hypotheses, business models, packages, terms checklist, payment provider MOCKED.'),
    'sales_delivery': ('Phase 5', 'backend/app/agents/sales_delivery.py', 'Input: adopted plan + accepted build. Output: offer and a DRAFT sales page; an honesty check rejects fake proof, urgency and income claims.'),
    'payments': ('Phase 5', 'backend/app/payments.py, webhooks.py, delivery.py, refunds.py, reconcile.py', 'TEST MODE simulator: idempotent checkout, HMAC-signed events, idempotent webhook, one entitlement per order, approved refund with revocation, reconciliation.'),
    'operations': ('Phase 6', 'backend/app/agents/operations.py', 'Input: recorded events, labelled manual/mock metrics, feedback with provenance, issues, demand tests. Output: derived metrics, a rule-based recommendation and a proposal back to Phase 1 or 3.'),
    'orchestrator': ('All', 'backend/app/orchestrator.py, gates.py, approval.py', 'Six-phase state machine: computes each gate in code, requests founder approvals bound to current state, and refuses stale, rejected, expired or reused approvals.'),
}


def main():
    out = ROOT / 'prompts'
    out.mkdir(exist_ok=True)
    for name, (phase, const, schema, role) in MODEL_AGENTS.items():
        (out / f'{name}.md').write_text(f'# {name}\n\n- Phase: {phase}\n- Kind: model agent (local Ollama)\n- Output schema: `{schema}` (backend/app/schemas.py)\n- Role: {role}\n\n'
                                        f'## System prompt (exact copy of `llm.{const}`)\n\n```text\n{getattr(llm, const)}\n```\n', encoding='utf-8')
    for name, (phase, src, contract) in CODE_AGENTS.items():
        (out / f'{name}.md').write_text(f'# {name}\n\n- Phase: {phase}\n- Kind: deterministic code agent (no model, no prompt)\n- Source: `{src}`\n\n## Contract\n\n{contract}\n', encoding='utf-8')
    print(f'wrote {len(MODEL_AGENTS) + len(CODE_AGENTS)} files to prompts/')


if __name__ == '__main__':
    main()
