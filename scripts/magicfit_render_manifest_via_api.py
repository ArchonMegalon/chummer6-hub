#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


MAGICFIT_BASE = "https://magicfit.pushowl.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
ENV_PATHS = (
    Path("/docker/chummercomplete/chummer.run-services/.env"),
    Path("/docker/EA/.env"),
    Path("/docker/chummercomplete/.integrated/chummer6-hub/.env"),
)


@dataclass(frozen=True)
class SceneJob:
    asset: dict[str, Any]
    scene: dict[str, Any]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip() or None
    for path in ENV_PATHS:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'") or None
    return None


def safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_") or "item"


def clip_dir(out_root: Path, asset: dict[str, Any]) -> Path:
    return out_root / safe_name(asset.get("asset_id"))


def scene_path(out_root: Path, asset: dict[str, Any], scene: dict[str, Any], suffix: str) -> Path:
    return clip_dir(out_root, asset) / f"{safe_name(scene.get('id'))}{suffix}"


def url_timestamp(url: str) -> int:
    match = re.search(r"/magicfit/(\d+)-", url)
    return int(match.group(1)) if match else 0


def unescape_url(value: str) -> str:
    return value.replace("\\/", "/").replace("\\u0026", "&").replace("\\u003d", "=")


def collect_urls(text: str, extensions: tuple[str, ...]) -> list[str]:
    ext = "|".join(re.escape(item) for item in extensions)
    pattern = re.compile(
        rf"https:\\?/\\?/(?:cdn\.pushowl\.com|media\.powlcdn\.com)\\?/magicfit\\?/[^\"'\\\s<>]+?\.({ext})(?:[^\"'\\\s<>]*)?",
        flags=re.I,
    )
    urls = [unescape_url(match.group(0)).rstrip("),]") for match in pattern.finditer(text)]
    return sorted(set(urls), key=lambda item: (url_timestamp(item), item), reverse=True)


class MagicFitClient:
    def __init__(self, session_cookie: str) -> None:
        self.session = requests.Session()
        self.session.cookies.set("__session", session_cookie, domain="magicfit.pushowl.com")
        self.session.headers.update({"User-Agent": USER_AGENT})

    @staticmethod
    def login_via_playwright(email: str, password: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError:
            return MagicFitClient.login_via_node_playwright(email, password)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(30000)
            page.goto(f"{MAGICFIT_BASE}/home", wait_until="domcontentloaded")
            body = page.locator("body").inner_text(timeout=10000)
            if re.search(r"login|sign in|email|password", body, re.I):
                email_field = page.locator("input[type=email], input[name*=email i], input[placeholder*=email i]").first
                password_field = page.locator("input[type=password]").first
                email_field.fill(email)
                password_field.fill(password)
                page.get_by_role("button", name=re.compile("Sign in|Log in|Login|Continue|Submit", re.I)).first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(6000)
            cookies = {row["name"]: row["value"] for row in context.cookies()}
            browser.close()
        cookie = cookies.get("__session")
        if not cookie:
            raise RuntimeError("MagicFit login did not return a __session cookie")
        return cookie

    @staticmethod
    def login_via_node_playwright(email: str, password: str) -> str:
        script = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://magicfit.pushowl.com/home', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(4000);
  const body = await page.locator('body').innerText({ timeout: 10000 }).catch(() => '');
  if (/login|sign in|email|password/i.test(body)) {
    const emailField = page.locator('input[type=email], input[name*=email i], input[placeholder*=email i]').first();
    if (await emailField.count()) await emailField.fill(process.env.MAGICFIT_LOGIN_EMAIL || '');
    const passwordField = page.locator('input[type=password]').first();
    if (await passwordField.count()) await passwordField.fill(process.env.MAGICFIT_LOGIN_PASSWORD || '');
    const submit = page.getByRole('button', { name: /sign in|log in|login|continue|submit/i }).first();
    if (await submit.count()) await submit.click();
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await page.waitForTimeout(8000);
  }
  const cookies = await context.cookies();
  await browser.close();
  const cookie = cookies.find((row) => row.name === '__session');
  if (!cookie || !cookie.value) throw new Error('MagicFit login did not return a __session cookie');
  process.stdout.write(cookie.value);
})().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
"""
        env = dict(os.environ)
        env["MAGICFIT_LOGIN_EMAIL"] = email
        env["MAGICFIT_LOGIN_PASSWORD"] = password
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        cookie = completed.stdout.strip()
        if not cookie:
            raise RuntimeError("MagicFit node login did not return a __session cookie")
        return cookie

    @classmethod
    def from_env(cls) -> "MagicFitClient":
        if cookie := read_env_value("MAGICFIT_SESSION_COOKIE"):
            return cls(cookie)
        email = read_env_value("CHUMMER_EA_MAGICFIT_EMAIL") or read_env_value("MAGICFIT_EMAIL")
        password = read_env_value("CHUMMER_EA_MAGICFIT_PASSWORD") or read_env_value("MAGICFIT_PASSWORD")
        if not email or not password:
            raise RuntimeError("Missing MagicFit credentials")
        return cls(cls.login_via_playwright(email, password))

    def post(self, url: str, data: dict[str, str]) -> str:
        response = self.session.post(url, data=data, timeout=120)
        response.raise_for_status()
        return response.text

    def fetch_session_raw(self, session_id: str) -> str:
        response = self.session.get(f"{MAGICFIT_BASE}/agents/generate/sessions/{session_id}.data", timeout=120)
        response.raise_for_status()
        return response.text

    def create_image_session(self, prompt: str, aspect_ratio: str = "16:9") -> str:
        payload = self.post(
            f"{MAGICFIT_BASE}/agents/generate.data",
            {
                "generationType": "image",
                "prompt": prompt,
                "aspectRatio": aspect_ratio,
                "shouldEnhance": "true",
                "model": "openai/gpt-image-2",
                "resolution": "2K",
                "quality": "medium",
            },
        )
        match = re.search(r"/agents/generate/sessions/([a-z0-9]+)", payload)
        if not match:
            raise RuntimeError(f"MagicFit image session creation returned unexpected body: {payload[:500]}")
        return match.group(1)

    def wait_for_image(self, session_id: str, timeout_seconds: int) -> dict[str, str]:
        deadline = time.time() + timeout_seconds
        last_body = ""
        while time.time() < deadline:
            last_body = self.fetch_session_raw(session_id)
            urls = collect_urls(last_body, ("png", "webp", "jpg", "jpeg"))
            if urls:
                return {
                    "status": "COMPLETED",
                    "output_url": urls[0],
                    "generation_id": self.extract_generation_id_for_url(last_body, urls[0]) or self.extract_generation_id(last_body) or "image",
                    "session_payload": last_body,
                }
            if '"status","FAILED"' in last_body or '"FAILED"' in last_body:
                raise RuntimeError(f"MagicFit image generation failed for session {session_id}")
            time.sleep(5)
        raise TimeoutError(f"Timed out waiting for MagicFit image session {session_id}: {last_body[:500]}")

    @staticmethod
    def extract_generation_id(payload: str) -> str | None:
        for pattern in (
            r'"generationId","([a-z0-9]+)"',
            r'"id","([a-z0-9]{8,})"',
            r'},\"([a-z0-9]{8,})\",\["D"',
            r'},"([a-z0-9]{8,})",\["D"',
        ):
            match = re.search(pattern, payload)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def extract_generation_id_for_url(payload: str, output_url: str) -> str | None:
        escaped_url = re.escape(output_url).replace("/", r"(?:\\/|/)")
        patterns = (
            rf'"([a-z0-9]{{8,}})".{{0,1200}}{escaped_url}',
            rf'{escaped_url}.{{0,1200}}"([a-z0-9]{{8,}})"',
        )
        for pattern in patterns:
            match = re.search(pattern, payload, flags=re.S)
            if match:
                candidate = match.group(1)
                if candidate not in {"outputUrl", "imageUrl", "generationId"}:
                    return candidate
        for match in re.finditer(r'"([a-z0-9]{8,})"', payload):
            start = max(match.start() - 800, 0)
            end = min(match.end() + 800, len(payload))
            window = payload[start:end].replace("\\/", "/")
            if output_url in window:
                return match.group(1)
        return None

    def create_video_generation(
        self,
        *,
        session_id: str,
        parent_id: str,
        image_url: str,
        prompt: str,
        duration_seconds: int,
    ) -> str:
        payload = self.post(
            f"{MAGICFIT_BASE}/agents/generate/sessions/{session_id}.data",
            {
                "generationType": "video",
                "prompt": prompt,
                "aspectRatio": "16:9",
                "shouldEnhance": "true",
                "imageURLs": json.dumps([image_url]),
                "model": "bytedance/seedance-2.0-fast",
                "duration": str(duration_seconds),
                "videoResolution": "720p",
                "smartMode": "false",
                "lastFrameImageUrl": image_url,
                "_action": "generate",
                "parentId": parent_id,
            },
        )
        match = re.search(r'"generationId","([a-z0-9]+)"', payload)
        if match:
            return match.group(1)
        generation_id = self.extract_generation_id(payload)
        if generation_id:
            return generation_id
        raise RuntimeError(f"MagicFit video generation returned unexpected body: {payload[:500]}")

    def wait_for_video(self, session_id: str, submitted_at_ms: int, timeout_seconds: int) -> dict[str, str]:
        deadline = time.time() + timeout_seconds
        last_body = ""
        while time.time() < deadline:
            last_body = self.fetch_session_raw(session_id)
            urls = [
                url
                for url in collect_urls(last_body, ("mp4", "webm"))
                if url_timestamp(url) == 0 or url_timestamp(url) >= submitted_at_ms - 120000
            ]
            if urls:
                return {"status": "COMPLETED", "output_url": urls[0], "generation_id": self.extract_generation_id(last_body) or "video"}
            if '"status","FAILED"' in last_body or '"FAILED"' in last_body:
                raise RuntimeError(f"MagicFit video generation failed for session {session_id}")
            time.sleep(10)
        raise TimeoutError(f"Timed out waiting for MagicFit video session {session_id}: {last_body[:500]}")

    def download(self, url: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(url, stream=True, timeout=180) as response:
            response.raise_for_status()
            with path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)


def select_work(manifest: dict[str, Any], *, asset_id: str, only: set[str], max_scenes: int) -> list[SceneJob]:
    jobs: list[SceneJob] = []
    for asset in manifest.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if asset_id and str(asset.get("asset_id")) != asset_id:
            continue
        for scene in asset.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("id") or "")
            scene_number = str(scene.get("scene_number") or "").zfill(2)
            if only and scene_id not in only and scene_number not in only:
                continue
            jobs.append(SceneJob(asset=asset, scene=scene))
    return jobs[:max_scenes] if max_scenes > 0 else jobs


def render_scene(client: MagicFitClient, job: SceneJob, out_root: Path, *, force: bool, image_timeout: int, video_timeout: int) -> dict[str, Any]:
    asset = job.asset
    scene = job.scene
    mp4_path = scene_path(out_root, asset, scene, ".mp4")
    sidecar_path = scene_path(out_root, asset, scene, ".magicfit.json")
    if mp4_path.is_file() and sidecar_path.is_file() and not force:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))

    full_prompt = f"{scene.get('prompt') or ''} Negative constraints: {scene.get('negative_prompt') or ''}".strip()
    print(f"[image] {asset['asset_id']}/{scene['id']} submit", flush=True)
    session_id = client.create_image_session(full_prompt)
    image = client.wait_for_image(session_id, timeout_seconds=image_timeout)
    scene_path(out_root, asset, scene, ".image-session.txt").write_text(
        image.get("session_payload", ""),
        encoding="utf-8",
    )
    image_path = scene_path(out_root, asset, scene, ".source-image")
    image_suffix = Path(image["output_url"].split("?", 1)[0]).suffix or ".png"
    image_path = image_path.with_suffix(image_suffix)
    client.download(image["output_url"], image_path)
    scene_path(out_root, asset, scene, ".image.magicfit.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "image_generation_id": image.get("generation_id"),
                "image_output_url": image.get("output_url"),
                "image_file": str(image_path),
                "captured_at_utc": utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    motion_prompt = (
        f"{scene.get('prompt') or ''} "
        "Animate as a single grounded cinematic shot with subtle camera drift, real actor movement, "
        "practical light shifts, and no readable generated text."
    ).strip()
    print(f"[video] {asset['asset_id']}/{scene['id']} submit", flush=True)
    submitted_at_ms = int(time.time() * 1000)
    video_generation_id = client.create_video_generation(
        session_id=session_id,
        parent_id=image.get("generation_id") or "image",
        image_url=image["output_url"],
        prompt=motion_prompt,
        duration_seconds=int(scene.get("duration_seconds") or 9),
    )
    video = client.wait_for_video(session_id, submitted_at_ms=submitted_at_ms, timeout_seconds=video_timeout)
    client.download(video["output_url"], mp4_path)

    sidecar = {
        "provider": "MagicFit",
        "rendered_by": "EA MagicFit direct session API",
        "lane": asset.get("lane"),
        "asset_id": asset.get("asset_id"),
        "horizon": asset.get("horizon"),
        "scene_id": scene.get("id"),
        "scene_number": scene.get("scene_number"),
        "title": scene.get("title"),
        "duration_seconds_requested": int(scene.get("duration_seconds") or 9),
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "model": "Seedance 2.0 Fast",
        "session_id": session_id,
        "image_generation_id": image.get("generation_id"),
        "image_output_url": image["output_url"],
        "image_file": str(image_path),
        "video_generation_id": video_generation_id or video.get("generation_id"),
        "video_output_url": video["output_url"],
        "video_file": str(mp4_path),
        "source_prompt": full_prompt,
        "official_ip_assets_used": False,
        "direct_publish": False,
        "generated_at_utc": utc_now(),
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    print(f"[done] {asset['asset_id']}/{scene['id']} -> {mp4_path}", flush=True)
    return sidecar


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a MagicFit manifest through the direct session API.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--asset", default="")
    parser.add_argument("--only", default="")
    parser.add_argument("--max-scenes", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--continue-on-fail", action="store_true")
    parser.add_argument("--image-timeout-minutes", type=int, default=12)
    parser.add_argument("--video-timeout-minutes", type=int, default=18)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_root = Path(args.out_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    only = {item.strip() for item in args.only.split(",") if item.strip()}
    jobs = select_work(manifest, asset_id=args.asset, only=only, max_scenes=args.max_scenes)
    if not jobs:
        raise SystemExit("no scenes selected")
    client = MagicFitClient.from_env()
    receipts = []
    failures = []
    for job in jobs:
        try:
            receipts.append(
                render_scene(
                    client,
                    job,
                    out_root,
                    force=args.force,
                    image_timeout=args.image_timeout_minutes * 60,
                    video_timeout=args.video_timeout_minutes * 60,
                )
            )
        except Exception as exc:
            failure = {
                "asset_id": job.asset.get("asset_id"),
                "scene_id": job.scene.get("id"),
                "error": str(exc),
                "failed_at_utc": utc_now(),
            }
            failures.append(failure)
            failed_path = scene_path(out_root, job.asset, job.scene, ".api-failed.json")
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            failed_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
            print(f"[failed] {failure['asset_id']}/{failure['scene_id']}: {exc}", flush=True)
            if not args.continue_on_fail:
                raise
    audit = {
        "contract_name": "chummer.magicfit_manifest_api_render",
        "status": "pass" if receipts and not failures else "partial" if receipts else "fail",
        "generated_at_utc": utc_now(),
        "manifest": str(manifest_path),
        "out_root": str(out_root),
        "rendered_count": len(receipts),
        "failure_count": len(failures),
        "failures": failures,
    }
    (out_root / "MAGICFIT_API_RENDER_AUDIT.generated.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    return 0 if receipts or args.continue_on_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
