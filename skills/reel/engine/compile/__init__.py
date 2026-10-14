"""Plan-to-video compiler: engine/compile_plan.py is the CLI; this package holds the per-style adapters.

  common.py           project loading, word windows, anchors, text helpers, safe JSON writes
  validate.py         plan + per-beat validators (fail with the beat id)
  kinds.py            plan component + on-screen text -> one neutral "shot kind" every adapter understands
  heroes.py           hero beats (component "custom"): a validated kit fallback now, the idea queued in work/hero_todo.json
  items.py            insert items shared by the adapters (kit pieces, word_card, odometer, typer, comment)
  split_engine.py     shared edl / project.json writer + motion presets (calm, polished) for split-engine styles
  split_deck.py       split-deck adapter
  motion_editorial.py motion-editorial adapter
  runner.py           draft render, final render (render -> deliver -> QA) with a worker cap
  kit_insert.py       split-engine inserts the compiled projects use ("kit", "word_card"); loaded by compose.py
"""
