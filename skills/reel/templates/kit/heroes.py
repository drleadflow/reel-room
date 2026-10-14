"""heroes: the Reel Room hero library (batch 1). Importing it registers every hero's contract in
heroes_base.HEROES; rrkit calls register(Kit, COMPONENTS) once so each hero is a Kit method and a planner component.

  title-stamp, word-stamp, magazine-cover        heroes_type.py
  money-counter, cycle-chart, evidence-hero      heroes_data.py
  nle-timeline, palette-fan                      heroes_edit.py
  video-card                                     heroes_card.py
  grid-collapse, reel-orbit                      heroes_frame.py
  fire-timeline                                  heroes_fire.py
Contracts (typed fields, fits, layouts, min window): heroes_base.catalog(); validator: engine/hero_schema.py.
Docs: references/kit.md section 5 ("Hero library").
"""
import importlib

from heroes_base import HEROES, catalog, register  # noqa: F401

for _m in ("heroes_type", "heroes_data", "heroes_edit", "heroes_card", "heroes_frame", "heroes_fire"):
    try:
        importlib.import_module(_m)
    except ModuleNotFoundError as exc:      # a module still being built: the others stay usable
        if exc.name != _m:
            raise
