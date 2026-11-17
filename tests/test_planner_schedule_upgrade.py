"""Regression checks for the functional local-only seven-day planner prototype."""
from backend.app.agents.website_builder import build


def test_planner_generates_real_schedule_controls():
    spec = {
        'archetype': 'planner', 'name': 'StudyFlow',
        'entity': {'singular': 'task', 'plural': 'tasks'},
        'attributes': [], 'areas': [], 'accent': '#0E6E62',
        'status_label': 'DEMO-ONLY', 'headline': 'Study smarter',
        'user_stories': [],
    }
    files = build(spec, 11)
    assert set(files) == {'index.html', 'styles.css', 'app.js', 'README.txt'}
    assert 'Personalized 7-day study plan' in files['index.html']
    assert 'Estimated hours' in files['index.html']
    assert 'Study hours available per day' in files['index.html']
    assert 'scheduleTasks' in files['app.js']
    assert 'cannot fit before its deadline' in files['app.js']
    assert 'textContent' in files['app.js']
    assert 'deterministic demo scheduler' in files['index.html']
