from pathlib import Path


WEB_ROOT = Path(__file__).parents[1] / "src" / "gui" / "web"


def test_lab_overview_explains_projects_and_links_to_each_one():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert "WELCOME TO THE LAB" in html
    assert "Choose a project to begin" in html
    assert html.count('class="lab-project-card"') == 5
    for project in ("source", "relationships", "grir", "fx", "timesheet"):
        assert f'data-lab-subtab="{project}"' in html
    assert html.count("<span>Objective</span>") == 5
    assert html.count("<span>Approach</span>") == 5
    assert html.count("<span>Method</span>") == 5


def test_lab_project_cards_have_responsive_styles():
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert ".lab-project-grid" in css
    assert ".lab-project-card" in css
    assert ".lab-project-brief" in css
