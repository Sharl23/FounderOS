"""Gate entry points. All gate logic is deterministic Python; model text never authorizes a transition.

The previous rule ("two verified supporting excerpts => PROCEED") was removed: source excerpts can
corroborate market background but can never establish customer demand. See decision.py.
"""
from .decision import discovery_gate, evaluate_validation  # noqa: F401

PHASES = ['discover', 'validate', 'build', 'commercial_setup', 'launch', 'operate_learn']
ACTIVE_PHASES = ('discover', 'validate')
