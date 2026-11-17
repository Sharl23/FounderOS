"""Safety & eligibility screen: the twelve rules in policy/safety_rules.yaml, enforced by code.

Design (Criteria PDF p.4: "The hard-stop tier should be a short written list, not the model's
general sense of right and wrong ... A list can be tested"):
  1. Deterministic detectors per rule id find exact brief spans (with negation handling and
     context exceptions such as "software FOR a physical business").
  2. An optional constrained model classification (from the refine call) may ESCALATE a rule
     to REVIEW_REQUIRED, only with a verbatim quote from the brief. It can never create a
     HARD_STOP and never remove one.
  3. Official-source questions (illegal_in_target_market, regulated_or_sensitive_area) stay
     UNKNOWN_SOURCE unless a founder-attached official source is fetched and its excerpt verified.
     Missing sources never mean "legal" and never mean "banned".
Outcomes per rule: HARD_STOP | REVIEW_REQUIRED | UNKNOWN_SOURCE | CLEAR | NOT_APPLICABLE.
Overall: BLOCK (any HARD_STOP; non-overridable) | REVIEW_REQUIRED | ALLOW_DISCOVERY.
This is not a legal review and certifies nothing.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

import yaml

POLICY_PATH = Path(__file__).resolve().parents[1] / 'policy' / 'safety_rules.yaml'
POLICY = yaml.safe_load(POLICY_PATH.read_text(encoding='utf-8'))
RULES = {r['id']: r for r in POLICY['rules']}
RULE_IDS = [r['id'] for r in POLICY['rules']]
POLICY_HASH = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
POLICY_VERSION = POLICY['version']
assert len(RULE_IDS) == 12, 'safety policy must define exactly twelve rules'

# A nearby negation turns a match into a value statement ("we will never buy fake reviews",
# "an app that DETECTS fake reviews"). Commas/semicolons break the window.
_NEG = re.compile(r"(?i)\b(no|not|never|without|avoid\w*|don'?t|do not|doesn'?t|does not|won'?t|will not|refus\w*|prevent\w*|"
                  r"detect\w*|against|ban\w*|prohibit\w*|stop\w*|fight\w*|combat\w*|report\w*|flag\w*|anti|"
                  r"protect\w*|warn\w*|spot\w*|identify\w*|block\w*|remov\w*|educat\w* (people|users|students|the public) about|awareness|instead of)\b[^.;,!?\n]{0,30}$")

# ----------------------------------------------------------------------------- detector table
# (rule_id, outcome, pattern, reason, negation_excuses)
_P = []


def det(rule, outcome, pattern, reason, neg=True):
    _P.append((rule, outcome, re.compile(pattern, re.I), reason, neg))


PHYS = r"(devices?|hardware|gadgets?|sensors?|wearables?|smart ?(rings?|bands?|watch(es)?|locks?|bottles?|plugs?)|t-?shirts?|clothes|clothing|apparel|shoes|furniture|cosmetics|jewel(le)?ry|phones?|laptops?|kits?|boxes|meal kits?|food boxes|physical (products?|goods|items)|printed (books|posters)|merch(andise)?|bottles|candles|toys|handmade \w+|3d[- ]printed \w+|drones?|chargers?)"
det('physical_goods_exclusion', 'HARD_STOP',
    r"\b(we|i|our (startup|company|business|brand)|the (startup|business|company))\s+(will\s+|would\s+|plan to\s+|want to\s+)?(sell|ship|manufactur\w*|make|produce|import|distribute|deliver)\w*\s+(\w+\s+){0,4}" + PHYS + r"\b",
    'The founder describes making, selling or shipping a physical item as the business.')
det('physical_goods_exclusion', 'HARD_STOP',
    r"\b(requires?|depends? on|revenue (comes )?from|business model is|core (offering|product) is)\s+(\w+\s+){0,4}(selling|shipping|manufacturing|making|renting)\s+(\w+\s+){0,3}" + PHYS + r"\b",
    'Revenue or the core offering depends on making, selling or shipping physical items.')
det('physical_goods_exclusion', 'HARD_STOP',
    r"\b(an?|our|the)\s+(online|e-?commerce)\s+(shop|store)\s+(selling|that sells|for selling)\s+(\w+\s+){0,3}" + PHYS + r"\b|\b(subscription box|smart (ring|band|watch|lock|bottle) (product|startup|company)|selling (physical|handmade) )",
    'The core offering is a physical product (store, box or device).')
det('physical_goods_exclusion', 'REVIEW_REQUIRED',
    r"\b(marketplace|delivery service|courier|resale|second-?hand)\b[^.;!?\n]{0,50}\b(goods|items|" + PHYS[1:-1] + r"|books|textbooks)\b",
    'A marketplace or delivery model for physical items: revenue may depend on physical goods. Founder must confirm the core deliverable is digital.')

det('financial_crypto_exclusion', 'HARD_STOP',
    r"\b(crypto\w*|bitcoin|ethereum|blockchain token|tokens? sale|ico|nft\w*|defi|stablecoin|forex|day[- ]trading|trading (bot|platform|signals?|app)|copy[- ]trading|stock (picks|tips|signals)|robo[- ]advis\w*|investment (advice|advisory|recommendations?|signals?)|(peer[- ]to[- ]peer|p2p|micro[- ]?|instant |payday )?(lending|loans?) (to|for) (users|students|people|customers|borrowers|individuals)|lend (money )?to (users|students|people|customers)|buy now,? pay later|bnpl|money transfer (app|service|platform)|remittance (app|service|platform)|escrow (service|account)|digital wallet for (users|customers)|e-?wallet (app|service)|manage (users'?|customers'?|people'?s?|their) (money|savings|investments?|portfolios?|funds))\b",
    'The core function involves trading, lending, investing advice, tokens, or handling/managing users\' money.')

det('health_legal_advice_exclusion', 'HARD_STOP',
    r"\b(diagnos\w*|symptom[- ]?(checker|interpret\w*|analy[sz]\w*)|interpret\w* (\w+\s+){0,2}symptoms?|treatment (plans?|recommendations?|advice)|prescrib\w*|dosage|which (medicine|medication|drug)s? to take|medical advice|tell\w* (users|patients|people|them) (what|which) (medication|treatment|medicine)|tell\w* (users|people|them|clients|tenants|workers) what the law requires|legal advice|personali[sz]ed legal (guidance|advice|answers?)|(answers?|advise\w*) (\w+\s+){0,2}(their|users'?) (individual |specific )?legal (cases?|questions?|rights|situations?|requirements?)|ai (lawyer|doctor|therapist)|replace (a |the |your )?(doctor|lawyer|therapist))\b",
    'The product diagnoses, treats, interprets symptoms or tells people what the law requires of them. Labels such as "educational" do not change this.')

det('advice_in_disguise', 'REVIEW_REQUIRED',
    r"\b(educational|tracker|tracking|wellness|coach\w*|tips|insights|guide|journal|planner|assistant)\b[^.;!?\n]{0,60}\b(symptoms?|mood|mental health|diet\w*|weight loss|calories|blood (sugar|pressure)|pregnan\w*|medication|budget\w*|spending|debt|savings?|investments?|tax(es)?|rights|contracts?|visa|immigration|lawsuit)\b|\b(symptoms?|mood|mental health|diet\w*|weight loss|blood (sugar|pressure)|medication|budget\w*|spending|debt|savings?|investments?|tax(es)?|legal rights|contracts?|visa)\b[^.;!?\n]{0,60}\b(tracker|tracking|tips|insights|recommend\w*|suggest\w*|coach\w*|educational)\b",
    'A tracker, coach or "educational" product touching health, money or legal position: people may act on its output as advice. Founder must decide in plain language.')

det('income_promise_dependency', 'HARD_STOP',
    r"\bguarante\w*\b[^.;!?\n]{0,40}\b(income|profits?|returns?|earnings|revenue|success|roi|rich|salary|wealth|money|to make|grades?|results?|jobs?|admission)\b"
    r"|\bpromis(e|es|ing)\s+(\w+\s+){0,6}(income|profits|returns|earnings|success|wealth|to make money|\d+\s*%)\b"
    r"|\bpromis(e|es|ing)\s+(\w+\s+){0,3}(they|members|users|customers|students|you)\s+will\s+(earn|make|get rich|double)\b"
    r"|\b(get[- ]rich[- ]quick|double your money|risk[- ]free (income|returns?|profits?)|passive income guaranteed|earn \$?\d[\d,]*\s*(egp|usd|\$)?\s*(per|a|every) (day|week|month) guaranteed|pyramid scheme|mlm|multi[- ]level marketing)\b",
    'The idea sells or markets itself on a promise of income or a guaranteed outcome.')

det('fake_proof_dependency', 'HARD_STOP',
    r"\b(fake|fabricat\w*|made[- ]up|bogus|phony|phoney|invent(ed|ing)?|synthetic|sock ?puppet\w*|astroturf\w*|bot)\b[^.;!?\n]{0,30}\b(reviews?|testimonials?|sign[- ]?ups?|ratings?|followers|customers?|users|interviews?|survey (results|responses)|waitlist|traction|downloads|endorsements?|case stud(y|ies)|social proof)\b"
    r"|\b(buy|buying|purchase|purchasing|pay for|paying for)\s+(\w+\s+){0,3}(reviews?|testimonials?|sign[- ]?ups?|ratings?|followers|likes|endorsements?)\b"
    r"|\b(generate|generating|auto[- ]?generate\w*|ai[- ]generated|write|writing|post|posting)\s+(\w+\s+){0,2}(5[- ]star |five[- ]star |positive |glowing )(reviews?|testimonials?|ratings?)\b"
    r"|\b(generate|generating|auto[- ]?generate\w*|ai[- ]generated)\s+(\w+\s+){0,2}(reviews?|testimonials?|sign[- ]?ups?|endorsements?)\b"
    r"|\b(fake|false|fabricat\w*|artificial|invented)\s+(\w+\s+){0,2}(urgency|scarcity|countdown\w*|timers?|limited[- ]stock|deadlines?)\b|\bpretend (that )?only \d+ (are )?left\b",
    'The business logic needs fabricated reviews, sign-ups, testimonials or urgency.')

det('impersonation_dependency', 'HARD_STOP',
    r"\b(impersonat\w*|pretend(ing)? to be|pose as|posing as|poses as|masquerad\w*|spoof\w*|clone (the |their |a )?(brand|website|site|app|login page)|look[- ]?alike (site|page|brand|domain)|deepfake\w*|fake (accounts?|profiles?|identit(y|ies)|personas?)|speak(s|ing)? as (a |the )?(real|famous|well[- ]known)|in the name of (a |an |the )?(real|famous|well[- ]known|another) (brand|company|person|university)|as if (it|they|messages?) (came|come|were) from (the |a )?(\w+\s+){0,3}(university|bank|ministry|company|government))\b",
    'The product speaks as, or poses as, a real person, company or brand it is not.')
det('impersonation_dependency', 'REVIEW_REQUIRED',
    r"\b(official (partner|reseller|app) of|on behalf of|white[- ]label\w*|using (the )?(\w+\s+){0,2}(logo|brand(ing)?|trademark) of|branded as)\b",
    'Uses another organization\'s name or branding: confirm written authorization before any research proceeds.')

det('money_or_credentials_dependency', 'HARD_STOP',
    r"\b(you|founder ?os|the ai|ai agents?|the agents?|the assistant|the bot|the (app|platform|system|product))\b[^.;!?\n]{0,50}\b(hold|holds|keep|keeps|transfer|transfers|wire|wires|refund|refunds|charge|charges|collect|collects|move|moves|withdraw|withdraws|pay|pays|process|processes|send|sends|stores?|safeguards?)\b[^.;!?\n]{0,30}\b(users'? money|customers'? money|their money|funds|deposits?|refunds?|cash|wallets?|balances?|bank transfers?)\b"
    r"|\b(store|stores|storing|save|saves|saving|keep|keeps|keeping|remember|log|logs|logging|collect|collects|collecting|harvest\w*|record|records|ask for)\b[^.;!?\n]{0,50}\b(card (details|numbers?|data)|credit ?card (numbers?|details|data)|debit ?card (numbers?|details)|cvv|cvc|bank(ing)? (logins?|passwords?|credentials)|one[- ]time (codes?|passwords?)|otp codes?|api (keys?|secrets?)|private keys?|seed phrases?)\b"
    r"|\b(store|save|keep|remember|log|record|collect|harvest\w*)\s+(\w+\s+){0,2}(my|our|their|customers'?|users'?|clients'?|plain[- ]?text|account)\s+(\w+\s+)?(passwords?|login credentials|credentials|logins?)\b"
    r"|\bplain[- ]?text passwords?\b|\b(hold|holds|holding) (the )?(funds|money|deposits)\b"
    r"|\b(we|i|our (app|platform|startup|company))\s+(will\s+|would\s+)?(hold|keep|store|manage|move|transfer|safeguard)\w*\s+(\w+'?\s+){0,2}(funds|money|deposits|savings|balances|wallets?)\b",
    'The product only works if the system moves or holds money, or stores passwords, keys or card details.')

det('harm_to_people', 'HARD_STOP',
    r"\b(stalk\w*|harass\w*|dox+\w*|revenge porn|track\w* (\w+\s+){0,2}(partner|spouse|wife|husband|girlfriend|boyfriend|ex|employees?|someone|a person|people|individuals?)('s)? (location|phone|messages|whereabouts)|secretly (track|monitor|record|follow)\w*|spy(ing)? on|spyware|stalkerware|keylogger\w*|surveil\w* (of )?(individuals?|specific people|a person|employees|neighbou?rs)|facial recognition (to|for) (identify|track|find) (strangers|people|individuals)"
    r"|(exam|test) cheating|cheat\w* (on|in|during) (\w+\s+){0,2}(exams?|tests?|quizzes)|writ\w* (\w+\s+){0,2}(their|students'?|others'?|people'?s?) (essays?|exams?|theses|thesis|assignments|homework|coursework) for (them|money|a fee|pay)|essay mill|contract cheating|(take|sit) (\w+\s+){0,2}exams? for (them|others|students|money)|fake (degrees?|diplomas?|certificates?|transcripts?|ids?|id cards?|documents?|prescriptions?)"
    r"|phish\w*|scam\w*|ponzi|money launder\w*|launder(ing)? (money|funds)|counterfeit\w*|(mislead|deceiv|trick|manipulat)\w* (\w+\s+){0,2}(elderly|seniors|vulnerable|children|kids|patients|people|users|customers|students)|dark pattern\w*|bait[- ]and[- ]switch"
    r"|pirat\w* (movies|films|software|books|content|courses)|pirated|crack(ed|ing)? (software|games|licen[cs]es)|torrent\w* (of )?(copyrighted|movies|games|courses)|re-?upload\w* (\w+\s+){0,2}(copyrighted|paid) (courses|content|books)|steal\w* (designs?|content|ip|intellectual property|data|passwords?|accounts?|identit\w*|credentials)|stolen (data|cards?|accounts?|credentials|content)|malware|ransomware|credential stuffing|hack(ing)? into)\b",
    'The product\'s purpose matches a listed harm: harassment, stalking, surveillance of individuals, academic/credential fraud, deceptive manipulation of vulnerable people, or IP theft. (The source labels this wall a proposed assumption.)')

det('regulated_or_sensitive_area', 'REVIEW_REQUIRED',
    r"\b(child(ren)?|kids?|minors?|under[- ]?1[0-8]|school ?(children|kids|pupils)|high[- ]school\w*|teen(s|agers?)?|toddlers?|bab(y|ies)|k[- ]?12|primary school|preparatory school)\b",
    'Children may be involved: children\'s data and safety rules apply.', neg=False)
det('regulated_or_sensitive_area', 'REVIEW_REQUIRED',
    r"\b(personal data|personal information|private data|user data|customer data|health (data|records?|information)|medical records?|biometric\w*|face recognition|facial recognition|fingerprints?|location (data|tracking|history)|gps tracking|contact lists?|phone numbers?|national ids?|id (cards?|numbers?)|religio\w*|ethnic\w*|sexual orientation|political (views|opinions)|cv data|resumes?|grades|student records|attendance records|employee (data|monitoring)|camera (feeds?|footage)|voice recordings?|chat logs|messages of)\b",
    'Personal or special-category data is processed: consent and data-protection duties apply.', neg=False)
det('regulated_or_sensitive_area', 'REVIEW_REQUIRED',
    r"\b(medical|medicine|medications?|patients?|clinic\w*|hospital\w*|therap\w*|mental health|pharmac\w*|insurance|loans?|lending|credit scor\w*|banking|fintech|payments? (app|platform|services? for (users|people|consumers))|tax (filing|returns?)|legal services?|lawyers?|law firm|immigration|visas?|real estate brokerage|tenants?|hiring decisions?|background checks?|food (production|safety|preparation)|alcohol|tobacco|gambling|betting|education accreditation|telecom\w*|drones?|transport(ation)? (of passengers|licen[cs]e)|ride[- ]?hailing)\b",
    'A regulated activity may be involved: licences or sector rules may apply in the target market.', neg=False)

# Legal-risk indicators: these ONLY create a research-only pause with UNKNOWN_SOURCE. A hard stop
# requires a verified official source attached to the rule (see official_source handling).
det('illegal_in_target_market', 'REVIEW_REQUIRED',
    r"\b(gambling|betting|casino|lotter(y|ies)|cannabis|marijuana|weed|drugs? (delivery|sales?)|vape|e-?cigarettes?|weapons?|firearms?|guns?|ammunition|alcohol (sales?|delivery)|escort\w*|adult content|porn\w*|unlicensed|without a licen[cs]e|bypass\w* (regulat\w*|licen[cs]\w*|kyc|age verification)|vpn (to|for) bypass\w*|scrap\w* (personal|private) (data|information)|sell\w* (personal|user|customer) data|data broker\w*|counterfeit\w*|replica (bags|watches|brands))\b",
    'The activity may be prohibited or licensed in the target market. Legal status is UNKNOWN until an official source is checked.', neg=False)

# System guards: not part of the twelve product rules; they protect FounderOS itself (X04 approval scope).
_GUARDS = [
    ('SYSTEM_PROMPT_INJECTION', re.compile(
        r"\b(ignore|disregard|forget|override|overrule|bypass|disable|turn off)\b[^.;!?\n]{0,30}\b(instructions?|system prompt|safety (rules?|polic(y|ies)|checks?)|approval (rules?|gates?|process|requirements?)|guardrails?|your rules|the rules|all rules|previous rules|prior rules|gates?)\b"
        r"|\b(auto[- ]?approv\w*|approve (it|this|everything|all( phases)?|the (gate|phase|idea))( \w+){0,2} (yourself|automatically|for me|without me)|mark (it|this|the idea|demand|the business) (as )?(validated|approved|verified|proven)|you are now (the|a|an|in)|act as (the )?(founder|admin|administrator|system)|developer mode|jailbreak\w*|system override)\b", re.I),
     'Text tries to change FounderOS approval or safety rules. Gates are enforced by backend code.', False),
    ('SYSTEM_UNAPPROVED_EXTERNAL_ACTION', re.compile(
        r"\b(publish|post|send|email|message|spend|buy|purchase|sign|launch|deploy|contact|outreach|advertis\w*)\w*\b[^.;!?\n]{0,50}\bwithout (asking|waiting|(my |the founder'?s? |founder |human |any |explicit |prior )?(approval|permission|review|consent|confirmation|sign[- ]?off))\b"
        r"|\b(you|founder ?os|the ai|ai agents?|the agents?|the assistant|the bot)\b[^.;!?\n]{0,30}\b(auto(matically)?|autonomously|on (its|your) own|by (it|your)self)\b[^.;!?\n]{0,30}\b(publish|post|send|email|message|spend|buy|purchase|sign|launch|contact)\w*\b"
        r"|\b(you|founder ?os|the ai|ai agents?|the agents?|the assistant|the bot)\s+(should |can |must |will |to )?(publish|post|send|email|spend|buy|purchase|sign|launch|contact)\w*\b[^.;!?\n]{0,50}\b(on my behalf|for me|immediately|right away|now)\b"
        r"|\b(skip|bypass|no need for)\s+(\w+\s+){0,2}(approval|permission|sign[- ]?off)\b|\b(spam\w*|mass[- ]?(email|dm|messag)\w*)\b", re.I),
     'Text asks FounderOS to publish, send, spend or sign without the founder\'s specific approval (approval scope, X04). FounderOS never does this.', True),
]

# Founder values: value keyword -> idea patterns that would betray it.
_VALUES = [
    (r"privacy|private|data minim\w*|no tracking|not track|confidential\w*",
     r"\b(track\w*|surveil\w*|monitor\w*|sell\w* (\w+\s+){0,2}data|share\w* (\w+\s+){0,2}data with (advertisers|third parties|partners)|targeted ads|ad targeting|location (data|tracking)|collect\w* (\w+\s+){0,2}(contacts|location|messages|personal data)|camera|record\w* (calls|conversations))\b"),
    (r"no ads|ad-?free|without ads|no advertising",
     r"\b(ads|advertis\w*|sponsored (posts|content)|ad revenue)\b"),
    (r"honest\w*|transparen\w*|integrity|no dark patterns|fair",
     r"\b(dark pattern\w*|hidden (fees?|charges?)|auto-?renew\w* (without|silently)|hard to cancel|fake\w*|mislead\w*|clickbait)\b"),
    (r"no gambling|halal|islamic|shariah|no alcohol",
     r"\b(gambl\w*|betting|casino|lotter\w*|alcohol|interest-bearing|riba)\b"),
    (r"free for students|free for everyone|accessib\w* to all|affordab\w*|low[- ]income",
     r"\b(premium[- ]only|paywall\w*|expensive|luxury|high[- ]end pricing)\b"),
    (r"child(ren)?'?s? safety|protect\w* (kids|children|minors)",
     r"\b(ads? (to|for|targeting) (kids|children|minors)|collect\w* (\w+\s+){0,2}(children|kids)'?s? data|chat with strangers)\b"),
    (r"sustainab\w*|environment\w*|eco[- ]friendly|green",
     r"\b(single[- ]use|fast fashion|disposable)\b"),
    (r"human (touch|support)|no bots|real people",
     r"\b(fully automated replies|chatbot replaces|no human support)\b"),
]

LIMITATIONS = [
    'Deterministic rule detectors (English) plus an optional model classifier that can only escalate to founder review. Not a legal review; certifies nothing.',
    'It can miss harmful ideas and can flag harmless ones. A flag is a question for the founder, not an accusation.',
    'A missing official source never means the activity is legal, and never means it is banned.',
    'A HARD_STOP cannot be overridden by founder approval or model output. Revise the brief instead.',
]


def _spans(rx, text, field, neg):
    out = []
    for m in rx.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if neg and _NEG.search(before):
            continue
        out.append({'field': field, 'text': m.group(0)[:200], 'start': m.start(), 'end': m.end(),
                    'context': text[max(0, m.start() - 30):m.end() + 30].replace('\n', ' ')[:240]})
        if len(out) >= 2:
            break
    return out


def _texts(fields: dict) -> list[tuple[str, str]]:
    keys = ('idea', 'idea_summary', 'problem', 'target_customers', 'current_workaround', 'constraints', 'skills', 'target_market', 'values')
    out = []
    for k in keys:
        v = fields.get(k)
        if v:
            out.append((k, str(v)))
    for k, v in (fields.get('founder_answers') or {}).items():
        if v:
            out.append((f'answer:{k}', str(v)))
    return out


_COUNTRIES = {
    'egypt': 'Egypt', 'cairo': 'Egypt', 'giza': 'Egypt', 'alexandria': 'Egypt', 'mansoura': 'Egypt', 'egyptian': 'Egypt',
    'saudi': 'Saudi Arabia', 'riyadh': 'Saudi Arabia', 'jeddah': 'Saudi Arabia', 'uae': 'United Arab Emirates',
    'dubai': 'United Arab Emirates', 'abu dhabi': 'United Arab Emirates', 'jordan': 'Jordan', 'amman': 'Jordan',
    'morocco': 'Morocco', 'tunisia': 'Tunisia', 'kenya': 'Kenya', 'nigeria': 'Nigeria', 'lagos': 'Nigeria',
    'united states': 'United States', 'usa': 'United States', 'united kingdom': 'United Kingdom', 'uk': 'United Kingdom',
    'london': 'United Kingdom', 'germany': 'Germany', 'france': 'France', 'india': 'India', 'canada': 'Canada',
    'turkey': 'Turkey', 'pakistan': 'Pakistan', 'lebanon': 'Lebanon', 'qatar': 'Qatar', 'kuwait': 'Kuwait',
}


def jurisdiction_of(fields: dict) -> dict:
    tm = (fields.get('target_market') or '').strip()
    hay = ' '.join(str(fields.get(k) or '') for k in ('target_market', 'idea', 'target_customers')).lower()
    found = sorted({c for k, c in _COUNTRIES.items() if re.search(r'\b' + re.escape(k) + r'\b', hay)})
    if len(found) == 1:
        return {'country': found[0], 'stated_as': tm or None, 'status': 'IDENTIFIED'}
    if len(found) > 1:
        return {'country': None, 'stated_as': tm or None, 'status': 'AMBIGUOUS', 'candidates': found}
    if re.search(r'\b(global|worldwide|international|everywhere|online)\b', hay) or tm:
        return {'country': None, 'stated_as': tm or None, 'status': 'AMBIGUOUS' if tm else 'UNKNOWN'}
    return {'country': None, 'stated_as': None, 'status': 'UNKNOWN'}


def _legal_queries(fields, jur):
    act = re.sub(r'[^\w\s-]', ' ', str(fields.get('idea_summary') or fields.get('idea') or ''))[:80].strip()
    place = jur.get('country') or 'the target market'
    return [f'{act} licence requirement {place} official regulator',
            f'{act} prohibited {place} law', f'{place} data protection law personal data official']


def screen(text: str, fields: dict | None = None, model_flags: list | None = None, official_sources: list | None = None) -> dict:
    """Run the twelve rules. `text` is the founder's original idea; `fields` the brief payload."""
    fields = dict(fields or {})
    fields.setdefault('idea', text)
    texts = _texts(fields) or [('idea', text or '')]
    jur = jurisdiction_of(fields)
    rows = {rid: {'rule_id': rid, 'question': RULES[rid]['question'], 'fail_if': RULES[rid]['fail_if'],
                  'kind': RULES[rid]['kind'], 'policy_outcome_on_fail': RULES[rid]['outcome_on_fail'],
                  'outcome': 'CLEAR', 'spans': [], 'reasons': [], 'source_needed': None,
                  'research_instruction': RULES[rid]['research_instruction'], 'attempted_searches': [],
                  'official_source': None, 'founder_review_scope': None, 'provenance': RULES[rid]['provenance'],
                  'detected_by': []} for rid in RULE_IDS}

    def raise_to(row, outcome):
        order = ['NOT_APPLICABLE', 'CLEAR', 'UNKNOWN_SOURCE', 'REVIEW_REQUIRED', 'HARD_STOP']
        if order.index(outcome) > order.index(row['outcome']):
            row['outcome'] = outcome

    for rule, outcome, rx, reason, neg in _P:
        for field, t in texts:
            sp = _spans(rx, t, field, neg)
            if sp:
                row = rows[rule]
                row['spans'] += sp
                if reason not in row['reasons']:
                    row['reasons'].append(reason)
                row['detected_by'].append('DETERMINISTIC_RULE')
                raise_to(row, outcome)

    # Escalation: health/legal advice beats advice_in_disguise; tracker that clearly diagnoses => hard stop via its own rule.
    # founder_values_conflict: exact quotations of BOTH spans are required.
    values = str(fields.get('values') or '').strip()
    vrow = rows['founder_values_conflict']
    if not values:
        vrow['outcome'] = 'NOT_APPLICABLE'
        vrow['reasons'].append('No founder values were written in the brief.')
    else:
        for vpat, ipat in _VALUES:
            vm = re.search(vpat, values, re.I)
            if not vm:
                continue
            for field, t in texts:
                if field in ('values', 'answer:values'):
                    continue
                for m in re.finditer(ipat, t, re.I):
                    before = t[max(0, m.start() - 40):m.start()]
                    if _NEG.search(before):
                        continue
                    vrow['spans'].append({'field': 'values', 'text': vm.group(0), 'value_statement': values[:300],
                                          'conflicts_with': {'field': field, 'text': m.group(0), 'context': t[max(0, m.start() - 30):m.end() + 30]}})
                    vrow['reasons'].append(f'Value "{vm.group(0)}" (from your values: "{values[:160]}") may conflict with "{m.group(0)}" in {field}.')
                    vrow['detected_by'].append('DETERMINISTIC_RULE')
                    raise_to(vrow, 'REVIEW_REQUIRED')
                    break
        vrow['source_needed'] = 'None (founder\'s own words; no web source needed).'

    # Official-source rules.
    legal = rows['illegal_in_target_market']
    legal['jurisdiction'] = jur
    legal['source_needed'] = 'Official source (statute, regulator page or government guidance) for the exact jurisdiction. Blogs/forums do not count.'
    legal['attempted_searches'] = [{'query': q, 'executed': False,
                                    'note': 'No compliant automated legal-search provider is configured; query proposed for the founder or a professional.'}
                                   for q in _legal_queries(fields, jur)]
    regulated = rows['regulated_or_sensitive_area']
    regulated['source_needed'] = 'Regulator page or legislation for the target market describing applicable rules.'
    official_sources = official_sources or []
    for src in official_sources:
        row = rows.get(src.get('rule_id'))
        if not row:
            continue
        verified = src.get('excerpt_status') == 'EXCERPT_MATCHED' and src.get('official_domain')
        row['official_source'] = {k: src.get(k) for k in ('id', 'url', 'excerpt', 'finding', 'excerpt_status', 'url_status', 'official_domain', 'retrieved_at', 'jurisdiction')}
        if verified and src.get('finding') in ('PROHIBITS', 'REQUIRES_UNOBTAINABLE_LICENCE') and row['rule_id'] == 'illegal_in_target_market':
            row['reasons'].append('A verified excerpt from an official-domain source, classified by the founder, states the activity is prohibited or needs a licence the founder cannot obtain.')
            row['detected_by'].append('OFFICIAL_SOURCE')
            raise_to(row, 'HARD_STOP')
    if legal['outcome'] != 'HARD_STOP':
        if jur['status'] != 'IDENTIFIED':
            legal['reasons'].append(f'Target jurisdiction is {jur["status"]}: legal status cannot be scoped. Name one country/city.')
            raise_to(legal, 'REVIEW_REQUIRED')
        if not legal['official_source']:
            legal['reasons'].append('No official source was checked. Legal status is UNKNOWN — this is not legal clearance and not a ban.')
            raise_to(legal, 'UNKNOWN_SOURCE')
    if regulated['outcome'] == 'REVIEW_REQUIRED' and not regulated['official_source']:
        regulated['reasons'].append('No regulator source checked yet (UNKNOWN_SOURCE). Professional advice recommended.')

    # Constrained model classification: escalate only, verbatim quotes only.
    model_flags = model_flags or []
    hay = ' \n'.join(t for _, t in texts) + ' \n' + values
    norm = lambda s: re.sub(r'\s+', ' ', (s or '').casefold()).strip()
    accepted_flags, rejected_flags = [], []
    for f in model_flags:
        rid, quote = f.get('rule_id'), (f.get('quote') or '').strip()
        if rid not in rows or len(quote) < 6 or norm(quote) not in norm(hay):
            rejected_flags.append({**f, 'why_rejected': 'unknown rule or quote not found verbatim in the brief'})
            continue
        row = rows[rid]
        accepted_flags.append(f)
        row['detected_by'].append('MODEL_CLASSIFIER_ESCALATION')
        row['spans'].append({'field': 'model_quote', 'text': quote[:200]})
        if row['outcome'] in ('CLEAR', 'UNKNOWN_SOURCE', 'NOT_APPLICABLE'):
            row['reasons'].append('The local model flagged this passage for this rule. A model flag can only request founder review; it cannot hard-stop.')
            row['outcome'] = 'REVIEW_REQUIRED'

    for row in rows.values():
        if row['outcome'] == 'REVIEW_REQUIRED':
            row['founder_review_scope'] = 'RESEARCH_ONLY: founder acknowledgment allows desk research and founder-run tests only. Never publishing, building, launching or legal clearance.'
        if row['outcome'] == 'CLEAR' and not row['reasons']:
            row['reasons'].append('No indicator found in the brief for this rule. (Absence of a match is not proof.)')

    guards = []
    for gid, rx, why, neg in _GUARDS:
        for field, t in texts:
            sp = _spans(rx, t, field, neg)
            if sp:
                guards.append({'guard_id': gid, 'outcome': 'HARD_STOP', 'reason': why, 'spans': sp})
                break

    ordered = [rows[r] for r in RULE_IDS]
    status = 'BLOCK' if any(r['outcome'] == 'HARD_STOP' for r in ordered) or guards else \
        'REVIEW_REQUIRED' if any(r['outcome'] == 'REVIEW_REQUIRED' for r in ordered) else 'ALLOW_DISCOVERY'
    # Legacy-compatible flat findings list (used by UI summaries and older tests).
    findings = []
    for r in ordered:
        if r['outcome'] in ('HARD_STOP', 'REVIEW_REQUIRED'):
            findings.append({'rule_id': r['rule_id'], 'severity': 'BLOCK' if r['outcome'] == 'HARD_STOP' else 'REVIEW',
                             'reason': ' '.join(r['reasons'][:2]), 'matched_text': [s.get('text') for s in r['spans'][:2]],
                             'safe_revision': _revision(r['rule_id'], r['outcome'])})
    for g in guards:
        findings.append({'rule_id': g['guard_id'], 'severity': 'BLOCK', 'reason': g['reason'],
                         'matched_text': [s['text'] for s in g['spans']], 'safe_revision': 'Remove this instruction. FounderOS never acts externally and its gates cannot be changed by text.'})
    return {'status': status, 'policy_version': POLICY_VERSION, 'policy_hash': POLICY_HASH, 'jurisdiction': jur,
            'rules': ordered, 'system_guards': guards, 'findings': findings,
            'counts': {o: sum(1 for r in ordered if r['outcome'] == o) for o in ('HARD_STOP', 'REVIEW_REQUIRED', 'UNKNOWN_SOURCE', 'CLEAR', 'NOT_APPLICABLE')},
            'model_classifier': {'accepted_flags': accepted_flags, 'rejected_flags': rejected_flags,
                                 'note': 'Model flags escalate to founder review only and need a verbatim brief quote.'},
            'feasibility_notes': feasibility_notes(fields), 'limitations': LIMITATIONS}


def _revision(rule_id, outcome):
    return {
        'physical_goods_exclusion': 'Make the core deliverable digital (software, content, a service delivered online). Software FOR a physical business is fine.',
        'financial_crypto_exclusion': 'Remove trading/lending/advice/tokens/handling of users\' money. Accepting your own fees via an external payment processor is different.',
        'health_legal_advice_exclusion': 'Remove diagnosis, treatment, symptom interpretation or individual legal guidance. Labels like "educational" do not change what the product does.',
        'advice_in_disguise': 'Describe exactly what users would act on. If they would act on it for health, money or legal decisions, redesign or consult a professional.',
        'income_promise_dependency': 'Remove promises of income or guaranteed outcomes; describe outcomes as untested hypotheses.',
        'fake_proof_dependency': 'Remove fabricated reviews, sign-ups, testimonials or urgency. Collect real, consented feedback instead.',
        'impersonation_dependency': 'Speak only as your own brand. Get written authorization before using another organization\'s name.',
        'money_or_credentials_dependency': 'Remove holding/moving money and storing passwords, keys or card data. Use established external processors and login providers.',
        'harm_to_people': 'Remove the harmful function. Products built to hurt or deceive people are rejected regardless of market size.',
        'founder_values_conflict': 'Revise the idea to honour the stated value, or revise the value statement if it no longer reflects you.',
        'regulated_or_sensitive_area': 'Minimize the data you need, plan consent, and consult a qualified professional for the target market.',
        'illegal_in_target_market': 'Name the exact jurisdiction and check an official source (regulator, statute, government guidance).',
    }.get(rule_id, 'Revise the brief.')


def feasibility_notes(fields: dict) -> list[str]:
    notes = []
    if not fields.get('budget'):
        notes.append('Budget UNKNOWN: experiment costs cannot be checked against your limits.')
    elif re.search(r'^\s*(0|zero|none|no budget)\b', str(fields.get('budget')), re.I):
        notes.append('Stated budget is zero: only free experiments (interviews, manual opt-in forms) are feasible.')
    if not fields.get('timeline'):
        notes.append('Timeline UNKNOWN: time-boxes are estimates only.')
    if not fields.get('skills'):
        notes.append('Founder skills UNKNOWN: build feasibility cannot be assessed.')
    return notes


def find_blocks(text: str) -> list[dict]:
    """Hard-stop findings for arbitrary text (experiment designs, feedback, agent outputs)."""
    a = screen(text, {'idea': text})
    return [f for f in a['findings'] if f['severity'] == 'BLOCK']


def looks_like_injection(text: str) -> bool:
    return bool(_GUARDS[0][1].search(text or ''))


def screen_agent_output(report: dict) -> list[dict]:
    """Re-screen model outputs (PDF p.4: 'Run the screen again ... on the outputs'). Flags prohibited TACTICS
    proposed by the agent; the founder's idea is not blocked by what a model wrote."""
    flags = []

    def walk(v, path):
        if isinstance(v, str):
            for f in find_blocks(v):
                flags.append({'field': path, 'rule_id': f['rule_id'], 'text': v[:220], 'reason': f['reason']})
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f'{path}[{i}]')
        elif isinstance(v, dict):
            for k, x in v.items():
                if not str(k).startswith('_'):
                    walk(x, f'{path}.{k}' if path else k)
    walk(report, '')
    return flags[:20]


OFFICIAL_SUFFIXES = ('.gov', '.gov.eg', '.gov.uk', '.gov.sa', '.gov.ae', '.gov.jo', '.gouv.fr', '.gob.es', '.gc.ca', '.gov.in',
                     '.gov.au', '.govt.nz', '.europa.eu', '.gov.ng', '.go.ke', '.gov.ma', '.gov.tn', '.gov.qa', '.gov.kw', '.gov.lb',
                     '.gov.tr', '.gov.pk', '.bund.de', '.int')
OFFICIAL_HOSTS = ('legislation.gov.uk', 'eur-lex.europa.eu', 'www.ecfr.gov', 'www.law.cornell.edu')


def is_official_domain(host: str) -> bool:
    """Heuristic only: a government-style domain is necessary, not sufficient, for 'official'."""
    host = (host or '').lower().rstrip('.')
    return host in OFFICIAL_HOSTS or any(host.endswith(s) for s in OFFICIAL_SUFFIXES)
