"""Focused plumbing tests; synthetic metadata is not native release evidence."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from test_release_shelf_generation import MODULE, ROOT


PROFILE = 'windows_unsigned_preview_v1'


def candidate(root):
    (root / 'files').mkdir(parents=True)
    name = 'chummer-avalonia-win-x64-installer.exe'
    data = b'synthetic-policy-test-only'
    (root / 'files' / name).write_bytes(data)
    row = {'id': 'avalonia-win-x64-installer', 'artifactId': 'avalonia-win-x64-installer',
           'fileName': name, 'downloadUrl': f'/downloads/files/{name}', 'url': f'/downloads/files/{name}',
           'sha256': hashlib.sha256(data).hexdigest(), 'sizeBytes': len(data), 'installAccessClass': 'open_public'}
    base = {'version': 'synthetic-test', 'channel': 'preview', 'status': 'published',
            'publishedAt': '2026-11-09T00:00:00Z', 'publicationProfile': PROFILE,
            'publicationScope': {'linux': 'outside_profile'}, 'platformScope': 'windows_only',
            'message': 'Unsigned Windows-only preview. Manual Windows and SR6 qualification remains incomplete.',
            'supportabilityState': 'review_required', 'rolloutState': 'public_release_review_required'}
    for name, key in ((MODULE.CANONICAL_MANIFEST, 'artifacts'), (MODULE.COMPATIBILITY_MANIFEST, 'downloads')):
        (root / name).write_text(json.dumps({**base, key: [row]}))
    return root


def test_profile_uses_existing_immutable_generation_and_preserves_disclosure(tmp_path):
    source = candidate(tmp_path / 'candidate')
    pointer = MODULE.prepare_layout(source, tmp_path / 'prepared', generation_id='synthetic-windows-preview')
    generation = tmp_path / 'prepared/generations/synthetic-windows-preview'
    MODULE.verify_generation(generation, pointer)
    payload = json.loads((generation / MODULE.CANONICAL_MANIFEST).read_text())
    assert payload['publicationProfile'] == PROFILE
    assert payload['publicationScope']['linux'] == 'outside_profile'
    assert payload['artifacts'][0]['downloadUrl'].startswith('/downloads/g/synthetic-windows-preview/files/')
    # Exercise the shipped runtime contract, including its real review-required floor.
    privacy = MODULE.load_privacy_launch_gate_contract()
    assert privacy['contractVersion'] == 2
    assert privacy['blocksLaunch'] is True
    floored = MODULE.apply_current_release_supportability_floor(payload, privacy)
    assert floored['supportabilityState'] == 'review_required'
    assert floored['message'] in floored['supportabilitySummary']
    assert not MODULE._is_bounded_preview_ready_profile(payload)


@pytest.mark.parametrize('name', ['files/private-key.pem', 'proof/raw.json', 'startup-smoke/private.log'])
def test_profile_does_not_copy_unselected_private_files(tmp_path, name):
    source = candidate(tmp_path / 'candidate')
    private = source / name
    private.parent.mkdir(exist_ok=True)
    private.write_text('synthetic test only')
    with pytest.raises(MODULE.ReleaseShelfError, match='unselected public file'):
        MODULE.copy_candidate(source, tmp_path / 'generation')


def test_profile_pair_disagreement_cannot_be_sealed(tmp_path):
    source = candidate(tmp_path / 'candidate')
    path = source / MODULE.COMPATIBILITY_MANIFEST
    payload = json.loads(path.read_text())
    payload.pop('publicationProfile')
    path.write_text(json.dumps(payload))
    with pytest.raises(MODULE.ReleaseShelfError, match='disagree|unnamed'):
        MODULE.copy_candidate(source, tmp_path / 'generation')


@pytest.mark.parametrize('script', ['generate-releases-manifest.sh', 'publish-download-bundle.sh'])
def test_shell_profile_rejects_skip_before_side_effects(tmp_path, script):
    result = subprocess.run(['bash', str(ROOT / 'scripts' / script)], cwd=tmp_path,
                            env={**os.environ, 'CHUMMER_PUBLIC_PUBLICATION_PROFILE': PROFILE,
                                 'CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER': 'true'},
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert 'skip flags are forbidden' in result.stderr
    assert not list(tmp_path.iterdir())


def test_download_view_shows_the_profile_disclosure():
    view = (ROOT / 'Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml').read_text()
    assert 'data-publication-profile="windows_unsigned_preview_v1">@Model.Manifest.Message</p>' in view


@pytest.mark.parametrize('script', ['generate-releases-manifest.sh', 'publish-download-bundle.sh'])
@pytest.mark.parametrize('flag', ['CHUMMER_VERIFY_SKIP_STARTUP_SMOKE_FILTER',
    'CHUMMER_VERIFY_ALLOW_SKIPPED_STARTUP_SMOKE', 'CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE',
    'CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS', 'CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS'])
def test_profile_cannot_disable_windows_checks(tmp_path, script, flag):
    result = subprocess.run(['bash', str(ROOT / 'scripts' / script)], cwd=tmp_path,
        env={**os.environ, 'CHUMMER_PUBLIC_PUBLICATION_PROFILE': PROFILE, flag: 'true'},
        text=True, capture_output=True)
    assert result.returncode != 0
    assert 'skip flags are forbidden' in result.stderr or 'cannot disable' in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('mutation', ['unknown', 'missing_pair', 'mixed_mode', 'supported', 'non_preview'])
def test_invalid_profiles_cannot_be_prepared(tmp_path, mutation):
    source = candidate(tmp_path / 'candidate')
    path = source / MODULE.CANONICAL_MANIFEST
    payload = json.loads(path.read_text())
    if mutation == 'unknown': payload['publicationProfile'] = 'unapproved'
    elif mutation == 'missing_pair': (source / MODULE.COMPATIBILITY_MANIFEST).unlink()
    elif mutation == 'mixed_mode': payload['projectionProfile'] = 'another-mode'
    elif mutation == 'supported': payload['supportabilityState'] = 'preview_supported'
    elif mutation == 'non_preview': payload['channel'] = 'stable'
    path.write_text(json.dumps(payload))
    with pytest.raises(MODULE.ReleaseShelfError):
        MODULE.prepare_layout(source, tmp_path / 'prepared', generation_id='synthetic-invalid')


def test_privacy_reader_matches_current_runtime_contract_and_rejects_old_version():
    contract = MODULE.load_privacy_launch_gate_contract()
    runtime = (ROOT / 'Chummer.Run.Api/Services/PrivacyLaunchGate.cs').read_text()
    assert f'public const int ContractVersion = {contract["contractVersion"]};' in runtime
    contract['contractVersion'] = 1
    with pytest.raises(MODULE.ReleaseShelfError):
        MODULE._validate_privacy_launch_gate_contract(contract)


def test_preview_publisher_refuses_legacy_mutable_shelf(tmp_path):
    result = subprocess.run(['bash', str(ROOT / 'scripts/publish-download-bundle.sh'),
        str(tmp_path / 'bundle'), str(tmp_path / 'shelf')], cwd=tmp_path,
        env={**os.environ, 'CHUMMER_PUBLIC_PUBLICATION_PROFILE': PROFILE,
             'CHUMMER_RELEASE_SHELF_LAYOUT_V1_ENABLED': 'false'}, text=True, capture_output=True)
    assert result.returncode != 0
    assert 'requires immutable generation publication' in result.stderr
    assert not (tmp_path / 'shelf').exists()


def test_preview_candidate_root_cannot_be_a_symlink(tmp_path):
    source = candidate(tmp_path / 'candidate')
    alias = tmp_path / 'alias'
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(MODULE.ReleaseShelfError, match='symlink'):
        MODULE.copy_candidate(alias, tmp_path / 'generation')
