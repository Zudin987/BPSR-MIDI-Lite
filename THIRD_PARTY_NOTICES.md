# Third-party notices

## ok-star-resonance

Project: `Sanheiii/ok-star-resonance`

The in-game keyboard mapping and general MIDI-player behavior were studied from the user-provided AGPL-3.0 source archive. BPSR MIDI Lite is distributed with source under AGPL-3.0.

## mido

Project: `mido`

Purpose: MIDI parsing and writing.

See the package/project distribution for its current license terms.

## pynput

Project: `pynput`

License: GNU Lesser General Public License v3.0.

Purpose: optional Windows keyboard-input compatibility backend.

## Online Sequencer

BPSR MIDI Lite can read public Online Sequencer sequence data and search the public sequence page.

Title search first makes a normal anonymous HTTPS request. If Online Sequencer requires interactive browser verification, the user can choose **Verify once** and complete that check in Firefox.

After that explicit user action, the application may reuse existing `onlinesequencer.net` cookies from the local Firefox profile together with the installed Firefox user agent. Those cookie values are sent only back to `onlinesequencer.net`. They are not displayed in the app, copied into application settings, or sent to unrelated services.

The application does not request Online Sequencer usernames or passwords and does not provide a login, paywall, or DRM bypass.

Direct public sequence URL / numeric-ID loading remains available independently of title search.

## Microlink

For a directly loaded public Online Sequencer sequence, BPSR MIDI Lite may send that public sequence URL to the Microlink metadata API to resolve display-only title and author information.

This metadata lookup is optional. MIDI download, analysis and playback continue to work if the metadata service is unavailable.
