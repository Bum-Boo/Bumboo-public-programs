# Design notes

Grimoire uses a quiet illustrated-book direction with space around the familiar, readable status text, and restrained motion. The built-in book familiar is drawn by the application; imported character packs remain optional and separate from the interface.

## Color tokens

| Role | Night | Dawn |
| --- | --- | --- |
| Background | `#1E1E2E` | `#EFF1F5` |
| Surface | `#282839` | `#E6E9EF` |
| Elevated | `#313244` | `#DCE0E8` |
| Text | `#CDD6F4` | `#4C4F69` |
| Muted text | `#A6ADC8` | `#5C5F77` |
| Accent | `#CBA6F7` | `#7040B0` |
| Audio | `#94E2D5` | `#14766B` |
| Success | `#A6E3A1` | `#356A35` |
| Attention | `#F9E2AF` | `#775619` |
| Error | `#F38BA8` | `#B62C50` |

Machine-readable values live in `src/grimoire/theme.py`. Status uses a word and a visual cue. Motion communicates recorded state and can be reduced or disabled. Audio only influences the spectrum and aura; it does not change the meaning of task status.

The [night](evidence/night.png) and [dawn](evidence/dawn.png) previews use synthetic example tasks and the original built-in artwork.
