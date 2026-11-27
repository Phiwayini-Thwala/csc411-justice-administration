"""Assemble the three consoles and the portal from one shared stylesheet and one shared core.

    python frontend/console-src/build.py

Edit the files in this folder, not the generated index.html files, so the three
consoles keep the same look and behaviour:
  base.css + extra.css   styles shared by every page
  common.js              sign-in, navigation, modals, console switcher, status pings
  template.html          page shell
  police.js / judiciary.js / correctional.js   the screens of each console
  portal.html            frontend/index.html
"""
import sys
from pathlib import Path

src = Path(__file__).parent
repo = Path(sys.argv[1]) if len(sys.argv) > 1 else src.parent.parent   # the repository root
css = (src / "base.css").read_text() + "\n" + (src / "extra.css").read_text()
core = (src / "common.js").read_text()
tpl = (src / "template.html").read_text()

PAGES = {
    "police": dict(ORG="Police", CONSOLE="Police Console", ICON="👮", TAGLINE="Suspects, Arrests &amp; Cases",
                   SIGNIN_SUB="Sign in to manage suspects, arrests and cases", USER_HINT="police1",
                   out=repo / "police-service/app/static/index.html"),
    "judiciary": dict(ORG="Judiciary", CONSOLE="Court Console", ICON="⚖️", TAGLINE="Court Case Management",
                      SIGNIN_SUB="Sign in to manage court cases", USER_HINT="court1",
                      out=repo / "judiciary-service/app/static/index.html"),
    "correctional": dict(ORG="Correctional", CONSOLE="Custody Console", ICON="🏛️", TAGLINE="Inmate Custody Management",
                         SIGNIN_SUB="Sign in to manage inmates and facilities", USER_HINT="correctional1",
                         out=repo / "correctional-service/static/index.html"),
}
for me, p in PAGES.items():
    html = tpl
    for k, v in p.items():
        if k != "out":
            html = html.replace("{{%s}}" % k, v)
    html = html.replace("{{ME}}", me).replace("{{CSS}}", css).replace("{{JS}}", core + "\n" + (src / f"{me}.js").read_text())
    assert "{{" not in html, me
    p["out"].parent.mkdir(parents=True, exist_ok=True)
    p["out"].write_text(html)
    print("wrote", p["out"], len(html))

portal = (src / "portal.html").read_text().replace("{{CSS}}", css)
(repo / "frontend/index.html").write_text(portal)
print("wrote portal", len(portal))
