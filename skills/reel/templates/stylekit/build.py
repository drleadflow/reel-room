#!/usr/bin/env python3
"""build.py <project> --out <dir> [--no-render] [--qa-only]

One command for any stylekit template (project.json "template": floating-cards | carousel-slideup | desk-demo):
  1. templates/<template>/compose.py compose(project)  -> index.html + work/meta.json (prepares base video first)
  2. hyperframes lint (0 errors) + render -> renders/raw.mp4
  3. sound: voice untouched + synthesized SFX cues (>= 18 LU under), video at ~9.5 Mbps, -14 LUFS / -1.5 dBTP master
  4. <out>/demo.mp4, <out>/loop.mp4 (6 s, silent, < 4 MB), <out>/poster.jpg
  5. stylekit/qa.py -> <out>/qa/report.json + contact sheets (exit 1 when anything fails)
"""
import importlib.util
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kit  # noqa: E402
import skqa as qa  # noqa: E402


def load_template(name):
    path = os.path.join(kit.TEMPLATES, name, "compose.py")
    if not os.path.exists(path):
        raise SystemExit(f"unknown template '{name}' (no {path})")
    spec = importlib.util.spec_from_file_location(f"tpl_{name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args or "--out" not in argv:
        raise SystemExit(__doc__)
    project = os.path.abspath(args[0])
    out = os.path.abspath(argv[argv.index("--out") + 1])
    os.makedirs(os.path.join(out, "qa"), exist_ok=True)
    pj = kit.jload(os.path.join(project, "project.json"))
    tpl = load_template(pj["template"])
    demo = os.path.join(out, "demo.mp4")
    t = time.time()
    if "--qa-only" not in argv:
        meta = tpl.compose(project)
        errs, warns, findings = kit.lint(project)
        print(f"lint: {errs} error(s), {warns} warning(s)")
        if errs:
            print(findings)
            raise SystemExit("lint errors; fix before rendering")
        raw = os.path.join(project, "renders", "raw.mp4")
        if "--no-render" not in argv or not os.path.exists(raw):
            dt = kit.render(project, "renders/raw.mp4")
            print(f"render: {dt:.0f}s")
        mix = kit.mix_and_master(project, raw, os.path.join(project, meta["voice_src"]), meta["cues"], demo,
                                 meta["frames"], voice_offset_frames=meta.get("voice_offset_frames", 0))
        meta["mix"] = mix
        kit.jsave(os.path.join(project, "work", "meta.json"), meta)
        print(f"master: {mix['master']}, sfx margin {mix['sfx_margin_lu']} LU")
        lp = kit.make_loop(demo, os.path.join(out, "loop.mp4"), meta["loop"]["t0"], meta["loop"].get("dur", 6.0))
        print(f"loop: {lp}")
        kit.make_poster(demo, os.path.join(out, "poster.jpg"), meta["poster"]["t"])
        shutil.copyfile(os.path.join(project, "index.html"), os.path.join(out, "qa", "index.html"))
    res = qa.run(project, demo, os.path.join(out, "qa"))
    print(f"done in {time.time() - t:.0f}s -> {out}")
    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
