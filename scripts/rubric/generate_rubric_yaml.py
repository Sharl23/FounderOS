import json, yaml, hashlib, re
d = json.load(open('parsed.json'))
DIM = {'Ethics and legality screen': 'D01', 'Problem and customer': 'D03', 'Demand signals': 'D04',
       'Competition and alternatives': 'D05', 'Feasibility and founder fit': 'D06', 'Viability, first look': 'D07'}
checks = [d['rubric'][i] for i in d['order']]
prov = [d['prov'][i] for i in d['order']]
team = {'checks': checks, 'provenance': prov}
canon = json.dumps(team, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
digest = hashlib.sha256(canon.encode()).hexdigest()
WORDS = {'one': 1, 'two': 2, 'three': 3}
def required(instr, cid):
    t = instr.lower()
    if 'no web source is needed' in t: return 0
    m = re.search(r'at least (one|two|three)', t) or re.search(r'\b(one|two|three)\b (independent|official|regulator)', t) or re.search(r'cite (one|two|three)\b', t) or re.search(r'find (one|two|three)\b', t)
    if m: return WORDS[m.group(1)]
    if 'patent database' in t: return 1
    if 'list every demand figure' in t: return 0
    return 1
RULES = [
  ('CUSTOMER_VOICE', r'forum|review|community posts|in their own words|own words|surveys|complain'),
  ('INDUSTRY_REPORT', r'industry report|reputable publication|news stor|guides|comparison articles|report'),
  ('OFFICIAL_SOURCE', r'official|regulator|statute|government|legislation|court record'),
  ('COMPANY_PAGE', r'product pages|pricing pages|advertising|company statements|vendor price|their own pages|own pages|technical documentation|descriptions of similar products|free tools|comparable live products|comparable products charge|pre-orders|crowdfunding|paid waitlists'),
  ('PRICING_PAGE', r'public prices|pricing pages|vendor price pages|pays for existing|what the target market pays'),
  ('PATENT_RECORD', r'patent'),
  ('TALENT_MARKET', r'job listings|job boards|salary surveys|freelancers|co-founder platforms|advisers'),
  ('DIRECTORY_OR_COMMUNITY', r'directories|platforms|publications|communities|gather'),
]
CUSTOMER_FIRSTHAND = {'must_have_pain', 'current_workaround_pain', 'customer_own_words', 'action_over_stated_interest', 'problem_framed_from_customer_view',
                      'buyers_show_willingness_to_pay', 'paying_customer_identified', 'payer_identified', 'narrow_early_adopter', 'current_alternatives_in_use',
                      'competitor_weak_points', 'difference_valued_by_customers', 'existing_paying_habit', 'raw_counts_discounted'}
ABSENCE = {'no_blocking_patent': 'STRONG means "no filed patent covers a core feature"; a bounded search is not proof of absence.',
           'free_alternatives_threat': 'STRONG means "no free alternative is used"; a bounded search is not proof of absence.',
           'substitution_threat': 'STRONG means "no credible new kind of solution"; a bounded search is not proof of absence.',
           'regulatory_barriers_manageable': 'STRONG can mean "no rule creates a barrier"; FounderOS never asserts legal clearance.'}
BRIEF_WEAK = {
  'narrow_early_adopter': 'BROAD_SEGMENT', 'paying_customer_identified': 'NO_PAYER', 'payer_identified': 'NO_PAYER',
  'help_network_available': 'NO_CONTACTS', 'cost_structure_understood': 'NO_COSTS', 'revenue_streams_named': 'NO_CHARGE_METHOD'}
OVR = {
 'current_workaround_pain': ['CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'FOUNDER_CUSTOMER_RESEARCH'],
 'reachable_path_to_customers': ['DIRECTORY_OR_COMMUNITY', 'COMPANY_PAGE', 'INDUSTRY_REPORT'],
 'problem_framed_from_customer_view': ['BRIEF', 'CUSTOMER_VOICE', 'FOUNDER_CUSTOMER_RESEARCH'],
 'current_alternatives_in_use': ['CUSTOMER_VOICE', 'COMPANY_PAGE', 'INDUSTRY_REPORT', 'FOUNDER_CUSTOMER_RESEARCH'],
 'paid_alternatives_exist': ['PRICING_PAGE', 'COMPANY_PAGE', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT'],
 'action_over_stated_interest': ['CUSTOMER_VOICE', 'COMPANY_PAGE', 'INDUSTRY_REPORT', 'FOUNDER_CUSTOMER_RESEARCH'],
 'substitutes_in_use': ['COMPANY_PAGE', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'FOUNDER_CUSTOMER_RESEARCH'],
 'direct_competitors_mapped': ['COMPANY_PAGE', 'PRICING_PAGE', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT'],
 'help_network_available': ['BRIEF', 'DIRECTORY_OR_COMMUNITY'],
 'charge_not_easily_bypassed': ['BRIEF', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'COMPANY_PAGE'],
 'revenue_streams_named': ['BRIEF', 'COMPANY_PAGE', 'PRICING_PAGE', 'INDUSTRY_REPORT'],
 'cash_source_explained': ['BRIEF', 'INDUSTRY_REPORT', 'ACADEMIC_PASSAGE'],
 'cost_structure_understood': ['BRIEF', 'INDUSTRY_REPORT', 'ACADEMIC_PASSAGE'],
 'market_understanding': ['BRIEF', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'ACADEMIC_PASSAGE'],
 'underserved_segment': ['CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'ACADEMIC_PASSAGE'],
 'payer_identified': ['BRIEF', 'COMPANY_PAGE', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'FOUNDER_CUSTOMER_RESEARCH'],
 'paying_customer_identified': ['BRIEF', 'COMPANY_PAGE', 'CUSTOMER_VOICE', 'INDUSTRY_REPORT', 'FOUNDER_CUSTOMER_RESEARCH'],
 'narrow_early_adopter': ['BRIEF', 'CUSTOMER_VOICE', 'DIRECTORY_OR_COMMUNITY', 'INDUSTRY_REPORT', 'OFFICIAL_STATISTIC', 'FOUNDER_CUSTOMER_RESEARCH'],
 'physical_goods_exclusion': ['BRIEF', 'COMPANY_PAGE', 'INDUSTRY_REPORT', 'OFFICIAL_SOURCE'],
 'enough_payers_at_price': ['INDUSTRY_REPORT', 'COMPANY_PAGE', 'OFFICIAL_STATISTIC'],
 'free_tier_converts': ['BRIEF', 'INDUSTRY_REPORT', 'COMPANY_PAGE', 'ACADEMIC_PASSAGE'],
}
REQ = {'price_vs_substitutes': 3, 'critical_resources_available': 1}
overlay = {}
for c in checks:
    instr = c['research_instruction']
    t = instr.lower()
    types = [name for name, pat in RULES if re.search(pat, t)]
    if c['id'] in CUSTOMER_FIRSTHAND: types.append('FOUNDER_CUSTOMER_RESEARCH')
    generic = not types or types == ['FOUNDER_CUSTOMER_RESEARCH']
    if generic or c['id'] in {'market_understanding', 'market_maturity_crowding', 'breakeven_time_fit', 'unexpected_costs_buffer', 'substitution_threat',
                              'retaliation_risk', 'time_commitment_fit', 'critical_resources_available', 'build_parts_manageable', 'known_model_precedent',
                              'dominant_player_edge', 'recurring_revenue', 'free_tier_converts', 'entry_barriers_for_newcomers', 'difference_hard_to_copy',
                              'price_war_exposure', 'skills_match_product', 'skill_gaps_fillable', 'startup_cash_within_budget', 'own_funds_cover_first_version',
                              'price_covers_costs', 'enough_payers_at_price', 'comparable_firms_revenue', 'specialized_talent_available'}:
        types += ['INDUSTRY_REPORT', 'ACADEMIC_PASSAGE']
    if c['type'] == 'Ethics and legality screen':
        types = ['OFFICIAL_SOURCE'] if c['id'] in ('illegal_in_target_market', 'regulated_or_sensitive_area') else ['OFFICIAL_SOURCE', 'INDUSTRY_REPORT']
        if c['id'] == 'founder_values_conflict': types = ['BRIEF']
    if c['id'] == 'founder_values_conflict' or c['id'] == 'raw_counts_discounted': types = sorted(set(types) | {'BRIEF'})
    if c['id'] in OVR: types = OVR[c['id']]
    seen = []
    [seen.append(x) for x in types if x not in seen]
    overlay[c['id']] = {'aggregates_into': DIM[c['type']], 'sources_required': REQ.get(c['id'], required(instr, c['id'])), 'accepted_source_types': seen}
    if c['id'] in ABSENCE: overlay[c['id']]['absence_claim_cap'] = ABSENCE[c['id']]
    if c['id'] in BRIEF_WEAK: overlay[c['id']]['brief_condition'] = BRIEF_WEAK[c['id']]
doc = {
 'version': 'rubric-phase1-2026-11-17.v8-1',
 'team_data_sha256': digest,
 'provenance_note': ('All book/chapter/page/supporting_passage/basis entries are team-supplied references (page: "not visible"). '
                     'FounderOS has NOT independently checked these quotations against the books. A supporting passage is the RATIONALE '
                     'for a criterion, never evidence that a venture satisfies it.'),
 'dimension_map': DIM,
 'checks': checks,
 'provenance': prov,
 'implementation_overlay': {
   'origin': 'FOUNDEROS_IMPLEMENTATION (TEAM_ASSUMPTION): derived from each research_instruction; not part of the team data and not hashed into team_data_sha256.',
   'source_types': {
     'CUSTOMER_VOICE': 'Forum threads, reviews, community posts where customers speak.',
     'INDUSTRY_REPORT': 'Industry reports, reputable publications, news, guides, comparison articles.',
     'OFFICIAL_SOURCE': 'Statute, regulator page, government guidance, court record.',
     'COMPANY_PAGE': 'A company\'s own product page, advertising, statement, documentation, or crowdfunding/pre-order page.',
     'PRICING_PAGE': 'A company\'s own public price list, dated at retrieval. Shows an advertised price, not purchases.',
     'PATENT_RECORD': 'A filed patent record from a patent database.',
     'TALENT_MARKET': 'Job listings, job boards, salary surveys, freelancer or co-founder platforms.',
     'DIRECTORY_OR_COMMUNITY': 'A community, directory, publication or platform where the target group gathers.',
     'ACADEMIC_PASSAGE': 'An exact, fetched passage from a paper. Background only.',
     'OFFICIAL_STATISTIC': 'A dated national statistic (e.g. World Bank). Never segment-level.',
     'FOUNDER_CUSTOMER_RESEARCH': 'Founder-run interviews/observations with consent. Founder-reported, not independently verified.',
     'BRIEF': 'The founder\'s own brief.'},
   'never_eligible': ['ACADEMIC_METADATA', 'SIMULATED_RESULT', 'BOOK_SUPPORTING_PASSAGE'],
   'rating_to_score': {'WEAK': 2, 'MIXED': 3, 'STRONG': 4, 'note': '1 and 5 are reserved for dimension-level judgments (5 needs locked-test results). UNKNOWN and NOT_APPLICABLE never become numbers.'},
   'aggregation': {'min_known_checks': 2, 'rule': 'Dimension score = mean of mapped granular ratings, rounded to 0.1, only when at least min_known_checks granular checks are WEAK/MIXED/STRONG. Otherwise the dimension falls back to its dimension-level judge (if any) or stays UNKNOWN.'},
   'checks': overlay}}
class D(yaml.SafeDumper): pass
def str_rep(dumper, s):
    return dumper.represent_scalar('tag:yaml.org,2002:str', s, style='"' if (':' in s or '"' in s or "'" in s or '#' in s or s[:1] in '-[{*&!|>%@`') else None)
D.add_representer(str, str_rep)
hdr = ('# FounderOS Phase-1 team rubric: 67 granular checks (12 ethics + 6 problem + 5 demand + 15 competition + 15 feasibility + 14 viability).\n'
       '# `checks` and `provenance` are the team-supplied data contract, copied without rewriting (parsed from the v0.8 contract).\n'
       '# team_data_sha256 = sha256 of canonical JSON {checks, provenance}; the loader recomputes it on startup and refuses to run on mismatch.\n'
       '# The 12 ethics checks are ENFORCED by policy/safety_rules.yaml (same IDs, same question/fail_if); here they are registered for traceability under D01.\n')
open('rubric_phase1.yaml', 'w', encoding='utf-8').write(hdr + yaml.dump(doc, Dumper=D, sort_keys=False, allow_unicode=True, width=4000))
back = yaml.safe_load(open('rubric_phase1.yaml', encoding='utf-8'))
assert back['checks'] == checks and back['provenance'] == prov
print(digest)
from collections import Counter
print(Counter(o['sources_required'] for o in overlay.values()))
for k, o in list(overlay.items())[:12]: print(k, o['sources_required'], o['accepted_source_types'])
