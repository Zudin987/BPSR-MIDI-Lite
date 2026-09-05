"""Generate an original synthetic audio fixture; no media is stored in git."""
from __future__ import annotations

import array
import math
import random
import wave
from pathlib import Path


def make_song(path: Path, duration=6.0, rate=44100):
    randomizer = random.Random(42)
    output = array.array("h")
    melody = (72, 74, 76, 79, 76, 74, 72, 67)
    for index in range(int(duration*rate)):
        t = index/rate
        if t < .5:
            value = 0
        else:
            elapsed = t-.5
            beat = int(elapsed/.5)
            position = elapsed % .5
            envelope = math.exp(-position*4) * min(1, position/.01)
            pitches = (48, 60, 64, 67, melody[beat % len(melody)])
            value = sum(math.sin(2*math.pi*(440*2**((p-69)/12))*elapsed) * (.045 if p < 70 else .10) for p in pitches)*envelope
            value += .12*math.sin(2*math.pi*70*position)*math.exp(-position*28)
            if beat % 2:
                value += randomizer.uniform(-.08, .08)*math.exp(-position*35)
        sample = int(max(-1, min(1, value))*32767)
        output.extend((sample, sample))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(output.tobytes())
