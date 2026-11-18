import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT / "ops/build-ghost-private-nonprod/deploy-first-provider-disabled-rook-lane.sh"
)
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def run_sourced(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"\n{body}', "test", str(SCRIPT_PATH)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_first_rollout_has_fail_closed_authorities_before_build() -> None:
    main = SCRIPT.split("main() {", 1)[1]
    build = main.index("build_under_limits")
    for required in (
        "validate_sources_and_authoritative_hub",
        "validate_external_secrets_without_output",
        "ensure_host_limits",
        "snapshot_runtime_authority",
        "verify_rendered_provider_disabled_compose",
        "validate_receipt_target",
        "create_rollback_refs",
    ):
        assert main.index(required) < build
    assert "git -C \"$repo_root\" ls-remote --exit-code origin refs/heads/main" in SCRIPT
    assert '"$remote_main" = "$CHUMMER_RUN_SERVICES_REVISION"' in SCRIPT
    assert "minimum_free_gib" in SCRIPT and ":-28}" in SCRIPT
    assert '"$minimum_free_gib" -ge 28' in SCRIPT
    assert "/proc/pressure/io" in SCRIPT
    assert "verify_candidate_source_labels" in SCRIPT
    for label in (
        "org.opencontainers.image.revision",
        "run.chummer.build-ghost.hub-revision",
        "run.chummer.build-ghost.core-revision",
        "run.chummer.build-ghost.hub-registry-revision",
        "run.chummer.build-ghost.ui-kit-revision",
        "run.chummer.build-ghost.media-factory-revision",
    ):
        assert label in SCRIPT


def test_first_rollout_is_provider_disabled_loopback_only() -> None:
    for gate in (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED",
    ):
        assert f'.environment.{gate} == \"false\"' in SCRIPT
    for empty in (
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_HMAC_KEY",
        "CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_HREF",
        "CHUMMER_BUILD_GHOST_MEETING_BROKER_API_TOKEN",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_API_KEY",
    ):
        assert empty in SCRIPT
    assert '.host_ip == \"127.0.0.1\"' in SCRIPT
    assert "loopback-port-must-remain-8443" in SCRIPT
    assert 'has(\"build-ghost-cloudflare-access-edge\") | not' in SCRIPT
    assert "COMPOSE_PROFILES=" in SCRIPT


def test_first_rollout_preserves_and_restores_without_deletion() -> None:
    assert "first-rollout-rollback-$nonce" in SCRIPT
    assert 'docker image tag "$old_presentation_image" "$presentation_image"' in SCRIPT
    assert 'docker image tag "$old_ai_image" "$ai_image"' in SCRIPT
    assert 'docker image tag "$old_edge_image" "$edge_image"' in SCRIPT
    assert "--force-recreate" in SCRIPT
    assert "rollback-restored volumes=preserved" in SCRIPT
    assert "positive_canary=passed" in SCRIPT
    assert "rook=text-fallback" in SCRIPT
    for forbidden in (
        "docker compose down",
        "docker volume rm",
        "docker image rm",
        "docker system prune",
        "docker volume prune",
    ):
        assert forbidden not in SCRIPT


def test_external_store_key_validation_accepts_only_canonical_distinct_32_bytes() -> None:
    valid = run_sourced(
        """
CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHUMMER_AI_INTERNAL_API_TOKEN=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
validate_external_secrets_without_output
printf 'accepted\\n'
"""
    )
    assert valid.returncode == 0, valid.stderr
    assert valid.stdout == "accepted\n"

    invalid = run_sourced(
        """
CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHUMMER_AI_INTERNAL_API_TOKEN=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY=not-canonical
validate_external_secrets_without_output
"""
    )
    assert invalid.returncode != 0
    assert "live-support-session-store-key-invalid" in invalid.stderr
    assert "not-canonical" not in invalid.stdout + invalid.stderr


def test_control_values_reject_reduced_disk_safety_margin() -> None:
    result = run_sourced(
        """
minimum_free_gib=27
max_io_full_avg10=10
poll_seconds=10
build_timeout_seconds=3600
up_timeout_seconds=900
validate_control_values
"""
    )
    assert result.returncode != 0
    assert "minimum-free-space-must-be-at-least-twenty-eight-gib" in result.stderr


FAKE_DOCKER = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
p=Path(os.environ['ROOK_FIXTURE_STATE']); s=json.loads(p.read_text()); a=sys.argv[1:]
with Path(os.environ['ROOK_FIXTURE_LOG']).open('a') as log: log.write(json.dumps(a)+'\n')
def save(): p.write_text(json.dumps(s))
def die(): raise SystemExit(87)
if a == ['fixture', 'activate']:
    for role,row in s['containers'].items():
        row['Id']=str(int(row['Id'][0])+3)*64
        row['Labels']['com.docker.compose.config-hash']='9'*64
    if s.get('change_version'): s['version']='5.3.1'
    if s.get('change_config'): s['hashes']['chummer-build-ghost-ai']='8'*64
    if s.get('change_file'): Path(s['change_file']).write_text('changed after snapshot\n')
    if s.get('change_ref'):
        for ref in list(s['tags']):
            if ref.startswith('chummer-build-ghost-ai:first-rollout-rollback-'): s['tags'][ref]='sha256:'+'8'*64
    save()
elif a[:1] == ['ps']:
    service=next((v.split('service=',1)[1] for v in a if 'service=' in v),None)
    for row in s['containers'].values():
        if row['Labels']['com.docker.compose.service']==service: print(row['Id'])
elif a[:2] == ['volume','inspect']: raise SystemExit(1)
elif a[:2] == ['image','tag']:
    s['tags'][a[3]]=s['tags'].get(a[2],a[2]); save()
elif a[:2] == ['image','inspect']:
    if a[2] not in s['tags']: raise SystemExit(1)
    print(s['tags'][a[2]])
elif a[:1] == ['inspect']:
    row=next((r for r in s['containers'].values() if r['Id']==a[1]),None)
    if row is None: die()
    fmt=a[-1]
    if fmt=='{{.Image}}': print(row['Image'])
    elif fmt=='{{json .Config.Labels}}': print(json.dumps(row['Labels']))
    elif fmt=='{{json .Mounts}}': print(json.dumps(row['Mounts']))
    elif fmt=='{{json .HostConfig.PortBindings}}': print(json.dumps(row['Ports']))
    elif fmt=='{{.State.Status}}': print('running')
    elif '.State.Health' in fmt: print('healthy')
    elif fmt.startswith('{{range .Mounts}}'):
        for mount in row['Mounts']:
            if mount['Type']=='volume' and '"'+mount['Destination']+'"' in fmt: print(mount['Name'])
    elif fmt.startswith('{{range .Config.Env}}{{if eq (printf '):
        import re
        match=re.fullmatch(r'\{\{range \.Config.Env\}\}\{\{if eq \(printf "%\.(\d+)s" \.\) "([A-Z_]+)="\}\}entry\{\{if eq \. "\2=(false)?"\}\}match\{\{end\}\}\{\{end\}\}\{\{end\}\}',fmt)
        if not match or int(match[1])!=len(match[2])+1: die()
        variable=match[2]; expected=variable+'='+(match[3] or '')
        values=s.get('gate_values_by_name',{}).get(variable,s.get('gate_values',[expected]))
        print(''.join('entry'+('match' if value==expected else '') for value in values if value.startswith(variable+'=')))
        if s.get('environment_inspect_exit'):
            print('synthetic-do-not-print',file=sys.stderr)
            raise SystemExit(s['environment_inspect_exit'])
    else: die() # No Config.Env values or whole-container dump.
elif a[:3] == ['compose','version','--short']:
    if s.get('oversized'):
        import signal
        Path(os.environ['ROOK_FIXTURE_CHILD_PID']).write_text(str(os.getpid()))
        stream=sys.stderr if s['oversized']=='stderr' else sys.stdout
        stream.write('x'*(2*1024*1024+1)); stream.flush(); signal.pause()
    print(s['version'])
elif a[:1] == ['compose']:
    recipe=a[a.index('--file')+1]
    if os.environ.get('COMPOSE_PROFILES')!='' or os.environ.get('COMPOSE_DISABLE_ENV_FILE')!='true': die()
    if 'COMPOSE_FILE' in os.environ or 'COMPOSE_ENV_FILES' in os.environ: die()
    if os.environ.get('CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE')!=s['prior_contract']: die()
    if '--env-file' not in a or a[a.index('--env-file')+1]!='/dev/null': die()
    if 'config' in a:
        service=a[-1]
        digest=s['hashes'].get(service)
        if digest is None or recipe != s['prior_recipe']: die()
        print(service+' '+digest)
    elif 'up' in a:
        if s.get('fail_up'): raise SystemExit(8)
        for role,row in s['containers'].items():
            row['Id']=str(int(row['Id'][0])+3)*64
            row['Image']=s['tags'][s['image_refs'][role]]
            row['Labels']['com.docker.compose.project.config_files']=recipe
            row['Labels']['com.docker.compose.project.working_dir']=a[a.index('--project-directory')+1]
            row['Labels']['com.docker.compose.config-hash']=s['hashes'][row['Labels']['com.docker.compose.service']] if recipe==s['prior_recipe'] else '9'*64
        if s.get('bad_restore'): s['containers']['ai']['Labels']['com.docker.compose.config-hash']='8'*64
        if s.get('bad_mount'): s['containers']['ai']['Mounts'][0]['Name']='substituted-trust'
        save()
    else: die()
else: die()
'''


def rollback_fixture(tmp_path, recipe_change=None):
    """Synthetic private history; never a deployment or provider receipt."""
    prior = tmp_path / "prior"
    candidate = tmp_path / "candidate"
    prior.mkdir(mode=0o700)
    candidate.mkdir(mode=0o700)
    source = prior / "ops/build-ghost-private-nonprod"
    source.mkdir(parents=True)
    caddy = source / "Caddyfile"
    caddy.write_text("# fixture prior Caddy bytes\n")
    contract = source / "tough-tongue-read-only-binding-contract.unconfigured.json"
    contract.write_text('{"schema":"chummer.build_ghost.tough_tongue.read_only_binding_contract.unconfigured.v2","status":"blocked"}\n')
    services = {"presentation":"chummer-build-ghost-presentation", "ai":"chummer-build-ghost-ai", "edge":"build-ghost-private-edge"}
    image_refs = {"presentation":"chummer-build-ghost-presentation:private-nonprod", "ai":"chummer-build-ghost-ai:private-nonprod", "edge":"caddy:2.10.2-alpine"}
    project = "chummer-build-ghost-private-nonprod"
    model = {"name":project, "services": {name:{"image":image_refs[role], "environment":{}, "volumes":[]} for role,name in services.items()}}
    model['services'][services['presentation']]['environment']['CHUMMER_AI_INTERNAL_API_TOKEN']='${CHUMMER_AI_INTERNAL_API_TOKEN:?operator supplied}'
    model['services'][services['ai']]['environment']={key:'false' for key in (
        'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED',
        'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED',
        'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED',
        'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED')}
    model['services'][services['presentation']]['volumes']=['packet:/app/state']
    model['services'][services['ai']]['volumes']=['trust:/caddy-trust:ro']
    model['services'][services['ai']]['secrets']=[{'source':'build-ghost-tough-tongue-read-only-binding-contract','target':'tough-tongue-read-only-binding-contract.json','mode':256}]
    model['secrets']={'build-ghost-tough-tongue-read-only-binding-contract':{'file':'${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE:-./ops/build-ghost-private-nonprod/tough-tongue-read-only-binding-contract.unconfigured.json}'}}
    model['volumes']={name:{} for name in ('packet','trust','data','config')}
    model['services'][services['edge']]['volumes']=['./ops/build-ghost-private-nonprod/Caddyfile:/etc/caddy/Caddyfile:ro','data:/data','config:/config']
    recipe = prior / 'docker-compose.build-ghost-private-nonprod.yml'
    source_text=json.dumps(model,indent=2)+'\n' # JSON is also an exact YAML recipe.
    recipe.write_text(recipe_change(source_text) if recipe_change else source_text)
    (candidate / recipe.name).write_text('# deliberately different candidate with a new journal volume\n')
    env = {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    for args in (['init','-q'], ['add','.'], ['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Synthetic prior deployment source']):
        subprocess.run(['git','-C',str(prior),*args],env=env,check=True,capture_output=True)
    head=subprocess.check_output(['git','-C',str(prior),'rev-parse','HEAD'],env=env,text=True).strip()
    tree=subprocess.check_output(['git','-C',str(prior),'rev-parse','HEAD^{tree}'],env=env,text=True).strip()
    def digest(path): return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
    def file_binding(path): return {'sha256':digest(path),'sizeBytes':path.stat().st_size,'pathSha256':'sha256:'+hashlib.sha256(str(path).encode()).hexdigest(),'matchesAttesterSource':True}
    containers={}
    rows={}
    volumes={'presentation': [('/app/state','packet')], 'ai':[('/caddy-trust','trust')], 'edge':[('/data','data'),('/config','config')]}
    for index,(role,service) in enumerate(services.items(),1):
        mounts=[{'Type':'volume','Destination':dest,'Name':name,'RW':role!='ai'} for dest,name in volumes[role]]
        if role=='edge': mounts.append({'Type':'bind','Destination':'/etc/caddy/Caddyfile','Source':str(caddy),'RW':False})
        if role=='ai': mounts.append({'Type':'bind','Destination':'/run/secrets/tough-tongue-read-only-binding-contract.json','Source':str(contract),'RW':False})
        labels={'com.docker.compose.project':project,'com.docker.compose.service':service,'com.docker.compose.project.config_files':str(recipe),'com.docker.compose.project.working_dir':str(prior),'com.docker.compose.version':'2.39.2','com.docker.compose.config-hash':str(index+3)*64}
        image='sha256:'+str(index)*64
        containers[role]={'Id':str(index)*64,'Image':image,'Labels':labels,'Mounts':mounts,'Ports':{'443/tcp':[{'HostIp':'127.0.0.1','HostPort':'8443'}]} if role=='edge' else {}}
        rows[role]={'containerId':'sha256:'+str(index)*64,'image':{'imageId':image},'composeConfigHash':str(index+3)*64,'composeSource':file_binding(recipe),'sourceRevisions':{'hub':head}}
    receipt={'schema':'chummer.build_ghost.private_nonprod_deployment_attestation.v1','project':project,'status':'deployed-private-nonprod','claim':'deployed-private-nonprod','blockers':[], 'providerActivationAuthorized':False,'externalMutationPerformed':False,'runtimeStableDuringAttestation':True,
        'sources':{'git':{'head':head,'tree':tree,'clean':True},'compose':file_binding(recipe),'caddy':file_binding(caddy)},
        'runtime':{'project':project,'containers':rows,'confinement':{'loopbackOnly':True,'caddySource':file_binding(caddy)},'providerGates':{'allLiteralFalse':True}},
        'evidenceDigestContract':'sha256-canonical-json-without-evidenceDigest'}
    receipt['evidenceDigest']='sha256:'+hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    evidence=tmp_path/'prior-attestation.json'; evidence.write_text(json.dumps(receipt,indent=2)+'\n'); evidence.chmod(0o600)
    state={'containers':containers,'prior_recipe':str(recipe),'prior_contract':str(contract),'version':'2.39.2','hashes':{services[r]:v['composeConfigHash'] for r,v in rows.items()},'image_refs':image_refs,'tags':{image_refs[r]:v['Image'] for r,v in containers.items()}}
    state_path=tmp_path/'state.json'; state_path.write_text(json.dumps(state))
    fakebin=tmp_path/'bin'; fakebin.mkdir(); docker=fakebin/'docker'; docker.write_text(FAKE_DOCKER); docker.chmod(0o700)
    env.update(PATH=str(fakebin)+':/usr/bin:/bin',ROOK_FIXTURE_STATE=str(state_path),ROOK_FIXTURE_LOG=str(tmp_path/'calls.jsonl'),CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_FILE=str(evidence),CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_SHA256=hashlib.sha256(evidence.read_bytes()).hexdigest(),CHUMMER_BUILD_GHOST_ROLLBACK_PROJECT_DIRECTORY=str(prior),CHUMMER_BUILD_GHOST_ROLLBACK_COMPOSE_FILE=str(recipe),CHUMMER_AI_INTERNAL_API_TOKEN='synthetic-do-not-print-service-token')
    return {'env':env,'state':state_path,'recipe':recipe,'caddy':caddy,'contract':contract,'candidate':candidate,'receipt':evidence,'log':tmp_path/'calls.jsonl'}


def run_rollback_case(fixture, body=''):
    text = r'''
source "$1"
repo_root="$2"
compose_file="$repo_root/docker-compose.build-ghost-private-nonprod.yml"
CHUMMER_RUN_SERVICES_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
snapshot_runtime_authority
create_rollback_refs
docker fixture activate
activation_started=true
''' + body + '\nrollback_if_needed\n'
    return subprocess.run(['bash','-c',text,'fixture',str(SCRIPT_PATH),str(fixture['candidate'])],env=fixture['env'],capture_output=True,text=True,timeout=15)


def test_rollback_restores_prior_configuration_not_candidate(tmp_path):
    fixture=rollback_fixture(tmp_path)
    result=run_rollback_case(fixture)
    assert result.returncode==0, result.stderr
    state=json.loads(fixture['state'].read_text())
    assert all(row['Labels']['com.docker.compose.config-hash']==state['hashes'][row['Labels']['com.docker.compose.service']] for row in state['containers'].values()), 'old images were recreated with candidate configuration, not the prior recipe'
    assert 'rollback-restored volumes=preserved' in result.stderr
    calls=[json.loads(line) for line in fixture['log'].read_text().splitlines()]
    ups=[call for call in calls if call[:1]==['compose'] and 'up' in call]
    assert len(ups)==1 and ups[0][ups[0].index('--file')+1]==str(fixture['recipe'])
    assert 'synthetic-do-not-print' not in result.stdout+result.stderr+fixture['log'].read_text()
    assert all('--env-file' in call and call[call.index('--env-file')+1]=='/dev/null' for call in calls if call[:1]==['compose'] and ('config' in call or 'up' in call))


def docker_calls(fixture):
    return [json.loads(line) for line in fixture['log'].read_text().splitlines()]


def patch_state(fixture, **values):
    state=json.loads(fixture['state'].read_text())
    state.update(values)
    fixture['state'].write_text(json.dumps(state))


def repin_synthetic_receipt(fixture, mutate):
    """Author synthetic negative fixtures, never refresh real historical evidence."""
    receipt=json.loads(fixture['receipt'].read_text())
    mutate(receipt)
    receipt.pop('evidenceDigest')
    receipt['evidenceDigest']='sha256:'+hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    fixture['receipt'].write_text(json.dumps(receipt,indent=2)+'\n')
    fixture['env']['CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_SHA256']=hashlib.sha256(fixture['receipt'].read_bytes()).hexdigest()


@pytest.mark.parametrize('fault', [
    'missing-receipt','unpinned-receipt','receipt-byte-drift','receipt-digest-drift',
    'missing-prior','missing-caddy','missing-contract','recipe-byte-drift','caddy-byte-drift','contract-byte-drift',
    'recipe-symlink','caddy-symlink','contract-symlink','writable-recipe',
    'no-independent-git','upward-git-discovery','attester-only-compose','false-compose-match','false-caddy-match',
    'newly-hashed-current-caddy','git-replaced-current-caddy','partial-runtime','unhealthy-history',
    'image-drift','container-drift','config-drift','label-config-drift','tool-drift',
    'historical-size-float',
])
def test_prior_authority_failure_precedes_any_docker_mutation(tmp_path, fault):
    fixture=rollback_fixture(tmp_path)
    if fault=='missing-receipt': fixture['receipt'].unlink()
    elif fault=='unpinned-receipt': fixture['env'].pop('CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_SHA256')
    elif fault=='receipt-byte-drift': fixture['receipt'].write_text(fixture['receipt'].read_text()+' ')
    elif fault=='receipt-digest-drift':
        data=json.loads(fixture['receipt'].read_text()); data['evidenceDigest']='sha256:'+'0'*64
        fixture['receipt'].write_text(json.dumps(data)); fixture['env']['CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_SHA256']=hashlib.sha256(fixture['receipt'].read_bytes()).hexdigest()
    elif fault.startswith('missing-') and fault in ('missing-prior','missing-caddy','missing-contract'):
        fixture[{'missing-prior':'recipe','missing-caddy':'caddy','missing-contract':'contract'}[fault]].unlink()
    elif fault.endswith('-byte-drift'):
        fixture[fault.removesuffix('-byte-drift')].write_text('substituted current bytes\n')
    elif fault.endswith('-symlink'):
        path=fixture[fault.removesuffix('-symlink')]; backup=path.with_suffix('.retained'); path.rename(backup); path.symlink_to(backup)
    elif fault=='writable-recipe': fixture['recipe'].chmod(0o666)
    elif fault=='no-independent-git': (fixture['recipe'].parent/'.git').rename(fixture['recipe'].parent/'.git-retained')
    elif fault=='upward-git-discovery':
        (fixture['recipe'].parent/'.git').rename(tmp_path/'.git')
    elif fault=='attester-only-compose':
        repin_synthetic_receipt(fixture,lambda receipt: receipt['runtime']['containers']['presentation']['composeSource'].update(matchesAttesterSource=False,sha256='',sizeBytes=0))
    elif fault=='false-compose-match':
        repin_synthetic_receipt(fixture,lambda receipt: receipt['runtime']['containers']['presentation']['composeSource'].update(matchesAttesterSource=False))
    elif fault=='false-caddy-match':
        repin_synthetic_receipt(fixture,lambda receipt: receipt['runtime']['confinement']['caddySource'].update(matchesAttesterSource=False))
    elif fault in ('newly-hashed-current-caddy','git-replaced-current-caddy'):
        fixture['caddy'].write_text('# newly hashed current bytes are not historical proof\n')
        def rehash_current(receipt):
            for binding in (receipt['sources']['caddy'],receipt['runtime']['confinement']['caddySource']):
                binding.update(sha256='sha256:'+hashlib.sha256(fixture['caddy'].read_bytes()).hexdigest(),sizeBytes=fixture['caddy'].stat().st_size)
        repin_synthetic_receipt(fixture,rehash_current)
        if fault=='git-replaced-current-caddy':
            root=fixture['recipe'].parent
            old=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD:ops/build-ghost-private-nonprod/Caddyfile'],text=True).strip()
            new=subprocess.check_output(['git','-C',str(root),'hash-object','-w',str(fixture['caddy'])],text=True).strip()
            subprocess.run(['git','-C',str(root),'replace',old,new],check=True,capture_output=True)
            assert subprocess.check_output(['git','-C',str(root),'show','HEAD:ops/build-ghost-private-nonprod/Caddyfile'])==fixture['caddy'].read_bytes()
    elif fault=='partial-runtime':
        repin_synthetic_receipt(fixture,lambda receipt: receipt['runtime']['containers'].pop('ai'))
    elif fault=='unhealthy-history':
        repin_synthetic_receipt(fixture,lambda receipt: receipt.update(status='blocked',claim=None,blockers=['canaries-skipped-unsafe-runtime']))
    elif fault=='historical-size-float':
        repin_synthetic_receipt(fixture,lambda receipt: receipt['sources']['compose'].update(sizeBytes=float(receipt['sources']['compose']['sizeBytes'])))
    else:
        state=json.loads(fixture['state'].read_text())
        if fault=='tool-drift': state['version']='5.3.1'
        elif fault=='config-drift': state['hashes']['chummer-build-ghost-ai']='8'*64
        elif fault=='label-config-drift': state['containers']['ai']['Labels']['com.docker.compose.config-hash']='8'*64
        elif fault=='container-drift': state['containers']['ai']['Id']='8'*64
        elif fault=='image-drift': state['containers']['ai']['Image']='sha256:'+'8'*64
        else: raise AssertionError(fault)
        fixture['state'].write_text(json.dumps(state))
    result=run_rollback_case(fixture)
    assert result.returncode!=0
    assert 'rollback-restored' not in result.stdout+result.stderr
    assert not any(call[:2]==['image','tag'] or 'up' in call or call[:1]==['fixture'] for call in docker_calls(fixture))
    assert 'synthetic-do-not-print' not in result.stdout+result.stderr+fixture['log'].read_text()


def recipe_with_feature(source, feature):
    model=json.loads(source)
    if feature in ('include','configs'): model[feature]={'file':'/must-not-be-read'}
    elif feature=='external-secret': model['secrets']['other']={'file':'/must-not-be-read'}
    elif feature=='volume-driver-bind': model['volumes']['packet']={'driver_opts':{'device':'/must-not-be-read','type':'none','o':'bind'}}
    else: model['services']['chummer-build-ghost-ai'][feature]={'file':'/must-not-be-read'}
    return json.dumps(model)


@pytest.mark.parametrize('change', [
    *[lambda source,feature=feature: recipe_with_feature(source,feature) for feature in ('include','configs','env_file','extends','external-secret','volume-driver-bind')],
    lambda source: source.replace('"name":', '"name":"duplicate", "name":',1),
    lambda source: 'name: &project chummer-build-ghost-private-nonprod\nservices: *project\n',
    lambda source: 'name: !unsafe chummer-build-ghost-private-nonprod\n',
    lambda source: 'name: chummer-build-ghost-private-nonprod\nservices:\n  <<: {}\n',
])
def test_unsupported_authenticated_recipe_fails_before_compose_evaluation(tmp_path, change):
    fixture=rollback_fixture(tmp_path,change)
    result=run_rollback_case(fixture)
    assert result.returncode!=0
    assert not any(call[:1]==['compose'] or call[:2]==['image','tag'] for call in docker_calls(fixture))


@pytest.mark.parametrize('fault', ['change_version','change_config','recipe','caddy','contract'])
def test_post_activation_prior_drift_never_claims_restored(tmp_path, fault):
    fixture=rollback_fixture(tmp_path)
    patch_state(fixture,**({fault:True} if fault.startswith('change_') else {'change_file':str(fixture[fault])}))
    result=run_rollback_case(fixture)
    assert result.returncode!=0
    assert 'rollback-started' in result.stderr and 'rollback-restored' not in result.stderr
    assert not any(call[:1]==['compose'] and 'up' in call for call in docker_calls(fixture))


@pytest.mark.parametrize('fault', ['fail_up','bad_restore','bad_mount','change_ref'])
def test_failed_or_inexact_rollback_never_emits_restored_rollout_receipt(tmp_path, fault):
    fixture=rollback_fixture(tmp_path)
    patch_state(fixture,**{fault:True})
    output=tmp_path/'rollout.json'; fixture['env']['CHUMMER_BUILD_GHOST_FIRST_ROLLOUT_RECEIPT']=str(output)
    result=run_rollback_case(fixture,'trap on_exit EXIT\nfailure_stage=synthetic-candidate-failure\nexit 1')
    assert result.returncode!=0
    assert 'rollback-restored' not in result.stderr
    receipt=json.loads(output.read_text())
    assert receipt['contract_name']=='chummer.build_ghost.first_provider_disabled_rook_rollout.v1'
    assert receipt['outcome']=='rollback-failed-volumes-preserved'
    assert receipt['status']=='failed' and receipt['volumes']['deleted'] is False
    assert receipt['provider_execution_enabled'] is False
    if fault=='change_ref':
        state=json.loads(fixture['state'].read_text())
        assert state['tags'][state['image_refs']['ai']]=='sha256:'+'2'*64
        assert not any(call[:2]==['image','tag'] and call[2].startswith('chummer-build-ghost-ai:first-rollout-rollback-') and call[3]==state['image_refs']['ai'] for call in docker_calls(fixture))


def test_successful_rollback_receipt_still_records_failed_candidate(tmp_path):
    fixture=rollback_fixture(tmp_path)
    output=tmp_path/'rollout.json'; fixture['env']['CHUMMER_BUILD_GHOST_FIRST_ROLLOUT_RECEIPT']=str(output)
    result=run_rollback_case(fixture,'trap on_exit EXIT\nfailure_stage=synthetic-candidate-failure\nexit 1')
    assert result.returncode!=0
    receipt=json.loads(output.read_text())
    assert receipt['status']=='failed' and receipt['outcome']=='rollback-restored-volumes-preserved'
    assert receipt['provider_execution_enabled'] is False and receipt['volumes']['deleted'] is False


def test_prior_and_rollback_compose_ignore_ambient_file_and_profile_selectors(tmp_path):
    fixture=rollback_fixture(tmp_path)
    fixture['env'].update(COMPOSE_FILE='/must-not-be-read',COMPOSE_ENV_FILES='/must-not-be-read',
                          COMPOSE_PROFILES='cloudflare-access-ingress',
                          CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE='/must-not-be-read')
    result=run_rollback_case(fixture)
    assert result.returncode==0, result.stderr
    # The executable fixture rejects each config/up unless both phases provide
    # explicit dotenv/profile isolation and the exact prior public contract.
    assert 'rollback-restored' in result.stderr


@pytest.mark.parametrize('values,accepted',[(None,True),([],False),(['false','false'],False),(['false','true'],False),(['true','false'],False)])
def test_runtime_provider_inspection_returns_only_allowlisted_matches(tmp_path, values, accepted):
    fixture=rollback_fixture(tmp_path)
    if values is not None:
        patch_state(fixture,gate_values=['CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED='+value for value in values])
    result=subprocess.run(['bash','-c','source "$1"\nassert_provider_disabled_runtime','fixture',str(SCRIPT_PATH)],env=fixture['env'],capture_output=True,text=True,timeout=15)
    assert (result.returncode==0) is accepted
    calls=docker_calls(fixture)
    env_calls=[call for call in calls if '.Config.Env' in call[-1]]
    assert env_calls
    for call in env_calls:
        assert '}}entry{{if eq . ' in call[-1]
        assert '{{println .}}' not in call[-1]
    assert 'synthetic-do-not-print' not in result.stdout+result.stderr+fixture['log'].read_text()


def test_runtime_provider_inspection_rejects_failed_inspect_with_matching_output(tmp_path):
    fixture=rollback_fixture(tmp_path)
    patch_state(fixture,environment_inspect_exit=42)
    result=subprocess.run(['bash','-c','source "$1"\nassert_provider_disabled_runtime','fixture',str(SCRIPT_PATH)],env=fixture['env'],capture_output=True,text=True,timeout=15)
    assert result.returncode != 0
    assert 'synthetic-do-not-print' not in result.stdout+result.stderr


def test_validator_ignores_ambient_python_wrapper_and_host_interpreter_selector(tmp_path):
    fixture=rollback_fixture(tmp_path)
    marker=tmp_path/'must-not-execute'
    executable=Path(fixture['env']['PATH'].split(':')[0])/'python3'
    executable.write_text('#!/bin/sh\nprintf wrong > "'+str(marker)+'"\nexit 127\n'); executable.chmod(0o700)
    fixture['env']['HOST_REAL_PYTHON3']=str(executable)
    result=run_rollback_case(fixture)
    assert result.returncode==0, result.stderr
    assert not marker.exists()
    assert '[ -x /usr/bin/python3 ]' in SCRIPT
    assert '/usr/bin/python3 -I -c' in SCRIPT and 'system-pyyaml-missing' in SCRIPT


@pytest.mark.parametrize('stream',['stdout','stderr'])
def test_oversized_tool_output_is_bounded_and_child_reaped_before_mutation(tmp_path, stream):
    fixture=rollback_fixture(tmp_path)
    marker=tmp_path/'child.pid'; fixture['env']['ROOK_FIXTURE_CHILD_PID']=str(marker)
    patch_state(fixture,oversized=stream)
    result=run_rollback_case(fixture)
    assert result.returncode!=0
    assert len(result.stdout+result.stderr)<1024
    pid=int(marker.read_text())
    with pytest.raises(ProcessLookupError): os.kill(pid,0)
    assert not any(call[:2]==['image','tag'] or 'up' in call for call in docker_calls(fixture))


def test_tool_deadline_kills_and_reaps_actual_child_without_waiting_for_timeout():
    # Invoke the actual bounded command runner; only its clock is controlled.
    # A real child waits for a signal and must have been reaped at the boundary.
    code=r'''
import importlib.util, os, subprocess, sys
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('prior',sys.argv[1])
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
original=subprocess.Popen; children=[]
def observe(*args,**kwargs):
    child=original(*args,**kwargs); children.append(child); return child
with patch.object(module.subprocess,'Popen',observe), patch.object(module.time,'monotonic',side_effect=[0,31]):
    try: module.command(['/usr/bin/python3','-I','-c','import signal; signal.pause()'])
    except ValueError: pass
    else: raise AssertionError('deadline was ignored')
assert len(children)==1 and children[0].returncode is not None
try: os.kill(children[0].pid,0)
except ProcessLookupError: pass
else: raise AssertionError('timed out child was not reaped')
'''
    result=subprocess.run(['/usr/bin/python3','-I','-c',code,str(SCRIPT_PATH.with_name('verify-prior-rollout-authority.py'))],capture_output=True,text=True,timeout=5)
    assert result.returncode==0, result.stderr
