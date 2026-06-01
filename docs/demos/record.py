#!/usr/bin/env python3
"""Record rich (animated) QDash UI demos for the docs and package them as GIFs.

Drives a real Chromium with Playwright, records a video of a YAML scenario
(smooth motion, cursor, typing animation, panel drags), and converts it to a
high-quality GIF with ffmpeg. Scenarios live in ``docs/demos/scenarios/`` and the
GIFs land in ``docs/public/images/guides/`` so they can be referenced from the
VitePress user guide as ``/images/guides/<name>.gif``.

Run it through uv so Playwright is available without touching the project env:

    uv run --with playwright python3 docs/demos/record.py \
        --scenario docs/demos/scenarios/login.yaml

The first run downloads Chromium into ~/.cache/ms-playwright. The local QDash
stack must be running (e.g. ``task dev-local``) and reachable at ``UI_PORT``
from ``.env``.

This script is self-contained: it has no dependency outside Playwright + ffmpeg.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from string import Template
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# .env + scenario loading
# --------------------------------------------------------------------------- #


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = Template(value).safe_substitute(values | os.environ)
    return values


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit(f"Scenario must be a YAML mapping: {path}")
        return data
    except ImportError:
        return _load_minimal_yaml(path)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.lstrip("-").isdigit():
        return int(value)
    if len(value) >= 2 and value[0] == value[-1] and value.startswith(("'", '"')):
        return value[1:-1]
    return value


def _parse_key_value(text: str) -> tuple[str, Any]:
    if ":" not in text:
        raise SystemExit(f"Unsupported YAML line: {text}")
    key, value = text.split(":", 1)
    return key.strip(), _parse_scalar(value)


def _load_minimal_yaml(path: Path) -> dict[str, Any]:
    """Parse the small scenario YAML subset without PyYAML (fallback)."""
    lines = [
        line.rstrip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    result: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(" "):
            raise SystemExit(f"Unexpected indentation at top level: {line}")
        key, value = _parse_key_value(line)
        if value != "":
            result[key] = value
            index += 1
            continue
        index += 1
        if key == "steps":
            steps: list[dict[str, Any]] = []
            while index < len(lines) and lines[index].startswith("  - "):
                step_key, step_value = _parse_key_value(lines[index][4:])
                step: dict[str, Any] = {step_key: step_value}
                index += 1
                while index < len(lines) and lines[index].startswith("    "):
                    child_key, child_value = _parse_key_value(lines[index].strip())
                    step[child_key] = child_value
                    index += 1
                steps.append(step)
            result[key] = steps
        else:
            mapping: dict[str, Any] = {}
            while (
                index < len(lines)
                and lines[index].startswith("  ")
                and not lines[index].startswith("  - ")
            ):
                child_key, child_value = _parse_key_value(lines[index].strip())
                mapping[child_key] = child_value
                index += 1
            result[key] = mapping
    return result


def expand(value: str, env: dict[str, str]) -> str:
    return Template(value).safe_substitute(env | os.environ)


def validate_scenario(scenario: dict[str, Any]) -> None:
    if not scenario.get("name"):
        raise SystemExit("Scenario is missing name")
    target = scenario.get("target")
    if not isinstance(target, dict) or not target.get("url"):
        raise SystemExit("Scenario is missing target.url")
    steps = scenario.get("steps")
    if not isinstance(steps, list) or not steps:
        raise SystemExit("Scenario must contain non-empty steps")
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or not step.get("action"):
            raise SystemExit(f"Step {index} is missing action")


# --------------------------------------------------------------------------- #
# Playwright recording
# --------------------------------------------------------------------------- #

# A small on-screen cursor injected into every page so the recorded video shows
# where clicks happen. add_init_script runs before page scripts, so we wait for
# the body to exist before attaching the dot.
CURSOR_JS = """
() => {
  const ensure = () => {
    if (!document.body || document.getElementById('pw-cursor')) return;
    const dot = document.createElement('div');
    dot.id = 'pw-cursor';
    Object.assign(dot.style, {
      position: 'fixed', left: '0px', top: '0px', width: '20px', height: '20px',
      marginLeft: '-10px', marginTop: '-10px', borderRadius: '50%',
      background: 'rgba(59,130,246,0.35)', border: '2px solid #3b82f6',
      boxShadow: '0 0 6px rgba(59,130,246,0.6)', pointerEvents: 'none',
      zIndex: '2147483647', transition: 'width .1s, height .1s, background .1s',
    });
    document.body.appendChild(dot);
  };
  document.addEventListener('DOMContentLoaded', ensure);
  ensure();
  document.addEventListener('mousemove', (e) => {
    const dot = document.getElementById('pw-cursor');
    if (dot) { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }
  }, true);
  document.addEventListener('mousedown', () => {
    const dot = document.getElementById('pw-cursor');
    if (dot) { dot.style.width = '12px'; dot.style.height = '12px';
               dot.style.background = 'rgba(59,130,246,0.6)'; }
  }, true);
  document.addEventListener('mouseup', () => {
    const dot = document.getElementById('pw-cursor');
    if (dot) { dot.style.width = '20px'; dot.style.height = '20px';
               dot.style.background = 'rgba(59,130,246,0.35)'; }
  }, true);
}
"""


def parse_viewport(value: str | None, default: str = "1280x800") -> dict[str, int]:
    text = (value or default).lower().replace(" ", "")
    width, _, height = text.partition("x")
    return {"width": int(width), "height": int(height)}


async def smart_locator(page: Any, target: str, kind: str = "click") -> Any:
    """Resolve a visible-text/description target into a Playwright locator.

    Honours explicit engine prefixes (css=, xpath=, text=) and otherwise tries
    role-based (matches title/aria-label too) and text-based strategies.
    """
    if target.startswith(("css=", "xpath=", "text=", "//")):
        return page.locator(target).first

    if kind == "fill":
        factories = [
            page.get_by_placeholder,
            page.get_by_label,
            lambda t: page.get_by_role("textbox", name=t),
        ]
        fallback = page.locator(
            f"input[name='{target}'], textarea[name='{target}'], "
            f"input[placeholder*='{target}'], input[type='text']"
        ).first
    else:
        factories = [
            lambda t: page.get_by_role("button", name=t),
            lambda t: page.get_by_role("link", name=t),
            lambda t: page.get_by_role("tab", name=t),
            lambda t: page.get_by_role("menuitem", name=t),
            lambda t: page.get_by_role("checkbox", name=t),
            page.get_by_text,
        ]
        fallback = page.get_by_text(target).first

    for factory in factories:
        loc = factory(target).first
        try:
            if await loc.count() > 0:
                return loc
        except Exception as exc:
            logger.debug("locator strategy failed for target %r", target, exc_info=exc)
            continue
    return fallback


async def move_cursor_to(page: Any, locator: Any, steps: int = 25) -> None:
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
        box = await locator.bounding_box()
    except Exception:
        box = None
    if box:
        await page.mouse.move(
            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps
        )


async def do_login(page: Any, scenario: dict[str, Any], env: dict[str, str]) -> None:
    auth = scenario.get("auth") or {}
    username = env.get(str(auth.get("usernameEnv", "")), "")
    password = env.get(str(auth.get("passwordEnv", "")), "")
    if not username or not password:
        print("[login] credentials not found in env; skipping login", file=sys.stderr)
        return
    user_field = await smart_locator(page, "username", kind="fill")
    try:
        if await user_field.count() == 0:
            user_field = page.locator("input[type='text'], input[name*='user' i]").first
    except Exception as exc:
        logger.debug("failed to count username field locator", exc_info=exc)
    await user_field.fill(username)
    await page.locator("input[type='password']").first.fill(password)
    submit = await smart_locator(page, "Sign In", kind="click")
    try:
        if await submit.count() == 0:
            submit = page.locator("button[type='submit'], button:has-text('Login')").first
    except Exception as exc:
        logger.debug("failed to count submit locator", exc_info=exc)
    await submit.click()
    # Login sets an auth cookie via a client-side request; poll for it so a
    # following storage_state() actually captures the session.
    context = page.context
    for _ in range(40):
        cookies = await context.cookies()
        if any(c.get("name") in {"access_token", "session", "token"} for c in cookies):
            break
        await page.wait_for_timeout(250)
    await page.wait_for_load_state("networkidle")


async def run_step(
    page: Any,
    step: dict[str, Any],
    env: dict[str, str],
    opts: argparse.Namespace,
    scenario: dict[str, Any],
    frames_dir: Path,
    index: int,
) -> None:
    action = step["action"]
    label = step.get("label", f"step-{index:02d}")
    optional = bool(step.get("optional"))
    timeout = int(step.get("timeoutMs", opts.timeout))

    async def settle() -> None:
        await page.wait_for_timeout(opts.pause)

    try:
        if action == "navigate":
            url = expand(str(step.get("url") or "${TARGET_URL}"), env)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            await settle()

        elif action == "login":
            when = step.get("whenText")
            if when and not await page.get_by_text(str(when), exact=False).first.is_visible():
                print(f"[{label}] already authenticated; skipping login", file=sys.stderr)
                return
            await do_login(page, scenario, env)
            await settle()

        elif action in {"click", "hover"}:
            loc = await smart_locator(page, expand(str(step["target"]), env), kind="click")
            await move_cursor_to(page, loc)
            await page.wait_for_timeout(150)
            if action == "click":
                await loc.click(timeout=timeout)
            else:
                await loc.hover(timeout=timeout)
            await settle()

        elif action == "fill":
            loc = await smart_locator(page, expand(str(step["target"]), env), kind="fill")
            await move_cursor_to(page, loc)
            await loc.click(timeout=timeout)
            await loc.fill("")
            await loc.press_sequentially(
                expand(str(step.get("value", "")), env), delay=opts.type_delay
            )
            await settle()

        elif action == "drag":
            # Grab an element and drag it by a pixel offset (dx/dy). Ideal for
            # resize handles / separators.
            loc = await smart_locator(page, expand(str(step["target"]), env), kind="click")
            await loc.scroll_into_view_if_needed(timeout=timeout)
            box = await loc.bounding_box()
            if not box:
                raise RuntimeError(f"drag target not found: {step['target']}")
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            dx, dy = float(step.get("dx", 0)), float(step.get("dy", 0))
            await page.mouse.move(cx, cy, steps=12)
            await page.wait_for_timeout(150)
            await page.mouse.down()
            await page.wait_for_timeout(120)
            await page.mouse.move(cx + dx, cy + dy, steps=35)
            await page.wait_for_timeout(120)
            await page.mouse.up()
            await settle()

        elif action == "press":
            await page.keyboard.press(str(step.get("value", step.get("text", "Enter"))))
            await settle()

        elif action == "scroll":
            await page.mouse.wheel(0, int(step.get("value", 400)))
            await settle()

        elif action == "waitForText":
            text = expand(str(step["text"]), env)
            await page.get_by_text(text, exact=False).first.wait_for(
                state="visible", timeout=timeout
            )

        elif action == "wait":
            await page.wait_for_timeout(int(step.get("value", opts.pause)))

        elif action == "capture":
            await settle()
            frames_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(frames_dir / f"{index:03d}-{label}.png"))

        elif action == "reload":
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            await settle()

        elif action == "note":
            print(f"[note] {expand(str(step.get('text', '')), env)}", file=sys.stderr)

        else:
            print(f"[{label}] unsupported action '{action}'", file=sys.stderr)

    except Exception as exc:
        if optional:
            print(f"[{label}] optional step failed, continuing: {exc}", file=sys.stderr)
            return
        raise


async def preauth_storage_state(
    browser: Any, scenario: dict[str, Any], env: dict[str, str], viewport: dict[str, int]
) -> dict[str, Any]:
    """Log in once in a throwaway, non-recorded context so the demo video starts
    on the real screen instead of the login form."""
    auth = scenario.get("auth") or {}
    target_url = expand(str(scenario["target"]["url"]), env)
    parts = target_url.split("/", 3)
    origin = "/".join(parts[:3]) if len(parts) >= 3 else target_url
    context = await browser.new_context(viewport=viewport)
    page = await context.new_page()
    await page.goto(origin + str(auth.get("loginPath", "/login")), wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    await do_login(page, scenario, env)
    state = await context.storage_state()
    await context.close()
    return state


async def record(opts: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    scenario = load_yaml(opts.scenario_path)
    validate_scenario(scenario)
    env = load_env(opts.repo_root / ".env")
    viewport = parse_viewport(scenario.get("target", {}).get("viewport"), opts.viewport)

    run_dir = opts.out_dir
    video_dir = run_dir / "video"
    frames_dir = run_dir / "frames"
    video_dir.mkdir(parents=True, exist_ok=True)

    env["TARGET_URL"] = expand(str(scenario["target"]["url"]), env)
    auth = scenario.get("auth") or {}

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=not opts.headed, slow_mo=opts.slowmo)
        except Exception as exc:
            if "Executable doesn" in str(exc) or "playwright install" in str(exc):
                print("[setup] installing Chromium for Playwright (one-time)...", file=sys.stderr)
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"], check=True
                )
                browser = await pw.chromium.launch(headless=not opts.headed, slow_mo=opts.slowmo)
            else:
                raise

        storage_state = None
        if auth and not opts.include_login:
            storage_state = await preauth_storage_state(browser, scenario, env, viewport)

        context = await browser.new_context(
            viewport=viewport,
            device_scale_factor=opts.scale,
            record_video_dir=str(video_dir),
            record_video_size=viewport,
            storage_state=storage_state,
        )
        await context.add_init_script(CURSOR_JS)
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.create_task(d.accept()))

        steps = scenario["steps"]
        for index, step in enumerate(steps, start=1):
            if step["action"] == "login" and storage_state is not None:
                continue
            await run_step(page, step, env, opts, scenario, frames_dir, index)

        await page.wait_for_timeout(opts.pause)
        await context.close()
        await browser.close()

    webm = run_dir / f"{scenario['name']}.webm"
    recorded = sorted(video_dir.glob("*.webm"))
    if recorded:
        shutil.move(str(recorded[-1]), str(webm))

    result: dict[str, Any] = {
        "scenario": scenario["name"],
        "out_dir": str(run_dir),
        "video": str(webm) if webm.exists() else None,
        "steps": len(steps),
    }
    if webm.exists() and not opts.no_gif:
        gif = opts.gif or (opts.gif_dir / f"{scenario['name']}.gif")
        gif.parent.mkdir(parents=True, exist_ok=True)
        convert_video_to_gif(webm, gif, fps=opts.fps, width=opts.gif_width)
        result["gif"] = str(gif)
    return result


def convert_video_to_gif(video: Path, output: Path, *, fps: int, width: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to convert the recording to GIF.")
    output.parent.mkdir(parents=True, exist_ok=True)
    palette = output.with_suffix(".palette.png")
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    subprocess.run(  # noqa: S603 - ffmpeg path is resolved locally and args are not shell-expanded.
        [ffmpeg, "-y", "-i", str(video), "-vf", f"{vf},palettegen=stats_mode=diff", str(palette)],
        check=True,
    )
    subprocess.run(  # noqa: S603 - ffmpeg path is resolved locally and args are not shell-expanded.
        [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-i",
            str(palette),
            "-lavfi",
            f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
            str(output),
        ],
        check=True,
    )
    palette.unlink(missing_ok=True)


def main() -> int:
    repo_root_default = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="path to a scenario YAML")
    parser.add_argument("--repo-root", default=str(repo_root_default), help="repo root for .env")
    parser.add_argument(
        "--out-dir", default=None, help="working dir for video/frames (default: .tmp)"
    )
    parser.add_argument("--gif", default=None, help="explicit output GIF path")
    parser.add_argument(
        "--gif-dir",
        default=None,
        help="output dir for the GIF (default: docs/public/images/guides)",
    )
    parser.add_argument("--viewport", default="1280x800")
    parser.add_argument(
        "--scale", type=float, default=1.0, help="device scale factor (2 = crisper, larger files)"
    )
    parser.add_argument(
        "--headed", action="store_true", help="show the browser window while recording"
    )
    parser.add_argument(
        "--include-login",
        action="store_true",
        help="record the login flow instead of pre-authenticating",
    )
    parser.add_argument(
        "--slowmo", type=float, default=0, help="ms delay added to every Playwright action"
    )
    parser.add_argument(
        "--pause", type=int, default=700, help="ms pause after each step (demo pacing)"
    )
    parser.add_argument(
        "--type-delay", type=int, default=55, help="ms per character when typing into fields"
    )
    parser.add_argument(
        "--timeout", type=int, default=30000, help="default ms timeout for waits/clicks"
    )
    parser.add_argument("--fps", type=int, default=16, help="GIF frame rate")
    parser.add_argument("--gif-width", type=int, default=1000, help="GIF width in px (height auto)")
    parser.add_argument(
        "--no-gif", action="store_true", help="record video only, skip GIF conversion"
    )
    args = parser.parse_args()

    args.repo_root = Path(args.repo_root).expanduser().resolve()
    args.scenario_path = Path(args.scenario).expanduser().resolve()
    args.gif_dir = (
        Path(args.gif_dir).expanduser().resolve()
        if args.gif_dir
        else args.repo_root / "docs" / "public" / "images" / "guides"
    )
    args.gif = Path(args.gif).expanduser().resolve() if args.gif else None
    args.out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if args.out_dir
        else args.repo_root / ".tmp" / "docs-demos" / args.scenario_path.stem
    )

    result = asyncio.run(record(args))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
