"""Single-use, exact-match edit; fail closed if source unexpectedly changed."""
from pathlib import Path

path = Path('player.py')
text = path.read_text(encoding='utf-8')
needle = 'from midi_engine import MidiPlan, PlannedEvent\n'
assert text.count(needle) == 1, 'Player imports changed'
text = text.replace(needle, 'from game_process import is_bpsr_process\n' + needle, 1)
needle = '        self._target_process_id = process_id\n'
assert text.count(needle) == 1, 'Player target capture changed'
text = text.replace(needle, '''        if not is_bpsr_process(process_id):
            raise RuntimeError(
                "BPSR game window was not focused when the countdown ended. "
                "Focus the game before the countdown reaches zero. If this "
                "regional executable is unrecognized, set BPSR_GAME_EXECUTABLES "
                "to its exact .exe name."
            )
        self._target_process_id = process_id
''', 1)
path.write_text(text, encoding='utf-8')
print('Added foreground BPSR identity guard to player.py')
