"""Product Architect agent (Phase 3, step 1-2): venture state -> structured product spec + user stories.

Deterministic (no model call): the spec is derived from the founder's confirmed brief fields and the
approved discovery direction. Everything that is not in the brief is labelled ASSUMPTION.
"""
from __future__ import annotations
import re

ARCHETYPES = {
    'directory': {'label': 'Searchable directory / listings',
                  'kw': r'\b(find|finding|discover\w*|search\w*|spaces?|places?|venues?|listings?|directory|near(by)?|cafes?|locations?|spots?|rooms?|providers?|tutors?|freelancers?|vendors?)\b'},
    'forecast': {'label': 'Tracker with simple forecast',
                 'kw': r'\b(predict\w*|forecast\w*|track\w*|inventory|stock|waste|ingredients?|usage|log\w*|monitor\w*|demand planning|orders? per day)\b'},
    'practice': {'label': 'Practice / quiz app',
                 'kw': r'\b(quiz\w*|practi[cs]e\w*|flashcards?|learn\w*|revision|exam prep|vocabulary|maths?|math)\b'},
    'planner': {'label': 'Planner / task tracker',
                'kw': r'\b(deadlines?|planner|plan\w*|schedul\w*|reminders?|assignments?|tasks?|to-?dos?|calendar)\b'},
    'tracker': {'label': 'Client and project tracker',
                'kw': r'\b(clients?|projects?|freelanc\w*|deliverables?|invoic\w*|milestones?|retainers?|agency|agencies|consultants?)\b'},
    'booking': {'label': 'Appointment booking',
                'kw': r'\b(book\w*|appointments?|slots?|reservations?|reserv\w*|availability|barbers?|salons?|walk-?ins?|sessions?)\b'},
}
BOOKING_SERVICES = [
    (r'\b(barber|hair|salon|beard)', ['Haircut (30 min)', 'Beard trim (15 min)', 'Haircut and beard (45 min)']),
    (r'\b(tutor|lesson|teacher|class)', ['Trial lesson (30 min)', 'Standard lesson (60 min)', 'Exam review (90 min)']),
    (r'\b(photo|photograph)', ['Portrait session (30 min)', 'Headshots (45 min)', 'Product shoot (60 min)']),
    (r'\b(repair|technician|laptop|phone)', ['Diagnosis (15 min)', 'Standard repair (60 min)', 'Pick-up slot (15 min)']),
]
GENERIC_SERVICES = ['Short session (30 min)', 'Standard session (60 min)', 'Long session (90 min)']

ATTRIBUTE_BANKS = [
    (r'\bstud(y|ying|ents?)\b', ['Wi-Fi', 'Quiet zone', 'Power outlets', 'Group tables', 'Open late']),
    (r'\b(restaurant|cafe|food|kitchen|ingredient)', ['Takeaway', 'Seating', 'Open late', 'Vegetarian options', 'Delivery']),
    (r'\b(tutor|teacher|lesson|course)', ['Online', 'In person', 'Beginner friendly', 'Weekend slots', 'Group sessions']),
    (r'\b(freelanc|designer|developer|agency)', ['Remote', 'Fixed price', 'Hourly', 'Portfolio', 'Fast turnaround']),
    (r'\b(event|workshop|meetup)', ['Free entry', 'Online', 'Weekend', 'Beginner friendly', 'Networking']),
]
GENERIC_ATTRS = ['Option A', 'Option B', 'Option C', 'Option D']

_STOP = set('a an and are as at be by for from has have i in into is it its my of on or our so that the their them they this to was we what when which who will with would want build tool app simple help helps using use based platform small local daily'.split())


def _text(brief: dict, discovery: dict | None) -> str:
    # The founder's own words dominate; captured fields add detail. Model text (idea_summary, discovery) is not used
    # to choose what to build, so a model hallucination cannot change the product type.
    own = brief.get('original_idea_text') or ''
    parts = [own, own] + [brief.get(k) or '' for k in ('problem', 'target_customers', 'current_workaround')]
    return ' '.join(parts)


def archetype(text: str) -> tuple[str, dict]:
    scores = {k: len(re.findall(v['kw'], text, re.I)) for k, v in ARCHETYPES.items()}
    best = max(scores, key=lambda k: (scores[k], -list(ARCHETYPES).index(k)))
    return (best if scores[best] else 'directory'), scores


def entity_noun(text: str, kind: str) -> tuple[str, str]:
    if kind == 'tracker':
        return 'project', 'projects'
    if kind == 'booking':
        return 'appointment', 'appointments'
    t = text.lower()
    pairs = [('study space', r'study (space|spot|room|place)s?'), ('ingredient', r'ingredients?'), ('tutor', r'tutors?'), ('cafe', r'cafes?'),
             ('restaurant', r'restaurants?'), ('workshop', r'workshops?'), ('freelancer', r'freelancers?'), ('assignment', r'assignments?'),
             ('venue', r'venues?'), ('task', r'tasks?'), ('question', r'questions?')]
    for noun, rx in pairs:
        if re.search(r'\b' + rx + r'\b', t):
            if kind == 'forecast' and noun == 'restaurant' and re.search(r'ingredient', t):
                continue
            return noun, noun + ('es' if noun.endswith('s') else 's')
    return {'directory': ('listing', 'listings'), 'forecast': ('item', 'items'), 'practice': ('question', 'questions'),
            'planner': ('task', 'tasks')}[kind]


def keyphrase(text: str, n: int = 4) -> str:
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", text or ''):
        if w.lower() in _STOP or len(w) < 3 or w.lower() in (x.lower() for x in out):
            continue
        out.append(w)
        if len(out) >= n:
            break
    return ' '.join(out)


def name_for(brief: dict, singular: str, kind: str) -> str:
    base = {'directory': f'{singular.title()} Finder', 'forecast': f'{singular.title()} Planner', 'practice': 'Practice Coach', 'planner': 'Deadline Planner',
            'tracker': 'Client Project Tracker', 'booking': 'Appointment Booker'}[kind]
    tm = (((brief.get('fields') or {}).get('target_market') or {}).get('typed') or {})
    return f'{base} {tm.get("city")}' if tm.get('city') and kind == 'directory' else base


def _sentence(text, limit=120):
    t = re.split(r'(?<=[.!?])\s', (text or '').strip())[0].strip().rstrip('.')
    if len(t) > limit:
        t = t[:limit].rsplit(' ', 1)[0] + '…'
    return t


def _headline(brief, audience, problem):
    if not problem.startswith('ASSUMPTION'):
        return _sentence(problem)
    return _sentence(brief.get('original_idea_text') or brief.get('idea_summary')) or 'Prototype'


def spec(brief: dict, discovery: dict | None, verdict: str | None, mode: str, overrides: dict | None = None) -> dict:
    text = _text(brief, discovery)
    kind, scores = archetype(text)
    if overrides and overrides.get('archetype') in ARCHETYPES:
        kind = overrides['archetype']
    singular, plural = entity_noun(text, kind)
    attrs = next((a for rx, a in ATTRIBUTE_BANKS if re.search(rx, text, re.I)), GENERIC_ATTRS)
    if kind == 'booking':
        attrs = next((a for rx, a in BOOKING_SERVICES if re.search(rx, text, re.I)), GENERIC_SERVICES)
    elif kind == 'tracker':
        attrs = ['Not started', 'In progress', 'Waiting on client', 'Delivered']
    audience = brief.get('target_customers') or 'ASSUMPTION: target customer not confirmed in the brief'
    problem = brief.get('problem') or 'ASSUMPTION: problem not confirmed in the brief'
    tm = (((brief.get('fields') or {}).get('target_market') or {}).get('typed') or {})
    areas = {'Cairo': ['Downtown', 'Zamalek', 'Nasr City', 'Maadi', 'Heliopolis'], 'Giza': ['Dokki', 'Mohandessin', 'Haram', 'Sheikh Zayed']}.get(tm.get('city'), ['Area 1', 'Area 2', 'Area 3', 'Area 4'])
    features, stories = [], []

    def story(sid, as_a, want, so_that, acceptance):
        stories.append({'id': sid, 'as_a': as_a, 'i_want': want, 'so_that': so_that, 'acceptance': acceptance})

    plain = re.sub(r'\(.*?\)', '', audience).strip().rstrip('.')
    low = plain[:1].lower() + plain[1:] if plain[1:2].islower() else plain
    who = ('one of the ' + low[:80]) if plain and len(plain) <= 80 and not plain.startswith('ASSUMPTION') else (keyphrase(plain, 3) or 'user')
    if kind == 'directory':
        features = [{'id': 'F1', 'title': f'Browse {plural}', 'check': 'list'}, {'id': 'F2', 'title': 'Search by name or area', 'check': 'search'},
                    {'id': 'F3', 'title': 'Filter by features', 'check': 'filters'}, {'id': 'F4', 'title': f'{singular.title()} details', 'check': 'detail'},
                    {'id': 'F5', 'title': 'Shortlist favourites (this session only)', 'check': 'shortlist'}]
        story('US1', who, f'to see {plural} near me', 'I can stop asking around', ['A list of demo ' + plural + ' is shown on load', 'Each card shows name, area and features'])
        story('US2', who, 'to search by name or area', 'I find a place quickly', ['Typing in the search box narrows the list on every keystroke', 'An empty result shows a clear message'])
        story('US3', who, 'to filter by the features I need', 'I only see suitable options', ['Ticking a feature shows only items that have it', 'Several features combine (AND)'])
        story('US4', who, 'to open details', 'I can decide where to go', ['Clicking a card opens its details', 'Details can be closed with a button or Escape'])
    elif kind == 'forecast':
        features = [{'id': 'F1', 'title': f'Log daily {singular} usage', 'check': 'form'}, {'id': 'F2', 'title': 'Usage history table', 'check': 'table'},
                    {'id': 'F3', 'title': 'Next-day forecast (7-day moving average)', 'check': 'forecast'}, {'id': 'F4', 'title': 'Over-order warning', 'check': 'warning'}]
        story('US1', who, f'to record how much of each {singular} I used today', 'I have a history to plan from', ['Submitting the form adds a row to the history', 'Invalid numbers are rejected with a message'])
        story('US2', who, 'to see a suggested quantity for tomorrow', 'I order less waste', ['The forecast is the average of the last 7 entries for that ' + singular, 'The method is shown next to the number'])
        story('US3', who, 'a warning when I plan to order far more than usual', 'I avoid over-ordering', ['Planned quantity above 130% of the forecast shows a warning'])
    elif kind == 'practice':
        features = [{'id': 'F1', 'title': 'Practice questions', 'check': 'quiz'}, {'id': 'F2', 'title': 'Instant feedback', 'check': 'feedback'},
                    {'id': 'F3', 'title': 'Score and retry', 'check': 'score'}]
        story('US1', who, 'to answer short practice questions', 'I can practise at home', ['One question at a time with choices', 'Choosing an answer shows right or wrong'])
        story('US2', who, 'to see my score', 'I know what to repeat', ['A score is shown at the end', 'A retry button restarts the set'])
    elif kind == 'tracker':
        features = [{'id': 'F1', 'title': 'Add clients', 'check': 'clients'}, {'id': 'F2', 'title': 'Add projects for a client with a delivery date', 'check': 'projects'},
                    {'id': 'F3', 'title': 'Add tasks to a project and mark them done', 'check': 'tasks'},
                    {'id': 'F4', 'title': 'Progress view: % done per project, late and at-risk deliveries, open work per client', 'check': 'progress'}]
        story('US1', who, 'to record each client once and attach projects to them', 'I stop tracking work across chats and notes',
              ['A client needs a name; duplicates are rejected', 'A project needs a client, a title and a delivery date'])
        story('US2', who, 'to break a project into tasks and tick them off', 'I know what is left before delivery',
              ['Adding a task to a project increases its task count', 'Marking a task done updates the project % immediately'])
        story('US3', who, 'to see which deliveries are late or at risk', 'I can warn a client before a deadline slips',
              ['Projects past their delivery date and not finished are marked Late', 'Projects due within 3 days with open tasks are marked At risk',
               'A per-client summary shows open tasks and the next delivery'])
    elif kind == 'booking':
        features = [{'id': 'F1', 'title': 'Available slots for the next 5 days', 'check': 'slots'},
                    {'id': 'F2', 'title': 'Booking form with validation', 'check': 'booking_form'},
                    {'id': 'F3', 'title': 'Confirmation summary (nothing is sent)', 'check': 'confirm'},
                    {'id': 'F4', 'title': 'Bookings list with cancel, which frees the slot', 'check': 'cancel'}]
        story('US1', who, 'to see which time slots are still free', 'I can book without calling back and forth',
              ['Only free slots can be chosen', 'Slots that are already booked are shown as taken'])
        story('US2', who, 'to book a service in a free slot', 'my appointment is recorded',
              ['A booking needs a client reference, a service and a free slot', 'Booking the same slot twice is refused with a message',
               'A confirmation summary is shown; it states that no message was sent'])
        story('US3', 'the service provider', 'to cancel a booking', 'the slot becomes available again',
              ['Cancelling removes the booking and the slot shows as free again'])
    else:
        features = [{'id': 'F1', 'title': f'Add {plural} with due dates', 'check': 'form'}, {'id': 'F2', 'title': 'Sorted by due date', 'check': 'table'},
                    {'id': 'F3', 'title': 'Overdue and due-soon highlighting', 'check': 'warning'}, {'id': 'F4', 'title': 'Mark done', 'check': 'done'}]
        story('US1', who, f'to add {plural} with a due date', 'nothing is forgotten', ['The form adds an item to the list', 'Items without a title are rejected'])
        story('US2', who, 'to see what is due soon', 'I start in time', ['The list is sorted by due date', 'Items due within 2 days are highlighted; overdue items are marked'])
        story('US3', who, 'to mark items done', 'I see progress', ['A done button moves the item to the completed count'])
    o = overrides or {}
    s = {
        'name': o.get('name') or name_for(brief, singular, kind),
        'headline': o.get('headline') or _headline(brief, audience, problem),
        'archetype': kind, 'archetype_label': ARCHETYPES[kind]['label'], 'archetype_scores': scores,
        'entity': {'singular': singular, 'plural': plural}, 'audience': audience, 'problem': problem,
        'current_workaround': brief.get('current_workaround') or 'ASSUMPTION: not stated in the brief',
        'attributes': (o.get('attributes') or attrs)[:8], 'areas': areas, 'accent': o.get('accent') or '#0E6E62',
        'features': features, 'user_stories': stories,
        'out_of_scope': ['Accounts, logins and passwords', 'Payments inside the prototype', 'Real business listings, reviews or bookings',
                         'Sending messages or notifications', 'Any server-side code'],
        'data_policy': 'DEMO DATA only: generated placeholder records, clearly labelled. No real businesses, people, reviews or bookings.',
        'mode': mode, 'validation_verdict_at_build': verdict,
        'status_label': ('DEMO-ONLY PROTOTYPE: not validated, not launch-ready, not commercially approved.' if mode == 'DEMO_ONLY'
                         else 'MVP PROTOTYPE built after the validation gate passed. Still not deployed.'),
        'show_search': o.get('show_search', True),
    }
    return s
